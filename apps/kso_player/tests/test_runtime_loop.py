"""KSO Player Runtime Loop Tests — safe, no real Chromium, no real sleep.

Tests the runtime-loop command:
  - prepare once, launch once
  - multi-cycle rotation (round-robin by slot_order)
  - without confirm → no PoP
  - with confirm → PoP per successful cycle
  - state gate → hold
  - state change → no PoP
  - max_cycles=0 → safe no-op
  - safe output everywhere
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from kso_player.runtime_loop import (
    run_kso_runtime_loop,
    format_kso_runtime_loop_result,
    KsoRuntimeLoopResult,
    STATUS_OK,
    STATUS_ERROR,
    REASON_COMPLETED,
    REASON_HOLD,
    REASON_NO_ITEMS,
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


def _make_counter_sleep():
    """Sleep that counts calls."""
    class C:
        calls = 0

        def fn(self, sec):
            C.calls += 1
    c = C()
    return c.fn, c


def _write_kso_manifest(root: Path, items=None, gateway_wrapper=False):
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    if items is None:
        items = [{
            "slotOrder": 0, "contentType": "image/png",
            "durationMs": 5000, "mediaRef": "media/current/slot-000",
        }]
    if gateway_wrapper:
        manifest = {
            "status": "served",
            "manifest_version_id": "mvid",
            "manifest_hash": "a" * 64,
            "manifest": {"schemaVersion": 1, "channel": "kso", "items": items},
        }
    else:
        manifest = {
            "schemaVersion": 1, "channel": "kso",
            "storeCode": "demo", "deviceCode": "demo",
            "items": items,
        }
    (root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))


def _write_idle_state(root: Path):
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "kso_state.json").write_text(json.dumps({
        "state": "idle",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "ukm4",
    }))


def _write_media_files(root: Path, count=1):
    (root / "media" / "current").mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (root / "media" / "current" / f"slot-{i:03d}").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)


def _setup_full_root(root: Path, item_count=1, gateway_wrapper=False):
    """Full setup: idle state + KSO manifest + media."""
    _write_idle_state(root)
    items = []
    for i in range(item_count):
        items.append({
            "slotOrder": i, "contentType": "image/png",
            "durationMs": 5000, "mediaRef": f"media/current/slot-{i:03d}",
        })
    _write_kso_manifest(root, items, gateway_wrapper=gateway_wrapper)
    _write_media_files(root, item_count)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestRuntimeLoop(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_rl_"))
        self.src = _make_source_shell_dir(self.tmp)
        self.rt = _make_runtime_dir(self.tmp)
        self.root = _make_root(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _safe(self, out):
        lo = out.lower() if isinstance(out, str) else str(out).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lo, f"'{fb}' in: {out[:200]}")

    # ── Prepare once, launch once ────────────────────────────

    def test_loop_prepares_shell_once(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_launch=False, confirm_display_completed=False,
            max_cycles=1, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.shell_prepared)
        self.assertTrue(result.launch_ready)
        self.assertFalse(result.launched)
        self.assertEqual(result.cycles_completed, 1)
        self._safe(repr(result))

    def test_launches_chromium_once_with_fake(self):
        _setup_full_root(self.root, item_count=2)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_launch=True, confirm_display_completed=False,
            max_cycles=3, sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )
        self.assertTrue(result.launched)
        self.assertEqual(result.cycles_completed, 3)
        self._safe(repr(result))

    def test_without_confirm_launch_no_launch(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_launch=False, max_cycles=1,
            sleep_fn=_make_noop_sleep(),
        )
        self.assertFalse(result.launched)

    # ── Rotation ────────────────────────────────────────────

    def test_single_item_rotates_multiple_cycles(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=5, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.cycles_completed, 5)
        self.assertEqual(result.rendered_count, 5)
        self.assertEqual(result.hold_count, 0)

    def test_multiple_items_rotate(self):
        _setup_full_root(self.root, item_count=3)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=3, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.cycles_completed, 3)
        self.assertEqual(result.rendered_count, 3)
        self.assertEqual(result.items_in_playlist, 3)

    # ── PoP behavior ────────────────────────────────────────

    def test_without_confirm_no_completed_pop(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_loop(
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
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            confirm_display_completed=True, max_cycles=2,
            sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.completed_pop_written_count, 2)
        pop = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop.exists())

    # ── Hold scenarios ─────────────────────────────────────

    def test_non_idle_state_hold(self):
        _setup_full_root(self.root, item_count=1)
        # Change state to transaction
        (self.root / "state" / "kso_state.json").write_text(json.dumps({
            "state": "transaction",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }))
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=1, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.cycles_completed, 1)
        self.assertEqual(result.rendered_count, 0)
        self.assertEqual(result.hold_count, 1)
        self._safe(repr(result))

    def test_missing_manifest_hold(self):
        _write_idle_state(self.root)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=1, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.reason, REASON_NO_ITEMS)
        self.assertEqual(result.cycles_completed, 0)

    def test_missing_media_hold(self):
        _write_idle_state(self.root)
        _write_kso_manifest(self.root, [{
            "slotOrder": 0, "contentType": "image/png",
            "durationMs": 5000, "mediaRef": "media/current/slot-000",
        }])
        # No media files
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=1, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.reason, REASON_NO_ITEMS)

    def test_gateway_wrapper_manifest_hold(self):
        _setup_full_root(self.root, item_count=1, gateway_wrapper=True)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=1, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.reason, REASON_NO_ITEMS)

    # ── max_cycles edge cases ───────────────────────────────

    def test_max_cycles_zero_noop(self):
        _setup_full_root(self.root, item_count=1)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=0, sleep_fn=_make_noop_sleep(),
        )
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.cycles_completed, 0)
        self._safe(repr(result))

    # ── Invalid args ────────────────────────────────────────

    def test_empty_chromium_bin_error(self):
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="",
        )
        self.assertEqual(result.status, STATUS_ERROR)

    def test_negative_max_cycles_error(self):
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=-1,
        )
        self.assertEqual(result.status, STATUS_ERROR)

    # ── Sleep coverage ──────────────────────────────────────

    def test_sleep_fn_called_per_cycle(self):
        _setup_full_root(self.root, item_count=1)
        sleep_fn, counter = _make_counter_sleep()
        run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=3, sleep_fn=sleep_fn,
        )
        self.assertEqual(counter.calls, 3)

    # ── Safe output ─────────────────────────────────────────

    def test_result_repr_safe(self):
        _setup_full_root(self.root, item_count=2)
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=2, sleep_fn=_make_noop_sleep(),
        )
        self._safe(repr(result))
        self._safe(format_kso_runtime_loop_result(result))

    def test_hold_result_repr_safe(self):
        _setup_full_root(self.root, item_count=1)
        (self.root / "state" / "kso_state.json").write_text(json.dumps({
            "state": "transaction",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }))
        result = run_kso_runtime_loop(
            root=self.root, source_shell_dir=str(self.src),
            runtime_shell_dir=str(self.rt), chromium_bin="chromium",
            max_cycles=1, sleep_fn=_make_noop_sleep(),
        )
        self._safe(repr(result))
        self._safe(format_kso_runtime_loop_result(result))
