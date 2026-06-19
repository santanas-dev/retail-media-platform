"""Tests for KSO Sidecar PoP Pickup classifier (pop_pickup.py)."""

import json
import tempfile
import unittest
from pathlib import Path

from kso_sidecar_agent.pop_pickup import (
    PopPickupClassification,
    PopPickupScanResult,
    classify_pop_event,
    scan_pending_pop_events,
    CLASS_DRAFT,
    CLASS_ELIGIBLE,
    CLASS_DIAGNOSTIC,
    CLASS_QUARANTINE,
    CLASS_INVALID,
    REASON_DRAFT_NOT_POP,
    REASON_BLOCKED_NOT_POP,
    REASON_FAILED_NOT_POP,
    REASON_ELIGIBLE,
    REASON_MANIFEST_MAPPING_MISSING,
    REASON_MANIFEST_UNAVAILABLE,
    REASON_MEDIA_CACHE_INCOMPLETE,
    REASON_INVALID_JSON,
    ALLOWED_RECORD_KEYS,
    FORBIDDEN_SUBSTRINGS,
    FORBIDDEN_KEYS,
    SCAN_OK,
    SCAN_WARNING,
    SCAN_ERROR,
    POP_PENDING_DIR,
    POP_JSONL_FILE,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_record(event_status="draft", event_type="would_play",
                 safety_state="idle", selected_order=0, **kwargs):
    """Build a safe JSONL-compatible record."""
    rec = {
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
    rec.update(kwargs)
    return rec


def _make_manifest_items(count=3):
    """Create fake manifest items with order 0..count-1."""
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
    """Write list of dicts as JSONL to pop/pending/player_events.jsonl."""
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


# ══════════════════════════════════════════════════════════════════════
# PopPickupClassification Tests
# ══════════════════════════════════════════════════════════════════════


class TestClassificationDefaults(unittest.TestCase):
    def test_default_is_invalid(self):
        c = PopPickupClassification()
        self.assertEqual(c.classification, CLASS_INVALID)
        self.assertFalse(c.backend_eligible)

    def test_no_paths_or_secrets(self):
        c = PopPickupClassification(reason="test")
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            val = getattr(c, attr)
            if isinstance(val, str):
                for fb in ("/", "token", "secret", "password"):
                    self.assertNotIn(fb, val.lower())


class TestPopPickupScanResultDefaults(unittest.TestCase):
    def test_default_ok(self):
        r = PopPickupScanResult()
        self.assertEqual(r.status, SCAN_OK)
        self.assertEqual(r.total_lines, 0)

    def test_no_paths_or_secrets(self):
        r = PopPickupScanResult()
        for attr in dir(r):
            if attr.startswith("_"):
                continue
            val = getattr(r, attr)
            if isinstance(val, str):
                for fb in ("/", "token", "secret"):
                    self.assertNotIn(fb, val.lower())


# ══════════════════════════════════════════════════════════════════════
# classify_pop_event Tests
# ══════════════════════════════════════════════════════════════════════


class TestClassifyDraft(unittest.TestCase):
    def test_draft_is_not_eligible(self):
        rec = _make_record("draft")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_DRAFT)
        self.assertEqual(c.reason, REASON_DRAFT_NOT_POP)
        self.assertFalse(c.backend_eligible)

    def test_draft_payment_not_eligible(self):
        rec = _make_record("draft", safety_state="payment")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_DRAFT)
        self.assertFalse(c.backend_eligible)


class TestClassifyCompleted(unittest.TestCase):
    def test_completed_eligible(self):
        rec = _make_record("completed", selected_order=1)
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=True)
        self.assertEqual(c.classification, CLASS_ELIGIBLE)
        self.assertEqual(c.reason, REASON_ELIGIBLE)
        self.assertTrue(c.backend_eligible)

    def test_completed_payment_quarantine(self):
        rec = _make_record("completed", safety_state="payment")
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=True)
        self.assertEqual(c.classification, CLASS_QUARANTINE)
        self.assertFalse(c.backend_eligible)

    def test_completed_no_manifest_quarantine(self):
        rec = _make_record("completed")
        c = classify_pop_event(rec, manifest_items=None, media_cache_complete=True)
        self.assertEqual(c.classification, CLASS_QUARANTINE)
        self.assertEqual(c.reason, REASON_MANIFEST_UNAVAILABLE)

    def test_completed_order_not_found_quarantine(self):
        rec = _make_record("completed", selected_order=99)
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=True)
        self.assertEqual(c.classification, CLASS_QUARANTINE)
        self.assertEqual(c.reason, REASON_MANIFEST_MAPPING_MISSING)

    def test_completed_no_selected_order_quarantine(self):
        rec = _make_record("completed", selected_order=None)
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=True)
        self.assertEqual(c.classification, CLASS_QUARANTINE)

    def test_completed_media_incomplete_quarantine(self):
        rec = _make_record("completed", selected_order=0)
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=False)
        self.assertEqual(c.classification, CLASS_QUARANTINE)
        self.assertEqual(c.reason, REASON_MEDIA_CACHE_INCOMPLETE)


class TestClassifyBlocked(unittest.TestCase):
    def test_blocked_diagnostic(self):
        rec = _make_record("blocked")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_DIAGNOSTIC)
        self.assertEqual(c.reason, REASON_BLOCKED_NOT_POP)
        self.assertFalse(c.backend_eligible)


class TestClassifyFailed(unittest.TestCase):
    def test_failed_diagnostic(self):
        rec = _make_record("failed")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_DIAGNOSTIC)
        self.assertEqual(c.reason, REASON_FAILED_NOT_POP)
        self.assertFalse(c.backend_eligible)


class TestClassifyInvalid(unittest.TestCase):
    def test_none_record(self):
        c = classify_pop_event(None)
        self.assertEqual(c.classification, CLASS_INVALID)

    def test_non_dict(self):
        c = classify_pop_event("not_a_dict")
        self.assertEqual(c.classification, CLASS_INVALID)

    def test_forbidden_key(self):
        rec = _make_record("draft")
        rec["token"] = "abc"
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_INVALID)

    def test_forbidden_value(self):
        rec = _make_record("draft", selected_content_type="file_path")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_INVALID)
        self.assertEqual(c.reason, "forbidden_value")

    def test_unknown_key(self):
        rec = _make_record("draft")
        rec["bogus_field"] = "hello"
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_INVALID)
        self.assertEqual(c.reason, "invalid_schema")

    def test_invalid_event_type(self):
        rec = _make_record("draft", event_type="bogus")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_INVALID)

    def test_forbidden_value_in_record(self):
        rec = _make_record("draft")
        rec["selected_content_type"] = "file_path"
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_INVALID)


class TestClassifyFieldSafety(unittest.TestCase):
    def test_no_manifest_item_id_returned(self):
        rec = _make_record("completed", selected_order=0)
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=True)
        # Classification result should NOT contain manifest_item_id
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            val = getattr(c, attr)
            if isinstance(val, str):
                self.assertNotIn("uuid-", val)

    def test_no_filename_in_result(self):
        rec = _make_record("completed", selected_order=0)
        manifest = _make_manifest_items(3)
        c = classify_pop_event(rec, manifest_items=manifest, media_cache_complete=True)
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            val = getattr(c, attr)
            if isinstance(val, str):
                self.assertNotIn(".png", val.lower())

    def test_receipt_state_ok_as_safety_state(self):
        """'receipt' as safety_state is fine — receipt_DATA is forbidden."""
        rec = _make_record("draft", safety_state="receipt")
        c = classify_pop_event(rec)
        self.assertEqual(c.classification, CLASS_DRAFT)


# ══════════════════════════════════════════════════════════════════════
# scan_pending_pop_events Tests
# ══════════════════════════════════════════════════════════════════════


class TestScanMissingFile(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_missing_file_ok_empty(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.status, SCAN_OK)
        self.assertEqual(result.total_lines, 0)
        self.assertEqual(result.draft_events, 0)


class TestScanDraftEvents(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        rec = _make_record("draft", event_type="would_play", selected_order=0)
        _write_jsonl(self.root, [rec])

    def test_draft_classified(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.total_lines, 1)
        self.assertEqual(result.valid_events, 1)
        self.assertEqual(result.draft_events, 1)
        self.assertEqual(result.eligible_events, 0)
        self.assertEqual(result.backend_eligible_events, 0)

    def test_draft_not_eligible(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.backend_eligible_events, 0)


class TestScanBlockedDiagnostic(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        rec = _make_record("blocked", event_type="blocked")
        _write_jsonl(self.root, [rec])

    def test_blocked_diagnostic(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.diagnostic_events, 1)
        self.assertEqual(result.eligible_events, 0)


class TestScanFailedDiagnostic(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        rec = _make_record("failed", event_type="error")
        _write_jsonl(self.root, [rec])

    def test_failed_diagnostic(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.diagnostic_events, 1)
        self.assertEqual(result.eligible_events, 0)


class TestScanInvalidLines(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_invalid_json_line(self):
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        (pending_dir / POP_JSONL_FILE).write_text("not json\n")
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.invalid_lines, 1)

    def test_forbidden_key_line(self):
        rec = _make_record("draft")
        rec["token"] = "abc"
        _write_jsonl(self.root, [rec])
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.invalid_lines, 1)

    def test_forbidden_value_line(self):
        rec = _make_record("draft")
        rec["selected_content_type"] = "secret_value"
        _write_jsonl(self.root, [rec])
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.invalid_lines, 1)

    def test_filename_in_record(self):
        rec = _make_record("draft")
        rec["filename"] = "bad.png"
        _write_jsonl(self.root, [rec])
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.invalid_lines, 1)

    def test_sha256_in_record(self):
        rec = _make_record("draft")
        rec["sha256"] = "a" * 64
        _write_jsonl(self.root, [rec])
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.invalid_lines, 1)


class TestScanMixedLines(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        lines = [
            _make_record("draft", selected_order=0),
            _make_record("blocked"),
            _make_record("draft", selected_order=1),
        ]
        _write_jsonl(self.root, lines)

    def test_mixed_counts(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.total_lines, 3)
        self.assertEqual(result.valid_events, 3)
        self.assertEqual(result.draft_events, 2)
        self.assertEqual(result.diagnostic_events, 1)
        self.assertEqual(result.invalid_lines, 0)


class TestScanEmptyLines(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        # File with empty lines and a valid line
        (pending_dir / POP_JSONL_FILE).write_text(
            "\n" + json.dumps(_make_record("draft"), sort_keys=True) + "\n\n"
        )

    def test_empty_lines_skipped(self):
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.total_lines, 1)  # only the non-empty line
        self.assertEqual(result.valid_events, 1)


class TestScanNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_does_not_delete_file(self):
        _write_jsonl(self.root, [_make_record("draft")])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        scan_pending_pop_events(self.root)
        self.assertTrue(jsonl_path.exists(), "Scanner must NOT delete pending file")

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        scan_pending_pop_events(self.root)
        self.assertFalse((self.root / "pop" / "sent").exists(),
            "Scanner must NOT create sent/ directory")

    def test_does_not_create_quarantine_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        scan_pending_pop_events(self.root)
        self.assertFalse((self.root / "pop" / "quarantine").exists(),
            "Scanner must NOT create quarantine/ directory")

    def test_does_not_create_dry_run_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        scan_pending_pop_events(self.root)
        self.assertFalse((self.root / "pop" / "dry_run").exists(),
            "Scanner must NOT create dry_run/ directory")

    def test_no_http(self):
        import kso_sidecar_agent.pop_pickup as pp
        source = open(pp.__file__).read()
        for lib in ("urllib", "requests", "http.client", "httpx", "aiohttp"):
            self.assertNotIn(lib, source, f"HTTP lib '{lib}' in pop_pickup.py")

    def test_no_secret_config_token(self):
        """Scanner works without config/secret/token files."""
        _write_jsonl(self.root, [_make_record("draft")])
        result = scan_pending_pop_events(self.root)
        self.assertEqual(result.total_lines, 1)


class TestScanSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("draft")])

    def test_result_no_forbidden(self):
        result = scan_pending_pop_events(self.root)
        # Check all string fields of result
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            val = getattr(result, attr)
            if isinstance(val, str):
                lower = val.lower()
                for fb in ("token", "secret", "password", "api_key",
                          "file_path", "local_path", "127.0.0.1",
                          "device_code", "backend_base_url"):
                    self.assertNotIn(fb, lower,
                        f"Forbidden '{fb}' in result.{attr}")

    def test_result_no_filename(self):
        result = scan_pending_pop_events(self.root)
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            val = getattr(result, attr)
            if isinstance(val, str):
                self.assertNotIn("filename", val.lower())

    def test_result_no_manifest_item_id(self):
        result = scan_pending_pop_events(self.root)
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            val = getattr(result, attr)
            if isinstance(val, str):
                self.assertNotIn("manifest_item_id", val.lower())

    def test_result_no_sha256(self):
        result = scan_pending_pop_events(self.root)
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            val = getattr(result, attr)
            if isinstance(val, str):
                self.assertNotIn("sha256", val.lower())

    def test_no_stacktrace(self):
        """Scanner must not raise or produce stacktrace on empty dir."""
        tmp = Path(tempfile.mkdtemp())
        try:
            result = scan_pending_pop_events(tmp)
            self.assertEqual(result.status, SCAN_OK)
        except Exception as e:
            self.fail(f"Scanner raised: {e}")

    def test_no_full_manifest_in_result(self):
        result = scan_pending_pop_events(self.root)
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            val = getattr(result, attr)
            if isinstance(val, str):
                # Manifest version IDs are UUIDs — shouldn't appear
                self.assertNotIn("uuid-", val.lower())


if __name__ == "__main__":
    unittest.main()
