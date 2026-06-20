"""Tests for KSO Player Runtime Snapshot Writer + CLI.

Tests write_kso_runtime_bootstrap_snapshot() and CLI command.
Uses temp fixture roots. NO backend, NO HTTP, NO Chromium.
"""

import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from kso_player.runtime_snapshot_writer import (
    KsoRuntimeSnapshotWriteResult,
    write_kso_runtime_bootstrap_snapshot,
    format_kso_runtime_snapshot_write_result,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    SNAPSHOT_METHOD_SET_HOLD,
    SNAPSHOT_METHOD_SET_RENDER_PLAN,
    SNAPSHOT_FILE,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_WRITTEN,
    REASON_INVALID_ARGS,
    REASON_WRITE_FAILED,
    FORBIDDEN_SUBSTRINGS,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return False
    return True


def _sha(content):
    return hashlib.sha256(content).hexdigest()

CONTENT = b"fake-media-content"
CONTENT_SHA = _sha(CONTENT)


def _write_state(root, state="idle", age_seconds=5):
    state_dir = Path(root) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    (state_dir / "kso_state.json").write_text(json.dumps(
        {"state": state, "updated_at_utc": updated_at.isoformat(), "source": "test"},
        sort_keys=True))


def _write_manifest(root, items=None):
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if items is None:
        items = [{"manifest_item_id": "m-001", "order": 1,
                   "content_type": "image/png", "duration_ms": 5000,
                   "filename": "ad_001.png", "sha256": CONTENT_SHA}]
    (manifest_dir / "current_manifest.json").write_text(
        json.dumps({"manifest_id": "test", "schema_version": 1, "items": items},
                   sort_keys=True))


def _write_media(root, filename="ad_001.png", content=CONTENT):
    media_dir = Path(root) / "media" / "current"
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / filename).write_bytes(content)
    (media_dir / (filename + ".sha256")).write_text(_sha(content) + "\n")


def _full_fixture(root, state="idle", age_seconds=5, content_type="image/png",
                  duration_ms=5000):
    _write_state(root, state, age_seconds)
    _write_media(root)
    _write_manifest(root, items=[{
        "manifest_item_id": "m-001", "order": 1,
        "content_type": content_type, "duration_ms": duration_ms,
        "filename": "ad_001.png", "sha256": CONTENT_SHA,
    }])


# ══════════════════════════════════════════════════════════════════════
# Tests: writer core
# ══════════════════════════════════════════════════════════════════════

class TestSnapshotWriter(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_idle_image_writes_render(self):
        _full_fixture(self.root, content_type="image/png")
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.written)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertEqual(result.shell_method, SNAPSHOT_METHOD_SET_RENDER_PLAN)
        self.assertEqual(result.reason, REASON_WRITTEN)

    def test_idle_video_writes_render(self):
        _full_fixture(self.root, content_type="video/mp4", duration_ms=30000)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertTrue(result.written)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)

    def test_transaction_writes_hold(self):
        _full_fixture(self.root, state="transaction")
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertTrue(result.written)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertEqual(result.shell_method, SNAPSHOT_METHOD_SET_HOLD)

    def test_missing_state_writes_hold(self):
        _write_manifest(self.root)
        _write_media(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertTrue(result.written)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_missing_manifest_writes_hold(self):
        _write_state(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertTrue(result.written)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_output_file_created(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        out = self.runtime / SNAPSHOT_FILE
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 50)

    def test_output_file_starts_with_use_strict(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        self.assertTrue(content.startswith('"use strict"'))

    def test_output_file_sets_window_variable(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        self.assertIn("window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT", content)
        self.assertIn("schemaVersion", content)

    def test_render_output_has_media_ref(self):
        _full_fixture(self.root, content_type="image/png")
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        self.assertIn("mediaRef", content)
        self.assertIn("media/current/slot-", content)

    def test_hold_output_no_media_ref(self):
        _full_fixture(self.root, state="transaction")
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        self.assertNotIn("mediaRef", content)

    def test_output_no_absolute_path(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        self.assertNotIn("/opt", content)
        self.assertNotIn(str(self.root), content)

    def test_output_no_ids_hash(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "sha256", "m-001"):
            self.assertNotIn(fb, content)

    def test_output_no_forbidden(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        content = (self.runtime / SNAPSHOT_FILE).read_text()
        self.assertTrue(_no_forbidden(content),
            f"forbidden in output: {content[:200]}")

    def test_creates_runtime_dir(self):
        _full_fixture(self.root)
        new_runtime = Path(tempfile.mkdtemp()) / "sub" / "runtime"
        try:
            result = write_kso_runtime_bootstrap_snapshot(self.root, new_runtime)
            self.assertEqual(result.status, STATUS_OK)
            self.assertTrue((new_runtime / SNAPSHOT_FILE).is_file())
        finally:
            import shutil
            shutil.rmtree(new_runtime.parents[2], ignore_errors=True)

    def test_invalid_args_stale_zero(self):
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_bytes_bucket_set(self):
        _full_fixture(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertIn(result.bytes_bucket, ("small", "medium", "large"))


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestWriterOutputSafety(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_repr_no_path(self):
        _full_fixture(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        text = repr(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.runtime), text)

    def test_repr_no_media_ref(self):
        _full_fixture(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        text = repr(result)
        self.assertNotIn("slot-", text)
        self.assertNotIn("media/current", text)

    def test_repr_no_forbidden(self):
        _full_fixture(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        text = repr(result) + format_kso_runtime_snapshot_write_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden: {text[:200]}")

    def test_error_no_stacktrace(self):
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime, stale_seconds=0)
        text = repr(result) + format_kso_runtime_snapshot_write_result(result)
        self.assertNotIn("Traceback", text)

    def test_format_has_expected_fields(self):
        _full_fixture(self.root)
        result = write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        text = format_kso_runtime_snapshot_write_result(result)
        self.assertIn("written: true", text)
        self.assertIn("snapshot_mode:", text)
        self.assertIn("bytes_bucket:", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestWriterNoSideEffects(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_no_state_modified(self):
        _full_fixture(self.root)
        before = (self.root / "state" / "kso_state.json").read_text()
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        after = (self.root / "state" / "kso_state.json").read_text()
        self.assertEqual(before, after)

    def test_no_pop_written(self):
        _full_fixture(self.root)
        write_kso_runtime_bootstrap_snapshot(self.root, self.runtime)
        self.assertFalse((self.root / "pop" / "pending").exists())

    def test_no_http_no_backend(self):
        import kso_player.runtime_snapshot_writer as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_no_chromium_no_systemd(self):
        import kso_player.runtime_snapshot_writer as mod
        with open(mod.__file__) as f:
            source = f.read()
        # Check for actual launch code, not docstrings
        self.assertNotIn("subprocess", source.lower())
        self.assertNotIn("os.system", source.lower())
        self.assertNotIn("webbrowser", source.lower())

    def test_no_windows_msi(self):
        import kso_player.runtime_snapshot_writer as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)


# ══════════════════════════════════════════════════════════════════════
# Tests: CLI
# ══════════════════════════════════════════════════════════════════════

class TestCLIShellSnapshotWrite(TestCase):

    def setUp(self):
        self.root_tmp = Path(tempfile.mkdtemp())
        self.runtime_tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root_tmp, ignore_errors=True)
        shutil.rmtree(self.runtime_tmp, ignore_errors=True)

    def _cli(self, *args):
        saved = sys.stdout
        try:
            sys.stdout = StringIO()
            from kso_player.cli import main
            sys.argv = ["kso-player", "shell-snapshot-write"] + list(args)
            try:
                main()
                return 0, sys.stdout.getvalue()
            except SystemExit as e:
                return e.code, sys.stdout.getvalue()
        finally:
            sys.stdout = saved

    def test_help(self):
        saved = sys.stdout
        try:
            sys.stdout = StringIO()
            from kso_player.cli import main
            sys.argv = ["kso-player", "shell-snapshot-write", "--help"]
            try:
                main()
                out = sys.stdout.getvalue()
            except SystemExit:
                out = sys.stdout.getvalue()
            self.assertIn("shell snapshot write", out.lower().replace("-", " "))
        finally:
            sys.stdout = saved

    def test_successful_hold_write(self):
        _full_fixture(self.root_tmp, state="transaction")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertIn("written: true", out)

    def test_successful_render_write(self):
        _full_fixture(self.root_tmp, content_type="image/png")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertIn("snapshot_mode: render", out)

    def test_invalid_args_exit_2(self):
        code, out = self._cli(
            "--root", str(self.root_tmp),
        )
        self.assertEqual(code, 2)

    def test_cli_output_no_paths(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root_tmp), out)
        self.assertNotIn(str(self.runtime_tmp), out)

    def test_cli_output_no_media_ref(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertNotIn("slot-", out)
        self.assertNotIn("media/current", out)

    def test_cli_output_no_forbidden(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertTrue(_no_forbidden(out),
            f"forbidden in CLI output: {out[:200]}")


if __name__ == "__main__":
    import unittest
    unittest.main()
