"""Tests for KSO Sidecar PoP Rotation Atomic File Ops."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock

from kso_sidecar_agent.pop_rotation_files import (
    PopRotationFileWriteResult,
    write_pop_rotation_records_atomic,
    format_pop_rotation_file_result,
    ALLOWED_TARGETS,
    FORBIDDEN_SUBSTRINGS,
    STATUS_WRITTEN,
    STATUS_SKIPPED,
    STATUS_ERROR,
    REASON_WRITTEN,
    REASON_NO_RECORDS,
    REASON_INVALID_TARGET,
    REASON_UNSAFE_RECORD,
    REASON_WRITE_FAILED,
    REASON_INVALID_ROOT,
    POP_BASE,
)

FORBIDDEN_VALUES = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
}


def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_VALUES:
        if fb in lower:
            return False
    return True


def _safe_record(extra=None):
    r = {
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "completed",
        "created_at": "2026-06-19T10:00:00Z",
        "started_at": "2026-06-19T10:00:00Z",
        "duration_ms": 15000,
        "playback_allowed": True,
        "session_action": "play",
        "session_reason": "ready",
        "selected_order": 1,
        "selected_content_type": "video/mp4",
        "safety_state": "idle",
        "result": "would_play",
    }
    if extra:
        r.update(extra)
    return r


def _list_jsonl_files(root, target):
    """List written .jsonl files in pop/<target>/."""
    tdir = Path(root) / POP_BASE / target
    if not tdir.exists():
        return []
    return sorted(f.name for f in tdir.glob("*.jsonl") if not f.name.startswith("."))


def _read_jsonl_content(root, target):
    """Read all jsonl content from pop/<target>/, return list of parsed records."""
    tdir = Path(root) / POP_BASE / target
    if not tdir.exists():
        return []
    records = []
    for f in sorted(tdir.glob("*.jsonl")):
        if f.name.startswith("."):
            continue
        for line in f.read_text().split("\n"):
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


# ══════════════════════════════════════════════════════════════════════
# Basic writes
# ══════════════════════════════════════════════════════════════════════

class TestWriteBasic(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_to_sent(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertTrue(result.written)
        self.assertEqual(result.target, "sent")
        self.assertEqual(result.records_written, 1)
        self.assertGreater(result.line_size_bytes, 0)
        self.assertEqual(result.reason, REASON_WRITTEN)

        # File exists
        files = _list_jsonl_files(self.tmp, "sent")
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("rotation_"))

    def test_write_to_quarantine(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "quarantine", [_safe_record()], now="20260619T100000Z")
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertEqual(result.target, "quarantine")
        files = _list_jsonl_files(self.tmp, "quarantine")
        self.assertEqual(len(files), 1)

    def test_write_to_dry_run(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "dry_run", [_safe_record()], now="20260619T100000Z")
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertEqual(result.target, "dry_run")
        files = _list_jsonl_files(self.tmp, "dry_run")
        self.assertEqual(len(files), 1)

    def test_write_to_failed(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "failed", [_safe_record()], now="20260619T100000Z")
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertEqual(result.target, "failed")
        files = _list_jsonl_files(self.tmp, "failed")
        self.assertEqual(len(files), 1)

    def test_write_multiple_records(self):
        records = [_safe_record() for _ in range(3)]
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", records, now="20260619T100000Z")
        self.assertEqual(result.records_written, 3)
        content = _read_jsonl_content(self.tmp, "sent")
        self.assertEqual(len(content), 3)

    def test_jsonl_is_parseable(self):
        records = [_safe_record(), _safe_record({"extra_key": "val1"})]
        write_pop_rotation_records_atomic(
            self.tmp, "sent", records, now="20260619T100000Z")
        content = _read_jsonl_content(self.tmp, "sent")
        self.assertEqual(len(content), 2)
        self.assertEqual(content[0]["schema_version"], 1)

    def test_each_line_ends_with_newline(self):
        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        files = _list_jsonl_files(self.tmp, "sent")
        tdir = Path(self.tmp) / POP_BASE / "sent"
        raw = (tdir / files[0]).read_text()
        self.assertTrue(raw.endswith("\n"))
        # One record → one trailing \n
        self.assertEqual(len(raw.split("\n")), 2)  # record + trailing empty

    def test_second_write_creates_another_file(self):
        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100001Z")
        files = _list_jsonl_files(self.tmp, "sent")
        self.assertEqual(len(files), 2)
        self.assertNotEqual(files[0], files[1])


# ══════════════════════════════════════════════════════════════════════
# Empty / no records
# ══════════════════════════════════════════════════════════════════════

class TestWriteEmptyNoRecords(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_records_skipped(self):
        result = write_pop_rotation_records_atomic(self.tmp, "sent", [])
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertFalse(result.written)
        self.assertEqual(result.reason, REASON_NO_RECORDS)
        self.assertFalse((self.tmp / POP_BASE / "sent").exists())

    def test_empty_records_no_dir_created(self):
        write_pop_rotation_records_atomic(self.tmp, "dry_run", [])
        self.assertFalse((self.tmp / POP_BASE / "dry_run").exists())


# ══════════════════════════════════════════════════════════════════════
# Invalid targets
# ══════════════════════════════════════════════════════════════════════

class TestWriteInvalidTarget(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_invalid_target_skipped(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "pending", [_safe_record()])
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertEqual(result.reason, REASON_INVALID_TARGET)
        self.assertIsNone(result.target)

    def test_unknown_target_skipped(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "garbage", [_safe_record()])
        self.assertEqual(result.status, STATUS_SKIPPED)

    def test_invalid_target_no_dir_created(self):
        write_pop_rotation_records_atomic(
            self.tmp, "pending", [_safe_record()])
        self.assertFalse((self.tmp / POP_BASE / "pending").exists())


# ══════════════════════════════════════════════════════════════════════
# Unsafe records
# ══════════════════════════════════════════════════════════════════════

class TestWriteUnsafeRecords(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_non_dict_record_error(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", ["not a dict"])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_forbidden_key_error(self):
        rec = _safe_record({"token": "abc"})
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [rec])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_forbidden_value_error(self):
        rec = _safe_record({"selected_content_type": "secret=abc"})
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [rec])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_forbidden_deep_value_error(self):
        rec = _safe_record({"extra": {"nested": "access_token=xyz"}})
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [rec])
        self.assertEqual(result.status, STATUS_ERROR)

    def test_forbidden_in_list_error(self):
        rec = _safe_record({"list_val": ["ok", "password=secret"]})
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [rec])
        self.assertEqual(result.status, STATUS_ERROR)

    def test_unsafe_record_no_file_created(self):
        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record({"token": "abc"})])
        files = _list_jsonl_files(self.tmp, "sent")
        self.assertEqual(files, [])

    def test_mixed_safe_and_unsafe_all_skipped(self):
        """All records must be safe — one unsafe voids the whole batch."""
        records = [_safe_record(), {"bad": "token=abc"}]
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", records)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)
        self.assertEqual(_list_jsonl_files(self.tmp, "sent"), [])


# ══════════════════════════════════════════════════════════════════════
# Atomic / tmp cleanup
# ══════════════════════════════════════════════════════════════════════

class TestWriteAtomicCleanup(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tmp_file_removed_after_success(self):
        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        tdir = self.tmp / POP_BASE / "sent"
        tmp_files = list(tdir.glob(".rotation_*.tmp"))
        self.assertEqual(tmp_files, [], f"tmp leftovers: {tmp_files}")

    def test_tmp_file_removed_after_failure(self):
        rec = _safe_record({"token": "abc"})
        write_pop_rotation_records_atomic(self.tmp, "sent", [rec])
        tdir = self.tmp / POP_BASE / "sent"
        if tdir.exists():
            tmp_files = list(tdir.glob(".rotation_*.tmp"))
            self.assertEqual(tmp_files, [])

    def test_simulated_write_failure_cleans_tmp(self):
        """Simulate fsync failure → error, no stacktrace, tmp cleaned."""
        rec = _safe_record()
        # Use a bad dir — write will fail on mkdir or write
        # Create the dir but make it non-writable
        tdir = self.tmp / POP_BASE / "sent"
        tdir.mkdir(parents=True)

        # Simulate: write to file, but os.replace fails by making dir read-only
        with patch("os.replace", side_effect=OSError("simulated")):
            result = write_pop_rotation_records_atomic(
                self.tmp, "sent", [rec])
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_WRITE_FAILED)
            # No stacktrace in result
            self.assertNotIn("simulated", repr(result))

            # tmp should be cleaned
            tmp_files = list(tdir.glob(".rotation_*.tmp"))
            self.assertEqual(tmp_files, [])

    def test_simulated_oserror_no_stacktrace(self):
        with patch("os.replace", side_effect=OSError("disk full")):
            result = write_pop_rotation_records_atomic(
                self.tmp, "sent", [_safe_record()])
            self.assertEqual(result.reason, REASON_WRITE_FAILED)
            self.assertNotIn("disk full", repr(result))
            self.assertNotIn("OSError", repr(result))


# ══════════════════════════════════════════════════════════════════════
# Invalid root
# ══════════════════════════════════════════════════════════════════════

class TestWriteInvalidRoot(TestCase):
    def test_none_root_error(self):
        result = write_pop_rotation_records_atomic(None, "sent", [_safe_record()])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ROOT)


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

class TestWriteSafeOutput(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_format_no_forbidden(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = format_pop_rotation_file_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_forbidden(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_file_path(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("rotation_", text.lower())

    def test_repr_no_filename(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = repr(result)
        self.assertNotIn(".jsonl", text)

    def test_repr_no_tmp_path(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = repr(result)
        self.assertNotIn(".tmp", text)

    def test_repr_no_ids(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = repr(result)
        self.assertNotIn("manifest_item_id", text.lower())
        self.assertNotIn("batch_id", text.lower())

    def test_no_stacktrace(self):
        with patch("os.replace", side_effect=OSError()):
            result = write_pop_rotation_records_atomic(
                self.tmp, "sent", [_safe_record()])
        text = repr(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("Exception", text)
        self.assertNotIn("OSError", text)

    def test_format_contains_all_fields(self):
        result = write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        text = format_pop_rotation_file_result(result)
        for field in [
            "status:", "written:", "target:", "records_written:",
            "line_size_bytes:", "reason:",
        ]:
            self.assertIn(field, text, f"Missing field '{field}'")


# ══════════════════════════════════════════════════════════════════════
# No side effects
# ══════════════════════════════════════════════════════════════════════

class TestWriteNoSideEffects(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_does_not_read_pending(self):
        """Function never reads pop/pending/player_events.jsonl."""
        pending = self.tmp / POP_BASE / "pending"
        pending.mkdir(parents=True)
        jl = pending / "player_events.jsonl"
        jl.write_text('{"test": 1}\n')

        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")

        # pending unchanged
        self.assertTrue(jl.exists())
        self.assertEqual(jl.read_text(), '{"test": 1}\n')

    def test_does_not_modify_pending(self):
        pending = self.tmp / POP_BASE / "pending"
        pending.mkdir(parents=True)
        jl = pending / "player_events.jsonl"
        original = '{"original": true}\n'
        jl.write_text(original)

        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()], now="20260619T100000Z")
        self.assertEqual(jl.read_text(), original)

    def test_does_not_delete_pending(self):
        pending = self.tmp / POP_BASE / "pending"
        pending.mkdir(parents=True)
        jl = pending / "player_events.jsonl"
        jl.write_text('{"a": 1}\n')

        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()])
        self.assertTrue(jl.exists())

    def test_no_http_imports(self):
        """Module has no HTTP/URL imports."""
        mod_path = Path(__file__).parent.parent / "kso_sidecar_agent" / "pop_rotation_files.py"
        content = mod_path.read_text()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import requests", content)
        self.assertNotIn("import http", content)

    def test_does_not_read_secret_config(self):
        """Function does not touch config/secret files."""
        write_pop_rotation_records_atomic(
            self.tmp, "sent", [_safe_record()])
        # Just verifies no exception on missing config
        self.assertFalse((self.tmp / "config").exists())


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import unittest
    unittest.main()
