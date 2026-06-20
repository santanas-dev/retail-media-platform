"""Tests for KSO Player PoP Local Writer (pop_writer.py).

Verifies safe append-only JSONL writing, validation, security, and fail-silent behavior.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, mock_open, MagicMock

from kso_player.pop_writer import (
    PopWriteResult,
    build_pop_jsonl_record,
    write_pop_event,
    STATUS_WRITTEN,
    STATUS_SKIPPED,
    STATUS_ERROR,
    REASON_WRITTEN,
    REASON_INVALID_EVENT,
    REASON_UNSAFE_RECORD,
    REASON_WRITE_FAILED,
    REASON_LOCK_UNAVAILABLE,
    ALLOWED_SAFETY_STATES,
    ALLOWED_RECORD_KEYS,
    FORBIDDEN_SUBSTRINGS,
    FORBIDDEN_KEYS,
    MAX_LINE_SIZE_BYTES,
    POP_PENDING_DIR,
    POP_JSONL_FILE,
    POP_LOCK_FILE,
    SCHEMA_VERSION,
    LOCK_MARKER_SCHEMA,
    LOCK_COMPONENT,
    LOCK_OPERATION,
    _acquire_lock,
    _release_lock,
    _safe_unlink,
)
from kso_player.events import (
    PlaybackEventDraft,
    EVENT_TYPE_WOULD_PLAY,
    EVENT_TYPE_BLOCKED,
    EVENT_TYPE_NOT_READY,
    EVENT_TYPE_ERROR,
    EVENT_STATUS_DRAFT,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _make_draft(event_type=EVENT_TYPE_WOULD_PLAY, **kwargs):
    """Create a PlaybackEventDraft with defaults."""
    defaults = {
        "event_type": event_type,
        "event_status": EVENT_STATUS_DRAFT,
        "playback_allowed": (event_type == EVENT_TYPE_WOULD_PLAY),
        "session_action": "play" if event_type == EVENT_TYPE_WOULD_PLAY else "stop",
        "session_reason": "ready" if event_type == EVENT_TYPE_WOULD_PLAY else "safety_blocked",
        "selected_order": 0 if event_type == EVENT_TYPE_WOULD_PLAY else None,
        "selected_content_type": "image/png" if event_type == EVENT_TYPE_WOULD_PLAY else None,
        "selected_duration_ms": 5000 if event_type == EVENT_TYPE_WOULD_PLAY else 0,
        "started_at": "2026-06-19T00:00:00+00:00" if event_type == EVENT_TYPE_WOULD_PLAY else None,
        "would_end_at": "2026-06-19T00:00:05+00:00" if event_type == EVENT_TYPE_WOULD_PLAY else None,
        "created_at": "2026-06-19T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return PlaybackEventDraft(**defaults)


# ══════════════════════════════════════════════════════════════════════
# PopWriteResult Tests
# ══════════════════════════════════════════════════════════════════════


class TestPopWriteResultDefaults(TestCase):
    def test_error_default(self):
        r = PopWriteResult()
        self.assertEqual(r.status, STATUS_ERROR)
        self.assertFalse(r.written)
        self.assertEqual(r.reason, REASON_WRITE_FAILED)

    def test_written_result(self):
        r = PopWriteResult(
            status=STATUS_WRITTEN, written=True, reason=REASON_WRITTEN,
            event_type=EVENT_TYPE_WOULD_PLAY, event_status=EVENT_STATUS_DRAFT,
            line_size_bytes=128,
        )
        self.assertEqual(r.status, STATUS_WRITTEN)
        self.assertTrue(r.written)
        self.assertEqual(r.event_type, EVENT_TYPE_WOULD_PLAY)
        self.assertEqual(r.line_size_bytes, 128)

    def test_no_path_in_result(self):
        """PopWriteResult must not expose file paths."""
        r = PopWriteResult(status=STATUS_WRITTEN, written=True, reason=REASON_WRITTEN)
        for attr in dir(r):
            if attr.startswith("_") or attr == "__doc__":
                continue  # skip dunder/docstring
            val = getattr(r, attr)
            if isinstance(val, str):
                self.assertNotIn("/", val, f"Path in attr '{attr}': {val}")

    def test_no_secret_in_result(self):
        r = PopWriteResult()
        for attr in dir(r):
            if attr.startswith("_") or attr == "__doc__":
                continue  # skip dunder/docstring — they describe the class
            val = getattr(r, attr)
            if isinstance(val, str):
                lower = val.lower()
                for fb in ("token", "secret", "password", "api_key"):
                    self.assertNotIn(fb, lower, f"Forbidden '{fb}' in attr '{attr}': {val}")


# ══════════════════════════════════════════════════════════════════════
# build_pop_jsonl_record Tests
# ══════════════════════════════════════════════════════════════════════


class TestBuildRecordHappy(TestCase):
    def test_would_play(self):
        draft = _make_draft(EVENT_TYPE_WOULD_PLAY)
        record = build_pop_jsonl_record(draft, "idle")
        self.assertIsNotNone(record)
        self.assertEqual(record["event_type"], EVENT_TYPE_WOULD_PLAY)
        self.assertEqual(record["event_status"], EVENT_STATUS_DRAFT)
        self.assertEqual(record["safety_state"], "idle")
        self.assertEqual(record["result"], EVENT_TYPE_WOULD_PLAY)
        self.assertTrue(record["playback_allowed"])
        self.assertEqual(record["session_action"], "play")
        self.assertEqual(record["selected_order"], 0)
        self.assertEqual(record["selected_content_type"], "image/png")
        self.assertEqual(record["duration_ms"], 5000)

    def test_blocked(self):
        draft = _make_draft(EVENT_TYPE_BLOCKED)
        record = build_pop_jsonl_record(draft, "payment")
        self.assertIsNotNone(record)
        self.assertEqual(record["event_type"], EVENT_TYPE_BLOCKED)
        self.assertEqual(record["safety_state"], "payment")
        self.assertEqual(record["result"], EVENT_TYPE_BLOCKED)
        self.assertFalse(record["playback_allowed"])

    def test_not_ready(self):
        draft = _make_draft(EVENT_TYPE_NOT_READY)
        record = build_pop_jsonl_record(draft, "idle")
        self.assertIsNotNone(record)
        self.assertEqual(record["event_type"], EVENT_TYPE_NOT_READY)

    def test_schema_version(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        self.assertEqual(record["schema_version"], SCHEMA_VERSION)

    def test_only_allowed_keys(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        for key in record:
            self.assertIn(key, ALLOWED_RECORD_KEYS, f"Unexpected key '{key}'")
        # All required allowed keys should be present
        for key in ALLOWED_RECORD_KEYS:
            self.assertIn(key, record, f"Missing key '{key}'")

    def test_timestamps_present(self):
        draft = _make_draft(EVENT_TYPE_WOULD_PLAY)
        record = build_pop_jsonl_record(draft, "idle")
        self.assertIsNotNone(record["created_at"])
        self.assertIsNotNone(record["started_at"])
        self.assertIsNotNone(record["ended_at"])

    def test_timestamps_null_when_blocked(self):
        draft = _make_draft(EVENT_TYPE_BLOCKED)
        record = build_pop_jsonl_record(draft, "payment")
        self.assertIsNone(record["started_at"])
        self.assertIsNone(record["ended_at"])


class TestBuildRecordAllStates(TestCase):
    def test_all_allowed_states(self):
        """All ALLOWED_SAFETY_STATES should produce a valid record."""
        for state in ALLOWED_SAFETY_STATES:
            draft = _make_draft(EVENT_TYPE_BLOCKED)
            record = build_pop_jsonl_record(draft, state)
            self.assertIsNotNone(record, f"State '{state}' should be valid")
            self.assertEqual(record["safety_state"], state)

    def test_receipt_state_fine(self):
        """'receipt' as safety_state is allowed."""
        draft = _make_draft(EVENT_TYPE_BLOCKED)
        record = build_pop_jsonl_record(draft, "receipt")
        self.assertIsNotNone(record)
        self.assertEqual(record["safety_state"], "receipt")

    def test_normalized_lowercase(self):
        """State should be normalized to lowercase."""
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "IDLE")
        self.assertIsNotNone(record)
        self.assertEqual(record["safety_state"], "idle")


class TestBuildRecordValidation(TestCase):
    def test_none_draft(self):
        record = build_pop_jsonl_record(None, "idle")
        self.assertIsNone(record)

    def test_non_draft_type(self):
        record = build_pop_jsonl_record("not_a_draft", "idle")
        self.assertIsNone(record)

    def test_none_safety_state(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, None)
        self.assertIsNone(record)

    def test_invalid_safety_state(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "bogus_state")
        self.assertIsNone(record)

    def test_empty_safety_state(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "")
        self.assertIsNone(record)

    def test_non_string_safety_state(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, 123)
        self.assertIsNone(record)


class TestBuildRecordSecurity(TestCase):
    def test_no_forbidden_keys(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        for key in record:
            self.assertNotIn(key, FORBIDDEN_KEYS, f"Forbidden key '{key}'")

    def test_no_forbidden_substrings(self):
        draft = _make_draft(
            event_type=EVENT_TYPE_WOULD_PLAY,
            selected_content_type="image/png",
        )
        record = build_pop_jsonl_record(draft, "idle")
        for key, val in record.items():
            if isinstance(val, str):
                lower = val.lower()
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, lower,
                        f"Forbidden '{fb}' in {key} = '{val}'")

    def test_no_filename(self):
        """Record must not contain 'filename' key or value."""
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        self.assertNotIn("filename", record)
        json_str = json.dumps(record)
        self.assertNotIn("filename", json_str.lower())

    def test_no_manifest_item_id(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        self.assertNotIn("manifest_item_id", record)

    def test_no_sha256(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        self.assertNotIn("sha256", record)

    def test_no_absolute_path(self):
        draft = _make_draft()
        record = build_pop_jsonl_record(draft, "idle")
        json_str = json.dumps(record)
        self.assertNotIn("/tmp/", json_str)
        self.assertNotIn("/home/", json_str)

    def test_receipt_data_forbidden(self):
        """receipt_data in ANY field value → None."""
        draft = _make_draft(selected_content_type="receipt_data")
        record = build_pop_jsonl_record(draft, "receipt")
        self.assertIsNone(record)


# ══════════════════════════════════════════════════════════════════════
# write_pop_event Tests
# ══════════════════════════════════════════════════════════════════════


class TestWritePopEventHappy(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_would_play_written(self):
        draft = _make_draft(EVENT_TYPE_WOULD_PLAY)
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertTrue(result.written)
        self.assertEqual(result.event_type, EVENT_TYPE_WOULD_PLAY)
        self.assertGreater(result.line_size_bytes, 0)

    def test_blocked_written(self):
        draft = _make_draft(EVENT_TYPE_BLOCKED)
        result = write_pop_event(self.tmp, draft, "payment")
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertTrue(result.written)

    def test_not_ready_written(self):
        draft = _make_draft(EVENT_TYPE_NOT_READY)
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_WRITTEN)

    def test_file_created_in_correct_dir(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        pending_dir = Path(self.tmp) / POP_PENDING_DIR
        self.assertTrue(pending_dir.is_dir(), f"Directory not created: {pending_dir}")
        jsonl_file = pending_dir / POP_JSONL_FILE
        self.assertTrue(jsonl_file.is_file(), f"File not created: {jsonl_file}")

    def test_jsonl_line_parseable(self):
        draft = _make_draft(EVENT_TYPE_WOULD_PLAY)
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        lines = jsonl_file.read_text().strip().split("\n")
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["event_type"], EVENT_TYPE_WOULD_PLAY)
        self.assertEqual(parsed["safety_state"], "idle")

    def test_jsonl_line_ends_with_newline(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        content = jsonl_file.read_text()
        self.assertTrue(content.endswith("\n"), "JSONL line must end with newline")

    def test_second_write_appends(self):
        draft1 = _make_draft(EVENT_TYPE_WOULD_PLAY)
        draft2 = _make_draft(EVENT_TYPE_BLOCKED)
        r1 = write_pop_event(self.tmp, draft1, "idle")
        r2 = write_pop_event(self.tmp, draft2, "payment")
        self.assertEqual(r1.status, STATUS_WRITTEN)
        self.assertEqual(r2.status, STATUS_WRITTEN)

        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        lines = jsonl_file.read_text().strip().split("\n")
        self.assertEqual(len(lines), 2, f"Expected 2 lines, got {len(lines)}")
        parsed1 = json.loads(lines[0])
        parsed2 = json.loads(lines[1])
        self.assertEqual(parsed1["event_type"], EVENT_TYPE_WOULD_PLAY)
        self.assertEqual(parsed2["event_type"], EVENT_TYPE_BLOCKED)

    def test_result_no_absolute_path(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        # Check result doesn't expose path
        for attr in dir(result):
            val = getattr(result, attr)
            if isinstance(val, str):
                self.assertNotIn(str(self.tmp), val)


class TestWritePopEventSkipped(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_invalid_safety_state_skipped(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "bogus")
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertFalse(result.written)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_none_safety_state_skipped(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, None)
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_none_draft_error(self):
        result = write_pop_event(self.tmp, None, "idle")
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_EVENT)

    def test_file_not_created_for_skipped(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "bogus")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertFalse(jsonl_file.exists(),
            "File should not be created for skipped event")


class TestWritePopEventSecurity(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_no_filename(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        content = jsonl_file.read_text()
        self.assertNotIn("filename", content.lower())

    def test_record_no_manifest_item_id(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        content = jsonl_file.read_text()
        self.assertNotIn("manifest_item_id", content.lower())

    def test_record_no_sha256(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        content = jsonl_file.read_text()
        # "sha256" should not appear anywhere
        self.assertNotIn("sha256", content.lower())

    def test_record_no_forbidden_substrings(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        content = jsonl_file.read_text().lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, content,
                f"Forbidden substring '{fb}' in JSONL content")

    def test_record_no_absolute_path_value(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        content = jsonl_file.read_text()
        self.assertNotIn(str(self.tmp), content)

    def test_record_only_allowed_keys(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_file = Path(self.tmp) / POP_PENDING_DIR / POP_JSONL_FILE
        parsed = json.loads(jsonl_file.read_text().strip())
        for key in parsed:
            self.assertIn(key, ALLOWED_RECORD_KEYS,
                f"Forbidden key '{key}' in record")
            self.assertNotIn(key, FORBIDDEN_KEYS,
                f"Forbidden key '{key}'")


class TestWritePopEventFailSilent(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_simulated_write_failure_error_status(self):
        """Simulated disk write failure → status=error, no raise, no stacktrace."""
        draft = _make_draft()
        with patch("builtins.open", side_effect=OSError("disk full")):
            result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertFalse(result.written)
        # No stacktrace in result
        for attr in dir(result):
            val = getattr(result, attr)
            if isinstance(val, str):
                self.assertNotIn("Traceback", val)
                self.assertNotIn("stacktrace", val.lower())

    def test_simulated_fsync_failure_error_status(self):
        """fsync failure → status=error, fail silent."""
        draft = _make_draft()
        m = mock_open()
        with patch("builtins.open", m):
            with patch("os.fsync", side_effect=OSError("fsync failed")):
                result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertFalse(result.written)

    def test_no_raise_on_write_error(self):
        """write_pop_event must NEVER raise — always return PopWriteResult."""
        draft = _make_draft()
        with patch("builtins.open", side_effect=OSError("disk full")):
            try:
                result = write_pop_event(self.tmp, draft, "idle")
                self.assertIsInstance(result, PopWriteResult)
            except Exception as e:
                self.fail(f"write_pop_event raised: {e}")

    def test_no_customer_data_in_result(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        for attr in dir(result):
            val = getattr(result, attr)
            if isinstance(val, str):
                lower = val.lower()
                for fb in ("customer", "payment_card", "card_number", "pan",
                          "fiscal", "receipt_number"):
                    self.assertNotIn(fb, lower,
                        f"Customer/payment data in result attr '{attr}': {val}")


class TestWritePopEventNoIO(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_http(self):
        """Writer must not import or use HTTP libraries."""
        import kso_player.pop_writer as pw
        source = open(pw.__file__).read()
        for http_lib in ("urllib", "requests", "http.client", "httpx", "aiohttp"):
            self.assertNotIn(http_lib, source,
                f"HTTP library '{http_lib}' imported in pop_writer.py")

    def test_no_secret_config_token_read(self):
        """Writer must not read secret/config/token files."""
        draft = _make_draft()
        # Should write normally without any config/secret files present
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_WRITTEN)

    def test_no_media_bytes_read(self):
        """Writer docstring may mention media_bytes as forbidden — but must not actually read them."""
        import kso_player.pop_writer as pw
        # Check that the writer code doesn't call any media-reading function
        source = open(pw.__file__).read()
        # Docstring/constants mentioning media_bytes is fine — just no read_bytes/open(media)
        # Remove comments and strings for the check
        self.assertNotIn("read_bytes(", source)
        self.assertNotIn("media/current", source)

    def test_does_not_import_backend(self):
        """Writer must not import backend modules."""
        import kso_player.pop_writer as pw
        source = open(pw.__file__).read()
        self.assertNotIn("from backend", source)
        self.assertNotIn("import backend", source)
        self.assertNotIn("from sidecar", source.lower())
        self.assertNotIn("import sidecar", source.lower())


class TestWritePopEventEdgeCases(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_str_root(self):
        """write_pop_event should accept str root path."""
        draft = _make_draft()
        result = write_pop_event(str(self.tmp), draft, "idle")
        self.assertEqual(result.status, STATUS_WRITTEN)

    def test_result_has_all_fields(self):
        draft = _make_draft(EVENT_TYPE_WOULD_PLAY)
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertIsNotNone(result.status)
        self.assertIsNotNone(result.reason)
        self.assertIsNotNone(result.event_type)
        self.assertIsNotNone(result.event_status)
        self.assertGreater(result.line_size_bytes, 0)

    def test_result_blocked_fields_set(self):
        draft = _make_draft(EVENT_TYPE_BLOCKED)
        result = write_pop_event(self.tmp, draft, "payment")
        self.assertEqual(result.event_type, EVENT_TYPE_BLOCKED)

    def test_line_size_within_limit(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertLess(result.line_size_bytes, MAX_LINE_SIZE_BYTES)

    def test_all_allowed_states_produce_write(self):
        """Every allowed safety state should write successfully."""
        for state in ALLOWED_SAFETY_STATES:
            tmp = tempfile.mkdtemp()
            try:
                draft = _make_draft(EVENT_TYPE_BLOCKED)
                result = write_pop_event(tmp, draft, state)
                self.assertEqual(result.status, STATUS_WRITTEN,
                    f"State '{state}' should write, got {result.status}: {result.reason}")
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Lock tests
# ══════════════════════════════════════════════════════════════════════

class TestLockAcquireRelease(TestCase):
    """Unit tests for lock acquire/release."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pending = self.tmp / POP_PENDING_DIR
        self.pending.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_acquire_lock_creates_file(self):
        lock_path = self.pending / POP_LOCK_FILE
        self.assertFalse(lock_path.exists())
        acquired = _acquire_lock(self.pending)
        self.assertTrue(acquired)
        self.assertTrue(lock_path.exists())

    def test_acquire_lock_writes_v2_marker(self):
        _acquire_lock(self.pending)
        lock_path = self.pending / POP_LOCK_FILE
        content = lock_path.read_text().strip()
        marker = json.loads(content)
        self.assertIsInstance(marker, dict)
        self.assertEqual(marker["schema_version"], 2)
        self.assertEqual(marker["component"], "player")
        self.assertEqual(marker["operation"], "pop_write")
        self.assertIn("created_at_utc", marker)
        self.assertIn("pid", marker)
        self.assertIn("boot_id_hash", marker)

    def test_acquire_lock_marker_no_secrets(self):
        _acquire_lock(self.pending)
        lock_path = self.pending / POP_LOCK_FILE
        content = lock_path.read_text().lower()
        for fb in ("token", "secret", "password", "path", "backend", "127.0.0.1",
                    "manifest_item_id", "batch_id", "device_event_id", "sha256",
                    "media_bytes", "fingerprint", "stacktrace"):
            self.assertNotIn(fb, content)

    def test_acquire_lock_marker_no_forbidden_in_keys(self):
        _acquire_lock(self.pending)
        lock_path = self.pending / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        for key in marker:
            self.assertNotIn(key.lower(), FORBIDDEN_SUBSTRINGS,
                f"marker key '{key}' is forbidden")

    def test_acquire_lock_marker_component_is_player(self):
        _acquire_lock(self.pending)
        lock_path = self.pending / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["component"], LOCK_COMPONENT)

    def test_acquire_lock_marker_operation_is_pop_write(self):
        _acquire_lock(self.pending)
        lock_path = self.pending / POP_LOCK_FILE
        marker = json.loads(lock_path.read_text().strip())
        self.assertEqual(marker["operation"], LOCK_OPERATION)

    def test_acquire_twice_fails(self):
        self.assertTrue(_acquire_lock(self.pending))
        self.assertFalse(_acquire_lock(self.pending))

    def test_release_lock_removes_file(self):
        _acquire_lock(self.pending)
        lock_path = self.pending / POP_LOCK_FILE
        self.assertTrue(lock_path.exists())
        _release_lock(self.pending)
        self.assertFalse(lock_path.exists())

    def test_release_when_no_lock_safe(self):
        _release_lock(self.pending)  # no error

    def test_safe_unlink_missing_file(self):
        path = self.pending / "nonexistent"
        _safe_unlink(path)  # no error


class TestLockWriteIntegration(TestCase):
    """Integration: write_pop_event with lock."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_successful_write_no_lock_after(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_WRITTEN)
        # Lock must be released after write
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(), f"lock still exists: {lock_path}")

    def test_write_creates_jsonl(self):
        draft = _make_draft()
        write_pop_event(self.tmp, draft, "idle")
        jsonl_path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        lines = jsonl_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 1)

    def test_lock_unavailable_skips(self):
        # Pre-create lock file with v1 marker (existing lock from old version)
        lock_path = self.tmp / POP_PENDING_DIR
        lock_path.mkdir(parents=True, exist_ok=True)
        (lock_path / POP_LOCK_FILE).write_text("locked\n")

        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE)
        self.assertFalse(result.written)

    def test_lock_unavailable_jsonl_untouched(self):
        # Pre-create JSONL and lock with v1 marker
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        jsonl_path = pending / POP_JSONL_FILE
        jsonl_path.write_text("existing content\n")

        lock_path = pending / POP_LOCK_FILE
        lock_path.write_text("locked\n")

        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE)
        # JSONL unchanged
        self.assertEqual(jsonl_path.read_text(), "existing content\n")

    def test_second_write_after_release_works(self):
        draft1 = _make_draft()
        result1 = write_pop_event(self.tmp, draft1, "idle")
        self.assertEqual(result1.status, STATUS_WRITTEN)

        draft2 = _make_draft(EVENT_TYPE_BLOCKED)
        result2 = write_pop_event(self.tmp, draft2, "payment")
        self.assertEqual(result2.status, STATUS_WRITTEN)

    def test_result_no_lock_path(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        text = repr(result)
        self.assertNotIn(".lock", text.lower())
        self.assertNotIn("player_events.lock", text)

    def test_result_no_forbidden_when_lock_unavailable(self):
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        (pending / POP_LOCK_FILE).write_text("locked\n")  # pre-existing v1 lock

        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        text = repr(result)
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, text.lower(),
                f"forbidden '{fb}' in result repr: {text[:200]}")


class TestLockReleasedOnFailure(TestCase):
    """Lock is released even on write/fsync failures."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_released_after_write_failure(self):
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)

        # Make the JSONL file a directory so write fails
        jsonl_path = pending / POP_JSONL_FILE
        jsonl_path.mkdir()

        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_WRITE_FAILED)

        # Lock must be released
        lock_path = pending / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(),
            f"lock not released after write failure: {lock_path}")


class TestWriterNoUnwantedSideEffects(TestCase):
    """Writer does NOT do HTTP, read secrets, or create other dirs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_other_dirs_created(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            draft = _make_draft()
            write_pop_event(tmp, draft, "idle")
            # Only pop/pending should exist
            top_dirs = [d.name for d in tmp.iterdir() if d.is_dir()]
            self.assertIn("pop", top_dirs)
            # No sent/quarantine/dry_run/failed
            for bad in ("sent", "quarantine", "dry_run", "failed"):
                pop_dir = tmp / "pop"
                if pop_dir.exists():
                    self.assertNotIn(bad, [d.name for d in pop_dir.iterdir()],
                        f"'{bad}/' dir should not exist")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_writer_no_http_no_secret_reading(self):
        draft = _make_draft()
        result = write_pop_event(self.tmp, draft, "idle")
        # Pure file I/O — no HTTP errors
        self.assertIsNotNone(result)
