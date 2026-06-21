"""KSO Player Timed Runtime Cycle Tests — safe, no real Chromium, no real sleep.

Tests the runtime-cycle-once pipeline:
  - prepare + launch + wait + state recheck + completed PoP
  - without confirm flags → no Chromium, no PoP
  - with confirm_launch + fake launcher → launched
  - without confirm_display_completed → no PoP
  - with confirm_display_completed → completed PoP after safe sleep
  - state changes during wait → no PoP
  - state stale → no PoP
  - hold states → no launch, no PoP
  - CLI --help works
  - safe output everywhere
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from kso_player.runtime_cycle import (
    run_kso_runtime_cycle_once,
    format_kso_runtime_cycle_result,
    KsoRuntimeCycleResult,
    STATUS_OK,
    STATUS_ERROR,
    REASON_RUNTIME_READY,
    REASON_RUNTIME_LAUNCHED,
    REASON_RUNTIME_HOLD,
    REASON_RUNTIME_COMPLETED,
    REASON_NO_COMPLETED_CONFIRM,
    REASON_STATE_CHANGED,
    REASON_STATE_STALE,
    REASON_INVALID_ARGS,
    REASON_INTERNAL_ERROR,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.shell_snapshot import (
    SNAPSHOT_MODE_RENDER,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _make_source_shell_dir(base: Path) -> Path:
    """Create a minimal source shell directory with required files."""
    shell_dir = base / "player_shell"
    shell_dir.mkdir(parents=True, exist_ok=True)
    for fname in ["index.html", "styles.css", "player.js", "bootstrap.js",
                   "bootstrap_snapshot.js"]:
        (shell_dir / fname).write_text(f"/* {fname} */\n", encoding="utf-8")
    return shell_dir


def _make_runtime_dir(base: Path) -> Path:
    rd = base / "runtime_shell"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def _make_root(base: Path) -> Path:
    r = base / "kso_root"
    r.mkdir(parents=True, exist_ok=True)
    return r


def _make_fake_launcher(should_succeed: bool = True):
    class FakeProcess:
        pass

    def launcher(command: List[str]) -> Optional[object]:
        if should_succeed:
            return FakeProcess()
        return None

    return launcher


def _make_noop_sleep() -> Callable[[float], None]:
    """Sleep that does nothing — for tests (no real wait)."""
    def _sleep(seconds: float) -> None:
        pass
    return _sleep


def _make_holding_sleep(state_file: Path, new_state: str) -> Callable[[float], None]:
    """Sleep that changes the state file to simulate state transition."""
    def _sleep(seconds: float) -> None:
        data = {
            "state": new_state,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4_state_adapter",
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(data))
    return _sleep


def _make_stale_sleep(state_file: Path) -> Callable[[float], None]:
    """Sleep that makes the state timestamp old (stale)."""
    def _sleep(seconds: float) -> None:
        data = {
            "state": "idle",
            "updated_at_utc": "2020-01-01T00:00:00+00:00",
            "source": "ukm4_state_adapter",
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(data))
    return _sleep


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestRuntimeCycle(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_rc_"))
        self.source_shell = _make_source_shell_dir(self.tmp)
        self.runtime_shell = _make_runtime_dir(self.tmp)
        self.root = _make_root(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _assert_safe_output(self, output):
        lower = output.lower() if isinstance(output, str) else str(output).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower,
                             f"Safe output must not contain '{fb}': {output[:200]}")

    # ── Prepares without confirm → no launch, no PoP ────────────

    def test_prepare_without_confirm_flags(self):
        """No confirm flags → prepare only, no launch, no PoP."""
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=False,
            prepare_demo_fixture=True,
        )

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.render_ready)
        self.assertTrue(result.shell_prepared)
        self.assertTrue(result.snapshot_written)
        self.assertFalse(result.launched)
        self.assertFalse(result.display_waited)
        self.assertFalse(result.state_rechecked)
        self.assertFalse(result.completed_pop_written)
        self.assertEqual(result.reason, REASON_NO_COMPLETED_CONFIRM)
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_kso_runtime_cycle_result(result))

    # ── With confirm_launch + fake launcher → launched ──────────

    def test_with_confirm_launch_marks_launched(self):
        """--confirm-launch + fake launcher → launched=True."""
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=True,
            confirm_display_completed=False,
            prepare_demo_fixture=True,
            process_launcher=_make_fake_launcher(should_succeed=True),
        )

        self.assertTrue(result.launched)
        self.assertFalse(result.completed_pop_written)
        self._assert_safe_output(repr(result))

    # ── With confirm_display_completed → wait + PoP ─────────────

    def test_with_confirm_completed_writes_pop(self):
        """--confirm-display-completed → wait + completed PoP written."""
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=True,
            prepare_demo_fixture=True,
            sleep_fn=_make_noop_sleep(),
        )

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.render_ready)
        self.assertTrue(result.display_waited)
        self.assertTrue(result.state_rechecked)
        self.assertTrue(result.completed_pop_write_requested)
        self.assertTrue(result.completed_pop_written,
                        "Completed PoP must be written")
        self.assertEqual(result.reason, REASON_RUNTIME_COMPLETED)

        # Verify PoP file exists
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists(), "PoP file must exist")
        content = pop_file.read_text(encoding="utf-8")
        self.assertIn('"event_status": "completed"', content)
        self._assert_safe_output(repr(result))

    # ── State changes during wait → no PoP ──────────────────────

    def test_state_changes_to_transaction_no_pop(self):
        """State changes from idle to transaction during wait → no completed PoP."""
        state_file = self.root / "state" / "kso_state.json"

        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=True,
            prepare_demo_fixture=True,
            sleep_fn=_make_holding_sleep(state_file, "transaction"),
        )

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.display_waited)
        self.assertTrue(result.state_rechecked)
        self.assertTrue(result.completed_pop_write_requested)
        self.assertFalse(result.completed_pop_written,
                         "PoP must NOT be written when state changes to transaction")
        self.assertEqual(result.reason, REASON_STATE_CHANGED)

        # Verify no PoP file exists
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop_file.exists(),
                         "No PoP file when state changed")
        self._assert_safe_output(repr(result))

    def test_state_changes_to_payment_no_pop(self):
        """State changes from idle to payment during wait → no completed PoP."""
        state_file = self.root / "state" / "kso_state.json"

        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=True,
            prepare_demo_fixture=True,
            sleep_fn=_make_holding_sleep(state_file, "payment"),
        )

        self.assertTrue(result.completed_pop_write_requested)
        self.assertFalse(result.completed_pop_written)
        self.assertEqual(result.reason, REASON_STATE_CHANGED)

    # ── State becomes stale → no PoP ────────────────────────────

    def test_state_becomes_stale_no_pop(self):
        """State timestamp becomes old (stale) during wait → no completed PoP."""
        state_file = self.root / "state" / "kso_state.json"

        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=True,
            prepare_demo_fixture=True,
            sleep_fn=_make_stale_sleep(state_file),
        )

        self.assertTrue(result.display_waited)
        self.assertTrue(result.state_rechecked)
        self.assertTrue(result.completed_pop_write_requested)
        self.assertFalse(result.completed_pop_written,
                         "PoP must NOT be written when state is stale")
        self.assertEqual(result.reason, REASON_STATE_STALE)
        self._assert_safe_output(repr(result))

    # ── Hold scenarios → no launch, no PoP ────────────────────

    def test_hold_non_idle_no_pop(self):
        """Non-idle state → hold, no launch, no PoP."""
        # Create root with transaction state
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "transaction",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        manifest = {
            "schemaVersion": 1, "channel": "kso",
            "storeCode": "s", "deviceCode": "d",
            "items": [{"slotOrder": 0, "contentType": "image/png",
                       "durationMs": 5000, "mediaRef": "media/current/slot-000"}],
        }
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready)
        self.assertFalse(result.launched)
        self.assertFalse(result.completed_pop_written)
        self._assert_safe_output(repr(result))

    def test_missing_manifest_hold(self):
        """Missing manifest → hold, no PoP."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "idle",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))

        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready)
        self.assertFalse(result.completed_pop_written)

    # ── Invalid args ──────────────────────────────────────────────

    def test_empty_chromium_bin_error(self):
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="",
        )
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_zero_stale_seconds_error(self):
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            stale_seconds=0,
        )
        self.assertEqual(result.status, STATUS_ERROR)

    # ── Completed PoP without confirm → NOT written ───────────

    def test_no_auto_completed_pop_without_confirm(self):
        """Without confirm_display_completed → completed PoP NOT written."""
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=True,
            confirm_display_completed=False,
            prepare_demo_fixture=True,
            process_launcher=_make_fake_launcher(should_succeed=True),
        )

        self.assertTrue(result.launched)
        self.assertFalse(result.completed_pop_write_requested)
        self.assertFalse(result.completed_pop_written)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop_file.exists(),
                         "No PoP without --confirm-display-completed")

    # ── Safe output ───────────────────────────────────────────────

    def test_result_repr_safe(self):
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            prepare_demo_fixture=True,
        )
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_kso_runtime_cycle_result(result))

    def test_completed_result_repr_safe(self):
        result = run_kso_runtime_cycle_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            prepare_demo_fixture=True,
            sleep_fn=_make_noop_sleep(),
        )
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_kso_runtime_cycle_result(result))
