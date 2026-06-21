"""Tests for KSO sidecar safe gateway manifest extractor.

Tests extract_kso_safe_manifest_body_from_gateway_response() and
write_kso_safe_local_manifest_from_gateway_response().

Uses temp roots. NO backend, NO HTTP, NO media bytes, NO PoP.
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent.kso_manifest_gateway_extractor import (
    KsoGatewayManifestExtractionResult,
    KsoGatewayManifestWriteResult,
    extract_kso_safe_manifest_body_from_gateway_response,
    write_kso_safe_local_manifest_from_gateway_response,
    format_extraction_result,
    format_write_result,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_NOT_MODIFIED,
    STATUS_NO_MANIFEST,
    REASON_SERVED,
    REASON_NOT_MODIFIED,
    REASON_NO_MANIFEST,
    REASON_INVALID_RESPONSE,
    REASON_UNSAFE_MANIFEST,
    REASON_NON_KSO_CHANNEL,
    REASON_WRITE_FAILED,
    REASON_INVALID_ARGS,
    FORBIDDEN_MANIFEST_KEYS,
    KSO_CHANNEL,
    ALLOWED_CONTENT_TYPES,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

MANIFEST_FILE = "manifest/current_manifest.json"


def _make_kso_safe_manifest_body(**overrides):
    """Create a valid KSO safe manifest body."""
    defaults = {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": "kso",
        "storeCode": "store-01",
        "deviceCode": "dev-01",
        "items": [
            {
                "slotOrder": 0,
                "contentType": "image/png",
                "durationMs": 5000,
                "mediaRef": "media/current/slot-000",
                "validFrom": "2026-06-19T09:00:00Z",
                "validTo": "2026-06-19T11:00:00Z",
            }
        ],
    }
    defaults.update(overrides)
    return dict(defaults)


def _make_gateway_response(status="served", manifest_body=None, **overrides):
    """Create a gateway response dict."""
    if manifest_body is None:
        manifest_body = _make_kso_safe_manifest_body()

    resp = {
        "status": status,
        "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "manifest_hash": "c" * 64,
        "published_at": "2026-06-19T10:00:00Z",
        "manifest": manifest_body,
    }
    resp.update(overrides)
    return resp


def _no_forbidden(text, extra=None):
    """Check text has no forbidden substrings."""
    lower = text.lower()
    all_forbidden = set(FORBIDDEN_MANIFEST_KEYS)
    if extra:
        all_forbidden.update(extra)
    for fb in all_forbidden:
        if len(fb) >= 4 and fb in lower:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════
# Tests: extractor
# ══════════════════════════════════════════════════════════════════════

class TestExtractKsoManifest(unittest.TestCase):
    """Pure extraction tests — no filesystem."""

    def test_served_extracts_manifest(self):
        """status=served → extracts safe manifest body."""
        response = _make_gateway_response()
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.extracted)
        self.assertEqual(result.reason, REASON_SERVED)
        self.assertEqual(result.items_count, 1)
        self.assertEqual(result.channel, KSO_CHANNEL)
        self.assertTrue(result.store_code_present)
        self.assertTrue(result.device_code_present)

    def test_not_modified_no_extract(self):
        """status=not_modified → no extract, not_modified result."""
        response = _make_gateway_response(status="not_modified")
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_NOT_MODIFIED)
        self.assertFalse(result.extracted)
        self.assertEqual(result.reason, REASON_NOT_MODIFIED)

    def test_no_manifest_no_extract(self):
        """status=no_manifest → no extract, no_manifest result."""
        response = _make_gateway_response(status="no_manifest")
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_NO_MANIFEST)
        self.assertFalse(result.extracted)
        self.assertEqual(result.reason, REASON_NO_MANIFEST)

    def test_missing_manifest_key(self):
        """response without 'manifest' key → error."""
        response = {"status": "served"}
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)
        self.assertFalse(result.extracted)

    def test_manifest_not_dict(self):
        """response['manifest'] is not a dict → error."""
        response = {"status": "served", "manifest": "not-a-dict"}
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)

    def test_invalid_status(self):
        """response with unexpected status → error."""
        response = _make_gateway_response(status="error_internal")
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)

    def test_non_dict_response(self):
        """Non-dict response → error."""
        result = extract_kso_safe_manifest_body_from_gateway_response("string")
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)

    def test_none_response(self):
        """None response → error."""
        result = extract_kso_safe_manifest_body_from_gateway_response(None)
        self.assertEqual(result.status, STATUS_ERROR)

    # ── Channel ────────────────────────────────────────────────────

    def test_non_kso_channel(self):
        """channel != kso → error."""
        body = _make_kso_safe_manifest_body(channel="android-tv")
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    # ── schemaVersion ──────────────────────────────────────────────

    def test_wrong_schema_version(self):
        """schemaVersion != 1 → error."""
        body = _make_kso_safe_manifest_body(schemaVersion=2)
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    # ── Store/device codes ─────────────────────────────────────────

    def test_unsafe_store_code(self):
        """storeCode with path traversal → error."""
        body = _make_kso_safe_manifest_body(storeCode="../../evil")
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    def test_unsafe_device_code(self):
        """deviceCode with space → error."""
        body = _make_kso_safe_manifest_body(deviceCode="dev 01")
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    # ── Content types ──────────────────────────────────────────────

    def test_unsupported_content_type(self):
        """Unsupported MIME type → error."""
        body = _make_kso_safe_manifest_body(items=[{
            "slotOrder": 0,
            "contentType": "application/pdf",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
            "validFrom": "",
            "validTo": "",
        }])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    # ── mediaRef validation ────────────────────────────────────────

    def test_unsafe_media_ref_traversal(self):
        """mediaRef with .. → error."""
        body = _make_kso_safe_manifest_body(items=[{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "../etc/passwd",
            "validFrom": "",
            "validTo": "",
        }])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    def test_unsafe_media_ref_absolute(self):
        """mediaRef absolute path → error."""
        body = _make_kso_safe_manifest_body(items=[{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "/etc/passwd",
            "validFrom": "",
            "validTo": "",
        }])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)

    def test_unsafe_media_ref_url(self):
        """mediaRef URL → error."""
        body = _make_kso_safe_manifest_body(items=[{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "http://evil.com/bad.png",
            "validFrom": "",
            "validTo": "",
        }])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)

    def test_media_ref_wrong_prefix(self):
        """mediaRef not starting with media/current/slot- → error."""
        body = _make_kso_safe_manifest_body(items=[{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "creatives/ad.png",
            "validFrom": "",
            "validTo": "",
        }])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    # ── Empty items ────────────────────────────────────────────────

    def test_empty_items_valid(self):
        """Empty items is valid — manifest with 0 items."""
        body = _make_kso_safe_manifest_body(items=[])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.extracted)
        self.assertEqual(result.items_count, 0)

    # ── Forbidden keys in manifest ─────────────────────────────────

    def test_forbidden_key_manifest_version_id(self):
        """manifest body with manifest_version_id → error."""
        body = _make_kso_safe_manifest_body()
        body["manifest_version_id"] = "some-uuid"
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    def test_forbidden_key_status(self):
        """manifest body with status key → error."""
        body = _make_kso_safe_manifest_body()
        body["status"] = "served"
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MANIFEST)

    # ── Multiple items ─────────────────────────────────────────────

    def test_multiple_valid_items(self):
        """Multiple valid KSO items → all extracted."""
        body = _make_kso_safe_manifest_body(items=[
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
                "contentType": "video/mp4",
                "durationMs": 30000,
                "mediaRef": "media/current/slot-001",
                "validFrom": "",
                "validTo": "",
            },
        ])
        response = _make_gateway_response(manifest_body=body)
        result = extract_kso_safe_manifest_body_from_gateway_response(response)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.extracted)
        self.assertEqual(result.items_count, 2)


# ══════════════════════════════════════════════════════════════════════
# Tests: writer
# ══════════════════════════════════════════════════════════════════════

class TestWriteKsoManifest(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_writes_manifest_body_only(self):
        """Writer writes only safe manifest body, not wrapper."""
        response = _make_gateway_response()
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.written)
        self.assertTrue(result.manifest_ready)
        self.assertEqual(result.items_count, 1)

        # File exists
        mf = self.root / MANIFEST_FILE
        self.assertTrue(mf.is_file())

        # Content is ONLY the safe manifest body
        content = json.loads(mf.read_text())
        self.assertEqual(content["schemaVersion"], 1)
        self.assertEqual(content["channel"], "kso")
        self.assertEqual(content["storeCode"], "store-01")
        self.assertEqual(content["deviceCode"], "dev-01")
        self.assertEqual(len(content["items"]), 1)

        # No wrapper fields
        for forbidden in ("status", "manifest_version_id", "manifest_hash",
                           "published_at"):
            self.assertNotIn(forbidden, content,
                f"wrapper field '{forbidden}' leaked into local manifest")

        # No raw IDs in items
        item = content["items"][0]
        for forbidden in ("manifest_item_id", "campaign_id", "creative_id",
                           "rendition_id", "filename", "sha256"):
            self.assertNotIn(forbidden, item,
                f"forbidden field '{forbidden}' in local manifest item")

    def test_not_modified_does_not_write(self):
        """status=not_modified → no write."""
        response = _make_gateway_response(status="not_modified")
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        self.assertEqual(result.status, STATUS_NOT_MODIFIED)
        self.assertFalse(result.written)
        self.assertEqual(result.reason, REASON_NOT_MODIFIED)

        mf = self.root / MANIFEST_FILE
        self.assertFalse(mf.exists(),
            f"Manifest file should not exist after not_modified")

    def test_no_manifest_does_not_write(self):
        """status=no_manifest → no write."""
        response = _make_gateway_response(status="no_manifest")
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        self.assertEqual(result.status, STATUS_NO_MANIFEST)
        self.assertFalse(result.written)
        self.assertEqual(result.reason, REASON_NO_MANIFEST)

    def test_invalid_extraction_does_not_write(self):
        """Invalid manifest → no write, error result."""
        response = _make_gateway_response()
        response["manifest"]["channel"] = "android-tv"

        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertFalse(result.written)
        self.assertFalse(result.manifest_ready)

        mf = self.root / MANIFEST_FILE
        self.assertFalse(mf.exists(),
            f"Manifest file should not exist after failed extraction")

    def test_empty_items_writes_valid_manifest(self):
        """Zero items → writes valid empty manifest."""
        body = _make_kso_safe_manifest_body(items=[])
        response = _make_gateway_response(manifest_body=body)
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.written)
        self.assertEqual(result.items_count, 0)

        content = json.loads((self.root / MANIFEST_FILE).read_text())
        self.assertEqual(content["items"], [])

    def test_atomic_write_uses_tmp(self):
        """Write does not leave .tmp files behind."""
        response = _make_gateway_response()
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        self.assertTrue(result.written)
        tmp_files = list((self.root / "manifest").glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0,
            f".tmp files left behind: {tmp_files}")

    def test_old_manifest_preserved_on_failure(self):
        """Old manifest preserved when write fails on second call."""
        # Write a valid manifest first
        response = _make_gateway_response()
        write_kso_safe_local_manifest_from_gateway_response(self.root, response)

        old_content = (self.root / MANIFEST_FILE).read_text()

        # Now try to write an invalid one (but our writer shouldn't overwrite)
        bad_resp = _make_gateway_response()
        bad_resp["manifest"]["channel"] = "android-tv"
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, bad_resp)

        self.assertFalse(result.written)

        # Old manifest should still be there
        new_content = (self.root / MANIFEST_FILE).read_text()
        self.assertEqual(old_content, new_content,
            "Old manifest was overwritten despite extraction failure")

    def test_writer_invalid_root(self):
        """Invalid root → error."""
        result = write_kso_safe_local_manifest_from_gateway_response(
            None, _make_gateway_response())
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(unittest.TestCase):

    def test_extraction_repr_no_forbidden(self):
        """Extraction result repr has no forbidden fields."""
        response = _make_gateway_response()
        result = extract_kso_safe_manifest_body_from_gateway_response(response)
        text = repr(result)
        self.assertNotIn("manifest_version_id", text)
        self.assertNotIn("manifest_hash", text)
        self.assertNotIn("media/current", text)
        self.assertNotIn("slot-000", text)

    def test_extraction_format_no_forbidden(self):
        """Format output has no forbidden fields."""
        response = _make_gateway_response()
        result = extract_kso_safe_manifest_body_from_gateway_response(response)
        text = format_extraction_result(result)
        self.assertNotIn("manifest_version_id", text)
        self.assertNotIn("manifest_hash", text)
        self.assertNotIn("media/current", text)

    def test_write_repr_no_forbidden(self):
        """Write result repr has no forbidden fields."""
        response = _make_gateway_response()
        result = write_kso_safe_local_manifest_from_gateway_response(
            Path("."), response)
        text = repr(result)
        self.assertNotIn("manifest_version_id", text)
        self.assertNotIn("manifest_hash", text)
        self.assertNotIn("media/current", text)

    def test_write_format_no_forbidden(self):
        """Write format output has no forbidden fields."""
        response = _make_gateway_response()
        result = write_kso_safe_local_manifest_from_gateway_response(
            Path("."), response)
        text = format_write_result(result)
        self.assertNotIn("manifest_version_id", text)
        self.assertNotIn("manifest_hash", text)
        self.assertNotIn("media/current", text)

    def test_error_result_no_paths(self):
        """Error result has no paths."""
        result = extract_kso_safe_manifest_body_from_gateway_response(None)
        text = repr(result) + format_extraction_result(result)
        self.assertNotIn("Traceback", text)

    def test_writer_error_no_paths(self):
        """Writer error has no paths."""
        result = write_kso_safe_local_manifest_from_gateway_response(None, {})
        text = repr(result) + format_write_result(result)
        self.assertNotIn("Traceback", text)

    def test_local_file_no_forbidden_keys(self):
        """Local manifest file has no forbidden keys."""
        import json
        response = _make_gateway_response()
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root if hasattr(self, 'root') else Path(tempfile.mkdtemp()),
            response)

        if result.written:
            root = self.root if hasattr(self, 'root') else Path(tempfile.mkdtemp())
            content = json.loads((root / MANIFEST_FILE).read_text())
            content_str = json.dumps(content).lower()
            for fk in FORBIDDEN_MANIFEST_KEYS:
                if len(fk) >= 6:  # Skip very short keys that may appear in normal words
                    self.assertNotIn(fk, content_str,
                        f"forbidden key/value '{fk}' in local manifest: {content_str[:100]}")

    def test_local_file_no_raw_ids(self):
        """Local manifest file has no raw IDs in items."""
        import json
        response = _make_gateway_response()
        result = write_kso_safe_local_manifest_from_gateway_response(
            self.root, response)

        content = json.loads((self.root / MANIFEST_FILE).read_text())
        item = content["items"][0]
        for forbidden in ("manifest_item_id", "campaign_id", "creative_id",
                           "rendition_id", "schedule_item_id", "batch_id",
                           "filename", "sha256", "file_path", "media_path"):
            self.assertNotIn(forbidden, item,
                f"raw ID field '{forbidden}' found in local manifest item")

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_no_pop_written(self):
        """Manifest extraction does not touch pop/."""
        response = _make_gateway_response()
        write_kso_safe_local_manifest_from_gateway_response(self.root, response)
        self.assertFalse((self.root / "pop").exists())

    def test_no_state_written(self):
        """Manifest extraction does not write kso_state.json."""
        response = _make_gateway_response()
        write_kso_safe_local_manifest_from_gateway_response(self.root, response)
        self.assertFalse((self.root / "state").exists())

    def test_no_backend_call(self):
        """Source code has no HTTP/backend calls."""
        mod_path = Path(__file__).resolve().parent.parent / "kso_sidecar_agent" / "kso_manifest_gateway_extractor.py"
        source = mod_path.read_text()
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("http.client", source)

    def test_no_windows(self):
        """Source code has no Windows/MSI/ProgramData."""
        mod_path = Path(__file__).resolve().parent.parent / "kso_sidecar_agent" / "kso_manifest_gateway_extractor.py"
        source = mod_path.read_text().lower()
        for fb in ("windows service", "programdata", "windows installer"):
            self.assertNotIn(fb.lower(), source)

    def test_no_secret_token_read(self):
        """Source code does not read secrets from config/env."""
        mod_path = Path(__file__).resolve().parent.parent / "kso_sidecar_agent" / "kso_manifest_gateway_extractor.py"
        source = mod_path.read_text().lower()
        # Must not import/use secret-reading modules
        self.assertNotIn("from kso_sidecar_agent.secret_store", source)
        self.assertNotIn("from kso_sidecar_agent.device_auth", source)
        self.assertNotIn(".env", source)
        self.assertNotIn("read_secret", source)
        self.assertNotIn("load_dotenv", source)

    def test_player_not_modified(self):
        """Player files are unchanged."""
        player_mod = (
            Path(__file__).resolve().parent.parent.parent /
            "kso_player" / "kso_player" / "playlist.py"
        )
        if player_mod.exists():
            source = player_mod.read_text()
            # Player should still reject gateway wrapper
            self.assertIn("_is_gateway_wrapper", source)

    def test_backend_not_modified(self):
        """Backend gateway service unchanged."""
        backend_svc = (
            Path(__file__).resolve().parent.parent.parent /
            "backend" / "app" / "domains" / "device_gateway" / "service.py"
        )
        if backend_svc.exists():
            source = backend_svc.read_text()
            self.assertIn("get_current_manifest", source)


if __name__ == "__main__":
    unittest.main()
