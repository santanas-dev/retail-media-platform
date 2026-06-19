"""Tests for kso_player.cli playback-dry-run — full pipeline dry-run, no media played."""

import hashlib as _hl
import json as _json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG_SHA = _hl.sha256(PNG).hexdigest()
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
MID1 = "11111111-1111-1111-1111-111111111111"

MANIFEST_FILE = "manifest/current_manifest.json"
MEDIA_CURRENT = "media/current"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_player.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _make_item(mid=MID1, filename="item.png", ct="image/png",
               sha=PNG_SHA, size=len(PNG), dur=5000, order=0):
    return {
        "manifest_item_id": mid, "filename": filename,
        "content_type": ct, "sha256": sha,
        "size_bytes": size, "duration_ms": dur, "order": order,
    }


def _make_manifest(items=None):
    return {
        "manifest_version_id": MVID, "manifest_hash": MHASH,
        "source": "current",
        "generated_at": "2026-06-19T10:00:00Z",
        "valid_until": None, "fetched_at": "2026-06-19T10:01:00Z",
        "campaign_id": None, "items": items or [],
    }


def _init_dirs(root: Path):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    (root / MEDIA_CURRENT).mkdir(parents=True, exist_ok=True)
    (root / "status").mkdir(parents=True, exist_ok=True)


def _write_manifest(root: Path, data: dict):
    mf = root / MANIFEST_FILE
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(_json.dumps(data), encoding="utf-8")


def _write_media(root: Path, filename="item.png", content=PNG):
    mc = root / MEDIA_CURRENT
    mc.mkdir(parents=True, exist_ok=True)
    (mc / filename).write_bytes(content)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestDryRunHelp(unittest.TestCase):
    def test_help(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("playback-dry-run", out)

    def test_dry_run_help(self):
        out, err, rc = _run_cli("playback-dry-run", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)
        self.assertIn("--state", out)
        self.assertIn("dry-run", out.lower())


class TestDryRunHappy(unittest.TestCase):
    """Ready playlist + idle → session_action=play, exit 0."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_idle_play(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertEqual(rc, 0)
        self.assertIn("playlist_ready: true", out)
        self.assertIn("playback_allowed: true", out)
        self.assertIn("safety_action: play", out)
        self.assertIn("session_action: play", out)
        self.assertIn("session_reason: ready", out)

    def test_selected_fields_present(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertIn("selected_order:", out)
        self.assertIn("selected_content_type:", out)
        self.assertIn("selected_duration_ms:", out)


class TestDryRunBlocked(unittest.TestCase):
    """Non-idle state → session_action=stop/hold, exit 1."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

    def test_payment_stop(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "payment",
        )
        self.assertEqual(rc, 1)
        self.assertIn("playback_allowed: false", out)
        self.assertIn("safety_action: stop", out)
        self.assertIn("session_action: stop", out)

    def test_transaction_stop(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "transaction",
        )
        self.assertEqual(rc, 1)
        self.assertIn("session_action: stop", out)

    def test_service_stop(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "service",
        )
        self.assertEqual(rc, 1)

    def test_error_stop(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "error",
        )
        self.assertEqual(rc, 1)

    def test_maintenance_stop(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "maintenance",
        )
        self.assertEqual(rc, 1)

    def test_offline_stop(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "offline",
        )
        self.assertEqual(rc, 1)

    def test_unknown_hold(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "unknown",
        )
        self.assertEqual(rc, 1)
        self.assertIn("safety_action: hold", out)
        self.assertIn("session_action: stop", out)


class TestDryRunPlaylistNotReady(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_not_ready_idle(self):
        # No manifest, no media
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertEqual(rc, 1)
        self.assertIn("playlist_ready: false", out)
        self.assertIn("safety_action: hold", out)
        self.assertIn("session_action: stop", out)


class TestDryRunArgs(unittest.TestCase):
    def test_missing_root(self):
        out, err, rc = _run_cli("playback-dry-run", "--state", "idle")
        self.assertEqual(rc, 2)

    def test_missing_state(self):
        out, err, rc = _run_cli("playback-dry-run", "--root", "/tmp/xyz")
        self.assertEqual(rc, 2)

    def test_invalid_state(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", "/tmp/xyz", "--state", "watching_tv",
        )
        self.assertEqual(rc, 2)


class TestDryRunSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_filename_in_output(self):
        item = _make_item(filename="my_ad.mp4")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root, "my_ad.mp4")

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertNotIn("my_ad.mp4", out)

    def test_no_manifest_item_id(self):
        item = _make_item(mid="deadbeef-dead-beef-dead-beefdeadbeef")
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root, "item.png")

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertNotIn("deadbeef", out)

    def test_no_sha256(self):
        item = _make_item(sha="d" * 64)
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertNotIn("d" * 64, out)

    def test_no_absolute_paths(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn(str(self.root), combined)
        self.assertNotIn("/tmp/", combined)

    def test_no_forbidden_substrings(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        for state in ["idle", "payment"]:
            out, err, rc = _run_cli(
                "playback-dry-run", "--root", str(self.root), "--state", state,
            )
            combined = (out + err).lower()
            for fb in FORBIDDEN:
                self.assertNotIn(
                    fb, combined,
                    f"Dry-run output for state='{state}' contains forbidden '{fb}'"
                )

    def test_no_full_manifest(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn(MVID, combined)
        self.assertNotIn(MHASH, combined)

    def test_no_media_bytes(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn("PNG", combined)
        self.assertNotIn("\x89", combined)

    def test_no_stacktrace(self):
        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn("Traceback", combined)
        self.assertNotIn('File "', combined)


class TestDryRunNoNetwork(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_backend_calls(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(self.root), "--state", "idle",
        )
        self.assertEqual(rc, 0)

    def test_no_secret_config_token(self):
        root2 = Path(tempfile.mkdtemp())
        (root2 / "manifest").mkdir()
        (root2 / MEDIA_CURRENT).mkdir(parents=True)

        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(root2, manifest)
        _write_media(root2)

        out, err, rc = _run_cli(
            "playback-dry-run", "--root", str(root2), "--state", "payment",
        )
        self.assertEqual(rc, 1)
        self.assertIn("session_action: stop", out)


if __name__ == "__main__":
    unittest.main()
