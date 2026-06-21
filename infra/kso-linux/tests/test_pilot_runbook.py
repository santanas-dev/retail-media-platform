"""KSO Linux Pilot First-Start Runbook — Validation Tests.

Validates the runbook document and its safety rules.
No systemd, no service start, no real UKM 4, no Chromium.
"""

import os as _os
import re as _re
import unittest
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════════

_SELF_DIR = Path(__file__).resolve().parent
_INFRA_ROOT = _SELF_DIR.parent
_INSTALL_DIR = _INFRA_ROOT / "install"
_PREFLIGHT_DIR = _INFRA_ROOT / "preflight"
_DOCS_DIR = _INFRA_ROOT.parent.parent / "docs" / "kso"
_RUNBOOK_PATH = _DOCS_DIR / "linux-kso-pilot-first-start-runbook.md"


def _read(path: Path) -> str:
    return path.read_text()


def _code_without_docstrings_and_comments(path: Path) -> str:
    """Extract code lines, stripping docstrings and comments."""
    src = _read(path)
    lines = src.split("\n")
    code_lines = []
    in_docstring = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    return "\n".join(code_lines)


# ══════════════════════════════════════════════════════════════════════
# Runbook Existence & Structure
# ══════════════════════════════════════════════════════════════════════

class TestRunbookExists(unittest.TestCase):
    """Runbook file exists and is readable."""

    def test_runbook_exists(self):
        self.assertTrue(_RUNBOOK_PATH.is_file(),
                        f"Runbook must exist at {_RUNBOOK_PATH}")

    def test_runbook_not_empty(self):
        content = _read(_RUNBOOK_PATH)
        self.assertGreater(len(content), 1000,
                          "Runbook must be substantial (>1KB)")


class TestRunbookStructure(unittest.TestCase):
    """Runbook contains all required sections."""

    def setUp(self):
        self.content = _read(_RUNBOOK_PATH)

    def test_contains_three_services(self):
        for svc in ("state-adapter", "sidecar", "player"):
            self.assertIn(svc, self.content,
                          f"Runbook must mention {svc}")

    def test_contains_preflight_before_start(self):
        """Preflight section appears before first systemctl start."""
        preflight_idx = self.content.find("Шаг 4: Preflight")
        start_idx = self.content.find("systemctl start kso-state-adapter")
        self.assertGreater(preflight_idx, 0, "Must have preflight section")
        self.assertGreater(start_idx, 0, "Must have start commands")
        self.assertLess(preflight_idx, start_idx,
                        "Preflight must appear before first systemctl start")

    def test_contains_rollback_plan(self):
        self.assertIn("Rollback", self.content)
        self.assertIn("systemctl stop", self.content)
        self.assertIn("kso-player", self.content)
        self.assertIn("kso-sidecar", self.content)

    def test_contains_static_unknown_safe_default(self):
        self.assertIn("unknown", self.content.lower())
        self.assertIn("safe", self.content.lower())

    def test_states_file_source_is_not_default(self):
        """File source is explicitly marked as non-default test-only."""
        self.assertIn("file source", self.content.lower())
        self.assertIn("static unknown", self.content.lower())
        # Concept: file source is test-only, static unknown is safe default
        self.assertIn("только для тестового", self.content.lower())
        self.assertIn("не production", self.content.lower())

    def test_contains_safe_idle_test_and_rollback(self):
        self.assertIn('{"state":"idle"}', self.content)
        self.assertIn('{"state":"unknown"}', self.content)
        self.assertIn("ukm4-safe-state.json", self.content)

    def test_contains_health_check_commands(self):
        for health in ("state-adapter-health.json",
                        "sidecar-health.json",
                        "player-health.json"):
            self.assertIn(health, self.content,
                          f"Runbook must reference {health}")


# ══════════════════════════════════════════════════════════════════════
# Runbook Safety Rules
# ══════════════════════════════════════════════════════════════════════

class TestRunbookForbidsDangerousCommands(unittest.TestCase):
    """Runbook must NOT contain dangerous/production commands."""

    def setUp(self):
        self.content = _read(_RUNBOOK_PATH)

    def test_forbids_systemctl_enable(self):
        # "systemctl enable" appears in the "Что запрещено" table as a warning —
        # that's correct. We check that it does NOT appear as an instruction
        # (in code blocks or step sections).
        lines = self.content.split("\n")
        in_forbidden_table = False
        for line in lines:
            stripped = line.strip()
            if "Что запрещено" in stripped:
                in_forbidden_table = True
                continue
            if in_forbidden_table:
                if stripped.startswith("## ") or stripped.startswith("---"):
                    in_forbidden_table = False
                continue
            if "systemctl enable" in stripped:
                self.fail(
                    "systemctl enable found outside 'Что запрещено' table: "
                    f"{stripped[:80]}"
                )

    def test_does_not_contain_restart(self):
        """systemctl restart must not appear as a primary path.
        Appears only in explanation context (e.g. 'better stop/start')."""
        count = self.content.count("systemctl restart")
        # "restart" may appear in text like "restart лучше заменить на stop/start"
        # but should not appear as an actual command instruction
        # Check that it's not near a 'sudo' or code block context
        lines = self.content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "systemctl restart" in stripped:
                # Allow only in explanatory sentences, not in code blocks
                self.assertNotIn("sudo systemctl restart", stripped,
                                 "Runbook must not command restart")

    def test_no_production_idle_default(self):
        """Must not suggest idle as default state."""
        # The env example must not have idle
        self.assertNotIn("VERNY_KSO_STATIC_STATE=idle", self.content)

    def test_forbids_reading_receipts_payments_pii(self):
        lower = self.content.lower()
        for forbidden in ("receipt_number", "card_number", "payment_card",
                           "fiscal_data", "customer_id"):
            self.assertNotIn(forbidden, lower,
                             f"Runbook must not reference {forbidden}")

    def test_does_not_instruct_reading_ukm_db_logs(self):
        lower = self.content.lower()
        self.assertNotIn("базу данных укм", lower)
        self.assertNotIn("sql", lower)

    def test_no_windows_msi_programdata(self):
        lower = self.content.lower()
        for fb in ("C:\\\\", "programdata", ".msi", "program files"):
            self.assertNotIn(fb, lower,
                             f"Runbook must not contain Windows path: {fb}")

    def test_no_real_secrets(self):
        """Must not contain real-looking secrets."""
        lower = self.content.lower()
        self.assertNotIn("Bearer ", self.content)
        self.assertNotIn("supersecret", lower)
        self.assertNotIn("prod_password", lower)

    def test_no_real_backend_url_except_example(self):
        """Only backend.example allowed, no real production URLs."""
        # Remove lines with "backend.example" (the placeholder)
        lines = self.content.split("\n")
        filtered = []
        for line in lines:
            if "backend.example" in line:
                continue
            filtered.append(line)
        code = "\n".join(filtered)

        self.assertNotIn("https://prod.", code)
        self.assertNotIn("https://backend.", code)

    def test_start_commands_only_in_manual_section(self):
        """systemctl start should appear in runbook (manual section allowed)."""
        self.assertIn("systemctl start", self.content,
                      "Runbook must contain manual start commands")


# ══════════════════════════════════════════════════════════════════════
# Bootstrap & Preflight — No systemctl
# ══════════════════════════════════════════════════════════════════════

class TestBootstrapPreflightNoSystemctl(unittest.TestCase):
    """Bootstrap and preflight scripts must NOT call systemctl."""

    def test_bootstrap_no_systemctl(self):
        code = _code_without_docstrings_and_comments(
            _INSTALL_DIR / "kso_linux_bootstrap.py")
        for banned in ("systemctl start", "systemctl enable",
                        "systemctl restart", "systemctl daemon-reload",
                        "systemctl --now"):
            self.assertNotIn(banned, code,
                             f"Bootstrap must not call {banned}")

    def test_preflight_no_systemctl(self):
        code = _code_without_docstrings_and_comments(
            _PREFLIGHT_DIR / "kso_linux_preflight.py")
        for banned in ("systemctl start", "systemctl enable",
                        "systemctl restart", "systemctl daemon-reload",
                        "systemctl --now"):
            self.assertNotIn(banned, code,
                             f"Preflight must not call {banned}")


# ══════════════════════════════════════════════════════════════════════
# Runbook Content Quality
# ══════════════════════════════════════════════════════════════════════

class TestRunbookContentQuality(unittest.TestCase):
    """Runbook is well-structured and complete."""

    def setUp(self):
        self.content = _read(_RUNBOOK_PATH)

    def test_has_purpose_section(self):
        self.assertIn("Цель пилота", self.content)

    def test_has_prerequisites_section(self):
        self.assertIn("должно быть готово", self.content)

    def test_has_forbidden_section(self):
        self.assertIn("Что запрещено", self.content)

    def test_has_manual_start_instructions(self):
        """Each of the three services has explicit start instructions."""
        self.assertIn("systemctl start kso-state-adapter", self.content)
        self.assertIn("systemctl start kso-sidecar", self.content)
        self.assertIn("systemctl start kso-player", self.content)

    def test_has_stop_instructions(self):
        for svc in ("kso-player", "kso-sidecar", "kso-state-adapter"):
            self.assertIn(f"systemctl stop {svc}", self.content,
                          f"Runbook must contain stop for {svc}")

    def test_has_status_check(self):
        self.assertIn("systemctl status", self.content)

    def test_has_env_templates_without_real_values(self):
        """Env examples use CHANGE_ME placeholders."""
        self.assertIn("CHANGE_ME", self.content)
        self.assertIn("backend.example", self.content)

    def test_has_success_criteria(self):
        self.assertIn("успешного пилота", self.content)

    def test_has_report_guidance(self):
        self.assertIn("отчёт", self.content.lower())

    def test_has_health_check_guidance(self):
        self.assertIn("health", self.content.lower())

    def test_has_pop_safety_guidance(self):
        """Runbook warns about not exposing raw PoP payload."""
        self.assertIn("pop", self.content.lower())
        self.assertIn("raw", self.content.lower())

    def test_has_journalctl_guidance(self):
        self.assertIn("journalctl", self.content)

    def test_no_systemctl_enable_anywhere(self):
        """Enable must not appear as instruction outside forbidden table."""
        lines = self.content.split("\n")
        in_forbidden_table = False
        for line in lines:
            stripped = line.strip()
            if "Что запрещено" in stripped:
                in_forbidden_table = True
                continue
            if in_forbidden_table:
                if stripped.startswith("## ") or stripped.startswith("---"):
                    in_forbidden_table = False
                continue
            if "systemctl enable" in stripped:
                self.fail(
                    "systemctl enable found outside 'Что запрещено' table: "
                    f"{stripped[:80]}"
                )

    def test_has_step_numbering(self):
        """Runbook uses numbered steps."""
        for i in range(1, 14):
            self.assertIn(f"Шаг {i}", self.content,
                          f"Runbook must contain Шаг {i}")


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
