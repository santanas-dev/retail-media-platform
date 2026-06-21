"""Tests for SafeStatusFileSource — file-based state source."""

import json as _json
import shutil
import tempfile
import unittest
from pathlib import Path

from kso_state_adapter.file_source import (
    SafeStatusFileSource,
    SafeStatusFileError,
    FileRejectedError,
    FileAccessError,
    MAX_FILE_SIZE_BYTES,
    DEFAULT_ALLOWED_ROOTS,
)
from kso_state_adapter.state_model import (
    STATE_IDLE,
    STATE_TRANSACTION,
    STATE_PAYMENT,
    STATE_RECEIPT,
    STATE_ERROR,
    STATE_UNKNOWN,
)


class TestSafeStatusFileSource(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_fs_"))
        self.file_path = self.tmp / "status.txt"
        # Allow this temp dir as a root
        self.source = SafeStatusFileSource(
            self.file_path,
            allowed_roots=[self.tmp],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content: str):
        self.file_path.write_text(content, encoding="utf-8")

    # ══════════════════════════════════════════════════════════════
    # Valid plain text
    # ══════════════════════════════════════════════════════════════

    def test_reads_plain_idle(self):
        self._write("idle")
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_IDLE)

    def test_reads_plain_transaction(self):
        self._write("transaction")
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_TRANSACTION)

    def test_reads_plain_payment(self):
        self._write("payment")
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_PAYMENT)

    def test_reads_plain_receipt(self):
        self._write("receipt")
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_RECEIPT)

    def test_reads_plain_unknown(self):
        self._write("unknown")
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_UNKNOWN)

    def test_reads_plain_error(self):
        self._write("error")
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_ERROR)

    # ══════════════════════════════════════════════════════════════
    # Valid JSON
    # ══════════════════════════════════════════════════════════════

    def test_reads_json_idle(self):
        self._write('{"state":"idle"}')
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_IDLE)

    def test_reads_json_transaction(self):
        self._write('{"state":"transaction"}')
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_TRANSACTION)

    def test_reads_json_with_whitespace(self):
        self._write('  {"state": "idle"}  ')
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_IDLE)

    def test_reads_json_with_allowed_extra_fields(self):
        self._write('{"state":"idle","updated_at_utc":"2026-01-01T00:00:00Z","source":"test"}')
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_IDLE)

    # ══════════════════════════════════════════════════════════════
    # Invalid states
    # ══════════════════════════════════════════════════════════════

    def test_rejects_invalid_plain_state(self):
        self._write("playing")
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_invalid_json_state(self):
        self._write('{"state":"playing"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_empty_file(self):
        self._write("")
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    # ══════════════════════════════════════════════════════════════
    # Missing / outside roots
    # ══════════════════════════════════════════════════════════════

    def test_rejects_missing_file(self):
        # Never created
        with self.assertRaises(FileAccessError):
            self.source.read_state()

    def test_rejects_outside_roots(self):
        outside = SafeStatusFileSource(
            Path("/etc/passwd"),
            allowed_roots=[self.tmp],
        )
        with self.assertRaises(FileAccessError):
            outside.read_state()

    # ══════════════════════════════════════════════════════════════
    # Size limit
    # ══════════════════════════════════════════════════════════════

    def test_rejects_oversized_file(self):
        self._write("x" * (MAX_FILE_SIZE_BYTES + 1))
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_accepts_file_at_size_limit(self):
        content = "x" * (MAX_FILE_SIZE_BYTES - 1)  # won't parse, but not rejected for size
        # JSON mode requires { ... }
        self._write('{"state":"idle"}' + " " * (MAX_FILE_SIZE_BYTES - 20))
        # Actually let's test with a valid JSON at limit
        self._write(" ")
        # Just make a 1023-byte padded JSON
        pad = " " * (MAX_FILE_SIZE_BYTES - len('{"state":"idle"}') - 1)
        self._write('{"state":"idle"}' + pad)
        state = self.source.read_state()
        self.assertEqual(state.state, STATE_IDLE)

    # ══════════════════════════════════════════════════════════════
    # Forbidden content
    # ══════════════════════════════════════════════════════════════

    def test_rejects_receipt_number(self):
        self._write('{"state":"idle","receipt_number":"123"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_card_number(self):
        self._write('{"state":"idle","card_number":"4111"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_customer_id(self):
        self._write('{"state":"idle","customer_id":"cust1"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_phone(self):
        self._write('{"state":"idle","phone":"+7900"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_email(self):
        self._write('{"state":"idle","email":"a@b.com"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_fiscal_data(self):
        self._write('{"state":"idle","fiscal_data":"fn:123"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_sku(self):
        self._write('{"state":"idle","sku":"ABC-123"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_amount(self):
        self._write('{"state":"idle","amount":"100"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_total(self):
        self._write('{"state":"idle","total":"500"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_token(self):
        self._write('{"state":"idle","token":"abc123"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_secret(self):
        self._write('{"state":"idle","secret":"xyz"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_password(self):
        self._write('{"state":"idle","password":"pass"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    # ══════════════════════════════════════════════════════════════
    # Extra keys in JSON
    # ══════════════════════════════════════════════════════════════

    def test_rejects_extra_json_keys(self):
        self._write('{"state":"idle","random_field":"value"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_deeply_nested_data(self):
        self._write('{"state":"idle","nested":{"key":"value"}}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    # ══════════════════════════════════════════════════════════════
    # Edge cases
    # ══════════════════════════════════════════════════════════════

    def test_rejects_plain_text_with_spaces(self):
        self._write("idle with spaces")
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_invalid_json(self):
        self._write("{not valid json")
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_json_array(self):
        self._write('["idle"]')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_missing_state_in_json(self):
        self._write('{"other":"value"}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_rejects_null_state_in_json(self):
        self._write('{"state":null}')
        with self.assertRaises(FileRejectedError):
            self.source.read_state()

    def test_call_count_increments(self):
        self._write("idle")
        self.assertEqual(self.source.call_count, 0)
        self.source.read_state()
        self.assertEqual(self.source.call_count, 1)
        self.source.read_state()
        self.assertEqual(self.source.call_count, 2)

    def test_exception_message_safe(self):
        """Exception messages must not contain forbidden strings."""
        self._write('{"state":"idle","card_number":"4111"}')
        try:
            self.source.read_state()
        except FileRejectedError as e:
            msg = str(e).lower()
            # Must not contain sensitive data from file
            self.assertNotIn("4111", msg)
            self.assertNotIn("receipt", msg)
            # But should mention the forbidden key
            self.assertIn("card_number", msg)

    def test_accepts_state_payment_as_technical(self):
        """State 'payment' is allowed as technical state, not PII."""
        self._write("payment")
        state = self.source.read_state()
        self.assertEqual(state.state, "payment")

    def test_default_allowed_roots(self):
        """Default allowed roots are /run/verny/kso and /var/lib/verny/kso."""
        self.assertEqual(len(DEFAULT_ALLOWED_ROOTS), 2)
        self.assertIn(Path("/run/verny/kso"), DEFAULT_ALLOWED_ROOTS)
        self.assertIn(Path("/var/lib/verny/kso"), DEFAULT_ALLOWED_ROOTS)


class TestFileSourceDaemonIntegration(unittest.TestCase):
    """Test SafeStatusFileSource with the daemon loop."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_fsd_"))
        self.status_file = self.tmp / "ukm4-safe-state.json"
        # Allow tmp as root for tests
        self.source = SafeStatusFileSource(
            self.status_file,
            allowed_roots=[self.tmp],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content: str):
        self.status_file.write_text(content, encoding="utf-8")

    def test_daemon_with_file_source_writes_idle(self):
        from kso_state_adapter.daemon import (
            run_kso_state_adapter_daemon,
            DAEMON_STATUS_STOPPED,
        )
        self._write("idle")
        result = run_kso_state_adapter_daemon(
            root=str(self.tmp / "root"),
            source=self.source,
            max_cycles=1,
            interval_seconds=0,
        )
        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertTrue(result.state_written)
        self.assertEqual(result.last_state, STATE_IDLE)

    def test_daemon_with_file_source_writes_transaction(self):
        from kso_state_adapter.daemon import (
            run_kso_state_adapter_daemon,
        )
        self._write("transaction")
        result = run_kso_state_adapter_daemon(
            root=str(self.tmp / "root"),
            source=self.source,
            max_cycles=1,
            interval_seconds=0,
        )
        self.assertTrue(result.state_written)
        self.assertEqual(result.last_state, STATE_TRANSACTION)

    def test_daemon_with_forbidden_file_writes_error(self):
        """Forbidden content → source raises → daemon writes error, NOT idle."""
        from kso_state_adapter.daemon import (
            run_kso_state_adapter_daemon,
        )
        self._write('{"state":"idle","card_number":"4111"}')
        result = run_kso_state_adapter_daemon(
            root=str(self.tmp / "root"),
            source=self.source,
            max_cycles=1,
            interval_seconds=0,
        )
        self.assertEqual(result.last_state, STATE_ERROR,
                         "Forbidden file must produce error state, never idle")

    def test_daemon_with_missing_file_writes_error(self):
        """Missing file → source raises → daemon writes error, NOT idle."""
        from kso_state_adapter.daemon import (
            run_kso_state_adapter_daemon,
        )
        # File never created
        result = run_kso_state_adapter_daemon(
            root=str(self.tmp / "root"),
            source=self.source,
            max_cycles=1,
            interval_seconds=0,
        )
        self.assertEqual(result.last_state, STATE_ERROR,
                         "Missing file must produce error state, never idle")


if __name__ == "__main__":
    unittest.main()
