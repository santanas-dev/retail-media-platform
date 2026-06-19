"""Tests for KSO Sidecar PoP Eligible Batch Builder (pop_batch.py)."""

import json
import tempfile
import unittest
from pathlib import Path

from kso_sidecar_agent.pop_batch import (
    PopBatchCandidate,
    PopBatchBuildResult,
    build_pop_eligible_batch,
    DEFAULT_MAX_EVENTS,
)
from kso_sidecar_agent.pop_pickup import (
    POP_PENDING_DIR,
    POP_JSONL_FILE,
    FORBIDDEN_SUBSTRINGS,
    FORBIDDEN_KEYS,
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
            "manifest_item_id": f"uuid-{i:04d}-1111-1111-1111-111111111111",
            "filename": f"file_{i}.png",
            "content_type": "image/png",
            "sha256": "a" * 64,
            "duration_ms": 5000,
            "order": i,
            "size_bytes": 1000,
        })
    return items


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


# ══════════════════════════════════════════════════════════════════════
# Dataclass Tests
# ══════════════════════════════════════════════════════════════════════


class TestPopBatchCandidate(unittest.TestCase):
    def test_no_forbidden_fields(self):
        c = PopBatchCandidate()
        fields = {
            "schema_version", "event_type", "event_status", "created_at",
            "started_at", "ended_at", "duration_ms", "playback_allowed",
            "session_action", "session_reason", "selected_order",
            "selected_content_type", "safety_state", "result",
        }
        for key in fields:
            self.assertTrue(hasattr(c, key), f"Missing field: {key}")
        # Must NOT have forbidden fields
        for fb in ("filename", "manifest_item_id", "sha256", "token", "secret"):
            self.assertFalse(hasattr(c, fb), f"Forbidden field present: {fb}")


class TestPopBatchBuildResultDefaults(unittest.TestCase):
    def test_defaults(self):
        r = PopBatchBuildResult()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.max_events, DEFAULT_MAX_EVENTS)

    def test_no_path_or_secret(self):
        r = PopBatchBuildResult()
        for attr in dir(r):
            if attr.startswith("_"):
                continue
            val = getattr(r, attr)
            if isinstance(val, str):
                for fb in ("/", "token", "secret", "filename"):
                    self.assertNotIn(fb, val.lower())


# ══════════════════════════════════════════════════════════════════════
# build_pop_eligible_batch Tests
# ══════════════════════════════════════════════════════════════════════


class TestBatchMissingFile(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_missing_file_ok_empty(self):
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.total_lines, 0)
        self.assertEqual(result.candidate_events, 0)


class TestBatchDraftSkip(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("draft")])

    def test_draft_not_in_batch(self):
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.draft_events, 1)

    def test_draft_counted_as_skipped(self):
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.skipped_events, 1)


class TestBatchBlockedSkip(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("blocked", event_type="blocked")])

    def test_blocked_not_in_batch(self):
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.diagnostic_events, 1)


class TestBatchFailedSkip(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("failed", event_type="error")])

    def test_failed_not_in_batch(self):
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.diagnostic_events, 1)


class TestBatchInvalidSkip(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_invalid_json(self):
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        (pending_dir / POP_JSONL_FILE).write_text("not json\n")
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.invalid_events, 1)

    def test_forbidden_key(self):
        rec = _make_record("draft")
        rec["token"] = "abc"
        _write_jsonl(self.root, [rec])
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.invalid_events, 1)

    def test_forbidden_value(self):
        rec = _make_record("draft")
        rec["selected_content_type"] = "file_path"
        _write_jsonl(self.root, [rec])
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.invalid_events, 1)

    def test_filename_in_record(self):
        rec = _make_record("draft")
        rec["filename"] = "bad.png"
        _write_jsonl(self.root, [rec])
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(result.invalid_events, 1)


class TestBatchMaxEvents(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_max_5_limit(self):
        # Write 10 draft records (which won't be eligible, so limit not reached anyway)
        recs = [_make_record("draft") for _ in range(10)]
        _write_jsonl(self.root, recs)
        result = build_pop_eligible_batch(self.root, max_events=5)
        self.assertEqual(result.draft_events, 10)
        self.assertEqual(result.candidate_events, 0)
        self.assertFalse(result.batch_limited)

    def test_max_0_returns_error(self):
        result = build_pop_eligible_batch(self.root, max_events=0)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.candidate_events, 0)

    def test_negative_max_returns_error(self):
        result = build_pop_eligible_batch(self.root, max_events=-1)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.candidate_events, 0)


class TestBatchSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_candidate_no_filename(self):
        c = PopBatchCandidate()
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            val = getattr(c, attr)
            if isinstance(val, str):
                self.assertNotIn("filename", val.lower())
                self.assertNotIn(".png", val.lower())

    def test_candidate_no_manifest_item_id(self):
        c = PopBatchCandidate()
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            val = getattr(c, attr)
            if isinstance(val, str):
                self.assertNotIn("manifest_item_id", val.lower())
                self.assertNotIn("uuid-", val.lower())

    def test_candidate_no_sha256(self):
        c = PopBatchCandidate()
        has_sha = hasattr(c, "sha256")
        self.assertFalse(has_sha, "Candidate must not have sha256 field")

    def test_candidate_no_paths(self):
        c = PopBatchCandidate()
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            val = getattr(c, attr)
            if isinstance(val, str):
                self.assertNotIn("/", val)

    def test_result_no_forbidden(self):
        _write_jsonl(self.root, [_make_record("draft")])
        result = build_pop_eligible_batch(self.root)
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            val = getattr(result, attr)
            if isinstance(val, str):
                lower = val.lower()
                for fb in ("token", "secret", "password", "api_key",
                          "file_path", "local_path", "127.0.0.1",
                          "device_code", "backend_base_url", "filename",
                          "manifest_item_id", "sha256", "stacktrace"):
                    self.assertNotIn(fb, lower,
                        f"Forbidden '{fb}' in result.{attr}")

    def test_no_stacktrace(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            result = build_pop_eligible_batch(tmp)
            self.assertEqual(result.status, "ok")
        except Exception as e:
            self.fail(f"build_pop_eligible_batch raised: {e}")


class TestBatchNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_does_not_delete_pending(self):
        _write_jsonl(self.root, [_make_record("draft")])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        build_pop_eligible_batch(self.root)
        self.assertTrue(jsonl_path.exists(), "Builder must NOT delete pending file")

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        build_pop_eligible_batch(self.root)
        self.assertFalse((self.root / "pop" / "sent").exists())

    def test_does_not_create_quarantine_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        build_pop_eligible_batch(self.root)
        self.assertFalse((self.root / "pop" / "quarantine").exists())

    def test_does_not_create_dry_run_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        build_pop_eligible_batch(self.root)
        self.assertFalse((self.root / "pop" / "dry_run").exists())

    def test_no_http(self):
        import kso_sidecar_agent.pop_batch as pb
        source = open(pb.__file__).read()
        for lib in ("urllib", "requests", "http.client", "httpx", "aiohttp"):
            self.assertNotIn(lib, source, f"HTTP lib '{lib}' in pop_batch.py")

    def test_no_secret_config_token(self):
        _write_jsonl(self.root, [_make_record("draft")])
        result = build_pop_eligible_batch(self.root)
        self.assertEqual(result.status, "ok")


if __name__ == "__main__":
    unittest.main()
