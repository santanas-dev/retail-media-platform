"""Tests for KSO Sidecar PoP Pending Lock Core.

Tests try_acquire_pop_pending_lock(), release_pop_pending_lock(),
and pop_pending_lock context manager.
Pure file I/O — no HTTP, no backend, no secret reading.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from kso_sidecar_agent.pop_pending_lock import (
    PopPendingLockResult,
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    pop_pending_lock,
    STATUS_LOCKED,
    STATUS_RELEASED,
    STATUS_SKIPPED,
    STATUS_ERROR,
    REASON_LOCKED,
    REASON_RELEASED,
    REASON_LOCK_UNAVAILABLE,
    REASON_LOCK_FAILED,
    REASON_RELEASE_FAILED,
    REASON_INVALID_ROOT,
    LOCK_MARKER_SCHEMA,
    LOCK_COMPONENT,
    DEFAULT_LOCK_OPERATION,
    ALLOWED_LOCK_OPERATIONS,
    FORBIDDEN_SUBSTRINGS,
    POP_PENDING_DIR,
    POP_LOCK_FILE,
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


# ══════════════════════════════════════════════════════════════════════
# Tests: acquire
# ══════════════════════════════════════════════════════════════════════

class TestAcquireLock(TestCase):
    """try_acquire_pop_pending_lock tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_acquire_success(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        self.assertEqual(result.status, STATUS_LOCKED)
        self.assertTrue(result.acquired)
        self.assertEqual(result.reason, REASON_LOCKED)

    def test_acquire_creates_lock_file(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists())

    def test_acquire_creates_pending_dir(self):
        try_acquire_pop_pending_lock(self.tmp)
        pending_dir = self.tmp / POP_PENDING_DIR
        self.assertTrue(pending_dir.is_dir())

    def test_acquire_marker_safe(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        content = lock_path.read_text()
        marker = json.loads(content.strip())
        self.assertEqual(marker["schema_version"], 2)
        self.assertEqual(marker["component"], "sidecar")
        self.assertIn("operation", marker)
        self.assertIn("created_at_utc", marker)
        self.assertIn("pid", marker)
        self.assertIn("boot_id_hash", marker)
        lower = content.lower()
        for fb in ("token", "secret", "password", "path", "backend",
                    "manifest_item_id", "batch_id", "sha256",
                    "media_bytes", "fingerprint", "stacktrace"):
            self.assertNotIn(fb, lower, f"forbidden '{fb}' in marker")

    def test_acquire_marker_no_paths(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        content = lock_path.read_text().lower()
        self.assertNotIn("/pop/", content)
        self.assertNotIn("player_events", content)
        self.assertNotIn(".lock", content)

    def test_acquire_twice_second_fails(self):
        result1 = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(result1.acquired)

        result2 = try_acquire_pop_pending_lock(self.tmp)
        self.assertFalse(result2.acquired)
        self.assertEqual(result2.status, STATUS_SKIPPED)
        self.assertEqual(result2.reason, REASON_LOCK_UNAVAILABLE)

    def test_acquire_twice_different_paths_both_work(self):
        tmp2 = Path(tempfile.mkdtemp())
        try:
            r1 = try_acquire_pop_pending_lock(self.tmp)
            r2 = try_acquire_pop_pending_lock(tmp2)
            self.assertTrue(r1.acquired)
            self.assertTrue(r2.acquired)
        finally:
            import shutil
            shutil.rmtree(tmp2, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Tests: release
# ══════════════════════════════════════════════════════════════════════

class TestReleaseLock(TestCase):
    """release_pop_pending_lock tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_release_after_acquire(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        released = release_pop_pending_lock(result)
        self.assertEqual(released.status, STATUS_RELEASED)
        self.assertTrue(released.released)
        self.assertEqual(released.reason, REASON_RELEASED)

    def test_release_removes_lock_file(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists())
        release_pop_pending_lock(result)
        self.assertFalse(lock_path.exists())

    def test_acquire_after_release_works(self):
        r1 = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(r1.acquired)
        release_pop_pending_lock(r1)

        r2 = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(r2.acquired)

    def test_release_non_result_safe(self):
        released = release_pop_pending_lock("not_a_result")
        self.assertEqual(released.status, STATUS_ERROR)
        self.assertEqual(released.reason, REASON_RELEASE_FAILED)

    def test_release_none_safe(self):
        released = release_pop_pending_lock(None)
        self.assertEqual(released.status, STATUS_ERROR)

    def test_double_release_safe(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        release_pop_pending_lock(result)
        # Second release — safe, no error
        released2 = release_pop_pending_lock(result)
        self.assertEqual(released2.status, STATUS_RELEASED)

    def test_release_result_without_path_safe(self):
        empty_result = PopPendingLockResult(status=STATUS_LOCKED, acquired=True)
        released = release_pop_pending_lock(empty_result)
        self.assertEqual(released.status, STATUS_RELEASED)


# ══════════════════════════════════════════════════════════════════════
# Tests: context manager
# ══════════════════════════════════════════════════════════════════════

class TestContextManager(TestCase):
    """pop_pending_lock context manager tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_context_manager_releases_on_exit(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(result.acquired)

        with pop_pending_lock(result):
            lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
            self.assertTrue(lock_path.exists())

        # After exit — lock released
        self.assertFalse(lock_path.exists())

    def test_context_manager_releases_on_exception(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        try:
            with pop_pending_lock(result):
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        # Lock released despite exception
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists())

    def test_context_manager_does_not_suppress_exception(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        with self.assertRaises(ValueError):
            with pop_pending_lock(result):
                raise ValueError("should propagate")


# ══════════════════════════════════════════════════════════════════════
# Tests: result safety
# ══════════════════════════════════════════════════════════════════════

class TestResultSafety(TestCase):
    """PopPendingLockResult repr/output safety."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repr_locked_no_forbidden(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text), f"forbidden in repr: {text[:200]}")

    def test_repr_skipped_no_forbidden(self):
        try_acquire_pop_pending_lock(self.tmp)
        result2 = try_acquire_pop_pending_lock(self.tmp)
        text = repr(result2)
        self.assertTrue(_no_forbidden(text))

    def test_repr_released_no_forbidden(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        released = release_pop_pending_lock(result)
        text = repr(released)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_absolute_path(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)

    def test_repr_no_lock_filename(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        text = repr(result)
        self.assertNotIn("player_events.lock", text)

    def test_repr_no_ids(self):
        result = try_acquire_pop_pending_lock(self.tmp)
        text = repr(result)
        self.assertNotIn("batch_id", text)
        self.assertNotIn("device_event_id", text)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("campaign_id", text)

    def test_all_reasons_safe_in_repr(self):
        base = PopPendingLockResult()
        for reason in [
            REASON_LOCKED, REASON_RELEASED, REASON_LOCK_UNAVAILABLE,
            REASON_LOCK_FAILED, REASON_RELEASE_FAILED, REASON_INVALID_ROOT,
        ]:
            r = PopPendingLockResult(status=STATUS_SKIPPED, reason=reason)
            text = repr(r)
            self.assertTrue(_no_forbidden(text), f"reason={reason}: {text}")


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid inputs
# ══════════════════════════════════════════════════════════════════════

class TestInvalidInputs(TestCase):
    """Invalid root paths — safe error, no crash.
    
    Uses TemporaryDirectory to avoid leaking pop/ artifacts into cwd.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_none_root(self):
        result = try_acquire_pop_pending_lock(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ROOT)
        self.assertFalse(result.acquired)

    def test_empty_string_root(self):
        result = try_acquire_pop_pending_lock("")
        # Path("") → cwd; should not crash, may succeed or error depending on cwd
        self.assertIsNotNone(result)
        # Release if acquired + remove leaked pop/ from cwd
        if result.acquired:
            release_pop_pending_lock(result)
        import shutil
        shutil.rmtree(Path("pop"), ignore_errors=True)

    def test_invalid_type(self):
        result = try_acquire_pop_pending_lock(12345)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ROOT)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """Lock helpers do NOT read/write JSONL, create dirs, or do HTTP."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_does_not_create_jsonl(self):
        try_acquire_pop_pending_lock(self.tmp)
        jsonl_path = self.tmp / POP_PENDING_DIR / "player_events.jsonl"
        self.assertFalse(jsonl_path.exists())

    def test_lock_does_not_modify_jsonl_if_exists(self):
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        jsonl_path = pending / "player_events.jsonl"
        original = "test line\n"
        jsonl_path.write_text(original)

        try_acquire_pop_pending_lock(self.tmp)
        self.assertEqual(jsonl_path.read_text(), original)

    def test_lock_does_not_create_sent_quarantine_dry_run_failed(self):
        try_acquire_pop_pending_lock(self.tmp)
        pop_dir = self.tmp / "pop"
        if pop_dir.exists():
            for bad in ("sent", "quarantine", "dry_run", "failed"):
                bad_path = pop_dir / bad
                self.assertFalse(bad_path.exists(),
                    f"'{bad}/' dir should not exist")

    def test_module_no_http_imports(self):
        with open(__file__.replace("tests/test_pop_pending_lock.py", "kso_sidecar_agent/pop_pending_lock.py")) as f:
            content = f.read()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import socket", content)
        self.assertNotIn("import requests", content)

    def test_module_no_secret_reading(self):
        with open(__file__.replace("tests/test_pop_pending_lock.py", "kso_sidecar_agent/pop_pending_lock.py")) as f:
            content = f.read()
        # No secret/config/auth module imports
        self.assertNotIn("secret_store", content)
        self.assertNotIn("local_config", content)
        self.assertNotIn("auth_client", content)
        self.assertNotIn("from kso_sidecar_agent.http_client", content)


# ══════════════════════════════════════════════════════════════════════
# Tests: lock marker validation
# ══════════════════════════════════════════════════════════════════════

class TestLockMarkerSafety(TestCase):
    """V2 lock marker and POP_LOCK_FILE constants are safe."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_marker_schema_version_is_two(self):
        self.assertEqual(LOCK_MARKER_SCHEMA, 2)

    def test_marker_component_is_sidecar(self):
        self.assertEqual(LOCK_COMPONENT, "sidecar")

    def test_allowed_operations_known(self):
        for op in ("rotation_plan", "rotation_apply", "send_package", "pop_write", "unknown"):
            self.assertIn(op, ALLOWED_LOCK_OPERATIONS)

    def test_default_operation_is_unknown(self):
        self.assertEqual(DEFAULT_LOCK_OPERATION, "unknown")

    def test_lock_file_matches_player(self):
        self.assertEqual(POP_LOCK_FILE, "player_events.lock")

    def test_pending_dir_matches_player(self):
        self.assertEqual(POP_PENDING_DIR, "pop/pending")

    def test_acquire_writes_v2_marker(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["schema_version"], 2)
        self.assertEqual(marker["component"], "sidecar")
        self.assertIn(marker["operation"], ALLOWED_LOCK_OPERATIONS)

    def test_acquire_default_operation(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["operation"], DEFAULT_LOCK_OPERATION)

    def test_acquire_custom_operation_rotation_apply(self):
        try_acquire_pop_pending_lock(self.tmp, operation="rotation_apply")
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["operation"], "rotation_apply")

    def test_acquire_custom_operation_send_package(self):
        try_acquire_pop_pending_lock(self.tmp, operation="send_package")
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["operation"], "send_package")

    def test_acquire_unknown_operation_normalised(self):
        try_acquire_pop_pending_lock(self.tmp, operation="bogus_operation_xyz")
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["operation"], DEFAULT_LOCK_OPERATION)

    def test_acquire_empty_operation_normalised(self):
        try_acquire_pop_pending_lock(self.tmp, operation="")
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["operation"], DEFAULT_LOCK_OPERATION)

    def test_marker_has_pid(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertIsInstance(marker["pid"], int)
        self.assertGreater(marker["pid"], 0)

    def test_marker_has_boot_id_hash(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertIn("boot_id_hash", marker)
        self.assertIsInstance(marker["boot_id_hash"], str)

    def test_marker_has_created_at_utc(self):
        try_acquire_pop_pending_lock(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertIn("created_at_utc", marker)
        # Should be an ISO8601-like timestamp (contains T and +/- or Z)
        self.assertIn("T", marker["created_at_utc"])

    def test_release_after_acquire_with_operation(self):
        result = try_acquire_pop_pending_lock(self.tmp, operation="rotation_apply")
        self.assertTrue(result.acquired)
        released = release_pop_pending_lock(result)
        self.assertEqual(released.status, STATUS_RELEASED)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: concurrent access simulation
# ══════════════════════════════════════════════════════════════════════

class TestConcurrentSimulation(TestCase):
    """Simulate concurrent access — second acquirer gets lock_unavailable."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_sequential_acquires(self):
        # Simulate: process A acquires, process B tries
        a = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(a.acquired)

        b = try_acquire_pop_pending_lock(self.tmp)
        self.assertFalse(b.acquired)
        self.assertEqual(b.reason, REASON_LOCK_UNAVAILABLE)

        # Process A releases
        release_pop_pending_lock(a)

        # Process B can now acquire
        b2 = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(b2.acquired)
        release_pop_pending_lock(b2)

    def test_three_acquires_third_also_skipped(self):
        a = try_acquire_pop_pending_lock(self.tmp)
        b = try_acquire_pop_pending_lock(self.tmp)
        c = try_acquire_pop_pending_lock(self.tmp)

        self.assertTrue(a.acquired)
        self.assertFalse(b.acquired)
        self.assertFalse(c.acquired)


if __name__ == "__main__":
    import unittest
    unittest.main()
