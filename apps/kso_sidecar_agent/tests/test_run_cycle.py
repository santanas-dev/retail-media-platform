"""Tests for run_cycle.py — skeleton only, no real backend, no HTTP."""

import json
import hashlib as _hl
import tempfile
import unittest
from pathlib import Path

from kso_sidecar_agent.run_cycle import (
    ALLOWED_CYCLE_STATUSES,
    FORBIDDEN_SUBSTRINGS,
    RunCycleContext,
    RunCycleOptions,
    RunCycleResult,
    RunCycleStepResult,
    _build_local_readiness_steps,
    _check_forbidden,
    _is_local_ready,
    _redact_forbidden,
    build_cycle_result,
    build_run_cycle_context,
    classify_cycle_status,
    evaluate_local_readiness,
    run_once,
    update_cycle_status,
)

TEST_CONTENT = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_SHA = _hl.sha256(TEST_CONTENT).hexdigest()


def _setup_full_root(root, with_media=True):
    """Set up a complete agent root with config, runtime_config, manifest, media."""
    from kso_sidecar_agent.local_file_store import init_local_root
    from kso_sidecar_agent.local_config import write_config

    init_local_root(root)

    config_data = {
        "backend_base_url": "http://127.0.0.1:8080",
        "device_code": "a-05954",
        "tls_verify": True,
        "request_timeout_sec": 10,
        "local_interface_version": "1.0",
    }
    write_config(root, config_data)

    # Runtime config
    rc_path = Path(root) / "config" / "runtime_config.json"
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    rc_data = {
        "status": "ok",
        "config_hash": "a" * 64,
        "etag": "etag-" + "a" * 12,
        "generated_at": "2026-06-19T10:00:00Z",
        "fetched_at": "2026-06-19T10:00:00Z",
        "config": {"key1": "value1"},
    }
    rc_path.write_text(json.dumps(rc_data))

    # Manifest
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    item_id = "11111111-1111-1111-1111-111111111111"
    manifest_data = {
        "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "manifest_hash": "c" * 64,
        "source": "current",
        "generated_at": "2026-06-19T10:00:00Z",
        "fetched_at": "2026-06-19T10:00:00Z",
        "items": [
            {
                "manifest_item_id": item_id,
                "filename": f"{item_id}.png",
                "sha256": TEST_SHA,
                "content_type": "image/png",
                "size_bytes": len(TEST_CONTENT) if with_media else 200,
                "duration_ms": 5000,
                "order": 0,
            },
        ],
    }
    (manifest_dir / "current_manifest.json").write_text(json.dumps(manifest_data))

    # Media
    if with_media:
        media_current = Path(root) / "media" / "current"
        media_current.mkdir(parents=True, exist_ok=True)
        (media_current / f"{item_id}.png").write_bytes(TEST_CONTENT)


def _setup_config_only(root):
    """Set up root with only config (no manifest, no media)."""
    from kso_sidecar_agent.local_file_store import init_local_root
    from kso_sidecar_agent.local_config import write_config

    init_local_root(root)
    config_data = {
        "backend_base_url": "http://127.0.0.1:8080",
        "device_code": "a-05954",
        "tls_verify": True,
        "request_timeout_sec": 10,
        "local_interface_version": "1.0",
    }
    write_config(root, config_data)


# ══════════════════════════════════════════════════════════════════════
# Tests: RunCycleOptions
# ══════════════════════════════════════════════════════════════════════

class TestRunCycleOptions(unittest.TestCase):

    def test_default_options_valid(self):
        opts = RunCycleOptions()
        self.assertFalse(opts.retry_auth)
        self.assertFalse(opts.skip_media)
        self.assertEqual(opts.max_cycle_sec, 120)

    def test_max_cycle_sec_reject_zero(self):
        with self.assertRaises(ValueError):
            RunCycleOptions(max_cycle_sec=0)

    def test_max_cycle_sec_reject_too_high(self):
        with self.assertRaises(ValueError):
            RunCycleOptions(max_cycle_sec=601)

    def test_max_cycle_sec_valid_boundaries(self):
        opts1 = RunCycleOptions(max_cycle_sec=1)
        self.assertEqual(opts1.max_cycle_sec, 1)

        opts2 = RunCycleOptions(max_cycle_sec=600)
        self.assertEqual(opts2.max_cycle_sec, 600)


# ══════════════════════════════════════════════════════════════════════
# Tests: RunCycleStepResult
# ══════════════════════════════════════════════════════════════════════

class TestRunCycleStepResult(unittest.TestCase):

    def test_basic_step_ok(self):
        step = RunCycleStepResult(name="preflight", status="ok")
        self.assertEqual(step.name, "preflight")
        self.assertEqual(step.status, "ok")
        self.assertFalse(step.fatal)

    def test_step_redacts_forbidden_message(self):
        step = RunCycleStepResult(
            name="auth",
            status="error",
            message="token expired, use local_path",
        )
        self.assertNotIn("token", step.message.lower())
        self.assertNotIn("local_path", step.message.lower())
        self.assertIn("[REDACTED]", step.message)

    def test_step_rejects_forbidden_name(self):
        with self.assertRaises(ValueError):
            RunCycleStepResult(name="local_path_check", status="ok")

    def test_step_safe_details_filtered(self):
        step = RunCycleStepResult(
            name="test",
            status="ok",
            safe_details={
                "items_count": 5,
                "bad_key with spaces": "value",
                "token_field": "should be excluded",
                "valid_key": "clean value",
            },
        )
        # bad_key with spaces rejected (regex mismatch)
        self.assertNotIn("bad_key with spaces", step.safe_details)
        # token_field rejected (key contains forbidden "token")
        self.assertNotIn("token_field", step.safe_details)
        # valid_key preserved
        self.assertIn("valid_key", step.safe_details)
        self.assertEqual(step.safe_details["items_count"], 5)


# ══════════════════════════════════════════════════════════════════════
# Tests: RunCycleResult
# ══════════════════════════════════════════════════════════════════════

class TestRunCycleResult(unittest.TestCase):

    def test_result_ok(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="ok",
            steps=steps,
            media_cache_complete=True,
        )
        self.assertEqual(result.status, "ok")

    def test_safe_summary_no_forbidden(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(status="ok", steps=steps)
        summary = result.safe_summary()
        summary_str = str(summary).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, summary_str, f"Found forbidden '{fb}' in safe_summary")

    def test_safe_summary_has_step_names(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="auth", status="ok"),
        ]
        result = RunCycleResult(status="ok", steps=steps)
        summary = result.safe_summary()
        self.assertEqual(len(summary["steps"]), 2)
        self.assertEqual(summary["steps"][0]["name"], "preflight")

    def test_cycle_block_no_forbidden(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="ok",
            steps=steps,
            media_cache_complete=True,
            media_items_total=5,
            media_items_cached=5,
        )
        block = result._cycle_block()
        block_str = str(block).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, block_str, f"Found forbidden '{fb}' in _cycle_block")

    def test_cycle_block_contains_required_fields(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="ok",
            steps=steps,
            finished_at="2026-06-19T10:00:00Z",
            duration_ms=1234.0,
        )
        block = result._cycle_block()
        self.assertEqual(block["last_cycle_status"], "ok")
        self.assertEqual(block["last_cycle_duration_ms"], 1234)
        self.assertIsNone(block["last_error_code"])

    def test_cycle_block_with_status_fields(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="ok",
            steps=steps,
            runtime_config_status="valid",
            manifest_status="valid",
        )
        block = result._cycle_block()
        self.assertEqual(block["runtime_config_status"], "valid")
        self.assertEqual(block["manifest_status"], "valid")

    def test_cycle_block_with_error_code(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="error",
            steps=steps,
            last_error_code="AUTH_FAIL",
        )
        block = result._cycle_block()
        self.assertEqual(block["last_error_code"], "AUTH_FAIL")

    def test_reject_invalid_status(self):
        with self.assertRaises(ValueError):
            RunCycleResult(status="invalid_status", steps=[])

    def test_reject_forbidden_error_code(self):
        with self.assertRaises(ValueError):
            RunCycleResult(status="error", steps=[], last_error_code="token_expired")

    def test_reject_forbidden_runtime_config_status(self):
        with self.assertRaises(ValueError):
            RunCycleResult(status="ok", steps=[], runtime_config_status="local_path_value")

    def test_reject_forbidden_manifest_status(self):
        with self.assertRaises(ValueError):
            RunCycleResult(status="ok", steps=[], manifest_status="token_value")


# ══════════════════════════════════════════════════════════════════════
# Tests: build_run_cycle_context
# ══════════════════════════════════════════════════════════════════════

class TestBuildContext(unittest.TestCase):

    def test_creates_context_with_run_id(self):
        ctx = build_run_cycle_context("/tmp/test-root")
        self.assertIsInstance(ctx, RunCycleContext)
        self.assertEqual(ctx.root, "/tmp/test-root")
        self.assertNotEqual(ctx.run_id, "")
        self.assertIsInstance(ctx.options, RunCycleOptions)

    def test_run_id_is_valid_uuid(self):
        import uuid
        ctx = build_run_cycle_context("/tmp/test-root")
        try:
            uuid.UUID(ctx.run_id)
        except ValueError:
            self.fail("run_id is not a valid UUID")

    def test_custom_options(self):
        opts = RunCycleOptions(retry_auth=True, max_cycle_sec=60)
        ctx = build_run_cycle_context("/tmp/test-root", options=opts)
        self.assertTrue(ctx.options.retry_auth)
        self.assertEqual(ctx.options.max_cycle_sec, 60)

    def test_root_forbidden_reject(self):
        with self.assertRaises(ValueError):
            build_run_cycle_context("/tmp/token/root")


# ══════════════════════════════════════════════════════════════════════
# Tests: classify_cycle_status
# ══════════════════════════════════════════════════════════════════════

class TestClassifyCycleStatus(unittest.TestCase):

    def test_all_ok(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="auth", status="ok"),
        ]
        self.assertEqual(classify_cycle_status(steps), "ok")

    def test_warning_step(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="heartbeat", status="warning"),
        ]
        self.assertEqual(classify_cycle_status(steps), "warning")

    def test_non_fatal_error(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="sync_runtime_config", status="error", fatal=False),
        ]
        self.assertEqual(classify_cycle_status(steps), "warning")

    def test_fatal_error(self):
        steps = [
            RunCycleStepResult(name="preflight", status="error", fatal=True),
        ]
        self.assertEqual(classify_cycle_status(steps), "error")

    def test_degraded(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="auth", status="degraded"),
        ]
        self.assertEqual(classify_cycle_status(steps), "degraded")

    def test_fatal_trumps_degraded(self):
        steps = [
            RunCycleStepResult(name="preflight", status="error", fatal=True),
            RunCycleStepResult(name="auth", status="degraded"),
        ]
        self.assertEqual(classify_cycle_status(steps), "error")

    def test_media_cache_incomplete(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="sync_media", status="ok"),
        ]
        self.assertEqual(
            classify_cycle_status(steps, media_cache_complete=False),
            "warning",
        )

    def test_empty_steps(self):
        self.assertEqual(classify_cycle_status([]), "ok")


# ══════════════════════════════════════════════════════════════════════
# Tests: build_cycle_result
# ══════════════════════════════════════════════════════════════════════

class TestBuildCycleResult(unittest.TestCase):

    def setUp(self):
        self.ctx = build_run_cycle_context("/tmp/test-root")

    def test_basic_result(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = build_cycle_result(self.ctx, steps)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.steps), 1)
        self.assertGreater(len(result.finished_at), 0)

    def test_result_duration(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = build_cycle_result(self.ctx, steps)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_media_status_in_result(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        media_status = {
            "items_total": 5,
            "items_cached": 4,
            "items_missing": 1,
            "items_invalid_hash": 0,
            "items_invalid_size": 0,
            "cache_complete": False,
        }
        result = build_cycle_result(self.ctx, steps, media_status=media_status)
        self.assertEqual(result.media_items_total, 5)
        self.assertEqual(result.media_items_cached, 4)
        self.assertEqual(result.media_items_missing, 1)
        self.assertFalse(result.media_cache_complete)
        self.assertEqual(result.status, "warning")  # incomplete

    def test_last_error_code(self):
        steps = [
            RunCycleStepResult(name="preflight", status="ok"),
            RunCycleStepResult(name="sync_manifest", status="error", fatal=False),
        ]
        result = build_cycle_result(self.ctx, steps)
        self.assertEqual(result.last_error_code, "SYNC_MANIFEST")

    def test_derives_status_fields_from_steps(self):
        steps = [
            RunCycleStepResult(name="runtime_config", status="ok", safe_details={"present": True, "valid": True}),
            RunCycleStepResult(name="manifest", status="ok", safe_details={"present": True, "valid": True}),
        ]
        result = build_cycle_result(self.ctx, steps)
        self.assertEqual(result.runtime_config_status, "valid")
        self.assertEqual(result.manifest_status, "valid")


# ══════════════════════════════════════════════════════════════════════
# Tests: update_cycle_status
# ══════════════════════════════════════════════════════════════════════

class TestUpdateCycleStatus(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "status").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_status(self, data):
        path = self.root / "status" / "agent_status.json"
        path.write_text(json.dumps(data))

    def _read_status(self):
        path = self.root / "status" / "agent_status.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def test_writes_cycle_block(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="ok",
            steps=steps,
            duration_ms=500.0,
            media_cache_complete=True,
            media_items_total=3,
            media_items_cached=3,
        )

        update_cycle_status(self.root, result)
        data = self._read_status()
        self.assertIn("_cycle", data)
        self.assertEqual(data["_cycle"]["last_cycle_status"], "ok")
        self.assertEqual(data["_cycle"]["media_items_total"], 3)

    def test_preserves_existing_fields(self):
        existing = {
            "status": "running",
            "updated_at": "2026-06-19T10:00:00Z",
            "offline_mode": False,
            "cached_items": 5,
            "invalid_hash_items": 0,
            "errors": [],
        }
        self._write_status(existing)

        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(status="ok", steps=steps)

        update_cycle_status(self.root, result)
        data = self._read_status()

        self.assertEqual(data["status"], "running")
        self.assertEqual(data["cached_items"], 5)
        self.assertEqual(data["offline_mode"], False)
        self.assertIn("_cycle", data)
        self.assertEqual(data["_cycle"]["last_cycle_status"], "ok")

    def test_no_forbidden_in_cycle_block(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="ok",
            steps=steps,
            duration_ms=100.0,
        )

        update_cycle_status(self.root, result)
        data = self._read_status()
        data_str = json.dumps(data).lower()

        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(
                fb, data_str,
                f"Forbidden '{fb}' found in agent_status after update_cycle_status"
            )

    def test_cycle_block_fields_present(self):
        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(
            status="warning",
            steps=steps,
            finished_at="2026-06-19T12:00:00Z",
            duration_ms=2000.0,
            runtime_config_status="valid",
            manifest_status="missing",
            media_cache_complete=False,
            media_items_total=5,
            media_items_cached=3,
            media_items_missing=2,
            media_items_failed=0,
            last_error_code="HEARTBEAT_FAIL",
        )

        update_cycle_status(self.root, result)
        data = self._read_status()
        block = data["_cycle"]

        self.assertEqual(block["last_cycle_status"], "warning")
        self.assertEqual(block["last_cycle_duration_ms"], 2000)
        self.assertEqual(block["runtime_config_status"], "valid")
        self.assertEqual(block["manifest_status"], "missing")
        self.assertFalse(block["media_cache_complete"])
        self.assertEqual(block["media_items_total"], 5)
        self.assertEqual(block["media_items_cached"], 3)
        self.assertEqual(block["media_items_missing"], 2)
        self.assertEqual(block["last_error_code"], "HEARTBEAT_FAIL")

    def test_redacts_forbidden_in_existing_status(self):
        existing = {
            "status": "running",
            "local_path_note": "some value",
        }
        self._write_status(existing)

        steps = [RunCycleStepResult(name="preflight", status="ok")]
        result = RunCycleResult(status="ok", steps=steps)

        with self.assertRaises(ValueError):
            update_cycle_status(self.root, result)


# ══════════════════════════════════════════════════════════════════════
# Tests: evaluate_local_readiness
# ══════════════════════════════════════════════════════════════════════

class TestEvaluateLocalReadiness(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_root(self):
        readiness = evaluate_local_readiness(self.root)
        self.assertTrue(readiness["root_exists"])
        self.assertFalse(readiness["config_present"])

    def test_full_ready_root(self):
        _setup_full_root(self.root)
        readiness = evaluate_local_readiness(self.root)

        self.assertTrue(readiness["root_exists"])
        self.assertTrue(readiness["config_present"])
        self.assertTrue(readiness["config_valid"])

        self.assertTrue(readiness["runtime_config_present"])
        self.assertTrue(readiness["runtime_config_valid"])

        self.assertTrue(readiness["manifest_present"])
        self.assertTrue(readiness["manifest_valid"])
        self.assertEqual(readiness["manifest_items_count"], 1)

        self.assertIsNotNone(readiness["media_status"])
        self.assertTrue(readiness["media_cache_complete"])

    def test_config_only_no_manifest(self):
        _setup_config_only(self.root)
        readiness = evaluate_local_readiness(self.root)

        self.assertTrue(readiness["config_valid"])
        self.assertFalse(readiness["manifest_present"])
        self.assertIsNone(readiness["media_cache_complete"])
        self.assertTrue(_is_local_ready(readiness) is False)

    def test_is_local_ready_true(self):
        _setup_full_root(self.root)
        readiness = evaluate_local_readiness(self.root)
        self.assertTrue(_is_local_ready(readiness))

    def test_is_local_ready_false_incomplete(self):
        _setup_full_root(self.root, with_media=False)
        readiness = evaluate_local_readiness(self.root)
        self.assertFalse(_is_local_ready(readiness))


# ══════════════════════════════════════════════════════════════════════
# Tests: _build_local_readiness_steps
# ══════════════════════════════════════════════════════════════════════

class TestBuildLocalReadinessSteps(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _find_step(self, steps, name):
        return next((s for s in steps if s.name == name), None)

    def test_full_ready(self):
        _setup_full_root(self.root)
        steps = _build_local_readiness_steps(self.root)

        config_s = self._find_step(steps, "local_config")
        self.assertEqual(config_s.status, "ok")

        rc_s = self._find_step(steps, "runtime_config")
        self.assertEqual(rc_s.status, "ok")

        manifest_s = self._find_step(steps, "manifest")
        self.assertEqual(manifest_s.status, "ok")

        media_s = self._find_step(steps, "media_cache")
        self.assertEqual(media_s.status, "ok")

    def test_missing_config(self):
        # Root exists but no config
        (self.root / "status").mkdir(parents=True, exist_ok=True)
        steps = _build_local_readiness_steps(self.root)

        config_s = self._find_step(steps, "local_config")
        self.assertEqual(config_s.status, "error")
        self.assertTrue(config_s.fatal)

    def test_missing_runtime_config(self):
        _setup_config_only(self.root)
        steps = _build_local_readiness_steps(self.root)

        rc_s = self._find_step(steps, "runtime_config")
        self.assertEqual(rc_s.status, "warning")
        self.assertFalse(rc_s.fatal)

    def test_missing_manifest(self):
        _setup_config_only(self.root)
        steps = _build_local_readiness_steps(self.root)

        manifest_s = self._find_step(steps, "manifest")
        self.assertEqual(manifest_s.status, "warning")

    def test_media_cache_skipped_when_no_manifest(self):
        _setup_config_only(self.root)
        steps = _build_local_readiness_steps(self.root)

        media_s = self._find_step(steps, "media_cache")
        self.assertEqual(media_s.status, "skipped")

    def test_safe_details_no_config(self):
        (self.root / "status").mkdir(parents=True, exist_ok=True)
        steps = _build_local_readiness_steps(self.root)

        for s in steps:
            details_str = str(s.safe_details).lower()
            for fb in FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(fb, details_str, f"Forbidden '{fb}' in {s.name} safe_details")

    def test_safe_details_no_forbidden_in_full_root(self):
        _setup_full_root(self.root)
        steps = _build_local_readiness_steps(self.root)

        for s in steps:
            details_str = str(s.safe_details).lower()
            for fb in FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(fb, details_str, f"Forbidden '{fb}' in {s.name} safe_details")


# ══════════════════════════════════════════════════════════════════════
# Tests: run_once with local readiness
# ══════════════════════════════════════════════════════════════════════

class TestRunOnceLocalReadiness(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _find_step(self, result, name):
        return next((s for s in result.steps if s.name == name), None)

    def test_full_ready_ok(self):
        _setup_full_root(self.root)
        result = run_once(self.root)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.media_cache_complete)

    def test_missing_config_error(self):
        (self.root / "status").mkdir(parents=True, exist_ok=True)
        result = run_once(self.root)
        self.assertEqual(result.status, "error")
        config_s = self._find_step(result, "local_config")
        self.assertIsNotNone(config_s)
        self.assertEqual(config_s.status, "error")
        self.assertTrue(config_s.fatal)

    def test_config_only_warning(self):
        _setup_config_only(self.root)
        result = run_once(self.root)
        # No manifest → manifest:warning, no rc → rc:warning
        # status = warning (non-fatal errors)
        self.assertIn(result.status, ("warning",))
        manifest_s = self._find_step(result, "manifest")
        self.assertEqual(manifest_s.status, "warning")

    def test_missing_runtime_config_non_fatal(self):
        _setup_full_root(self.root)
        # Remove runtime config
        rc_path = self.root / "config" / "runtime_config.json"
        rc_path.unlink()

        result = run_once(self.root)
        rc_s = self._find_step(result, "runtime_config")
        self.assertEqual(rc_s.status, "warning")
        self.assertFalse(rc_s.fatal)
        # Manifest + media still ok → status ok (only non-fatal warnings)
        self.assertIn(result.status, ("ok", "warning"))

    def test_missing_media_warning(self):
        _setup_full_root(self.root, with_media=False)
        result = run_once(self.root)
        media_s = self._find_step(result, "media_cache")
        self.assertEqual(media_s.status, "warning")
        self.assertFalse(result.media_cache_complete)
        self.assertIn(result.status, ("warning",))

    def test_corrupted_media_error(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        _setup_full_root(self.root, with_media=True)
        # Corrupt the media file
        item_id = "11111111-1111-1111-1111-111111111111"
        media_file = self.root / "media" / "current" / f"{item_id}.png"
        media_file.write_bytes(b"corrupted data")

        result = run_once(self.root)
        media_s = self._find_step(result, "media_cache")
        self.assertEqual(media_s.status, "error")
        self.assertFalse(result.media_cache_complete)
        self.assertIn(result.status, ("warning",))

    def test_cycle_block_has_media_fields(self):
        _setup_full_root(self.root)
        result = run_once(self.root)

        status_path = self.root / "status" / "agent_status.json"
        data = json.loads(status_path.read_text())
        block = data["_cycle"]

        self.assertEqual(block["media_items_total"], 1)
        self.assertEqual(block["media_items_cached"], 1)
        self.assertEqual(block["media_items_missing"], 0)
        self.assertTrue(block["media_cache_complete"])

    def test_cycle_block_has_status_fields(self):
        _setup_full_root(self.root)
        result = run_once(self.root)

        status_path = self.root / "status" / "agent_status.json"
        data = json.loads(status_path.read_text())
        block = data["_cycle"]

        self.assertEqual(block["runtime_config_status"], "valid")
        self.assertEqual(block["manifest_status"], "valid")

    def test_no_forbidden_in_agent_status(self):
        _setup_full_root(self.root)
        run_once(self.root)

        status_path = self.root / "status" / "agent_status.json"
        data = json.loads(status_path.read_text())
        data_str = json.dumps(data).lower()

        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, data_str, f"Forbidden '{fb}' in agent_status")

    def test_safe_details_no_full_config(self):
        _setup_full_root(self.root)
        result = run_once(self.root)

        for s in result.steps:
            details_str = str(s.safe_details)
            self.assertNotIn("backend_base_url", details_str)
            self.assertNotIn("device_code", details_str)

    def test_safe_details_no_forbidden(self):
        _setup_full_root(self.root)
        result = run_once(self.root)

        for s in result.steps:
            details_str = str(s.safe_details).lower()
            for fb in FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(fb, details_str, f"Forbidden '{fb}' in {s.name} safe_details")

    def test_no_backend_calls(self):
        _setup_full_root(self.root)
        result = run_once(self.root)
        self.assertIsInstance(result, RunCycleResult)

    def test_manifest_error_non_fatal(self):
        _setup_full_root(self.root)
        # Invalid manifest
        manifest_path = self.root / "manifest" / "current_manifest.json"
        manifest_path.write_text("not valid json {{{")

        result = run_once(self.root)
        manifest_s = self._find_step(result, "manifest")
        self.assertEqual(manifest_s.status, "error")
        self.assertFalse(manifest_s.fatal)

    def test_no_stacktrace_in_result(self):
        _setup_full_root(self.root)
        result = run_once(self.root)

        result_str = str(result.safe_summary())
        self.assertNotIn("Traceback", result_str)
        self.assertNotIn("File \"", result_str)

    def test_run_once_missing_root(self):
        result = run_once("/tmp/nonexistent-root-kso-12345")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.steps[0].name, "preflight")
        self.assertEqual(result.steps[0].status, "error")
        self.assertTrue(result.steps[0].fatal)


# ══════════════════════════════════════════════════════════════════════
# Tests: Helpers
# ══════════════════════════════════════════════════════════════════════

class TestHelpers(unittest.TestCase):

    def test_check_forbidden_raises(self):
        with self.assertRaises(ValueError):
            _check_forbidden("my_token_here", "test_field")

    def test_check_forbidden_ok(self):
        _check_forbidden("clean value", "test_field")

    def test_redact_forbidden(self):
        result = _redact_forbidden("Error: token expired for local_path")
        self.assertNotIn("token", result.lower())
        self.assertNotIn("local_path", result.lower())
        self.assertIn("[REDACTED]", result)

    def test_redact_multiple(self):
        result = _redact_forbidden("secret key and access_token failed")
        self.assertNotIn("secret", result.lower())
        self.assertNotIn("access_token", result.lower())
        self.assertEqual(result.count("[REDACTED]"), 2)


# ══════════════════════════════════════════════════════════════════════
# Tests: Constants
# ══════════════════════════════════════════════════════════════════════

class TestConstants(unittest.TestCase):

    def test_allowed_statuses(self):
        self.assertIn("ok", ALLOWED_CYCLE_STATUSES)
        self.assertIn("warning", ALLOWED_CYCLE_STATUSES)
        self.assertIn("degraded", ALLOWED_CYCLE_STATUSES)
        self.assertIn("error", ALLOWED_CYCLE_STATUSES)

    def test_forbidden_substrings(self):
        self.assertIn("token", FORBIDDEN_SUBSTRINGS)
        self.assertIn("secret", FORBIDDEN_SUBSTRINGS)
        self.assertIn("authorization", FORBIDDEN_SUBSTRINGS)
        self.assertIn("local_path", FORBIDDEN_SUBSTRINGS)
        self.assertIn("media_path", FORBIDDEN_SUBSTRINGS)


if __name__ == "__main__":
    unittest.main()
