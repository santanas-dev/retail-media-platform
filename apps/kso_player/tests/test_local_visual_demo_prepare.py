"""Tests for KSO Player Local Visual Demo Prepare + CLI.

Tests prepare_kso_local_visual_demo() and local-demo-prepare CLI command.
Uses temp fixture roots. NO backend, NO HTTP, NO Chromium.

Uses KSO safe manifest format by default:
  schemaVersion, channel=kso, items[].mediaRef.
  Media at media/current/slot-000.
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

KSO_CHANNEL = "kso"
KSO_MEDIA_REF = "media/current/slot-000"


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


def _write_manifest_kso(root, items=None):
    """Write KSO safe format manifest."""
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if items is None:
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": KSO_MEDIA_REF,
            "validFrom": "",
            "validTo": "",
        }]
    (manifest_dir / "current_manifest.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "channel": KSO_CHANNEL,
            "storeCode": "test-store",
            "deviceCode": "test-device",
            "items": items,
        }, sort_keys=True))


def _write_manifest(root, items=None):
    """Write LEGACY format manifest (kept for backward compat)."""
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if items is None:
        items = [{"manifest_item_id": "m-001", "order": 0,
                   "content_type": "image/png", "duration_ms": 5000,
                   "filename": "ad_001.png", "sha256": CONTENT_SHA}]
    (manifest_dir / "current_manifest.json").write_text(
        json.dumps({"manifest_id": "test", "schema_version": 1, "items": items},
                   sort_keys=True))


def _write_media_kso(root, content=CONTENT):
    """Write media at KSO safe mediaRef target."""
    media_dir = Path(root) / "media" / "current"
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "slot-000").write_bytes(content)


def _write_media(root, filename="ad_001.png", content=CONTENT):
    """Write LEGACY media file."""
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
    """Full fixture with KSO safe format manifest + media."""
    _write_state(root, state, age_seconds)
    _write_media_kso(root)
    _write_manifest_kso(root, items=[{
        "slotOrder": 0,
        "contentType": content_type,
        "durationMs": duration_ms,
        "mediaRef": KSO_MEDIA_REF,
        "validFrom": "",
        "validTo": "",
    }])


def _full_fixture_legacy(root, state="idle", age_seconds=5, content_type="image/png",
                          duration_ms=5000):
    """Legacy full fixture for backward compat tests."""
    _write_state(root, state, age_seconds)
    _write_media(root)
    _write_manifest(root, items=[{
        "manifest_item_id": "m-001", "order": 0,
        "content_type": content_type, "duration_ms": duration_ms,
        "filename": "ad_001.png", "sha256": CONTENT_SHA,
    }])


# ══════════════════════════════════════════════════════════════════════
# Tests: core prepare (KSO safe format)
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
        _write_media_kso(self.root)
        _write_manifest_kso(self.root)
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
        self.assertIn("KSO_PLAYER_BOOTSTRAP_SNAPSHOT", content)
        self.assertIn("schemaVersion", content)

    # ── KSO safe format specific tests ─────────────────────────────

    def test_kso_media_ref_alias_created(self):
        """Media alias symlink is created at runtime shell mediaRef target."""
        _full_fixture(self.root, content_type="image/png")
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)

        alias = self.runtime / KSO_MEDIA_REF
        self.assertTrue(
            alias.exists() and (alias.is_file() or alias.is_symlink()),
            f"Expected {alias} to exist as file or symlink"
        )

    def test_kso_media_alias_idempotent(self):
        """Second prepare skips already-existing media alias."""
        _full_fixture(self.root, content_type="image/png")
        result1 = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertTrue(result1.media_alias_ready)

        # Second call with same runtime dir → alias already exists → should succeed
        result2 = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertTrue(result2.media_alias_ready)


# ══════════════════════════════════════════════════════════════════════
# Tests: legacy backward compat
# ══════════════════════════════════════════════════════════════════════

class TestDemoPrepareLegacy(TestCase):
    """Legacy manifest format still works for backward compat."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_legacy_image_render_with_alias(self):
        _full_fixture_legacy(self.root, content_type="image/png")
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.prepared)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertTrue(result.media_alias_ready)


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

    def test_repr_no_media_ref(self):
        """Result repr must not contain mediaRef value."""
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = repr(result)
        self.assertNotIn(KSO_MEDIA_REF, text)

    def test_repr_no_forbidden(self):
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = repr(result) + format_kso_local_visual_demo_prepare_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_format_has_expected_fields(self):
        _full_fixture(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = format_kso_local_visual_demo_prepare_result(result)
        self.assertIn("prepared: true", text)
        self.assertIn("workspace_ready:", text)
        self.assertIn("snapshot_written:", text)
        self.assertIn("snapshot_mode:", text)
        self.assertIn("media_alias_ready:", text)

    def test_error_no_stacktrace(self):
        result = prepare_kso_local_visual_demo(None, None, None)
        text = repr(result) + format_kso_local_visual_demo_prepare_result(result)
        self.assertNotIn("Traceback", text)

    def test_error_no_path(self):
        result = prepare_kso_local_visual_demo(None, None, None)
        text = repr(result) + format_kso_local_visual_demo_prepare_result(result)
        self.assertNotIn("None", text)

    def test_hold_output_safe(self):
        """Even hold output has no forbidden substrings."""
        _write_state(self.root, state="transaction")
        _write_media_kso(self.root)
        _write_manifest_kso(self.root)
        result = prepare_kso_local_visual_demo(
            self.root, self.source, self.runtime)
        text = repr(result) + format_kso_local_visual_demo_prepare_result(result)
        self.assertTrue(_no_forbidden(text))


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

    def test_no_state_written(self):
        _full_fixture(self.root)
        state_before = (self.root / "state" / "kso_state.json").read_text()
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        state_after = (self.root / "state" / "kso_state.json").read_text()
        self.assertEqual(state_before, state_after)

    def test_no_pop_written(self):
        _full_fixture(self.root)
        prepare_kso_local_visual_demo(self.root, self.source, self.runtime)
        self.assertFalse((self.runtime / "pop").exists())

    def test_no_backend_import(self):
        import kso_player.local_visual_demo_prepare as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)

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
        self.assertNotIn("device_secret", source)


# ══════════════════════════════════════════════════════════════════════
# Tests: CLI
# ══════════════════════════════════════════════════════════════════════

class TestCLIDemoPrepare(TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())
        _write_source_shell(self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def _cli(self, *args, expect_exit=0):
        saved = sys.stdout
        try:
            sys.stdout = StringIO()
            from kso_player.cli import main
            sys.argv = ["kso-player"] + list(args)
            try:
                main()
                return 0, sys.stdout.getvalue()
            except SystemExit as e:
                return e.code, sys.stdout.getvalue()
        finally:
            sys.stdout = saved

    def test_help(self):
        code, out = self._cli("local-demo-prepare", "--help", expect_exit=0)
        self.assertIn("local demo prepare", out.lower().replace("-", " "))

    def test_success(self):
        _full_fixture(self.root)
        code, out = self._cli(
            "local-demo-prepare",
            "--root", str(self.root),
            "--source-shell-dir", str(self.source),
            "--runtime-shell-dir", str(self.runtime),
        )
        self.assertEqual(code, 0)
        self.assertIn("prepared: true", out)
        self.assertIn("snapshot_mode:", out)

    def test_missing_source(self):
        code, out = self._cli(
            "local-demo-prepare",
            "--root", str(self.root),
            "--source-shell-dir", "/nonexistent",
            "--runtime-shell-dir", str(self.runtime),
        )
        self.assertEqual(code, 1)
        self.assertIn("status: error", out)

    def test_cli_output_no_paths(self):
        _full_fixture(self.root)
        code, out = self._cli(
            "local-demo-prepare",
            "--root", str(self.root),
            "--source-shell-dir", str(self.source),
            "--runtime-shell-dir", str(self.runtime),
        )
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), out)

    def test_cli_output_no_media_ref(self):
        _full_fixture(self.root)
        code, out = self._cli(
            "local-demo-prepare",
            "--root", str(self.root),
            "--source-shell-dir", str(self.source),
            "--runtime-shell-dir", str(self.runtime),
        )
        self.assertEqual(code, 0)
        self.assertNotIn(KSO_MEDIA_REF, out)

    def test_cli_output_no_forbidden(self):
        _full_fixture(self.root)
        code, out = self._cli(
            "local-demo-prepare",
            "--root", str(self.root),
            "--source-shell-dir", str(self.source),
            "--runtime-shell-dir", str(self.runtime),
        )
        self.assertEqual(code, 0)
        self.assertTrue(_no_forbidden(out),
            f"forbidden in CLI output: {out[:200]}")

    def test_cli_error_no_stacktrace(self):
        code, out = self._cli(
            "local-demo-prepare",
            "--root", str(self.root),
            "--source-shell-dir", "/nonexistent",
            "--runtime-shell-dir", str(self.runtime),
        )
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    import unittest
    unittest.main()
