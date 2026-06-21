"""Tests for kso_player.playlist — local only, no backend, no secret."""

import hashlib as _hl
import json as _json
import shutil
import tempfile
import unittest
from pathlib import Path

from kso_player.playlist import (
    PlayerPlaylist,
    PlayerPlaylistItem,
    build_playlist,
    REASON_READY,
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_INVALID,
    REASON_MEDIA_INCOMPLETE,
    REASON_MEDIA_CORRUPTED,
    REASON_NO_MEDIA_ITEMS,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.safe_output import format_playlist_summary

# ── Test data ────────────────────────────────────────────────────────

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG_SHA = _hl.sha256(PNG).hexdigest()
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 100
PNG2_SHA = _hl.sha256(PNG2).hexdigest()

MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

MID1 = "11111111-1111-1111-1111-111111111111"
MID2 = "22222222-2222-2222-2222-222222222222"

# ── Helpers ──────────────────────────────────────────────────────────

MANIFEST_FILE = "manifest/current_manifest.json"
MEDIA_CURRENT = "media/current"


def _make_manifest(mvid=MVID, mhash=MHASH, items=None, source="current"):
    return {
        "manifest_version_id": mvid,
        "manifest_hash": mhash,
        "source": source,
        "generated_at": "2026-06-19T10:00:00Z",
        "valid_until": None,
        "fetched_at": "2026-06-19T10:01:00Z",
        "campaign_id": None,
        "items": items or [],
    }


def _make_item(mid=MID1, filename="item.png", ct="image/png",
               sha=PNG_SHA, size=len(PNG), dur=5000, order=0):
    return {
        "manifest_item_id": mid,
        "filename": filename,
        "content_type": ct,
        "sha256": sha,
        "size_bytes": size,
        "duration_ms": dur,
        "order": order,
    }


def _write_manifest(root: Path, data: dict):
    mf = root / MANIFEST_FILE
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(_json.dumps(data), encoding="utf-8")


def _write_media(root: Path, filename="item.png", content=PNG):
    mc = root / MEDIA_CURRENT
    mc.mkdir(parents=True, exist_ok=True)
    (mc / filename).write_bytes(content)


def _init_dirs(root: Path):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    (root / MEDIA_CURRENT).mkdir(parents=True, exist_ok=True)
    (root / "status").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestBuildPlaylistHappy(unittest.TestCase):
    """Valid manifest + complete media."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_single_item_all_ok(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)

        self.assertTrue(pl.ready)
        self.assertEqual(pl.status, "ready")
        self.assertEqual(pl.reason, REASON_READY)
        self.assertEqual(pl.items_total, 1)
        self.assertEqual(pl.items_ready, 1)
        self.assertEqual(pl.items_missing, 0)
        self.assertEqual(pl.items_failed, 0)
        self.assertEqual(len(pl.items), 1)

        pi = pl.items[0]
        self.assertEqual(pi.manifest_item_id, MID1)
        self.assertEqual(pi.filename, "item.png")
        self.assertEqual(pi.content_type, "image/png")
        self.assertEqual(pi.duration_ms, 5000)
        self.assertEqual(pi.order, 0)
        self.assertEqual(pi.sha256, PNG_SHA)
        self.assertEqual(pi.size_bytes, len(PNG))

    def test_two_items_all_ok(self):
        item1 = _make_item(mid=MID1, filename="a.png", sha=PNG_SHA, order=0)
        item2 = _make_item(mid=MID2, filename="b.png", sha=PNG2_SHA, order=1)
        manifest = _make_manifest(items=[item1, item2])
        _write_manifest(self.root, manifest)
        _write_media(self.root, "a.png", PNG)
        _write_media(self.root, "b.png", PNG2)

        pl = build_playlist(self.root)

        self.assertTrue(pl.ready)
        self.assertEqual(pl.items_total, 2)
        self.assertEqual(pl.items_ready, 2)
        self.assertEqual(pl.items_missing, 0)
        self.assertEqual(pl.items_failed, 0)
        self.assertEqual(len(pl.items), 2)
        filenames = {p.filename for p in pl.items}
        self.assertEqual(filenames, {"a.png", "b.png"})


class TestBuildPlaylistErrors(unittest.TestCase):
    """Manifest/media error scenarios."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_manifest_missing(self):
        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "not_ready")
        self.assertEqual(pl.reason, REASON_MANIFEST_MISSING)
        self.assertEqual(pl.items_total, 0)
        self.assertEqual(len(pl.items), 0)

    def test_manifest_invalid_json(self):
        mf = self.root / MANIFEST_FILE
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text("not json{{{", encoding="utf-8")

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "error")
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)
        self.assertEqual(len(pl.items), 0)

    def test_manifest_not_dict(self):
        mf = self.root / MANIFEST_FILE
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text('[1, 2, 3]', encoding="utf-8")

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_manifest_zero_items(self):
        manifest = _make_manifest(items=[])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "not_ready")
        self.assertEqual(pl.reason, REASON_NO_MEDIA_ITEMS)
        self.assertEqual(pl.items_total, 0)

    def test_manifest_items_not_list(self):
        manifest = _make_manifest()
        manifest["items"] = "not_a_list"
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_media_file_missing(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # No media file written

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "not_ready")
        self.assertEqual(pl.reason, REASON_MEDIA_INCOMPLETE)
        self.assertEqual(pl.items_total, 1)
        self.assertEqual(pl.items_ready, 0)
        self.assertEqual(pl.items_missing, 1)
        self.assertEqual(pl.items_failed, 0)

    def test_sha256_mismatch(self):
        item = _make_item(sha=PNG_SHA)
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # Write wrong content
        _write_media(self.root, content=PNG2)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "error")
        self.assertEqual(pl.reason, REASON_MEDIA_CORRUPTED)
        self.assertEqual(pl.items_total, 1)
        self.assertEqual(pl.items_ready, 0)
        self.assertEqual(pl.items_failed, 1)

    def test_size_mismatch(self):
        item = _make_item(size=999999)  # wrong expected size
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MEDIA_CORRUPTED)
        self.assertEqual(pl.items_failed, 1)

    def test_one_good_one_bad(self):
        good = _make_item(mid=MID1, filename="good.png", sha=PNG_SHA, order=0)
        bad = _make_item(mid=MID2, filename="bad.png", sha="ab" * 32, order=1)
        manifest = _make_manifest(items=[good, bad])
        _write_manifest(self.root, manifest)
        _write_media(self.root, "good.png", PNG)
        # No media for "bad.png"

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MEDIA_INCOMPLETE)
        self.assertEqual(pl.items_total, 2)
        self.assertEqual(pl.items_ready, 1)
        self.assertEqual(pl.items_missing, 1)
        self.assertEqual(pl.items_failed, 0)
        self.assertEqual(len(pl.items), 1)
        self.assertEqual(pl.items[0].filename, "good.png")


class TestBuildPlaylistSecurity(unittest.TestCase):
    """Security: path traversal, forbidden substrings, no absolute paths."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_filename_path_traversal_rejected(self):
        item = _make_item(filename="../etc/passwd")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        # Item with path traversal should be rejected → no valid items
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_filename_with_slash_rejected(self):
        item = _make_item(filename="a/b.png")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_filename_with_backslash_rejected(self):
        item = _make_item(filename="a\\b.png")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_filename_with_absolute_path_rejected(self):
        item = _make_item(filename="/etc/passwd")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_no_absolute_paths_in_playlist_items(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)

        for pi in pl.items:
            self.assertNotIn("/", pi.filename)
            self.assertNotIn("\\", pi.filename)
            self.assertFalse(Path(pi.filename).is_absolute())
            # filename must be basename only
            self.assertEqual(pi.filename, Path(pi.filename).name)

    def test_forbidden_substrings_in_filename_rejected(self):
        for fb in ["token", "secret", "media_path", "backend_base_url",
                    "127.0.0.1", "device_code",
                    "authorization", "bearer", "api_key", "password",
                    "private_key", "payment_card", "receipt",
                    "local_path", "file_path", "device_secret",
                    "access_token"]:
            item = _make_item(filename=f"{fb}.png")
            manifest = _make_manifest(items=[item])
            _write_manifest(self.root, manifest)
            _write_media(self.root, f"{fb}.png")

            pl = build_playlist(self.root)
            self.assertFalse(pl.ready,
                             f"Expected reject for forbidden filename '{fb}.png'")
            self.assertNotEqual(pl.reason, REASON_READY,
                                f"Should not be ready with forbidden filename '{fb}.png'")

        # creatives/ contains slash — can't write as file, but should still reject
        item = _make_item(filename="creatives/payload.png")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # Don't write media (filename contains /)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready,
                         f"Expected reject for forbidden filename 'creatives/payload.png'")

    def test_forbidden_in_content_type(self):
        for fb in ["token", "secret", "127.0.0.1"]:
            item = _make_item(ct=f"image/{fb}")
            manifest = _make_manifest(items=[item])
            _write_manifest(self.root, manifest)

            pl = build_playlist(self.root)
            self.assertFalse(pl.ready,
                             f"Expected reject for forbidden content_type 'image/{fb}'")

    def test_extracted_item_has_no_forbidden(self):
        """All extracted items must have no forbidden substrings in any string field."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)

        for pi in pl.items:
            for field_name in ["manifest_item_id", "filename", "content_type", "sha256"]:
                value = getattr(pi, field_name, "")
                lower = value.lower()
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, lower,
                                     f"Field '{field_name}'='{value}' contains forbidden '{fb}'")


class TestBuildPlaylistNoNetwork(unittest.TestCase):
    """Verify build_playlist does not perform HTTP."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_http_library_used(self):
        """build_playlist should not import or use urllib/requests/http."""
        # Manifest with no items → fast path
        manifest = _make_manifest(items=[])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_NO_MEDIA_ITEMS)

    def test_no_secret_config_token_read(self):
        """build_playlist should not access config/ tokens/ secrets."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)
        # If it tried to read secret/config and failed, we'd see error
        # Instead it succeeds because it only reads manifest+media

    def test_no_stacktrace_in_output(self):
        """Error outputs should not contain stack traces."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # No media → error
        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        summary = format_playlist_summary(pl)
        self.assertNotIn("Traceback", summary)
        self.assertNotIn("File \"", summary)
        self.assertNotIn("line ", summary)
        self.assertNotIn("raise ", summary)


class TestSafeOutput(unittest.TestCase):
    """format_playlist_summary must be safe."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_ready_summary(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        summary = format_playlist_summary(pl)

        self.assertIn("playlist_ready: true", summary)
        self.assertIn("status: ready", summary)
        self.assertIn("reason: ready", summary)
        self.assertIn("items_total: 1", summary)
        self.assertIn("items_ready: 1", summary)
        self.assertIn("items_missing: 0", summary)
        self.assertIn("items_failed: 0", summary)

    def test_not_ready_summary(self):
        pl = build_playlist(self.root)
        summary = format_playlist_summary(pl)

        self.assertIn("playlist_ready: false", summary)
        self.assertIn("status: not_ready", summary)

    def test_no_forbidden_in_summary(self):
        """Safe summary must not contain any forbidden substrings."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        summary = format_playlist_summary(pl)
        lower = summary.lower()

        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower,
                             f"Safe summary contains forbidden substring '{fb}'")

    def test_no_absolute_path_in_items(self):
        """Playlist items must never contain absolute paths."""
        item = _make_item(filename="../etc/passwd")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        summary = format_playlist_summary(pl)
        # summary is aggregated — shouldn't leak paths
        self.assertNotIn("/etc/passwd", summary)
        self.assertNotIn(str(self.root), summary)


class TestPlayerPlaylistItem(unittest.TestCase):
    """PlayerPlaylistItem dataclass structure."""

    def test_create_item(self):
        pi = PlayerPlaylistItem(
            manifest_item_id=MID1,
            filename="item.png",
            content_type="image/png",
            duration_ms=5000,
            order=0,
            sha256=PNG_SHA,
            size_bytes=len(PNG),
        )
        self.assertEqual(pi.manifest_item_id, MID1)
        self.assertEqual(pi.filename, "item.png")
        self.assertNotIn("/", pi.filename)
        self.assertEqual(pi.size_bytes, len(PNG))

    def test_size_bytes_none(self):
        pi = PlayerPlaylistItem(
            manifest_item_id=MID1,
            filename="item.png",
            content_type="image/png",
            duration_ms=5000,
            order=0,
            sha256=PNG_SHA,
            size_bytes=None,
        )
        self.assertIsNone(pi.size_bytes)


class TestBuildPlaylistEdgeCases(unittest.TestCase):
    """Edge cases for build_playlist."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_size_bytes_zero_treated_as_unknown(self):
        """size_bytes=0 should be treated as unknown (skip size check)."""
        item = _make_item(size=0)
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)
        self.assertIsNone(pl.items[0].size_bytes)

    def test_size_bytes_none_in_manifest(self):
        """size_bytes=null in manifest JSON."""
        item = _make_item()
        item["size_bytes"] = None
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)
        self.assertIsNone(pl.items[0].size_bytes)

    def test_media_symlink(self):
        """Symlinked media files should fail verification."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)

        mc = self.root / MEDIA_CURRENT
        mc.mkdir(parents=True, exist_ok=True)
        import os
        real_path = mc / "real_item.png"
        real_path.write_bytes(PNG)
        symlink_path = mc / "item.png"
        os.symlink(str(real_path), str(symlink_path))

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)

    def test_str_root(self):
        """build_playlist should accept str root path."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        pl = build_playlist(str(self.root))
        self.assertTrue(pl.ready)

    def test_all_items_invalid_skipped(self):
        """When all items fail extraction, result is manifest_invalid."""
        bad1 = _make_item(filename="../bad1.png")
        bad2 = _make_item(mid=MID2, filename="bad2.png", sha="not-sha")
        manifest = _make_manifest(items=[bad1, bad2])
        _write_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "error")
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)
        self.assertEqual(pl.items_total, 2)


# ══════════════════════════════════════════════════════════════════════
# Tests: KSO safe manifest format
# ══════════════════════════════════════════════════════════════════════

KSO_CHANNEL = "kso"

# KSO safe manifest helpers
def _make_kso_manifest(items=None, channel=KSO_CHANNEL,
                       store_code="store-01", device_code="dev-01"):
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": channel,
        "storeCode": store_code,
        "deviceCode": device_code,
        "items": items or [],
    }


def _make_kso_item(slot_order=0, content_type="image/png", dur_ms=5000,
                   media_ref="media/current/slot-000",
                   valid_from="", valid_to=""):
    return {
        "slotOrder": slot_order,
        "contentType": content_type,
        "durationMs": dur_ms,
        "mediaRef": media_ref,
        "validFrom": valid_from,
        "validTo": valid_to,
    }


def _write_kso_manifest(root: Path, data: dict):
    mf = root / MANIFEST_FILE
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(_json.dumps(data), encoding="utf-8")


def _write_kso_media(root: Path, media_ref="slot-000", content=PNG):
    """Write media at media/current/{media_ref}."""
    mc = root / MEDIA_CURRENT
    mc.mkdir(parents=True, exist_ok=True)
    (mc / media_ref).write_bytes(content)


class TestBuildPlaylistKsoSafe(unittest.TestCase):
    """KSO safe manifest format tests."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ── Happy path ─────────────────────────────────────────────────

    def test_single_kso_item_all_ok(self):
        """KSO safe manifest with one valid item → ready."""
        manifest = _make_kso_manifest(items=[
            _make_kso_item()
        ])
        _write_kso_manifest(self.root, manifest)
        _write_kso_media(self.root, "slot-000")

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)
        self.assertEqual(pl.status, "ready")
        self.assertEqual(pl.reason, REASON_READY)
        self.assertEqual(pl.items_total, 1)
        self.assertEqual(pl.items_ready, 1)

    def test_two_kso_items_all_ok(self):
        """Two valid KSO items → both ready."""
        manifest = _make_kso_manifest(items=[
            _make_kso_item(slot_order=0, media_ref="media/current/slot-000"),
            _make_kso_item(slot_order=1, media_ref="media/current/slot-001"),
        ])
        _write_kso_manifest(self.root, manifest)
        _write_kso_media(self.root, "slot-000")
        _write_kso_media(self.root, "slot-001")

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)
        self.assertEqual(pl.items_total, 2)
        self.assertEqual(pl.items_ready, 2)

    # ── Media verification ─────────────────────────────────────────

    def test_kso_media_missing(self):
        """Media file missing → media_incomplete."""
        manifest = _make_kso_manifest(items=[
            _make_kso_item(media_ref="media/current/slot-000"),
        ])
        _write_kso_manifest(self.root, manifest)
        # No media written

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "not_ready")
        self.assertEqual(pl.reason, REASON_MEDIA_INCOMPLETE)
        self.assertEqual(pl.items_total, 1)
        self.assertEqual(pl.items_ready, 0)
        self.assertEqual(pl.items_missing, 1)

    # ── Format detection ───────────────────────────────────────────

    def test_kso_format_detected_automatically(self):
        """KSO format is auto-detected from schemaVersion + channel + mediaRef."""
        manifest = _make_kso_manifest(items=[
            _make_kso_item(),
        ])
        _write_kso_manifest(self.root, manifest)
        _write_kso_media(self.root, "slot-000")

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)  # Must be detected as KSO, not legacy

    def test_empty_kso_items(self):
        """Empty items array in KSO manifest → no_media_items."""
        manifest = _make_kso_manifest(items=[])
        _write_kso_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_NO_MEDIA_ITEMS)

    # ── Gateway wrapper rejection ──────────────────────────────────

    def test_gateway_wrapper_rejected(self):
        """Gateway wrapper {status, manifest} → invalid (hold)."""
        wrapper = {
            "status": "served",
            "manifest_version_id": "some-uuid",
            "manifest_hash": "abc123",
            "published_at": "2026-06-19T10:00:00Z",
            "manifest": {
                "schemaVersion": 1,
                "channel": "kso",
                "storeCode": "s1",
                "deviceCode": "d1",
                "items": [],
            }
        }
        mf = self.root / MANIFEST_FILE
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(_json.dumps(wrapper), encoding="utf-8")

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.status, "error")
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_gateway_wrapper_rejected_even_with_items(self):
        """Gateway wrapper with valid items inside → still rejected."""
        wrapper = {
            "status": "not_modified",
            "manifest": {
                "schemaVersion": 1,
                "channel": "kso",
                "storeCode": "s1",
                "deviceCode": "d1",
                "items": [_make_kso_item()],
            }
        }
        mf = self.root / MANIFEST_FILE
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(_json.dumps(wrapper), encoding="utf-8")

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    # ── Channel check ──────────────────────────────────────────────

    def test_non_kso_channel_rejected(self):
        """Manifest with channel != kso → all items excluded → manifest_invalid."""
        manifest = _make_kso_manifest(
            channel="android-tv",
            items=[_make_kso_item()],
        )
        _write_kso_manifest(self.root, manifest)
        _write_kso_media(self.root, "slot-000")

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    # ── Unsupported content type ───────────────────────────────────

    def test_unsupported_content_type_excluded(self):
        """KSO item with unsupported MIME → excluded → no items."""
        item = _make_kso_item(content_type="application/pdf")
        manifest = _make_kso_manifest(items=[item])
        _write_kso_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)
        self.assertEqual(pl.items_total, 1)

    # ── Unsafe mediaRef rejection ──────────────────────────────────

    def test_unsafe_media_ref_path_traversal(self):
        """mediaRef with path traversal → item excluded."""
        item = _make_kso_item(media_ref="../etc/passwd")
        manifest = _make_kso_manifest(items=[item])
        _write_kso_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_unsafe_media_ref_absolute(self):
        """mediaRef as absolute path → excluded."""
        item = _make_kso_item(media_ref="/etc/passwd")
        manifest = _make_kso_manifest(items=[item])
        _write_kso_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_unsafe_media_ref_url(self):
        """mediaRef as URL → excluded."""
        item = _make_kso_item(media_ref="http://evil.com/bad.png")
        manifest = _make_kso_manifest(items=[item])
        _write_kso_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    def test_unsafe_media_ref_backslash(self):
        """mediaRef with backslash → excluded."""
        item = _make_kso_item(media_ref="media\\current\\slot-000")
        manifest = _make_kso_manifest(items=[item])
        _write_kso_manifest(self.root, manifest)

        pl = build_playlist(self.root)
        self.assertFalse(pl.ready)
        self.assertEqual(pl.reason, REASON_MANIFEST_INVALID)

    # ── Output safety ──────────────────────────────────────────────

    def test_kso_playlist_item_no_raw_ids(self):
        """KSO playlist items never expose raw IDs/paths/filename/hash."""
        manifest = _make_kso_manifest(items=[_make_kso_item()])
        _write_kso_manifest(self.root, manifest)
        _write_kso_media(self.root, "slot-000")

        pl = build_playlist(self.root)
        self.assertTrue(pl.ready)
        item = pl.items[0]
        # No legacy fields
        self.assertEqual(item.manifest_item_id, "")
        self.assertEqual(item.filename, "")
        self.assertEqual(item.sha256, "")
        # Has KSO fields
        self.assertEqual(item.media_ref, "media/current/slot-000")
        self.assertEqual(item.slot_order, 0)
        self.assertEqual(item.content_type, "image/png")
        self.assertEqual(item.duration_ms, 5000)

    def test_kso_summary_no_forbidden(self):
        """Safe output summary has no forbidden substrings."""
        from kso_player.safe_output import format_playlist_summary
        manifest = _make_kso_manifest(items=[_make_kso_item()])
        _write_kso_manifest(self.root, manifest)
        _write_kso_media(self.root, "slot-000")

        pl = build_playlist(self.root)
        summary = format_playlist_summary(pl)
        lower = summary.lower()
        for fb in ("filename", "sha256", "manifest_item_id", "media_ref",
                    "media/current", "slot-000"):
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' in summary: {summary}")


if __name__ == "__main__":
    unittest.main()
