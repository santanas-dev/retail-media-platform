"""Tests for KSO Sidecar PoP Sender Retry Decision Core.

Tests decide_pop_send_retry(), calculate_pop_retry_delay_ms(),
and format_pop_send_retry_decision().
Pure logic — no HTTP, no sleep, no backend, no file I/O.
"""

import unittest

from kso_sidecar_agent.pop_sender import (
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_PROCESSED,
    REASON_NO_PAYLOAD,
    REASON_UNAUTHORIZED,
    REASON_DUPLICATE_BATCH,
    REASON_BAD_REQUEST,
    REASON_FORBIDDEN,
    REASON_NOT_FOUND,
    REASON_VALIDATION_ERROR,
    REASON_RATE_LIMITED,
    REASON_SERVER_ERROR,
    REASON_NETWORK_ERROR,
    REASON_TIMEOUT,
    REASON_UNKNOWN_RESPONSE,
    FORBIDDEN_IN_OUTPUT,
    PopSendResult,
)
from kso_sidecar_agent.pop_sender_retry import (
    ACTION_STOP,
    ACTION_RETRY,
    ACTION_REFRESH_AUTH_THEN_RETRY,
    RETRY_REASON_SUCCESS,
    RETRY_REASON_NO_PAYLOAD,
    RETRY_REASON_AUTH_REFRESH_REQUIRED,
    RETRY_REASON_AUTH_REFRESH_FAILED,
    RETRY_REASON_RETRYABLE_ERROR,
    RETRY_REASON_RETRY_EXHAUSTED,
    RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS,
    RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS,
    RETRY_REASON_INVALID_ARGS,
    PopSendRetryDecision,
    decide_pop_send_retry,
    calculate_pop_retry_delay_ms,
    format_pop_send_retry_decision,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            return False
    return True


def _ok_result():
    return PopSendResult(
        send_status=SEND_OK,
        reason=REASON_PROCESSED,
        attempted_events=3,
        accepted_events=3,
        pending_should_remain=False,
    )


# ══════════════════════════════════════════════════════════════════════
# Tests: delay calculation
# ══════════════════════════════════════════════════════════════════════

class TestDelayCalculation(unittest.TestCase):
    """calculate_pop_retry_delay_ms tests."""

    def test_attempt_1_returns_base(self):
        self.assertEqual(calculate_pop_retry_delay_ms(1, base_delay_ms=1000), 1000)

    def test_attempt_2_doubles(self):
        self.assertEqual(calculate_pop_retry_delay_ms(2, base_delay_ms=1000), 2000)

    def test_attempt_3_doubles_again(self):
        self.assertEqual(calculate_pop_retry_delay_ms(3, base_delay_ms=1000), 4000)

    def test_attempt_4_capped(self):
        self.assertEqual(calculate_pop_retry_delay_ms(4, base_delay_ms=1000, max_delay_ms=5000), 5000)

    def test_max_delay_respected(self):
        delay = calculate_pop_retry_delay_ms(10, base_delay_ms=1000, max_delay_ms=30000)
        self.assertEqual(delay, 30000)

    def test_custom_base_delay(self):
        self.assertEqual(calculate_pop_retry_delay_ms(1, base_delay_ms=2000), 2000)
        self.assertEqual(calculate_pop_retry_delay_ms(2, base_delay_ms=2000), 4000)
        self.assertEqual(calculate_pop_retry_delay_ms(3, base_delay_ms=2000), 8000)

    def test_invalid_attempt_returns_0(self):
        self.assertEqual(calculate_pop_retry_delay_ms(0), 0)
        self.assertEqual(calculate_pop_retry_delay_ms(-1), 0)

    def test_invalid_base_returns_0(self):
        self.assertEqual(calculate_pop_retry_delay_ms(1, base_delay_ms=-100), 0)

    def test_invalid_max_returns_0(self):
        self.assertEqual(calculate_pop_retry_delay_ms(1, max_delay_ms=-100), 0)

    def test_non_int_types_return_0(self):
        self.assertEqual(calculate_pop_retry_delay_ms("1"), 0)
        self.assertEqual(calculate_pop_retry_delay_ms(1, base_delay_ms=None), 0)
        self.assertEqual(calculate_pop_retry_delay_ms(1, base_delay_ms="1000"), 0)


# ══════════════════════════════════════════════════════════════════════
# Tests: success → stop
# ══════════════════════════════════════════════════════════════════════

class TestSuccessStop(unittest.TestCase):
    """Success → stop."""

    def test_ok_result_stop(self):
        result = _ok_result()
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_SUCCESS)
        self.assertFalse(decision.retryable)
        self.assertFalse(decision.pending_should_remain)

    def test_ok_with_duplicate_events_stop(self):
        result = PopSendResult(
            send_status=SEND_OK,
            reason="duplicate_events",
            pending_should_remain=False,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertFalse(decision.pending_should_remain)

    def test_warning_with_pending_not_stop_for_success(self):
        # warning with pending → not in "success" branch
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_RETRY)  # retryable, not stop


# ══════════════════════════════════════════════════════════════════════
# Tests: no_payload → stop
# ══════════════════════════════════════════════════════════════════════

class TestNoPayload(unittest.TestCase):
    """no_payload → stop."""

    def test_no_payload_stop(self):
        result = PopSendResult(reason=REASON_NO_PAYLOAD, send_status=SEND_WARNING)
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_NO_PAYLOAD)
        self.assertTrue(decision.pending_should_remain)


# ══════════════════════════════════════════════════════════════════════
# Tests: auth refresh
# ══════════════════════════════════════════════════════════════════════

class TestAuthRefresh(unittest.TestCase):
    """401 → auth refresh."""

    def test_401_refresh_auth_then_retry(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_UNAUTHORIZED,
            retryable=True,
            auth_refresh_required=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertEqual(decision.action, ACTION_REFRESH_AUTH_THEN_RETRY)
        self.assertTrue(decision.auth_refresh_required)
        self.assertTrue(decision.retryable)
        self.assertEqual(decision.next_attempt_number, 2)
        self.assertEqual(decision.reason, RETRY_REASON_AUTH_REFRESH_REQUIRED)

    def test_401_after_refresh_attempted_stop(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_UNAUTHORIZED,
            retryable=True,
            auth_refresh_required=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(
            result, attempt_number=1, max_attempts=3,
            auth_refresh_attempted=True,
        )
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_AUTH_REFRESH_FAILED)
        self.assertTrue(decision.pending_should_remain)

    def test_401_no_attempts_left_no_refresh(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_UNAUTHORIZED,
            retryable=True,
            auth_refresh_required=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=3, max_attempts=3)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_RETRY_EXHAUSTED)


# ══════════════════════════════════════════════════════════════════════
# Tests: retry
# ══════════════════════════════════════════════════════════════════════

class TestRetry(unittest.TestCase):
    """Retryable errors → retry."""

    def test_429_retry(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_RATE_LIMITED,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertEqual(decision.action, ACTION_RETRY)
        self.assertEqual(decision.reason, RETRY_REASON_RETRYABLE_ERROR)
        self.assertEqual(decision.next_attempt_number, 2)
        self.assertEqual(decision.delay_ms, 1000)
        self.assertTrue(decision.pending_should_remain)

    def test_500_retry(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertEqual(decision.action, ACTION_RETRY)
        self.assertEqual(decision.delay_ms, 1000)

    def test_502_retry(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=2, max_attempts=3)
        self.assertEqual(decision.action, ACTION_RETRY)
        self.assertEqual(decision.next_attempt_number, 3)
        self.assertEqual(decision.delay_ms, 2000)  # attempt 2 → 2000

    def test_503_retry(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=5)
        self.assertEqual(decision.action, ACTION_RETRY)

    def test_network_error_retry(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_NETWORK_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertEqual(decision.action, ACTION_RETRY)
        self.assertEqual(decision.delay_ms, 1000)

    def test_timeout_retry(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_TIMEOUT,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertEqual(decision.action, ACTION_RETRY)


class TestRetryExhausted(unittest.TestCase):
    """Retryable but exhausted → stop."""

    def test_retry_exhausted_last_attempt(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=3, max_attempts=3)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_RETRY_EXHAUSTED)
        self.assertTrue(decision.pending_should_remain)
        self.assertIsNone(decision.next_attempt_number)

    def test_retry_exhausted_beyond_max(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=5, max_attempts=3)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_RETRY_EXHAUSTED)

    def test_retry_exhausted_429(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_RATE_LIMITED,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=2, max_attempts=2)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_RETRY_EXHAUSTED)


# ══════════════════════════════════════════════════════════════════════
# Tests: non-retryable → stop
# ══════════════════════════════════════════════════════════════════════

class TestNonRetryableStop(unittest.TestCase):
    """Non-retryable errors → stop."""

    def test_400_stop(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_BAD_REQUEST,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS)

    def test_403_stop(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_FORBIDDEN,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)

    def test_404_stop(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_NOT_FOUND,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)

    def test_422_stop(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_VALIDATION_ERROR,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)


# ══════════════════════════════════════════════════════════════════════
# Tests: 409 duplicate_batch → stop
# ══════════════════════════════════════════════════════════════════════

class Test409DuplicateBatch(unittest.TestCase):
    """409 duplicate_batch → stop, pending remains."""

    def test_409_stop(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_DUPLICATE_BATCH,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS)
        self.assertTrue(decision.pending_should_remain)

    def test_409_not_overridden_by_retryable(self):
        # Even if someone misconfigured retryable=true, 409 takes priority
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_DUPLICATE_BATCH,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid args
# ══════════════════════════════════════════════════════════════════════

class TestInvalidArgs(unittest.TestCase):
    """Invalid inputs → safe stop."""

    def test_none_result(self):
        decision = decide_pop_send_retry(None)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, RETRY_REASON_INVALID_ARGS)

    def test_invalid_attempt_number(self):
        decision = decide_pop_send_retry(_ok_result(), attempt_number=0)
        self.assertEqual(decision.reason, RETRY_REASON_INVALID_ARGS)

    def test_invalid_max_attempts(self):
        decision = decide_pop_send_retry(_ok_result(), max_attempts=0)
        self.assertEqual(decision.reason, RETRY_REASON_INVALID_ARGS)

    def test_string_result(self):
        decision = decide_pop_send_retry("not_a_result")
        self.assertEqual(decision.action, ACTION_STOP)


# ══════════════════════════════════════════════════════════════════════
# Tests: safe output
# ══════════════════════════════════════════════════════════════════════

class TestSafeFormatOutput(unittest.TestCase):
    """format_pop_send_retry_decision safety."""

    def test_format_retry_no_forbidden(self):
        decision = PopSendRetryDecision(
            action=ACTION_RETRY,
            retryable=True,
            next_attempt_number=2,
            delay_ms=1000,
            reason=RETRY_REASON_RETRYABLE_ERROR,
        )
        text = format_pop_send_retry_decision(decision)
        self.assertTrue(_no_forbidden(text))

    def test_format_stop_no_forbidden(self):
        decision = PopSendRetryDecision(
            action=ACTION_STOP,
            reason=RETRY_REASON_SUCCESS,
            pending_should_remain=False,
        )
        text = format_pop_send_retry_decision(decision)
        self.assertTrue(_no_forbidden(text))

    def test_format_refresh_auth_no_forbidden(self):
        decision = PopSendRetryDecision(
            action=ACTION_REFRESH_AUTH_THEN_RETRY,
            retryable=True,
            auth_refresh_required=True,
            next_attempt_number=2,
            reason=RETRY_REASON_AUTH_REFRESH_REQUIRED,
        )
        text = format_pop_send_retry_decision(decision)
        self.assertTrue(_no_forbidden(text))

    def test_format_all_reasons_safe(self):
        for reason in [
            RETRY_REASON_SUCCESS,
            RETRY_REASON_NO_PAYLOAD,
            RETRY_REASON_RETRYABLE_ERROR,
            RETRY_REASON_RETRY_EXHAUSTED,
            RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS,
            RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS,
            RETRY_REASON_AUTH_REFRESH_REQUIRED,
            RETRY_REASON_AUTH_REFRESH_FAILED,
        ]:
            decision = PopSendRetryDecision(reason=reason)
            text = format_pop_send_retry_decision(decision)
            self.assertTrue(_no_forbidden(text), f"reason={reason}: {text}")

    def test_format_contains_expected_fields(self):
        decision = PopSendRetryDecision(
            action=ACTION_RETRY,
            retryable=True,
            next_attempt_number=2,
            delay_ms=1000,
            reason=RETRY_REASON_RETRYABLE_ERROR,
        )
        text = format_pop_send_retry_decision(decision)
        self.assertIn("retry_action:", text)
        self.assertIn("retryable:", text)
        self.assertIn("auth_refresh_required:", text)
        self.assertIn("pending_should_remain:", text)
        self.assertIn("next_attempt_number:", text)
        self.assertIn("delay_ms:", text)
        self.assertIn("reason:", text)
        self.assertIn("retry", text)
        self.assertIn("1000", text)

    def test_format_no_ids_urls(self):
        decision = PopSendRetryDecision(
            action=ACTION_RETRY,
            reason=RETRY_REASON_RETRYABLE_ERROR,
            next_attempt_number=2,
            delay_ms=1000,
        )
        text = format_pop_send_retry_decision(decision)
        self.assertNotIn("batch_id", text)
        self.assertNotIn("device_event_id", text)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("backend_base_url", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)


class TestReprSafety(unittest.TestCase):
    """PopSendRetryDecision repr safety."""

    def test_repr_no_forbidden(self):
        decision = PopSendRetryDecision(
            action=ACTION_RETRY,
            retryable=True,
            reason=RETRY_REASON_RETRYABLE_ERROR,
            next_attempt_number=2,
            delay_ms=1000,
        )
        text = repr(decision)
        self.assertTrue(_no_forbidden(text))

    def test_repr_all_reasons_safe(self):
        for reason in [
            RETRY_REASON_SUCCESS,
            RETRY_REASON_NO_PAYLOAD,
            RETRY_REASON_RETRYABLE_ERROR,
            RETRY_REASON_RETRY_EXHAUSTED,
            RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS,
            RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS,
            RETRY_REASON_AUTH_REFRESH_REQUIRED,
            RETRY_REASON_AUTH_REFRESH_FAILED,
        ]:
            decision = PopSendRetryDecision(reason=reason)
            text = repr(decision)
            self.assertTrue(_no_forbidden(text), f"reason={reason}: {text}")


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects (no HTTP, no files, no sleep)
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(unittest.TestCase):
    """Functions do not make HTTP calls, read files, or sleep."""

    def test_decide_no_side_effects(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        # Call many times — no exceptions, no side effects
        for i in range(5):
            decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
            self.assertIsNotNone(decision)

    def test_module_no_http_imports(self):
        with open(__file__.replace("tests/test_pop_sender_retry.py", "kso_sidecar_agent/pop_sender_retry.py")) as f:
            content = f.read()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import socket", content)
        self.assertNotIn("import http.", content)
        self.assertNotIn("import requests", content)
        self.assertNotIn("from pathlib import", content)
        self.assertNotIn("time.sleep", content)
        self.assertNotIn("open(", content)


class TestPendingShouldRemain(unittest.TestCase):
    """pending_should_remain is True for all non-success cases."""

    def test_retry_pending_true(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=1, max_attempts=3)
        self.assertTrue(decision.pending_should_remain)

    def test_exhausted_pending_true(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_SERVER_ERROR,
            retryable=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, attempt_number=3, max_attempts=3)
        self.assertTrue(decision.pending_should_remain)

    def test_non_retryable_pending_true(self):
        result = PopSendResult(
            send_status=SEND_ERROR,
            reason=REASON_BAD_REQUEST,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertTrue(decision.pending_should_remain)

    def test_409_pending_true(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_DUPLICATE_BATCH,
            retryable=False,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result)
        self.assertTrue(decision.pending_should_remain)

    def test_auth_failed_pending_true(self):
        result = PopSendResult(
            send_status=SEND_WARNING,
            reason=REASON_UNAUTHORIZED,
            retryable=True,
            auth_refresh_required=True,
            pending_should_remain=True,
        )
        decision = decide_pop_send_retry(result, auth_refresh_attempted=True)
        self.assertTrue(decision.pending_should_remain)

    def test_success_pending_false(self):
        result = _ok_result()
        decision = decide_pop_send_retry(result)
        self.assertFalse(decision.pending_should_remain)


if __name__ == "__main__":
    unittest.main()
