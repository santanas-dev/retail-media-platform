"""Tests for kso_sidecar_agent.cli pop-payload-preview — safe aggregated payload preview CLI."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

POP_PENDING_DIR = "pop/pending"
POP_JSONL_FILE = "player_events.jsonl"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "customer_id", "phone", "email", "receipt_number", "fiscal_data",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "stacktrace",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_sidecar_agent.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _make_record(event_status="draft", event_type="would_play",
                 safety_state="idle", selected_order=0):
    return {
        "schema_version": 1,
        "event_type": event_type,
        "event_status": event_status,
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": "2026-06-19T00:00:00+00:00",
        "ended_at": "2026-06-19T00:00:05+00:00",
        "duration_ms": 5000 if event_type == "would_play" else 0,
        "playback_allowed": True if event_type == "would_play" else False,
        "session_action": "play" if event_type == "would_play" else "stop",
        "session_reason": "ready" if event_type == "would_play" else "safety_blocked",
        "selected_order": selected_order,
        "selected_content_type": "image/png",
        "safety_state": safety_state,
        "result": event_type,
    }


def _make_manifest_items(count=3):
    items = []
    for i in range(count):
        items.append({
            "manifest_item_id": str(uuid.uuid4()),
            "filename": f"file_{i}.png",
            "content_type": "image/png",
            "sha256": "a" * 64,
            "duration_ms": 5000,
            "order": i,
            "size_bytes": 100,
        })
    return items


def _make_manifest_data(items=None):
    return {
        "manifest_version_id": str(uuid.uuid4()),
        "manifest_hash": "a" * 64,
        "source": "current",
        "generated_at": "2026-06-19T00:00:00Z",
        "items": items or _make_manifest_items(3),
    }


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


def _write_manifest(root, manifest_data):
    mdir = root / "manifest"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "current_manifest.json").write_text(json.dumps(manifest_data))


def _write_media_files(root, manifest_items):
    mdir = root / "media" / "current"
    mdir.mkdir(parents=True, exist_ok=True)
    for item in manifest_items:
        data = b"\x00" * 100
        sha = hashlib.sha256(data).hexdigest()
        item["sha256"] = sha
        (mdir / item["filename"]).write_bytes(data)


# ══════════════════════════════════════════════════════════════════════


class TestPopPayloadPreviewHelp(unittest.TestCase):
    def test_help_lists_command(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("pop-payload-preview", out)

    def test_pop_payload_preview_help(self):
        out, err, rc = _run_cli("pop-payload-preview", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)
        self.assertIn("--max-events", out)


class TestPopPayloadPreviewEmpty(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_missing_file_exit_0(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("payload_events:      0", out)


class TestPopPayloadPreviewDraft(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("draft")])

    def test_draft_exit_0_no_payload(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("payload_events:      0", out)
        self.assertIn("draft_events:        1", out)


class TestPopPayloadPreviewBlocked(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [_make_record("blocked", event_type="blocked")])

    def test_blocked_no_payload(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("payload_events:      0", out)


class TestPopPayloadPreviewInvalid(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_invalid_json_exit_1(self):
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        (pending_dir / POP_JSONL_FILE).write_text("not json\n")
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("invalid_events:      1", out)

    def test_forbidden_key_exit_1(self):
        rec = _make_record("draft")
        rec["token"] = "abc"
        _write_jsonl(self.root, [rec])
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("invalid_events:      1", out)


class TestPopPayloadPreviewMaxEvents(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_max_0_exit_2(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root), "--max-events", "0")
        self.assertEqual(rc, 2)

    def test_max_2_shown(self):
        _write_jsonl(self.root, [_make_record("draft")])
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root), "--max-events", "2")
        self.assertIn("max_events:          2", out)

    def test_default_max_events(self):
        _write_jsonl(self.root, [_make_record("draft")])
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertIn("max_events:          100", out)


class TestPopPayloadPreviewArgs(unittest.TestCase):
    def test_missing_root_exit_2(self):
        out, err, rc = _run_cli("pop-payload-preview")
        self.assertEqual(rc, 2)


class TestPopPayloadPreviewSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        items = _make_manifest_items(3)
        _write_media_files(self.root, items)
        _write_manifest(self.root, _make_manifest_data(items))
        _write_jsonl(self.root, [
            _make_record("completed", selected_order=0),
        ])

    def test_no_raw_json(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn('"event_type"', out)

    def test_no_payload_body(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("device_event_id", (out + err).lower())

    def test_no_batch_id(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("batch_id", (out + err).lower())

    def test_no_manifest_item_id(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("manifest_item_id", (out + err).lower())

    def test_no_campaign_id(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("campaign_id", (out + err).lower())

    def test_no_filename(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("filename", (out + err).lower())
        self.assertNotIn("file_0", out + err)

    def test_no_sha256(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("sha256", (out + err).lower())

    def test_no_absolute_paths(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn(str(self.root), out + err)

    def test_no_forbidden(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        combined = (out + err).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, combined,
                f"stdout/err contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertNotIn("Traceback", out + err)


class TestPopPayloadPreviewNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "sent").exists())

    def test_does_not_create_quarantine_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "quarantine").exists())

    def test_does_not_create_dry_run_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "dry_run").exists())

    def test_does_not_delete_pending(self):
        _write_jsonl(self.root, [_make_record("draft")])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertTrue(jsonl_path.exists())

    def test_no_http(self):
        _write_jsonl(self.root, [_make_record("draft")])
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 0)

    def test_no_secret_config_token(self):
        _write_jsonl(self.root, [_make_record("draft")])
        out, err, rc = _run_cli("pop-payload-preview", "--root", str(self.root))
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
