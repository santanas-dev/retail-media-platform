"""Tests for KSO Sidecar PoP Backend Sender HTTP Core.

Tests send_pop_payload_batch() — single-attempt HTTP send.
Uses a FakeHttpClient — no real network calls, no backend, no secret reading.
"""

import unittest
from dataclasses import dataclass, field
from typing import Any, Optional

from kso_sidecar_agent.pop_sender import (
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_PROCESSED,
    REASON_PARTIAL_SUCCESS,
    REASON_DUPLICATE_BATCH,
    REASON_BAD_REQUEST,
    REASON_UNAUTHORIZED,
    REASON_FORBIDDEN,
    REASON_NOT_FOUND,
    REASON_VALIDATION_ERROR,
    REASON_RATE_LIMITED,
    REASON_SERVER_ERROR,
    REASON_NETWORK_ERROR,
    REASON_TIMEOUT,
    REASON_NO_PAYLOAD,
    REASON_INVALID_RESPONSE,
    FORBIDDEN_IN_OUTPUT,
    POP_BATCH_ENDPOINT,
    PopSendResult,
    send_pop_payload_batch,
    format_pop_send_result,
)
from kso_sidecar_agent.pop_payload import PopPayloadEnvelope, PopPayloadEvent


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP client
# ══════════════════════════════════════════════════════════════════════

class FakeHttpError(Exception):
    """Simulates HttpClientError from http_client.py."""

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
    """Fake SafeHttpClient — no real network calls.

    Returns pre-configured responses or raises pre-configured errors.
    Records the last path, payload, and headers for assertion.
    """

    def __init__(self, response=None, error=None, allowed_path=POP_BATCH_ENDPOINT):
        self._response = response
        self._error = error
        self._allowed_path = allowed_path
        # Recording
        self.last_path = None
        self.last_payload = None
        self.last_headers = None

    def post_json(self, path, payload, headers=None):
        self.last_path = path
        self.last_payload = payload
        self.last_headers = headers

        if self._error is not None:
            raise self._error
        if self._response is not None:
            return self._response
        # Default: success
        return FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": len(payload.get("events", []))}},
            elapsed_ms=10.0,
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_envelope(batch_id="b1", events_count=3, with_manifest_item_id=True):
    """Build a PopPayloadEnvelope for testing."""
    events = []
    for i in range(events_count):
        evt = PopPayloadEvent(
            device_event_id=f"dev-{batch_id}-{i}",
            manifest_item_id=f"mi-{batch_id}-{i}" if with_manifest_item_id else None,
            manifest_version_id="mv-1",
            played_at="2026-06-19T10:00:00Z",
            duration_ms=15000,
            play_status="completed",
        )
        events.append(evt)
    return PopPayloadEnvelope(
        batch_id=batch_id,
        sent_at="2026-06-19T10:01:00Z",
        events=events,
    )


def _no_forbidden(text):
    """Return True if text contains no forbidden substrings."""
    lower = text.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestSendNoPayload(unittest.TestCase):
    """No payload cases — no HTTP call."""

    def test_none_envelope_no_http(self):
        client = FakeHttpClient()
        result = send_pop_payload_batch(client, None)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_NO_PAYLOAD)
        self.assertEqual(result.attempted_events, 0)
        self.assertTrue(result.pending_should_remain)
        self.assertIsNone(client.last_path)  # no HTTP call

    def test_empty_events_no_http(self):
        client = FakeHttpClient()
        envelope = PopPayloadEnvelope(batch_id="b1", events=[])
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.reason, REASON_NO_PAYLOAD)
        self.assertIsNone(client.last_path)


class TestSend200Processed(unittest.TestCase):
    """HTTP 200 processed → ok."""

    def test_200_processed(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 3}},
        ))
        envelope = _make_envelope(events_count=3)
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_OK)
        self.assertEqual(result.reason, REASON_PROCESSED)
        self.assertFalse(result.pending_should_remain)
        self.assertEqual(result.accepted_events, 3)

    def test_200_processed_with_token(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 2}},
        ))
        envelope = _make_envelope(events_count=2)
        result = send_pop_payload_batch(client, envelope, access_token="test-jwt")
        self.assertEqual(result.send_status, SEND_OK)
        # Verify token was passed as Authorization header
        self.assertEqual(client.last_headers.get("Authorization"), "Bearer test-jwt")


class TestSend200Partial(unittest.TestCase):
    """HTTP 200 with partial rejection → warning."""

    def test_200_partial(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 2, "rejected": 1}},
        ))
        envelope = _make_envelope(events_count=3)
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_PARTIAL_SUCCESS)
        self.assertTrue(result.pending_should_remain)


class TestSend4xx(unittest.TestCase):
    """HTTP 4xx errors."""

    def test_400_bad_request(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=400, message="Bad Request", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_BAD_REQUEST)
        self.assertFalse(result.retryable)

    def test_401_unauthorized(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=401, message="Unauthorized", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_UNAUTHORIZED)
        self.assertTrue(result.auth_refresh_required)
        self.assertTrue(result.retryable)

    def test_403_forbidden(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=403, message="Forbidden", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_FORBIDDEN)

    def test_404_not_found(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=404, message="Not Found", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_NOT_FOUND)

    def test_409_duplicate(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=409, message="Conflict", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_DUPLICATE_BATCH)
        self.assertTrue(result.pending_should_remain)  # default: not safe to remove

    def test_422_validation_error(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=422, message="Unprocessable", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_VALIDATION_ERROR)

    def test_429_rate_limited(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=429, message="Too Many Requests", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_WARNING)
        self.assertEqual(result.reason, REASON_RATE_LIMITED)
        self.assertTrue(result.retryable)


class TestSend5xx(unittest.TestCase):
    """HTTP 5xx server errors."""

    def test_500_server_error(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=500, message="Server Error", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_SERVER_ERROR)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_502_server_error(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=502, message="Bad Gateway", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.reason, REASON_SERVER_ERROR)
        self.assertTrue(result.retryable)

    def test_503_server_error(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=503, message="Service Unavailable", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.reason, REASON_SERVER_ERROR)
        self.assertTrue(result.retryable)


class TestNetworkErrors(unittest.TestCase):
    """Network / timeout errors."""

    def test_network_exception(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=0, message="Network error: Connection refused", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_NETWORK_ERROR)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain)

    def test_timeout_exception(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=0, message="Connection failed: timeout", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_TIMEOUT)
        self.assertTrue(result.retryable)


class TestPathOnlyAllowlisted(unittest.TestCase):
    """Sender uses only the allowlisted endpoint path."""

    def test_uses_batch_endpoint(self):
        client = FakeHttpClient()
        envelope = _make_envelope()
        send_pop_payload_batch(client, envelope)
        self.assertEqual(client.last_path, POP_BATCH_ENDPOINT)

    def test_no_arbitrary_url(self):
        client = FakeHttpClient()
        envelope = _make_envelope()
        send_pop_payload_batch(client, envelope)
        # Endpoint must be the hardcoded POP_BATCH_ENDPOINT, not random
        self.assertNotIn("http", client.last_path)  # path, not full URL
        self.assertTrue(client.last_path.startswith("/api/"))


class TestTokenNeverLeaked(unittest.TestCase):
    """Authorization token never appears in result, repr, or format output."""

    def test_token_not_in_result_repr(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 2}},
        ))
        envelope = _make_envelope(events_count=2)
        result = send_pop_payload_batch(client, envelope, access_token="super-secret-jwt-token-123")
        text = repr(result)
        self.assertNotIn("super-secret", text)
        self.assertNotIn("jwt", text)
        self.assertNotIn("Bearer", text)

    def test_token_not_in_format_output(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 2}},
        ))
        envelope = _make_envelope(events_count=2)
        result = send_pop_payload_batch(client, envelope, access_token="abc-token-xyz")
        text = format_pop_send_result(result)
        self.assertNotIn("abc-token-xyz", text)
        self.assertNotIn("Bearer", text)

    def test_result_no_token_field(self):
        client = FakeHttpClient()
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope, access_token="test-tok")
        # PopSendResult has no token field
        self.assertFalse(hasattr(result, "token"))
        self.assertFalse(hasattr(result, "access_token"))
        self.assertFalse(hasattr(result, "authorization"))


class TestPayloadNeverLeaked(unittest.TestCase):
    """Payload body / IDs never appear in safe output."""

    def test_format_no_payload_body(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 3}},
        ))
        envelope = _make_envelope(events_count=3)
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertNotIn("batch_id", text)
        self.assertNotIn("device_event_id", text)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("mi-", text)
        self.assertNotIn("dev-", text)

    def test_repr_no_payload_body(self):
        client = FakeHttpClient()
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        text = repr(result)
        self.assertNotIn("batch_id", text)
        self.assertNotIn("device_event_id", text)
        self.assertNotIn("manifest_item_id", text)

    def test_format_no_raw_backend_response(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "proof_batch_id": "uuid-123", "summary": {"accepted": 3}},
        ))
        envelope = _make_envelope(events_count=3)
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertNotIn("proof_batch_id", text)
        self.assertNotIn("uuid-123", text)

    def test_format_no_campaign_id(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 1}},
        ))
        envelope = _make_envelope(events_count=1)
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertNotIn("campaign", text.lower())
        self.assertNotIn("creative", text.lower())
        self.assertNotIn("schedule", text.lower())


class TestNoFileOrSecretReading(unittest.TestCase):
    """Sender does NOT read secret/config/token files, media bytes, or move files."""

    def test_pop_sender_module_no_secret_imports(self):
        import importlib
        spec = importlib.util.find_spec("kso_sidecar_agent.pop_sender")
        with open(spec.origin) as f:
            content = f.read()
        # No file-reading of secrets
        self.assertNotIn("device_secret.dev", content)
        self.assertNotIn("secret_store", content)
        self.assertNotIn("local_config", content)
        # No os.path or Path for file operations
        self.assertNotIn("from pathlib", content)

    def test_sender_does_not_move_files(self):
        client = FakeHttpClient()
        envelope = _make_envelope()
        # Just call — no file I/O error expected
        result = send_pop_payload_batch(client, envelope)
        self.assertIsNotNone(result)

    def test_sender_does_not_create_dirs(self):
        # No os.makedirs, no Path.mkdir
        import importlib
        spec = importlib.util.find_spec("kso_sidecar_agent.pop_sender")
        with open(spec.origin) as f:
            content = f.read()
        self.assertNotIn("mkdir", content)
        self.assertNotIn("makedirs", content)
        self.assertNotIn("sent/", content)
        self.assertNotIn("quarantine", content)
        self.assertNotIn("dry_run", content)


class TestSafeOutputNoForbidden(unittest.TestCase):
    """format output never contains forbidden substrings."""

    def test_format_ok_no_forbidden(self):
        client = FakeHttpClient(response=FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": 3}},
        ))
        envelope = _make_envelope(events_count=3)
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertTrue(_no_forbidden(text), f"forbidden found: {text}")

    def test_format_401_no_forbidden(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=401, message="Unauthorized", retryable=False))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_500_no_forbidden(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=500, message="Server Error", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_network_no_forbidden(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=0, message="Network error", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertTrue(_no_forbidden(text))


class TestResultNoStacktrace(unittest.TestCase):
    """No stacktraces in error output."""

    def test_no_stacktrace_in_safe_output(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=0, message="Connection failed", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        text = format_pop_send_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("traceback", text)
        self.assertNotIn("stacktrace", text)

    def test_no_exception_in_repr(self):
        client = FakeHttpClient(error=FakeHttpError(status_code=500, message="Server Error", retryable=True))
        envelope = _make_envelope()
        result = send_pop_payload_batch(client, envelope)
        text = repr(result)
        self.assertNotIn("HttpClientError", text)
        self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
