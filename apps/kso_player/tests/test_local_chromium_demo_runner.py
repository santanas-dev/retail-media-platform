"""Tests for KSO Player Guarded Local Chromium Demo Runner + CLI.

Tests prepare_and_maybe_launch_kso_local_chromium_demo() and CLI command.
Uses temp fixture roots and mocked process_launcher. NO actual Chromium.
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
from unittest.mock import MagicMock, patch

from kso_player.local_chromium_demo_runner import (
    KsoLocalChromiumDemoRunnerResult,
    prepare_and_maybe_launch_kso_local_chromium_demo,
    format_kso_local_chromium_demo_runner_result,
    _build_chromium_command,
    _validate_command_forbidden_flags,
    _FORBIDDEN_CHROMIUM_FLAGS,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_PREPARED_LAUNCH_READY,
    REASON_PREPARED_LAUNCHED,
    REASON_PREPARE_FAILED,
    REASON_LAUNCH_FAILED,
    REASON_INVALID_ARGS,
    FORBIDDEN_SUBSTRINGS,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
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


def _fake_launcher_ok(command):
    """Fake process launcher — returns a MagicMock."""
    return MagicMock()


def _fake_launcher_none(command):
    """Fake process launcher — returns None (failure)."""
    return None


# ══════════════════════════════════════════════════════════════════════
# Tests: core runner
# ══════════════════════════════════════════════════════════════════════

class TestChromiumDemoRunner(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_no_confirm_prepares_but_no_launch(self):
        _full_fixture(self.root, content_type="image/png")
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.prepared)
        self.assertTrue(result.launch_ready)
        self.assertFalse(result.launched)
        self.assertEqual(result.reason, REASON_PREPARED_LAUNCH_READY)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)

    def test_confirm_calls_launcher_once(self):
        _full_fixture(self.root, content_type="image/png")
        mock_launcher = MagicMock(return_value=MagicMock())
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=True, process_launcher=mock_launcher)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.launched)
        self.assertEqual(result.reason, REASON_PREPARED_LAUNCHED)
        mock_launcher.assert_called_once()

    def test_confirm_launcher_gets_list_args(self):
        _full_fixture(self.root, content_type="image/png")
        mock_launcher = MagicMock(return_value=MagicMock())
        prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=True, process_launcher=mock_launcher)
        command = mock_launcher.call_args[0][0]
        self.assertIsInstance(command, list)
        self.assertNotIsInstance(command, str)

    def test_non_idle_prepares_hold_snapshot(self):
        _full_fixture(self.root, state="transaction")
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        self.assertTrue(result.prepared)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertTrue(result.launch_ready)

    def test_idle_image_prepares_render_alias(self):
        _full_fixture(self.root, content_type="image/png")
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertTrue(result.media_alias_ready)

    def test_idle_video_prepares_render_alias(self):
        _full_fixture(self.root, content_type="video/mp4", duration_ms=30000)
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertTrue(result.media_alias_ready)

    def test_prepare_failure_no_launch(self):
        # Use a truly invalid path — missing source shell → prepare fails
        missing_source = Path(tempfile.mkdtemp())
        try:
            mock_launcher = MagicMock()
            result = prepare_and_maybe_launch_kso_local_chromium_demo(
                self.root, missing_source, self.runtime, "chromium",
                confirm_launch=True, process_launcher=mock_launcher)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_PREPARE_FAILED)
            self.assertFalse(result.launched)
            self.assertFalse(result.launch_ready)
            mock_launcher.assert_not_called()
        finally:
            shutil.rmtree(missing_source, ignore_errors=True)

    def test_launch_failure_returns_error(self):
        _full_fixture(self.root, content_type="image/png")
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=True, process_launcher=_fake_launcher_none)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertTrue(result.prepared)
        self.assertTrue(result.launch_ready)
        self.assertFalse(result.launched)
        self.assertEqual(result.reason, REASON_LAUNCH_FAILED)


# ══════════════════════════════════════════════════════════════════════
# Tests: command building
# ══════════════════════════════════════════════════════════════════════

class TestChromiumCommand(TestCase):

    def setUp(self):
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_command_is_list_not_string(self):
        cmd = _build_chromium_command("chromium", self.runtime)
        self.assertIsInstance(cmd, list)

    def test_command_has_window_size(self):
        cmd = _build_chromium_command("chromium", self.runtime)
        size_arg = f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"
        self.assertIn(size_arg, cmd)

    def test_command_has_position_zero(self):
        cmd = _build_chromium_command("chromium", self.runtime)
        self.assertIn("--window-position=0,0", cmd)

    def test_command_uses_app_mode(self):
        cmd = _build_chromium_command("chromium", self.runtime)
        app_arg = [a for a in cmd if a.startswith("--app=")]
        self.assertEqual(len(app_arg), 1)
        self.assertIn("file://", app_arg[0])

    def test_command_no_external_url(self):
        cmd = _build_chromium_command("chromium", self.runtime)
        cmd_str = " ".join(cmd)
        self.assertNotIn("http://", cmd_str)
        self.assertNotIn("https://", cmd_str)

    def test_command_no_forbidden_flags(self):
        cmd = _build_chromium_command("chromium", self.runtime)
        self.assertTrue(_validate_command_forbidden_flags(cmd))

    def test_forbidden_flags_detected(self):
        bad_cmd = ["chromium", "--disable-web-security",
                    f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"]
        self.assertFalse(_validate_command_forbidden_flags(bad_cmd))

    def test_all_forbidden_flags_blocked(self):
        for flag in _FORBIDDEN_CHROMIUM_FLAGS:
            cmd = ["chromium", flag,
                   f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"]
            self.assertFalse(
                _validate_command_forbidden_flags(cmd),
                f"Flag {flag} was not blocked")


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestChromiumDemoOutputSafety(TestCase):

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
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        text = repr(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.source), text)
        self.assertNotIn(str(self.runtime), text)

    def test_repr_no_file_url(self):
        _full_fixture(self.root)
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        text = repr(result)
        self.assertNotIn("file://", text)

    def test_repr_no_command(self):
        _full_fixture(self.root)
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        text = repr(result)
        self.assertNotIn("--app=", text)
        self.assertNotIn("chromium", text)
        self.assertNotIn("--window-size", text)

    def test_repr_no_forbidden(self):
        _full_fixture(self.root)
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        text = repr(result) + format_kso_local_chromium_demo_runner_result(
            result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_error_no_stacktrace(self):
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False, stale_seconds=0)
        text = repr(result) + format_kso_local_chromium_demo_runner_result(
            result)
        self.assertNotIn("Traceback", text)

    def test_format_has_expected_fields(self):
        _full_fixture(self.root)
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        text = format_kso_local_chromium_demo_runner_result(result)
        self.assertIn("prepared: true", text)
        self.assertIn("launch_ready:", text)
        self.assertIn("launched:", text)
        self.assertIn("snapshot_mode:", text)
        self.assertIn("media_alias_ready:", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestChromiumDemoNoSideEffects(TestCase):

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
        prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        after = (self.root / "state" / "kso_state.json").read_text()
        self.assertEqual(before, after)

    def test_no_pop_written(self):
        _full_fixture(self.root)
        prepare_and_maybe_launch_kso_local_chromium_demo(
            self.root, self.source, self.runtime, "chromium",
            confirm_launch=False)
        self.assertFalse((self.root / "pop" / "pending").exists())

    def test_no_http_no_backend_in_source(self):
        import kso_player.local_chromium_demo_runner as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_no_systemd_in_source(self):
        import kso_player.local_chromium_demo_runner as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        # Strip module docstring (between first """ and """)
        body = source.split('"""', 2)[-1] if source.count('"""') >= 2 else source
        self.assertNotIn("systemd", body)

    def test_no_windows_msi(self):
        import kso_player.local_chromium_demo_runner as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)

    def test_no_secret_config_token_read(self):
        import kso_player.local_chromium_demo_runner as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        self.assertNotIn(".env", source)
        self.assertNotIn("device_secret", source)

    def test_no_shell_true_in_subprocess(self):
        """Actual launch uses subprocess.Popen but NEVER shell=True."""
        import kso_player.local_chromium_demo_runner as mod
        with open(mod.__file__) as f:
            source = f.read()
        # Strip module and function docstrings
        body = source
        while '"""' in body:
            start = body.index('"""')
            end = body.index('"""', start + 3)
            body = body[:start] + body[end + 3:]
        self.assertNotIn("shell=True", body)
        self.assertNotIn("shell = True", body)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid args
# ══════════════════════════════════════════════════════════════════════

class TestChromiumDemoInvalidArgs(TestCase):

    def setUp(self):
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_stale_zero_error(self):
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            "/tmp", self.source, self.runtime, "chromium",
            confirm_launch=False, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_empty_chromium_bin_error(self):
        result = prepare_and_maybe_launch_kso_local_chromium_demo(
            "/tmp", self.source, self.runtime, "",
            confirm_launch=False)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: CLI
# ══════════════════════════════════════════════════════════════════════

class TestCLIChromiumDemo(TestCase):

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
            sys.argv = ["kso-player", "local-chromium-demo"] + list(args)
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
            sys.argv = ["kso-player", "local-chromium-demo", "--help"]
            try:
                main()
                out = sys.stdout.getvalue()
            except SystemExit:
                out = sys.stdout.getvalue()
            self.assertIn("local chromium demo", out.lower().replace("-", " "))
        finally:
            sys.stdout = saved

    def test_no_confirm_exit_0_no_launch(self):
        _full_fixture(self.root_tmp, content_type="image/png")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
            "--chromium-bin", "chromium",
        )
        self.assertEqual(code, 0)
        self.assertIn("prepared: true", out)
        self.assertIn("launch_ready: true", out)
        self.assertIn("launched: false", out)

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
            "--chromium-bin", "chromium",
        )
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root_tmp), out)
        self.assertNotIn(str(self.source_tmp), out)
        self.assertNotIn(str(self.runtime_tmp), out)

    def test_cli_output_no_file_url(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
            "--chromium-bin", "chromium",
        )
        self.assertEqual(code, 0)
        self.assertNotIn("file://", out)

    def test_cli_output_no_command(self):
        _full_fixture(self.root_tmp)
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
            "--chromium-bin", "chromium",
        )
        self.assertEqual(code, 0)
        self.assertNotIn("--app=", out)
        self.assertNotIn("--window-size", out)

    def test_cli_output_no_media_ref(self):
        _full_fixture(self.root_tmp, content_type="image/png")
        code, out = self._cli(
            "--root", str(self.root_tmp),
            "--source-shell-dir", str(self.source_tmp),
            "--runtime-shell-dir", str(self.runtime_tmp),
            "--chromium-bin", "chromium",
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
            "--chromium-bin", "chromium",
        )
        self.assertEqual(code, 0)
        self.assertTrue(_no_forbidden(out),
            f"forbidden in CLI output: {out[:200]}")

    def test_cli_output_no_stacktrace(self):
        code, out = self._cli(
            "--root", str(self.root_tmp),
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", out)

    def test_cli_no_forbidden_launch_code(self):
        import kso_player.cli as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("import subprocess", "os.system(", "webbrowser.",
                    "shell=true", "shell = true"):
            self.assertNotIn(fb, source,
                f"CLI source contains forbidden call '{fb}'")


if __name__ == "__main__":
    import unittest
    unittest.main()
