"""KSO Runtime Release Package Contract — Validation Tests.

Validates release contract doc, manifest example, builder script.
No systemd, no service start, no real UKM 4, no Chromium.
"""

import json as _json
import os as _os
import re as _re
import sys as _sys
import tempfile
import unittest
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════════

_SELF_DIR = Path(__file__).resolve().parent
_INFRA_ROOT = _SELF_DIR.parent
_RELEASE_DIR = _INFRA_ROOT / "release"
_INSTALL_DIR = _INFRA_ROOT / "install"
_PREFLIGHT_DIR = _INFRA_ROOT / "preflight"
_DOCS_DIR = _INFRA_ROOT.parent.parent / "docs" / "kso"

_CONTRACT_PATH = _DOCS_DIR / "kso-runtime-release-package-contract.md"
_MANIFEST_PATH = _RELEASE_DIR / "kso_release_manifest.example.json"
_BUILDER_PATH = _RELEASE_DIR / "kso_release_package_builder.py"

# Add release dir to path for builder import
if str(_RELEASE_DIR) not in _sys.path:
    _sys.path.insert(0, str(_RELEASE_DIR))

from kso_release_package_builder import (
    run_build,
    BuildResult,
    format_build_result,
)


def _read(path: Path) -> str:
    return path.read_text()


def _code_without_docstrings(path: Path) -> str:
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


FORBIDDEN = frozenset({
    "bearer", "backend_url", "device_code", "api_key",
    "receipt_number", "card_number", "pan",
    "customer_id", "phone", "fiscal_data",
    "CHANGE_ME_SECRET",
    "C:\\\\", "ProgramData", ".msi",
    "systemctl enable", "systemctl restart",
})


def _assert_safe(test, output: str):
    lower = output.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Safe output must not contain '{fb}': {output[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Contract Doc
# ══════════════════════════════════════════════════════════════════════

class TestReleaseContractExists(unittest.TestCase):

    def test_contract_doc_exists(self):
        self.assertTrue(_CONTRACT_PATH.is_file(),
                        "Release package contract must exist")

    def test_contract_not_empty(self):
        content = _read(_CONTRACT_PATH)
        self.assertGreater(len(content), 500,
                          "Contract must be substantial (>500 chars)")

    def test_manifest_example_exists(self):
        self.assertTrue(_MANIFEST_PATH.is_file(),
                        "Manifest example must exist")


class TestReleaseContractContent(unittest.TestCase):

    def setUp(self):
        self.content = _read(_CONTRACT_PATH)

    def test_describes_package_structure(self):
        self.assertIn("kso-runtime", self.content)

    def test_describes_versioning(self):
        self.assertIn("MAJOR.MINOR.PATCH", self.content)
        self.assertIn("version", self.content.lower())

    def test_describes_checksums(self):
        self.assertIn("CHECKSUMS.sha256", self.content)
        self.assertIn("sha256", self.content.lower())

    def test_describes_current_symlink_layout(self):
        self.assertIn("current", self.content.lower())
        self.assertIn("releases", self.content.lower())
        self.assertIn("symlink", self.content.lower())

    def test_describes_rollback(self):
        self.assertIn("rollback", self.content.lower())
        self.assertIn("предыдущий", self.content.lower())  # "previous" in Russian

    def test_forbids_deleting_pop_cache(self):
        self.assertIn("не удалять", self.content.lower())
        self.assertIn("sent", self.content.lower())

    def test_mentions_internal_storage_only(self):
        self.assertIn("внутреннем", self.content.lower())
        self.assertIn("GitLab Releases", self.content)

    def test_forbids_public_download(self):
        self.assertIn("GitHub", self.content)
        self.assertIn("запрещено", self.content.lower())

    def test_no_real_secrets(self):
        lower = self.content.lower()
        self.assertNotIn("CHANGE_ME_SECRET", lower)

    def test_no_windows_paths(self):
        lower = self.content.lower()
        for fb in ("C:\\\\", "programdata", ".msi"):
            self.assertNotIn(fb, lower)


# ══════════════════════════════════════════════════════════════════════
# Manifest Example
# ══════════════════════════════════════════════════════════════════════

class TestManifestExample(unittest.TestCase):

    def setUp(self):
        self.data = _json.loads(_read(_MANIFEST_PATH))

    def test_valid_json(self):
        self.assertIsInstance(self.data, dict)

    def test_has_required_fields(self):
        for key in ("schema_version", "package_name", "version",
                     "components", "created_at_utc", "checksums_file"):
            self.assertIn(key, self.data,
                          f"Manifest must have '{key}'")

    def test_components_list(self):
        self.assertIsInstance(self.data["components"], list)
        self.assertGreater(len(self.data["components"]), 0)

    def test_no_secrets_urls_device_values(self):
        raw = _read(_MANIFEST_PATH).lower()
        for fb in ("secret", "token", "device_code", "backend_url",
                    "password", "bearer", "api_key"):
            self.assertNotIn(fb, raw,
                             f"Manifest must not contain '{fb}'")


# ══════════════════════════════════════════════════════════════════════
# Package Builder
# ══════════════════════════════════════════════════════════════════════

class TestBuilderDryRun(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_bld_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_changes_nothing(self):
        """Dry-run must not create files."""
        out_dir = self.tmp / "output"
        result = run_build(
            version="0.1.0",
            output_dir=str(out_dir),
            dry_run=True,
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.package_size_bytes, 0)
        self.assertFalse(out_dir.exists(),
                         "Dry-run must not create output directory")
        self.assertGreater(result.files_collected, 0)
        self.assertGreater(result.files_excluded, 0)
        self.assertEqual(result.reason, "dry_run_completed")
        _assert_safe(self, repr(result))
        _assert_safe(self, format_build_result(result))


class TestBuilderBuild(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_bld_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_writes_only_to_output_dir(self):
        """Build must not write to /opt, /etc, /var."""
        out_dir = self.tmp / "output"
        result = run_build(
            version="0.1.0",
            output_dir=str(out_dir),
            dry_run=False,
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reason, "build_completed")
        self.assertTrue(out_dir.is_dir())

        # Check files created
        self.assertTrue((out_dir / "VERSION").is_file())
        self.assertTrue((out_dir / "MANIFEST.json").is_file())
        self.assertTrue((out_dir / "CHECKSUMS.sha256").is_file())

        pkg_name = f"kso-runtime-0.1.0.tar.gz"
        self.assertTrue((out_dir / pkg_name).is_file())

        # Must not create files in /opt, /etc, /var
        for bad_dir in ("/opt", "/etc", "/var"):
            self.assertFalse(
                Path(bad_dir, "verny").exists(),
                f"Must not write to {bad_dir}"
            )

        _assert_safe(self, repr(result))
        _assert_safe(self, format_build_result(result))

    def test_build_excludes_env_files(self):
        """Package must not contain real .env files."""
        out_dir = self.tmp / "output"
        result = run_build(
            version="0.1.0",
            output_dir=str(out_dir),
            dry_run=False,
        )

        pkg_path = out_dir / "kso-runtime-0.1.0.tar.gz"
        import tarfile
        with tarfile.open(str(pkg_path), "r:gz") as tar:
            names = tar.getnames()
            for name in names:
                fname = Path(name).name
                if fname.endswith(".env") and not fname.endswith(".example"):
                    self.fail(f"Package contains forbidden .env: {name}")

    def test_build_excludes_runtime_data(self):
        """Package must not contain pop/, state/, media/current, runtime/."""
        out_dir = self.tmp / "output"
        run_build(version="0.1.0", output_dir=str(out_dir), dry_run=False)

        pkg_path = out_dir / "kso-runtime-0.1.0.tar.gz"
        import tarfile
        with tarfile.open(str(pkg_path), "r:gz") as tar:
            names = tar.getnames()
            for name in names:
                parts = name.split("/")
                if "pop" in parts:
                    self.fail(f"Package contains pop/: {name}")
                if "state" in parts and parts[-1].endswith(".json"):
                    self.fail(f"Package contains state file: {name}")
                if "runtime" in parts and "player_shell" in name:
                    self.fail(f"Package contains runtime player_shell: {name}")

    def test_build_creates_version(self):
        out_dir = self.tmp / "output"
        run_build(version="0.1.0", output_dir=str(out_dir), dry_run=False)

        v = (out_dir / "VERSION").read_text().strip()
        self.assertEqual(v, "0.1.0")

    def test_build_creates_manifest_json(self):
        out_dir = self.tmp / "output"
        run_build(version="0.1.0", output_dir=str(out_dir), dry_run=False)

        manifest = _json.loads((out_dir / "MANIFEST.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["package_name"], "kso-runtime")
        self.assertIn("components", manifest)

    def test_build_creates_checksums_file(self):
        out_dir = self.tmp / "output"
        run_build(version="0.1.0", output_dir=str(out_dir), dry_run=False)

        csums = (out_dir / "CHECKSUMS.sha256").read_text()
        self.assertGreater(len(csums), 100)
        self.assertIn("  ", csums)  # format: <sha256>  <path>

    def test_build_result_output_safe(self):
        out_dir = self.tmp / "output"
        result = run_build(
            version="0.1.0",
            output_dir=str(out_dir),
            dry_run=False,
        )
        output = format_build_result(result)
        _assert_safe(self, output)

    def test_build_no_secrets_in_package(self):
        """Package contents must not contain real secrets.
        README/docs may mention 'bearer' in auth protocol descriptions — skip those."""
        out_dir = self.tmp / "output"
        run_build(version="0.1.0", output_dir=str(out_dir), dry_run=False)

        pkg_path = out_dir / "kso-runtime-0.1.0.tar.gz"
        import tarfile
        with tarfile.open(str(pkg_path), "r:gz") as tar:
            for member in tar:
                if member.isfile():
                    # Skip README/docs and Python source — they describe auth protocol
                    if member.name.endswith((".md", ".txt", ".py")):
                        continue
                    f = tar.extractfile(member)
                    if f:
                        content = f.read().decode("utf-8", errors="ignore").lower()
                        for fb in ("CHANGE_ME_SECRET", "bearer "):
                            self.assertNotIn(fb, content,
                                             f"Package contains '{fb}' in {member.name}")


class TestBuilderSafety(unittest.TestCase):

    def test_no_systemctl_in_builder(self):
        code = _code_without_docstrings(_BUILDER_PATH)
        for banned in ("systemctl start", "systemctl enable",
                        "systemctl restart", "systemctl daemon-reload"):
            self.assertNotIn(banned, code,
                             f"Builder must not call {banned}")

    def test_no_windows_in_builder(self):
        src = _read(_BUILDER_PATH)
        # Remove FORBIDDEN_IN_OUTPUT block
        lines = src.split("\n")
        filtered = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if "FORBIDDEN_IN_OUTPUT" in stripped and "frozenset" in stripped:
                skip = True
                continue
            if skip:
                if stripped == "})":
                    skip = False
                continue
            filtered.append(line)
        code = "\n".join(filtered)
        self.assertNotIn("C:\\\\", code)
        self.assertNotIn("ProgramData", code)
        self.assertNotIn(".msi", code.lower())


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
