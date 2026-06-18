"""Tests for media_cache.py — local file operations only, no backend calls."""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path


TEST_ITEM_ID = "11111111-1111-1111-1111-111111111111"
TEST_FILENAME = f"{TEST_ITEM_ID}.png"
TEST_SHA256 = None  # computed from TEST_CONTENT below
TEST_CONTENT = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_CONTENT_SHA = hashlib.sha256(TEST_CONTENT).hexdigest()
WRONG_CONTENT = b"corrupted" + b"\x00" * 50
WRONG_CONTENT_SHA = hashlib.sha256(WRONG_CONTENT).hexdigest()


def _make_manifest_item(filename=TEST_FILENAME, sha256=None, content_type="image/png", size_bytes=0):
    return {
        "manifest_item_id": TEST_ITEM_ID,
        "filename": filename,
        "sha256": sha256 or TEST_CONTENT_SHA,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "duration_ms": 5000,
        "order": 0,
    }


def _make_media_content(sha256=None, content=None, content_type="image/png", size_bytes=None):
    """Create a MediaContent-like object with the right attributes."""
    class FakeMediaContent:
        pass
    mc = FakeMediaContent()
    data = content if content is not None else TEST_CONTENT
    mc.sha256 = sha256 or hashlib.sha256(data).hexdigest()
    mc.size_bytes = size_bytes if size_bytes is not None else len(data)
    mc.content_type = content_type
    mc.content = data
    return mc


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestEnsureMediaDirs(unittest.TestCase):

    def test_creates_dirs(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR, MEDIA_STAGING_DIR, MEDIA_QUARANTINE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            result = ensure_media_dirs(tmp)
            self.assertTrue(result["current_exists"])
            self.assertTrue(result["staging_exists"])
            self.assertTrue(result["quarantine_exists"])
            self.assertTrue((Path(tmp) / MEDIA_CURRENT_DIR).is_dir())
            self.assertTrue((Path(tmp) / MEDIA_STAGING_DIR).is_dir())
            self.assertTrue((Path(tmp) / MEDIA_QUARANTINE_DIR).is_dir())

    def test_creates_dirs_idempotent(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        with tempfile.TemporaryDirectory() as tmp:
            result1 = ensure_media_dirs(tmp)
            # First call creates dirs
            self.assertGreater(len(result1["created"]), 0)
            result2 = ensure_media_dirs(tmp)
            # Second call is idempotent — nothing new
            self.assertEqual(result2["created"], [])


class TestWriteMediaAtomic(unittest.TestCase):

    def setUp(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_media_dirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_success(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR, MEDIA_STAGING_DIR

        item = _make_manifest_item()
        mc = _make_media_content()

        result = write_media_atomic(self.root, item, mc)
        self.assertEqual(result["status"], "written")
        self.assertTrue(result["sha256_ok"])
        self.assertTrue(result["size_ok"])

        # File exists in current
        target = self.root / MEDIA_CURRENT_DIR / TEST_FILENAME
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), TEST_CONTENT)

        # No .download left in staging
        staging = self.root / MEDIA_STAGING_DIR
        downloads = list(staging.glob("*.download"))
        self.assertEqual(len(downloads), 0)

    def test_write_sha256_mismatch_reject(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR

        item = _make_manifest_item()
        mc = _make_media_content(sha256=WRONG_CONTENT_SHA, content=WRONG_CONTENT)

        result = write_media_atomic(self.root, item, mc)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["sha256_ok"])

        # File NOT in current
        target = self.root / MEDIA_CURRENT_DIR / TEST_FILENAME
        self.assertFalse(target.exists())

    def test_write_size_mismatch_reject(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR

        item = _make_manifest_item(size_bytes=999999)
        mc = _make_media_content(size_bytes=len(TEST_CONTENT))

        result = write_media_atomic(self.root, item, mc)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["size_ok"])

        # File NOT in current
        target = self.root / MEDIA_CURRENT_DIR / TEST_FILENAME
        self.assertFalse(target.exists())

    def test_write_content_type_mismatch_reject(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR

        item = _make_manifest_item(content_type="video/mp4")
        mc = _make_media_content(content_type="image/png")

        result = write_media_atomic(self.root, item, mc)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["content_type_ok"])

        target = self.root / MEDIA_CURRENT_DIR / TEST_FILENAME
        self.assertFalse(target.exists())

    def test_write_empty_content_reject(self):
        from kso_sidecar_agent.media_cache import write_media_atomic

        item = _make_manifest_item()
        mc = _make_media_content(content=b"")

        with self.assertRaises(ValueError) as ctx:
            write_media_atomic(self.root, item, mc)
        self.assertIn("non-empty", str(ctx.exception).lower())

    def test_existing_valid_not_corrupted(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR

        # Write a valid file first
        item = _make_manifest_item()
        mc = _make_media_content()
        write_media_atomic(self.root, item, mc)

        # Now try to write a bad file — should not corrupt the good one
        bad_mc = _make_media_content(sha256=WRONG_CONTENT_SHA, content=WRONG_CONTENT)
        write_media_atomic(self.root, item, bad_mc)

        # Original file should still be intact
        target = self.root / MEDIA_CURRENT_DIR / TEST_FILENAME
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), TEST_CONTENT)

    def test_unsafe_filename_reject(self):
        from kso_sidecar_agent.media_cache import write_media_atomic

        item = _make_manifest_item(filename="../evil.png")
        mc = _make_media_content()

        with self.assertRaises(ValueError) as ctx:
            write_media_atomic(self.root, item, mc)
        self.assertIn("traversal", str(ctx.exception).lower())

    def test_path_traversal_reject(self):
        from kso_sidecar_agent.media_cache import write_media_atomic

        item = _make_manifest_item(filename="sub/file.png")
        mc = _make_media_content()

        with self.assertRaises(ValueError):
            write_media_atomic(self.root, item, mc)


class TestVerifyMediaFile(unittest.TestCase):

    def setUp(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs, write_media_atomic
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_media_dirs(self.root)

        item = _make_manifest_item(size_bytes=len(TEST_CONTENT))
        mc = _make_media_content()
        write_media_atomic(self.root, item, mc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verify_success(self):
        from kso_sidecar_agent.media_cache import verify_media_file
        item = _make_manifest_item(size_bytes=len(TEST_CONTENT))
        result = verify_media_file(self.root, item)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["sha256_ok"])
        self.assertTrue(result["size_ok"])
        self.assertTrue(result["exists"])

    def test_verify_missing(self):
        from kso_sidecar_agent.media_cache import verify_media_file
        item = _make_manifest_item(filename="nonexistent.png")
        result = verify_media_file(self.root, item)
        self.assertEqual(result["status"], "missing")
        self.assertFalse(result["exists"])

    def test_verify_invalid_hash(self):
        from kso_sidecar_agent.media_cache import verify_media_file
        item = _make_manifest_item(sha256=WRONG_CONTENT_SHA)
        result = verify_media_file(self.root, item)
        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["sha256_ok"])

    def test_verify_invalid_size(self):
        from kso_sidecar_agent.media_cache import verify_media_file
        item = _make_manifest_item(size_bytes=999999)
        result = verify_media_file(self.root, item)
        self.assertFalse(result["size_ok"])
        self.assertIn("invalid", result["status"])

    def test_verify_symlink_reject(self):
        from kso_sidecar_agent.media_cache import verify_media_file
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR

        target = self.root / MEDIA_CURRENT_DIR / "symlink.png"
        # Remove existing file and create symlink
        existing = self.root / MEDIA_CURRENT_DIR / TEST_FILENAME
        existing.unlink()
        existing.symlink_to("/etc/passwd")  # safe — doesn't actually need to exist

        item = _make_manifest_item(filename=TEST_FILENAME)
        result = verify_media_file(self.root, item)
        self.assertEqual(result["status"], "rejected")


class TestMediaCacheStatus(unittest.TestCase):

    def setUp(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_media_dirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_without_manifest(self):
        from kso_sidecar_agent.media_cache import media_cache_status
        result = media_cache_status(self.root)
        self.assertTrue(result["present"])
        self.assertEqual(result["current_files_count"], 0)
        self.assertEqual(result["staging_files_count"], 0)
        self.assertEqual(result["quarantine_files_count"], 0)

    def test_status_with_manifest_complete(self):
        from kso_sidecar_agent.media_cache import media_cache_status, write_media_atomic

        item = _make_manifest_item()
        mc = _make_media_content()
        write_media_atomic(self.root, item, mc)

        result = media_cache_status(self.root, manifest_items=[item])
        self.assertEqual(result["items_total"], 1)
        self.assertEqual(result["items_cached"], 1)
        self.assertEqual(result["items_missing"], 0)
        self.assertEqual(result["items_invalid_hash"], 0)
        self.assertTrue(result["cache_complete"])

    def test_status_with_missing_item(self):
        from kso_sidecar_agent.media_cache import media_cache_status

        item = _make_manifest_item()
        result = media_cache_status(self.root, manifest_items=[item])
        self.assertEqual(result["items_total"], 1)
        self.assertEqual(result["items_cached"], 0)
        self.assertEqual(result["items_missing"], 1)
        self.assertFalse(result["cache_complete"])

    def test_status_with_corrupted_item(self):
        from kso_sidecar_agent.media_cache import media_cache_status, ensure_media_dirs
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR

        # Write wrong content to current
        current = self.root / MEDIA_CURRENT_DIR
        (current / TEST_FILENAME).write_bytes(WRONG_CONTENT)

        item = _make_manifest_item()
        result = media_cache_status(self.root, manifest_items=[item])
        self.assertEqual(result["items_total"], 1)
        self.assertEqual(result["items_cached"], 0)
        self.assertEqual(result["items_invalid_hash"], 1)
        self.assertFalse(result["cache_complete"])


class TestQuarantineMediaFile(unittest.TestCase):

    def setUp(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs, write_media_atomic
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_media_dirs(self.root)

        item = _make_manifest_item()
        mc = _make_media_content()
        write_media_atomic(self.root, item, mc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_quarantine_success(self):
        from kso_sidecar_agent.media_cache import quarantine_media_file
        from kso_sidecar_agent.paths import MEDIA_CURRENT_DIR, MEDIA_QUARANTINE_DIR

        result = quarantine_media_file(self.root, TEST_FILENAME, reason="test quarantine")
        self.assertEqual(result["status"], "quarantined")
        self.assertTrue(result["moved"])

        # File no longer in current
        self.assertFalse((self.root / MEDIA_CURRENT_DIR / TEST_FILENAME).exists())

        # File in quarantine
        quarantine = self.root / MEDIA_QUARANTINE_DIR
        bad_files = list(quarantine.glob("*.bad"))
        self.assertTrue(len(bad_files) > 0)

    def test_quarantine_not_found(self):
        from kso_sidecar_agent.media_cache import quarantine_media_file
        result = quarantine_media_file(self.root, "nonexistent.png")
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(result["moved"])

    def test_quarantine_unsafe_filename(self):
        from kso_sidecar_agent.media_cache import quarantine_media_file
        with self.assertRaises(ValueError):
            quarantine_media_file(self.root, "../evil.png")


class TestSecurityNoLeaks(unittest.TestCase):

    def setUp(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_media_dirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_no_local_path_in_output(self):
        from kso_sidecar_agent.media_cache import media_cache_status
        result = media_cache_status(self.root)
        str_result = str(result)
        self.assertNotIn(str(self.root), str_result)
        self.assertNotIn("/media/current", str_result)
        self.assertNotIn("local_path", str_result.lower())
        self.assertNotIn("file_path", str_result.lower())

    def test_write_no_local_path_in_output(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        item = _make_manifest_item()
        mc = _make_media_content()
        result = write_media_atomic(self.root, item, mc)
        str_result = str(result)
        self.assertNotIn(str(self.root), str_result)
        self.assertNotIn("local_path", str_result.lower())
        self.assertNotIn("file_path", str_result.lower())

    def test_verify_no_local_path_in_output(self):
        from kso_sidecar_agent.media_cache import verify_media_file, write_media_atomic
        item = _make_manifest_item()
        mc = _make_media_content()
        write_media_atomic(self.root, item, mc)
        result = verify_media_file(self.root, item)
        str_result = str(result)
        self.assertNotIn(str(self.root), str_result)

    def test_no_token_in_output(self):
        from kso_sidecar_agent.media_cache import media_cache_status
        result = media_cache_status(self.root)
        str_result = str(result).lower()
        self.assertNotIn("token", str_result)
        self.assertNotIn("secret", str_result)
        self.assertNotIn("authorization", str_result)
        self.assertNotIn("bearer", str_result)


if __name__ == "__main__":
    unittest.main()
