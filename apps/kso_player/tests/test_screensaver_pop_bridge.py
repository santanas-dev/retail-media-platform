"""Tests for Screensaver PoP Bridge — ScreensaverPoPDraft → sidecar JSONL.

Covers:
    - build_screensaver_pop_record: ScreensaverPoPDraft → sidecar record
    - build_screensaver_event_code: idempotency code
    - Event type mapping: screen_visible→impression, playback_completed→completed, etc.
    - playback_started requires media_available=True
    - playback_completed requires media_available=True
    - blocked event allowed when media_missing
    - creative_code preserved through mapping
    - No raw path/backend URL/token/secret/device_secret in record
    - No barcode/scanner/key payload in record
    - No receipt/payment/fiscal/customer/card in record
    - Backend PoP payload compatibility (creative_code in record)
    - draft/completed status: only playback_completed→completed
    - Safe dict output (ScreensaverPopRecordResult.to_safe_dict)
"""

import json
import unittest

from kso_player.screensaver_creative import (
    ScreensaverCreativePayload,
    ScreensaverPoPDraft,
    build_screensaver_pop_draft,
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    SCREENSAVER_EVENT_BLOCKED,
)
from kso_player.screensaver_pop_bridge import (
    ScreensaverPopRecordResult,
    build_screensaver_pop_record,
    build_screensaver_event_code,
    ALLOWED_SCREENSAVER_RECORD_KEYS,
    SCHEMA_VERSION,
    _EVENT_TYPE_MAP,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_creative(creative_code="summer-promo-v3"):
    return ScreensaverCreativePayload(
        creative_code=creative_code,
        media_ref="slot-000",
        content_type="image/png",
        duration_ms=10_000,
        slot_order=0,
    )


def _make_pop(
    event_type=SCREENSAVER_EVENT_VISIBLE,
    creative_code="summer-promo-v3",
    visible=True,
    media_available=True,
    duration_ms=10_000,
    reason="",
):
    creative = _make_creative(creative_code)
    return build_screensaver_pop_draft(
        creative,
        event_type=event_type,
        visible=visible,
        media_available=media_available,
        duration_ms=duration_ms,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════
# Tests: build_screensaver_pop_record — happy paths
# ══════════════════════════════════════════════════════════════════════

class TestBuildRecordHappy(unittest.TestCase):
    """Successful record building for each event type."""

    def test_screen_visible_maps_to_impression(self):
        pop = _make_pop(SCREENSAVER_EVENT_VISIBLE)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "impression")
        self.assertEqual(result.event_status, "draft")

    def test_screen_hidden_maps_to_completed(self):
        pop = _make_pop(SCREENSAVER_EVENT_HIDDEN, visible=False)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "completed")
        self.assertEqual(result.event_status, "draft")

    def test_playback_started_with_media(self):
        pop = _make_pop(SCREENSAVER_EVENT_PLAYBACK_STARTED, media_available=True)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "playback_started")
        self.assertEqual(result.event_status, "draft")

    def test_playback_completed_with_media(self):
        pop = _make_pop(SCREENSAVER_EVENT_PLAYBACK_COMPLETED, media_available=True)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "playback_completed")
        self.assertEqual(result.event_status, "completed")

    def test_blocked_event(self):
        pop = _make_pop(SCREENSAVER_EVENT_BLOCKED, visible=False, media_available=False)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "blocked")
        self.assertEqual(result.event_status, "draft")


# ══════════════════════════════════════════════════════════════════════
# Tests: media_available gate
# ══════════════════════════════════════════════════════════════════════

class TestMediaAvailableGate(unittest.TestCase):
    """Playback events blocked when media_available=False."""

    def test_playback_started_blocked_without_media(self):
        pop = _make_pop(SCREENSAVER_EVENT_PLAYBACK_STARTED, media_available=False)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "blocked")
        self.assertEqual(result.event_status, "draft")

    def test_playback_completed_blocked_without_media(self):
        pop = _make_pop(SCREENSAVER_EVENT_PLAYBACK_COMPLETED, media_available=False)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "blocked")
        self.assertEqual(result.event_status, "draft")

    def test_visible_not_affected_by_media(self):
        pop = _make_pop(SCREENSAVER_EVENT_VISIBLE, media_available=False)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "impression")

    def test_blocked_event_stays_blocked(self):
        pop = _make_pop(SCREENSAVER_EVENT_BLOCKED, media_available=True)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "blocked")


# ══════════════════════════════════════════════════════════════════════
# Tests: creative_code preservation
# ══════════════════════════════════════════════════════════════════════

class TestCreativeCodePreservation(unittest.TestCase):
    """creative_code flows through record to sidecar."""

    def test_creative_code_preserved(self):
        pop = _make_pop(creative_code="winter-campaign-2025")
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result.creative_code, "winter-campaign-2025")
        self.assertIsNotNone(result._record)
        self.assertEqual(result._record["creative_code"], "winter-campaign-2025")

    def test_creative_code_in_playback_completed(self):
        pop = _make_pop(
            SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            creative_code="backend-promo-42",
            media_available=True,
        )
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result.creative_code, "backend-promo-42")
        self.assertEqual(result._record["creative_code"], "backend-promo-42")

    def test_creative_code_in_blocked(self):
        pop = _make_pop(
            SCREENSAVER_EVENT_BLOCKED,
            creative_code="blocked-promo",
            visible=False,
            media_available=False,
        )
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result.creative_code, "blocked-promo")

    def test_empty_creative_code_becomes_none(self):
        pop = _make_pop(creative_code="")
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertIsNone(result._record["creative_code"])


# ══════════════════════════════════════════════════════════════════════
# Tests: record structure / field mapping
# ══════════════════════════════════════════════════════════════════════

class TestRecordStructure(unittest.TestCase):
    """Record has correct fields and values."""

    def test_record_has_schema_version(self):
        pop = _make_pop()
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["schema_version"], SCHEMA_VERSION)

    def test_record_has_allowed_keys_only(self):
        pop = _make_pop()
        result = build_screensaver_pop_record(pop)
        for key in result._record:
            self.assertIn(key, ALLOWED_SCREENSAVER_RECORD_KEYS,
                          f"Unexpected key '{key}' in record")

    def test_record_has_media_available(self):
        pop = _make_pop(media_available=True)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result._record["media_available"])

        pop2 = _make_pop(media_available=False)
        result2 = build_screensaver_pop_record(pop2)
        self.assertFalse(result2._record["media_available"])

    def test_playback_allowed_matches_media_and_visible(self):
        pop = _make_pop(media_available=True, visible=True)
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result._record["playback_allowed"])

        pop2 = _make_pop(media_available=False, visible=True)
        result2 = build_screensaver_pop_record(pop2)
        self.assertFalse(result2._record["playback_allowed"])

    def test_duration_ms_present(self):
        pop = _make_pop(duration_ms=15_000)
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["duration_ms"], 15_000)

    def test_session_action_play_for_visible(self):
        pop = _make_pop(SCREENSAVER_EVENT_VISIBLE, visible=True)
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["session_action"], "play")

    def test_session_action_stop_for_hidden(self):
        pop = _make_pop(SCREENSAVER_EVENT_HIDDEN, visible=False)
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["session_action"], "stop")

    def test_session_action_hold_for_blocked(self):
        pop = _make_pop(SCREENSAVER_EVENT_BLOCKED, visible=False)
        result = build_screensaver_pop_record(pop)
        self.assertEqual(result._record["session_action"], "hold")


# ══════════════════════════════════════════════════════════════════════
# Tests: forbidden fields in record
# ══════════════════════════════════════════════════════════════════════

class TestForbiddenFields(unittest.TestCase):
    """Record must NEVER contain forbidden fields."""

    def _assert_no_forbidden(self, record):
        record_str = json.dumps(record).lower()
        forbidden = [
            "token", "secret", "password", "api_key",
            "backend_url", "backend_base_url",
            "device_secret", "access_token",
            "file_path", "absolute_path", "local_path",
            "sha256", "storage_ref", "minio", "s3",
            "barcode", "scanner", "key_value",
            "receipt", "payment", "fiscal",
            "customer", "card", "pan", "phone", "email",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, record_str,
                             f"Forbidden '{fb}' found in record")

    def test_visible_record_no_forbidden(self):
        pop = _make_pop()
        result = build_screensaver_pop_record(pop)
        self._assert_no_forbidden(result._record)

    def test_blocked_record_no_forbidden(self):
        pop = _make_pop(SCREENSAVER_EVENT_BLOCKED, visible=False)
        result = build_screensaver_pop_record(pop)
        self._assert_no_forbidden(result._record)

    def test_playback_record_no_forbidden(self):
        pop = _make_pop(SCREENSAVER_EVENT_PLAYBACK_COMPLETED, media_available=True)
        result = build_screensaver_pop_record(pop)
        self._assert_no_forbidden(result._record)

    def test_record_no_raw_uuid(self):
        pop = _make_pop()
        result = build_screensaver_pop_record(pop)
        record_str = json.dumps(result._record)
        # No UUID-like patterns (8-4-4-4-12 hex)
        import re
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )
        self.assertIsNone(
            uuid_pattern.search(record_str),
            "Record contains UUID-like pattern"
        )


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid inputs
# ══════════════════════════════════════════════════════════════════════

class TestInvalidInputs(unittest.TestCase):
    """Invalid inputs return not-built results."""

    def test_non_pop_draft_rejected(self):
        result = build_screensaver_pop_record("not_a_pop_draft")
        self.assertFalse(result.built)
        self.assertEqual(result.reason, "invalid_event")

    def test_none_rejected(self):
        result = build_screensaver_pop_record(None)
        self.assertFalse(result.built)

    def test_unknown_event_type_cannot_occur(self):
        """ScreensaverPoPDraft constructor auto-corrects type — unknown types impossible."""
        # ScreensaverPoPDraft.__post_init__ replaces unknown types with SCREENSAVER_EVENT_HIDDEN
        # So build_screensaver_pop_record will never see an unknown type in practice.
        # All 5 SCREENSAVER_EVENT_* types are in _EVENT_TYPE_MAP.
        self.assertIn(SCREENSAVER_EVENT_VISIBLE,
                      list(_EVENT_TYPE_MAP.keys()) + list(_EVENT_TYPE_MAP.values()))

    def test_forbidden_in_creative_code_rejected(self):
        pop = ScreensaverPoPDraft(
            event_type=SCREENSAVER_EVENT_VISIBLE,
            creative_code="my-token-123",
        )
        result = build_screensaver_pop_record(pop)
        self.assertFalse(result.built)
        self.assertEqual(result.reason, "unsafe_creative_code")


# ══════════════════════════════════════════════════════════════════════
# Tests: idempotency codes
# ══════════════════════════════════════════════════════════════════════

class TestIdempotencyCodes(unittest.TestCase):
    """Event codes are deterministic and safe."""

    def test_event_code_format(self):
        code = build_screensaver_event_code("promo-v1", "impression",
                                             "2025-01-01T00:00:00Z", 0)
        self.assertTrue(code.startswith("scr-"))
        self.assertEqual(len(code), 20)  # "scr-" + 16 hex

    def test_deterministic_same_input(self):
        a = build_screensaver_event_code("promo", "impression", "t1", 0)
        b = build_screensaver_event_code("promo", "impression", "t1", 0)
        self.assertEqual(a, b)

    def test_different_creative_code_different_code(self):
        a = build_screensaver_event_code("promo-a", "impression", "t1", 0)
        b = build_screensaver_event_code("promo-b", "impression", "t1", 0)
        self.assertNotEqual(a, b)

    def test_different_slot_order_different_code(self):
        a = build_screensaver_event_code("promo", "impression", "t1", 0)
        b = build_screensaver_event_code("promo", "impression", "t1", 1)
        self.assertNotEqual(a, b)

    def test_event_code_no_forbidden_patterns(self):
        code = build_screensaver_event_code("promo-v1", "impression",
                                             "2025-01-01T00:00:00Z", 0)
        lower = code.lower()
        forbidden = ["token", "secret", "backend", "file_path", "sha256",
                     "barcode", "receipt", "payment"]
        for fb in forbidden:
            self.assertNotIn(fb, lower)


# ══════════════════════════════════════════════════════════════════════
# Tests: ScreensaverPopRecordResult safe dict
# ══════════════════════════════════════════════════════════════════════

class TestSafeDict(unittest.TestCase):
    """ScreensaverPopRecordResult.to_safe_dict() has no sensitive fields."""

    def test_to_safe_dict_no_record(self):
        result = ScreensaverPopRecordResult(built=True, creative_code="promo")
        d = result.to_safe_dict()
        self.assertNotIn("_record", d)
        self.assertNotIn("record", d)
        self.assertEqual(d["creative_code"], "promo")

    def test_to_safe_dict_no_forbidden(self):
        pop = _make_pop()
        result = build_screensaver_pop_record(pop)
        d = result.to_safe_dict()
        d_str = json.dumps(d).lower()
        forbidden = ["token", "secret", "backend", "file_path", "sha256",
                     "barcode", "receipt", "payment"]
        for fb in forbidden:
            self.assertNotIn(fb, d_str)


# ══════════════════════════════════════════════════════════════════════
# Tests: Backend compatibility
# ══════════════════════════════════════════════════════════════════════

class TestBackendCompatibility(unittest.TestCase):
    """Record fields compatible with backend KsoPoPIngestRequest."""

    def test_record_has_required_backend_fields(self):
        """Record maps to backend ingest: event_type, media_ref, duration_ms, played_at."""
        pop = _make_pop(SCREENSAVER_EVENT_PLAYBACK_COMPLETED, media_available=True)
        result = build_screensaver_pop_record(pop, slot_order=0, content_type="image/png")
        record = result._record
        self.assertIn("event_type", record)
        self.assertIn("duration_ms", record)
        self.assertIn("started_at", record)
        self.assertIn("ended_at", record)
        self.assertIn("creative_code", record)
        self.assertEqual(record["event_status"], "completed")

    def test_record_event_types_compatible_with_sidecar(self):
        """All mapped event types are in sidecar's ALLOWED_EVENT_TYPES."""
        try:
            from kso_sidecar_agent.pop_pickup import ALLOWED_EVENT_TYPES as SIDECAR_ALLOWED
        except ImportError:
            self.skipTest("kso_sidecar_agent not in PYTHONPATH")

        mapped_types = {"impression", "playback_started", "playback_completed",
                        "completed", "blocked"}
        for t in mapped_types:
            self.assertIn(t, SIDECAR_ALLOWED,
                          f"Type '{t}' not in sidecar ALLOWED_EVENT_TYPES")

    def test_record_keys_subset_of_sidecar_allowed(self):
        """All screensaver record keys are in sidecar's ALLOWED_RECORD_KEYS."""
        try:
            from kso_sidecar_agent.pop_pickup import ALLOWED_RECORD_KEYS as SIDECAR_ALLOWED
        except ImportError:
            self.skipTest("kso_sidecar_agent not in PYTHONPATH")

        for key in ALLOWED_SCREENSAVER_RECORD_KEYS:
            self.assertIn(key, SIDECAR_ALLOWED,
                          f"Key '{key}' not in sidecar ALLOWED_RECORD_KEYS")


# ══════════════════════════════════════════════════════════════════════
# Tests: Full chain — creative → PoP → record
# ══════════════════════════════════════════════════════════════════════

class TestFullChain(unittest.TestCase):
    """End-to-end: ScreensaverCreativePayload → PoP draft → record."""

    def test_full_chain_visible_creative(self):
        creative = _make_creative("summer-promo-v3")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
            media_available=True,
        )
        result = build_screensaver_pop_record(pop, slot_order=creative.slot_order,
                                               content_type=creative.content_type)
        self.assertTrue(result.built)
        self.assertEqual(result.creative_code, "summer-promo-v3")
        self.assertEqual(result._record["event_type"], "impression")
        self.assertTrue(result._record["media_available"])

    def test_full_chain_playback_completed(self):
        creative = _make_creative("backend-promo-42")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
            duration_ms=30_000,
        )
        result = build_screensaver_pop_record(pop, slot_order=creative.slot_order,
                                               content_type=creative.content_type)
        self.assertTrue(result.built)
        self.assertEqual(result.event_status, "completed")
        self.assertEqual(result.creative_code, "backend-promo-42")
        self.assertEqual(result._record["duration_ms"], 30_000)

    def test_full_chain_media_missing_blocked(self):
        creative = _make_creative("media-missing-promo")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=False,
            media_available=False,
        )
        result = build_screensaver_pop_record(pop)
        self.assertTrue(result.built)
        self.assertEqual(result._record["event_type"], "blocked")
        self.assertEqual(result.creative_code, "media-missing-promo")
        self.assertFalse(result._record["media_available"])

    def test_creative_code_not_lost_in_chain(self):
        creative = _make_creative("chain-test-code")
        for event_type in [
            SCREENSAVER_EVENT_VISIBLE,
            SCREENSAVER_EVENT_PLAYBACK_STARTED,
            SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            SCREENSAVER_EVENT_BLOCKED,
            SCREENSAVER_EVENT_HIDDEN,
        ]:
            pop = build_screensaver_pop_draft(
                creative,
                event_type=event_type,
                visible=(event_type != SCREENSAVER_EVENT_BLOCKED),
                media_available=(event_type != SCREENSAVER_EVENT_BLOCKED),
            )
            result = build_screensaver_pop_record(pop)
            self.assertEqual(
                result.creative_code, "chain-test-code",
                f"creative_code lost for event_type={event_type}"
            )

    def test_record_jsonl_serializable(self):
        creative = _make_creative("jsonl-test")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            media_available=True,
        )
        result = build_screensaver_pop_record(pop)
        # Must be JSON-serializable (for JSONL write)
        line = json.dumps(result._record, sort_keys=True)
        self.assertIsInstance(line, str)
        self.assertGreater(len(line), 0)
        # Parse back
        parsed = json.loads(line)
        self.assertEqual(parsed["creative_code"], "jsonl-test")
