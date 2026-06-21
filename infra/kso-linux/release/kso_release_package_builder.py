#!/usr/bin/env python3
"""KSO Runtime Release Package Builder.

Builds kso-runtime-<version>.tar.gz for internal IT distribution.

Usage:
    # Dry-run (default — safe, no changes):
    python3 kso_release_package_builder.py --dry-run

    # Build to output dir:
    python3 kso_release_package_builder.py --build --version 0.1.0 \
        --output-dir /tmp/kso-release

NEVER writes to /opt, /etc, /var. NEVER includes runtime data or secrets.
"""

import argparse
import hashlib
import json as _json
import os as _os
import sys as _sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Files/directories to include (relative to project root)
_INCLUDE_ROOTS = [
    "apps/kso_player",
    "apps/kso_sidecar_agent",
    "apps/kso_state_adapter",
    "player_shell",
    "infra/kso-linux/systemd",
    "infra/kso-linux/env-examples",
    "infra/kso-linux/install",
    "infra/kso-linux/preflight",
    "infra/kso-linux/release",
    "docs/kso",
]

# Player shell source
_PLAYER_SHELL_DIR = _PROJECT_ROOT / "apps" / "kso_player" / "player_shell"

# Paths/files to EXCLUDE (glob patterns are matched against file paths)
_EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".gitignore",
    ".DS_Store",
    "*.log",
    "*.pid",
    "*.lock",
    "*.env",                           # real .env files (but NOT .example)
    "state/kso_state.json",
    "manifest/current_manifest.json",
    "media/current",
    "pop/pending",
    "pop/sent",
    "health",
    "runtime/player_shell",
    "tests/",
    "*.egg-info",
    "*.dist-info",
]

# Specific files to exclude (exact relative paths)
_EXCLUDE_FILES = {
    # No specific files yet — patterns above handle the categories
}

FORBIDDEN_IN_OUTPUT = frozenset({
    "secret", "token", "password", "authorization",
    "bearer", "backend_url", "device_code", "api_key",
    "receipt_number", "card_number", "pan",
    "customer_id", "phone", "fiscal_data",
    "CHANGE_ME_SECRET",
    "C:\\\\", "ProgramData", ".msi",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class BuildResult:
    """Safe build result. Never contains paths/secrets beyond allowed."""

    status: str = "ok"                # ok | error
    dry_run: bool = True
    version: str = "0.0.0"
    output_dir: str = ""
    package_name: str = ""
    package_path: str = ""

    files_collected: int = 0
    files_excluded: int = 0
    package_size_bytes: int = 0

    warnings: List[str] = field(default_factory=list)
    warnings_count: int = 0
    reason: str = "dry_run_completed"

    def __post_init__(self):
        self.warnings_count = len(self.warnings)

    def __repr__(self) -> str:
        return (
            f"BuildResult("
            f"status={self.status!r}, "
            f"dry_run={self.dry_run}, "
            f"version={self.version!r}, "
            f"files_collected={self.files_collected}, "
            f"files_excluded={self.files_excluded}, "
            f"package_size_bytes={self.package_size_bytes}, "
            f"warnings_count={self.warnings_count}, "
            f"reason={self.reason!r})"
        )


def format_build_result(result: BuildResult) -> str:
    """Safe formatted output."""
    lines = [
        f"status: {result.status}",
        f"dry_run: {str(result.dry_run).lower()}",
        f"version: {result.version}",
        f"package_name: {result.package_name}",
        f"package_path: {result.package_path}",
        f"files_collected: {result.files_collected}",
        f"files_excluded: {result.files_excluded}",
        f"package_size_bytes: {result.package_size_bytes}",
        f"warnings_count: {result.warnings_count}",
        f"reason: {result.reason}",
    ]
    if result.warnings:
        lines.append("warnings:")
        for w in result.warnings:
            lines.append(f"  - {w}")

    output = "\n".join(lines)
    lower = output.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            raise ValueError(f"Output contains forbidden '{fb}'")
    return output


# ══════════════════════════════════════════════════════════════════════
# File filtering
# ══════════════════════════════════════════════════════════════════════

def _should_include(file_path: str) -> bool:
    """Check if a file should be included in the package."""
    # Check exact excludes
    if file_path in _EXCLUDE_FILES:
        return False

    # Check exclude patterns
    parts = file_path.replace("\\", "/").split("/")
    fname = parts[-1] if parts else ""

    for pattern in _EXCLUDE_PATTERNS:
        # Exact directory match
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            if dir_name in parts:
                return False
        # Glob match on filename
        if pattern.startswith("*."):
            ext = pattern[1:]
            if fname.endswith(ext):
                return False
        # Exact name match
        if fname == pattern or pattern in parts:
            return False
        # Path contains excluded directory
        if f"/{pattern}/" in f"/{file_path}/":
            return False

    # Exclude .env files that are NOT .example
    if fname.endswith(".env") and not fname.endswith(".env.example"):
        return False

    # Exclude __pycache__ anywhere in path
    if "__pycache__" in parts:
        return False

    return True


def _collect_files(project_root: Path) -> tuple:
    """Collect all files to include in the package. Returns (files, excluded)."""
    files = []
    excluded = []

    for root in _INCLUDE_ROOTS:
        root_path = project_root / root
        if not root_path.exists():
            continue
        if root_path.is_file():
            files.append(root)
            continue

        for dirpath, dirnames, filenames in _os.walk(str(root_path)):
            # Get relative path from project root
            for fname in sorted(filenames):
                abs_path = _os.path.join(dirpath, fname)
                rel_path = _os.path.relpath(abs_path, str(project_root))
                rel_path_unix = rel_path.replace("\\", "/")

                if _should_include(rel_path_unix):
                    files.append(rel_path_unix)
                else:
                    excluded.append(rel_path_unix)

    return files, excluded


# ══════════════════════════════════════════════════════════════════════
# Checksum
# ══════════════════════════════════════════════════════════════════════

def _compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _generate_checksums(project_root: Path, file_list: List[str]) -> str:
    """Generate CHECKSUMS.sha256 content."""
    lines = []
    for rel_path in sorted(file_list):
        full_path = project_root / rel_path
        sha = _compute_sha256(full_path)
        lines.append(f"{sha}  {rel_path}")
    return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_build(
    version: str = "0.1.0",
    output_dir: str = "/tmp/kso-release",
    dry_run: bool = True,
    project_root: Optional[Path] = None,
) -> BuildResult:
    """Build KSO runtime release package.

    Args:
        version: Semantic version (MAJOR.MINOR.PATCH)
        output_dir: Where to write the package
        dry_run: If True, only collect files, don't create archive
        project_root: Project root (default: auto-detect)

    Returns:
        BuildResult — always safe, never raises.
    """
    root = project_root or _PROJECT_ROOT
    result = BuildResult(
        dry_run=dry_run,
        version=version,
        output_dir=output_dir,
        package_name=f"kso-runtime-{version}.tar.gz",
    )

    # ── Collect files ─────────────────────────────────────────────
    try:
        files, excluded = _collect_files(root)
        result.files_collected = len(files)
        result.files_excluded = len(excluded)
    except Exception as e:
        result.status = "error"
        result.reason = "collect_failed"
        result.warnings.append(f"File collection failed: {e}")
        return result

    if result.files_collected == 0:
        result.status = "error"
        result.reason = "no_files_collected"
        result.warnings.append("No files collected — check include roots")
        return result

    # ── Dry-run ───────────────────────────────────────────────────
    if dry_run:
        result.reason = "dry_run_completed"
        result.status = "ok"
        return result

    # ── Build ─────────────────────────────────────────────────────
    out_path = Path(output_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)

        pkg_path = out_path / result.package_name

        # Create tar.gz
        with tarfile.open(str(pkg_path), "w:gz") as tar:
            for rel_path in sorted(files):
                full_path = root / rel_path
                tar.add(str(full_path), arcname=rel_path)

        # Write VERSION
        version_path = out_path / "VERSION"
        version_path.write_text(f"{version}\n")

        # Write MANIFEST.json
        manifest = {
            "schema_version": 1,
            "package_name": "kso-runtime",
            "version": version,
            "components": [
                "kso_player",
                "kso_sidecar_agent",
                "kso_state_adapter",
                "kso_linux_deployment",
            ],
            "created_at_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "checksums_file": "CHECKSUMS.sha256",
        }
        manifest_path = out_path / "MANIFEST.json"
        manifest_path.write_text(_json.dumps(manifest, indent=2) + "\n")

        # Write CHECKSUMS.sha256 (of files inside the archive)
        checksums = _generate_checksums(root, files)
        checksums_path = out_path / "CHECKSUMS.sha256"
        checksums_path.write_text(checksums)

        # Add metadata files to archive
        with tarfile.open(str(pkg_path), "w:gz") as tar:
            for rel_path in sorted(files):
                full_path = root / rel_path
                tar.add(str(full_path), arcname=rel_path)
            # Add metadata files
            for meta_file in ("VERSION", "MANIFEST.json", "CHECKSUMS.sha256"):
                tar.add(str(out_path / meta_file), arcname=meta_file)

        result.status = "ok"
        result.reason = "build_completed"
        result.package_path = str(pkg_path.resolve())
        result.package_size_bytes = pkg_path.stat().st_size

    except Exception as e:
        result.status = "error"
        result.reason = "build_failed"
        result.warnings.append(f"Build failed: {e}")

    return result


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-release-package-builder",
        description="KSO Runtime Release Package Builder",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Plan only, no changes (default)",
    )
    parser.add_argument(
        "--build", action="store_true", default=False,
        help="Actually build the package",
    )
    parser.add_argument(
        "--version", type=str, default="0.1.0",
        help="Semantic version (default: 0.1.0)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="/tmp/kso-release",
        help="Output directory (default: /tmp/kso-release)",
    )

    args = parser.parse_args()

    result = run_build(
        version=args.version,
        output_dir=args.output_dir,
        dry_run=not args.build,
    )

    print(format_build_result(result))
    if result.status == "error":
        _sys.exit(1)
    _sys.exit(0)


if __name__ == "__main__":
    main()
