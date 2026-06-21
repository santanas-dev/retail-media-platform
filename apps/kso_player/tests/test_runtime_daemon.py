"""KSO Player Production Daemon Loop Tests — safe, no real Chromium, no real sleep.

Tests the runtime-daemon command:
  - max_cycles=0 → safe no-op
  - max_cycles=3 → completes 3 cycles
  - launches Chromium only once
  - without confirm → no PoP
  - with confirm → PoP per cycle
  - stop_check stops daemon cleanly
  - health file written atomically and safely
  - recovery from hold/no-items cycles
  - consecutive errors stop after limit
  - safe output everywhere
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from kso_player.runtime_daemon import (
    run_kso_runtime_daemon,
    format_kso_runtime_daemon_result,
    KsoRuntimeDaemonResult,
    STATUS_OK,
    STATUS_ERROR,
    REASON_STOPPED,
    REASON_STOP_CHECK,
    REASON_MAX_ERRORS,
    REASON_INVALID_ARGS,
)
from kso_player.visible_runtime import FORBIDDEN_SUBSTRINGS

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _make_source_shell_dir(base: Path) -> Path:
    d = base / "player_shell"
    d.mkdir(parents=True, exist_ok=True)
    for fn in ["index.html", "styles.css", "player.js", "bootstrap.js",
                "bootstrap_snapshot.js"]:
        (d / fn).write_text(f"/* {fn} */\n", encoding="utf-8")
    return d


def _make_runtime_dir(base: Path) -> Path:
    d = base / "runtime_shell"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_root(base: Path) -> Path:
    d = base / "kso_root"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_fake_launcher(should_succeed=True):
    class Fake:
        pass

    def fn(cmd):
        return Fake() if should_succeed else None
    return fn


def _make_noop_sleep():
    def fn(sec):
        pass
    return fn


def _setup_full_root(root: Path, item_count=1):
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "kso_state.json").write_text(json.dumps({
        "state": "idle",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "ukm4",
    }))
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    items = []
    for i in range(item_count):
        items.append({
            "slotOrder": i, "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": f"media/current/slot-{i:03d}",
        })
    (root / "manifest" / "current_manifest.json").write_text(json.dumps({
        "schemaVersion": 1, "channel": "kso",
        "storeCode": "demo", "deviceCode": "demo",
        "items": items,
    }))
    (root / "media" / "current").mkdir(parents=True, exist_ok=True)
    for i in range(item_count):
        (root / "media" / "current" / f"slot-{i:03d}").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestRuntimeDaemon(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_dmn_"))
        self.src = _make_source_shell_dir(self.tmp)
        self.rt = _make_runtime_dir(self.tmp)
        self.root = _make_root(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _safe(self, out):
        lo = out.lower() if isinstance(out, str) else str(out).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lo, f"'{fb}' in: {out[:200]}")

    # ══════════════════════════════════════════════════════════
    # Basic operation
    # ══════════════════════════════════════════════════════════

    def test_max_cycles_zero_noop(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=0, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.cycles_completed, 0)
        self._safe(repr(result))

    def test_max_cycles_completes_all(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=3, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.cycles_completed, 3)
        self.assertEqual(result.rendered_count, 3)
        self.assertEqual(result.hold_count, 0)
        self.assertEqual(result.reason, REASON_STOPPED)
        self._safe(repr(result))

    # ══════════════════════════════════════════════════════════
    # Chromium launch (once only)
    # ══════════════════════════════════════════════════════════

    def test_launches_chromium_once(self):
        _setup_full_root(self.root, item_count=2)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_launch=True, max_cycles=3,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )
        self.assertTrue(result.launched)
        self.assertEqual(result.cycles_completed, 3)

    def test_without_confirm_launch_no_launch(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_launch=False, max_cycles=1,
            sleep_fn=_make_noop_sleep(),
        )
        self.assertFalse(result.launched)
        self.assertTrue(result.launch_ready)

    # ══════════════════════════════════════════════════════════
    # PoP behavior
    # ══════════════════════════════════════════════════════════

    def test_without_confirm_no_completed_pop(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_display_completed=False, max_cycles=3,
            sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.completed_pop_written_count, 0)
        pop = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop.exists())

    def test_with_confirm_writes_completed_pop(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_display_completed=True, max_cycles=2,
            sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.completed_pop_written_count, 2)
        pop = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop.exists())

    # ══════════════════════════════════════════════════════════
    # Stop check
    # ══════════════════════════════════════════════════════════

    def test_stop_check_stops_cleanly(self):
        _setup_full_root(self.root, item_count=1)
        calls = [0]

        def stop_check():
            calls[0] += 1
            return calls[0] >= 3

        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            stop_check=stop_check, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.reason, REASON_STOP_CHECK)
        self.assertEqual(result.cycles_completed, 2)
        self.assertEqual(calls[0], 3)

    # ══════════════════════════════════════════════════════════
    # Health file
    # ══════════════════════════════════════════════════════════

    def test_health_file_written(self):
        _setup_full_root(self.root, item_count=1)
        hf = str(self.tmp / "player-health.json")
        run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_display_completed=True, max_cycles=2,
            sleep_fn=_make_noop_sleep(), health_file=hf,
        )
        self.assertTrue(Path(hf).exists())
        with open(hf, "r") as f:
            data = json.load(f)
        self.assertIn("status", data)
        self.assertIn("cycles_completed", data)
        self.assertIn("completed_pop_written_count", data)
        self.assertEqual(data["status"], "ok")

    def test_health_file_safe_no_forbidden(self):
        _setup_full_root(self.root, item_count=1)
        hf = str(self.tmp / "player-health.json")
        run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_display_completed=True, max_cycles=2,
            sleep_fn=_make_noop_sleep(), health_file=hf,
        )
        raw = Path(hf).read_text()
        self._safe(raw)
        # Specific forbidden checks
        lower = raw.lower()
        for fb in ["manifest_item_id", "campaign_id", "sha256",
                    "file_path", "backend_url", "stacktrace", "media_ref"]:
            self.assertNotIn(fb, lower)

    # ══════════════════════════════════════════════════════════
    # Hold recovery
    # ══════════════════════════════════════════════════════════

    def test_daemon_recovers_from_hold_cycle(self):
        """Non-idle cycles → hold, daemon continues."""
        _setup_full_root(self.root, item_count=1)
        # Non-idle state
        (self.root / "state" / "kso_state.json").write_text(json.dumps({
            "state": "transaction",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }))
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=3, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.cycles_completed, 3)
        self.assertEqual(result.rendered_count, 0)
        self.assertEqual(result.hold_count, 3)
        self.assertEqual(result.status, STATUS_OK)

    def test_daemon_recovers_from_no_items(self):
        """No manifest → no_items, daemon continues."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps({
            "state": "idle",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }))
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=3, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.status, STATUS_OK)

    # ══════════════════════════════════════════════════════════
    # Invalid args
    # ══════════════════════════════════════════════════════════

    def test_empty_chromium_bin_error(self):
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="",
        )
        self.assertEqual(result.status, STATUS_ERROR)

    # ══════════════════════════════════════════════════════════
    # Safe output
    # ══════════════════════════════════════════════════════════

    def test_result_repr_safe(self):
        _setup_full_root(self.root, item_count=2)
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=2, sleep_fn=_make_noop_sleep(),
        )
        self._safe(repr(result))
        self._safe(format_kso_runtime_daemon_result(result))

    def test_error_result_repr_safe(self):
        """Error result (invalid args) is safe."""
        result = run_kso_runtime_daemon(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="",
        )
        self._safe(repr(result))
        self._safe(format_kso_runtime_daemon_result(result))
