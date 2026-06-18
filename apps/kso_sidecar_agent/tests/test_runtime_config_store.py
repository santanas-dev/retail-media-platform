"""Tests for RuntimeConfigStore — local file only, no network, no backend."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_CONFIG_HASH = "abc123hash123"
NOW = 1_750_000_000.0

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
    )
    return r.returncode, r.stdout, r.stderr


def _init_root(root):
    _run("init-local-root", "--root", root)


def _valid_snapshot(**overrides):
    from kso_sidecar_agent.runtime_config_client import RuntimeConfigSnapshot
    kwargs = {
        "status": "updated",
        "config_hash": TEST_CONFIG_HASH,
        "etag": f'"{TEST_CONFIG_HASH}"',
        "generated_at": "2026-06-18T10:00:00+00:00",
        "config": {"display_timeout_sec": 30, "log_level": "info"},
        "fetched_at": NOW,
        "not_modified": False,
    }
    kwargs.update(overrides)
    return RuntimeConfigSnapshot(**kwargs)


# ══════════════════════════════════════════════════════════════════════

class TestRuntimeConfigStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        _init_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # ── Write / Read ───────────────────────────────────────────────

    def test_write_creates_file(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        snap = _valid_snapshot()
        result = write_runtime_config(self.root, snap, now=NOW)
        self.assertTrue(result["written"])
        path = Path(self.root) / "config" / "runtime_config.json"
        self.assertTrue(path.exists())

    def test_read_roundtrip(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config, read_runtime_config
        snap = _valid_snapshot()
        write_runtime_config(self.root, snap, now=NOW)
        data = read_runtime_config(self.root)
        self.assertEqual(data["config_hash"], TEST_CONFIG_HASH)
        self.assertEqual(data["config"]["display_timeout_sec"], 30)

    # ── not_modified ───────────────────────────────────────────────

    def test_not_modified_existing_file_no_overwrite(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        snap = _valid_snapshot()
        write_runtime_config(self.root, snap, now=NOW)

        # Now write a not_modified snapshot
        snap2 = _valid_snapshot(not_modified=True, config_hash="should-not-change")
        result = write_runtime_config(self.root, snap2, now=NOW + 100)
        self.assertFalse(result["written"])
        self.assertEqual(result["reason"], "not_modified")
        # Original hash preserved
        from kso_sidecar_agent.runtime_config_store import read_runtime_config
        data = read_runtime_config(self.root)
        self.assertEqual(data["config_hash"], TEST_CONFIG_HASH)

    def test_not_modified_missing_file_raises(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        snap = _valid_snapshot(not_modified=True)
        with self.assertRaises(FileNotFoundError):
            write_runtime_config(self.root, snap, now=NOW)

    # ── Validation ─────────────────────────────────────────────────

    def test_forbidden_key_rejected(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        snap = _valid_snapshot(config={"token": "value"})
        with self.assertRaises(ValueError):
            write_runtime_config(self.root, snap, now=NOW)

    def test_forbidden_value_rejected(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        snap = _valid_snapshot(config={"url": "https://x.com?token=abc"})
        with self.assertRaises(ValueError):
            write_runtime_config(self.root, snap, now=NOW)

    def test_forbidden_nested_key_rejected(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        snap = _valid_snapshot(config={"nested": {"api_key": "secret"}})
        with self.assertRaises(ValueError):
            write_runtime_config(self.root, snap, now=NOW)

    def test_missing_config_hash_rejected(self):
        from kso_sidecar_agent.runtime_config_store import validate_runtime_config_file
        with self.assertRaises(ValueError):
            validate_runtime_config_file({"config": {}, "fetched_at": "x"})

    def test_config_not_dict_rejected(self):
        from kso_sidecar_agent.runtime_config_store import validate_runtime_config_file
        with self.assertRaises(ValueError):
            validate_runtime_config_file({
                "config_hash": "x", "config": "string", "fetched_at": "x",
            })

    # ── CLI: runtime-config-status ─────────────────────────────────

    def test_cli_status_missing(self):
        code, out, err = _run("runtime-config-status", "--root", self.root)
        self.assertEqual(code, 0)
        self.assertIn("MISSING", out)

    def test_cli_status_present(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        write_runtime_config(self.root, _valid_snapshot(), now=NOW)
        code, out, err = _run("runtime-config-status", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("PRESENT", out)
        self.assertIn("config_hash:", out)
        self.assertIn("etag_present:", out)
        self.assertIn("config_keys_count:", out)

    def test_cli_status_no_full_config_dump(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        write_runtime_config(self.root, _valid_snapshot(), now=NOW)
        code, out, err = _run("runtime-config-status", "--root", self.root)
        # Should not print the entire config dict
        self.assertNotIn("display_timeout_sec", out)

    def test_cli_status_invalid_json(self):
        path = Path(self.root) / "config" / "runtime_config.json"
        path.write_text("not json at all")
        code, out, err = _run("runtime-config-status", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("INVALID", out)

    # ── CLI: doctor ────────────────────────────────────────────────

    def test_doctor_without_runtime_config(self):
        # doctor should work without runtime_config (warning, not fatal)
        _run("set-status", "--root", self.root, "--status", "running")
        _run("write-config", "--root", self.root,
             "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = _run("doctor", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("runtime_config_ok: False", out)
        self.assertIn("All checks passed", out)

    def test_doctor_with_valid_runtime_config(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        write_runtime_config(self.root, _valid_snapshot(), now=NOW)
        _run("set-status", "--root", self.root, "--status", "running")
        _run("write-config", "--root", self.root,
             "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = _run("doctor", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("runtime_config_ok: True", out)

    def test_doctor_with_invalid_runtime_config(self):
        path = Path(self.root) / "config" / "runtime_config.json"
        path.write_text("bad json")
        _run("set-status", "--root", self.root, "--status", "running")
        _run("write-config", "--root", self.root,
             "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = _run("doctor", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")  # warning, not fatal
        self.assertIn("runtime_config_ok: False", out)

    # ── Runtime config file security ───────────────────────────────

    def test_runtime_config_json_has_no_forbidden(self):
        """Verify the written file contains no forbidden strings."""
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        write_runtime_config(self.root, _valid_snapshot(), now=NOW)
        content = (Path(self.root) / "config" / "runtime_config.json").read_text()

        forbidden = [
            "token", "jwt", "password", "secret", "api_key",
            "private_key", "payment_card", "receipt",
            "local_path", "file_path", "authorization", "bearer",
        ]
        lower = content.lower()
        for word in forbidden:
            self.assertNotIn(word, lower, f"Forbidden word '{word}' in runtime_config.json")

    def test_atomic_write_no_tmp_left(self):
        from kso_sidecar_agent.runtime_config_store import write_runtime_config
        write_runtime_config(self.root, _valid_snapshot(), now=NOW)
        config_dir = Path(self.root) / "config"
        tmp_files = list(config_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0, f"Leftover .tmp files: {tmp_files}")

    # ── Doctor no stacktrace ───────────────────────────────────────

    def test_doctor_invalid_runtime_no_stacktrace(self):
        path = Path(self.root) / "config" / "runtime_config.json"
        path.write_text("{invalid")
        _run("set-status", "--root", self.root, "--status", "running")
        _run("write-config", "--root", self.root,
             "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = _run("doctor", "--root", self.root)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
