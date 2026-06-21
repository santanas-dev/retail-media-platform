"""Tests for KSO sidecar manifest + media sync core.

Tests sync_kso_manifest_and_media() with fake gateway client.
No HTTP, no backend, no secrets, no PoP.
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    KsoManifestMediaSyncResult,
    KsoGatewayClient,
    sync_kso_manifest_and_media,
    format_kso_manifest_media_sync_result,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_NOT_MODIFIED,
    STATUS_NO_MANIFEST,
    REASON_SYNCED,
    REASON_NOT_MODIFIED,
    REASON_NO_MANIFEST,
    REASON_CONTENT_TYPE_MISMATCH,
    REASON_MEDIA_TOO_LARGE,
    REASON_MEDIA_WRITE_FAILED,
    REASON_MANIFEST_WRITE_FAILED,
    REASON_MEDIA_DOWNLOAD_FAILED,
    REASON_INVALID_ARGS,
    MAX_MEDIA_SIZE_BYTES,
)

# ══════════════════════════════════════════════════════════════════════
# Fake gateway client
# ══════════════════════════════════════════════════════════════════════

MANIFEST_FILE = "manifest/current_manifest.json"
MEDIA_CURRENT = "media/current"

PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # 108 bytes
JPEG_BODY = b"\xff\xd8\xff\xe0" + b"\x01" * 200  # 204 bytes
MP4_BODY = b"\x00\x00\x00\x18ftypmp42" + b"\x02" * 500


class FakeKsoGatewayClient:
    """Fake gateway client for tests.

    Returns pre-configured responses. No HTTP.
    """

    def __init__(self, manifest_response=None, media_map=None,
                 fail_fetch=False, fail_download=False):
        self.manifest_response = manifest_response
        self.media_map = media_map or {}
        self.fail_fetch = fail_fetch
        self.fail_download = fail_download

    def fetch_current_manifest(self):
        if self.fail_fetch:
            raise RuntimeError("simulated fetch failure")
        return self.manifest_response

    def download_kso_media(self, media_ref):
        if self.fail_download:
            raise RuntimeError("simulated download failure")
        resp = self.media_map.get(media_ref)
        if resp is None:
            return KsoMediaDownloadResponse(
                status=STATUS_ERROR,
                content_type="",
                content_length=0,
                body=b"",
            )
        return resp


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_served_response(items=None):
    """Create a valid gateway response with KSO safe manifest."""
    if items is None:
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
            "validFrom": "",
            "validTo": "",
        }]
    manifest = {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": "kso",
        "storeCode": "store-01",
        "deviceCode": "dev-01",
        "items": items,
    }
    return {
        "status": "served",
        "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "manifest_hash": "c" * 64,
        "published_at": "2026-06-19T10:00:00Z",
        "manifest": manifest,
    }


def _make_media_dl(content_type="image/png", body=PNG_BODY, status=STATUS_OK):
    return KsoMediaDownloadResponse(
        status=status,
        content_type=content_type,
        content_length=len(body),
        body=body,
    )


# ══════════════════════════════════════════════════════════════════════
# Tests: happy path
# ══════════════════════════════════════════════════════════════════════

class TestSyncHappyPath(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_served_one_image_syncs(self):
        """One image item → downloads media, writes media, writes manifest."""
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.manifest_written)
        self.assertEqual(result.media_downloaded_count, 1)
        self.assertEqual(result.media_written_count, 1)
        self.assertEqual(result.items_count, 1)
        self.assertEqual(result.reason, REASON_SYNCED)

        # Manifest written
        mf = self.root / MANIFEST_FILE
        self.assertTrue(mf.is_file())

        # Media written
        slot = self.root / MEDIA_CURRENT / "slot-000"
        self.assertTrue(slot.is_file())
        self.assertEqual(slot.read_bytes(), PNG_BODY)

        # Manifest contains ONLY safe body
        manifest = json.loads(mf.read_text())
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertNotIn("manifest_version_id", manifest)
        self.assertNotIn("manifest_hash", manifest)
        self.assertNotIn("status", manifest)

    def test_served_video_syncs(self):
        """Video item syncs correctly."""
        resp = _make_served_response(items=[{
            "slotOrder": 0,
            "contentType": "video/mp4",
            "durationMs": 30000,
            "mediaRef": "media/current/slot-000",
            "validFrom": "",
            "validTo": "",
        }])
        media_map = {"media/current/slot-000": _make_media_dl("video/mp4", MP4_BODY)}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.manifest_written)
        self.assertEqual(result.media_downloaded_count, 1)

        slot = self.root / MEDIA_CURRENT / "slot-000"
        self.assertEqual(slot.read_bytes(), MP4_BODY)

    def test_served_two_items_syncs_both(self):
        """Two items → both media downloaded and written."""
        resp = _make_served_response(items=[
            {
                "slotOrder": 0,
                "contentType": "image/png",
                "durationMs": 5000,
                "mediaRef": "media/current/slot-000",
                "validFrom": "",
                "validTo": "",
            },
            {
                "slotOrder": 1,
                "contentType": "image/jpeg",
                "durationMs": 3000,
                "mediaRef": "media/current/slot-001",
                "validFrom": "",
                "validTo": "",
            },
        ])
        media_map = {
            "media/current/slot-000": _make_media_dl("image/png", PNG_BODY),
            "media/current/slot-001": _make_media_dl("image/jpeg", JPEG_BODY),
        }
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.media_downloaded_count, 2)
        self.assertEqual(result.media_written_count, 2)
        self.assertTrue((self.root / MEDIA_CURRENT / "slot-000").is_file())
        self.assertTrue((self.root / MEDIA_CURRENT / "slot-001").is_file())

    def test_empty_items_writes_manifest_only(self):
        """Empty items → writes manifest, skips media."""
        resp = _make_served_response(items=[])
        client = FakeKsoGatewayClient(manifest_response=resp)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.manifest_written)
        self.assertEqual(result.media_downloaded_count, 0)
        self.assertEqual(result.media_written_count, 0)
        self.assertEqual(result.items_count, 0)

        mf = self.root / MANIFEST_FILE
        self.assertTrue(mf.is_file())

    def test_media_written_before_manifest(self):
        """Verify: media files exist before manifest is written.

        We detect this indirectly: if a media write failure prevents
        manifest from being written (tested in another test).
        But for success: both should exist.
        """
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)
        self.assertTrue(result.manifest_written)
        self.assertEqual(result.media_written_count, 1)
        # Both files exist
        self.assertTrue((self.root / MEDIA_CURRENT / "slot-000").is_file())
        self.assertTrue((self.root / MANIFEST_FILE).is_file())


# ══════════════════════════════════════════════════════════════════════
# Tests: not_modified / no_manifest
# ══════════════════════════════════════════════════════════════════════

class TestSyncNoOp(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_not_modified_no_write(self):
        resp = {
            "status": "not_modified",
            "manifest_version_id": "uuid",
            "manifest_hash": "hhh",
        }
        client = FakeKsoGatewayClient(manifest_response=resp)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_NOT_MODIFIED)
        self.assertEqual(result.reason, REASON_NOT_MODIFIED)
        self.assertFalse(result.manifest_written)
        self.assertFalse((self.root / MANIFEST_FILE).exists())

    def test_no_manifest_no_write(self):
        resp = {"status": "no_manifest"}
        client = FakeKsoGatewayClient(manifest_response=resp)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_NO_MANIFEST)
        self.assertEqual(result.reason, REASON_NO_MANIFEST)
        self.assertFalse((self.root / MANIFEST_FILE).exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: errors
# ══════════════════════════════════════════════════════════════════════

class TestSyncErrors(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_fetch_failure(self):
        client = FakeKsoGatewayClient(fail_fetch=True)
        result = sync_kso_manifest_and_media(self.root, client)
        self.assertEqual(result.status, STATUS_ERROR)

    def test_invalid_gateway_response(self):
        resp = {"status": "invalid_status"}
        client = FakeKsoGatewayClient(manifest_response=resp)
        result = sync_kso_manifest_and_media(self.root, client)
        self.assertEqual(result.status, STATUS_ERROR)

    def test_media_download_failure_manifest_not_written(self):
        """Media download fails → manifest NOT written, old state preserved."""
        # First write an old manifest
        old_mf = self.root / MANIFEST_FILE
        old_mf.parent.mkdir(parents=True, exist_ok=True)
        old_mf.write_text('{"old": true}')

        resp = _make_served_response()
        media_map = {
            "media/current/slot-000": KsoMediaDownloadResponse(
                status=STATUS_ERROR, body=b"")
        }
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertFalse(result.manifest_written)

        # Old manifest preserved
        self.assertEqual(old_mf.read_text(), '{"old": true}')

    def test_content_type_mismatch_manifest_not_written(self):
        """Content-Type mismatch → manifest not written."""
        resp = _make_served_response()  # expects image/png
        media_map = {
            "media/current/slot-000": _make_media_dl("video/mp4", MP4_BODY)
        }
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_CONTENT_TYPE_MISMATCH)
        self.assertFalse(result.manifest_written)
        self.assertFalse((self.root / MANIFEST_FILE).exists())

    def test_oversized_media_rejected(self):
        """Media over MAX_MEDIA_SIZE_BYTES → rejected."""
        resp = _make_served_response()
        huge = KsoMediaDownloadResponse(
            status=STATUS_OK,
            content_type="image/png",
            content_length=MAX_MEDIA_SIZE_BYTES + 1,
            body=b"x" * 100,
        )
        media_map = {"media/current/slot-000": huge}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_MEDIA_TOO_LARGE)
        self.assertFalse(result.manifest_written)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_OUTPUT = {
    "media/current/slot", "manifest_version_id", "manifest_hash",
    "rendition_id", "creative_id", "campaign_id",
    "schedule_item_id", "batch_id",
    "file_path", "media_path", "creatives/",
    "minio", "sha256", "storage_key",
    "token", "secret", "backend_base_url",
    "Traceback",
}


class TestOutputSafety(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_repr_no_forbidden(self):
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)
        text = repr(result)
        lower = text.lower()
        for fb in FORBIDDEN_OUTPUT:
            self.assertNotIn(fb.lower(), lower,
                f"forbidden '{fb}' in repr: {text[:150]}")

    def test_format_no_forbidden(self):
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        result = sync_kso_manifest_and_media(self.root, client)
        text = format_kso_manifest_media_sync_result(result)
        lower = text.lower()
        for fb in FORBIDDEN_OUTPUT:
            self.assertNotIn(fb.lower(), lower,
                f"forbidden '{fb}' in format: {text[:150]}")

    def test_error_no_stacktrace(self):
        client = FakeKsoGatewayClient(fail_fetch=True)
        result = sync_kso_manifest_and_media(self.root, client)
        text = repr(result) + format_kso_manifest_media_sync_result(result)
        self.assertNotIn("Traceback", text)

    def test_local_manifest_safe(self):
        """Written manifest has no wrapper fields."""
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        sync_kso_manifest_and_media(self.root, client)

        mf = self.root / MANIFEST_FILE
        content = json.loads(mf.read_text())
        # No wrapper fields
        for wrapper_key in ("status", "manifest_version_id", "manifest_hash",
                            "published_at", "manifest"):
            self.assertNotIn(wrapper_key, content)

        # Item has no raw IDs
        item = content["items"][0]
        for raw_id in ("manifest_item_id", "campaign_id", "creative_id",
                       "rendition_id", "filename", "sha256"):
            self.assertNotIn(raw_id, item)

    def test_media_dl_response_repr_safe(self):
        """KsoMediaDownloadResponse repr is safe."""
        dl = _make_media_dl()
        text = repr(dl)
        self.assertNotIn("PNG", text)
        self.assertNotIn("body", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_no_pop_written(self):
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)
        sync_kso_manifest_and_media(self.root, client)
        self.assertFalse((self.root / "pop").exists())

    def test_no_state_written(self):
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)
        sync_kso_manifest_and_media(self.root, client)
        self.assertFalse((self.root / "state").exists())

    def test_no_backend_in_source(self):
        mod_path = Path(__file__).resolve().parent.parent / "kso_sidecar_agent" / "kso_manifest_media_sync.py"
        source = mod_path.read_text()
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source)

    def test_no_windows(self):
        mod_path = Path(__file__).resolve().parent.parent / "kso_sidecar_agent" / "kso_manifest_media_sync.py"
        source = mod_path.read_text().lower()
        for fb in ("windows service", "programdata", "windows installer"):
            self.assertNotIn(fb, source)

    def test_player_not_modified(self):
        player_mod = (
            Path(__file__).resolve().parent.parent.parent /
            "kso_player" / "kso_player" / "playlist.py"
        )
        if player_mod.exists():
            source = player_mod.read_text()
            self.assertIn("_is_gateway_wrapper", source)

    def test_backend_not_modified(self):
        backend_svc = (
            Path(__file__).resolve().parent.parent.parent /
            "backend" / "app" / "domains" / "device_gateway" / "service.py"
        )
        if backend_svc.exists():
            source = backend_svc.read_text()
            self.assertIn("get_current_manifest", source)

    def test_invalid_args(self):
        result = sync_kso_manifest_and_media(None, FakeKsoGatewayClient())
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_none_client(self):
        result = sync_kso_manifest_and_media(self.root, None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_media_written_at_correct_path(self):
        """Media is written at media/current/slot-NNN, not staging/quarantine."""
        resp = _make_served_response()
        media_map = {"media/current/slot-000": _make_media_dl()}
        client = FakeKsoGatewayClient(manifest_response=resp, media_map=media_map)

        sync_kso_manifest_and_media(self.root, client)

        self.assertTrue((self.root / MEDIA_CURRENT / "slot-000").is_file())
        # No staging or quarantine dirs created
        self.assertFalse((self.root / "media" / "staging").exists())
        self.assertFalse((self.root / "media" / "quarantine").exists())


if __name__ == "__main__":
    unittest.main()
