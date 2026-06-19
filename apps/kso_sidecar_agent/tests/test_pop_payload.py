"""Tests for KSO Sidecar PoP Backend Payload Builder (pop_payload.py)."""

import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from kso_sidecar_agent.pop_payload import (
    PopPayloadEvent,
    PopPayloadEnvelope,
    PopPayloadBuildResult,
    build_pop_backend_payload,
    format_pop_payload_build_result,
    DEFAULT_MAX_EVENTS,
)
from kso_sidecar_agent.pop_pickup import (
    POP_PENDING_DIR,
    POP_JSONL_FILE,
    FORBIDDEN_SUBSTRINGS,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_record(event_status="draft", event_type="would_play",
                 safety_state="idle", selected_order=0):
    return {
        "schema_version": 1,
        "event_type": event_type,
        "event_status": event_status,
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": "2026-06-19T00:00:00+00:00",
        "ended_at": "2026-06-19T00:00:05+00:00",
        "duration_ms": 5000 if event_type == "would_play" else 0,
        "playback_allowed": True if event_type == "would_play" else False,
        "session_action": "play" if event_type == "would_play" else "stop",
        "session_reason": "ready" if event_type == "would_play" else "safety_blocked",
        "selected_order": selected_order,
        "selected_content_type": "image/png",
        "safety_state": safety_state,
        "result": event_type,
    }


def _make_manifest_items(count=3):
    items = []
    for i in range(count):
        items.append({
            "manifest_item_id": str(uuid.uuid4()),
            "filename": f"file_{i}.png",
            "content_type": "image/png",
            "sha256": "a" * 64,
            "duration_ms": 5000,
            "order": i,
            "size_bytes": 100,  # match actual file size
            "campaign_id": str(uuid.uuid4()),
            "schedule_item_id": str(uuid.uuid4()),
        })
    return items


def _make_manifest_data(items=None, mvid=None):
    if mvid is None:
        mvid = str(uuid.uuid4())
    return {
        "manifest_version_id": mvid,
        "manifest_hash": "a" * 64,
        "source": "current",
        "generated_at": "2026-06-19T00:00:00Z",
        "publication_target_id": str(uuid.uuid4()),
        "items": items or _make_manifest_items(3),
    }


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


def _write_manifest(root, manifest_data):
    mdir = root / "manifest"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "current_manifest.json").write_text(json.dumps(manifest_data))


def _write_media_files(root, manifest_items):
    mdir = root / "media" / "current"
    mdir.mkdir(parents=True, exist_ok=True)
    for item in manifest_items:
        fname = item["filename"]
        data = b"\x00" * 100
        sha = hashlib.sha256(data).hexdigest()
        item["sha256"] = sha
        (mdir / fname).write_bytes(data)


# ══════════════════════════════════════════════════════════════════════


class TestPayloadDataclasses(unittest.TestCase):
    def test_payload_event_repr_hides_sensitive(self):
        e = PopPayloadEvent(
            device_event_id="dev-123",
            manifest_item_id="mi-456",
        )
        r = repr(e)
        self.assertNotIn("dev-123", r)
        self.assertNotIn("mi-456", r)
        self.assertNotIn("manifest_item_id", r)

    def test_payload_envelope_repr_hides_sensitive(self):
        env = PopPayloadEnvelope(
            batch_id="batch-789",
            events=[PopPayloadEvent(device_event_id="ev-1")],
        )
        r = repr(env)
        self.assertNotIn("batch-789", r)
        self.assertNotIn("ev-1", r)

    def test_build_result_repr_hides_envelope(self):
        result = PopPayloadBuildResult()
        r = repr(result)
        self.assertNotIn("_envelope", r)
        self.assertNotIn("Envelope", r)

    def test_payload_event_no_filename(self):
        e = PopPayloadEvent(device_event_id="x")
        self.assertFalse(hasattr(e, "filename"))

    def test_payload_event_no_sha256(self):
        e = PopPayloadEvent(device_event_id="x")
        self.assertFalse(hasattr(e, "sha256"))

    def test_payload_event_no_path(self):
        e = PopPayloadEvent(device_event_id="x")
        for attr in dir(e):
            if attr.startswith("_"):
                continue
            val = getattr(e, attr)
            if isinstance(val, str):
                self.assertNotIn("/", val)


class TestBuildPayloadMissingFile(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_missing_file_empty(self):
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload_events, 0)


class TestBuildPayloadDraftSkip(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("draft")])

    def test_draft_not_in_payload(self):
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.draft_events, 1)


class TestBuildPayloadBlockedSkip(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("blocked", event_type="blocked")])

    def test_blocked_not_in_payload(self):
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.diagnostic_events, 1)


class TestBuildPayloadCompletedEligible(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        # Write media FIRST (updates sha256 in-place), then manifest
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("completed", selected_order=1)])

    def test_eligible_in_payload(self):
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.payload_events, 1)
        self.assertEqual(result.status, "ok")

    def test_envelope_has_batch_id(self):
        result = build_pop_backend_payload(self.root)
        env = result._envelope
        self.assertIsNotNone(env)
        self.assertTrue(len(env.batch_id) > 0)
        self.assertEqual(len(env.events), 1)

    def test_payload_event_has_device_event_id(self):
        result = build_pop_backend_payload(self.root)
        ev = result._envelope.events[0]
        self.assertTrue(len(ev.device_event_id) > 0)

    def test_payload_event_has_manifest_item_id_internal(self):
        result = build_pop_backend_payload(self.root)
        ev = result._envelope.events[0]
        self.assertIsNotNone(ev.manifest_item_id)
        self.assertTrue(len(ev.manifest_item_id) > 0)

    def test_payload_event_has_manifest_version_id(self):
        result = build_pop_backend_payload(self.root)
        ev = result._envelope.events[0]
        self.assertIsNotNone(ev.manifest_version_id)
        self.assertTrue(len(ev.manifest_version_id) > 0)

    def test_payload_event_has_played_at(self):
        result = build_pop_backend_payload(self.root)
        ev = result._envelope.events[0]
        self.assertIsNotNone(ev.played_at)
        self.assertIn("2026", ev.played_at)

    def test_payload_event_no_filename_field(self):
        result = build_pop_backend_payload(self.root)
        ev = result._envelope.events[0]
        self.assertFalse(hasattr(ev, "filename"))

    def test_payload_event_no_sha256_field(self):
        result = build_pop_backend_payload(self.root)
        ev = result._envelope.events[0]
        self.assertFalse(hasattr(ev, "sha256"))


class TestBuildPayloadNotEligible(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.items = _make_manifest_items(3)
        _write_media_files(self.root, self.items)
        _write_manifest(self.root, _make_manifest_data(self.items))

    def test_payment_not_payload(self):
        _write_jsonl(self.root, [_make_record("completed", safety_state="payment")])
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.quarantine_events, 1)

    def test_no_selected_order_not_payload(self):
        rec = _make_record("completed", selected_order=None)
        rec.pop("selected_order")
        _write_jsonl(self.root, [rec])
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.payload_events, 0)

    def test_order_not_found_not_payload(self):
        _write_jsonl(self.root, [_make_record("completed", selected_order=99)])
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.quarantine_events, 1)


class TestBuildPayloadInvalid(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_invalid_json(self):
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        (pending_dir / POP_JSONL_FILE).write_text("not json\n")
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.invalid_events, 1)
        self.assertEqual(result.payload_events, 0)

    def test_forbidden_key(self):
        rec = _make_record("draft")
        rec["token"] = "abc"
        _write_jsonl(self.root, [rec])
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.invalid_events, 1)

    def test_filename_in_record(self):
        rec = _make_record("draft")
        rec["filename"] = "bad.png"
        _write_jsonl(self.root, [rec])
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.invalid_events, 1)


class TestBuildPayloadMaxEvents(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_max_0_error(self):
        result = build_pop_backend_payload(self.root, max_events=0)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.payload_events, 0)

    def test_max_negative_error(self):
        result = build_pop_backend_payload(self.root, max_events=-1)
        self.assertEqual(result.status, "error")


class TestBuildPayloadSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("completed", selected_order=0)])

    def test_result_repr_no_manifest_item_id(self):
        result = build_pop_backend_payload(self.root)
        r = repr(result)
        self.assertNotIn("manifest_item_id", r.lower())

    def test_result_repr_no_batch_id(self):
        result = build_pop_backend_payload(self.root)
        r = repr(result)
        # batch_id keyword should not appear in repr
        self.assertNotIn("batch_id", r.lower())

    def test_result_repr_no_forbidden(self):
        result = build_pop_backend_payload(self.root)
        r = repr(result).lower()
        for fb in ("token", "secret", "password", "filename", "sha256",
                   "file_path", "127.0.0.1", "device_code", "stacktrace"):
            self.assertNotIn(fb, r, f"Forbidden '{fb}' in repr")

    def test_safe_output_no_payload_body(self):
        result = build_pop_backend_payload(self.root)
        out = format_pop_payload_build_result(result)
        self.assertNotIn("batch_id", out.lower())
        self.assertNotIn("manifest_item_id", out.lower())
        self.assertNotIn("device_event_id", out.lower())

    def test_safe_output_no_forbidden(self):
        result = build_pop_backend_payload(self.root)
        out = format_pop_payload_build_result(result).lower()
        for fb in ("token", "secret", "filename", "sha256", "file_path",
                   "127.0.0.1", "device_code", "stacktrace"):
            self.assertNotIn(fb, out, f"Forbidden '{fb}' in safe output")

    def test_safe_output_has_aggregates(self):
        result = build_pop_backend_payload(self.root)
        out = format_pop_payload_build_result(result)
        self.assertIn("payload_events:", out)
        self.assertIn("payload_status:", out)
        self.assertIn("max_events:", out)


class TestBuildPayloadNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_no_http(self):
        import kso_sidecar_agent.pop_payload as pp
        source = open(pp.__file__).read()
        for lib in ("urllib", "requests", "http.client", "httpx", "aiohttp"):
            self.assertNotIn(lib, source, f"HTTP lib '{lib}' in pop_payload.py")

    def test_does_not_delete_pending(self):
        _write_jsonl(self.root, [_make_record("draft")])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        build_pop_backend_payload(self.root)
        self.assertTrue(jsonl_path.exists())

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        build_pop_backend_payload(self.root)
        self.assertFalse((self.root / "pop" / "sent").exists())

    def test_does_not_create_quarantine_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        build_pop_backend_payload(self.root)
        self.assertFalse((self.root / "pop" / "quarantine").exists())

    def test_does_not_create_dry_run_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        build_pop_backend_payload(self.root)
        self.assertFalse((self.root / "pop" / "dry_run").exists())

    def test_no_secret_config_token(self):
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("completed", selected_order=0)])
        result = build_pop_backend_payload(self.root)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload_events, 1)

    def test_no_stacktrace(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            result = build_pop_backend_payload(tmp)
            self.assertEqual(result.status, "ok")
        except Exception as e:
            self.fail(f"build_pop_backend_payload raised: {e}")


if __name__ == "__main__":
    unittest.main()
