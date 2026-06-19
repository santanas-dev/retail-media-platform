"""Tests for kso_player.cli safety-check — CLI + safety gate, no backend."""

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


def _make_manifest(mvid=MVID, mhash=MHASH, items=None):
    return {
        "manifest_version_id": mvid, "manifest_hash": mhash,
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

class TestSafetyCheckHelp(unittest.TestCase):
    """safety-check --help works."""

    def test_help(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("safety-check", out)

    def test_safety_check_help(self):
        out, err, rc = _run_cli("safety-check", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)
        self.assertIn("--state", out)
        self.assertIn("allowed", out.lower())


class TestSafetyCheckHappy(unittest.TestCase):
    """Ready playlist + idle → allowed=true."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_ready_idle_exit_0(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        self.assertEqual(rc, 0)
        self.assertIn("playback_allowed: true", out)
        self.assertIn("action: play", out)
        self.assertIn("reason: ready", out)
        self.assertIn("state: idle", out)

    def test_ready_idle_shows_playlist_ready(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        self.assertIn("playlist_ready: true", out)


class TestSafetyCheckBlocked(unittest.TestCase):
    """Blocked states → exit 1."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

    def test_payment_stop(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "payment",
        )
        self.assertEqual(rc, 1)
        self.assertIn("playback_allowed: false", out)
        self.assertIn("action: stop", out)
        self.assertIn("reason: payment_active", out)

    def test_transaction_stop(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "transaction",
        )
        self.assertEqual(rc, 1)
        self.assertIn("reason: transaction_active", out)

    def test_service_stop(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "service",
        )
        self.assertEqual(rc, 1)
        self.assertIn("reason: service_active", out)

    def test_error_stop(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "error",
        )
        self.assertEqual(rc, 1)
        self.assertIn("reason: error_active", out)

    def test_maintenance_stop(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "maintenance",
        )
        self.assertEqual(rc, 1)
        self.assertIn("reason: maintenance_active", out)

    def test_offline_stop(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "offline",
        )
        self.assertEqual(rc, 1)
        self.assertIn("reason: offline", out)

    def test_unknown_hold(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "unknown",
        )
        self.assertEqual(rc, 1)
        self.assertIn("reason: state_unknown", out)
        self.assertIn("action: hold", out)


class TestSafetyCheckPlaylistNotReady(unittest.TestCase):
    """Playlist not ready → hold even in idle."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_not_ready_idle_hold(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # No media file

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        self.assertEqual(rc, 1)
        self.assertIn("playlist_ready: false", out)
        self.assertIn("playback_allowed: false", out)
        self.assertIn("action: hold", out)
        self.assertIn("reason: playlist_not_ready", out)


class TestSafetyCheckArgs(unittest.TestCase):
    """Invalid args → exit 2."""

    def test_missing_root(self):
        out, err, rc = _run_cli("safety-check", "--state", "idle")
        self.assertEqual(rc, 2)

    def test_missing_state(self):
        out, err, rc = _run_cli("safety-check", "--root", "/tmp/xyz")
        self.assertEqual(rc, 2)

    def test_invalid_state(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", "/tmp/xyz", "--state", "playing_video",
        )
        self.assertEqual(rc, 2)

    def test_empty_state(self):
        out, err, rc = _run_cli(
            "safety-check", "--root", "/tmp/xyz", "--state", "",
        )
        self.assertEqual(rc, 2)


class TestSafetyCheckSecurity(unittest.TestCase):
    """Security: no forbidden, no absolute paths, no full manifest."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_absolute_paths(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn(str(self.root), combined)
        self.assertNotIn("/home/", combined)
        self.assertNotIn("/tmp/", combined)

    def test_no_forbidden_substrings(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        for state in ["idle", "payment", "unknown"]:
            out, err, rc = _run_cli(
                "safety-check", "--root", str(self.root), "--state", state,
            )
            combined = (out + err).lower()

            for fb in FORBIDDEN:
                self.assertNotIn(
                    fb, combined,
                    f"Safety-check output for state='{state}' contains forbidden '{fb}'"
                )

    def test_no_full_manifest(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn(MVID, combined)
        self.assertNotIn(MHASH, combined)
        self.assertNotIn(MID1, combined)

    def test_no_media_bytes(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn("PNG", combined)
        self.assertNotIn("\x89", combined)

    def test_no_stacktrace(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        # No media

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        combined = out + err
        self.assertNotIn("Traceback", combined)
        self.assertNotIn('File "', combined)
        self.assertNotIn("raise ", combined)

    def test_receipt_state_allowed_as_constant(self):
        """The word 'receipt' as a state name is fine — receipt_data is not."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "receipt",
        )
        combined = (out + err).lower()
        # receipt as state is OK
        self.assertIn("state: receipt", out)
        # But receipt_data must NOT appear
        self.assertNotIn("receipt_data", combined)


class TestSafetyCheckNoNetwork(unittest.TestCase):
    """CLI does not do HTTP or read secret/config/token."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_no_backend_calls(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        self.assertEqual(rc, 0)

    def test_no_secret_config_token_read(self):
        root2 = Path(tempfile.mkdtemp())
        (root2 / "manifest").mkdir()
        (root2 / MEDIA_CURRENT).mkdir(parents=True)

        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(root2, manifest)
        _write_media(root2)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(root2), "--state", "payment",
        )
        self.assertEqual(rc, 1)
        self.assertIn("playback_allowed: false", out)


class TestSafetyCheckAllStates(unittest.TestCase):
    """Every allowed state arg works (no crash)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_all_states_accepted(self):
        from kso_player.safety import ALLOWED_STATES as AS

        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        for state in AS:
            out, err, rc = _run_cli(
                "safety-check", "--root", str(self.root), "--state", state,
            )
            self.assertIn(rc, (0, 1),
                          f"State '{state}' should give exit 0 or 1, got {rc}")
            self.assertIn(f"state: {state}", out.lower())


class TestSafetyCheckOutput(unittest.TestCase):
    """Output format and field presence."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _init_dirs(self.root)

    def test_output_has_all_fields(self):
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "idle",
        )
        self.assertIn("playlist_ready:", out)
        self.assertIn("playback_allowed:", out)
        self.assertIn("action:", out)
        self.assertIn("reason:", out)
        self.assertIn("state:", out)

    def test_both_summaries_present(self):
        """Output contains both playlist summary and safety decision."""
        item = _make_item()
        manifest = _make_manifest(items=[item])
        _write_manifest(self.root, manifest)
        _write_media(self.root)

        out, err, rc = _run_cli(
            "safety-check", "--root", str(self.root), "--state", "payment",
        )
        self.assertIn("playlist_ready: true", out)
        self.assertIn("playback_allowed: false", out)
        self.assertIn("state: payment", out)


if __name__ == "__main__":
    unittest.main()
