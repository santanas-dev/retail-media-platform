"""Tests for KSO Player Local Demo Fixture + CLI.

Tests prepare_kso_local_demo_fixture() and local-demo-fixture CLI command.
Uses temp fixture roots. NO backend, NO HTTP.

KSO safe manifest format (v1+):
  manifest has schemaVersion, channel=kso, storeCode, deviceCode, items[].mediaRef.
  Media file is at media/current/slot-000.
"""

import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest import TestCase

from kso_player.local_demo_fixture import (
    KsoLocalDemoFixtureResult,
    prepare_kso_local_demo_fixture,
    format_kso_local_demo_fixture_result,
    STATUS_OK,
    STATUS_ERROR,
    REASON_READY,
    REASON_INVALID_ARGS,
    REASON_WRITE_FAILED,
    DEMO_PNG,
    DEMO_MEDIA_REF,
    DEMO_CONTENT_TYPE,
    DEMO_DURATION_MS,
    DEMO_SLOT_ORDER,
    KSO_CHANNEL,
)

# Forbidden substrings for output safety
FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
    "sha256", "full_manifest", "media_bytes",
    "fingerprint", "stacktrace", "boot_id",
})


def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════
# Tests: fixture core
# ══════════════════════════════════════════════════════════════════════

class TestDemoFixture(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_creates_valid_idle_state(self):
        result = prepare_kso_local_demo_fixture(self.root)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.state_ready)

        state_path = self.root / "state" / "kso_state.json"
        self.assertTrue(state_path.is_file())
        state = json.loads(state_path.read_text())
        self.assertEqual(state["state"], "idle")
        self.assertEqual(state["source"], "ukm4_state_adapter")
        self.assertIn("updated_at_utc", state)

    def test_creates_valid_kso_manifest(self):
        """Manifest uses KSO safe format: schemaVersion, channel=kso, mediaRef."""
        result = prepare_kso_local_demo_fixture(self.root)
        self.assertTrue(result.manifest_ready)

        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text())

        # KSO safe format top-level fields
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["channel"], KSO_CHANNEL)
        self.assertEqual(manifest["storeCode"], "demo-store")
        self.assertEqual(manifest["deviceCode"], "demo-device")
        self.assertIn("generatedAt", manifest)
        self.assertEqual(len(manifest["items"]), 1)

        item = manifest["items"][0]
        self.assertEqual(item["slotOrder"], DEMO_SLOT_ORDER)
        self.assertEqual(item["contentType"], DEMO_CONTENT_TYPE)
        self.assertEqual(item["durationMs"], DEMO_DURATION_MS)
        self.assertEqual(item["mediaRef"], DEMO_MEDIA_REF)
        self.assertIn("validFrom", item)
        self.assertIn("validTo", item)

        # Forbidden fields: NO filename, NO sha256, NO manifest_item_id
        self.assertNotIn("filename", item)
        self.assertNotIn("sha256", item)
        self.assertNotIn("manifest_item_id", item)
        self.assertNotIn("manifest_id", manifest)

    def test_creates_valid_media(self):
        """Media file is at media/current/slot-000 (mediaRef target)."""
        result = prepare_kso_local_demo_fixture(self.root)
        self.assertTrue(result.media_ready)

        media_path = self.root / "media" / "current" / "slot-000"
        self.assertTrue(media_path.is_file())
        self.assertEqual(media_path.read_bytes(), DEMO_PNG)

        # No .sha256 file (not in KSO safe format)
        sha_path = self.root / "media" / "current" / "slot-000.sha256"
        self.assertFalse(sha_path.exists())

        # No legacy filename
        legacy = self.root / "media" / "current" / "ad_demo.png"
        self.assertFalse(legacy.exists())

    def test_manifest_compatible_with_build_playlist(self):
        """After fixture, build_playlist returns ready with KSO safe format."""
        from kso_player.playlist import build_playlist
        prepare_kso_local_demo_fixture(self.root)
        playlist = build_playlist(self.root)
        self.assertTrue(playlist.ready)
        self.assertEqual(playlist.reason, "ready")
        self.assertEqual(playlist.items_total, 1)
        self.assertEqual(playlist.items_ready, 1)

    def test_runtime_gate_returns_play_allowed(self):
        """After fixture, runtime gate returns play_allowed."""
        from kso_player.runtime_gate import evaluate_kso_runtime_gate
        prepare_kso_local_demo_fixture(self.root)
        gate = evaluate_kso_runtime_gate(self.root)
        self.assertTrue(gate.play_allowed)
        self.assertEqual(gate.action, "play")

    def test_render_plan_returns_render(self):
        """After fixture, render plan returns render action."""
        from kso_player.render_plan import build_kso_render_plan
        prepare_kso_local_demo_fixture(self.root)
        plan = build_kso_render_plan(self.root)
        self.assertEqual(plan.render_action, "render")
        self.assertEqual(plan.media_type, "image")

    def test_shell_snapshot_returns_render(self):
        """After fixture, shell snapshot returns render."""
        from kso_player.shell_snapshot import (
            build_kso_shell_snapshot,
            SNAPSHOT_MODE_RENDER,
        )
        prepare_kso_local_demo_fixture(self.root)
        snapshot = build_kso_shell_snapshot(self.root)
        self.assertEqual(snapshot.snapshot_mode, SNAPSHOT_MODE_RENDER)

    def test_full_result_all_ready(self):
        result = prepare_kso_local_demo_fixture(self.root)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.fixture_ready)
        self.assertTrue(result.state_ready)
        self.assertTrue(result.manifest_ready)
        self.assertTrue(result.media_ready)
        self.assertEqual(result.reason, REASON_READY)

    def test_idempotent_overwrite(self):
        """Running fixture twice overwrites — second call succeeds."""
        result1 = prepare_kso_local_demo_fixture(self.root)
        self.assertTrue(result1.fixture_ready)
        result2 = prepare_kso_local_demo_fixture(self.root)
        self.assertTrue(result2.fixture_ready)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestDemoFixtureOutputSafety(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_repr_no_paths(self):
        result = prepare_kso_local_demo_fixture(self.root)
        text = repr(result)
        self.assertNotIn(str(self.root), text)

    def test_repr_no_media_ref(self):
        """Result repr must not contain mediaRef value."""
        result = prepare_kso_local_demo_fixture(self.root)
        text = repr(result)
        self.assertNotIn(DEMO_MEDIA_REF, text)

    def test_repr_no_forbidden(self):
        result = prepare_kso_local_demo_fixture(self.root)
        text = repr(result) + format_kso_local_demo_fixture_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_error_no_stacktrace(self):
        result = prepare_kso_local_demo_fixture(None)
        text = repr(result) + format_kso_local_demo_fixture_result(result)
        self.assertNotIn("Traceback", text)

    def test_error_no_path(self):
        result = prepare_kso_local_demo_fixture(None)
        text = repr(result) + format_kso_local_demo_fixture_result(result)
        self.assertNotIn("None", text)

    def test_format_has_expected_fields(self):
        result = prepare_kso_local_demo_fixture(self.root)
        text = format_kso_local_demo_fixture_result(result)
        self.assertIn("fixture_ready: true", text)
        self.assertIn("state_ready:", text)
        self.assertIn("manifest_ready:", text)
        self.assertIn("media_ready:", text)

    def test_bootstrap_output_safe(self):
        """After fixture + runner, bootstrap_snapshot.js has no forbidden."""
        from kso_player.local_chromium_demo_runner import (
            prepare_and_maybe_launch_kso_local_chromium_demo,
            FORBIDDEN_SUBSTRINGS as CHR_FORBIDDEN,
        )
        source = Path(tempfile.mkdtemp())
        runtime = Path(tempfile.mkdtemp())
        try:
            # Copy shell files to source
            REAL_SHELL = Path(__file__).resolve().parent.parent / "player_shell"
            SHELL = frozenset({
                "index.html", "styles.css", "player.js",
                "bootstrap_snapshot.js", "bootstrap.js",
            })
            for fname in SHELL:
                src = REAL_SHELL / fname
                if src.is_file():
                    shutil.copy2(src, source / fname)

            prepare_kso_local_demo_fixture(self.root)
            prepare_and_maybe_launch_kso_local_chromium_demo(
                self.root, source, runtime, "chromium",
                confirm_launch=False)

            content = (runtime / "bootstrap_snapshot.js").read_text()
            lower = content.lower()
            for fb in CHR_FORBIDDEN:
                self.assertNotIn(fb, lower,
                    f"forbidden '{fb}' in bootstrap: {content[:100]}")
        finally:
            shutil.rmtree(source, ignore_errors=True)
            shutil.rmtree(runtime, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestDemoFixtureNoSideEffects(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_no_http_no_backend_in_source(self):
        import kso_player.local_demo_fixture as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)

    def test_no_windows_msi(self):
        import kso_player.local_demo_fixture as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)

    def test_no_secret_config_token_read(self):
        import kso_player.local_demo_fixture as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        self.assertNotIn(".env", source)
        self.assertNotIn("device_secret", source)

    def test_no_pop_written(self):
        prepare_kso_local_demo_fixture(self.root)
        self.assertFalse((self.root / "pop").exists())

    def test_no_state_modified_after_second_call(self):
        """Second call overwrites cleanly, no side effects elsewhere."""
        prepare_kso_local_demo_fixture(self.root)
        state_before = (self.root / "state" / "kso_state.json").read_text()
        prepare_kso_local_demo_fixture(self.root)
        state_after = (self.root / "state" / "kso_state.json").read_text()
        self.assertNotEqual(state_before, state_after)  # timestamp changed
        state_obj = json.loads(state_after)
        self.assertEqual(state_obj["state"], "idle")


# ══════════════════════════════════════════════════════════════════════
# Tests: CLI
# ══════════════════════════════════════════════════════════════════════

class TestCLIDemoFixture(TestCase):

    def setUp(self):
        self.root_tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root_tmp, ignore_errors=True)

    def _cli(self, *args):
        saved = sys.stdout
        try:
            sys.stdout = StringIO()
            from kso_player.cli import main
            sys.argv = ["kso-player", "local-demo-fixture"] + list(args)
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
            sys.argv = ["kso-player", "local-demo-fixture", "--help"]
            try:
                main()
                out = sys.stdout.getvalue()
            except SystemExit:
                out = sys.stdout.getvalue()
            self.assertIn("local demo fixture", out.lower().replace("-", " "))
        finally:
            sys.stdout = saved

    def test_success_exit_0(self):
        code, out = self._cli("--root", str(self.root_tmp))
        self.assertEqual(code, 0)
        self.assertIn("fixture_ready: true", out)
        self.assertIn("state_ready: true", out)

    def test_invalid_args_exit_2(self):
        code, out = self._cli()
        self.assertEqual(code, 2)

    def test_cli_output_no_paths(self):
        code, out = self._cli("--root", str(self.root_tmp))
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root_tmp), out)

    def test_cli_output_no_media_ref(self):
        """CLI output must not contain mediaRef values."""
        code, out = self._cli("--root", str(self.root_tmp))
        self.assertEqual(code, 0)
        self.assertNotIn(DEMO_MEDIA_REF, out)

    def test_cli_output_no_forbidden(self):
        code, out = self._cli("--root", str(self.root_tmp))
        self.assertEqual(code, 0)
        self.assertTrue(_no_forbidden(out),
            f"forbidden in CLI output: {out[:200]}")

    def test_cli_output_no_stacktrace(self):
        code, out = self._cli()
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", out)

    def test_then_chromium_demo_no_confirm(self):
        """Fixture → chromium demo without confirm → no launch."""
        source = Path(tempfile.mkdtemp())
        runtime = Path(tempfile.mkdtemp())
        try:
            REAL_SHELL = Path(__file__).resolve().parent.parent / "player_shell"
            SHELL = frozenset({
                "index.html", "styles.css", "player.js",
                "bootstrap_snapshot.js", "bootstrap.js",
            })
            for fname in SHELL:
                src = REAL_SHELL / fname
                if src.is_file():
                    shutil.copy2(src, source / fname)

            # First: fixture
            prepare_kso_local_demo_fixture(self.root_tmp)

            # Second: chromium demo (no confirm)
            saved = sys.stdout
            try:
                sys.stdout = StringIO()
                from kso_player.cli import main
                sys.argv = [
                    "kso-player", "local-chromium-demo",
                    "--root", str(self.root_tmp),
                    "--source-shell-dir", str(source),
                    "--runtime-shell-dir", str(runtime),
                    "--chromium-bin", "chromium",
                ]
                try:
                    main()
                    code = 0
                except SystemExit as e:
                    code = e.code
                out = sys.stdout.getvalue()
            finally:
                sys.stdout = saved

            self.assertEqual(code, 0)
            self.assertIn("launch_ready: true", out)
            self.assertIn("launched: false", out)
        finally:
            shutil.rmtree(source, ignore_errors=True)
            shutil.rmtree(runtime, ignore_errors=True)


if __name__ == "__main__":
    import unittest
    unittest.main()
