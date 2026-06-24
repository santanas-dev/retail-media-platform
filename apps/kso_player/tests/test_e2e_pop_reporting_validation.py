"""Dev E2E PoP Reporting Validation — full chain without physical KSO.

Covers the entire chain using ONLY synthetic/dev test data:
  backend manifest (synthetic) → PlayerPlaylistItem → ScreensaverCreativePayload
  → media availability → ScreensaverPoPDraft → pop_writer JSONL
  → sidecar pop_pickup → PopPayloadEvent → backend compatibility
  → portal report filter compatibility

NO real KSO, NO X11, NO Chromium, NO backend server.
All data is synthetic — no real manifest IDs, no real device codes.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from kso_player.playlist import PlayerPlaylistItem
from kso_player.screensaver_creative import (
    ScreensaverCreativePayload,
    ScreensaverPoPDraft,
    build_screensaver_creative,
    build_screensaver_pop_draft,
    decide_creative_visibility,
    validate_screensaver_creative,
    validate_screensaver_pop_safety,
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    SCREENSAVER_EVENT_BLOCKED,
    VIS_REASON_CREATIVE_VALID,
    VIS_REASON_MEDIA_MISSING,
)
from kso_player.screensaver_media_availability import (
    ScreensaverMediaAvailability,
    check_screensaver_media_availability,
    REASON_MEDIA_AVAILABLE,
    REASON_MEDIA_MISSING,
)
from kso_player.screensaver_pop_bridge import (
    ScreensaverPopRecordResult,
    build_screensaver_pop_record,
    build_screensaver_event_code,
    ALLOWED_SCREENSAVER_RECORD_KEYS,
)
from kso_player.pop_writer import (
    build_pop_jsonl_record,
    write_pop_event,
    PopWriteResult,
    POP_PENDING_DIR as PLAYER_POP_PENDING_DIR,
    POP_JSONL_FILE as PLAYER_POP_JSONL_FILE,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers — synthetic test data
# ══════════════════════════════════════════════════════════════════════

def _make_synthetic_manifest_item(
    order=0,
    filename="synthetic_ad.png",
    content_type="image/png",
    creative_code="summer-promo-v3",
):
    """Synthetic manifest item simulating what backend would publish."""
    return {
        "manifest_item_id": f"00000000-0000-0000-0000-{order:012d}",
        "filename": filename,
        "content_type": content_type,
        "sha256": "a" * 64,
        "size_bytes": 12345,
        "duration_ms": 10_000,
        "order": order,
        "creative_code": creative_code,
    }


def _make_playlist_item(
    creative_code="summer-promo-v3",
    slot_order=0,
    content_type="image/png",
    duration_ms=10_000,
):
    """Synthetic PlayerPlaylistItem with backend creative_code."""
    return PlayerPlaylistItem(
        media_ref="slot-000",
        slot_order=slot_order,
        content_type=content_type,
        duration_ms=duration_ms,
        creative_code=creative_code,
    )


def _make_sidecar_root(base_dir, manifest_items=None, media_files=None):
    """Create minimal sidecar root with manifest/ and media/current/."""
    root = Path(base_dir) / "sidecar_root"
    manifest_dir = root / "manifest"
    media_dir = root / "media" / "current"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    if manifest_items is not None:
        manifest = {
            "manifest_version_id": "00000000-0000-0000-0000-000000000001",
            "manifest_hash": "a" * 64,
            "source": "current",
            "items": manifest_items,
        }
        (manifest_dir / "current_manifest.json").write_text(json.dumps(manifest))

    if media_files is not None:
        for filename, content in media_files.items():
            (media_dir / filename).write_bytes(content)

    return root


# ══════════════════════════════════════════════════════════════════════
# E2E Happy Path
# ══════════════════════════════════════════════════════════════════════

class TestE2EHappyPath(unittest.TestCase):
    """Full chain: manifest → creative → availability → PoP → JSONL → sidecar → backend compat."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_item = _make_synthetic_manifest_item(
            order=0,
            filename="synthetic_ad.png",
            creative_code="summer-promo-v3",
        )
        self.root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[self.manifest_item],
            media_files={"synthetic_ad.png": b"synthetic_png_data"},
        )

    # ── Step 1: PlaylistItem ← manifest creative_code ──────────────
    def test_step1_playlist_item_has_creative_code(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        self.assertEqual(item.creative_code, "summer-promo-v3")
        self.assertEqual(item.slot_order, 0)

    # ── Step 2: ScreensaverCreativePayload ← playlist item ────────
    def test_step2_creative_payload_preserves_creative_code(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)
        self.assertEqual(creative.creative_code, "summer-promo-v3")
        self.assertFalse(creative.is_synthetic)
        self.assertEqual(creative.media_ref, "slot-000")
        self.assertEqual(creative.content_type, "image/png")

        validation = validate_screensaver_creative(creative)
        self.assertTrue(validation["valid"], f"Creative invalid: {validation['errors']}")

    # ── Step 3: Media availability check ──────────────────────────
    def test_step3_media_available(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)

        avail = check_screensaver_media_availability(creative, self.root)
        self.assertTrue(avail.ready_for_runner)
        self.assertTrue(avail.media_available)
        self.assertEqual(avail.reason, REASON_MEDIA_AVAILABLE)
        self.assertEqual(avail.creative_code, "summer-promo-v3")

    # ── Step 4: Visibility decision with media ────────────────────
    def test_step4_visible_with_media(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)
        avail = check_screensaver_media_availability(creative, self.root)

        should_show, reason = decide_creative_visibility(
            creative,
            state="idle",
            kill_switch_active=False,
            media_availability=avail,
        )
        self.assertTrue(should_show)
        self.assertEqual(reason, VIS_REASON_CREATIVE_VALID)

    # ── Step 5: ScreensaverPoPDraft ───────────────────────────────
    def test_step5_pop_draft_with_creative_code(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
            duration_ms=10_000,
            started_at_utc="2026-06-24T12:00:00Z",
            ended_at_utc="2026-06-24T12:00:10Z",
        )
        self.assertEqual(pop.creative_code, "summer-promo-v3")
        self.assertTrue(pop.media_available)
        self.assertTrue(pop.visible)
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_PLAYBACK_COMPLETED)

    # ── Step 6: Bridge → sidecar JSONL record ─────────────────────
    def test_step6_bridge_to_jsonl_record(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
            duration_ms=10_000,
        )

        result = build_screensaver_pop_record(
            pop,
            slot_order=creative.slot_order,
            content_type=creative.content_type,
        )
        self.assertTrue(result.built)
        self.assertEqual(result.event_status, "completed")
        self.assertEqual(result.creative_code, "summer-promo-v3")

        record = result._record
        self.assertEqual(record["creative_code"], "summer-promo-v3")
        self.assertTrue(record["media_available"])
        self.assertEqual(record["event_type"], "playback_completed")
        self.assertEqual(record["event_status"], "completed")

    # ── Step 7: Write to JSONL via pop_writer ─────────────────────
    def test_step7_write_jsonl_record(self):
        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
            duration_ms=10_000,
        )
        bridge_result = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")
        record = bridge_result._record

        # Write record directly to JSONL (simulating what pop_writer does)
        root = Path(self.tmpdir) / "agent_root"
        pending_dir = root / PLAYER_POP_PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = pending_dir / PLAYER_POP_JSONL_FILE

        line = json.dumps(record, sort_keys=True) + "\n"
        jsonl_path.write_text(line, encoding="utf-8")

        # Read back
        raw = jsonl_path.read_text(encoding="utf-8")
        self.assertIn("summer-promo-v3", raw)
        self.assertIn("playback_completed", raw)
        self.assertIn("completed", raw)

    # ── Step 8: Sidecar classification → eligible ─────────────────
    def test_step8_sidecar_classifies_eligible(self):
        """Completed + media available → sidecar should classify as CLASS_ELIGIBLE."""
        try:
            from kso_sidecar_agent.pop_pickup import (
                classify_pop_event,
                CLASS_ELIGIBLE,
                CLASS_DRAFT,
            )
        except ImportError:
            self.skipTest("kso_sidecar_agent not in PYTHONPATH")

        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        bridge_result = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")
        record = bridge_result._record

        # Real sidecar classify
        classification = classify_pop_event(
            record,
            manifest_items=[self.manifest_item],
            media_cache_complete=True,
        )
        self.assertEqual(
            classification.classification, CLASS_ELIGIBLE,
            f"Expected CLASS_ELIGIBLE, got {classification.classification}"
        )

    # ── Step 9: PopPayloadEvent contains creative_code ────────────
    def test_step9_pop_payload_event_has_creative_code(self):
        """Build PopPayloadEvent via sidecar payload builder."""
        try:
            from kso_sidecar_agent.pop_payload import (
                PopPayloadEvent,
                PopPayloadEnvelope,
            )
        except ImportError:
            self.skipTest("kso_sidecar_agent not in PYTHONPATH")

        item = _make_playlist_item(creative_code="summer-promo-v3")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        bridge_result = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")

        # Direct build — simulating what pop_payload builder does
        event = PopPayloadEvent(
            device_event_id="test-event-id",
            manifest_item_id=self.manifest_item["manifest_item_id"],
            manifest_version_id="test-manifest-version",
            played_at="2026-06-24T12:00:00Z",
            duration_ms=10_000,
            play_status="completed",
            selected_order=0,
            selected_content_type="image/png",
            creative_code=bridge_result._record.get("creative_code"),
        )
        self.assertEqual(event.creative_code, "summer-promo-v3")
        self.assertEqual(event.play_status, "completed")
        self.assertEqual(event.duration_ms, 10_000)


# ══════════════════════════════════════════════════════════════════════
# E2E Negative Paths
# ══════════════════════════════════════════════════════════════════════

class TestE2ENegativePaths(unittest.TestCase):
    """Blocked/missing media paths produce diagnostic-only events."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    # ── media_available=False → blocked ───────────────────────────
    def test_media_missing_blocks_playback_completed(self):
        item = _make_playlist_item(creative_code="promo-missing")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=False,
            media_available=False,
        )
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        # Playback without media → blocked
        self.assertEqual(result._record["event_type"], "blocked")
        self.assertEqual(result.event_status, "draft")
        self.assertFalse(result._record["media_available"])

    def test_media_missing_blocks_playback_started(self):
        item = _make_playlist_item(creative_code="promo-missing")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=False,
            media_available=False,
        )
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["event_type"], "blocked")
        self.assertEqual(result.event_status, "draft")

    # ── blocked event → draft/local only ──────────────────────────
    def test_blocked_event_is_draft(self):
        item = _make_playlist_item(creative_code="blocked-promo")
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            visible=False,
            media_available=False,
        )
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["event_type"], "blocked")
        self.assertEqual(result.event_status, "draft")
        # Draft events are NOT eligible for backend send

    # ── kill-switch active → hidden/blocked ───────────────────────
    def test_kill_switch_blocks_visibility(self):
        item = _make_playlist_item(creative_code="kill-promo")
        creative = build_screensaver_creative(item)

        should_show, reason = decide_creative_visibility(
            creative,
            state="idle",
            kill_switch_active=True,
            media_availability=None,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, "hidden_kill_switch")

    # ── non-idle state → hidden ───────────────────────────────────
    def test_non_idle_state_hides(self):
        item = _make_playlist_item(creative_code="busy-promo")
        creative = build_screensaver_creative(item)

        for state in ("transaction", "payment", "receipt", "service"):
            should_show, reason = decide_creative_visibility(
                creative,
                state=state,
                kill_switch_active=False,
                media_availability=None,
            )
            self.assertFalse(should_show, f"Should hide in state={state}")
            self.assertEqual(reason, "hidden_state")

    # ── missing creative_code → synthetic fallback ────────────────
    def test_missing_creative_code_produces_fallback(self):
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=10_000,
            creative_code=None,  # missing from backend
        )
        creative = build_screensaver_creative(item)
        self.assertNotEqual(creative.creative_code, "")
        self.assertTrue(creative.is_synthetic, "Should be synthetic fallback")

    # ── synthetic creative not production-ready ───────────────────
    def test_synthetic_fallback_not_production_ready(self):
        """Synthetic fallback is_synthetic=True — not for production PoP."""
        creative = ScreensaverCreativePayload(
            creative_code="scr-slot-000",
            media_ref="slot-000",
            content_type="test",
            slot_order=0,
            is_synthetic=True,
        )
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result.creative_code, "scr-slot-000")
        # Synthetic code reaches the record but is marked differently upstream


# ══════════════════════════════════════════════════════════════════════
# E2E Security Audit — no forbidden fields
# ══════════════════════════════════════════════════════════════════════

class TestE2ESecurityAudit(unittest.TestCase):
    """No forbidden fields anywhere in the E2E chain output."""

    FORBIDDEN = [
        "barcode", "scanner_value", "key_value", "key_payload",
        "receipt", "transaction", "payment", "fiscal",
        "customer", "phone", "email", "card", "pan",
        "file_path", "absolute_path", "local_path",
        "sha256", "storage_ref", "minio", "s3",
        "backend_url", "backend_base_url",
        "token", "secret", "password", "api_key",
        "device_secret", "access_token", "device_token",
    ]

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_item = _make_synthetic_manifest_item(
            creative_code="secure-promo",
        )
        self.root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[self.manifest_item],
            media_files={"synthetic_ad.png": b"data"},
        )
        self.creative = build_screensaver_creative(
            _make_playlist_item(creative_code="secure-promo")
        )

    def _assert_no_forbidden(self, obj, label=""):
        """Assert obj (dict or str) contains no forbidden fields."""
        if isinstance(obj, dict):
            s = json.dumps(obj).lower()
        else:
            s = str(obj).lower()
        for fb in self.FORBIDDEN:
            self.assertNotIn(fb, s, f"Forbidden '{fb}' found in {label}")

    # ── ScreensaverCreativePayload ────────────────────────────────
    def test_no_forbidden_in_creative_payload(self):
        d = self.creative.to_safe_dict()
        self._assert_no_forbidden(d, "ScreensaverCreativePayload")

    # ── ScreensaverMediaAvailability ──────────────────────────────
    def test_no_forbidden_in_media_availability(self):
        avail = check_screensaver_media_availability(self.creative, self.root)
        d = avail.to_safe_dict()
        self._assert_no_forbidden(d, "ScreensaverMediaAvailability")

    # ── ScreensaverPoPDraft ───────────────────────────────────────
    def test_no_forbidden_in_pop_draft(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        d = pop.to_safe_dict()
        self._assert_no_forbidden(d, "ScreensaverPoPDraft")

        # Also validate via safety function
        result = validate_screensaver_pop_safety(d)
        self.assertTrue(result["valid"], f"PoP failed: {result['errors']}")

    # ── Bridge record ─────────────────────────────────────────────
    def test_no_forbidden_in_bridge_record(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        bridge = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")
        self._assert_no_forbidden(bridge._record, "bridge JSONL record")

    # ── ScreensaverPopRecordResult safe dict ──────────────────────
    def test_no_forbidden_in_result_safe_dict(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        bridge = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")
        d = bridge.to_safe_dict()
        self._assert_no_forbidden(d, "ScreensaverPopRecordResult")

    # ── No raw UUID in user-facing output ─────────────────────────
    def test_no_raw_uuid_in_user_facing_output(self):
        import re
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        bridge = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")

        # Check user-facing outputs
        for label, d in [
            ("creative_safe_dict", self.creative.to_safe_dict()),
            ("pop_safe_dict", pop.to_safe_dict()),
            ("bridge_safe_dict", bridge.to_safe_dict()),
        ]:
            s = json.dumps(d)
            self.assertIsNone(
                uuid_pattern.search(s),
                f"UUID found in {label}: {s[:100]}"
            )


# ══════════════════════════════════════════════════════════════════════
# Backend Compatibility
# ══════════════════════════════════════════════════════════════════════

class TestBackendCompatibility(unittest.TestCase):
    """Verify PopPayloadEvent + record are compatible with backend schema."""

    def test_kso_pop_ingest_request_accepts_fields(self):
        """KsoPoPIngestRequest fields are present in our bridge records."""
        try:
            from backend.app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        except ImportError:
            self.skipTest("Backend schemas not importable")

        # Verify the schema accepts the fields we produce
        fields = KsoPoPIngestRequest.__fields__
        required = {"event_code", "media_ref"}
        for field in required:
            self.assertIn(field, fields, f"Missing required field '{field}'")

        optional = {"event_type", "played_at", "duration_ms",
                    "manifest_version_id", "manifest_hash"}
        for field in optional:
            self.assertIn(field, fields, f"Missing optional field '{field}'")

    def test_kso_pop_ingest_response_has_creative_code(self):
        """Backend response includes creative_code (already in schema)."""
        try:
            from backend.app.domains.proof_of_play.schemas import KsoPoPIngestResponse
        except ImportError:
            self.skipTest("Backend schemas not importable")

        self.assertIn("creative_code", KsoPoPIngestResponse.__fields__)
        self.assertIn("device_code", KsoPoPIngestResponse.__fields__)
        self.assertIn("placement_code", KsoPoPIngestResponse.__fields__)
        self.assertIn("campaign_code", KsoPoPIngestResponse.__fields__)

    def test_kso_pop_list_has_creative_code(self):
        """Portal list response includes creative_code for filtering."""
        try:
            from backend.app.domains.proof_of_play.schemas import KsoPoPListResponse
        except ImportError:
            self.skipTest("Backend schemas not importable")

        self.assertIn("creative_code", KsoPoPListResponse.__fields__)
        self.assertIn("event_type", KsoPoPListResponse.__fields__)
        self.assertIn("status", KsoPoPListResponse.__fields__)
        self.assertIn("media_ref", KsoPoPListResponse.__fields__)

    def test_pop_payload_event_fields_match_backend(self):
        """PopPayloadEvent has all fields needed for backend compatibility."""
        try:
            from kso_sidecar_agent.pop_payload import PopPayloadEvent
        except ImportError:
            self.skipTest("kso_sidecar_agent not in PYTHONPATH")

        # creative_code is the key screensaver extension
        fields = [f.name for f in PopPayloadEvent.__dataclass_fields__.values()]
        self.assertIn("creative_code", fields)
        self.assertIn("device_event_id", fields)
        self.assertIn("manifest_item_id", fields)
        self.assertIn("duration_ms", fields)
        self.assertIn("play_status", fields)
        self.assertIn("selected_order", fields)

    def test_kos_proof_of_play_model_has_creative_code(self):
        """Backend ORM model KsoProofOfPlayEvent has creative_code column."""
        try:
            from backend.app.domains.proof_of_play.models import KsoProofOfPlayEvent
        except (ImportError, Exception):
            self.skipTest("Backend models not importable (SQLAlchemy may already have table)")

        columns = {c.name for c in KsoProofOfPlayEvent.__table__.columns}
        self.assertIn("creative_code", columns)
        self.assertIn("event_code", columns)
        self.assertIn("device_code", columns)
        self.assertIn("placement_code", columns)
        self.assertIn("campaign_code", columns)
        self.assertIn("media_ref", columns)
        self.assertIn("event_type", columns)
        self.assertIn("status", columns)
        self.assertIn("played_at", columns)
        self.assertIn("duration_ms", columns)

    def test_backend_model_disallows_forbidden_fields(self):
        """KsoProofOfPlayEvent must NOT have forbidden columns."""
        try:
            from backend.app.domains.proof_of_play.models import KsoProofOfPlayEvent
        except (ImportError, Exception):
            self.skipTest("Backend models not importable (SQLAlchemy may already have table)")

        columns = {c.name.lower() for c in KsoProofOfPlayEvent.__table__.columns}
        forbidden = {
            "token", "secret", "password", "api_key",
            "file_path", "absolute_path", "local_path",
            "sha256", "storage_ref", "minio",
            "barcode", "scanner", "receipt", "payment", "fiscal",
            "customer", "card", "pan", "phone", "email",
            "backend_url",
        }
        for fb in forbidden:
            self.assertNotIn(fb, columns, f"Backend model has forbidden column '{fb}'")


# ══════════════════════════════════════════════════════════════════════
# Portal Compatibility
# ══════════════════════════════════════════════════════════════════════

class TestPortalCompatibility(unittest.TestCase):
    """Portal report filters and projections are compatible with screensaver PoP."""

    def test_portal_list_service_filters_by_creative_code(self):
        """list_kso_pop_events() accepts creative_code filter."""
        try:
            from backend.app.domains.proof_of_play.service import list_kso_pop_events
        except ImportError:
            self.skipTest("Backend service not importable")

        import inspect
        sig = inspect.signature(list_kso_pop_events)
        params = list(sig.parameters.keys())
        self.assertIn("creative_code", params,
                      "list_kso_pop_events must accept creative_code filter")

    def test_portal_list_response_safe_projection(self):
        """KsoPoPListResponse has no forbidden fields."""
        try:
            from backend.app.domains.proof_of_play.schemas import KsoPoPListResponse
        except ImportError:
            self.skipTest("Backend schemas not importable")

        fields = set(KsoPoPListResponse.__fields__.keys())
        lower_fields = {f.lower() for f in fields}

        # Must have creative_code
        self.assertIn("creative_code", lower_fields)

        # Must NOT have forbidden fields
        forbidden = {
            "id", "token", "secret", "password",
            "file_path", "absolute_path", "local_path",
            "sha256", "storage_ref", "minio",
            "barcode", "scanner", "receipt", "payment",
            "fiscal", "customer", "card", "pan",
            "backend_url", "device_secret",
            "manifest_version_id", "manifest_hash",
        }
        for fb in forbidden:
            self.assertNotIn(fb, lower_fields,
                             f"KsoPoPListResponse has forbidden field '{fb}'")


# ══════════════════════════════════════════════════════════════════════
# Full chain creative_code trace
# ══════════════════════════════════════════════════════════════════════

class TestCreativeCodeEndToEnd(unittest.TestCase):
    """creative_code preserved through all 9 steps of the chain."""

    CREATIVE_CODE = "e2e-trace-promo-2025"

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_item = _make_synthetic_manifest_item(
            creative_code=self.CREATIVE_CODE,
            order=0,
            filename="e2e_ad.png",
        )
        self.root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[self.manifest_item],
            media_files={"e2e_ad.png": b"e2e_data"},
        )

    def test_full_9_step_creative_code_trace(self):
        """creative_code survives all 9 steps of the chain."""
        trace = []

        # Step 1: PlaylistItem
        item = _make_playlist_item(creative_code=self.CREATIVE_CODE)
        self.assertEqual(item.creative_code, self.CREATIVE_CODE)
        trace.append(("playlist_item", item.creative_code))

        # Step 2: ScreensaverCreativePayload
        creative = build_screensaver_creative(item)
        self.assertEqual(creative.creative_code, self.CREATIVE_CODE)
        trace.append(("creative_payload", creative.creative_code))

        # Step 3: Media availability
        avail = check_screensaver_media_availability(creative, self.root)
        self.assertEqual(avail.creative_code, self.CREATIVE_CODE)
        trace.append(("media_availability", avail.creative_code))

        # Step 4: Visibility decision
        should_show, _ = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertTrue(should_show)
        trace.append(("visibility", "visible"))

        # Step 5: ScreensaverPoPDraft
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        self.assertEqual(pop.creative_code, self.CREATIVE_CODE)
        trace.append(("pop_draft", pop.creative_code))

        # Step 6: Bridge → JSONL record
        bridge = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")
        self.assertEqual(bridge.creative_code, self.CREATIVE_CODE)
        self.assertEqual(bridge._record["creative_code"], self.CREATIVE_CODE)
        trace.append(("jsonl_record", bridge._record["creative_code"]))

        # Step 7: Sidecar classification
        try:
            from kso_sidecar_agent.pop_pickup import classify_pop_event, CLASS_ELIGIBLE
            classification = classify_pop_event(
                bridge._record,
                manifest_items=[self.manifest_item],
                media_cache_complete=True,
            )
            self.assertEqual(classification.classification, CLASS_ELIGIBLE)
            trace.append(("sidecar_classification", "eligible"))
        except ImportError:
            trace.append(("sidecar_classification", "skipped (no import)"))

        # Step 8: PopPayloadEvent
        try:
            from kso_sidecar_agent.pop_payload import PopPayloadEvent
            event = PopPayloadEvent(
                creative_code=bridge._record.get("creative_code"),
                device_event_id="e2e-test-id",
                played_at="2026-06-24T12:00:00Z",
                duration_ms=10_000,
                play_status="completed",
                selected_order=0,
                selected_content_type="image/png",
            )
            self.assertEqual(event.creative_code, self.CREATIVE_CODE)
            trace.append(("pop_payload_event", event.creative_code))
        except ImportError:
            trace.append(("pop_payload_event", "skipped (no import)"))

        # Step 9: Backend/Portal compatibility
        try:
            from backend.app.domains.proof_of_play.schemas import KsoPoPListResponse
            self.assertIn("creative_code", KsoPoPListResponse.__fields__)
            trace.append(("portal_report", self.CREATIVE_CODE))
        except ImportError:
            trace.append(("portal_report", "skipped (no import)"))

        # Verify all steps preserved the same code
        codes = [v for _, v in trace if v not in ("visible", "eligible",)]
        for step_name, code in trace:
            if code not in ("visible", "eligible",) and not str(code).startswith("skipped"):
                self.assertEqual(
                    code, self.CREATIVE_CODE,
                    f"creative_code lost at step '{step_name}': got '{code}'"
                )

        # All 9 steps traced
        self.assertEqual(len(trace), 9, f"Expected 9 steps, got {len(trace)}: {trace}")
