"""Tests for run-once --local-only CLI — no backend, no HTTP, no secret."""

import hashlib as _hl
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

FORBIDDEN_OUTPUT = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
]

TEST_CONTENT = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_SHA = _hl.sha256(TEST_CONTENT).hexdigest()


def _run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
        timeout=15,
    )
    return r.returncode, r.stdout, r.stderr


def _setup_full_root(root):
    """Set up a complete agent root with config, runtime_config, manifest, media."""
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root,
         "--backend-base-url", "http://127.0.0.1:8080",
         "--device-code", "a-05954")

    # Runtime config
    rc_path = Path(root) / "config" / "runtime_config.json"
    rc_data = {
        "status": "ok",
        "config_hash": "a" * 64,
        "etag": "etag-" + "a" * 12,
        "generated_at": "2026-06-19T10:00:00Z",
        "fetched_at": "2026-06-19T10:00:00Z",
        "config": {"key1": "value1"},
    }
    rc_path.parent.mkdir(parents=True, exist_ok=True)
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
                "size_bytes": len(TEST_CONTENT),
                "duration_ms": 5000,
                "order": 0,
            },
        ],
    }
    (manifest_dir / "current_manifest.json").write_text(json.dumps(manifest_data))

    # Media
    media_current = Path(root) / "media" / "current"
    media_current.mkdir(parents=True, exist_ok=True)
    (media_current / f"{item_id}.png").write_bytes(TEST_CONTENT)


def _setup_config_only(root):
    """Set up root with only config (no manifest, no media, no rc)."""
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root,
         "--backend-base-url", "http://127.0.0.1:8080",
         "--device-code", "a-05954")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestRunOnceCLI(unittest.TestCase):

    # ── Help ────────────────────────────────────────────────────────

    def test_help_shows_run_once(self):
        rc, out, err = _run("--help")
        self.assertEqual(rc, 0)
        self.assertIn("run-once", out)

    def test_run_once_help_shows_local_only(self):
        rc, out, err = _run("run-once", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--local-only", out)

    # ── Gate: --local-only required ────────────────────────────────

    def test_reject_without_local_only(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_config_only(root)
            rc, out, err = _run("run-once", "--root", root)
            self.assertNotEqual(rc, 0)
            self.assertIn("only --local-only", err)

    # ── Success: full ready root ───────────────────────────────────

    def test_full_ready_ok(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            self.assertEqual(rc, 0)
            self.assertIn("run_cycle:", out)
            self.assertIn("mode:                local_only", out)
            self.assertIn("runtime_config_status:", out)
            self.assertIn("manifest_status:", out)

    def test_full_ready_media_counts(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            self.assertEqual(rc, 0)
            self.assertIn("media_cache_complete:", out)
            self.assertIn("media_items_total:", out)
            self.assertIn("media_items_cached:", out)

    # ── Warning: config only, no manifest ──────────────────────────

    def test_config_only_warning(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_config_only(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            self.assertEqual(rc, 0)
            self.assertIn("run_cycle:           warning", out)

    # ── Error: no config ───────────────────────────────────────────

    def test_no_config_error(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "status").mkdir(parents=True, exist_ok=True)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            self.assertEqual(rc, 1)
            self.assertIn("run_cycle:           error", out)
            self.assertIn("last_error_code:", out)

    # ── Agent status update ────────────────────────────────────────

    def test_updates_agent_status(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            _run("run-once", "--root", root, "--local-only")

            status_path = Path(root) / "status" / "agent_status.json"
            self.assertTrue(status_path.exists())

            data = json.loads(status_path.read_text())
            self.assertIn("_cycle", data)
            self.assertEqual(data["_cycle"]["media_items_total"], 1)
            self.assertTrue(data["_cycle"]["media_cache_complete"])

    # ── Safe output — no secrets ───────────────────────────────────

    def test_no_forbidden_in_output_ok(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            combined = (out + err).lower()

            for fb in FORBIDDEN_OUTPUT:
                self.assertNotIn(fb, combined,
                                 f"Forbidden '{fb}' found in run-once output")

    def test_no_forbidden_in_output_error(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "status").mkdir(parents=True, exist_ok=True)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            combined = (out + err).lower()

            for fb in FORBIDDEN_OUTPUT:
                self.assertNotIn(fb, combined,
                                 f"Forbidden '{fb}' found in run-once error output")

    def test_no_full_config_in_output(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            combined = out + err

            self.assertNotIn("backend_base_url", combined)
            self.assertNotIn("device_code", combined)
            self.assertNotIn("127.0.0.1", combined)

    def test_no_full_manifest_in_output(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            combined = out + err

            self.assertNotIn("manifest_version_id", combined)
            self.assertNotIn("11111111-1111", combined)

    def test_no_stacktrace_in_output(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            rc, out, err = _run("run-once", "--root", root, "--local-only")
            combined = out + err

            self.assertNotIn("Traceback", combined)
            self.assertNotIn('File "', combined)

    # ── No backend calls ───────────────────────────────────────────

    def test_no_backend_calls(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)
            rc, out, err = _run("run-once", "--root", root, "--local-only")
            self.assertEqual(rc, 0)
            # No HTTP error messages that would indicate backend attempts
            self.assertNotIn("Connection refused", err)
            self.assertNotIn("HTTP", err)

    # ── No forbidden in agent_status ───────────────────────────────

    def test_no_forbidden_in_agent_status(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_full_root(root)

            _run("run-once", "--root", root, "--local-only")

            status_path = Path(root) / "status" / "agent_status.json"
            data = json.loads(status_path.read_text())
            data_str = json.dumps(data).lower()

            for fb in FORBIDDEN_OUTPUT:
                self.assertNotIn(fb, data_str,
                                 f"Forbidden '{fb}' found in agent_status")

    # ── Missing root ───────────────────────────────────────────────

    def test_missing_root_error(self):
        rc, out, err = _run("run-once", "--root", "/tmp/nonexistent-root-kso-12345",
                            "--local-only")
        self.assertEqual(rc, 1)
        self.assertIn("run_cycle:           error", out)

    # ── help output shows future flags ─────────────────────────────

    def test_help_shows_future_flags(self):
        rc, out, err = _run("run-once", "--help")
        self.assertIn("--retry-auth", out)
        self.assertIn("--skip-media", out)
        self.assertIn("--max-cycle-sec", out)


if __name__ == "__main__":
    unittest.main()
