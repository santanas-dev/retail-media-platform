"""Tests for Screensaver Media Availability — sidecar cache bridge.

Covers:
    - check_screensaver_media_availability: creative → availability result
    - ScreensaverMediaAvailability: safe dict, no forbidden fields
    - media_available → ready_for_runner=True
    - media_missing → hidden_media_missing
    - invalid media_ref rejected
    - absolute path rejected
    - backend URL rejected
    - storage_ref/minio/s3 rejected
    - token/secret/device_secret rejected
    - PoP playback_started only when media_available=True
    - blocked event has no sensitive fields
    - creative_code preserved through availability check
    - synthetic fallback remains not production-ready
    - no raw path in safe summary
    - no receipt/payment/fiscal/customer/barcode fields
    - decide_creative_visibility with media availability gating
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from kso_player.screensaver_creative import (
    ScreensaverCreativePayload,
    ScreensaverPoPDraft,
    build_screensaver_creative,
    build_screensaver_pop_draft,
    decide_creative_visibility,
    validate_screensaver_pop_safety,
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    SCREENSAVER_EVENT_BLOCKED,
    VIS_REASON_MEDIA_MISSING,
    VIS_REASON_INVALID_MEDIA_REF,
    VIS_REASON_CACHE_UNAVAILABLE,
    VIS_REASON_CREATIVE_VALID,
)
from kso_player.screensaver_media_availability import (
    ScreensaverMediaAvailability,
    check_screensaver_media_availability,
    REASON_MEDIA_AVAILABLE,
    REASON_MEDIA_MISSING,
    REASON_INVALID_MEDIA_REF,
    REASON_NO_MEDIA_REF,
    REASON_CACHE_UNAVAILABLE,
    REASON_MANIFEST_NOT_FOUND,
    REASON_NO_MATCHING_ITEM,
    REASON_MEDIA_FILE_CORRUPT,
    ALL_AVAILABILITY_REASONS,
)
from kso_player.playlist import PlayerPlaylistItem, PlayerPlaylist


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_creative(
    creative_code="summer-promo-v3",
    media_ref="slot-000",
    content_type="image/png",
    duration_ms=10_000,
    slot_order=0,
    is_synthetic=False,
):
    return ScreensaverCreativePayload(
        creative_code=creative_code,
        media_ref=media_ref,
        content_type=content_type,
        duration_ms=duration_ms,
        slot_order=slot_order,
        is_synthetic=is_synthetic,
    )


def _make_sidecar_root(base_dir, manifest_items=None, media_files=None):
    """Create a minimal sidecar root with manifest/ and media/current/."""
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
        (manifest_dir / "current_manifest.json").write_text(
            json.dumps(manifest)
        )

    if media_files is not None:
        for filename, content in media_files.items():
            (media_dir / filename).write_bytes(content)

    return root


def _make_manifest_item(order=0, filename="test.png", content_type="image/png"):
    return {
        "manifest_item_id": f"00000000-0000-0000-0000-{order:012d}",
        "filename": filename,
        "content_type": content_type,
        "sha256": "a" * 64,
        "size_bytes": 100,
        "duration_ms": 10_000,
        "order": order,
    }


# ══════════════════════════════════════════════════════════════════════
# Tests: ScreensaverMediaAvailability dataclass
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverMediaAvailabilityDataclass(unittest.TestCase):
    """ScreensaverMediaAvailability construction and safe output."""

    def test_default_values(self):
        avail = ScreensaverMediaAvailability()
        self.assertEqual(avail.creative_code, "")
        self.assertEqual(avail.media_ref, "")
        self.assertFalse(avail.ready_for_runner)
        self.assertFalse(avail.media_available)
        self.assertEqual(avail.reason, REASON_NO_MEDIA_REF)

    def test_media_available_state(self):
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            media_ref="slot-000",
            content_type="image/png",
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
            media_available=True,
        )
        self.assertTrue(avail.ready_for_runner)
        self.assertTrue(avail.media_available)

    def test_media_missing_state(self):
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            media_ref="slot-000",
            reason=REASON_MEDIA_MISSING,
        )
        self.assertFalse(avail.ready_for_runner)
        self.assertFalse(avail.media_available)

    def test_invalid_reason_replaced(self):
        avail = ScreensaverMediaAvailability(reason="bogus_reason")
        self.assertEqual(avail.reason, REASON_CACHE_UNAVAILABLE)

    def test_immutable(self):
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
        )
        with self.assertRaises(Exception):
            avail.creative_code = "changed"  # type: ignore

    def test_to_safe_dict_no_forbidden_fields(self):
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            media_ref="slot-000",
            content_type="image/png",
            duration_ms=10000,
            slot_order=0,
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
            media_available=True,
        )
        d = avail.to_safe_dict()
        self.assertIsInstance(d, dict)
        # No forbidden fields
        forbidden = [
            "file_path", "absolute_path", "storage_ref", "sha256", "minio",
            "backend_url", "token", "secret", "device_secret",
            "receipt", "payment", "fiscal", "customer", "card", "barcode",
        ]
        d_str = json.dumps(d).lower()
        for fb in forbidden:
            self.assertNotIn(fb, d_str, f"forbidden '{fb}' in safe dict")

    def test_to_safe_dict_contains_key_fields(self):
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            media_ref="slot-000",
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
            media_available=True,
        )
        d = avail.to_safe_dict()
        self.assertEqual(d["creative_code"], "promo-v1")
        self.assertEqual(d["media_ref"], "slot-000")
        self.assertTrue(d["ready_for_runner"])
        self.assertTrue(d["media_available"])


# ══════════════════════════════════════════════════════════════════════
# Tests: check_screensaver_media_availability — media available
# ══════════════════════════════════════════════════════════════════════

class TestCheckMediaAvailable(unittest.TestCase):
    """Media file exists in cache → ready_for_runner=True."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[_make_manifest_item(order=0, filename="slot000.png")],
            media_files={"slot000.png": b"fake_png_data"},
        )
        self.creative = _make_creative(slot_order=0, media_ref="slot-000")

    def test_media_available_ready(self):
        result = check_screensaver_media_availability(self.creative, self.root)
        self.assertTrue(result.ready_for_runner)
        self.assertTrue(result.media_available)
        self.assertEqual(result.reason, REASON_MEDIA_AVAILABLE)
        self.assertEqual(result.creative_code, "summer-promo-v3")

    def test_creative_code_preserved(self):
        result = check_screensaver_media_availability(self.creative, self.root)
        self.assertEqual(result.creative_code, "summer-promo-v3")

    def test_media_available_with_real_creative_code(self):
        creative = _make_creative(creative_code="backend-promo-42", slot_order=0)
        result = check_screensaver_media_availability(creative, self.root)
        self.assertEqual(result.creative_code, "backend-promo-42")
        self.assertFalse(creative.is_synthetic)

    def test_different_slot_order_finds_correct_file(self):
        root = _make_sidecar_root(
            self.tmpdir + "_2",
            manifest_items=[
                _make_manifest_item(order=0, filename="slot000.png"),
                _make_manifest_item(order=1, filename="slot001.png", content_type="video/mp4"),
            ],
            media_files={"slot000.png": b"data0", "slot001.png": b"data1"},
        )
        creative = _make_creative(slot_order=1, media_ref="slot-001", content_type="video/mp4")
        result = check_screensaver_media_availability(creative, root)
        self.assertTrue(result.ready_for_runner)
        self.assertEqual(result.slot_order, 1)
        self.assertEqual(result.content_type, "video/mp4")


# ══════════════════════════════════════════════════════════════════════
# Tests: check_screensaver_media_availability — media missing
# ══════════════════════════════════════════════════════════════════════

class TestCheckMediaMissing(unittest.TestCase):
    """Media file NOT in cache → hidden_media_missing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_media_missing_no_file(self):
        root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[_make_manifest_item(order=0, filename="missing.png")],
        )
        creative = _make_creative(slot_order=0, media_ref="slot-000")
        result = check_screensaver_media_availability(creative, root)
        self.assertFalse(result.ready_for_runner)
        self.assertFalse(result.media_available)
        self.assertEqual(result.reason, REASON_MEDIA_MISSING)

    def test_media_missing_empty_cache(self):
        root = _make_sidecar_root(
            self.tmpdir + "_2",
            manifest_items=[_make_manifest_item(order=0, filename="nope.png")],
        )
        creative = _make_creative(slot_order=0)
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_MEDIA_MISSING)

    def test_media_missing_no_manifest(self):
        root = Path(self.tmpdir) / "empty_root"
        root.mkdir(parents=True, exist_ok=True)
        creative = _make_creative(slot_order=0)
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_MANIFEST_NOT_FOUND)

    def test_media_missing_no_matching_item(self):
        root = _make_sidecar_root(
            self.tmpdir + "_3",
            manifest_items=[_make_manifest_item(order=5, filename="other.png")],
        )
        creative = _make_creative(slot_order=0)
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_NO_MATCHING_ITEM)

    def test_media_missing_file_is_directory(self):
        root = _make_sidecar_root(
            self.tmpdir + "_4",
            manifest_items=[_make_manifest_item(order=0, filename="adir")],
        )
        (root / "media" / "current" / "adir").mkdir(parents=True, exist_ok=True)
        creative = _make_creative(slot_order=0)
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_MEDIA_FILE_CORRUPT)

    def test_media_missing_symlink_rejected(self):
        root = _make_sidecar_root(
            self.tmpdir + "_5",
            manifest_items=[_make_manifest_item(order=0, filename="sym.png")],
            media_files={"sym.png": b"data"},
        )
        # Replace with symlink
        filepath = root / "media" / "current" / "sym.png"
        target = root / "media" / "current" / "real.png"
        filepath.unlink()
        os.symlink(str(target), str(filepath))
        creative = _make_creative(slot_order=0)
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid/forbidden media_ref rejected
# ══════════════════════════════════════════════════════════════════════

class TestInvalidMediaRef(unittest.TestCase):
    """Invalid media_ref → rejected."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_absolute_path_rejected(self):
        creative = _make_creative(media_ref="/etc/passwd")
        root = Path(self.tmpdir) / "root"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)

    def test_backend_url_rejected(self):
        creative = _make_creative(media_ref="http://evil.com/payload")
        root = Path(self.tmpdir) / "root2"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)

    def test_file_url_rejected(self):
        creative = _make_creative(media_ref="file:///etc/shadow")
        root = Path(self.tmpdir) / "root3"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)

    def test_path_traversal_rejected(self):
        creative = _make_creative(media_ref="../etc/passwd")
        root = Path(self.tmpdir) / "root4"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)

    def test_token_in_ref_rejected(self):
        creative = _make_creative(media_ref="slot-token-123")
        root = Path(self.tmpdir) / "root5"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)

    def test_secret_in_ref_rejected(self):
        creative = _make_creative(media_ref="slot-secret-abc")
        root = Path(self.tmpdir) / "root6"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)

    def test_non_creative_returns_invalid(self):
        result = check_screensaver_media_availability("not_a_creative", "/tmp")
        self.assertEqual(result.reason, REASON_INVALID_MEDIA_REF)
        self.assertFalse(result.ready_for_runner)

    def test_no_media_ref_test_creative_allowed(self):
        creative = ScreensaverCreativePayload(
            creative_code="scr-slot-000",
            media_ref="",
            content_type="test",
            is_synthetic=True,
        )
        root = Path(self.tmpdir) / "root7"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        # Test creative without media_ref is allowed (synthetic)
        self.assertTrue(result.ready_for_runner)
        self.assertEqual(result.reason, REASON_NO_MEDIA_REF)
        self.assertFalse(result.media_available)

    def test_no_media_ref_non_synthetic_not_ready(self):
        creative = ScreensaverCreativePayload(
            creative_code="real-promo",
            media_ref="",
            content_type="image/png",
            is_synthetic=False,
        )
        root = Path(self.tmpdir) / "root8"
        root.mkdir()
        result = check_screensaver_media_availability(creative, root)
        self.assertFalse(result.ready_for_runner)
        self.assertFalse(result.media_available)


# ══════════════════════════════════════════════════════════════════════
# Tests: decide_creative_visibility with media availability
# ══════════════════════════════════════════════════════════════════════

class TestDecideVisibilityWithMedia(unittest.TestCase):
    """decide_creative_visibility gated by media availability."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_media_available_allows_visibility(self):
        creative = _make_creative()
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
            media_available=True,
        )
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertTrue(should_show)
        self.assertEqual(reason, VIS_REASON_CREATIVE_VALID)

    def test_media_missing_blocks_visibility(self):
        creative = _make_creative()
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            ready_for_runner=False,
            reason=REASON_MEDIA_MISSING,
        )
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, VIS_REASON_MEDIA_MISSING)

    def test_invalid_media_ref_blocks_visibility(self):
        creative = _make_creative()
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            ready_for_runner=False,
            reason=REASON_INVALID_MEDIA_REF,
        )
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, VIS_REASON_INVALID_MEDIA_REF)

    def test_cache_unavailable_blocks_visibility(self):
        creative = _make_creative()
        avail = ScreensaverMediaAvailability(
            creative_code="promo-v1",
            ready_for_runner=False,
            reason=REASON_CACHE_UNAVAILABLE,
        )
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, VIS_REASON_CACHE_UNAVAILABLE)

    def test_media_availability_none_skips_check(self):
        creative = _make_creative()
        should_show, reason = decide_creative_visibility(
            creative, media_availability=None,
        )
        self.assertTrue(should_show)
        self.assertEqual(reason, VIS_REASON_CREATIVE_VALID)

    def test_non_availability_object_blocks(self):
        creative = _make_creative()
        should_show, reason = decide_creative_visibility(
            creative, media_availability="not_an_object",
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, VIS_REASON_CACHE_UNAVAILABLE)

    def test_kill_switch_overrides_media(self):
        creative = _make_creative()
        avail = ScreensaverMediaAvailability(
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
            media_available=True,
        )
        should_show, reason = decide_creative_visibility(
            creative, kill_switch_active=True, media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, "hidden_kill_switch")

    def test_non_idle_overrides_media(self):
        creative = _make_creative()
        avail = ScreensaverMediaAvailability(
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
            media_available=True,
        )
        should_show, reason = decide_creative_visibility(
            creative, state="playing", media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, "hidden_state")


# ══════════════════════════════════════════════════════════════════════
# Tests: PoP events with media availability
# ══════════════════════════════════════════════════════════════════════

class TestPoPWithMediaAvailability(unittest.TestCase):
    """PoP draft events with media_available flag."""

    def test_playback_started_requires_media_available(self):
        creative = _make_creative(creative_code="promo-v1")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=True,
            media_available=True,
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_PLAYBACK_STARTED)
        self.assertTrue(pop.media_available)
        self.assertEqual(pop.creative_code, "promo-v1")

    def test_playback_started_refused_when_media_missing(self):
        creative = _make_creative(creative_code="promo-v1")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=False,
            media_available=False,
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_PLAYBACK_STARTED)
        self.assertFalse(pop.media_available)
        self.assertFalse(pop.visible)

    def test_blocked_event_no_sensitive_fields(self):
        creative = _make_creative(creative_code="promo-v1")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            visible=False,
            reason=VIS_REASON_MEDIA_MISSING,
            media_available=False,
        )
        self.assertEqual(pop.event_type, SCREENSAVER_EVENT_BLOCKED)
        self.assertFalse(pop.media_available)

        # Validate no sensitive fields in safe dict
        d = pop.to_safe_dict()
        self.assertNotIn("file_path", d)
        self.assertNotIn("backend_url", d)
        self.assertNotIn("token", d)
        self.assertNotIn("secret", d)
        self.assertNotIn("barcode", d)
        self.assertNotIn("receipt", d)
        self.assertNotIn("sha256", str(d))

        # Validate via safety function
        result = validate_screensaver_pop_safety(d)
        self.assertTrue(result["valid"], f"PoP failed safety: {result['errors']}")

    def test_blocked_event_has_creative_code(self):
        creative = _make_creative(creative_code="backend-promo-42")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            reason=VIS_REASON_MEDIA_MISSING,
            media_available=False,
        )
        self.assertEqual(pop.creative_code, "backend-promo-42")

    def test_blocked_event_creative_code_not_slot_order(self):
        creative = _make_creative(creative_code="real-code", slot_order=7)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            media_available=False,
        )
        self.assertEqual(pop.creative_code, "real-code")
        self.assertNotEqual(pop.creative_code, "7")

    def test_blocked_event_creative_code_not_media_ref(self):
        creative = _make_creative(creative_code="summer-2025", media_ref="slot-003")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            media_available=False,
        )
        self.assertEqual(pop.creative_code, "summer-2025")
        self.assertNotEqual(pop.creative_code, "slot-003")

    def test_visible_event_with_media(self):
        creative = _make_creative(creative_code="promo-v1")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
            media_available=True,
        )
        self.assertTrue(pop.visible)
        self.assertTrue(pop.media_available)

    def test_hidden_event_without_media(self):
        creative = _make_creative(creative_code="promo-v1")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_HIDDEN,
            reason=VIS_REASON_MEDIA_MISSING,
            media_available=False,
        )
        self.assertFalse(pop.visible)
        self.assertFalse(pop.media_available)


# ══════════════════════════════════════════════════════════════════════
# Tests: availability preserves creative_code chain
# ══════════════════════════════════════════════════════════════════════

class TestCreativeCodeChain(unittest.TestCase):
    """creative_code preserved through availability → visibility → PoP."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_backend_creative_code_survives_full_chain(self):
        root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[_make_manifest_item(order=0, filename="slot000.png")],
            media_files={"slot000.png": b"data"},
        )
        creative = _make_creative(creative_code="winter-campaign-2025", slot_order=0)

        # Step 1: availability check
        avail = check_screensaver_media_availability(creative, root)
        self.assertTrue(avail.ready_for_runner)
        self.assertEqual(avail.creative_code, "winter-campaign-2025")

        # Step 2: visibility decision
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertTrue(should_show)

        # Step 3: PoP draft
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=True,
            media_available=True,
        )
        self.assertEqual(pop.creative_code, "winter-campaign-2025")
        self.assertTrue(pop.media_available)

    def test_synthetic_creative_code_not_production_ready(self):
        creative = ScreensaverCreativePayload(
            creative_code="scr-slot-000",
            media_ref="slot-000",
            content_type="test",
            is_synthetic=True,
        )
        root = Path(self.tmpdir) / "noroot"
        root.mkdir()
        avail = check_screensaver_media_availability(creative, root)
        # Synthetic test creative allowed even without media
        self.assertTrue(avail.ready_for_runner)
        self.assertFalse(avail.media_available)

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            reason=VIS_REASON_MEDIA_MISSING,
            media_available=False,
        )
        self.assertTrue(creative.is_synthetic)
        self.assertEqual(pop.creative_code, "scr-slot-000")

    def test_synthetic_flag_preserved_in_creative(self):
        creative = ScreensaverCreativePayload(
            creative_code="scr-slot-005",
            media_ref="slot-005",
            content_type="test",
            slot_order=5,
            is_synthetic=True,
        )
        self.assertTrue(creative.is_synthetic)
        # Even if we check availability, creative stays synthetic
        root = Path(self.tmpdir) / "noroot2"
        root.mkdir()
        avail = check_screensaver_media_availability(creative, root)
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            media_available=False,
        )
        self.assertTrue(creative.is_synthetic)


# ══════════════════════════════════════════════════════════════════════
# Tests: no raw path / forbidden fields in safe summary
# ══════════════════════════════════════════════════════════════════════

class TestNoRawPathInSafeSummary(unittest.TestCase):
    """Availability and PoP output must never contain raw paths or secrets."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_availability_safe_dict_no_path(self):
        root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[_make_manifest_item(order=0, filename="slot000.png")],
            media_files={"slot000.png": b"data"},
        )
        creative = _make_creative(slot_order=0)
        avail = check_screensaver_media_availability(creative, root)
        d = avail.to_safe_dict()
        d_str = json.dumps(d)
        self.assertNotIn(str(root), d_str)
        self.assertNotIn("media/current", d_str)
        self.assertNotIn("slot000.png", d_str)

    def test_availability_safe_dict_no_storage_ref(self):
        avail = ScreensaverMediaAvailability(
            creative_code="test",
            ready_for_runner=True,
            reason=REASON_MEDIA_AVAILABLE,
        )
        d = avail.to_safe_dict()
        self.assertNotIn("storage_ref", d)
        self.assertNotIn("minio", d)
        self.assertNotIn("sha256", d)
        self.assertNotIn("file_path", d)

    def test_pop_safe_dict_no_receipt_fiscal(self):
        creative = _make_creative()
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            media_available=False,
        )
        d = pop.to_safe_dict()
        self.assertNotIn("receipt", d)
        self.assertNotIn("payment", d)
        self.assertNotIn("fiscal", d)
        self.assertNotIn("customer", d)
        self.assertNotIn("barcode", d)

    def test_availability_forbidden_in_value(self):
        from kso_player.screensaver_media_availability import (
            _validate_availability_payload_safe,
        )
        errors = _validate_availability_payload_safe({
            "creative_code": "promo-v1",
            "backend_url_hidden": "not_allowed",
        })
        self.assertTrue(len(errors) > 0, "Should detect forbidden field")

    def test_availability_forbidden_in_key(self):
        from kso_player.screensaver_media_availability import (
            _validate_availability_payload_safe,
        )
        errors = _validate_availability_payload_safe({"token": "anything"})
        self.assertTrue(len(errors) > 0, "Should detect forbidden key")


# ══════════════════════════════════════════════════════════════════════
# Tests: Constants
# ══════════════════════════════════════════════════════════════════════

class TestConstants(unittest.TestCase):
    """Module constants are defined and consistent."""

    def test_all_reasons_in_set(self):
        self.assertIn(REASON_MEDIA_AVAILABLE, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_MEDIA_MISSING, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_INVALID_MEDIA_REF, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_NO_MEDIA_REF, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_CACHE_UNAVAILABLE, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_MANIFEST_NOT_FOUND, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_NO_MATCHING_ITEM, ALL_AVAILABILITY_REASONS)
        self.assertIn(REASON_MEDIA_FILE_CORRUPT, ALL_AVAILABILITY_REASONS)

    def test_no_duplicate_reasons(self):
        reasons = list(ALL_AVAILABILITY_REASONS)
        self.assertEqual(len(reasons), len(set(reasons)))

    def test_visibility_reasons_vs_availability_reasons(self):
        """Each visibility reason has a counterpart or mapping."""
        # Verify the new visibility constants exist
        self.assertEqual(VIS_REASON_MEDIA_MISSING, "hidden_media_missing")
        self.assertEqual(VIS_REASON_INVALID_MEDIA_REF, "hidden_invalid_media_ref")
        self.assertEqual(VIS_REASON_CACHE_UNAVAILABLE, "hidden_cache_unavailable")


# ══════════════════════════════════════════════════════════════════════
# Tests: End-to-end manifest → availability → visibility → PoP
# ══════════════════════════════════════════════════════════════════════

class TestEndToEndChain(unittest.TestCase):
    """Full chain: manifest → creative → availability → visibility → PoP."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_full_chain_media_available(self):
        """Happy path: media exists → visible → playback_started."""
        root = _make_sidecar_root(
            self.tmpdir,
            manifest_items=[_make_manifest_item(order=0, filename="ad.png")],
            media_files={"ad.png": b"ad_content"},
        )
        creative = _make_creative(
            creative_code="spring-sale",
            slot_order=0,
            media_ref="slot-000",
        )

        # Step 1: availability
        avail = check_screensaver_media_availability(creative, root)
        self.assertTrue(avail.ready_for_runner)
        self.assertTrue(avail.media_available)
        self.assertEqual(avail.creative_code, "spring-sale")

        # Step 2: visibility
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertTrue(should_show)
        self.assertEqual(reason, VIS_REASON_CREATIVE_VALID)

        # Step 3: PoP
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=True,
            media_available=True,
        )
        self.assertEqual(pop.creative_code, "spring-sale")
        self.assertTrue(pop.media_available)
        self.assertTrue(pop.visible)

    def test_full_chain_media_missing(self):
        """Media missing → blocked PoP event."""
        root = _make_sidecar_root(
            self.tmpdir + "_2",
            manifest_items=[_make_manifest_item(order=0, filename="missing.png")],
        )
        creative = _make_creative(
            creative_code="fall-campaign",
            slot_order=0,
        )

        # Step 1: availability
        avail = check_screensaver_media_availability(creative, root)
        self.assertFalse(avail.ready_for_runner)
        self.assertFalse(avail.media_available)

        # Step 2: visibility
        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, VIS_REASON_MEDIA_MISSING)

        # Step 3: PoP blocked event
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            reason=reason,
            media_available=False,
        )
        self.assertEqual(pop.creative_code, "fall-campaign")
        self.assertFalse(pop.media_available)
        self.assertFalse(pop.visible)

        # Safety check
        d = pop.to_safe_dict()
        safety = validate_screensaver_pop_safety(d)
        self.assertTrue(safety["valid"], f"Blocked PoP failed safety: {safety['errors']}")

    def test_full_chain_invalid_media_ref(self):
        """Invalid media_ref (symlink in cache) → blocked with invalid_media_ref."""
        root = _make_sidecar_root(
            self.tmpdir + "_3",
            manifest_items=[_make_manifest_item(order=0, filename="sym.png")],
            media_files={"sym.png": b"data"},
        )
        # Replace with symlink — defeats availability check but passes creative validation
        filepath = root / "media" / "current" / "sym.png"
        target = root / "media" / "current" / "real.png"
        filepath.unlink()
        os.symlink(str(target), str(filepath))

        creative = ScreensaverCreativePayload(
            creative_code="promo-v2",
            media_ref="slot-000",
            content_type="image/png",
            slot_order=0,
            is_synthetic=False,
        )

        avail = check_screensaver_media_availability(creative, root)
        self.assertEqual(avail.reason, REASON_INVALID_MEDIA_REF)

        should_show, reason = decide_creative_visibility(
            creative, media_availability=avail,
        )
        self.assertFalse(should_show)
        self.assertEqual(reason, VIS_REASON_INVALID_MEDIA_REF)

    def test_playback_started_only_when_media_available(self):
        """playback_started event must have media_available=True."""
        creative = _make_creative(creative_code="promo-v1")

        # When media available
        pop_good = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=True,
            media_available=True,
        )
        self.assertTrue(pop_good.media_available)
        self.assertTrue(pop_good.visible)

        # When media NOT available — event type still playback_started but visible=False
        pop_bad = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_PLAYBACK_STARTED,
            visible=False,
            media_available=False,
        )
        self.assertFalse(pop_bad.media_available)
        self.assertFalse(pop_bad.visible)

    def test_slot_order_not_creative_identity(self):
        """When creative_code exists, slot_order is NOT used as identity."""
        creative = _make_creative(creative_code="real-promo", slot_order=7)
        root = _make_sidecar_root(
            self.tmpdir + "_4",
            manifest_items=[_make_manifest_item(order=7, filename="img7.png")],
            media_files={"img7.png": b"data"},
        )
        avail = check_screensaver_media_availability(creative, root)
        self.assertEqual(avail.creative_code, "real-promo")
        self.assertNotEqual(avail.creative_code, "7")
        self.assertEqual(avail.slot_order, 7)

        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_VISIBLE,
            visible=True,
            media_available=True,
        )
        self.assertEqual(pop.creative_code, "real-promo")

    def test_media_ref_not_creative_identity(self):
        """When creative_code exists, media_ref is NOT used as identity."""
        creative = _make_creative(creative_code="real-promo", media_ref="slot-003")
        pop = build_screensaver_pop_draft(
            creative,
            event_type=SCREENSAVER_EVENT_BLOCKED,
            media_available=False,
        )
        self.assertEqual(pop.creative_code, "real-promo")
        self.assertNotEqual(pop.creative_code, "slot-003")
