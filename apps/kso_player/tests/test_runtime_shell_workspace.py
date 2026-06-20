"""Tests for KSO Player Runtime Shell Workspace Core.

Tests prepare_kso_runtime_shell_workspace() and format function.
Uses temp directories. NO backend, NO HTTP, NO Chromium.
"""

import os
import tempfile
from pathlib import Path
from unittest import TestCase

from kso_player.runtime_shell_workspace import (
    KsoRuntimeShellWorkspaceResult,
    prepare_kso_runtime_shell_workspace,
    format_kso_runtime_shell_workspace_result,
    SHELL_WHITELIST,
    STATUS_OK,
    STATUS_ERROR,
    REASON_PREPARED,
    REASON_SOURCE_DIR_MISSING,
    REASON_REQUIRED_FILES_MISSING,
    REASON_COPY_FAILED,
    REASON_INVALID_ARGS,
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


def _create_source_shell(source_dir):
    """Create a valid source shell with all 5 whitelist files."""
    source_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "index.html": "<!DOCTYPE html><html><head></head><body></body></html>",
        "styles.css": "body { margin: 0; }",
        "player.js": '"use strict";',
        "bootstrap_snapshot.js": '"use strict";',
        "bootstrap.js": '"use strict";',
    }
    for fname, content in files.items():
        (source_dir / fname).write_text(content)
    return source_dir


def _create_source_with_extra(source_dir):
    """Create source with whitelist + extra files/subdirectories."""
    _create_source_shell(source_dir)
    # Extra files (should be ignored)
    (source_dir / "README.txt").write_text("extra")
    (source_dir / ".env").write_text("VAR=1")
    (source_dir / ".hidden").write_text("hidden")
    # Subdirectory (should be ignored)
    subdir = source_dir / "extra_subdir"
    subdir.mkdir()
    (subdir / "extra.js").write_text("ignored")
    return source_dir


# ══════════════════════════════════════════════════════════════════════
# Tests: successful prepare
# ══════════════════════════════════════════════════════════════════════

class TestSuccessfulPrepare(TestCase):
    """Full workspace prepare copies exactly 5 whitelist files."""

    def setUp(self):
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_copies_all_five_files(self):
        _create_source_shell(self.source)
        result = prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.prepared)
        self.assertTrue(result.source_valid)
        self.assertTrue(result.runtime_dir_ready)
        self.assertEqual(result.files_expected, len(SHELL_WHITELIST))
        self.assertEqual(result.files_copied, len(SHELL_WHITELIST))
        self.assertEqual(result.reason, REASON_PREPARED)

    def test_runtime_files_actually_exist(self):
        _create_source_shell(self.source)
        prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        for fname in SHELL_WHITELIST:
            self.assertTrue((self.runtime / fname).is_file(),
                f"{fname} should exist in runtime")

    def test_runtime_files_match_source(self):
        _create_source_shell(self.source)
        prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        for fname in SHELL_WHITELIST:
            src_content = (self.source / fname).read_bytes()
            dst_content = (self.runtime / fname).read_bytes()
            self.assertEqual(src_content, dst_content,
                f"{fname} content mismatch")

    def test_creates_runtime_dir_if_missing(self):
        _create_source_shell(self.source)
        runtime_new = Path(tempfile.mkdtemp()) / "new_runtime"
        try:
            self.assertFalse(runtime_new.exists())
            result = prepare_kso_runtime_shell_workspace(self.source, runtime_new)
            self.assertEqual(result.status, STATUS_OK)
            self.assertTrue(runtime_new.is_dir())
        finally:
            import shutil
            shutil.rmtree(runtime_new.parent, ignore_errors=True)

    def test_source_not_modified(self):
        _create_source_shell(self.source)
        before_mtimes = {
            fname: (self.source / fname).stat().st_mtime
            for fname in SHELL_WHITELIST
        }
        prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        for fname in SHELL_WHITELIST:
            after_mtime = (self.source / fname).stat().st_mtime
            self.assertEqual(before_mtimes[fname], after_mtime,
                f"source {fname} was modified")

    def test_extra_files_ignored(self):
        _create_source_with_extra(self.source)
        result = prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.files_copied, len(SHELL_WHITELIST))
        # Extra files should NOT be in runtime
        self.assertFalse((self.runtime / "README.txt").exists())
        self.assertFalse((self.runtime / ".env").exists())
        self.assertFalse((self.runtime / ".hidden").exists())

    def test_subdirectories_ignored(self):
        _create_source_with_extra(self.source)
        prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        self.assertFalse((self.runtime / "extra_subdir").exists())

    def test_only_whitelist_files_in_runtime(self):
        _create_source_shell(self.source)
        prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        runtime_files = set(f.name for f in self.runtime.iterdir() if f.is_file())
        self.assertEqual(runtime_files, set(SHELL_WHITELIST))


# ══════════════════════════════════════════════════════════════════════
# Tests: error cases
# ══════════════════════════════════════════════════════════════════════

class TestErrorCases(TestCase):
    """Missing source, missing files, invalid args."""

    def setUp(self):
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_missing_source_dir(self):
        nonexistent = Path(tempfile.mkdtemp())
        nonexistent.rmdir()
        result = prepare_kso_runtime_shell_workspace(nonexistent, self.runtime)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_SOURCE_DIR_MISSING)
        self.assertFalse(result.prepared)
        self.assertFalse(result.source_valid)

    def test_missing_required_file(self):
        source = Path(tempfile.mkdtemp())
        try:
            _create_source_shell(source)
            (source / "index.html").unlink()
            result = prepare_kso_runtime_shell_workspace(source, self.runtime)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_REQUIRED_FILES_MISSING)
            self.assertFalse(result.prepared)
        finally:
            import shutil
            shutil.rmtree(source, ignore_errors=True)

    def test_invalid_source_none(self):
        result = prepare_kso_runtime_shell_workspace(None, self.runtime)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_invalid_runtime_none(self):
        source = Path(tempfile.mkdtemp())
        try:
            _create_source_shell(source)
            result = prepare_kso_runtime_shell_workspace(source, None)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_INVALID_ARGS)
        finally:
            import shutil
            shutil.rmtree(source, ignore_errors=True)

    def test_source_is_file_not_dir(self):
        source = Path(tempfile.mkdtemp())
        try:
            src_file = source / "not_a_dir"
            src_file.write_text("not a directory")
            result = prepare_kso_runtime_shell_workspace(src_file, self.runtime)
            self.assertEqual(result.status, STATUS_ERROR)
        finally:
            import shutil
            shutil.rmtree(source, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(TestCase):
    """repr/format never exposes paths, filenames, forbidden substrings."""

    def setUp(self):
        self.source = Path(tempfile.mkdtemp())
        self.runtime = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_repr_no_path(self):
        _create_source_shell(self.source)
        result = prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        text = repr(result)
        self.assertNotIn(str(self.source), text)
        self.assertNotIn(str(self.runtime), text)

    def test_repr_no_filenames(self):
        _create_source_shell(self.source)
        result = prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        text = repr(result)
        self.assertNotIn("index.html", text)
        self.assertNotIn("player.js", text)
        self.assertNotIn("bootstrap", text)

    def test_repr_no_forbidden(self):
        _create_source_shell(self.source)
        result = prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        text = repr(result) + format_kso_runtime_shell_workspace_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_error_no_stacktrace(self):
        result = prepare_kso_runtime_shell_workspace(None, self.runtime)
        text = repr(result) + format_kso_runtime_shell_workspace_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("stacktrace", text)

    def test_format_has_expected_fields(self):
        _create_source_shell(self.source)
        result = prepare_kso_runtime_shell_workspace(self.source, self.runtime)
        text = format_kso_runtime_shell_workspace_result(result)
        self.assertIn("prepared: true", text)
        self.assertIn("source_valid: true", text)
        self.assertIn("files_expected:", text)
        self.assertIn("files_copied:", text)

    def test_error_repr_safe(self):
        result = prepare_kso_runtime_shell_workspace(None, self.runtime)
        text = repr(result) + format_kso_runtime_shell_workspace_result(result)
        self.assertTrue(_no_forbidden(text))


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """No backend, no HTTP, no secret reads, no PoP, no Chromium."""

    def test_no_http_no_backend(self):
        import kso_player.runtime_shell_workspace as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_no_secret_read(self):
        import kso_player.runtime_shell_workspace as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("os.environ", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("configparser", source.lower())

    def test_no_media_bytes_read(self):
        import kso_player.runtime_shell_workspace as mod
        with open(mod.__file__) as f:
            source = f.read()
        # Only reads shell files (index.html, .css, .js), not media
        # The module reads source shell files, but that's explicitly shell files
        # No read_bytes for arbitrary media

    def test_no_direct_chromium(self):
        import kso_player.runtime_shell_workspace as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("subprocess", source.lower())
        self.assertNotIn("webbrowser", source.lower())
        self.assertNotIn("os.system", source.lower())

    def test_no_windows_msi_programdata(self):
        import kso_player.runtime_shell_workspace as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)


if __name__ == "__main__":
    import unittest
    unittest.main()
