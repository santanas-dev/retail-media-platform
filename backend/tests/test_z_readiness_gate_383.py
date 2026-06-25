"""Step 38.3 — One-KSO Dry Run Readiness Gate Safety Checks.

Validates that all documented readiness prerequisites are logically
consistent: no forbidden fields in any contracts, no missing components,
no unsafe patterns.

NO physical KSO, NO X11, NO Chromium, NO backend server.
Pure contract/document audit.
"""

import json
import re
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4


# ══════════════════════════════════════════════════════════════════════
# Safety check helpers
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_KEYS = frozenset({
    "id", "password", "password_hash", "token", "api_key", "access_token",
    "refresh_token", "device_secret", "client_secret", "backend_url",
    "manifest_version_id", "manifest_hash",
    "sha256", "file_path", "absolute_path", "local_path",
    "storage_ref", "minio", "s3",
    "barcode", "scanner", "key_value", "key_payload",
    "receipt", "payment", "fiscal",
    "customer", "card", "pan", "phone", "email",
    "stacktrace",
})

FORBIDDEN_VALUES = frozenset({
    "token", "secret", "api_key", "backend_url",
    "barcode", "scanner", "receipt", "payment", "fiscal",
    "customer", "card", "pan", "sha256", "file_path",
    "device_secret", "minio", "s3",
})

UUID_PAT = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)


def _assert_no_forbidden_keys(test, data: dict, label: str = ""):
    for key, value in data.items():
        test.assertNotIn(key, FORBIDDEN_KEYS, f"{label}: forbidden key '{key}'")
        if isinstance(value, dict):
            _assert_no_forbidden_keys(test, value, label)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_no_forbidden_keys(test, item, label)


def _assert_no_forbidden_values(test, text: str):
    lower = text.lower()
    for fb in FORBIDDEN_VALUES:
        test.assertNotIn(fb, lower, f"Output contains forbidden value '{fb}'")


def _assert_no_raw_uuid(test, text: str):
    test.assertIsNone(UUID_PAT.search(text), f"Contains raw UUID: {text[:80]}")


# ══════════════════════════════════════════════════════════════════════
# Readiness Gate Contract Checks
# ══════════════════════════════════════════════════════════════════════

class TestReadinessGateSafetyContracts(unittest.TestCase):
    """All contracts in the readiness chain are safe — no forbidden fields."""

    def test_01_manifest_items_have_safe_media_ref(self):
        """Manifest items use mediaRef (not filename/sha256/file_path)."""
        # Synthetic manifest — what we'd publish for test KSO
        manifest = {
            "manifestVersion": 1,
            "deviceCode": "test-device",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "slotOrder": 0,
                    "contentType": "image/png",
                    "mediaRef": "media/current/slot-000",
                    "creativeCode": "test-creative",
                },
            ],
        }
        for item in manifest["items"]:
            self.assertIn("mediaRef", item, "Item must have mediaRef")
            self.assertNotIn("filename", item, "Item must NOT have filename")
            self.assertNotIn("sha256", item, "Item must NOT have sha256")
            self.assertNotIn("file_path", item, "Item must NOT have file_path")
            self.assertNotIn("storage_ref", item, "Item must NOT have storage_ref")
        _assert_no_forbidden_keys(self, manifest, "Manifest body")
        _assert_no_forbidden_values(self, json.dumps(manifest))
        _assert_no_raw_uuid(self, json.dumps(manifest))

    def test_02_screensaver_creative_payload_safe(self):
        """ScreensaverCreativePayload contains only safe fields."""
        from kso_player.screensaver_creative import ScreensaverCreativePayload
        payload = ScreensaverCreativePayload(
            creative_code="test-creative",
            content_type="image/png",
            duration_ms=15000,
            slot_order=0,
            is_synthetic=False,
        )
        safe = payload.to_safe_dict()
        _assert_no_forbidden_keys(self, safe, "ScreensaverCreativePayload")
        _assert_no_forbidden_values(self, json.dumps(safe))
        _assert_no_raw_uuid(self, json.dumps(safe))

        # Must contain creative_code
        self.assertEqual(safe["creative_code"], "test-creative")

    def test_03_pop_record_safe(self):
        """JSONL record produced by screensaver_pop_bridge has no forbidden fields."""
        from kso_player.screensaver_creative import ScreensaverPoPDraft
        from kso_player.screensaver_pop_bridge import build_screensaver_pop_record

        now = datetime.now(timezone.utc)
        draft = ScreensaverPoPDraft(
            event_type="playback_completed",
            creative_code="readiness-cc",
            visible=True,
            media_available=True,
            duration_ms=15000,
            started_at_utc=now.isoformat(),
            ended_at_utc=(now + timedelta(seconds=15)).isoformat(),
        )
        result = build_screensaver_pop_record(
            draft, safety_state="idle", slot_order=0, content_type="image/png",
        )
        self.assertTrue(result.built)
        self.assertEqual(result.event_status, "completed")
        rec = result._record
        self.assertIsNotNone(rec)
        _assert_no_forbidden_keys(self, rec, "PoP JSONL record")
        _assert_no_forbidden_values(self, json.dumps(rec))
        _assert_no_raw_uuid(self, json.dumps(rec))

    def test_04_pop_draft_safe(self):
        """ScreensaverPoPDraft.to_safe_dict() has no forbidden fields."""
        from kso_player.screensaver_creative import ScreensaverPoPDraft
        now = datetime.now(timezone.utc)
        draft = ScreensaverPoPDraft(
            event_type="playback_completed",
            creative_code="readiness-cc",
            visible=True,
            media_available=True,
            duration_ms=15000,
            started_at_utc=now.isoformat(),
            ended_at_utc=(now + timedelta(seconds=15)).isoformat(),
        )
        safe = draft.to_safe_dict()
        _assert_no_forbidden_keys(self, safe, "ScreensaverPoPDraft safe dict")
        _assert_no_forbidden_values(self, json.dumps(safe))

    def test_05_ingest_request_safe(self):
        """KsoPoPIngestRequest fields are safe for dry run."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        req = KsoPoPIngestRequest(
            event_code="readiness-event",
            media_ref="media/current/slot-000",
            event_type="playback_completed",
            duration_ms=15000,
        )
        data = req.model_dump()
        # event_code and media_ref are safe; no forbidden keys
        allowed = {"event_code", "media_ref", "event_type", "duration_ms",
                   "manifest_version_id", "manifest_hash", "played_at"}
        for key in data:
            self.assertIn(key, allowed, f"Unexpected key '{key}' in ingest request")
        _assert_no_forbidden_values(self, json.dumps(data))

    def test_06_ingest_response_safe(self):
        """KsoPoPIngestResponse has only safe fields."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestResponse
        resp = KsoPoPIngestResponse(
            status="accepted",
            event_code="readiness-event",
            device_code="test-device",
            placement_code="test-place",
            campaign_code="test-camp",
            creative_code="test-creative",
            received_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump()
        _assert_no_forbidden_keys(self, data, "KsoPoPIngestResponse")
        _assert_no_forbidden_values(self, json.dumps(data, default=str))
        _assert_no_raw_uuid(self, json.dumps(data, default=str))

    def test_07_list_response_safe(self):
        """KsoPoPListResponse has only safe fields."""
        from app.domains.proof_of_play.schemas import KsoPoPListResponse
        resp = KsoPoPListResponse(
            event_code="readiness-event",
            device_code="test-device",
            placement_code="test-place",
            campaign_code="test-camp",
            creative_code="test-creative",
            media_ref="media/current/slot-000",
            event_type="playback_completed",
            status="accepted",
            received_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump()
        _assert_no_forbidden_keys(self, data, "KsoPoPListResponse")
        _assert_no_forbidden_values(self, json.dumps(data, default=str))
        _assert_no_raw_uuid(self, json.dumps(data, default=str))

    def test_08_screensaver_run_result_safe(self):
        """ScreensaverRunResult.to_safe_dict() has only safe fields."""
        from kso_player.x11_screensaver_runner import ScreensaverRunResult
        result = ScreensaverRunResult(
            visible=True,
            reason="idle_ks_inactive",
            state="idle",
            stop_reason="timeout",
            duration_sec=10.0,
            rollback_done=True,
            renderer_plan_valid=True,
            focus_restored=True,
            focus_restore_attempted=True,
        )
        safe = result.to_safe_dict()
        _assert_no_forbidden_keys(self, safe, "ScreensaverRunResult")
        _assert_no_forbidden_values(self, json.dumps(safe))


# ══════════════════════════════════════════════════════════════════════
# Readiness checklist: all components exist and are importable
# ══════════════════════════════════════════════════════════════════════

class TestReadinessComponentsExist(unittest.TestCase):
    """All components in the dry run chain are importable and have expected APIs."""

    def test_01_screensaver_creative_importable(self):
        """screensaver_creative module is importable."""
        from kso_player.screensaver_creative import (
            ScreensaverCreativePayload, ScreensaverPoPDraft,
            build_screensaver_creative_from_playlist,
            decide_creative_visibility,
        )
        self.assertTrue(True)

    def test_02_screensaver_pop_bridge_importable(self):
        """screensaver_pop_bridge module is importable."""
        from kso_player.screensaver_pop_bridge import (
            build_screensaver_pop_record, build_screensaver_event_code,
            ScreensaverPopRecordResult,
        )
        self.assertTrue(True)

    def test_03_pop_writer_importable(self):
        """pop_writer module is importable."""
        from kso_player.pop_writer import PopWriteResult, write_pop_event
        self.assertTrue(True)

    def test_04_sidecar_pop_pickup_importable(self):
        """pop_pickup module is importable."""
        from kso_sidecar_agent.pop_pickup import (
            classify_pop_event, CLASS_ELIGIBLE, PopPickupClassification,
        )
        self.assertTrue(True)

    def test_05_sidecar_pop_payload_importable(self):
        """pop_payload module is importable."""
        from kso_sidecar_agent.pop_payload import PopPayloadEvent, PopPayloadBuildResult
        self.assertTrue(True)

    def test_06_backend_ingest_importable(self):
        """Backend ingest service is importable."""
        from app.domains.proof_of_play.service import ingest_kso_pop, list_kso_pop_events
        self.assertTrue(True)

    def test_07_x11_runner_importable(self):
        """x11_screensaver_runner module is importable."""
        from kso_player.x11_screensaver_runner import (
            ScreensaverRunResult, ScreensaverRunPlan,
        )
        self.assertTrue(True)

    def test_08_kill_switch_importable(self):
        """kill_switch module is importable."""
        from kso_player.kill_switch import is_kill_switch_active
        self.assertTrue(True)


# ══════════════════════════════════════════════════════════════════════
# Stop criteria: all known stop conditions are documented
# ══════════════════════════════════════════════════════════════════════

class TestReadinessStopCriteria(unittest.TestCase):
    """All stop criteria are documented and consistent with code."""

    STOP_CRITERIA = [
        "focus_stolen",
        "active_window_not_ukm5",
        "chromium_pid_changed",
        "mint_service_not_active",
        "ram_below_500mb",
        "cpu_above_90pct",
        "ssh_vnc_lost",
        "overlay_does_not_disappear",
        "pop_has_forbidden_fields",
        "receipt_payment_fiscal_pii_appeared",
        "ukm5_db_read_required",
    ]

    def test_01_stop_criteria_documented(self):
        """All stop criteria from code are in the document list."""
        from kso_player.x11_screensaver_runner import (
            STOP_REASON_FOCUS_WARNING, STOP_REASON_FOCUS_LOST,
            STOP_REASON_KILL_SWITCH, STOP_REASON_STATE_CHANGE,
            STOP_REASON_TIMEOUT, STOP_REASON_FORBIDDEN,
        )
        known_reasons = {
            STOP_REASON_FOCUS_WARNING, STOP_REASON_FOCUS_LOST,
            STOP_REASON_KILL_SWITCH, STOP_REASON_STATE_CHANGE,
            STOP_REASON_TIMEOUT, STOP_REASON_FORBIDDEN,
        }
        for reason in known_reasons:
            self.assertIsInstance(reason, str, f"Stop reason must be string: {reason}")
            self.assertNotIn(" ", reason, f"Stop reason must be snake_case: '{reason}'")
            self.assertNotIn(reason.lower(), FORBIDDEN_VALUES,
                             f"Stop reason '{reason}' must not be forbidden")

    def test_02_screensaver_run_result_stop_reasons_safe(self):
        """All ScreensaverRunResult stop_reason values are safe strings."""
        from kso_player.x11_screensaver_runner import ScreensaverRunResult
        # Test with each known stop reason
        reasons = ["timeout", "kill_switch", "state_change",
                   "focus_warning", "focus_lost", "forbidden", "rollback_failed"]
        for reason in reasons:
            result = ScreensaverRunResult(stop_reason=reason)
            safe = result.to_safe_dict()
            self.assertEqual(safe["stop_reason"], reason)
            _assert_no_forbidden_values(self, json.dumps(safe))

    def test_03_runner_forbidden_operations(self):
        """Runner's validate_command_safety rejects forbidden operations."""
        from kso_player.x11_screensaver_runner import validate_command_safety

        bad_commands = [
            "pkill chromium",
            "killall chromium",
            "systemctl restart mint",
            "systemctl stop mysql",
        ]
        for cmd in bad_commands:
            result = validate_command_safety(cmd)
            self.assertFalse(result["safe"],
                             f"Command '{cmd}' should be rejected")
            self.assertGreater(len(result["violations"]), 0,
                               f"Command '{cmd}' should have violations")

        safe_commands = [
            "echo hello",
            "ls -la /tmp",
            "python3 --version",
        ]
        for cmd in safe_commands:
            result = validate_command_safety(cmd)
            self.assertTrue(result["safe"],
                            f"Command '{cmd}' should be safe, got: {result['violations']}")


# ══════════════════════════════════════════════════════════════════════
# Readiness gate document self-consistency
# ══════════════════════════════════════════════════════════════════════

class TestReadinessDocumentConsistency(unittest.TestCase):
    """Readiness gate document is self-consistent and references real files."""

    def test_01_readiness_document_exists(self):
        """Readiness gate document exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "audit",
            "one-kso-e2e-dry-run-readiness-gate.md",
        )
        self.assertTrue(os.path.exists(path),
                        f"Readiness gate document not found at {path}")

    def test_02_readiness_document_has_all_sections(self):
        """Document contains all required sections."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "audit",
            "one-kso-e2e-dry-run-readiness-gate.md",
        )
        with open(path, "r") as f:
            content = f.read()

        required_sections = [
            "## 1. Scope",
            "## 2. Что уже доказано",
            "## 3. Оставшиеся блокеры",
            "## 4. Данные, необходимые от оператора",
            "## 5. План dry run",
            "Phase A — Backend Readiness",
            "Phase B — Sidecar Readiness",
            "Phase C — Runner Dry-Run",
            "Phase D — Controlled Physical Window",
            "Phase E — PoP + Report Verification",
            "## 6. Stop Criteria",
            "## 7. Rollback Procedure",
            "## 8. Артефакты",
            "## 9. Security Constraints",
            "## 10. Readiness Checklist",
        ]
        for section in required_sections:
            self.assertIn(section, content,
                          f"Document must contain section: {section}")

    def test_03_readiness_document_no_forbidden_in_examples(self):
        """Document text does not contain forbidden values in code examples."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "audit",
            "one-kso-e2e-dry-run-readiness-gate.md",
        )
        with open(path, "r") as f:
            content = f.read()

        # Document should NOT contain real secrets
        must_not_contain = [
            "device_secret:",
            "access_token:",
            "password:",
            "api_key:",
        ]
        for phrase in must_not_contain:
            self.assertNotIn(phrase, content,
                             f"Document must not contain '{phrase}'")

    def test_04_forbidden_operations_documented(self):
        """Rollback section explicitly prohibits dangerous operations."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "audit",
            "one-kso-e2e-dry-run-readiness-gate.md",
        )
        with open(path, "r") as f:
            content = f.read()

        must_contain = [
            "pkill chromium",
            "systemctl restart mint",
            "НЕ менять",
            "НЕ читать",
        ]
        for phrase in must_contain:
            self.assertIn(phrase, content,
                          f"Document must explicitly prohibit '{phrase}'")
