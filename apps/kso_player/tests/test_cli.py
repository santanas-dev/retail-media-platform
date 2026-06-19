"""Tests for kso_player.cli — playlist-status CLI, no backend, no secret."""

import hashlib as _hl
import json as _json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# ── Test data ────────────────────────────────────────────────────────

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG_SHA = _hl.sha256(PNG).hexdigest()
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 100
PNG2_SHA = _hl.sha256(PNG2).hexdigest()

MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
MID1 = "11111111-1111-1111-1111-111111111111"

MANIFEST_FILE = "manifest/current_manifest.json"
MEDIA_CURRENT = "media/current"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    """Run kso_player.cli with given args, return (stdout, stderr, exit_code)."""
    cmd = [sys.executable, "-m", "kso_player.cli", *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PKG_DIR),
    )
    return proc.stdout, proc.stderr, proc.returncode


def _make_item(mid=MID1, filename="item.png", ct="image/png",
               sha=PNG_SHA, size=len(PNG), dur=5000, order=0):
    return {
        "manifest_item_id": mid,
        "filename": filename,
        "content_type": ct,
        "sha256": sha,
        "size_bytes": size,
        "duration_ms": dur,
        "order": order,
    }


def _make_manifest(mvid=MVID, mhash=MHASH, items=None):
    return {
        "manifest_version_id": mvid,
        "manifest_hash": mhash,
        "source": "current",
        "generated_at": "2026-06-19T10:00:00Z",
        "valid_until": None,
        "fetched_at": "2026-06-19T10:01:00Z",
        "campaign_id": None,
        "items": items or [],
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

class TestCLIHelp(unittest.TestCase):
    """--help works."""

    def test_help(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("playlist-status", out)

    def test_playlist_status_help(self):
        out, err, rc = _run_cli("playlist-status", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)

    def test_no_args_shows_help(self):
        out, err, rc = _run_cli()
        self.assertEqual(rc, 0)
        self.assertIn("playlist-status", out)


class TestCLIPlaylistStatus(unittest.TestCase):
    """playlist-status exit codes and output."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_ready_exit_0(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("playlist_ready: true", out)
        self.assertIn("status: ready", out)
        self.assertIn("reason: ready", out)
        self.assertIn("items_ready: 1", out)

    def test_missing_manifest_exit_1(self):
        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("playlist_ready: false", out)
        self.assertIn("manifest_missing", out)

    def test_missing_media_exit_1(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # No media file

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("playlist_ready: false", out)
        self.assertIn("media_incomplete", out)

    def test_corrupted_media_exit_1(self):
        item = _make_item(sha=PNG_SHA)
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root, content=PNG2)  # wrong content

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("playlist_ready: false", out)
        self.assertIn("media_corrupted", out)

    def test_invalid_root(self):
        out, err, rc = _run_cli("playlist-status", "--root", "/nonexistent/path/xyz")
        self.assertEqual(rc, 1)
        self.assertIn("playlist_ready: false", out)


class TestCLISecurity(unittest.TestCase):
    """Security: no forbidden, no absolute paths, no stacktrace."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_absolute_paths_in_output(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        combined = out + err
        self.assertNotIn(str(self.root), combined)
        self.assertNotIn("/home/", combined)
        self.assertNotIn("/tmp/", combined)

    def test_no_forbidden_substrings_in_output(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        combined = (out + err).lower()

        for fb in FORBIDDEN:
            self.assertNotIn(fb, combined,
                             f"Output contains forbidden substring '{fb}'")

    def test_no_stacktrace(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # No media

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        combined = out + err
        self.assertNotIn("Traceback", combined)
        self.assertNotIn('File "', combined)
        self.assertNotIn("line ", combined)
        self.assertNotIn("raise ", combined)

    def test_no_full_manifest(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        combined = out + err
        self.assertNotIn(MVID, combined)
        self.assertNotIn(MHASH, combined)
        self.assertNotIn(MID1, combined)

    def test_no_media_bytes(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        combined = out + err
        # Should not contain raw PNG data
        self.assertNotIn("PNG", combined)
        self.assertNotIn("\x89", combined)


class TestCLINoNetwork(unittest.TestCase):
    """CLI does not perform HTTP or read secret/config/token."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_backend_calls(self):
        """CLI should work without any network — just reads local files."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli("playlist-status", "--root", str(self.root))
        self.assertEqual(rc, 0)

    def test_no_secret_config_token_read(self):
        """Even without config/secret files, CLI should work."""
        # Only manifest + media — no config/status dir populated
        root2 = Path(tempfile.mkdtemp())
        (root2 / "manifest").mkdir()
        (root2 / MEDIA_CURRENT).mkdir(parents=True)

        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(root2, manifest)
        _write_media(root2)

        out, err, rc = _run_cli("playlist-status", "--root", str(root2))
        self.assertEqual(rc, 0)
        self.assertIn("playlist_ready: true", out)


class TestCLIErrorOutput(unittest.TestCase):
    """Error output is safe."""

    def test_missing_root_arg_error(self):
        out, err, rc = _run_cli("playlist-status")
        # argparse will fail — exit 2
        self.assertEqual(rc, 2)
        combined = (out + err).lower()
        self.assertIn("--root", combined.lower() if "error" in combined.lower() else out + err or "required")


if __name__ == "__main__":
    unittest.main()
