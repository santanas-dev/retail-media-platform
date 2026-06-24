"""Tests for Screensaver Creative Payload — manifest-to-screensaver bridge.

Covers:
    - ScreensaverCreativePayload: construction, immutability, safe dict
    - build_screensaver_creative: PlayerPlaylistItem → creative
    - build_screensaver_creative_from_playlist: playlist → creative
    - validate_screensaver_creative: content_type, duration, forbidden patterns
    - decide_creative_visibility: state/kill-switch/creative/playlist
    - ScreensaverPoPDraft: event types, safe dict, no forbidden fields
    - build_screensaver_pop_draft: creative → PoP
    - validate_screensaver_pop_safety: forbidden PoP fields
    - Safety: no UUID, file_path, sha256, backend_url, token, secret
    - Safety: no receipt, payment, fiscal, customer, card, barcode, scanner
"""

import unittest
import json

from kso_player.playlist import PlayerPlaylistItem, PlayerPlaylist
from kso_player.screensaver_creative import (
    ScreensaverCreativePayload,
    ScreensaverPoPDraft,
    ALLOWED_SCREENSAVER_CONTENT_TYPES,
    MIN_DURATION_MS,
    MAX_DURATION_MS,
    MODULE_NAME,
    MODULE_VERSION,
    build_screensaver_creative,
    build_screensaver_creative_from_playlist,
    validate_screensaver_creative,
    decide_creative_visibility,
    build_screensaver_pop_draft,
    validate_screensaver_pop_safety,
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    SCREENSAVER_EVENT_BLOCKED,
    SCREENSAVER_EVENT_TYPES,
    VIS_REASON_EMPTY_PLAYLIST,
    VIS_REASON_NO_VALID_CREATIVE,
    VIS_REASON_CREATIVE_EXPIRED,
    VIS_REASON_CREATIVE_VALID,
    POP_FORBIDDEN_FIELDS,
    CREATIVE_FORBIDDEN_PATTERNS,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _test_item(
    media_ref="slot-000",
    slot_order=0,
    content_type="image/png",
    duration_ms=10_000,
) -> PlayerPlaylistItem:
    return PlayerPlaylistItem(
        media_ref=media_ref,
        slot_order=slot_order,
        content_type=content_type,
        duration_ms=duration_ms,
        order=slot_order,
    )


def _test_playlist(items=None, ready=True, reason="ready"):
    if items is None:
        items = [_test_item()]
    return PlayerPlaylist(
        ready=ready,
        status="ready" if ready else "not_ready",
        reason=reason,
        items_total=len(items),
        items_ready=len(items) if ready else 0,
        items=items,
    )


# ══════════════════════════════════════════════════════════════════════
# ScreensaverCreativePayload — construction and defaults
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverCreativePayload(unittest.TestCase):

    def test_default_creative_is_test(self):
        c = ScreensaverCreativePayload()
        self.assertEqual(c.content_type, "test")
        self.assertEqual(c.duration_ms, 10_000)

    def test_creative_is_immutable(self):
        c = ScreensaverCreativePayload(creative_code="test-001")
        with self.assertRaises(Exception):
            c.creative_code = "hacked"

    def test_to_safe_dict_has_no_forbidden(self):
        c = ScreensaverCreativePayload(
            creative_code="scr-slot-000",
            media_ref="slot-000",
            content_type="image/png",
            duration_ms=30_000,
            slot_order=0,
        )
        d = c.to_safe_dict()
        d_str = json.dumps(d)
        for forbidden in [
            "uuid", "file_path", "sha256", "minio", "storage_ref",
            "backend_url", "token", "secret", "device_secret",
        ]:
            self.assertNotIn(
                forbidden, d_str.lower(),
                f"forbidden '{forbidden}' in safe dict"
            )

    def test_duration_clamped_min(self):
        c = ScreensaverCreativePayload(duration_ms=500)
        self.assertEqual(c.duration_ms, MIN_DURATION_MS)

    def test_duration_clamped_max(self):
        c = ScreensaverCreativePayload(duration_ms=999_999)
        self.assertEqual(c.duration_ms, MAX_DURATION_MS)

    def test_is_valid_true(self):
        c = ScreensaverCreativePayload(
            creative_code="scr-001",
            media_ref="slot-000",
            content_type="image/png",
        )
        self.assertTrue(c.is_valid)

    def test_is_expired_false_when_no_valid_to(self):
        c = ScreensaverCreativePayload()
        self.assertFalse(c.is_expired)

    def test_is_expired_false_with_future_date(self):
        c = ScreensaverCreativePayload(valid_to="2099-01-01T00:00:00+00:00")
        self.assertFalse(c.is_expired)

    def test_is_expired_true_with_past_date(self):
        c = ScreensaverCreativePayload(valid_to="2020-01-01T00:00:00+00:00")
        self.assertTrue(c.is_expired)

    def test_valid_from_and_to_in_safe_dict(self):
        c = ScreensaverCreativePayload(
            creative_code="test",
            valid_from="2026-01-01T00:00:00Z",
            valid_to="2026-12-31T23:59:59Z",
        )
        d = c.to_safe_dict()
        self.assertIn("valid_from", d)
        self.assertIn("valid_to", d)


# ══════════════════════════════════════════════════════════════════════
# build_screensaver_creative — adapter
# ══════════════════════════════════════════════════════════════════════

class TestBuildScreensaverCreative(unittest.TestCase):

    def test_valid_item_maps_to_creative(self):
        item = _test_item(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=15_000,
        )
        c = build_screensaver_creative(item, creative_code="test-creative")
        self.assertEqual(c.creative_code, "test-creative")
        self.assertEqual(c.media_ref, "slot-000")
        self.assertEqual(c.content_type, "image/png")
        self.assertEqual(c.duration_ms, 15_000)
        self.assertEqual(c.slot_order, 0)
        self.assertTrue(c.is_valid)

    def test_item_with_path_in_media_ref_strips_path(self):
        item = _test_item(
            media_ref="media/current/slot-001",
            slot_order=1,
        )
        c = build_screensaver_creative(item, "test-strip")
        self.assertEqual(c.media_ref, "slot-001")

    def test_item_no_media_ref_generates_code(self):
        item = _test_item(media_ref="", slot_order=3, content_type="image/jpeg")
        c = build_screensaver_creative(item)
        self.assertEqual(c.creative_code, "scr-slot-003")
        self.assertEqual(c.content_type, "image/jpeg")

    def test_item_unknown_content_type_falls_back_to_test(self):
        item = _test_item(content_type="application/pdf")
        c = build_screensaver_creative(item, "pdf-test")
        self.assertEqual(c.content_type, "test")

    def test_non_item_input_returns_safe_fallback(self):
        c = build_screensaver_creative(
            "not an item", creative_code="fallback"
        )
        self.assertEqual(c.content_type, "test")
        self.assertEqual(c.creative_code, "fallback")

    def test_duration_below_min_clamped(self):
        item = _test_item(duration_ms=100)
        c = build_screensaver_creative(item)
        self.assertEqual(c.duration_ms, MIN_DURATION_MS)

    def test_duration_above_max_clamped(self):
        item = _test_item(duration_ms=999_999)
        c = build_screensaver_creative(item)
        self.assertEqual(c.duration_ms, MAX_DURATION_MS)

    def test_video_mp4_accepted(self):
        item = _test_item(content_type="video/mp4")
        c = build_screensaver_creative(item, "vid")
        self.assertEqual(c.content_type, "video/mp4")

    def test_test_content_type_accepted(self):
        item = _test_item(content_type="test")
        c = build_screensaver_creative(item, "proof")
        self.assertEqual(c.content_type, "test")

    def test_legacy_item_with_manifest_item_id_not_leaked(self):
        """manifest_item_id (UUID) is never in creative_code or media_ref."""
        item = PlayerPlaylistItem(
            manifest_item_id="abc-123-uuid",
            media_ref="slot-005",
            slot_order=5,
            content_type="image/png",
            duration_ms=20_000,
            filename="creative.png",
            sha256="a" * 64,
        )
        c = build_screensaver_creative(item, "safe-code")
        self.assertEqual(c.creative_code, "safe-code")
        self.assertEqual(c.media_ref, "slot-005")
        # Verify no UUID leaked
        d_str = json.dumps(c.to_safe_dict())
        self.assertNotIn("abc-123-uuid", d_str)
        self.assertNotIn("manifest_item_id", d_str)


# ══════════════════════════════════════════════════════════════════════
# build_screensaver_creative_from_playlist
# ══════════════════════════════════════════════════════════════════════

class TestBuildFromPlaylist(unittest.TestCase):

    def test_valid_playlist_picks_first_item(self):
        pl = _test_playlist(items=[
            _test_item("slot-000", 0, "image/png", 15_000),
            _test_item("slot-001", 1, "video/mp4", 30_000),
        ])
        c = build_screensaver_creative_from_playlist(pl, creative_code="camp-1")
        self.assertEqual(c.creative_code, "camp-1")
        self.assertEqual(c.media_ref, "slot-000")
        self.assertEqual(c.slot_order, 0)

    def test_playlist_picks_by_slot_order(self):
        pl = _test_playlist(items=[
            _test_item("slot-000", 0, "image/png", 15_000),
            _test_item("slot-001", 1, "video/mp4", 30_000),
        ])
        c = build_screensaver_creative_from_playlist(
            pl, slot_order=1, creative_code="second"
        )
        self.assertEqual(c.media_ref, "slot-001")
        self.assertEqual(c.slot_order, 1)

    def test_empty_playlist_returns_fallback(self):
        pl = PlayerPlaylist(ready=False, reason="manifest_missing")
        c = build_screensaver_creative_from_playlist(pl)
        self.assertEqual(c.creative_code, "fallback")
        self.assertEqual(c.content_type, "test")

    def test_not_ready_playlist_returns_fallback(self):
        pl = _test_playlist(ready=False, reason="media_incomplete")
        c = build_screensaver_creative_from_playlist(pl)
        self.assertEqual(c.creative_code, "fallback")

    def test_non_playlist_input_returns_fallback(self):
        c = build_screensaver_creative_from_playlist("not a playlist")
        self.assertEqual(c.creative_code, "fallback")


# ══════════════════════════════════════════════════════════════════════
# validate_screensaver_creative
# ══════════════════════════════════════════════════════════════════════

class TestValidateScreensaverCreative(unittest.TestCase):

    def test_valid_image_png(self):
        c = ScreensaverCreativePayload(
            creative_code="scr-001",
            content_type="image/png",
            duration_ms=10_000,
        )
        result = validate_screensaver_creative(c)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_valid_video_mp4(self):
        c = ScreensaverCreativePayload(
            creative_code="scr-002",
            content_type="video/mp4",
            duration_ms=60_000,
        )
        result = validate_screensaver_creative(c)
        self.assertTrue(result["valid"])

    def test_valid_test_content_type(self):
        c = ScreensaverCreativePayload(
            creative_code="proof-screen",
            content_type="test",
            duration_ms=10_000,
        )
        result = validate_screensaver_creative(c)
        self.assertTrue(result["valid"])

    def test_audio_rejected(self):
        c = ScreensaverCreativePayload(content_type="audio/mpeg")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_audio_ogg_rejected(self):
        c = ScreensaverCreativePayload(content_type="audio/ogg")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_application_rejected(self):
        c = ScreensaverCreativePayload(content_type="application/pdf")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_empty_content_type_rejected(self):
        c = ScreensaverCreativePayload(content_type="")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_duration_clamped_not_revalidated(self):
        """Duration clamped in __post_init__; validate sees valid bounds."""
        c = ScreensaverCreativePayload(duration_ms=999_999)
        self.assertEqual(c.duration_ms, MAX_DURATION_MS)
        result = validate_screensaver_creative(c)
        self.assertTrue(result["valid"])

    def test_duration_below_min_clamped_too(self):
        c = ScreensaverCreativePayload(duration_ms=100)
        self.assertEqual(c.duration_ms, MIN_DURATION_MS)
        result = validate_screensaver_creative(c)
        self.assertTrue(result["valid"])

    def test_backend_url_in_creative_code_rejected(self):
        c = ScreensaverCreativePayload(
            creative_code="backend_url=https://evil.com",
        )
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_token_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(
            media_ref="token=abc123",
        )
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_http_url_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(
            media_ref="https://evil.com/payload",
        )
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_file_url_rejected(self):
        c = ScreensaverCreativePayload(
            media_ref="file:///etc/passwd",
        )
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_secret_in_creative_code_rejected(self):
        c = ScreensaverCreativePayload(creative_code="secret-key")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_minio_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(media_ref="minio:bucket/obj")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_sha256_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(media_ref="sha256=abcdef")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_barcode_in_creative_code_rejected(self):
        c = ScreensaverCreativePayload(creative_code="barcode-123")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_scanner_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(media_ref="scanner-value")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_receipt_in_code_rejected(self):
        c = ScreensaverCreativePayload(creative_code="receipt-id")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_payment_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(media_ref="payment-data")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_fiscal_in_code_rejected(self):
        c = ScreensaverCreativePayload(creative_code="fiscal-data")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_customer_in_media_ref_rejected(self):
        c = ScreensaverCreativePayload(media_ref="customer-info")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_card_in_code_rejected(self):
        c = ScreensaverCreativePayload(creative_code="card-number")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_device_secret_rejected(self):
        c = ScreensaverCreativePayload(
            creative_code="device_secret=xyz"
        )
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_file_path_rejected(self):
        """file_path pattern in media_ref is rejected."""
        c = ScreensaverCreativePayload(media_ref="/var/lib/data")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_storage_ref_rejected(self):
        """storage_ref in creative_code is rejected."""
        c = ScreensaverCreativePayload(creative_code="storage_ref=s3")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])

    def test_backend_host_rejected(self):
        c = ScreensaverCreativePayload(creative_code="backend_host:8080")
        result = validate_screensaver_creative(c)
        self.assertFalse(result["valid"])


# ══════════════════════════════════════════════════════════════════════
# decide_creative_visibility
# ══════════════════════════════════════════════════════════════════════

class TestDecideCreativeVisibility(unittest.TestCase):

    def setUp(self):
        self.creative = ScreensaverCreativePayload(
            creative_code="scr-001",
            media_ref="slot-000",
            content_type="image/png",
            duration_ms=15_000,
        )
        self.pl = _test_playlist()

    def test_idle_valid_creative_visible(self):
        should, reason = decide_creative_visibility(
            self.creative, self.pl, state="idle", kill_switch_active=False,
        )
        self.assertTrue(should)
        self.assertEqual(reason, VIS_REASON_CREATIVE_VALID)

    def test_kill_switch_active_hidden(self):
        should, reason = decide_creative_visibility(
            self.creative, self.pl, state="idle", kill_switch_active=True,
        )
        self.assertFalse(should)
        self.assertEqual(reason, "hidden_kill_switch")

    def test_state_busy_hidden(self):
        should, reason = decide_creative_visibility(
            self.creative, self.pl, state="busy", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, "hidden_state")

    def test_state_payment_hidden(self):
        should, reason = decide_creative_visibility(
            self.creative, self.pl, state="payment", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, "hidden_state")

    def test_state_scan_hidden(self):
        for state in ("scan", "cart", "error", "offline", "unknown", "stale"):
            should, reason = decide_creative_visibility(
                self.creative, self.pl, state=state, kill_switch_active=False,
            )
            self.assertFalse(
                should, f"state={state} should hide"
            )

    def test_empty_playlist_hidden(self):
        pl = PlayerPlaylist(ready=False, reason="manifest_missing")
        should, reason = decide_creative_visibility(
            self.creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, VIS_REASON_EMPTY_PLAYLIST)

    def test_not_ready_playlist_hidden(self):
        pl = _test_playlist(ready=False, reason="media_incomplete")
        should, reason = decide_creative_visibility(
            self.creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, VIS_REASON_EMPTY_PLAYLIST)

    def test_invalid_creative_hidden(self):
        bad = ScreensaverCreativePayload(
            content_type="audio/mpeg",
        )
        should, reason = decide_creative_visibility(
            bad, self.pl, state="idle", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, VIS_REASON_NO_VALID_CREATIVE)

    def test_expired_creative_hidden(self):
        expired = ScreensaverCreativePayload(
            creative_code="scr-old",
            content_type="image/png",
            valid_to="2020-01-01T00:00:00+00:00",
        )
        should, reason = decide_creative_visibility(
            expired, self.pl, state="idle", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, VIS_REASON_CREATIVE_EXPIRED)

    def test_none_playlist_uses_creative_only(self):
        """When playlist is None, skip playlist check."""
        should, reason = decide_creative_visibility(
            self.creative, None, state="idle", kill_switch_active=False,
        )
        self.assertTrue(should)
        self.assertEqual(reason, VIS_REASON_CREATIVE_VALID)


# ══════════════════════════════════════════════════════════════════════
# ScreensaverPoPDraft
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverPoPDraft(unittest.TestCase):

    def test_default_event_type(self):
        pop = ScreensaverPoPDraft()
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_VISIBLE)

    def test_custom_event_type(self):
        pop = ScreensaverPoPDraft(event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED)
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_PLAYBACK_STARTED)

    def test_invalid_event_type_clamped(self):
        pop = ScreensaverPoPDraft(event_type="barcode_scan")
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_HIDDEN)

    def test_all_event_types_valid(self):
        for et in SCREENSAVER_EVENT_TYPES:
            pop = ScreensaverPoPDraft(event_type=et)
            self.assertEqual(pop.event_type, et)

    def test_to_safe_dict_has_no_forbidden(self):
        pop = ScreensaverPoPDraft(
            event_type=SCREENSAVER_EVENT_VISIBLE,
            creative_code="scr-001",
            visible=True,
            state="idle",
            duration_ms=15_000,
            reason="creative_valid",
        )
        d = pop.to_safe_dict()
        d_str = json.dumps(d)
        for forbidden in [
            "barcode", "scanner_value", "receipt", "payment",
            "fiscal", "customer", "card", "pan", "backend_url",
            "token", "secret", "device_secret",
            "file_path", "storage_ref", "minio", "sha256",
        ]:
            self.assertNotIn(
                forbidden, d_str.lower(),
                f"forbidden '{forbidden}' in PoP draft"
            )

    def test_hidden_event(self):
        pop = ScreensaverPoPDraft(
            event_type=SCREENSAVER_EVENT_HIDDEN,
            visible=False,
            reason="hidden_kill_switch",
        )
        self.assertFalse(pop.visible)
        self.assertEqual(pop.reason, "hidden_kill_switch")

    def test_immutable(self):
        pop = ScreensaverPoPDraft()
        with self.assertRaises(Exception):
            pop.event_type = "hacked"


# ══════════════════════════════════════════════════════════════════════
# build_screensaver_pop_draft
# ══════════════════════════════════════════════════════════════════════

class TestBuildScreensaverPopDraft(unittest.TestCase):

    def setUp(self):
        self.creative = ScreensaverCreativePayload(
            creative_code="scr-001",
            content_type="image/png",
            duration_ms=15_000,
        )

    def test_visible_event(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
            state="idle",
            reason="creative_valid",
            duration_ms=15_000,
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_VISIBLE)
        self.assertTrue(pop.visible)
        self.assertEqual(pop.creative_code, "scr-001")
        self.assertEqual(pop.state, "idle")

    def test_hidden_event(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_HIDDEN,
            visible=False,
            reason="hidden_kill_switch",
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_HIDDEN)
        self.assertFalse(pop.visible)

    def test_playback_started_event(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=True,
            state="idle",
            started_at_utc="2026-06-24T23:00:00Z",
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_PLAYBACK_STARTED)
        self.assertEqual(pop.started_at_utc, "2026-06-24T23:00:00Z")

    def test_playback_completed_event(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            state="idle",
            duration_ms=30_000,
            ended_at_utc="2026-06-24T23:00:30Z",
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_PLAYBACK_COMPLETED)
        self.assertEqual(pop.duration_ms, 30_000)
        self.assertEqual(pop.ended_at_utc, "2026-06-24T23:00:30Z")

    def test_invalid_event_type_clamped(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type="scan_event",
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_HIDDEN)

    def test_non_creative_input_handled(self):
        """Non-creative input → empty creative_code, safe fallback."""
        pop = build_screensaver_pop_draft(
            "not a creative",
            event_type=SCREENSAVER_EVENT_HIDDEN,
        )
        self.assertEqual(pop.creative_code, "")

    def test_no_barcode_in_pop(self):
        pop = build_screensaver_pop_draft(
            self.creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
        )
        d = pop.to_safe_dict()
        d_str = json.dumps(d)
        for bad in ["barcode", "scanner", "receipt", "payment"]:
            self.assertNotIn(bad, d_str.lower())


# ══════════════════════════════════════════════════════════════════════
# validate_screensaver_pop_safety
# ══════════════════════════════════════════════════════════════════════

class TestValidateScreensaverPopSafety(unittest.TestCase):

    def test_safe_pop_passes(self):
        pop = ScreensaverPoPDraft(
            event_type=SCREENSAVER_EVENT_VISIBLE,
            creative_code="scr-001",
            visible=True,
            state="idle",
        )
        result = validate_screensaver_pop_safety(pop.to_safe_dict())
        self.assertTrue(result["valid"])

    def test_barcode_field_rejected(self):
        result = validate_screensaver_pop_safety({"barcode": "12345"})
        self.assertFalse(result["valid"])

    def test_scanner_value_rejected(self):
        result = validate_screensaver_pop_safety({"scanner_value": "abc"})
        self.assertFalse(result["valid"])

    def test_receipt_id_rejected(self):
        result = validate_screensaver_pop_safety({"receipt_id": "r-001"})
        self.assertFalse(result["valid"])

    def test_payment_amount_rejected(self):
        result = validate_screensaver_pop_safety({"payment_amount": 100})
        self.assertFalse(result["valid"])

    def test_fiscal_data_rejected(self):
        result = validate_screensaver_pop_safety({"fiscal_data": "fd-001"})
        self.assertFalse(result["valid"])

    def test_customer_name_rejected(self):
        result = validate_screensaver_pop_safety({"customer_name": "John"})
        self.assertFalse(result["valid"])

    def test_card_number_rejected(self):
        result = validate_screensaver_pop_safety({"card_number": "4111..."})
        self.assertFalse(result["valid"])

    def test_backend_url_rejected(self):
        result = validate_screensaver_pop_safety({"backend_url": "http://x"})
        self.assertFalse(result["valid"])

    def test_token_rejected(self):
        result = validate_screensaver_pop_safety({"token": "abc"})
        self.assertFalse(result["valid"])

    def test_secret_rejected(self):
        result = validate_screensaver_pop_safety({"secret": "xyz"})
        self.assertFalse(result["valid"])

    def test_device_secret_rejected(self):
        result = validate_screensaver_pop_safety({"device_secret": "ds"})
        self.assertFalse(result["valid"])

    def test_non_dict_rejected(self):
        result = validate_screensaver_pop_safety("not a dict")
        self.assertFalse(result["valid"])

    def test_forbidden_fields_set_covers_all(self):
        """All expected forbidden fields are in POP_FORBIDDEN_FIELDS."""
        expected = {
            "barcode", "scanner_value", "key_value", "event_key", "event_code",
            "receipt_id", "transaction_id", "payment_amount", "payment_method",
            "fiscal_data", "customer_name", "customer_id", "customer_phone",
            "customer_email", "card_number", "pan", "items", "total_amount",
            "cashier_id", "cashier_name", "receipt_number",
            "backend_url", "token", "secret", "api_key", "password",
            "device_secret", "device_token", "access_token",
            "file_path", "storage_ref", "minio", "sha256",
        }
        self.assertTrue(expected.issubset(POP_FORBIDDEN_FIELDS))


# ══════════════════════════════════════════════════════════════════════
# Integration — creative → runner interaction (no X11)
# ══════════════════════════════════════════════════════════════════════

class TestCreativeRunnerIntegration(unittest.TestCase):

    def test_idle_with_creative_produces_valid_visibility(self):
        """Full chain: playlist → creative → visibility → PoP draft."""
        pl = _test_playlist(items=[
            _test_item("slot-000", 0, "image/png", 15_000),
        ])
        creative = build_screensaver_creative_from_playlist(
            pl, creative_code="camp-summer"
        )
        self.assertTrue(creative.is_valid)

        should, reason = decide_creative_visibility(
            creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertTrue(should)

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
            state="idle",
            reason=reason,
            duration_ms=creative.duration_ms,
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_VISIBLE)
        self.assertEqual(pop.creative_code, "camp-summer")
        self.assertTrue(pop.visible)

        # Safety audit
        pop_result = validate_screensaver_pop_safety(pop.to_safe_dict())
        self.assertTrue(pop_result["valid"])

    def test_kill_switch_active_integration(self):
        pl = _test_playlist()
        creative = build_screensaver_creative_from_playlist(pl, "test")
        should, reason = decide_creative_visibility(
            creative, pl, state="idle", kill_switch_active=True,
        )
        self.assertFalse(should)

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_HIDDEN,
            visible=False,
            reason=reason,
        )
        self.assertFalse(pop.visible)
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_HIDDEN)

    def test_empty_manifest_integration(self):
        pl = PlayerPlaylist(ready=False, reason="manifest_missing")
        creative = build_screensaver_creative_from_playlist(pl)
        # Fallback creative passes safety validation (content_type="test" is valid)
        # But the visibility chain hides because playlist is not ready
        self.assertEqual(creative.content_type, "test")

        should, reason = decide_creative_visibility(
            creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertFalse(should)
        self.assertEqual(reason, VIS_REASON_EMPTY_PLAYLIST)

    def test_expired_creative_integration(self):
        pl = _test_playlist()
        creative = build_screensaver_creative_from_playlist(
            pl, creative_code="old",
            valid_to="2020-01-01T00:00:00Z",
        )
        self.assertTrue(creative.is_expired)

        should, reason = decide_creative_visibility(
            creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertFalse(should)


# ══════════════════════════════════════════════════════════════════════
# Constants and coverage
# ══════════════════════════════════════════════════════════════════════

class TestConstants(unittest.TestCase):

    def test_module_identity(self):
        self.assertEqual(MODULE_NAME, "screensaver_creative")
        self.assertEqual(MODULE_VERSION, "0.1.0")

    def test_allowed_content_types(self):
        self.assertIn("image/png", ALLOWED_SCREENSAVER_CONTENT_TYPES)
        self.assertIn("image/jpeg", ALLOWED_SCREENSAVER_CONTENT_TYPES)
        self.assertIn("video/mp4", ALLOWED_SCREENSAVER_CONTENT_TYPES)
        self.assertIn("test", ALLOWED_SCREENSAVER_CONTENT_TYPES)

    def test_event_types(self):
        self.assertEqual(
            SCREENSAVER_EVENT_TYPES,
            frozenset({
                SCREENSAVER_EVENT_VISIBLE,
                SCREENSAVER_EVENT_HIDDEN,
                SCREENSAVER_EVENT_PLAYBACK_STARTED,
                SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
                SCREENSAVER_EVENT_BLOCKED,
            })
        )

    def test_visibility_reasons(self):
        self.assertEqual(VIS_REASON_EMPTY_PLAYLIST, "empty_playlist")
        self.assertEqual(VIS_REASON_NO_VALID_CREATIVE, "no_valid_creative")
        self.assertEqual(VIS_REASON_CREATIVE_EXPIRED, "creative_expired")
        self.assertEqual(VIS_REASON_CREATIVE_VALID, "creative_valid")


# ══════════════════════════════════════════════════════════════════════
# 38.2.1 — Backend creative_code preservation
# ══════════════════════════════════════════════════════════════════════

class TestCreativeCodePreservation(unittest.TestCase):
    """Backend creative_code flows manifest → playlist → runner → PoP."""

    def test_playlist_item_has_creative_code_field(self):
        """PlayerPlaylistItem accepts creative_code."""
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=15_000,
            creative_code="summer-campaign-001",
        )
        self.assertEqual(item.creative_code, "summer-campaign-001")

    def test_playlist_item_creative_code_default_none(self):
        """creative_code defaults to None when not provided."""
        item = PlayerPlaylistItem()
        self.assertIsNone(item.creative_code)

    def test_creative_code_maps_from_playlist_item(self):
        """Backend creative_code in PlaylistItem → ScreensaverCreativePayload."""
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=15_000,
            creative_code="summer-campaign-001",
        )
        c = build_screensaver_creative(item)
        self.assertEqual(c.creative_code, "summer-campaign-001")
        self.assertFalse(c.is_synthetic)

    def test_creative_code_overrides_caller_param(self):
        """item.creative_code wins over the creative_code function parameter."""
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=15_000,
            creative_code="backend-real-code",
        )
        c = build_screensaver_creative(item, creative_code="caller-fallback")
        self.assertEqual(c.creative_code, "backend-real-code")
        self.assertFalse(c.is_synthetic)

    def test_synthetic_when_no_creative_code(self):
        """When item has no creative_code, synthetic fallback is generated."""
        item = _test_item("slot-000", 0, "image/png", 15_000)
        c = build_screensaver_creative(item)
        self.assertTrue(c.is_synthetic)
        self.assertTrue(c.creative_code.startswith("scr-"))

    def test_synthetic_marked_explicitly(self):
        """is_synthetic=True when creative_code is auto-generated."""
        item = PlayerPlaylistItem(
            media_ref="slot-005",
            slot_order=5,
            content_type="image/png",
            duration_ms=20_000,
            # no creative_code
        )
        c = build_screensaver_creative(item)
        self.assertTrue(c.is_synthetic)
        self.assertEqual(c.creative_code, "scr-slot-005")

    def test_synthetic_in_safe_dict(self):
        """is_synthetic appears in safe dict."""
        c = build_screensaver_creative(
            PlayerPlaylistItem(slot_order=7, content_type="image/png", duration_ms=10000)
        )
        d = c.to_safe_dict()
        self.assertIn("is_synthetic", d)
        self.assertTrue(d["is_synthetic"])

    def test_backend_creative_not_synthetic_in_safe_dict(self):
        """When creative_code comes from backend, is_synthetic=False."""
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            content_type="image/png",
            creative_code="prod-camp-42",
        )
        c = build_screensaver_creative(item)
        self.assertFalse(c.is_synthetic)
        d = c.to_safe_dict()
        self.assertFalse(d["is_synthetic"])

    def test_slot_order_not_identity_when_creative_code_exists(self):
        """slot_order is NOT the creative identity when creative_code is present."""
        item = PlayerPlaylistItem(
            slot_order=999,
            creative_code="real-code",
            content_type="image/png",
            duration_ms=10_000,
        )
        c = build_screensaver_creative(item)
        self.assertEqual(c.creative_code, "real-code")
        self.assertNotEqual(c.creative_code, f"scr-slot-999")
        self.assertFalse(c.is_synthetic)

    def test_media_ref_not_identity_when_creative_code_exists(self):
        """media_ref is NOT the creative identity when creative_code is present."""
        item = PlayerPlaylistItem(
            media_ref="slot-abc",
            creative_code="real-code",
            content_type="image/png",
            duration_ms=10_000,
        )
        c = build_screensaver_creative(item)
        self.assertEqual(c.creative_code, "real-code")
        self.assertNotEqual(c.creative_code, "scr-slot-abc")

    def test_pop_draft_uses_backend_creative_code(self):
        """PoP draft event uses the same creative_code from backend manifest."""
        item = PlayerPlaylistItem(
            creative_code="summer-campaign-001",
            content_type="image/png",
            duration_ms=15_000,
        )
        creative = build_screensaver_creative(item)
        self.assertEqual(creative.creative_code, "summer-campaign-001")

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
            state="idle",
            reason="creative_valid",
            duration_ms=creative.duration_ms,
        )
        self.assertEqual(pop.creative_code, "summer-campaign-001")

    def test_pop_draft_marks_synthetic(self):
        """PoP draft for synthetic creative still reports correct creative_code."""
        item = PlayerPlaylistItem(slot_order=3, content_type="image/png", duration_ms=10_000)
        creative = build_screensaver_creative(item)
        self.assertTrue(creative.is_synthetic)

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
        )
        self.assertEqual(pop.creative_code, "scr-slot-003")

    def test_pop_draft_slot_order_not_identity(self):
        """PoP creative_code is NOT just slot_order stringified."""
        item = PlayerPlaylistItem(
            slot_order=7,
            creative_code="prod-camp-7",
            content_type="image/png",
            duration_ms=10_000,
        )
        creative = build_screensaver_creative(item)
        pop = build_screensaver_pop_draft(creative, event_type=SCREENSAVER_EVENT_VISIBLE)
        self.assertEqual(pop.creative_code, "prod-camp-7")
        self.assertNotEqual(pop.creative_code, "scr-slot-007")

    def test_full_chain_backend_to_pop(self):
        """Full chain: playlist item → creative → visibility → PoP."""
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=15_000,
            creative_code="summer-promo-v2",
        )
        # 1. Playlist item has backend creative_code
        self.assertEqual(item.creative_code, "summer-promo-v2")

        # 2. Adapter preserves it
        creative = build_screensaver_creative(item)
        self.assertEqual(creative.creative_code, "summer-promo-v2")
        self.assertFalse(creative.is_synthetic)

        # 3. Visibility check
        pl = _test_playlist(items=[item])
        should, reason = decide_creative_visibility(
            creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertTrue(should)

        # 4. PoP preserves backend creative_code
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
            visible=True,
            state="idle",
            reason=reason,
            duration_ms=creative.duration_ms,
        )
        self.assertEqual(pop.creative_code, "summer-promo-v2")

        # 5. Safety audit
        pop_result = validate_screensaver_pop_safety(pop.to_safe_dict())
        self.assertTrue(pop_result["valid"])

    def test_no_creative_code_no_problem(self):
        """Missing creative_code is handled gracefully — synthetic fallback."""
        item = PlayerPlaylistItem(
            media_ref="slot-000",
            slot_order=0,
            content_type="image/png",
            duration_ms=10_000,
        )
        self.assertIsNone(item.creative_code)
        creative = build_screensaver_creative(item)
        self.assertTrue(creative.is_synthetic)
        # Still works end-to-end
        pl = _test_playlist(items=[item])
        should, _ = decide_creative_visibility(
            creative, pl, state="idle", kill_switch_active=False,
        )
        self.assertTrue(should)

    def test_empty_creative_code_string_treated_as_missing(self):
        """Empty string creative_code → treated as None."""
        item = PlayerPlaylistItem(
            creative_code="",
            slot_order=0,
            content_type="image/png",
            duration_ms=10_000,
        )
        c = build_screensaver_creative(item)
        self.assertTrue(c.is_synthetic)

    def test_whitespace_only_creative_code_treated_as_missing(self):
        """Whitespace-only creative_code → treated as None."""
        item = PlayerPlaylistItem(
            creative_code="   ",
            slot_order=0,
            content_type="image/png",
            duration_ms=10_000,
        )
        c = build_screensaver_creative(item)
        self.assertTrue(c.is_synthetic)


if __name__ == "__main__":
    unittest.main()
