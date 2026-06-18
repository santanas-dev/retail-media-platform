"""E2E smoke tests for KSO Simulator.

Run: cd tools/kso_simulator && python3 -m unittest discover -s tests
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# Test data
# ══════════════════════════════════════════════════════════════════════

EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ITEM_1 = "66111111-a111-1111-a111-111111111111"
ITEM_2 = "66222222-a222-2222-a222-222222222222"

TWO_ITEM_MANIFEST = {
    "manifest_version_id": "550e8400-e29b-41d4-a716-446655440000",
    "manifest_hash": EMPTY_SHA,
    "generated_at": "2026-06-18T10:00:00Z",
    "valid_until": "2026-12-31T23:59:59Z",
    "items": [
        {
            "manifest_item_id": ITEM_1,
            "filename": "item_01.jpg",
            "content_type": "image/jpeg",
            "sha256": EMPTY_SHA,
            "size_bytes": 0,
            "duration_ms": 10000,
            "order": 1,
        },
        {
            "manifest_item_id": ITEM_2,
            "filename": "item_02.jpg",
            "content_type": "image/jpeg",
            "sha256": EMPTY_SHA,
            "size_bytes": 0,
            "duration_ms": 5000,
            "order": 2,
        },
    ],
}

FORBIDDEN_WORDS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "local_path", "file_path", "receipt", "payment_card",
]


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def run(*args):
    """Run kso_simulator.cli as a subprocess. Returns (returncode, stdout, stderr)."""
    r = subprocess.run(
        [sys.executable, "-m", "kso_simulator.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return r.returncode, r.stdout, r.stderr


def write_manifest(root, manifest):
    path = Path(root) / "manifest" / "current_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest))


def create_media(root, filename, content=b""):
    path = Path(root) / "media" / "current" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def read_json(path):
    return json.loads(Path(path).read_text())


def count_log_lines(root):
    log = Path(root) / "pop" / "events.log"
    if not log.exists():
        return 0
    return len([l for l in log.read_text().split("\n") if l.strip()])


def read_log(root):
    log = Path(root) / "pop" / "events.log"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().split("\n") if l.strip()]


def has_forbidden(text):
    lower = text.lower()
    return [w for w in FORBIDDEN_WORDS if w in lower]


# ══════════════════════════════════════════════════════════════════════
# Test Cases
# ══════════════════════════════════════════════════════════════════════

class TestInitStatus(unittest.TestCase):
    """A. init creates folders + status file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_creates_status(self):
        code, out, err = run("init", "--root", self.root)
        self.assertEqual(code, 0, f"stderr={err}")

        # Check kso_status.json
        status_path = Path(self.root) / "status" / "kso_status.json"
        self.assertTrue(status_path.exists(), "kso_status.json not created")
        data = read_json(status_path)
        self.assertEqual(data["state"], "unknown")
        self.assertFalse(data["can_show_ads"])

    def test_init_creates_folders(self):
        code, out, err = run("init", "--root", self.root)
        self.assertEqual(code, 0)

        expected = [
            "config", "manifest",
            "media/current", "media/staging", "media/quarantine",
            "pop", "status", "logs",
        ]
        for folder in expected:
            path = Path(self.root) / folder
            self.assertTrue(path.is_dir(), f"Missing folder: {folder}")

    def test_status_after_init(self):
        run("init", "--root", self.root)
        code, out, err = run("status", "--root", self.root)
        self.assertEqual(code, 0)
        self.assertIn("unknown", out)
        self.assertIn("can_show_ads", out)


class TestSetState(unittest.TestCase):
    """B. set-state transitions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init", "--root", self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_idle(self):
        code, out, err = run("set-state", "idle", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        data = read_json(Path(self.root) / "status" / "kso_status.json")
        self.assertEqual(data["state"], "idle")
        self.assertTrue(data["can_show_ads"])

    def test_set_payment(self):
        code, out, err = run("set-state", "payment", "--root", self.root)
        self.assertEqual(code, 0)
        data = read_json(Path(self.root) / "status" / "kso_status.json")
        self.assertEqual(data["state"], "payment")
        self.assertFalse(data["can_show_ads"])

    def test_set_invalid_state(self):
        code, out, err = run("set-state", "INVALID", "--root", self.root)
        self.assertNotEqual(code, 0, "Should fail on invalid state")


class TestManifestMedia(unittest.TestCase):
    """C. manifest + media creation and verification."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init", "--root", self.root)
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        create_media(self.root, "item_01.jpg")
        create_media(self.root, "item_02.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def test_manifest_status_ok(self):
        code, out, err = run("manifest-status", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("PRESENT", out)
        self.assertIn("items_count:", out)
        self.assertRegex(out, r"items_count:\s+2")

    def test_list_items(self):
        code, out, err = run("list-items", "--root", self.root)
        self.assertEqual(code, 0)
        self.assertIn("item_01.jpg", out)
        self.assertIn("item_02.jpg", out)

    def test_verify_media_success(self):
        code, out, err = run("verify-media", "--root", self.root)
        self.assertEqual(code, 0, f"out={out}\nerr={err}")
        self.assertIn("hash_ok:         2", out)
        self.assertIn("missing:         0", out)


class TestShowOnce(unittest.TestCase):
    """D. show-once scenarios."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init", "--root", self.root)
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        create_media(self.root, "item_01.jpg")
        create_media(self.root, "item_02.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def test_show_completed_idle(self):
        run("set-state", "idle", "--root", self.root)
        code, out, err = run("show-once", "--root", self.root,
                             "--manifest-item-id", ITEM_1)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("SHOW_COMPLETED", out)
        self.assertEqual(count_log_lines(self.root), 1)
        events = read_log(self.root)
        self.assertEqual(events[0]["result"], "completed")

    def test_show_blocked_payment(self):
        run("set-state", "payment", "--root", self.root)
        code, out, err = run("show-once", "--root", self.root,
                             "--manifest-item-id", ITEM_1)
        self.assertNotEqual(code, 0)
        self.assertIn("SHOW_BLOCKED", out)
        self.assertIn("kso_not_idle", out)
        # No completed PoP written
        events = read_log(self.root)
        completed = [e for e in events if e.get("result") == "completed"]
        self.assertEqual(len(completed), 0)


class TestIdleLoop(unittest.TestCase):
    """E. run-idle-loop scenarios."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init", "--root", self.root)
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        create_media(self.root, "item_01.jpg")
        create_media(self.root, "item_02.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def test_loop_idle(self):
        run("set-state", "idle", "--root", self.root)
        code, out, err = run("run-idle-loop", "--root", self.root,
                             "--iterations", "2", "--interval-ms", "0")
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("LOOP_DONE", out)
        self.assertIn("completed=2", out)
        self.assertIn("blocked=0", out)
        self.assertIn("failed=0", out)

        events = read_log(self.root)
        completed = [e for e in events if e.get("result") == "completed"]
        self.assertEqual(len(completed), 2)

    def test_loop_transaction(self):
        run("set-state", "transaction", "--root", self.root)
        code, out, err = run("run-idle-loop", "--root", self.root,
                             "--iterations", "2", "--interval-ms", "0")
        self.assertNotEqual(code, 0)
        self.assertIn("blocked=2", out)
        self.assertIn("completed=0", out)

        events = read_log(self.root)
        completed = [e for e in events if e.get("result") == "completed"]
        self.assertEqual(len(completed), 0)


class TestNegativeSecurity(unittest.TestCase):
    """F. Negative/security scenarios."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init", "--root", self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_path_traversal_filename_rejected(self):
        bad_manifest = {
            "manifest_version_id": "550e8400-e29b-41d4-a716-446655440000",
            "manifest_hash": EMPTY_SHA,
            "generated_at": "2026-06-18T10:00:00Z",
            "valid_until": "2026-12-31T23:59:59Z",
            "items": [{
                "manifest_item_id": ITEM_1,
                "filename": "../../etc/passwd",
                "content_type": "text/plain",
                "sha256": EMPTY_SHA,
                "size_bytes": 0,
                "duration_ms": 10000,
                "order": 1,
            }],
        }
        write_manifest(self.root, bad_manifest)
        code, out, err = run("manifest-status", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("path traversal", (out + err).lower())

    def test_forbidden_reason_in_pop_rejected(self):
        run("set-state", "idle", "--root", self.root)
        code, out, err = run(
            "write-pop", "--root", self.root,
            "--manifest-item-id", ITEM_1,
            "--result", "interrupted",
            "--duration-ms", "1000",
            "--reason", "token expired",
        )
        self.assertNotEqual(code, 0, "Should reject forbidden reason")

    def test_output_no_full_path(self):
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        create_media(self.root, "item_01.jpg")
        run("set-state", "idle", "--root", self.root)
        code, out, err = run("verify-media", "--root", self.root)
        # The temp directory path pattern will be unique per test
        self.assertNotIn("/tmp/", out, "Should not contain /tmp/ paths")

    def test_events_log_no_forbidden_words(self):
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        create_media(self.root, "item_01.jpg")
        run("set-state", "idle", "--root", self.root)
        run("show-once", "--root", self.root, "--manifest-item-id", ITEM_1)

        events = read_log(self.root)
        for ev in events:
            ev_text = json.dumps(ev).lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, ev_text,
                                 f"Forbidden word '{word}' in event: {ev}")

    def test_cli_output_no_forbidden_words(self):
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        create_media(self.root, "item_01.jpg")
        run("set-state", "idle", "--root", self.root)
        code, out, err = run("show-once", "--root", self.root,
                             "--manifest-item-id", ITEM_1)
        combined = (out + err).lower()
        bad = [w for w in FORBIDDEN_WORDS if w in combined]
        self.assertEqual(len(bad), 0,
                         f"Forbidden words in output: {bad}")

    def test_manifest_status_no_forbidden_words(self):
        write_manifest(self.root, TWO_ITEM_MANIFEST)
        code, out, err = run("manifest-status", "--root", self.root)
        combined = (out + err).lower()
        bad = [w for w in FORBIDDEN_WORDS if w in combined]
        self.assertEqual(len(bad), 0,
                         f"Forbidden words in manifest-status: {bad}")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
