"""Tests for KSO Player display cycle core.

Covers run_kso_display_cycle_once() + format + CLI.
No backend, no HTTP, no sidecar, no Chromium, no systemd.
"""

import json
import shutil
import sys as _sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kso_player.display_cycle import (
    run_kso_display_cycle_once,
    format_kso_display_cycle_result,
    KsoDisplayCycleResult,
    STATUS_OK,
    STATUS_HOLD,
    STATUS_ERROR,
    STATUS_WARNING,
    REASON_RENDER_READY,
    REASON_POP_WRITTEN,
    REASON_NO_POP_CONFIRM,
    REASON_DECISION_HOLD,
    REASON_INVALID_ARGS,
    REASON_INTERNAL_ERROR,
    RENDER_ACTION_RENDER,
    RENDER_ACTION_HOLD,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_idle_state(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return {
        "state": "idle",
        "updated_at_utc": now.isoformat(timespec="seconds"),
        "source": "ukm4_state_adapter",
    }


def _make_kso_manifest():
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": "kso",
        "storeCode": "safe_store",
        "deviceCode": "safe_device",
        "items": [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }],
    }


_PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _setup_idle_with_manifest(root):
    """Setup: idle state + KSO safe manifest + media file."""
    (root / "state").mkdir(parents=True, exist_ok=True)
    state = _make_idle_state()
    (root / "state" / "kso_state.json").write_text(json.dumps(state))

    (root / "manifest").mkdir(parents=True, exist_ok=True)
    manifest = _make_kso_manifest()
    (root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))

    (root / "media" / "current").mkdir(parents=True, exist_ok=True)
    (root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestDisplayCycle(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_dc_"))
        self.root = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Happy path ───────────────────────────────────────────────

    def test_idle_manifest_media_no_confirm(self):
        """idle + safe manifest + media exists + no confirm → render_ready, pop_written=false."""
        _setup_idle_with_manifest(self.root)

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=False)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.render_ready)
        self.assertEqual(result.render_action, RENDER_ACTION_RENDER)
        self.assertFalse(result.pop_written)
        self.assertFalse(result.pop_write_requested)
        self.assertEqual(result.reason, REASON_NO_POP_CONFIRM)

    def test_idle_manifest_media_with_confirm(self):
        """idle + manifest + media + confirm → pop_written=true."""
        _setup_idle_with_manifest(self.root)

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.render_ready)
        self.assertEqual(result.render_action, RENDER_ACTION_RENDER)
        self.assertTrue(result.pop_write_requested)
        self.assertTrue(result.pop_written)
        self.assertEqual(result.reason, REASON_POP_WRITTEN)

        # Verify pop file exists
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists(), "PoP file must exist after confirm")

    # ── No PoP without confirm ───────────────────────────────────

    def test_confirm_flag_required_for_pop_write(self):
        """PoP write only when confirm_pop_write=True."""
        _setup_idle_with_manifest(self.root)

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=False)
        self.assertFalse(result.pop_write_requested)
        self.assertFalse(result.pop_written)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop_file.exists(), "PoP must NOT be written without confirm")

    # ── Non-idle state → no pop ─────────────────────────────────

    def test_non_idle_state_no_pop(self):
        """Non-idle state → hold, no PoP."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {"state": "transaction", "updated_at_utc": datetime.now(timezone.utc).isoformat(), "source": "ukm4"}
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))

        # Set up manifest + media separately (not _setup_idle_with_manifest — that writes state=idle)
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(_make_kso_manifest()))
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        self.assertIn(result.status, [STATUS_HOLD, STATUS_WARNING])
        self.assertFalse(result.render_ready)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertFalse(result.pop_written)

    def test_stale_state_no_pop(self):
        """Stale state → hold, no PoP."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        old = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        state = {"state": "idle", "updated_at_utc": old.isoformat(), "source": "ukm4"}
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True, stale_seconds=30)
        self.assertFalse(result.pop_written)

    def test_missing_state_no_pop(self):
        """Missing state → hold."""
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(_make_kso_manifest()))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.pop_written)
        self.assertFalse(result.render_ready)

    # ── Missing manifest → no pop ────────────────────────────────

    def test_missing_manifest_no_pop(self):
        """Missing manifest → hold."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps(_make_idle_state()))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.render_ready)
        self.assertFalse(result.pop_written)

    def test_gateway_wrapper_manifest_no_pop(self):
        """Gateway wrapper manifest → invalid → hold."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps(_make_idle_state()))
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        wrapper = {"status": "served", "manifest": _make_kso_manifest()}
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(wrapper))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.render_ready)
        self.assertFalse(result.pop_written)

    # ── Missing media → no pop ──────────────────────────────────

    def test_missing_media_no_pop(self):
        """Manifest exists but media missing → hold."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps(_make_idle_state()))
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(_make_kso_manifest()))
        # No media directory

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.render_ready)
        self.assertFalse(result.pop_written)

    def test_unsupported_content_type_no_pop(self):
        """Unsupported content type → hold."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps(_make_idle_state()))

        manifest = _make_kso_manifest()
        manifest["items"][0]["contentType"] = "application/pdf"
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.render_ready)
        self.assertFalse(result.pop_written)

    def test_unsafe_media_ref_no_pop(self):
        """Unsafe mediaRef → hold."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps(_make_idle_state()))

        manifest = _make_kso_manifest()
        manifest["items"][0]["mediaRef"] = "../../etc/passwd"
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.render_ready)
        self.assertFalse(result.pop_written)

    # ── PoP writer integration ──────────────────────────────────

    def test_pop_writer_confirm_writes_valid_jsonl(self):
        """Confirm writes valid JSONL with allowed keys."""
        _setup_idle_with_manifest(self.root)

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertTrue(result.pop_written)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists())

        lines = pop_file.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])

        # Check allowed keys present
        self.assertIn("schema_version", record)
        self.assertIn("event_type", record)
        self.assertIn("safety_state", record)
        self.assertEqual(record["safety_state"], "idle")

        # No forbidden keys
        forbidden = {"token", "secret", "filename", "sha256",
                     "manifest_item_id", "backend_base_url", "stacktrace",
                     "media_path", "file_path"}
        self.assertTrue(forbidden.isdisjoint(record.keys()))

    # ── Invalid args ────────────────────────────────────────────

    def test_invalid_stale_seconds(self):
        result = run_kso_display_cycle_once(self.root, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_invalid_root(self):
        result = run_kso_display_cycle_once(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    # ── Output safety ───────────────────────────────────────────

    def _assert_safe_output(self, output):
        lower = output.lower()
        forbidden = [
            "/tmp/", "/var/", "slot-", "current_manifest",
            "backend_url", "device_code", "device_secret",
            "authorization", "bearer", "sha256",
            "manifest_item_id", "manifest_version_id", "manifest_hash",
            "campaign_id", "creative_id", "rendition_id",
            "schedule_item_id", "batch_id", "booking_id",
            "file_path", "media_path", "storage", "minio",
            "stacktrace", "traceback",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, lower,
                             f"Safe output must not contain '{fb}': {output[:200]}")

    def test_result_repr_safe(self):
        _setup_idle_with_manifest(self.root)
        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self._assert_safe_output(repr(result))

    def test_format_safe(self):
        _setup_idle_with_manifest(self.root)
        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        output = format_kso_display_cycle_result(result)
        self._assert_safe_output(output)
        # Check allowed fields present
        self.assertIn("status:", output)
        self.assertIn("render_ready:", output)
        self.assertIn("pop_written:", output)


# ══════════════════════════════════════════════════════════════════════
# CLI tests
# ══════════════════════════════════════════════════════════════════════

# Add player to path
_PLAYER_DIR = Path(__file__).resolve().parent.parent
if str(_PLAYER_DIR) not in _sys.path:
    _sys.path.insert(0, str(_PLAYER_DIR))


class TestDisplayCycleCLI(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_dc_cli_"))
        self.root = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_cli(self, *args):
        import subprocess
        import kso_player.cli as cli_mod

        old_argv = _sys.argv
        _sys.argv = ["kso_player.cli"] + list(args)
        # Capture stdout
        from io import StringIO
        import sys
        buf = StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            exit_code = cli_mod.main()
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        finally:
            sys.stdout = old_stdout
            _sys.argv = old_argv
        return exit_code, buf.getvalue()

    def test_help_works(self):
        """display-cycle-once --help works."""
        code, out = self._run_cli("display-cycle-once", "--help")
        self.assertEqual(code, 0)
        self.assertIn("display-cycle-once", out.lower())

    def test_without_confirm_no_pop_file(self):
        """Without --confirm-pop-write, no PoP file written."""
        _setup_idle_with_manifest(self.root)
        code, out = self._run_cli("display-cycle-once",
                                   "--root", str(self.root))
        # Should succeed (render ready) without PoP
        self.assertIn("render_ready: true", out)
        self.assertIn("pop_written: false", out)
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop_file.exists())

    def test_with_confirm_writes_pop(self):
        """With --confirm-pop-write, PoP file written."""
        _setup_idle_with_manifest(self.root)
        code, out = self._run_cli("display-cycle-once",
                                   "--root", str(self.root),
                                   "--confirm-pop-write")
        self.assertIn("pop_written: true", out)
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists())

    def test_cli_output_safe(self):
        """CLI output has no forbidden substrings."""
        _setup_idle_with_manifest(self.root)
        code, out = self._run_cli("display-cycle-once",
                                   "--root", str(self.root),
                                   "--confirm-pop-write")
        lower = out.lower()
        forbidden = ["slot-", "/tmp/", "backend_url", "device_code",
                     "device_secret", "authorization", "bearer",
                     "sha256", "manifest_item_id", "stacktrace"]
        for fb in forbidden:
            self.assertNotIn(fb, lower,
                             f"CLI output must not contain '{fb}': {out[:200]}")


if __name__ == "__main__":
    unittest.main()
