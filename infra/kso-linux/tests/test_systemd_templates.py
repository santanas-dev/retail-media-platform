"""KSO Linux systemd Unit Templates — Validation Tests.

Validates structure, safety, and correctness of:
  - systemd unit templates
  - env file examples
  - README

No real systemd, no systemctl, no service start.
"""

import os as _os
import re as _re
import unittest
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

_SELF_DIR = Path(__file__).resolve().parent
_INFRA_ROOT = _SELF_DIR.parent
_SYSTEMD_DIR = _INFRA_ROOT / "systemd"
_ENV_DIR = _INFRA_ROOT / "env-examples"
_README_PATH = _INFRA_ROOT / "README.md"


def _read(path: Path) -> str:
    return path.read_text()


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestSystemdTemplatesExist(unittest.TestCase):
    """All required files exist."""

    def test_systemd_dir_exists(self):
        self.assertTrue(_SYSTEMD_DIR.is_dir())

    def test_sidecar_service_exists(self):
        self.assertTrue((_SYSTEMD_DIR / "kso-sidecar.service").is_file())

    def test_player_service_exists(self):
        self.assertTrue((_SYSTEMD_DIR / "kso-player.service").is_file())

    def test_state_adapter_service_exists(self):
        self.assertTrue((_SYSTEMD_DIR / "kso-state-adapter.service").is_file())

    def test_env_dir_exists(self):
        self.assertTrue(_ENV_DIR.is_dir())

    def test_sidecar_env_example_exists(self):
        self.assertTrue((_ENV_DIR / "kso-sidecar.env.example").is_file())

    def test_player_env_example_exists(self):
        self.assertTrue((_ENV_DIR / "kso-player.env.example").is_file())

    def test_state_adapter_env_example_exists(self):
        self.assertTrue((_ENV_DIR / "kso-state-adapter.env.example").is_file())

    def test_readme_exists(self):
        self.assertTrue(_README_PATH.is_file())


class TestSidecarServiceContent(unittest.TestCase):
    """kso-sidecar.service content checks."""

    def setUp(self):
        self.content = _read(_SYSTEMD_DIR / "kso-sidecar.service")

    def test_uses_sidecar_daemon(self):
        self.assertIn("sidecar-daemon", self.content,
                      "Unit must use sidecar-daemon command")

    def test_uses_linux_paths_only(self):
        self.assertIn("/var/lib/verny/kso", self.content)
        self.assertIn("/run/verny/kso", self.content)

    def test_no_windows_paths(self):
        self.assertNotIn("C:\\", self.content)
        self.assertNotIn("ProgramData", self.content)
        self.assertNotIn("Program Files", self.content)

    def test_no_msi(self):
        self.assertNotIn(".msi", self.content.lower())
        self.assertNotIn("msiexec", self.content.lower())

    def test_no_real_secret_values(self):
        """Secret must be env var name, not literal value."""
        # ExecStart may span multiple lines with \ continuation.
        # Collect all ExecStart-related lines.
        all_exec = []
        in_exec = False
        for line in self.content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("ExecStart=") or stripped.startswith("ExecStart ="):
                in_exec = True
                all_exec.append(stripped)
            elif in_exec:
                if stripped.endswith("\\") or not stripped:
                    all_exec.append(stripped)
                else:
                    all_exec.append(stripped)
                    in_exec = False

        full_exec = " ".join(all_exec)
        self.assertIn("VERNY_KSO_DEVICE_SECRET", full_exec,
                      "ExecStart must reference VERNY_KSO_DEVICE_SECRET env")
        self.assertNotIn("CHANGE_ME", full_exec,
                         "ExecStart must not contain placeholder secret literal")

    def test_uses_network_online_target(self):
        self.assertIn("network-online.target", self.content)

    def test_secret_by_env_name_only(self):
        """Must use --device-secret-env ENV_VAR_NAME, not --device-secret VALUE."""
        self.assertIn("--device-secret-env VERNY_KSO_DEVICE_SECRET", self.content)
        self.assertNotIn("--device-secret ", self.content,
                         "Must not use --device-secret with value, use --device-secret-env")

    def test_restart_policy(self):
        self.assertIn("Restart=always", self.content)

    def test_no_shell_true(self):
        self.assertNotIn("shell=True", self.content.lower())
        self.assertNotIn("/bin/sh", self.content)
        self.assertNotIn("/bin/bash", self.content)

    def test_no_curl_wget(self):
        self.assertNotIn("curl", self.content.lower())
        self.assertNotIn("wget", self.content.lower())

    def test_security_hardening_options(self):
        self.assertIn("NoNewPrivileges=true", self.content)
        self.assertIn("PrivateTmp=true", self.content)
        self.assertIn("ProtectSystem=full", self.content)
        self.assertIn("ProtectHome=true", self.content)

    def test_read_write_paths(self):
        self.assertIn("ReadWritePaths=", self.content)
        self.assertIn("/var/lib/verny/kso", self.content)
        self.assertIn("/run/verny/kso", self.content)
        self.assertIn("/var/log/verny/kso", self.content)

    def test_read_only_paths(self):
        self.assertIn("ReadOnlyPaths=", self.content)
        self.assertIn("/opt/verny/kso", self.content)

    def test_health_file_path(self):
        self.assertIn("/run/verny/kso/sidecar-health.json", self.content)

    def test_root_path(self):
        self.assertIn("--root /var/lib/verny/kso", self.content)

    def test_no_state_adapter_dependency(self):
        """Sidecar must not depend on state adapter."""
        self.assertNotIn("kso-state-adapter", self.content,
                         "Sidecar must not depend on state adapter")


class TestPlayerServiceContent(unittest.TestCase):
    """kso-player.service content checks."""

    def setUp(self):
        self.content = _read(_SYSTEMD_DIR / "kso-player.service")

    def test_uses_runtime_daemon(self):
        self.assertIn("runtime-daemon", self.content,
                      "Unit must use runtime-daemon command")

    def test_uses_linux_paths_only(self):
        self.assertIn("/var/lib/verny/kso", self.content)
        self.assertIn("/opt/verny/kso/player_shell", self.content)
        self.assertIn("/var/lib/verny/kso/runtime/player_shell", self.content)

    def test_no_windows_paths(self):
        self.assertNotIn("C:\\", self.content)
        self.assertNotIn("ProgramData", self.content)
        self.assertNotIn("Program Files", self.content)

    def test_no_msi(self):
        self.assertNotIn(".msi", self.content.lower())

    def test_uses_wants_not_requires_for_sidecar(self):
        # Wants may list multiple services: "Wants=kso-state-adapter.service kso-sidecar.service"
        self.assertIn("Wants=kso-state-adapter.service", self.content)
        self.assertIn("kso-sidecar.service", self.content)
        self.assertNotIn("Requires=kso-sidecar.service", self.content,
                         "Player must use Wants= not Requires= for sidecar")
        self.assertNotIn("Requires=kso-state-adapter.service", self.content,
                         "Player must use Wants= not Requires= for state adapter")

    def test_after_sidecar_service(self):
        self.assertIn("kso-sidecar.service", self.content)
        self.assertIn("kso-state-adapter.service", self.content)

    def test_chromium_bin_from_env(self):
        self.assertIn("${VERNY_KSO_CHROMIUM_BIN}", self.content)

    def test_confirm_launch(self):
        self.assertIn("--confirm-launch", self.content)

    def test_confirm_display_completed(self):
        self.assertIn("--confirm-display-completed", self.content)

    def test_max_cycles_daemon_mode(self):
        """Daemon mode: no --max-cycles flag (None = run forever)."""
        self.assertNotIn("--max-cycles", self.content,
                         "Daemon mode should not use --max-cycles flag")

    def test_restart_policy(self):
        self.assertIn("Restart=always", self.content)

    def test_no_shell_true(self):
        self.assertNotIn("shell=True", self.content.lower())
        self.assertNotIn("/bin/sh", self.content)
        self.assertNotIn("/bin/bash", self.content)

    def test_no_curl_wget(self):
        self.assertNotIn("curl", self.content.lower())
        self.assertNotIn("wget", self.content.lower())

    def test_security_hardening_options(self):
        self.assertIn("NoNewPrivileges=true", self.content)
        self.assertIn("PrivateTmp=true", self.content)
        self.assertIn("ProtectSystem=full", self.content)
        self.assertIn("ProtectHome=true", self.content)

    def test_read_write_paths(self):
        self.assertIn("ReadWritePaths=", self.content)
        self.assertIn("/var/lib/verny/kso", self.content)
        self.assertIn("/run/verny/kso", self.content)

    def test_read_only_paths(self):
        self.assertIn("ReadOnlyPaths=", self.content)
        self.assertIn("/opt/verny/kso", self.content)

    def test_health_file_path(self):
        self.assertIn("/run/verny/kso/player-health.json", self.content)

    def test_root_path(self):
        self.assertIn("--root /var/lib/verny/kso", self.content)

    def test_source_shell_path(self):
        self.assertIn("--source-shell-dir /opt/verny/kso/player_shell", self.content)

    def test_runtime_shell_path(self):
        self.assertIn("--runtime-shell-dir /var/lib/verny/kso/runtime/player_shell",
                      self.content)


class TestAdapterServiceContent(unittest.TestCase):
    """kso-state-adapter.service content checks."""

    def setUp(self):
        self.content = _read(_SYSTEMD_DIR / "kso-state-adapter.service")

    def test_uses_state_adapter_cli(self):
        self.assertIn("kso_state_adapter.cli daemon", self.content)

    def test_uses_linux_paths_only(self):
        self.assertIn("/var/lib/verny/kso", self.content)

    def test_no_windows_paths(self):
        self.assertNotIn("C:\\", self.content)

    def test_no_real_secrets(self):
        self.assertNotIn("CHANGE_ME", self.content)

    def test_health_file_path(self):
        self.assertIn("/run/verny/kso/state-adapter-health.json", self.content)

    def test_security_hardening(self):
        self.assertIn("NoNewPrivileges=true", self.content)
        self.assertIn("ProtectSystem=full", self.content)

    def test_source_state_from_env(self):
        self.assertIn("${VERNY_KSO_STATIC_STATE}", self.content)

    def test_env_file_path(self):
        self.assertIn("/etc/verny/kso/state-adapter.env", self.content)

    def test_restart_policy(self):
        self.assertIn("Restart=always", self.content)


class TestEnvExamples(unittest.TestCase):
    """Environment example files checks."""

    def test_sidecar_env_no_real_secrets(self):
        content = _read(_ENV_DIR / "kso-sidecar.env.example")
        # Must contain placeholders, not real secrets
        self.assertIn("CHANGE_ME", content)
        self.assertIn("CHANGE_ME_SECRET", content)
        self.assertNotIn("Bearer", content, "No real tokens")
        self.assertNotIn(
            "https://prod", content,
            "No real production URLs"
        )

    def test_sidecar_env_has_backend_url(self):
        content = _read(_ENV_DIR / "kso-sidecar.env.example")
        self.assertIn("VERNY_KSO_BACKEND_URL", content)
        self.assertIn("VERNY_KSO_DEVICE_CODE", content)
        self.assertIn("VERNY_KSO_DEVICE_SECRET", content)

    def test_player_env_has_chromium_bin(self):
        content = _read(_ENV_DIR / "kso-player.env.example")
        self.assertIn("VERNY_KSO_CHROMIUM_BIN", content)

    def test_player_env_no_real_secrets(self):
        content = _read(_ENV_DIR / "kso-player.env.example")
        self.assertNotIn("Bearer", content)
        self.assertNotIn("password", content.lower())

    def test_env_files_are_examples_not_production(self):
        """Ensure .example files, not real .env files."""
        self.assertTrue(
            (_ENV_DIR / "kso-sidecar.env.example").name.endswith(".example"),
            "Sidecar env must be .example, not production"
        )
        self.assertTrue(
            (_ENV_DIR / "kso-player.env.example").name.endswith(".example"),
            "Player env must be .example, not production"
        )


class TestReadmeContent(unittest.TestCase):
    """README.md checks."""

    def setUp(self):
        self.content = _read(_README_PATH)

    def test_documents_deployment(self):
        self.assertIn("systemd", self.content.lower())

    def test_lists_required_dirs(self):
        for d in ["/opt/verny/kso", "/etc/verny/kso",
                   "/var/lib/verny/kso", "/run/verny/kso", "/var/log/verny/kso"]:
            self.assertIn(d, self.content,
                          f"README must document directory: {d}")

    def test_mentions_security_hardening(self):
        self.assertIn("NoNewPrivileges", self.content)
        self.assertIn("hardening", self.content.lower())

    def test_no_android_led_esl_in_v1(self):
        self.assertIn("Android", self.content,
                      "README must document that Android is NOT in v1")
        self.assertIn("LED", self.content,
                      "README must document that LED is NOT in v1")
        self.assertIn("ESL", self.content,
                      "README must document that ESL is NOT in v1")

    def test_no_real_secrets(self):
        self.assertNotIn("supersecret", self.content.lower())
        self.assertNotIn("prod_password", self.content.lower())
        self.assertNotIn(
            "https://prod.", self.content,
            "No real production URLs"
        )

    def test_checklist_present(self):
        self.assertIn("systemd-analyze verify", self.content)
        self.assertIn("systemctl", self.content.lower())


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
