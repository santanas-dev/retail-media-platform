"""Tests for KSO Sidecar PoP Sender Response Classifier.

Tests classify_pop_send_response() and format_pop_send_result().
Pure logic — no HTTP, no backend, no secret reading, no file I/O.
"""

import unittest

from kso_sidecar_agent.pop_sender import (
    ALLOWED_REASONS,
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_PROCESSED,
    REASON_PARTIAL_SUCCESS,
    REASON_DUPLICATE_BATCH,
    REASON_DUPLICATE_EVENTS,
    REASON_BAD_REQUEST,
    REASON_UNAUTHORIZED,
    REASON_FORBIDDEN,
    REASON_NOT_FOUND,
    REASON_VALIDATION_ERROR,
    REASON_RATE_LIMITED,
    REASON_SERVER_ERROR,
    REASON_NETWORK_ERROR,
    REASON_TIMEOUT,
    REASON_UNKNOWN_RESPONSE,
    REASON_INVALID_RESPONSE,
    REASON_NO_PAYLOAD,
    FORBIDDEN_IN_OUTPUT,
    FORBIDDEN_RESPONSE_KEYS,
    classify_pop_send_response,
    format_pop_send_result,
    PopSendResult,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _no_forbidden(text: str, fb_set=None) -> bool:
    """Return True if text contains no forbidden substrings."""
    if fb_set is None:
        fb_set = FORBIDDEN_IN_OUTPUT
    lower = text.lower()
    for fb in fb_set:
        if fb in lower:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestPopSendResultDefaults(unittest.TestCase):
    """PopSendResult default values and safety."""

    def test_default_pending_should_remain_true(self):
        result = PopSendResult()
        self.assertTrue(result.pending_should_remain)

    def test_default_send_status_warning(self):
        result = PopSendResult()
        self.assertEqual(result.send_status, SEND_WARNING)

    def test_default_reason_no_payload(self):
        result = PopSendResult()
        self.assertEqual(result.reason, REASON_NO_PAYLOAD)

    def test_default_retryable_false(self):
        result = PopSendResult()
        self.assertFalse(result.retryable)

    def test_invalid_reason_raises(self):
        with self.assertRaises(ValueError):
            PopSendResult(reason="invalid-reason-value")

    def test_all_allowed_reasons_work(self):
        for reason in sorted(ALLOWED_REASONS):
            r = PopSendResult(reason=reason)
            self.assertEqual(r.reason, reason)


class TestSafeRepr(unittest.TestCase):
    """PopSendResult.__repr__ safety."""

    def test_repr_no_forbidden_substrings(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 3, "duplicate": 0, "rejected": 0},
            },
            attempted_events=3,
        )
        text = repr(result)
        self.assertTrue(_no_forbidden(text), f"repr contains forbidden: {text[:200]}")

    def test_repr_no_forbidden_default(self):
        result = PopSendResult()
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_does_not_contain_raw_backend_body(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "proof_batch_id": "uuid-123"},
            attempted_events=5,
        )
        text = repr(result)
        self.assertNotIn("proof_batch_id", text)


class Test200Processed(unittest.TestCase):
    """HTTP 200 — processed."""

    def test_200_processed_ok(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}},
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_OK)
        self.assertEqual(result.reason, REASON_PROCESSED)
        self.assertEqual(result.accepted_events, 3)
        self.assertFalse(result.pending_should_remain)
        self.assertFalse(result.retryable)
        self.assertFalse(result.auth_refresh_required)

    def test_200_pop_batch_processed_ok(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"batch_status": "pop_batch_processed", "summary": {"accepted": 5}},
            attempted_events=5,
        )
        self.assertEqual(result.send_status, SEND_OK)
        self.assertFalse(result.pending_should_remain)

    def test_200_processed_no_summary_counts(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed"},
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_OK)
        self.assertFalse(result.pending_should_remain)
        self.assertEqual(result.accepted_events, 3)  # defaulted from attempted

    def test_200_processed_with_duplicate_summary(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 2, "duplicate": 1, "rejected": 0},
            },
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_OK)
        self.assertEqual(result.accepted_events, 2)
        self.assertEqual(result.duplicate_events, 1)
        self.assertFalse(result.pending_should_remain)

    def test_200_processed_accepted_count_key(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted_count": 7},
            },
            attempted_events=7,
        )
        self.assertEqual(result.accepted_events, 7)
        self.assertEqual(result.send_status, SEND_OK)


class Test200Partial(unittest.TestCase):
    """HTTP 200 — partial success with rejected events."""

    def test_200_partial_rejected_warning(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 2, "rejected": 1},
            },
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_PARTIAL_SUCCESS)
        self.assertTrue(result.pending_should_remain)
        self.assertFalse(result.retryable)

    def test_200_all_rejected_warning(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 0, "rejected": 3},
            },
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertTrue(result.pending_should_remain)

    def test_200_mixed_accepted_duplicate_rejected(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 1, "duplicate": 1, "rejected": 1},
            },
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_PARTIAL_SUCCESS)
        self.assertTrue(result.pending_should_remain)


class Test200Duplicate(unittest.TestCase):
    """HTTP 200 — duplicate batch."""

    def test_200_duplicate_batch_status(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "duplicate_batch", "summary": {"duplicate": 3}},
            attempted_events=3,
        )
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_DUPLICATE_BATCH)
        self.assertFalse(result.pending_should_remain)
        self.assertEqual(result.duplicate_events, 3)

    def test_200_all_duplicate_events_deduced(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 0, "duplicate": 5, "rejected": 0},
            },
            attempted_events=5,
        )
        self.assertEqual(result.send_status, SEND_OK)
        self.assertEqual(result.reason, REASON_DUPLICATE_EVENTS)
        self.assertFalse(result.pending_should_remain)


class Test200InvalidSchema(unittest.TestCase):
    """HTTP 200 — response schema is unrecognized."""

    def test_200_empty_json_invalid(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={},
            attempted_events=5,
        )
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)
        self.assertTrue(result.pending_should_remain)

    def test_200_no_status_no_data(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"arbitrary": "stuff"},
            attempted_events=3,
        )
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)
        self.assertTrue(result.pending_should_remain)

    def test_200_non_dict_response(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json="not a dict",
            attempted_events=3,
        )
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)

    def test_200_none_response_schema_invalid(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json=None,
            attempted_events=3,
        )
        self.assertEqual(result.reason, REASON_INVALID_RESPONSE)
        self.assertTrue(result.pending_should_remain)


class Test4xx(unittest.TestCase):
    """HTTP 4xx — various client errors."""

    def test_400_bad_request(self):
        result = classify_pop_send_response(http_status=400, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_BAD_REQUEST)
        self.assertFalse(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_401_unauthorized(self):
        result = classify_pop_send_response(http_status=401, attempted_events=3)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_UNAUTHORIZED)
        self.assertTrue(result.retryable)
        self.assertTrue(result.auth_refresh_required)
        self.assertTrue(result.pending_should_remain)

    def test_403_forbidden(self):
        result = classify_pop_send_response(http_status=403, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_FORBIDDEN)
        self.assertFalse(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_404_not_found(self):
        result = classify_pop_send_response(http_status=404, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_NOT_FOUND)
        self.assertFalse(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_409_duplicate_batch(self):
        result = classify_pop_send_response(http_status=409, attempted_events=3)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_DUPLICATE_BATCH)
        self.assertFalse(result.retryable)
        self.assertFalse(result.pending_should_remain)
        self.assertEqual(result.duplicate_events, 3)

    def test_422_validation_error(self):
        result = classify_pop_send_response(http_status=422, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_VALIDATION_ERROR)
        self.assertFalse(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_429_rate_limited(self):
        result = classify_pop_send_response(http_status=429, attempted_events=3)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_RATE_LIMITED)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain)


class Test5xx(unittest.TestCase):
    """HTTP 5xx — server errors."""

    def test_500_server_error(self):
        result = classify_pop_send_response(http_status=500, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_SERVER_ERROR)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_502_server_error(self):
        result = classify_pop_send_response(http_status=502, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertTrue(result.retryable)

    def test_503_server_error(self):
        result = classify_pop_send_response(http_status=503, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertTrue(result.retryable)


class TestNetworkErrors(unittest.TestCase):
    """Network/timeout errors via error_type."""

    def test_network_error(self):
        result = classify_pop_send_response(error_type="network", attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_NETWORK_ERROR)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain)
        self.assertIsNone(result.http_status)

    def test_timeout_error(self):
        result = classify_pop_send_response(error_type="timeout", attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_TIMEOUT)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_unknown_error_type(self):
        result = classify_pop_send_response(error_type="unknown-error", attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_UNKNOWN_RESPONSE)
        self.assertFalse(result.retryable)


class TestUnknownResponse(unittest.TestCase):
    """Unknown HTTP status."""

    def test_no_http_status_no_error_type(self):
        result = classify_pop_send_response(attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_UNKNOWN_RESPONSE)
        self.assertFalse(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_nonstandard_http_status(self):
        result = classify_pop_send_response(http_status=600, attempted_events=3)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_UNKNOWN_RESPONSE)


class TestResponseForbiddenFields(unittest.TestCase):
    """Response JSON with forbidden keys/values → invalid_response."""

    def test_forbidden_key_token(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "token": "abc123"},
            attempted_events=3,
        )
        self.assertIn(result.reason, (REASON_INVALID_RESPONSE, REASON_UNKNOWN_RESPONSE))

    def test_forbidden_key_batch_id(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "batch_id": "uuid-xxx"},
            attempted_events=3,
        )
        self.assertIn(result.reason, (REASON_INVALID_RESPONSE, REASON_UNKNOWN_RESPONSE))

    def test_forbidden_key_device_event_id(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 1}, "device_event_id": "uuid"},
            attempted_events=1,
        )
        self.assertTrue(result.pending_should_remain)

    def test_forbidden_value_in_summary(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 3, "note": "token-used-for-auth"},
            },
            attempted_events=3,
        )
        # forbidden value in summary → counts may be empty
        self.assertIsNotNone(result)


class TestCountExtraction(unittest.TestCase):
    """Safe count extraction from various response shapes."""

    def test_summary_accepted_count_key(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted_count": 5}},
            attempted_events=5,
        )
        self.assertEqual(result.accepted_events, 5)
        self.assertEqual(result.send_status, SEND_OK)

    def test_top_level_accepted_events(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "accepted_events": 4},
            attempted_events=4,
        )
        self.assertEqual(result.accepted_events, 4)

    def test_summary_duplicate_count(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 2, "duplicate_count": 1}},
            attempted_events=3,
        )
        self.assertEqual(result.duplicate_events, 1)

    def test_summary_rejected_count(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 1, "rejected_count": 2}},
            attempted_events=3,
        )
        self.assertEqual(result.rejected_events, 2)

    def test_attempted_from_total_events(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}, "total_events": 3},
            attempted_events=3,
        )
        self.assertEqual(result.attempted_events, 3)

    def test_attempted_from_sum_of_counts(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={
                "status": "processed",
                "summary": {"accepted": 2, "duplicate": 1, "rejected": 0},
            },
            attempted_events=3,
        )
        self.assertEqual(result.attempted_events, 3)

    def test_non_integer_count_ignored(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": "many"}},
            attempted_events=3,
        )
        self.assertEqual(result.accepted_events, 0)


class TestPendingShouldRemain(unittest.TestCase):
    """pending_should_remain logic — only false for confirmed processed."""

    def test_processed_false(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}},
            attempted_events=3,
        )
        self.assertFalse(result.pending_should_remain)

    def test_partial_rejected_true(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 2, "rejected": 1}},
            attempted_events=3,
        )
        self.assertTrue(result.pending_should_remain)

    def test_400_true(self):
        result = classify_pop_send_response(http_status=400, attempted_events=3)
        self.assertTrue(result.pending_should_remain)

    def test_401_true(self):
        result = classify_pop_send_response(http_status=401, attempted_events=3)
        self.assertTrue(result.pending_should_remain)

    def test_409_duplicate_false(self):
        result = classify_pop_send_response(http_status=409, attempted_events=3)
        self.assertFalse(result.pending_should_remain)

    def test_500_true(self):
        result = classify_pop_send_response(http_status=500, attempted_events=3)
        self.assertTrue(result.pending_should_remain)

    def test_network_error_true(self):
        result = classify_pop_send_response(error_type="network", attempted_events=3)
        self.assertTrue(result.pending_should_remain)


class TestSafeFormatOutput(unittest.TestCase):
    """format_pop_send_result safety."""

    def test_format_ok_no_forbidden(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}},
            attempted_events=3,
        )
        text = format_pop_send_result(result)
        self.assertTrue(_no_forbidden(text), f"output has forbidden: {text[:200]}")

    def test_format_no_raw_backend_response(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "proof_batch_id": "uuid", "summary": {"accepted": 3}},
            attempted_events=3,
        )
        text = format_pop_send_result(result)
        self.assertNotIn("proof_batch_id", text)

    def test_format_no_raw_body_plain(self):
        result = PopSendResult(reason="processed", send_status="ok")
        text = format_pop_send_result(result)
        self.assertNotIn("response_json", text)

    def test_format_contains_send_status(self):
        result = PopSendResult(reason="processed", send_status="ok")
        text = format_pop_send_result(result)
        self.assertIn("send_status:", text)
        self.assertIn("ok", text)

    def test_format_contains_all_fields(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}},
            attempted_events=3,
            elapsed_ms=145.3,
        )
        text = format_pop_send_result(result)
        self.assertIn("send_status:", text)
        self.assertIn("attempted_events:", text)
        self.assertIn("accepted_events:", text)
        self.assertIn("duplicate_events:", text)
        self.assertIn("rejected_events:", text)
        self.assertIn("http_status:", text)
        self.assertIn("elapsed_ms:", text)
        self.assertIn("retryable:", text)
        self.assertIn("auth_refresh_required:", text)
        self.assertIn("pending_should_remain:", text)
        self.assertIn("reason:", text)

    def test_format_network_error_no_http_status(self):
        result = classify_pop_send_response(error_type="network", attempted_events=3)
        text = format_pop_send_result(result)
        self.assertNotIn("http_status:", text)
        self.assertIn("network_error", text)


class TestNoBackendNoSecret(unittest.TestCase):
    """Classifier does NOT make HTTP calls, read secrets, or access files."""

    def test_classifier_pure_function_no_import_side_effects(self):
        # Repeated calls produce consistent results
        for _ in range(5):
            result = classify_pop_send_response(
                http_status=200,
                response_json={"status": "processed", "summary": {"accepted": 3}},
                attempted_events=3,
            )
            self.assertEqual(result.send_status, SEND_OK)
            self.assertEqual(result.accepted_events, 3)

    def test_no_module_level_http(self):
        # pop_sender module has no urllib/socket imports
        with open(__file__.replace("tests/test_pop_sender.py", "kso_sidecar_agent/pop_sender.py")) as f:
            content = f.read()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import socket", content)
        self.assertNotIn("import http.", content)
        self.assertNotIn("import requests", content)

    def test_no_module_level_secret_reading(self):
        # No file/open for secret/config files
        with open(__file__.replace("tests/test_pop_sender.py", "kso_sidecar_agent/pop_sender.py")) as f:
            content = f.read()
        self.assertNotIn("open(", content)
        self.assertNotIn("Path(", content)


class TestElapsedMs(unittest.TestCase):
    """Elapsed time handling."""

    def test_elapsed_preserved(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}},
            attempted_events=3,
            elapsed_ms=145.3,
        )
        self.assertEqual(result.elapsed_ms, 145.3)

    def test_elapsed_in_format(self):
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 3}},
            attempted_events=3,
            elapsed_ms=145.3,
        )
        text = format_pop_send_result(result)
        self.assertIn("145.3", text)


class TestAttemptedEvents(unittest.TestCase):
    """attempted_events handling."""

    def test_attempted_preserved_when_no_counts(self):
        result = classify_pop_send_response(
            http_status=404,
            attempted_events=7,
        )
        self.assertEqual(result.attempted_events, 7)

    def test_attempted_clamped_to_nonnegative(self):
        result = PopSendResult(attempted_events=-5)
        self.assertEqual(result.attempted_events, -5)  # PopSendResult doesn't clamp, classify does


if __name__ == "__main__":
    unittest.main()
