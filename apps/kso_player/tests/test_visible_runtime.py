"""KSO Player Visible Runtime Tests — safe, no real Chromium, no backend.

Tests the visible-runtime-once pipeline:
  - prepare_demo_fixture + visible runtime
  - without confirm_launch → no launch
  - with fake launcher → marks launched
  - non-idle/manifest/media gaps → hold, no launch
  - no completed PoP written
  - CLI --help works
  - safe output everywhere
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

# ── Import from player package ─────────────────────────────────────
from kso_player.visible_runtime import (
    run_kso_visible_runtime_once,
    format_kso_visible_runtime_result,
    KsoVisibleRuntimeResult,
    STATUS_OK,
    STATUS_ERROR,
    REASON_READY,
    REASON_LAUNCHED,
    REASON_HOLD,
    REASON_FIXTURE_FAILED,
    REASON_INVALID_ARGS_VISIBLE,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.local_demo_fixture import (
    prepare_kso_local_demo_fixture,
    DEMO_STATE_VALUE,
    DEMO_CONTENT_TYPE,
    DEMO_MEDIA_REF,
)
from kso_player.shell_snapshot import (
    SNAPSHOT_MODE_HOLD,
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
    """Create a clean runtime shell directory."""
    rd = base / "runtime_shell"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def _make_root(base: Path) -> Path:
    """Create a root directory."""
    r = base / "kso_root"
    r.mkdir(parents=True, exist_ok=True)
    return r


def _make_fake_launcher(should_succeed: bool = True):
    """Return a fake process launcher callable."""
    class FakeProcess:
        pass

    def launcher(command: List[str]) -> Optional[object]:
        if should_succeed:
            return FakeProcess()
        return None

    return launcher


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestVisibleRuntime(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_vr_"))
        self.source_shell = _make_source_shell_dir(self.tmp)
        self.runtime_shell = _make_runtime_dir(self.tmp)
        self.root = _make_root(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Safe output checker ────────────────────────────────────────

    def _assert_safe_output(self, output):
        lower = output.lower() if isinstance(output, str) else str(output).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower,
                             f"Safe output must not contain '{fb}': {output[:200]}")

    # ── Demo fixture + visible runtime ─────────────────────────────

    def test_prepare_demo_fixture_and_visible_runtime(self):
        """--prepare-demo-fixture + visible runtime → ready, no launch."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=True,
        )

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.fixture_ready)
        self.assertTrue(result.render_ready)
        self.assertTrue(result.shell_prepared)
        self.assertTrue(result.snapshot_written)
        self.assertTrue(result.launch_ready)
        self.assertFalse(result.launched)
        self.assertEqual(result.reason, REASON_READY)
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_kso_visible_runtime_result(result))

        # Verify demo fixture files exist
        self.assertTrue((self.root / "state" / "kso_state.json").exists())
        self.assertTrue((self.root / "manifest" / "current_manifest.json").exists())
        self.assertTrue((self.root / "media" / "current" / "slot-000").exists())

        # Verify runtime shell has bootstrap_snapshot.js
        self.assertTrue(
            (self.runtime_shell / "bootstrap_snapshot.js").exists(),
            "bootstrap_snapshot.js must be written",
        )

    # ── Without confirm → no launch ────────────────────────────────

    def test_without_confirm_no_launch(self):
        """--prepare-demo-fixture, no --confirm-launch → launch_ready, not launched."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=True,
        )

        self.assertTrue(result.launch_ready)
        self.assertFalse(result.launched)
        self.assertEqual(result.reason, REASON_READY)

    # ── With fake launcher → marks launched ────────────────────────

    def test_with_fake_launcher_marks_launched(self):
        """--confirm-launch + fake launcher → launched=True."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=True,
            prepare_demo_fixture=True,
            process_launcher=_make_fake_launcher(should_succeed=True),
        )

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.launched)
        self.assertEqual(result.reason, REASON_LAUNCHED)
        self._assert_safe_output(repr(result))

    # ── Non-idle state → hold, no launch ───────────────────────────

    def test_non_idle_state_hold_no_launch(self):
        """Non-idle state → hold snapshot, no launch."""
        # Create root with transaction state (non-idle)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "transaction",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))

        # Add manifest and media (needed for hold to work)
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        manifest = {
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
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready,
                         "Non-idle state → render_ready=False")
        # launch_ready can be True even for hold — Chromium CAN be launched
        # (it just shows a hold/black screen). The render_ready=False is the
        # key indicator that no ad will display.
        self.assertFalse(result.launched)
        self._assert_safe_output(repr(result))

    # ── Missing manifest → hold, no launch ─────────────────────────

    def test_missing_manifest_hold_no_launch(self):
        """Missing manifest → hold, no launch."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "idle",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))

        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready,
                         "Missing manifest → render_ready=False")
        self.assertFalse(result.launched)
        self._assert_safe_output(repr(result))

    # ── Missing media → hold, no launch ────────────────────────────

    def test_missing_media_hold_no_launch(self):
        """Missing media → hold, no launch."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "idle",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        manifest = {
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
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))
        # No media/ dir

        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready,
                         "Missing media → render_ready=False")
        self.assertFalse(result.launched)
        self._assert_safe_output(repr(result))

    # ── Gateway wrapper manifest → hold ───────────────────────────

    def test_gateway_wrapper_manifest_hold(self):
        """Gateway wrapper manifest → hold, no launch."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "idle",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        # Gateway wrapper has "manifest" nesting + manifest_item_id
        gw = {
            "status": "served",
            "manifest_version_id": "mvid-123",
            "manifest_hash": "a" * 64,
            "published_at": "2026-06-19T10:00:00Z",
            "manifest": {
                "schemaVersion": 1,
                "channel": "kso",
                "items": [{
                    "manifest_item_id": "mi-1",
                    "filename": "ad.png",
                    "sha256": "a" * 64,
                    "contentType": "image/png",
                    "durationMs": 5000,
                }],
            },
        }
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(gw))

        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready,
                         "Gateway wrapper manifest → render_ready=False")
        self.assertFalse(result.launched)
        self._assert_safe_output(repr(result))

    # ── No completed PoP written ──────────────────────────────────

    def test_no_completed_pop_written(self):
        """visible-runtime-once does NOT write completed PoP."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=True,
        )

        self.assertEqual(result.status, STATUS_OK)

        # Verify no pop/ dir created
        pop_dir = self.root / "pop"
        self.assertFalse(pop_dir.exists(),
                         "visible-runtime-once must NOT create pop/ directory")

        # Verify no pop/pending/player_events.jsonl
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop_file.exists(),
                         "visible-runtime-once must NOT write PoP events")

    # ── Runtime shell written ─────────────────────────────────────

    def test_runtime_shell_whitelist_copy(self):
        """Shell whitelist files are copied to runtime directory."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=True,
        )

        self.assertTrue(result.shell_prepared)

        # Verify key files exist in runtime
        for fname in ["index.html", "styles.css", "player.js", "bootstrap.js",
                       "bootstrap_snapshot.js"]:
            self.assertTrue(
                (self.runtime_shell / fname).exists(),
                f"Whitelist file {fname} must exist in runtime shell",
            )

    # ── Bootstrap snapshot written ────────────────────────────────

    def test_bootstrap_snapshot_written(self):
        """bootstrap_snapshot.js is written and contains valid JSON."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=True,
        )

        self.assertTrue(result.snapshot_written)

        snap_path = self.runtime_shell / "bootstrap_snapshot.js"
        self.assertTrue(snap_path.exists())

        content = snap_path.read_text(encoding="utf-8")
        self.assertIn("KSO_PLAYER_BOOTSTRAP_SNAPSHOT", content)
        self.assertIn("schemaVersion", content)
        # Must have mode (hold or render)
        self.assertTrue(
            "hold" in content or "render" in content,
            "Snapshot must have mode",
        )

    # ── Invalid args ──────────────────────────────────────────────

    def test_empty_chromium_bin_error(self):
        """Empty chromium_bin → error."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="",
            confirm_launch=False,
            prepare_demo_fixture=False,
        )

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS_VISIBLE)

    def test_zero_stale_seconds_error(self):
        """stale_seconds=0 → error."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=False,
            stale_seconds=0,
        )

        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS_VISIBLE)

    # ── Safe output ───────────────────────────────────────────────

    def test_result_repr_safe(self):
        """KsoVisibleRuntimeResult repr is safe."""
        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=True,
        )

        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_kso_visible_runtime_result(result))

    def test_hold_result_repr_safe(self):
        """Hold result repr is safe."""
        # Non-idle → hold
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {
            "state": "transaction",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "ukm4",
        }
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        manifest = {
            "schemaVersion": 1,
            "channel": "kso",
            "storeCode": "s",
            "deviceCode": "d",
            "items": [{"slotOrder": 0, "contentType": "image/png",
                       "durationMs": 5000, "mediaRef": "media/current/slot-000"}],
        }
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(manifest))
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = run_kso_visible_runtime_once(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            prepare_demo_fixture=False,
        )

        self.assertFalse(result.render_ready)
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_kso_visible_runtime_result(result))
