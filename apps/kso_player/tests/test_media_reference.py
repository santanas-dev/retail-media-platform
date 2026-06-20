"""Tests for KSO Player Safe Local Media Reference Core.

Tests build_kso_safe_media_reference() and
build_kso_safe_media_reference_from_render_plan().
Uses playlist fixtures. NO backend, NO HTTP, NO media bytes.
"""

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_player.media_reference import (
    KsoSafeMediaReferenceResult,
    build_kso_safe_media_reference,
    build_kso_safe_media_reference_from_render_plan,
    format_kso_safe_media_reference_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    MEDIA_REF_KIND_LOCAL_ALIAS,
    MEDIA_REF_KIND_NONE,
    REASON_VALID_REFERENCE,
    REASON_UNSUPPORTED_MEDIA_TYPE,
    REASON_NO_SELECTED_ITEM,
    REASON_UNSAFE_ALIAS,
    REASON_INVALID_ARGS,
    FORBIDDEN_SUBSTRINGS,
)

from kso_player.render_plan import (
    KsoRenderPlanResult,
    RENDER_ACTION_RENDER,
    RENDER_ACTION_HOLD,
    MEDIA_IMAGE, MEDIA_VIDEO, MEDIA_UNKNOWN,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return False
    return True


def _sha(content):
    return hashlib.sha256(content).hexdigest()


CONTENT = b"fake-media-content"
CONTENT_SHA = _sha(CONTENT)


@dataclass
class FakePlaylistItem:
    """Fake playlist item for testing media reference."""
    manifest_item_id: str = "m-001"
    filename: str = "ad_001.png"
    content_type: str = "image/png"
    duration_ms: int = 5000
    order: int = 0
    sha256: str = ""
    size_bytes: int = 1024

    def __post_init__(self):
        if not self.sha256:
            self.sha256 = CONTENT_SHA


# ══════════════════════════════════════════════════════════════════════
# Tests: valid media references
# ══════════════════════════════════════════════════════════════════════

class TestValidMediaReference(TestCase):
    """Valid items → media_ref_present=true with safe alias."""

    def test_image_item_produces_media_ref(self):
        item = FakePlaylistItem(content_type="image/png", order=0)
        result = build_kso_safe_media_reference(item)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.media_ref_present)
        self.assertEqual(result.media_ref_kind, MEDIA_REF_KIND_LOCAL_ALIAS)
        self.assertEqual(result.media_type, MEDIA_IMAGE)
        self.assertEqual(result.reason, REASON_VALID_REFERENCE)

    def test_video_item_produces_media_ref(self):
        item = FakePlaylistItem(content_type="video/mp4", order=3)
        result = build_kso_safe_media_reference(item)
        self.assertTrue(result.media_ref_present)
        self.assertEqual(result.media_type, MEDIA_VIDEO)

    def test_multiple_orders_produce_different_refs(self):
        item0 = FakePlaylistItem(content_type="image/png", order=0)
        item5 = FakePlaylistItem(content_type="image/jpeg", order=5)
        r0 = build_kso_safe_media_reference(item0)
        r5 = build_kso_safe_media_reference(item5)
        self.assertNotEqual(r0._media_ref, r5._media_ref)

    def test_order_zero_formatted(self):
        item = FakePlaylistItem(content_type="image/png", order=0)
        result = build_kso_safe_media_reference(item)
        self.assertEqual(result._media_ref, "media/current/slot-000")

    def test_order_42_formatted(self):
        item = FakePlaylistItem(content_type="video/mp4", order=42)
        result = build_kso_safe_media_reference(item)
        self.assertEqual(result._media_ref, "media/current/slot-042")

    def test_order_999_formatted(self):
        item = FakePlaylistItem(content_type="image/jpeg", order=999)
        result = build_kso_safe_media_reference(item)
        self.assertEqual(result._media_ref, "media/current/slot-999")


# ══════════════════════════════════════════════════════════════════════
# Tests: no media reference (unsupported / missing)
# ══════════════════════════════════════════════════════════════════════

class TestNoMediaReference(TestCase):
    """Invalid/unsupported → no media_ref."""

    def test_unsupported_media_type(self):
        item = FakePlaylistItem(content_type="audio/mpeg", order=0)
        result = build_kso_safe_media_reference(item)
        self.assertFalse(result.media_ref_present)
        self.assertEqual(result.reason, REASON_UNSUPPORTED_MEDIA_TYPE)

    def test_text_media_type_rejected(self):
        item = FakePlaylistItem(content_type="text/html", order=0)
        result = build_kso_safe_media_reference(item)
        self.assertFalse(result.media_ref_present)

    def test_none_selected_item(self):
        result = build_kso_safe_media_reference(None)
        self.assertFalse(result.media_ref_present)
        self.assertEqual(result.reason, REASON_NO_SELECTED_ITEM)
        self.assertEqual(result.status, STATUS_WARNING)

    def test_item_with_no_order(self):
        item = FakePlaylistItem(content_type="image/png", order=-1)
        result = build_kso_safe_media_reference(item)
        self.assertFalse(result.media_ref_present)

    def test_item_with_non_int_order(self):
        item = FakePlaylistItem(content_type="image/png")
        item.order = "abc"
        result = build_kso_safe_media_reference(item)
        self.assertFalse(result.media_ref_present)


# ══════════════════════════════════════════════════════════════════════
# Tests: unsafe alias rejection
# ══════════════════════════════════════════════════════════════════════

class TestUnsafeAliasRejection(TestCase):
    """Unsafe aliases (even from order) are rejected via whitelist."""

    def test_valid_alias_always_safe(self):
        # Generated aliases are always safe — verified by whitelist
        item = FakePlaylistItem(content_type="image/png", order=0)
        result = build_kso_safe_media_reference(item)
        self.assertTrue(result.media_ref_present)
        # Check that _media_ref passes validation
        ref = result._media_ref
        self.assertTrue(ref.startswith("media/current/slot-"))
        self.assertNotIn("..", ref)
        self.assertNotIn("//", ref)
        self.assertNotIn("\\", ref)

    def test_alias_never_contains_forbidden(self):
        for order in range(0, 100):
            item = FakePlaylistItem(content_type="image/png", order=order)
            result = build_kso_safe_media_reference(item)
            if result.media_ref_present:
                ref = result._media_ref
                self.assertNotIn("..", ref)
                self.assertNotIn("file:", ref)
                self.assertNotIn("http:", ref)


# ══════════════════════════════════════════════════════════════════════
# Tests: from render plan
# ══════════════════════════════════════════════════════════════════════

class TestFromRenderPlan(TestCase):
    """build_kso_safe_media_reference_from_render_plan."""

    def test_render_plan_with_item(self):
        item = FakePlaylistItem(content_type="image/png", order=3)
        rp = KsoRenderPlanResult(
            status=STATUS_OK,
            render_action=RENDER_ACTION_RENDER,
            _selected_item=item,
        )
        result = build_kso_safe_media_reference_from_render_plan(rp)
        self.assertTrue(result.media_ref_present)
        self.assertEqual(result._media_ref, "media/current/slot-003")

    def test_render_plan_with_none_item(self):
        rp = KsoRenderPlanResult(
            status=STATUS_OK,
            render_action=RENDER_ACTION_HOLD,
            _selected_item=None,
        )
        result = build_kso_safe_media_reference_from_render_plan(rp)
        self.assertFalse(result.media_ref_present)

    def test_null_render_plan(self):
        result = build_kso_safe_media_reference_from_render_plan(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(TestCase):
    """repr/format never exposes paths, IDs, hashes, internal ref."""

    def test_repr_no_media_ref(self):
        item = FakePlaylistItem(content_type="image/png", order=0)
        result = build_kso_safe_media_reference(item)
        text = repr(result)
        self.assertNotIn("_media_ref", text)
        self.assertNotIn("slot-", text)
        self.assertNotIn("media/current", text)

    def test_repr_no_path(self):
        item = FakePlaylistItem(content_type="image/png")
        result = build_kso_safe_media_reference(item)
        text = repr(result)
        self.assertNotIn("/home", text)
        self.assertNotIn("ad_001", text)

    def test_repr_no_ids(self):
        item = FakePlaylistItem(content_type="image/png")
        result = build_kso_safe_media_reference(item)
        text = repr(result)
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "schedule_item_id", "sha256"):
            self.assertNotIn(fb, text)

    def test_repr_no_forbidden(self):
        item = FakePlaylistItem(content_type="image/png")
        result = build_kso_safe_media_reference(item)
        text = repr(result) + format_kso_safe_media_reference_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_format_safe(self):
        item = FakePlaylistItem(content_type="image/png")
        result = build_kso_safe_media_reference(item)
        text = format_kso_safe_media_reference_result(result)
        self.assertIn("media_ref_present: true", text)
        self.assertIn("media_ref_kind: local_alias", text)
        self.assertTrue(_no_forbidden(text))

    def test_format_no_media_ref_value(self):
        item = FakePlaylistItem(content_type="image/png", order=0)
        result = build_kso_safe_media_reference(item)
        text = format_kso_safe_media_reference_result(result)
        self.assertNotIn("slot-", text)
        self.assertNotIn("media/current", text)

    def test_no_stacktrace(self):
        result = build_kso_safe_media_reference(None)
        text = repr(result) + format_kso_safe_media_reference_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("stacktrace", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """No media bytes, no HTTP, no backend, no config."""

    def test_no_media_bytes_read(self):
        import kso_player.media_reference as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("read_bytes", source)

    def test_no_http_no_backend(self):
        import kso_player.media_reference as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_no_secret_read(self):
        import kso_player.media_reference as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("os.environ", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("configparser", source.lower())

    def test_no_direct_chromium(self):
        import kso_player.media_reference as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("subprocess", source.lower())
        self.assertNotIn("webbrowser", source.lower())
        self.assertNotIn("os.system", source.lower())

    def test_no_windows_msi_programdata(self):
        import kso_player.media_reference as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)


if __name__ == "__main__":
    import unittest
    unittest.main()
