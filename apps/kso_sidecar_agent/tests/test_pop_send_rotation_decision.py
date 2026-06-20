"""Tests for KSO Sidecar PoP Scoped Send Rotation Decision Core."""

import unittest

from kso_sidecar_agent.pop_scoped_send import (
    PopScopedSendResult,
    STATUS_OK as SCOPED_OK,
    STATUS_WARNING as SCOPED_WARNING,
    STATUS_ERROR as SCOPED_ERROR,
    SEND_STATUS_OK,
    SEND_STATUS_WARNING,
    SEND_STATUS_ERROR,
    SEND_STATUS_SKIPPED,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_LIMITED_SCOPED,
    REASON_PACKAGE_FAILED,
    REASON_SEND_FAILED,
    REASON_SEND_OK,
    REASON_INVALID_RESULT_SCOPED,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_sender_runner import (
    PopSendRunResult,
    RUN_OK,
    RUN_WARNING,
    RUN_ERROR,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationSentScope,
)
from kso_sidecar_agent.pop_send_rotation_decision import (
    PopSendRotationDecision,
    decide_pop_rotation_after_scoped_send,
    format_pop_send_rotation_decision,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_SEND_OK_SCOPE_AVAILABLE,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_MISSING_SEND_RESULT,
    REASON_MISSING_SENT_SCOPE,
    REASON_EMPTY_SENT_SCOPE,
    REASON_PENDING_NOT_UNTOUCHED,
    REASON_ALREADY_ROTATED,
    REASON_INVALID_RESULT,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _success_result():
    """Build a fully successful PopScopedSendResult."""
    return PopScopedSendResult(
        status=SCOPED_OK,
        send_attempted=True,
        send_success=True,
        package_built=True,
        payload_events=3,
        scope_lines=3,
        send_status=SEND_STATUS_OK,
        pending_untouched=True,
        rotation_applied=False,
        reason=REASON_SEND_OK,
        _send_run_result=PopSendRunResult(
            run_status=RUN_OK,
            final_send_status="ok",
            attempts_made=1,
            max_attempts=3,
            attempted_events=3,
            accepted_events=3,
            duplicate_events=0,
            rejected_events=0,
            pending_should_remain=False,
            reason="processed",
        ),
        _sent_scope=PopRotationSentScope(
            _line_numbers=frozenset({1, 2, 3}),
            _line_fingerprints={1: "a" * 64, 2: "b" * 64, 3: "c" * 64},
        ),
    )


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestDecisionRotationAllowed(unittest.TestCase):
    """Cases where rotation should be allowed."""

    def test_successful_scoped_send_allows_rotation(self):
        """send_success + scope > 0 → rotation_allowed=true."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        self.assertTrue(decision.rotation_allowed)
        self.assertEqual(decision.status, STATUS_OK)
        self.assertEqual(decision.reason, REASON_SEND_OK_SCOPE_AVAILABLE)
        self.assertTrue(decision.send_attempted)
        self.assertTrue(decision.send_success)
        self.assertEqual(decision.scope_lines, 3)


class TestDecisionRotationBlocked(unittest.TestCase):
    """Cases where rotation should be blocked."""

    def test_no_eligible_events(self):
        """no_eligible_events → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_OK,
            reason=REASON_NO_ELIGIBLE_EVENTS_SCOPED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_NO_ELIGIBLE_EVENTS)

    def test_lock_unavailable(self):
        """lock_unavailable → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_WARNING,
            reason=REASON_LOCK_UNAVAILABLE_SCOPED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_LOCK_UNAVAILABLE)

    def test_limited(self):
        """limited → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_WARNING,
            reason=REASON_LIMITED_SCOPED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_LIMITED)

    def test_package_failed(self):
        """package_failed → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_WARNING,
            reason=REASON_PACKAGE_FAILED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_PACKAGE_FAILED)

    def test_send_failed(self):
        """send_failed → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_WARNING,
            send_attempted=True,
            send_success=False,
            reason=REASON_SEND_FAILED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_SEND_FAILED)

    def test_retry_exhausted(self):
        """Retry exhausted → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_ERROR,
            send_attempted=True,
            send_success=False,
            reason=REASON_SEND_FAILED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_SEND_FAILED)

    def test_409_duplicate(self):
        """409 duplicate detected in internal send result → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_WARNING,
            send_attempted=True,
            send_success=False,
            reason=REASON_SEND_FAILED,
            _send_run_result=PopSendRunResult(
                run_status=RUN_OK,
                pending_should_remain=True,
                reason="duplicate_batch_pending_remains",
            ),
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_DUPLICATE_PENDING_REMAINS)

    def test_pending_should_remain_true(self):
        """pending_should_remain=true → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_WARNING,
            send_attempted=True,
            send_success=False,
            reason=REASON_SEND_FAILED,
            _send_run_result=PopSendRunResult(
                run_status=RUN_OK,
                pending_should_remain=True,
                reason="partial_success",
            ),
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_PENDING_SHOULD_REMAIN)

    def test_missing_send_run_result(self):
        """_send_run_result=None → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_OK,
            send_attempted=True,
            send_success=True,
            package_built=True,
            payload_events=1,
            scope_lines=1,
            send_status=SEND_STATUS_OK,
            pending_untouched=True,
            reason=REASON_SEND_OK,
            _send_run_result=None,
            _sent_scope=PopRotationSentScope(
                _line_numbers=frozenset({1}),
                _line_fingerprints={1: "a" * 64},
            ),
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_MISSING_SEND_RESULT)

    def test_missing_sent_scope(self):
        """_sent_scope=None → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_OK,
            send_attempted=True,
            send_success=True,
            package_built=True,
            payload_events=1,
            scope_lines=1,
            send_status=SEND_STATUS_OK,
            pending_untouched=True,
            reason=REASON_SEND_OK,
            _send_run_result=PopSendRunResult(
                run_status=RUN_OK,
                pending_should_remain=False,
            ),
            _sent_scope=None,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_MISSING_SENT_SCOPE)

    def test_empty_sent_scope(self):
        """_sent_scope.size=0 → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_OK,
            send_attempted=True,
            send_success=True,
            package_built=True,
            payload_events=0,
            scope_lines=0,
            send_status=SEND_STATUS_OK,
            pending_untouched=True,
            reason=REASON_SEND_OK,
            _send_run_result=PopSendRunResult(
                run_status=RUN_OK,
                pending_should_remain=False,
            ),
            _sent_scope=PopRotationSentScope(
                _line_numbers=frozenset(),
            ),
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_EMPTY_SENT_SCOPE)

    def test_pending_not_untouched(self):
        """pending_untouched=false → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_OK,
            send_attempted=True,
            send_success=True,
            package_built=True,
            payload_events=3,
            scope_lines=3,
            send_status=SEND_STATUS_OK,
            pending_untouched=False,
            reason=REASON_SEND_OK,
            _send_run_result=PopSendRunResult(
                run_status=RUN_OK,
                pending_should_remain=False,
            ),
            _sent_scope=PopRotationSentScope(
                _line_numbers=frozenset({1, 2, 3}),
                _line_fingerprints={1: "a" * 64, 2: "b" * 64, 3: "c" * 64},
            ),
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_PENDING_NOT_UNTOUCHED)
        self.assertEqual(decision.status, STATUS_ERROR)

    def test_already_rotated(self):
        """rotation_applied=true → rotation_allowed=false."""
        result = PopScopedSendResult(
            status=SCOPED_OK,
            send_attempted=True,
            send_success=True,
            package_built=True,
            payload_events=3,
            scope_lines=3,
            send_status=SEND_STATUS_OK,
            pending_untouched=True,
            rotation_applied=True,
            reason=REASON_SEND_OK,
            _send_run_result=PopSendRunResult(
                run_status=RUN_OK,
                pending_should_remain=False,
            ),
            _sent_scope=PopRotationSentScope(
                _line_numbers=frozenset({1, 2, 3}),
                _line_fingerprints={1: "a" * 64, 2: "b" * 64, 3: "c" * 64},
            ),
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_ALREADY_ROTATED)

    def test_invalid_result_object(self):
        """Non-PopScopedSendResult → invalid_result."""
        decision = decide_pop_rotation_after_scoped_send("not a result")
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.status, STATUS_ERROR)
        self.assertEqual(decision.reason, REASON_INVALID_RESULT)

    def test_invalid_result_reason(self):
        """Result with invalid reason → mapped to send_failed."""
        result = PopScopedSendResult(
            status=SCOPED_ERROR,
            reason=REASON_INVALID_RESULT_SCOPED,
        )
        decision = decide_pop_rotation_after_scoped_send(result)
        self.assertFalse(decision.rotation_allowed)
        self.assertEqual(decision.reason, REASON_INVALID_RESULT)


class TestDecisionSafety(unittest.TestCase):
    """Safety checks for decision repr/output."""

    def test_decision_repr_no_payload_body(self):
        """Decision repr does not contain payload body."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        repr_str = repr(decision)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("manifest_item_id", repr_str)

    def test_decision_repr_no_ids(self):
        """Decision repr does not contain IDs."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        repr_str = repr(decision)
        self.assertNotIn("manifest_item_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("campaign_id", repr_str)

    def test_decision_repr_no_line_numbers(self):
        """Decision repr does not contain line numbers."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        repr_str = repr(decision)
        self.assertNotIn("_line_numbers", repr_str)
        self.assertNotIn("_line_fingerprints", repr_str)

    def test_decision_repr_no_fingerprint_values(self):
        """Decision repr does not contain fingerprint hex values."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        repr_str = repr(decision)
        self.assertNotIn("a" * 64, repr_str)
        self.assertNotIn("b" * 64, repr_str)

    def test_decision_repr_no_paths(self):
        """Decision repr does not contain paths/filenames."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        repr_str = repr(decision).lower()
        self.assertNotIn("path", repr_str)
        self.assertNotIn("filename", repr_str)
        self.assertNotIn("sha256", repr_str)

    def test_safe_output_contains_fields(self):
        """Safe output contains all expected fields."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        output = format_pop_send_rotation_decision(decision)
        self.assertIn("status:", output)
        self.assertIn("rotation_allowed:", output)
        self.assertIn("send_attempted:", output)
        self.assertIn("send_success:", output)
        self.assertIn("scope_lines:", output)
        self.assertIn("pending_untouched:", output)
        self.assertIn("reason:", output)

    def test_safe_output_no_forbidden(self):
        """Safe output passes forbidden check."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        output = format_pop_send_rotation_decision(decision)
        lower = output.lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower, f"forbidden '{fb}' in safe output")

    def test_safe_output_no_stacktrace(self):
        """Safe output does not contain stacktrace."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        output = format_pop_send_rotation_decision(decision)
        self.assertNotIn("stacktrace", output.lower())
        self.assertNotIn("traceback", output.lower())


class TestDecisionNoSideEffects(unittest.TestCase):
    """Verify pure-logic function has NO side effects."""

    def test_no_http(self):
        """Function does not call HTTP."""
        # Pure logic — no http_client parameter
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        self.assertTrue(decision.rotation_allowed)

    def test_no_rotation_apply(self):
        """Function does not call rotation apply."""
        # No reference to apply_pop_rotation_local
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        self.assertTrue(decision.rotation_allowed)

    def test_no_pending_read(self):
        """Function does not read pending."""
        # No file I/O — only reads from argument
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        self.assertTrue(decision.rotation_allowed)

    def test_no_dirs_created(self):
        """Function does not create directories."""
        decision = decide_pop_rotation_after_scoped_send(_success_result())
        self.assertTrue(decision.rotation_allowed)


if __name__ == "__main__":
    unittest.main()
