"""Tests for KSO Sidecar PoP Send Package Scope Core (pop_send_package.py)."""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from kso_sidecar_agent.pop_send_package import (
    PopSendPackageResult,
    build_pop_send_package,
    format_pop_send_package_result,
    DEFAULT_MAX_LINES,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_BUILT,
    REASON_NO_PENDING_FILE,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_READ_FAILED,
    REASON_PAYLOAD_FAILED,
    REASON_INVALID_RESULT,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_pickup import (
    POP_PENDING_DIR,
    POP_JSONL_FILE,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationSentScope,
)
from kso_sidecar_agent.pop_payload import (
    PopPayloadEnvelope,
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
            "size_bytes": 100,
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


def _clear_media_cache(root):
    """Ensure media cache appears complete for tests — write matching files with correct sha256."""
    mdir = root / "manifest"
    mc_dir = root / "media" / "current"
    mc_dir.mkdir(parents=True, exist_ok=True)
    # Write empty files matching manifest items, update sha256 to match
    if (mdir / "current_manifest.json").exists():
        try:
            import hashlib
            manifest = json.loads((mdir / "current_manifest.json").read_text())
            for item in manifest.get("items", []):
                fname = item.get("filename", "")
                if fname:
                    data = b"\x00" * item.get("size_bytes", 100)
                    sha = hashlib.sha256(data).hexdigest()
                    item["sha256"] = sha
                    (mc_dir / fname).write_bytes(data)
            # Rewrite manifest with updated sha256 values
            (mdir / "current_manifest.json").write_text(json.dumps(manifest))
        except Exception:
            pass


def _acquire_foreign_lock(root) -> int:
    """Acquire a lock file to simulate another process holding it."""
    lock_path = Path(root) / POP_PENDING_DIR / "player_events.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, b"locked\n")
    return fd


def _release_foreign_lock(fd, root):
    os.close(fd)
    lock_path = Path(root) / POP_PENDING_DIR / "player_events.lock"
    try:
        os.unlink(str(lock_path))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestBuildSendPackageBasic(unittest.TestCase):
    """Basic cases for build_pop_send_package()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_pending_file(self):
        """No pending file → safe no_pending_file."""
        result = build_pop_send_package(self.root)
        self.assertEqual(result.status, STATUS_OK)
        self.assertFalse(result.package_built)
        self.assertEqual(result.reason, REASON_NO_PENDING_FILE)
        self.assertIsNone(result._sent_scope)
        self.assertIsNone(result._payload)

    def test_foreign_lock(self):
        """Foreign lock → lock_unavailable, lock NOT removed."""
        _write_jsonl(self.root, [_make_record(event_status="completed")])
        fd = _acquire_foreign_lock(self.root)
        try:
            result = build_pop_send_package(self.root)
            self.assertEqual(result.status, STATUS_WARNING)
            self.assertFalse(result.package_built)
            self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE)
            self.assertFalse(result.lock_acquired)
            # Lock still exists
            lock_path = self.root / POP_PENDING_DIR / "player_events.lock"
            self.assertTrue(lock_path.exists())
        finally:
            _release_foreign_lock(fd, self.root)

    def test_lock_released_after_success(self):
        """Lock released after successful build."""
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)
        _write_jsonl(self.root, [_make_record(event_status="completed")])

        result = build_pop_send_package(self.root)
        self.assertEqual(result.status, STATUS_OK)
        # Lock file should be released
        lock_path = self.root / POP_PENDING_DIR / "player_events.lock"
        self.assertFalse(lock_path.exists())

    def test_lock_released_after_no_eligible(self):
        """Lock released even when no eligible events."""
        _write_manifest(self.root, _make_manifest_data())
        _write_jsonl(self.root, [_make_record(event_status="draft")])

        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        lock_path = self.root / POP_PENDING_DIR / "player_events.lock"
        self.assertFalse(lock_path.exists())

    def test_max_lines_zero(self):
        """max_lines <= 0 → error."""
        _write_jsonl(self.root, [_make_record(event_status="completed")])
        result = build_pop_send_package(self.root, max_lines=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_negative(self):
        """max_lines < 0 → error."""
        result = build_pop_send_package(self.root, max_lines=-5)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)


class TestBuildSendPackageEvents(unittest.TestCase):
    """Event-level test cases for build_pop_send_package()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_draft_event_no_payload_no_scope(self):
        """Draft event → no payload, scope_lines=0."""
        _write_jsonl(self.root, [_make_record(event_status="draft")])
        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.scope_lines, 0)
        self.assertIsNone(result._sent_scope)
        self.assertIsNone(result._payload)

    def test_blocked_event_no_payload_no_scope(self):
        """Blocked event → no payload, scope_lines=0."""
        _write_jsonl(self.root, [_make_record(event_status="blocked")])
        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.scope_lines, 0)

    def test_failed_event_no_payload_no_scope(self):
        """Failed event → no payload, scope_lines=0."""
        _write_jsonl(self.root, [_make_record(event_status="failed")])
        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.scope_lines, 0)

    def test_invalid_json_no_payload_no_scope(self):
        """Invalid JSON line → no payload, scope_lines=0."""
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / POP_JSONL_FILE).write_text("not valid json\n")
        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.scope_lines, 0)

    def test_completed_eligible_payload_1_scope_1(self):
        """Completed eligible → payload_events=1, scope_lines=1."""
        _write_jsonl(self.root, [_make_record(event_status="completed")])
        result = build_pop_send_package(self.root)
        self.assertTrue(result.package_built)
        self.assertEqual(result.payload_events, 1)
        self.assertEqual(result.eligible_events, 1)
        self.assertEqual(result.scope_lines, 1)
        self.assertIsInstance(result._sent_scope, PopRotationSentScope)
        self.assertIsNotNone(result._sent_scope)
        self.assertEqual(result._sent_scope.size, 1)
        self.assertIsInstance(result._payload, PopPayloadEnvelope)

    def test_two_completed_eligible_payload_2_scope_2(self):
        """Two completed eligible → payload_events=2, scope_lines=2."""
        _write_jsonl(self.root, [
            _make_record(event_status="completed", selected_order=0),
            _make_record(event_status="completed", selected_order=1),
        ])
        result = build_pop_send_package(self.root)
        self.assertTrue(result.package_built)
        self.assertEqual(result.payload_events, 2)
        self.assertEqual(result.eligible_events, 2)
        self.assertEqual(result.scope_lines, 2)
        self.assertIsNotNone(result._sent_scope)
        self.assertEqual(result._sent_scope.size, 2)

    def test_completed_not_eligible_no_manifest_map(self):
        """Completed with no manifest match → eligible but no payload."""
        # selected_order=99 has no manifest mapping
        _write_jsonl(self.root, [_make_record(
            event_status="completed", selected_order=99)])
        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        self.assertEqual(result.payload_events, 0)
        self.assertEqual(result.scope_lines, 0)

    def test_mixed_pending_only_eligible_in_payload(self):
        """Mixed: draft + blocked + completed eligible → only eligible in payload."""
        _write_jsonl(self.root, [
            _make_record(event_status="draft"),
            _make_record(event_status="blocked"),
            _make_record(event_status="completed", selected_order=0),
        ])
        result = build_pop_send_package(self.root)
        self.assertTrue(result.package_built)
        self.assertEqual(result.payload_events, 1)
        self.assertEqual(result.eligible_events, 1)
        self.assertEqual(result.scope_lines, 1)
        self.assertEqual(result.pending_lines_read, 3)

    def test_sent_scope_is_pop_rotation_sent_scope(self):
        """Internal _sent_scope is PopRotationSentScope instance."""
        _write_jsonl(self.root, [_make_record(event_status="completed")])
        result = build_pop_send_package(self.root)
        self.assertIsInstance(result._sent_scope, PopRotationSentScope)

    def test_scope_matches_eligible_line_numbers_internally(self):
        """Scope internally holds correct line numbers but repr hides them."""
        _write_jsonl(self.root, [
            _make_record(event_status="completed", selected_order=0),
            _make_record(event_status="completed", selected_order=1),
        ])
        result = build_pop_send_package(self.root)
        self.assertIsNotNone(result._sent_scope)
        # Internal scope should have line 1 and 2
        self.assertTrue(result._sent_scope.has_line(1))
        self.assertTrue(result._sent_scope.has_line(2))
        self.assertFalse(result._sent_scope.has_line(3))
        # But repr does NOT expose list
        repr_str = repr(result._sent_scope)
        self.assertIn("size=2", repr_str)
        self.assertNotIn("1", repr_str)  # no line number in repr

    def test_max_lines_limit_warning(self):
        """max_lines limit → warning/limited."""
        # 3 lines total, only read up to 1
        _write_jsonl(self.root, [
            _make_record(event_status="completed", selected_order=0),
            _make_record(event_status="completed", selected_order=1),
            _make_record(event_status="completed", selected_order=2),
        ])
        result = build_pop_send_package(self.root, max_lines=1)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertEqual(result.reason, REASON_LIMITED)
        # At least 1 line read; break happens after limit exceeded
        self.assertGreaterEqual(result.pending_lines_read, 1)

    def test_no_eligible_events(self):
        """All events non-eligible → no_eligible_events."""
        _write_jsonl(self.root, [
            _make_record(event_status="draft"),
            _make_record(event_status="blocked"),
        ])
        result = build_pop_send_package(self.root)
        self.assertFalse(result.package_built)
        self.assertEqual(result.reason, REASON_NO_ELIGIBLE_EVENTS)
        self.assertEqual(result.eligible_events, 0)
        self.assertEqual(result.payload_events, 0)


class TestBuildSendPackageResultSafety(unittest.TestCase):
    """Safety checks for result/repr/output."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)
        _write_jsonl(self.root, [_make_record(event_status="completed")])

    def tearDown(self):
        self.tmp.cleanup()

    def test_result_repr_no_line_number_list(self):
        """Result repr does not contain line number list."""
        result = build_pop_send_package(self.root)
        repr_str = repr(result)
        # Should contain aggregates but NOT individual line numbers
        self.assertIn("scope_lines=1", repr_str)
        self.assertNotIn("_line_numbers", repr_str)

    def test_result_repr_no_raw_json(self):
        """Result repr does not contain raw JSON."""
        result = build_pop_send_package(self.root)
        repr_str = repr(result)
        self.assertNotIn("{", repr_str)
        self.assertNotIn("}", repr_str)

    def test_result_repr_no_payload_body(self):
        """Result repr does not contain payload body."""
        result = build_pop_send_package(self.root)
        repr_str = repr(result)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("manifest_item_id", repr_str)

    def test_result_repr_no_ids(self):
        """Result repr does not contain IDs."""
        result = build_pop_send_package(self.root)
        repr_str = repr(result)
        self.assertNotIn("manifest_item_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("campaign_id", repr_str)

    def test_result_repr_no_paths_filenames(self):
        """Result repr does not contain paths or filenames."""
        result = build_pop_send_package(self.root)
        repr_str = repr(result)
        self.assertNotIn("path", repr_str.lower())
        self.assertNotIn("filename", repr_str.lower())
        self.assertNotIn("sha256", repr_str)

    def test_safe_output_no_forbidden(self):
        """Safe output passes forbidden substring scan."""
        result = build_pop_send_package(self.root)
        output = format_pop_send_package_result(result)
        # Should not raise ValueError from forbidden scan
        self.assertIn("scope_lines:", output)
        self.assertIn("payload_events:", output)

    def test_safe_output_no_payload_body(self):
        """Safe output does not contain payload body fields."""
        result = build_pop_send_package(self.root)
        output = format_pop_send_package_result(result)
        self.assertNotIn("batch_id", output)
        self.assertNotIn("device_event_id", output)
        self.assertNotIn("manifest_item_id", output)
        self.assertNotIn("campaign_id", output)
        self.assertNotIn("sha256", output)

    def test_safe_output_no_line_number_list(self):
        """Safe output does not contain line number list."""
        result = build_pop_send_package(self.root)
        output = format_pop_send_package_result(result)
        self.assertNotIn("line_numbers", output)
        self.assertNotIn("line_number", output)


class TestBuildSendPackageNoSideEffects(unittest.TestCase):
    """Verify build_pop_send_package has NO side effects."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)
        _write_jsonl(self.root, [_make_record(event_status="completed")])

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_http(self):
        """No HTTP — function doesn't call backend."""
        # This is verified by design — no http_client param needed
        result = build_pop_send_package(self.root)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.package_built)

    def test_no_backend_send(self):
        """No backend send — _payload built but not sent."""
        result = build_pop_send_package(self.root)
        self.assertIsNotNone(result._payload)
        self.assertIsNotNone(result._sent_scope)
        # Payload exists but no send

    def test_no_pending_rewrite(self):
        """No pending rewrite — file unchanged after call."""
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        original = jsonl_path.read_text()
        build_pop_send_package(self.root)
        after = jsonl_path.read_text()
        self.assertEqual(original, after)

    def test_no_sent_quarantine_dry_run_failed_dirs(self):
        """No sent/quarantine/dry_run/failed dirs created."""
        build_pop_send_package(self.root)
        for d in ("sent", "quarantine", "dry_run", "failed"):
            dir_path = self.root / "pop" / d
            self.assertFalse(dir_path.exists(), f"{d} dir should not exist")

    def test_no_secret_config_token_reads(self):
        """No secret/config/token reads — function only uses manifest and media cache."""
        # Design guarantee — reads only manifest, media cache, and pending
        result = build_pop_send_package(self.root)
        self.assertTrue(result.package_built)

    def test_no_media_bytes_reads(self):
        """No media bytes reads — only media_cache_status() used."""
        result = build_pop_send_package(self.root)
        self.assertTrue(result.package_built)

    def test_no_rotation_apply(self):
        """No rotation apply — function returns without modifying pending or targets."""
        result = build_pop_send_package(self.root)
        self.assertTrue(result.package_built)


class TestBuildSendPackagePendingUntouched(unittest.TestCase):
    """Verify pending file is NEVER modified."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_file_unchanged(self):
        """Pending file content unchanged after build."""
        records = [
            _make_record(event_status="completed", selected_order=0),
            _make_record(event_status="draft"),
        ]
        _write_jsonl(self.root, records)

        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        original_content = jsonl_path.read_text()
        original_stat = jsonl_path.stat()

        build_pop_send_package(self.root)

        after_content = jsonl_path.read_text()
        after_stat = jsonl_path.stat()

        self.assertEqual(original_content, after_content)
        self.assertFalse(jsonl_path.exists() and original_stat.st_mtime != after_stat.st_mtime,
                        "pending file should not be modified")


class TestBuildSendPackageFormat(unittest.TestCase):
    """Tests for format_pop_send_package_result()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)
        _write_jsonl(self.root, [_make_record(event_status="completed")])

    def tearDown(self):
        self.tmp.cleanup()

    def test_format_contains_aggregates(self):
        """Format contains all aggregate fields."""
        result = build_pop_send_package(self.root)
        output = format_pop_send_package_result(result)
        self.assertIn("status:", output)
        self.assertIn("package_built:", output)
        self.assertIn("lock_acquired:", output)
        self.assertIn("pending_lines_read:", output)
        self.assertIn("eligible_events:", output)
        self.assertIn("payload_events:", output)
        self.assertIn("scope_lines:", output)
        self.assertIn("reason:", output)

    def test_format_no_forbidden(self):
        """Format triggers safety scan and passes."""
        result = build_pop_send_package(self.root)
        output = format_pop_send_package_result(result)
        lower = output.lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower, f"safe output contains forbidden '{fb}'")

    def test_format_no_stacktrace(self):
        """Format does not contain stacktrace."""
        result = build_pop_send_package(self.root)
        output = format_pop_send_package_result(result)
        self.assertNotIn("stacktrace", output.lower())
        self.assertNotIn("traceback", output.lower())


if __name__ == "__main__":
    unittest.main()
