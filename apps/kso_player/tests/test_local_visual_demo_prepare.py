"""Tests for KSO Player Local Visual Demo Prepare + CLI.

Tests prepare_kso_local_visual_demo() and local-demo-prepare CLI command.
Uses temp fixture roots. NO backend, NO HTTP, NO Chromium.
"""

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from kso_player.local_visual_demo_prepare import (
    KsoLocalVisualDemoPrepareResult,
    prepare_kso_local_visual_demo,
    format_kso_local_visual_demo_prepare_result,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_PREPARED,
    REASON_WORKSPACE_FAILED,
    REASON_INVALID_ARGS,
    FORBIDDEN_SUBSTRINGS,
    _prepare_media_aliases,
    _HOLD_SNAPSHOT_JS,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

SHELL_FILES = frozenset({
    "index.html", "styles.css", "player.js",
    "bootstrap_snapshot.js", "bootstrap.js",
})

REAL_SHELL_DIR = Path(__file__).resolve().parent.parent / "player_shell"

CONTENT = b"fake-media-content"
CONTENT_SHA = hashlib.sha256(CONTENT).hexdigest()


def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return False
    return True


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _write_state(root, state="idle", age_seconds=5):
    state_dir = Path(root) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    (state_dir / "kso_state.json").write_text(json.dumps(
        {"state": state, "updated_at_utc": updated_at.isoformat(),
         "source": "test"},
        sort_keys=True))


def _write_manifest(root, items=None):
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if items is None:
        items = [{"manifest_item_id": "m-001", "order": 0,
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


def _write_source_shell(source_dir):
    """Copy real shell files to temp source dir (simulating /opt)."""
    for fname in sorted(SHELL_FILES):
        src = REAL_SHELL_DIR / fname
        if src.is_file():
            shutil.copy2(src, source_dir / fname)
    return source_dir


def _full_fixture(root, state="idle", age_seconds=5, content_type="image/png",
                  duration_ms=5000):
    _write_state(root, state, age_seconds)
    _write_media(root)
    _write_manifest(root, items=[{
        "manifest_item_id": "m-001", "order": 0,
        "content_type": content_type, "duration_ms": duration_ms,
        "filename": "ad_001.png", "sha256": CONTENT_SHA,
    }])


# ══════════════════════════════════════════════════════════════════════
# Tests: core prepare
# ══════════════════════════════════════════════════════════════════════

class TestDemoPrepare(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_idle_image_render_with_alias(self):
        _full_fixture(self.root, content_type="image/png")
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.prepared)
        self.assertTrue(result.workspace_ready)
        self.assertTrue(result.snapshot_written)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertTrue(result.media_alias_ready)
        self.assertEqual(result.reason, REASON_PREPARED)

    def test_idle_video_render_with_alias(self):
        _full_fixture(self.root, content_type="video/mp4", duration_ms=30000)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertTrue(result.prepared)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertTrue(result.media_alias_ready)

    def test_non_idle_hold_no_alias(self):
        _full_fixture(self.root, state="transaction")
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertTrue(result.prepared)
        self.assertTrue(result.workspace_ready)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertFalse(result.media_alias_ready)

    def test_missing_state_hold(self):
        _write_media(self.root)
        _write_manifest(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertFalse(result.media_alias_ready)

    def test_missing_source_shell_error(self):
        missing = Path(tempfile.mkdtemp())
        try:
            result = prepare_kso_local_visual_demo(
                self.root, missing, self.runtime)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_WORKSPACE_FAILED)
            self.assertFalse(result.prepared)
        finally:
            shutil.rmtree(missing, ignore_errors=True)

    def test_creates_runtime_dir(self):
        _full_fixture(self.root)
        new_runtime = Path(tempfile.mkdtemp()) / "sub" / "runtime"
        try:
            result = prepare_kso_local_visual_demo(
                self.root, self.source, new_runtime)
            self.assertEqual(result.status, STATUS_OK)
            self.assertTrue((new_runtime / "index.html").is_file())
        finally:
            shutil.rmtree(new_runtime.parents[2], ignore_errors=True)

    def test_source_not_modified(self):
        _full_fixture(self.root)
        # Snapshot source before
        index_before = (self.source / "index.html").read_bytes()
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        index_after = (self.source / "index.html").read_bytes()
        self.assertEqual(index_before, index_after)

    def test_bootstrap_written(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        out = self.runtime / "bootstrap_snapshot.js"
        self.assertTrue(out.is_file())
        content = out.read_text()
        self.assertTrue(content.startswith('"use strict"'))
        self.assertIn("window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT", content)

    def test_media_alias_symlink_created(self):
        _full_fixture(self.root, content_type="image/png")
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        alias = self.runtime / "media" / "current" / "slot-000"
        self.assertTrue(alias.is_symlink())
        self.assertTrue(alias.exists())

    def test_media_alias_not_created_for_hold(self):
        _full_fixture(self.root, state="transaction")
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        alias = self.runtime / "media" / "current"
        self.assertFalse(alias.exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: alias failure → hold
# ══════════════════════════════════════════════════════════════════════

class TestDemoPrepareAliasFailHold(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_alias_fail_writes_hold_snapshot(self):
        """When render aliases fail, a hold snapshot is written instead."""
        _full_fixture(self.root, content_type="image/png")
        # Make media path invalid to force alias failure
        shutil.rmtree(self.root / "media")

        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)

        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertFalse(result.media_alias_ready)
        self.assertTrue(result.snapshot_written)

        # Verify the written file is a hold snapshot
        out = self.runtime / "bootstrap_snapshot.js"
        self.assertTrue(out.is_file())
        content = out.read_text()
        self.assertIn('"mode":"hold"', content)
        self.assertIn('"method":"setHold"', content)
        self.assertNotIn("mediaRef", content)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestDemoPrepareOutputSafety(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_repr_no_paths(self):
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = repr(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.source), text)
        self.assertNotIn(str(self.runtime), text)

    def test_repr_no_media_ref(self):
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = repr(result)
        self.assertNotIn("slot-", text)
        self.assertNotIn("media/current", text)

    def test_repr_no_forbidden(self):
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = repr(result) + format_kso_local_visual_demo_prepare_result(
            result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_error_no_stacktrace(self):
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime, stale_seconds=0)
        text = repr(result) + format_kso_local_visual_demo_prepare_result(
            result)
        self.assertNotIn("Traceback", text)

    def test_format_has_expected_fields(self):
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = format_kso_local_visual_demo_prepare_result(result)
        self.assertIn("prepared: true", text)
        self.assertIn("workspace_ready:", text)
        self.assertIn("snapshot_mode:", text)
        self.assertIn("media_alias_ready:", text)

    def test_bootstrap_output_no_path(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        content = (self.runtime / "bootstrap_snapshot.js").read_text()
        self.assertNotIn("/opt", content)
        self.assertNotIn(str(self.root), content)

    def test_bootstrap_output_no_ids(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        content = (self.runtime / "bootstrap_snapshot.js").read_text()
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "sha256", "m-001"):
            self.assertNotIn(fb, content)

    def test_bootstrap_output_no_forbidden(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        content = (self.runtime / "bootstrap_snapshot.js").read_text()
        self.assertTrue(_no_forbidden(content),
            f"forbidden in bootstrap: {content[:200]}")

    def test_bootstrap_no_real_filename(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        content = (self.runtime / "bootstrap_snapshot.js").read_text()
        self.assertNotIn("ad_001.png", content)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestDemoPrepareNoSideEffects(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_no_state_modified(self):
        _full_fixture(self.root)
        before = (self.root / "state" / "kso_state.json").read_text()
        prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        after = (self.root / "state" / "kso_state.json").read_text()
        self.assertEqual(before, after)

    def test_no_pop_written(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertFalse((self.root / "pop" / "pending").exists())

    def test_no_opt_modified(self):
        """Source shell (simulating /opt) is never modified."""
        _full_fixture(self.root)
        # Collect checksums before
        before = {}
        for fname in sorted(SHELL_FILES):
            fpath = self.source / fname
            if fpath.is_file():
                before[fname] = hashlib.sha256(
                    fpath.read_bytes()).hexdigest()

        prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)

        # Verify source unchanged
        for fname, expected_sha in before.items():
            actual = hashlib.sha256(
                (self.source / fname).read_bytes()).hexdigest()
            self.assertEqual(expected_sha, actual,
                f"Source file {fname} was modified!")

    def test_source_unchanged_file_count(self):
        _full_fixture(self.root)
        before = set(f.name for f in self.source.iterdir() if f.is_file())
        prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        after = set(f.name for f in self.source.iterdir() if f.is_file())
        self.assertEqual(before, after)

    def test_no_http_no_backend_in_source(self):
        import kso_player.local_visual_demo_prepare as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_no_chromium_no_systemd_in_source(self):
        import kso_player.local_visual_demo_prepare as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("webbrowser", source)

    def test_no_windows_msi(self):
        import kso_player.local_visual_demo_prepare as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)

    def test_no_secret_config_token_read(self):
        import kso_player.local_visual_demo_prepare as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        self.assertNotIn(".env", source)
        self.assertNotIn("config.yaml", source)
        self.assertNotIn("device_secret", source)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid args
# ══════════════════════════════════════════════════════════════════════

class TestDemoPrepareInvalidArgs(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_stale_zero_error(self):
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_none_root_error(self):
        result = prepare_kso_local_visual_demo(
            None, self.source, self.runtime)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: _prepare_media_aliases helper
# ══════════════════════════════════════════════════════════════════════

class TestPrepareMediaAliases(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_unsafe_filename_rejected(self):
        _full_fixture(self.root)
        # Overwrite manifest with unsafe filename
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(
            json.dumps({
                "manifest_id": "test", "schema_version": 1,
                "items": [{"manifest_item_id": "m-002", "order": 0,
                            "content_type": "image/png", "duration_ms": 5000,
                            "filename": "../etc/passwd",
                            "sha256": CONTENT_SHA}],
            }))
        # Media file must exist for the filename check
        media_root_parts = self.root / "media" / "current" / ".."
        okay = _prepare_media_aliases(self.root, self.runtime, 30, None)
        self.assertFalse(okay)


# ══════════════════════════════════════════════════════════════════════
# Tests: CLI
# ══════════════════════════════════════════════════════════════════════

class TestCLIDemoPrepare(TestCase):

    def setUp(self):
        self.root_tmp = Path(tempfile.mkdtemp())
        self.source_tmp = Path(tempfile.mkdtemp())
        self.runtime_tmp = Path(tempfile.mkdtemp())
        _write_source_shell(self.source_tmp)

    def tearDown(self):
        shutil.rmtree(self.root_tmp, ignore_errors=True)
        shutil.rmtree(self.source_tmp, ignore_errors=True)
        shutil.rmtree(self.runtime_tmp, ignore_errors=True)

    def _cli(self, *args):
        saved = sys.stdout
        try:
            sys.stdout = StringIO()
            from kso_player.cli import main
            sys.argv = ["kso-player", "local-demo-prepare"] + list(args)
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
            sys.argv = ["kso-player", "local-demo-prepare", "--help"]
            try:
                main()
                out = sys.stdout.getvalue()
            except SystemExit:
                out = sys.stdout.getvalue()
            self.assertIn("local demo prepare", out.lower().replace("-", " "))
        finally:
            sys.stdout = saved

    def test_success_hold(self):
        _full_fixture(self.root_tmp, state="transaction")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertIn("prepared: true", out)
        self.assertIn("snapshot_mode: hold", out)

    def test_success_render(self):
        _full_fixture(self.root_tmp, content_type="image/png")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertIn("snapshot_mode: render", out)
        self.assertIn("media_alias_ready: true", out)

    def test_invalid_args_exit_2(self):
        code, out = self._cli(
            "--root", str(self.root_tmp),
        )
        self.assertEqual(code, 2)

    def test_cli_output_no_paths(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root_tmp), out)
        self.assertNotIn(str(self.source_tmp), out)
        self.assertNotIn(str(self.runtime_tmp), out)

    def test_cli_output_no_media_ref(self):
        _full_fixture(self.root_tmp, content_type="image/png")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertNotIn("slot-", out)
        self.assertNotIn("media/current", out)

    def test_cli_output_no_forbidden(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
        )
        self.assertEqual(code, 0)
        self.assertTrue(_no_forbidden(out),
            f"forbidden in CLI output: {out[:200]}")

    def test_cli_output_no_stacktrace(self):
        # Invalid args → error with stacktrace
        code, out = self._cli(
            "--root", str(self.root_tmp),
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", out)

    def test_cli_no_forbidden_in_source(self):
        import kso_player.cli as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        # Check for actual launch/invoke code, not docstring mentions
        for fb in ("import subprocess", "os.system(", "webbrowser."):
            self.assertNotIn(fb, source,
                f"CLI source contains forbidden call '{fb}'")


if __name__ == "__main__":
    import unittest
    unittest.main()
