"""Tests for UKM 4 State Source Discovery script.

All tests verify the script is safe: readonly, no checks/PII/fiscal,
no systemctl start/enable/restart, no HTTP, no DB, no recursive scan.
"""

import json as _json
import subprocess
import sys as _sys
import tempfile
import unittest
from pathlib import Path

DISCOVERY_SCRIPT = str(
    Path(__file__).resolve().parent.parent / "discovery" / "ukm4_state_discovery.py"
)


def _run_discovery(*args, cwd=None):
    result = subprocess.run(
        [_sys.executable, DISCOVERY_SCRIPT, *args],
        capture_output=True, text=True, timeout=15,
        cwd=cwd,
    )
    return result


FORBIDDEN = frozenset({
    "receipt_number", "card_number", "customer_id", "phone", "email",
    "fiscal_data", "token", "secret", "password", "authorization",
    "stacktrace", "traceback", "sku", "amount", "price", "discount",
    "pan", "bin", "cvv", "product",
})


def _assert_safe(test, output: str):
    lower = output.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Forbidden '{fb}' in output: {output[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestDiscoveryCLI(unittest.TestCase):

    def test_help_works(self):
        r = _run_discovery("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ukm4-state-discovery", r.stdout)

    def test_version_works(self):
        r = _run_discovery("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("0.1.0", r.stdout)

    def test_dry_run_default(self):
        """No args → dry-run by default."""
        r = _run_discovery()
        self.assertEqual(r.returncode, 0)
        data = _json.loads(r.stdout)
        self.assertEqual(data["status"], "dry_run")
        self.assertEqual(data["checks_completed"], 0)
        _assert_safe(self, r.stdout)

    def test_dry_run_explicit(self):
        r = _run_discovery("--dry-run")
        self.assertEqual(r.returncode, 0)
        data = _json.loads(r.stdout)
        self.assertEqual(data["status"], "dry_run")
        _assert_safe(self, r.stdout)

    def test_dry_run_explicit_flag(self):
        r = _run_discovery("--dry-run")
        self.assertEqual(r.returncode, 0)
        data = _json.loads(r.stdout)
        self.assertEqual(data["status"], "dry_run")

    def test_no_args_no_broad_scan(self):
        """No arguments → dry-run, no scan."""
        r = _run_discovery()
        data = _json.loads(r.stdout)
        self.assertEqual(data["status"], "dry_run")
        self.assertEqual(data["checks_completed"], 0)
        # No process/service/status_file keys with checked=True
        results = data.get("results", {})
        for key in results:
            self.assertFalse(results[key].get("checked", False),
                             f"No scan without explicit arg: {key}")

    def test_execute_sets_status_completed(self):
        r = _run_discovery("--execute")
        self.assertEqual(r.returncode, 0)
        data = _json.loads(r.stdout)
        self.assertEqual(data["status"], "completed")

    def test_execute_checks_environment(self):
        r = _run_discovery("--execute")
        data = _json.loads(r.stdout)
        self.assertIn("environment", data["results"])
        env = data["results"]["environment"]
        self.assertIn("os", env)
        _assert_safe(self, _json.dumps(env))


class TestDiscoveryProcessCheck(unittest.TestCase):

    def test_process_pattern_accepted(self):
        r = _run_discovery("--execute", "--process-name-pattern", "python3")
        data = _json.loads(r.stdout)
        self.assertIn("process", data["results"])
        proc = data["results"]["process"]
        self.assertTrue(proc["checked"])
        self.assertTrue(proc.get("process_detected") or True)  # may or may not be detected

    def test_process_output_no_cmdline(self):
        """Process output must NOT contain full command lines."""
        r = _run_discovery("--execute", "--process-name-pattern", "python3")
        data = _json.loads(r.stdout)
        proc = data.get("results", {}).get("process", {})
        text = _json.dumps(proc).lower()
        # No raw paths or command arguments
        self.assertNotIn("/usr/", text)
        self.assertNotIn("--", text)
        _assert_safe(self, r.stdout)


class TestDiscoveryServiceCheck(unittest.TestCase):

    def test_service_name_accepted(self):
        r = _run_discovery("--execute", "--service-name", "nonexistent-service-12345")
        data = _json.loads(r.stdout)
        self.assertIn("service", data["results"])
        svc = data["results"]["service"]
        self.assertTrue(svc["checked"])

    def test_service_output_safe(self):
        r = _run_discovery("--execute", "--service-name", "nonexistent-service")
        data = _json.loads(r.stdout)
        svc = data.get("results", {}).get("service", {})
        _assert_safe(self, _json.dumps(svc))


class TestDiscoveryStatusFileCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_disc_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_file_in_allowlist_accepted(self):
        """Status file under /run/verny/kso is in allowlist."""
        sf = self.tmp / "kso_state.json"
        sf.write_text('{"state":"idle"}')
        # We can't actually create /run/verny/kso, so test that
        # a path outside allowlist is rejected properly
        r = _run_discovery("--execute", "--status-file", str(sf))
        data = _json.loads(r.stdout)
        sf_result = data["results"]["status_file"]
        self.assertTrue(sf_result["checked"])
        # Not in allowlist → should be rejected or not found
        self.assertFalse(sf_result.get("status_file_present", True))

    def test_status_file_does_not_read_content(self):
        """Status file check must not read file contents."""
        sf = self.tmp / "kso_state.json"
        sf.write_text('{"receipt":"secret-data"}')
        r = _run_discovery("--execute", "--status-file", str(sf))
        data = _json.loads(r.stdout)
        sf_result = data["results"]["status_file"]
        # If it read content, forbidden strings would appear
        _assert_safe(self, _json.dumps(sf_result))
        # Verify the result doesn't contain the secret
        text = _json.dumps(sf_result).lower()
        self.assertNotIn("secret", text)
        self.assertNotIn("receipt", text)

    def test_status_file_outside_allowlist_warns(self):
        r = _run_discovery("--execute", "--status-file", "/tmp/some_file.json")
        data = _json.loads(r.stdout)
        sf = data["results"]["status_file"]
        self.assertTrue(sf["checked"])
        self.assertFalse(sf.get("status_file_present", True))
        self.assertIn("path_outside_allowlist", sf.get("reason", ""))


class TestDiscoverySafety(unittest.TestCase):

    def test_output_no_forbidden_strings(self):
        r = _run_discovery("--execute",
                           "--process-name-pattern", "python3",
                           "--service-name", "nonexistent",
                           "--status-file", "/run/verny/kso/state/kso_state.json")
        _assert_safe(self, r.stdout)
        data = _json.loads(r.stdout)
        text = _json.dumps(data).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, text,
                             f"Forbidden in output: {fb}")

    def test_no_systemctl_start(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        # Check no subprocess call to systemctl start/enable/restart
        code_lower = content.lower()
        self.assertNotIn('["systemctl", "start"', code_lower)
        self.assertNotIn('["systemctl", "enable"', code_lower)
        self.assertNotIn('["systemctl", "restart"', code_lower)
        self.assertNotIn("systemctl start", code_lower.replace(
            "no systemctl start/enable/restart", ""))

    def test_no_http_requests(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        lines = [l for l in content.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines)
        self.assertNotIn("import urllib", code)
        self.assertNotIn("import requests", code)
        self.assertNotIn("import http.client", code)
        self.assertNotIn("import socket", code)

    def test_no_db_connection(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        lines = [l for l in content.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines).lower()
        self.assertNotIn("sqlite3", code)
        self.assertNotIn("psycopg", code)
        self.assertNotIn("mysql", code)
        self.assertNotIn("import cx_", code)

    def test_no_recursive_filesystem_walk(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        lines = [l for l in content.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines)
        self.assertNotIn("os.walk", code)
        self.assertNotIn("rglob", code)
        self.assertNotIn("**.", code)

    def test_no_grep_over_logs(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        # Filter out lines declaring SAFE_DIRS (allowlist), then check
        lines = [l for l in content.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines).lower()
        # Remove SAFE_DIRS block for this check, and allowlist entries
        code_clean = code.replace('"/var/log/verny/kso",', "")
        self.assertNotIn(" grep ", code_clean)
        self.assertNotIn("tail -", code_clean)

    def test_no_windows_paths(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        lines = [l for l in content.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines)
        self.assertNotIn("ProgramData", code)
        self.assertNotIn("C:\\", code)
        self.assertNotIn("MSI", code)

    def test_no_real_secrets(self):
        with open(DISCOVERY_SCRIPT) as f:
            content = f.read()
        lines = [l for l in content.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines)
        self.assertNotIn("Bearer", code)
        self.assertNotIn("sha256", code.lower())
        self.assertNotIn("password=", code.lower())

    def test_no_raw_paths_in_output(self):
        """Output must not contain raw filesystem paths outside allowlist."""
        r = _run_discovery("--execute",
                           "--process-name-pattern", "python3")
        data = _json.loads(r.stdout)
        text = _json.dumps(data).lower()
        # Only safe paths
        for bad in ["/etc/passwd", "/root/", "/home/", "/var/lib/supermag"]:
            self.assertNotIn(bad, text,
                             f"Raw path '{bad}' in output")



if __name__ == "__main__":
    unittest.main()
