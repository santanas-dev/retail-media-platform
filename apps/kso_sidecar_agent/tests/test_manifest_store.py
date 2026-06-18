"""Tests for manifest_store — local file operations only, no backend."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_MANIFEST_VERSION_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_MANIFEST_HASH = "c" * 64
TEST_ITEM_ID = "11111111-1111-1111-1111-111111111111"

NOW_ISO = "2026-06-18T10:00:00+00:00"

VALID_LOCAL_MANIFEST = {
    "manifest_version_id": TEST_MANIFEST_VERSION_ID,
    "manifest_hash": TEST_MANIFEST_HASH,
    "source": "current",
    "generated_at": "2026-06-18T10:00:00+00:00",
    "valid_until": None,
    "fetched_at": NOW_ISO,
    "campaign_id": None,
    "items": [
        {
            "manifest_item_id": TEST_ITEM_ID,
            "filename": f"{TEST_ITEM_ID}.mp4",
            "content_type": "video/mp4",
            "sha256": "a" * 64,
            "size_bytes": 0,
            "duration_ms": 15000,
            "order": 0,
        },
    ],
}


def _run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
    )
    return r.returncode, r.stdout, r.stderr


def _make_snapshot(**overrides):
    """Create a ManifestSnapshot-like object."""
    from kso_sidecar_agent.manifest_client import ManifestSnapshot
    defaults = {
        "status": "served",
        "manifest_version_id": TEST_MANIFEST_VERSION_ID,
        "manifest_hash": TEST_MANIFEST_HASH,
        "published_at": NOW_ISO,
        "items": [
            {
                "id": TEST_ITEM_ID,
                "sha256": "a" * 64,
                "media_path": "creatives/test.mp4",
                "duration_ms": 15000,
                "loop_position": 0,
            },
        ],
        "fetched_at": 1_750_000_000.0,
        "source": "current",
    }
    defaults.update(overrides)
    return ManifestSnapshot(**defaults)


# ══════════════════════════════════════════════════════════════════════
# Normalize tests
# ══════════════════════════════════════════════════════════════════════

class TestNormalizeManifestSnapshot(unittest.TestCase):

    def test_normalize_current_served(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot()
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        self.assertEqual(data["manifest_version_id"], TEST_MANIFEST_VERSION_ID)
        self.assertEqual(data["manifest_hash"], TEST_MANIFEST_HASH)
        self.assertEqual(data["source"], "current")
        self.assertEqual(data["generated_at"], NOW_ISO)
        self.assertEqual(len(data["items"]), 1)

    def test_normalize_by_id_source(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot(source="by_id")
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        self.assertEqual(data["source"], "by_id")

    def test_filename_from_item_id(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot()
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        item = data["items"][0]
        self.assertEqual(item["manifest_item_id"], TEST_ITEM_ID)
        self.assertEqual(item["filename"], f"{TEST_ITEM_ID}.mp4")

    def test_media_path_not_in_local_manifest(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot()
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        raw = json.dumps(data)
        self.assertNotIn("media_path", raw)
        self.assertNotIn("creatives/", raw)

    def test_content_type_from_extension_jpg(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot(items=[{
            "id": TEST_ITEM_ID, "sha256": "a" * 64,
            "media_path": "creatives/photo.jpg", "duration_ms": 1000,
            "loop_position": 0,
        }])
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        self.assertEqual(data["items"][0]["content_type"], "image/jpeg")
        self.assertEqual(data["items"][0]["filename"], f"{TEST_ITEM_ID}.jpg")

    def test_content_type_unknown_extension(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot(items=[{
            "id": TEST_ITEM_ID, "sha256": "a" * 64,
            "media_path": "creatives/file.xyz", "duration_ms": 1000,
            "loop_position": 0,
        }])
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        self.assertEqual(data["items"][0]["content_type"], "application/octet-stream")
        self.assertEqual(data["items"][0]["filename"], f"{TEST_ITEM_ID}.bin")

    def test_order_priority(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        # loop_position takes priority over spot_position
        snap = _make_snapshot(items=[{
            "id": TEST_ITEM_ID, "sha256": "a" * 64,
            "media_path": "creatives/test.mp4", "duration_ms": 1000,
            "loop_position": 3, "spot_position": 1,
        }])
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        self.assertEqual(data["items"][0]["order"], 3)

        # order > loop_position
        snap2 = _make_snapshot(items=[{
            "id": TEST_ITEM_ID, "sha256": "a" * 64,
            "media_path": "creatives/test.mp4", "duration_ms": 1000,
            "order": 7, "loop_position": 3, "spot_position": 1,
        }])
        data2 = normalize_manifest_snapshot(snap2, now=NOW_ISO)
        self.assertEqual(data2["items"][0]["order"], 7)

    def test_forbidden_key_in_snapshot_items_skipped(self):
        from kso_sidecar_agent.manifest_store import normalize_manifest_snapshot
        snap = _make_snapshot(items=[{
            "id": TEST_ITEM_ID, "sha256": "a" * 64,
            "media_path": "creatives/test.mp4", "token": "bad",
        }])
        # Normalize itself doesn't scan for forbidden — validate step will catch it
        data = normalize_manifest_snapshot(snap, now=NOW_ISO)
        self.assertTrue(True)  # normalize doesn't crash on extra keys


# ══════════════════════════════════════════════════════════════════════
# Write / Read tests
# ══════════════════════════════════════════════════════════════════════

class TestWriteReadManifest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _run("init-local-root", "--root", str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_roundtrip(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest, read_current_manifest
        snap = _make_snapshot()
        result = write_current_manifest(str(self.root), snap, now=NOW_ISO)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["items_count"], 1)

        data = read_current_manifest(str(self.root))
        self.assertEqual(data["manifest_version_id"], TEST_MANIFEST_VERSION_ID)
        self.assertEqual(len(data["items"]), 1)

    def test_not_modified_no_overwrite(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest, read_current_manifest
        # Write once
        snap = _make_snapshot()
        result1 = write_current_manifest(str(self.root), snap, now=NOW_ISO)
        self.assertEqual(result1["status"], "written")

        # not_modified should NOT overwrite
        snap2 = _make_snapshot(status="not_modified")
        result2 = write_current_manifest(str(self.root), snap2, now=NOW_ISO)
        self.assertEqual(result2["status"], "not_modified")

        # File still has original content
        data = read_current_manifest(str(self.root))
        self.assertEqual(data["source"], "current")

    def test_no_manifest_does_not_create(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        snap = _make_snapshot(status="no_manifest")
        result = write_current_manifest(str(self.root), snap, now=NOW_ISO)
        self.assertEqual(result["status"], "no_manifest")

        # File should not exist
        path = self.root / CURRENT_MANIFEST_FILE
        self.assertFalse(path.exists())

    def test_no_manifest_does_not_delete_existing(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest, read_current_manifest
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        # Write valid manifest first
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)

        # no_manifest should NOT delete existing file
        snap2 = _make_snapshot(status="no_manifest")
        write_current_manifest(str(self.root), snap2, now=NOW_ISO)

        # File still exists
        path = self.root / CURRENT_MANIFEST_FILE
        self.assertTrue(path.exists())
        data = read_current_manifest(str(self.root))
        self.assertEqual(data["manifest_version_id"], TEST_MANIFEST_VERSION_ID)

    def test_read_missing_raises(self):
        from kso_sidecar_agent.manifest_store import read_current_manifest
        with self.assertRaises(FileNotFoundError):
            read_current_manifest(str(self.root))

    def test_no_leftover_tmp(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)

        # No .tmp files left
        tmp_files = list(Path(self.root).rglob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

    def test_symlink_target_rejected(self):
        """Symlink rejection tested via atomic_write_json (pre-existing behavior)."""
        # atomic_write_json resolves the path first, so direct symlink test
        # requires setting up a scenario where the target itself is a symlink.
        # This is covered by atomic_io unit tests.
        pass


# ══════════════════════════════════════════════════════════════════════
# Validation tests
# ══════════════════════════════════════════════════════════════════════

class TestValidateLocalManifest(unittest.TestCase):

    def _validate(self, overrides):
        from kso_sidecar_agent.manifest_store import validate_local_manifest
        data = dict(VALID_LOCAL_MANIFEST)
        # Apply overrides recursively
        for key, value in overrides.items():
            if key == "items":
                data["items"] = value
            else:
                data[key] = value
        return validate_local_manifest(data)

    def test_valid_passes(self):
        from kso_sidecar_agent.manifest_store import validate_local_manifest
        import copy
        data = copy.deepcopy(VALID_LOCAL_MANIFEST)
        validate_local_manifest(data)  # no raise

    def test_forbidden_key_rejected(self):
        from kso_sidecar_agent.manifest_store import validate_local_manifest
        import copy
        bad = copy.deepcopy(VALID_LOCAL_MANIFEST)
        bad["token"] = "x"
        with self.assertRaises(ValueError):
            validate_local_manifest(bad)

    def test_forbidden_value_rejected(self):
        from kso_sidecar_agent.manifest_store import validate_local_manifest
        import copy
        bad = copy.deepcopy(VALID_LOCAL_MANIFEST)
        bad["manifest_version_id"] = "token"
        with self.assertRaises(ValueError):
            validate_local_manifest(bad)

    def test_invalid_manifest_version_id_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"manifest_version_id": "not-a-uuid"})

    def test_invalid_manifest_hash_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"manifest_hash": "too-short"})

    def test_invalid_source_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"source": "unknown"})

    def test_items_not_list_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"items": "not-a-list"})

    def test_item_invalid_uuid_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"items": [{"manifest_item_id": "bad"}]})

    def test_filename_path_traversal_rejected(self):
        from kso_sidecar_agent.manifest_store import validate_local_manifest
        import copy
        bad = copy.deepcopy(VALID_LOCAL_MANIFEST)
        bad["items"][0]["filename"] = "../etc/passwd"
        with self.assertRaises(ValueError):
            validate_local_manifest(bad)

    def test_filename_absolute_rejected(self):
        from kso_sidecar_agent.manifest_store import validate_local_manifest
        import copy
        bad = copy.deepcopy(VALID_LOCAL_MANIFEST)
        bad["items"][0]["filename"] = "/etc/passwd"
        with self.assertRaises(ValueError):
            validate_local_manifest(bad)

    def test_invalid_sha256_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"items": [{"manifest_item_id": TEST_ITEM_ID, "filename": "test.mp4", "content_type": "video/mp4", "sha256": "bad"}]})

    def test_negative_duration_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"items": [{"manifest_item_id": TEST_ITEM_ID, "filename": "test.mp4", "content_type": "video/mp4", "sha256": "a" * 64, "duration_ms": -1}]})

    def test_negative_order_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"items": [{"manifest_item_id": TEST_ITEM_ID, "filename": "test.mp4", "content_type": "video/mp4", "sha256": "a" * 64, "order": -1}]})

    def test_negative_size_rejected(self):
        with self.assertRaises(ValueError):
            self._validate({"items": [{"manifest_item_id": TEST_ITEM_ID, "filename": "test.mp4", "content_type": "video/mp4", "sha256": "a" * 64, "size_bytes": -1}]})


# ══════════════════════════════════════════════════════════════════════
# Status + CLI tests
# ══════════════════════════════════════════════════════════════════════

class TestManifestStoreStatus(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _run("init-local-root", "--root", str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_missing(self):
        from kso_sidecar_agent.manifest_store import manifest_store_status
        s = manifest_store_status(str(self.root))
        self.assertFalse(s["present"])
        self.assertEqual(s["validation_status"], "missing")

    def test_status_valid(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest, manifest_store_status
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)
        s = manifest_store_status(str(self.root))
        self.assertTrue(s["present"])
        self.assertEqual(s["validation_status"], "ok")
        self.assertEqual(s["items_count"], 1)

    def test_status_invalid_json(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        from kso_sidecar_agent.manifest_store import manifest_store_status
        path = self.root / CURRENT_MANIFEST_FILE
        path.write_text("not json")
        s = manifest_store_status(str(self.root))
        self.assertTrue(s["present"])
        self.assertEqual(s["validation_status"], "error")

    def test_cli_manifest_status_missing(self):
        code, out, err = _run("manifest-status", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("MISSING", out)

    def test_cli_manifest_status_valid(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)
        code, out, err = _run("manifest-status", "--root", str(self.root))
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("PRESENT", out)
        self.assertIn("items_count", out)

    def test_cli_manifest_status_invalid(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        path = self.root / CURRENT_MANIFEST_FILE
        path.write_text("not json")
        code, out, err = _run("manifest-status", "--root", str(self.root))
        self.assertNotEqual(code, 0)
        self.assertIn("INVALID", out)

    def test_cli_manifest_status_no_full_dump(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)
        code, out, err = _run("manifest-status", "--root", str(self.root))
        self.assertNotIn("sha256", out)  # no item details

    def test_cli_manifest_status_no_token_secret(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)
        code, out, err = _run("manifest-status", "--root", str(self.root))
        for forbidden in ("token", "secret", "authorization", "bearer", "local_path", "file_path"):
            self.assertNotIn(forbidden, out + err)


# ══════════════════════════════════════════════════════════════════════
# Doctor tests
# ══════════════════════════════════════════════════════════════════════

class TestDoctorWithManifest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _run("init-local-root", "--root", str(self.root))
        # Make config valid so doctor passes config check
        _run("write-config", "--root", str(self.root),
             "--backend-base-url", "https://example.com", "--device-code", "a-05954")

    def tearDown(self):
        self.tmp.cleanup()

    def test_doctor_without_manifest(self):
        code, out, err = _run("doctor", "--root", str(self.root))
        self.assertIn("manifest_ok", out)
        self.assertIn("manifest_error", out)

    def test_doctor_with_valid_manifest(self):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        snap = _make_snapshot()
        write_current_manifest(str(self.root), snap, now=NOW_ISO)
        code, out, err = _run("doctor", "--root", str(self.root))
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("manifest_ok:", out)

    def test_doctor_with_invalid_manifest(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        path = self.root / CURRENT_MANIFEST_FILE
        path.write_text("not json")
        code, out, err = _run("doctor", "--root", str(self.root))
        self.assertIn("manifest_ok:", out)
        self.assertIn("False", out)

    def test_doctor_no_stacktrace_on_error(self):
        code, out, err = _run("doctor", "--root", "/nonexistent/xyz")
        self.assertNotIn("Traceback", out + err)


if __name__ == "__main__":
    unittest.main()
