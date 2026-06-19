"""Tests for KSO Sidecar PoP Sender Retry Runner Core.

Tests run_pop_send_with_retry() — send orchestration with retry decisions.
Uses FakeHttpClient — no real network, no backend, no secret reading.
"""

import unittest
from dataclasses import dataclass
from typing import Any, Optional

from kso_sidecar_agent.pop_sender import (
    SEND_OK, SEND_WARNING, SEND_ERROR,
    REASON_PROCESSED, REASON_NO_PAYLOAD, REASON_DUPLICATE_BATCH,
    REASON_BAD_REQUEST, REASON_FORBIDDEN, REASON_NOT_FOUND,
    REASON_VALIDATION_ERROR, REASON_SERVER_ERROR,
    REASON_NETWORK_ERROR, REASON_TIMEOUT,
    FORBIDDEN_IN_OUTPUT,
    PopSendResult,
)
from kso_sidecar_agent.pop_sender_retry import (
    RETRY_REASON_RETRY_EXHAUSTED,
)
from kso_sidecar_agent.pop_payload import PopPayloadEnvelope, PopPayloadEvent
from kso_sidecar_agent.pop_sender_runner import (
    RUN_OK, RUN_WARNING, RUN_ERROR,
    PopSendRunResult,
    run_pop_send_with_retry,
    format_pop_send_run_result,
)

# ══════════════════════════════════════════════════════════════════════
# Fake HTTP client (supports call-sequence responses)
# ══════════════════════════════════════════════════════════════════════

class FakeHttpError(Exception):
    def __init__(self, status_code=0, message="", retryable=False):
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


@dataclass
class FakeHttpResponse:
    status_code: int
    json_body: Any
    elapsed_ms: float = 10.0


class FakeHttpClient:
    """Fake SafeHttpClient — returns responses/errors from a queue."""

    def __init__(self, responses=None, errors=None):
        self._responses = list(responses) if responses else []
        self._errors = list(errors) if errors else []
        self.call_count = 0
        self.last_path = None
        self.last_payload = None
        self.last_headers = None

    def post_json(self, path, payload, headers=None):
        self.call_count += 1
        self.last_path = path
        self.last_payload = payload
        self.last_headers = headers

        # Errors take priority
        if self._errors:
            err = self._errors.pop(0)
            if err is not None:
                raise err

        # Responses
        if self._responses:
            resp = self._responses.pop(0)
            if resp is not None:
                return resp

        # Default: 200 success
        return FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": len(payload.get("events", []))}},
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_envelope(events_count=3):
    events = [PopPayloadEvent(
        device_event_id=f"dev-{i}",
        manifest_item_id=f"mi-{i}",
        manifest_version_id="mv-1",
        played_at="2026-06-19T10:00:00Z",
        duration_ms=15000,
        play_status="completed",
    ) for i in range(events_count)]
    return PopPayloadEnvelope(batch_id="b1", sent_at="2026-06-19T10:01:00Z", events=events)


def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            return False
    return True


def _fake_auth_callback(new_token="new-token-from-refresh"):
    """Return a closure that returns new_token."""
    def cb():
        return new_token
    return cb


def _failing_auth_callback():
    def cb():
        raise RuntimeError("auth service down")
    return cb


# ══════════════════════════════════════════════════════════════════════
# Tests: no_payload
# ══════════════════════════════════════════════════════════════════════

class TestRunnerNoPayload(unittest.TestCase):
    """No payload → no HTTP call."""

    def test_none_envelope(self):
        client = FakeHttpClient()
        result = run_pop_send_with_retry(client, None)
        self.assertEqual(result.run_status, RUN_WARNING)
        self.assertEqual(result.reason, REASON_NO_PAYLOAD)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.pending_should_remain)
        self.assertEqual(client.call_count, 0)  # no HTTP call for no_payload

    def test_empty_events(self):
        client = FakeHttpClient()
        envelope = PopPayloadEnvelope(batch_id="b1", events=[])
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.reason, REASON_NO_PAYLOAD)


class TestRunnerFirstAttemptSuccess(unittest.TestCase):
    """200 on first attempt → ok."""

    def test_200_first_attempt_ok(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.run_status, RUN_OK)
        self.assertEqual(result.final_send_status, SEND_OK)
        self.assertEqual(result.attempts_made, 1)
        self.assertFalse(result.pending_should_remain)
        self.assertEqual(result.accepted_events, 3)


class TestRunnerRetryThenSuccess(unittest.TestCase):
    """Retryable error → retry → success."""

    def test_500_then_200(self):
        client = FakeHttpClient(
            errors=[FakeHttpError(500, "Server Error", True)],
            responses=[FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}})],
        )
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.run_status, RUN_OK)
        self.assertEqual(result.attempts_made, 2)
        self.assertFalse(result.retry_exhausted)
        self.assertFalse(result.pending_should_remain)

    def test_429_then_200(self):
        client = FakeHttpClient(
            errors=[FakeHttpError(429, "Rate Limited", True)],
            responses=[FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}})],
        )
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.run_status, RUN_OK)
        self.assertEqual(result.attempts_made, 2)

    def test_network_then_200(self):
        client = FakeHttpClient(
            errors=[FakeHttpError(0, "Network error", True)],
            responses=[FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}})],
        )
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.run_status, RUN_OK)
        self.assertEqual(result.attempts_made, 2)

    def test_timeout_then_200(self):
        client = FakeHttpClient(
            errors=[FakeHttpError(0, "Connection failed: timeout", True)],
            responses=[FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}})],
        )
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.run_status, RUN_OK)
        self.assertEqual(result.attempts_made, 2)


class TestRunnerRetryExhausted(unittest.TestCase):
    """All attempts exhausted → error."""

    def test_500_all_attempts_exhausted(self):
        client = FakeHttpClient(errors=[
            FakeHttpError(500, "Server Error", True),
            FakeHttpError(500, "Server Error", True),
            FakeHttpError(500, "Server Error", True),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=3)
        self.assertEqual(result.run_status, RUN_ERROR)
        self.assertTrue(result.retry_exhausted)
        self.assertEqual(result.attempts_made, 3)
        self.assertTrue(result.pending_should_remain)
        self.assertEqual(result.reason, RETRY_REASON_RETRY_EXHAUSTED)

    def test_2_of_2_exhausted(self):
        client = FakeHttpClient(errors=[
            FakeHttpError(503, "Unavailable", True),
            FakeHttpError(503, "Unavailable", True),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=2)
        self.assertTrue(result.retry_exhausted)
        self.assertEqual(result.attempts_made, 2)


class TestRunnerAuthRefresh(unittest.TestCase):
    """401 → auth refresh → success or fail."""

    def test_401_refresh_then_200(self):
        client = FakeHttpClient(
            errors=[FakeHttpError(401, "Unauthorized", False)],
            responses=[FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}})],
        )
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope,
            access_token="old-token",
            refresh_auth_callback=_fake_auth_callback("new-jwt"),
            max_attempts=3,
        )
        self.assertEqual(result.run_status, RUN_OK)
        self.assertTrue(result.auth_refresh_attempted)
        self.assertEqual(result.attempts_made, 2)
        self.assertFalse(result.pending_should_remain)

    def test_401_no_callback_fails(self):
        client = FakeHttpClient(errors=[FakeHttpError(401, "Unauthorized", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope,
            access_token="old-token",
            refresh_auth_callback=None,
            max_attempts=3,
        )
        self.assertEqual(result.run_status, RUN_WARNING)
        self.assertTrue(result.auth_refresh_attempted)
        self.assertTrue(result.pending_should_remain)
        self.assertIn("auth_refresh", result.reason)

    def test_401_callback_returns_none_fails(self):
        client = FakeHttpClient(errors=[FakeHttpError(401, "Unauthorized", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope,
            access_token="old-token",
            refresh_auth_callback=lambda: None,
            max_attempts=3,
        )
        self.assertEqual(result.run_status, RUN_WARNING)
        self.assertTrue(result.auth_refresh_attempted)
        self.assertIn("auth_refresh", result.reason)

    def test_401_callback_throws_fails(self):
        client = FakeHttpClient(errors=[FakeHttpError(401, "Unauthorized", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope,
            access_token="old-token",
            refresh_auth_callback=_failing_auth_callback(),
            max_attempts=3,
        )
        self.assertEqual(result.run_status, RUN_WARNING)
        self.assertTrue(result.auth_refresh_attempted)
        self.assertIn("auth_refresh", result.reason)


class TestRunnerNonRetryable(unittest.TestCase):
    """Non-retryable errors → stop immediately."""

    def test_400_stop(self):
        client = FakeHttpClient(errors=[FakeHttpError(400, "Bad Request", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.pending_should_remain)
        self.assertFalse(result.retry_exhausted)

    def test_403_stop(self):
        client = FakeHttpClient(errors=[FakeHttpError(403, "Forbidden", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.pending_should_remain)

    def test_404_stop(self):
        client = FakeHttpClient(errors=[FakeHttpError(404, "Not Found", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.pending_should_remain)

    def test_422_stop(self):
        client = FakeHttpClient(errors=[FakeHttpError(422, "Unprocessable", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.pending_should_remain)


class TestRunner409DuplicateBatch(unittest.TestCase):
    """409 → stop, pending remains."""

    def test_409_stop(self):
        client = FakeHttpClient(errors=[FakeHttpError(409, "Conflict", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.pending_should_remain)
        self.assertFalse(result.retry_exhausted)

    def test_409_not_retried(self):
        client = FakeHttpClient(errors=[
            FakeHttpError(409, "Conflict", False),
            FakeHttpError(500, "Should not reach", True),  # should not be called
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=3)
        self.assertEqual(result.attempts_made, 1)


class TestRunnerMaxAttempts(unittest.TestCase):
    """Edge cases for max_attempts."""

    def test_max_attempts_zero_error(self):
        client = FakeHttpClient()
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=0)
        self.assertEqual(result.run_status, RUN_ERROR)
        self.assertEqual(result.reason, "invalid_args")

    def test_max_attempts_negative_error(self):
        client = FakeHttpClient()
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=-1)
        self.assertEqual(result.reason, "invalid_args")

    def test_max_attempts_1_no_retry(self):
        client = FakeHttpClient(errors=[FakeHttpError(500, "Server Error", True)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=1)
        self.assertEqual(result.attempts_made, 1)
        self.assertTrue(result.retry_exhausted)


class TestRunnerNoSleep(unittest.TestCase):
    """Runner does not sleep/wait."""

    def test_no_sleep_in_module(self):
        with open(__file__.replace("tests/test_pop_sender_runner.py", "kso_sidecar_agent/pop_sender_runner.py")) as f:
            content = f.read()
        self.assertNotIn("time.sleep", content)
        self.assertNotIn("sleep(", content)


class TestTokenNeverLeaked(unittest.TestCase):
    """token never appears in result/repr/output."""

    def test_token_not_in_result(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope, access_token="super-secret-jwt-abc123",
        )
        # PopSendRunResult has no token field
        self.assertFalse(hasattr(result, "token"))
        self.assertFalse(hasattr(result, "access_token"))

    def test_token_not_in_repr(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope, access_token="my-jwt",
        )
        text = repr(result)
        self.assertNotIn("my-jwt", text)
        self.assertNotIn("Bearer", text)

    def test_token_not_in_format(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope, access_token="abcdef12345",
        )
        text = format_pop_send_run_result(result)
        self.assertNotIn("abcdef12345", text)
        self.assertNotIn("Bearer", text)

    def test_callback_token_not_logged(self):
        callback_was_called_with_result = None

        def check_callback():
            return "refreshed-token-xyz"

        client = FakeHttpClient(
            errors=[FakeHttpError(401, "Unauthorized", False)],
            responses=[FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}})],
        )
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope,
            access_token="old-token",
            refresh_auth_callback=check_callback,
            max_attempts=3,
        )
        text = repr(result)
        self.assertNotIn("refreshed-token-xyz", text)
        self.assertNotIn("old-token", text)


class TestPayloadNeverLeaked(unittest.TestCase):
    """Payload/IDs never appear in safe output."""

    def test_format_no_payload(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        text = format_pop_send_run_result(result)
        self.assertNotIn("batch_id", text)
        self.assertNotIn("device_event_id", text)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("mi-", text)
        self.assertNotIn("dev-", text)

    def test_repr_no_payload(self):
        client = FakeHttpClient()
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        text = repr(result)
        self.assertNotIn("batch_id", text)
        self.assertNotIn("manifest_item_id", text)

    def test_format_no_campaign_id(self):
        client = FakeHttpClient()
        envelope = _make_envelope(1)
        result = run_pop_send_with_retry(client, envelope)
        text = format_pop_send_run_result(result)
        self.assertNotIn("campaign", text.lower())
        self.assertNotIn("creative", text.lower())


class TestSafeOutputNoForbidden(unittest.TestCase):
    """format output never contains forbidden substrings."""

    def test_format_ok_no_forbidden(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        text = format_pop_send_run_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_exhausted_no_forbidden(self):
        client = FakeHttpClient(errors=[
            FakeHttpError(500, "Err", True), FakeHttpError(500, "Err", True),
            FakeHttpError(500, "Err", True),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=3)
        text = format_pop_send_run_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_401_fail_no_forbidden(self):
        client = FakeHttpClient(errors=[FakeHttpError(401, "Unauthorized", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(
            client, envelope,
            access_token="x",
            refresh_auth_callback=lambda: None,
            max_attempts=3,
        )
        text = format_pop_send_run_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_409_no_forbidden(self):
        client = FakeHttpClient(errors=[FakeHttpError(409, "Conflict", False)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        text = format_pop_send_run_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_ok_no_forbidden(self):
        client = FakeHttpClient(responses=[
            FakeHttpResponse(200, {"status": "processed", "summary": {"accepted": 3}}),
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_exhausted_no_forbidden(self):
        client = FakeHttpClient(errors=[
            FakeHttpError(500, "Err", True)
        ])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=1)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))


class TestRunnerNoStacktrace(unittest.TestCase):
    """No stacktraces in output."""

    def test_no_stacktrace_in_format(self):
        client = FakeHttpClient(errors=[FakeHttpError(500, "Server Error", True)])
        envelope = _make_envelope(3)
        result = run_pop_send_with_retry(client, envelope, max_attempts=1)
        text = format_pop_send_run_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("stacktrace", text)


class TestRunnerNoFileOrSecretReading(unittest.TestCase):
    """Runner does NOT read secret/config/token files or move files."""

    def test_module_no_secret_imports(self):
        with open(__file__.replace("tests/test_pop_sender_runner.py", "kso_sidecar_agent/pop_sender_runner.py")) as f:
            content = f.read()
        self.assertNotIn("device_secret.dev", content)
        self.assertNotIn("secret_store", content)
        self.assertNotIn("local_config", content)
        self.assertNotIn("from pathlib import", content)

    def test_module_no_file_dirs(self):
        with open(__file__.replace("tests/test_pop_sender_runner.py", "kso_sidecar_agent/pop_sender_runner.py")) as f:
            content = f.read()
        self.assertNotIn("mkdir", content)
        self.assertNotIn("makedirs", content)
        self.assertNotIn("sent/", content)
        self.assertNotIn("quarantine", content)
        self.assertNotIn("dry_run", content)


class TestFormatOutputExpectedFields(unittest.TestCase):
    """format_pop_send_run_result contains all expected fields."""

    def test_format_contains_all_fields(self):
        result = PopSendRunResult(
            run_status=RUN_OK,
            attempts_made=1,
            reason="success",
            pending_should_remain=False,
        )
        text = format_pop_send_run_result(result)
        for field in [
            "run_status:", "final_send_status:", "attempts_made:", "max_attempts:",
            "auth_refresh_attempted:", "retry_exhausted:", "attempted_events:",
            "accepted_events:", "duplicate_events:", "rejected_events:",
            "pending_should_remain:", "reason:",
        ]:
            self.assertIn(field, text, f"Missing field '{field}'")


if __name__ == "__main__":
    unittest.main()
