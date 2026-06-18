"""Tests for RetryBackoffManager — no network, no real sleep, no secrets."""

import unittest
from http.client import HTTPException

from kso_sidecar_agent.http_client import HttpClientError
from kso_sidecar_agent.retry_backoff import (
    BackoffPolicy,
    RetryBackoffManager,
    RetryDecision,
    execute_with_retries,
    _redact_reason,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _fixed_random(value: float):
    """Return a callable that always returns the same value."""
    def _fn():
        return value
    return _fn


# ══════════════════════════════════════════════════════════════════════
# BackoffPolicy validation
# ══════════════════════════════════════════════════════════════════════

class TestBackoffPolicy(unittest.TestCase):

    def test_defaults_valid(self):
        p = BackoffPolicy()
        self.assertEqual(p.max_attempts, 3)
        self.assertEqual(p.base_delay_sec, 2.0)
        self.assertEqual(p.max_delay_sec, 60.0)
        self.assertEqual(p.multiplier, 2.0)
        self.assertEqual(p.jitter_ratio, 0.25)

    def test_max_attempts_out_of_range_rejected(self):
        for bad in (0, -1, 11, 100):
            with self.subTest(max_attempts=bad):
                with self.assertRaises(ValueError):
                    BackoffPolicy(max_attempts=bad)

    def test_max_attempts_not_int_rejected(self):
        with self.assertRaises(ValueError):
            BackoffPolicy(max_attempts=1.5)  # type: ignore

    def test_base_delay_zero_rejected(self):
        for bad in (0, -1):
            with self.subTest(base_delay_sec=bad):
                with self.assertRaises(ValueError):
                    BackoffPolicy(base_delay_sec=bad)

    def test_max_delay_less_than_base_rejected(self):
        with self.assertRaises(ValueError):
            BackoffPolicy(base_delay_sec=5.0, max_delay_sec=3.0)

    def test_multiplier_below_one_rejected(self):
        with self.assertRaises(ValueError):
            BackoffPolicy(multiplier=0.9)

    def test_jitter_out_of_range_rejected(self):
        for bad in (-0.1, 1.1, 2.0):
            with self.subTest(jitter_ratio=bad):
                with self.assertRaises(ValueError):
                    BackoffPolicy(jitter_ratio=bad)


# ══════════════════════════════════════════════════════════════════════
# Delay computation
# ══════════════════════════════════════════════════════════════════════

class TestComputeDelay(unittest.TestCase):

    def setUp(self):
        self.policy = BackoffPolicy(
            max_attempts=5,
            base_delay_sec=2.0,
            max_delay_sec=60.0,
            multiplier=2.0,
            jitter_ratio=0.0,  # zero jitter for exact testing
        )
        self.mgr = RetryBackoffManager(self.policy)

    def test_delay_grows_exponentially(self):
        # attempt 1 → delay for next attempt (2) = 2.0 * 2^1 = 4.0
        self.assertAlmostEqual(self.mgr.compute_delay(2), 4.0)
        # attempt 2 → delay for next attempt (3) = 2.0 * 2^2 = 8.0
        self.assertAlmostEqual(self.mgr.compute_delay(3), 8.0)
        # attempt 3 → delay for next attempt (4) = 2.0 * 2^3 = 16.0
        self.assertAlmostEqual(self.mgr.compute_delay(4), 16.0)

    def test_delay_first_attempt(self):
        # attempt 1 → delay = 2.0 * 2^0 = 2.0
        self.assertAlmostEqual(self.mgr.compute_delay(1), 2.0)

    def test_delay_clamped_to_max(self):
        policy = BackoffPolicy(
            base_delay_sec=10.0,
            max_delay_sec=15.0,
            multiplier=2.0,
            jitter_ratio=0.0,
        )
        mgr = RetryBackoffManager(policy)
        # attempt 2 → 10 * 2^1 = 20 → clamped to 15
        self.assertAlmostEqual(mgr.compute_delay(2), 15.0)

    def test_delay_with_quarter_jitter(self):
        """With jitter_ratio=0.25 and delay=4.0, jitter range is ±1.0."""
        policy = BackoffPolicy(
            base_delay_sec=2.0,
            multiplier=2.0,
            jitter_ratio=0.25,
        )
        # random=0.0 → jitter = -0.25*4 = -1.0 → delay 3.0
        mgr_min = RetryBackoffManager(policy, random_fn=_fixed_random(0.0))
        self.assertAlmostEqual(mgr_min.compute_delay(2), 3.0)

        # random=1.0 → jitter = +0.25*4 = +1.0 → delay 5.0
        mgr_max = RetryBackoffManager(policy, random_fn=_fixed_random(1.0))
        self.assertAlmostEqual(mgr_max.compute_delay(2), 5.0)

        # random=0.5 → jitter = 0 → delay 4.0
        mgr_mid = RetryBackoffManager(policy, random_fn=_fixed_random(0.5))
        self.assertAlmostEqual(mgr_mid.compute_delay(2), 4.0)

    def test_jitter_stays_in_bounds(self):
        """Run 500 random samples, verify all are within expected range."""
        policy = BackoffPolicy(base_delay_sec=2.0, multiplier=2.0, jitter_ratio=0.25)
        mgr = RetryBackoffManager(policy)
        for _ in range(500):
            delay = mgr.compute_delay(2)
            # base=2.0*2^1=4.0, jitter range ±1.0 → [3.0, 5.0]
            self.assertGreaterEqual(delay, 3.0, f"delay {delay} below 3.0")
            self.assertLessEqual(delay, 5.0, f"delay {delay} above 5.0")

    def test_delay_not_negative(self):
        """With extreme jitter, delay should never go negative."""
        policy = BackoffPolicy(base_delay_sec=0.01, multiplier=1.0, jitter_ratio=1.0)
        # random=0.0 → jitter = -1.0 * 0.01 = -0.01 → delay 0.0 (clamped)
        mgr = RetryBackoffManager(policy, random_fn=_fixed_random(0.0))
        delay = mgr.compute_delay(1)
        self.assertGreaterEqual(delay, 0.0)

    def test_invalid_attempt_rejected(self):
        for bad in (0, -1):
            with self.subTest(attempt=bad):
                with self.assertRaises(ValueError):
                    self.mgr.compute_delay(bad)


# ══════════════════════════════════════════════════════════════════════
# Error classification
# ══════════════════════════════════════════════════════════════════════

class TestClassifyError(unittest.TestCase):

    def setUp(self):
        self.mgr = RetryBackoffManager(BackoffPolicy())

    # ── HttpClientError cases ──────────────────────────────────────

    def test_429_retryable(self):
        retryable, reason = self.mgr.classify_error(
            HttpClientError(status_code=429, message="Rate limited", retryable=True)
        )
        self.assertTrue(retryable)
        self.assertIn("Rate limited", reason)

    def test_500_retryable(self):
        retryable, reason = self.mgr.classify_error(
            HttpClientError(status_code=500, message="Server error", retryable=True)
        )
        self.assertTrue(retryable)

    def test_401_non_retryable(self):
        retryable, reason = self.mgr.classify_error(
            HttpClientError(status_code=401, message="Unauthorized", retryable=False)
        )
        self.assertFalse(retryable)

    def test_403_non_retryable(self):
        retryable, reason = self.mgr.classify_error(
            HttpClientError(status_code=403, message="Forbidden", retryable=False)
        )
        self.assertFalse(retryable)

    def test_422_non_retryable(self):
        retryable, reason = self.mgr.classify_error(
            HttpClientError(status_code=422, message="Validation error", retryable=False)
        )
        self.assertFalse(retryable)

    # ── Built-in exceptions ────────────────────────────────────────

    def test_timeout_error_retryable(self):
        retryable, reason = self.mgr.classify_error(TimeoutError("Connection timed out"))
        self.assertTrue(retryable)

    def test_connection_error_retryable(self):
        retryable, reason = self.mgr.classify_error(ConnectionError("Connection refused"))
        self.assertTrue(retryable)

    def test_os_error_retryable(self):
        retryable, reason = self.mgr.classify_error(OSError("Network unreachable"))
        self.assertTrue(retryable)

    def test_value_error_non_retryable(self):
        retryable, reason = self.mgr.classify_error(ValueError("Invalid config"))
        self.assertFalse(retryable)

    def test_runtime_error_non_retryable(self):
        retryable, reason = self.mgr.classify_error(RuntimeError("Secret missing"))
        self.assertFalse(retryable)


# ══════════════════════════════════════════════════════════════════════
# next_decision
# ══════════════════════════════════════════════════════════════════════

class TestNextDecision(unittest.TestCase):

    def setUp(self):
        self.policy = BackoffPolicy(max_attempts=3, jitter_ratio=0.0)
        self.mgr = RetryBackoffManager(self.policy)

    def test_retryable_first_attempt(self):
        err = HttpClientError(status_code=500, message="oops", retryable=True)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertTrue(dec.retryable)
        self.assertTrue(dec.should_retry)
        self.assertGreater(dec.delay_sec, 0)

    def test_retryable_last_attempt_no_retry(self):
        """On the last attempt (attempt == max_attempts), should_retry is False."""
        err = HttpClientError(status_code=500, message="oops", retryable=True)
        dec = self.mgr.next_decision(attempt=3, error=err)
        self.assertTrue(dec.retryable)
        self.assertFalse(dec.should_retry)
        self.assertEqual(dec.delay_sec, 0.0)

    def test_non_retryable_no_retry(self):
        err = HttpClientError(status_code=401, message="bad", retryable=False)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertFalse(dec.retryable)
        self.assertFalse(dec.should_retry)
        self.assertEqual(dec.delay_sec, 0.0)

    def test_attempt_count_reflected(self):
        err = HttpClientError(status_code=500, message="oops", retryable=True)
        dec = self.mgr.next_decision(attempt=2, error=err)
        self.assertEqual(dec.attempt, 2)
        self.assertEqual(dec.max_attempts, 3)

    def test_beyond_max_attempts(self):
        """attempt > max_attempts should still produce a valid decision (no retry)."""
        err = HttpClientError(status_code=500, message="oops", retryable=True)
        dec = self.mgr.next_decision(attempt=5, error=err)
        self.assertTrue(dec.retryable)
        self.assertFalse(dec.should_retry)


# ══════════════════════════════════════════════════════════════════════
# Security: forbidden substrings in reason
# ══════════════════════════════════════════════════════════════════════

class TestReasonSafety(unittest.TestCase):

    def setUp(self):
        self.mgr = RetryBackoffManager(BackoffPolicy())

    def test_token_redacted(self):
        err = HttpClientError(status_code=500, message="Invalid token abc123", retryable=True)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertNotIn("token", dec.reason.lower(), f"Reason contains 'token': {dec.reason}")
        self.assertIn("[REDACTED]", dec.reason)

    def test_secret_redacted(self):
        err = HttpClientError(status_code=500, message="Wrong secret provided", retryable=True)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertNotIn("secret", dec.reason.lower())

    def test_access_token_redacted(self):
        err = HttpClientError(status_code=401, message="access_token expired", retryable=False)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertNotIn("access_token", dec.reason.lower())

    def test_jwt_redacted(self):
        err = HttpClientError(status_code=401, message="jwt is invalid", retryable=False)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertNotIn("jwt", dec.reason.lower())

    def test_api_key_redacted(self):
        err = HttpClientError(status_code=403, message="api_key missing", retryable=False)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertNotIn("api_key", dec.reason.lower())

    def test_device_secret_redacted(self):
        err = HttpClientError(status_code=401, message="device_secret mismatch", retryable=False)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertNotIn("device_secret", dec.reason.lower())

    def test_clean_reason_preserved(self):
        err = HttpClientError(status_code=500, message="Internal server error", retryable=True)
        dec = self.mgr.next_decision(attempt=1, error=err)
        self.assertIn("Internal server error", dec.reason)
        self.assertNotIn("[REDACTED]", dec.reason)

    def test_repr_no_forbidden(self):
        err = HttpClientError(status_code=500, message="token revoked", retryable=True)
        dec = self.mgr.next_decision(attempt=1, error=err)
        r = repr(dec)
        self.assertNotIn("token", r.lower(), f"repr contains forbidden: {r}")

    def test_str_no_forbidden(self):
        err = HttpClientError(status_code=500, message="secret expired", retryable=True)
        dec = self.mgr.next_decision(attempt=1, error=err)
        s = str(dec)
        self.assertNotIn("secret", s.lower(), f"str contains forbidden: {s}")


# ══════════════════════════════════════════════════════════════════════
# _redact_reason helper
# ══════════════════════════════════════════════════════════════════════

class TestRedactReason(unittest.TestCase):

    def test_single_forbidden(self):
        self.assertEqual(_redact_reason("invalid token"), "invalid [REDACTED]")

    def test_multiple_forbidden(self):
        result = _redact_reason("token and secret mismatch")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("token", result.lower())
        self.assertNotIn("secret", result.lower())

    def test_clean_text(self):
        self.assertEqual(_redact_reason("Connection timed out"), "Connection timed out")

    def test_case_insensitive(self):
        self.assertNotIn("TOKEN", _redact_reason("TOKEN is bad").lower())
        self.assertNotIn("Secret", _redact_reason("Secret missing"))


# ══════════════════════════════════════════════════════════════════════
# execute_with_retries
# ══════════════════════════════════════════════════════════════════════

class TestExecuteWithRetries(unittest.TestCase):

    def setUp(self):
        self.slept = []  # track sleep calls

    def _fake_sleep(self, sec):
        self.slept.append(sec)

    def test_success_on_first_try(self):
        calls = []
        def succeed():
            calls.append(1)
            return "ok"

        mgr = RetryBackoffManager(BackoffPolicy(max_attempts=3, jitter_ratio=0.0))
        result = execute_with_retries(succeed, mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(result, "ok")
        self.assertEqual(calls, [1])
        self.assertEqual(self.slept, [])

    def test_retry_then_succeed(self):
        call_count = [0]
        def fail_then_ok():
            call_count[0] += 1
            if call_count[0] < 2:
                raise HttpClientError(status_code=500, message="oops", retryable=True)
            return "recovered"

        mgr = RetryBackoffManager(BackoffPolicy(max_attempts=3, jitter_ratio=0.0))
        result = execute_with_retries(fail_then_ok, mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(result, "recovered")
        self.assertEqual(call_count[0], 2)
        self.assertEqual(len(self.slept), 1)

    def test_non_retryable_stops_immediately(self):
        call_count = [0]
        def fail():
            call_count[0] += 1
            raise HttpClientError(status_code=401, message="bad", retryable=False)

        mgr = RetryBackoffManager(BackoffPolicy(max_attempts=3))
        with self.assertRaises(HttpClientError):
            execute_with_retries(fail, mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(call_count[0], 1)
        self.assertEqual(self.slept, [])

    def test_exhaust_retries(self):
        call_count = [0]
        def always_fail():
            call_count[0] += 1
            raise HttpClientError(status_code=500, message="oops", retryable=True)

        mgr = RetryBackoffManager(BackoffPolicy(max_attempts=3, jitter_ratio=0.0))
        with self.assertRaises(HttpClientError):
            execute_with_retries(always_fail, mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(call_count[0], 3)
        self.assertEqual(len(self.slept), 2)  # slept between attempt 1→2 and 2→3

    def test_no_sleep_on_default(self):
        """Default sleep_fn is time.sleep — we verify the helper doesn't crash."""
        call_count = [0]
        def succeed():
            call_count[0] += 1
            return "direct"

        mgr = RetryBackoffManager(BackoffPolicy(max_attempts=2))
        result = execute_with_retries(succeed, mgr)
        self.assertEqual(result, "direct")


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
