"""KSO Player Runtime Shell Workspace Core — prepare runtime copy of HTML shell.

Copies whitelist shell files from the immutable source directory to
the mutable runtime directory. Uses atomic writes (tmp → rename).

Pipeline (future): prepare workspace → snapshot writer → Chromium launch.

NO Chromium, NO systemd, NO backend, NO PoP write, NO snapshot writer.
Source shell is NEVER modified.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

REASON_PREPARED = "prepared"
REASON_SOURCE_DIR_MISSING = "source_dir_missing"
REASON_SOURCE_DIR_NOT_DIR = "source_dir_not_dir"
REASON_REQUIRED_FILES_MISSING = "required_files_missing"
REASON_COPY_FAILED = "copy_failed"
REASON_INVALID_ARGS = "invalid_args"

# Only these files are copied to the runtime workspace
SHELL_WHITELIST = frozenset({
    "index.html",
    "styles.css",
    "player.js",
    "bootstrap_snapshot.js",
    "bootstrap.js",
})

# Forbidden substrings — checked in result/repr/output
FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "backend_base_url", "127.0.0.1", "device_code",
    "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes",
    "fingerprint", "stacktrace", "boot_id", "pid",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRuntimeShellWorkspaceResult:
    """Safe result of runtime shell workspace preparation.

    NEVER contains absolute paths, filenames, exception text, stacktraces,
    or forbidden substrings.
    """

    status: str = STATUS_ERROR
    prepared: bool = False
    source_valid: bool = False
    runtime_dir_ready: bool = False
    files_expected: int = 0
    files_copied: int = 0
    reason: str = REASON_INVALID_ARGS

    def __repr__(self) -> str:
        return (
            f"KsoRuntimeShellWorkspaceResult("
            f"status={self.status!r}, "
            f"prepared={self.prepared}, "
            f"source_valid={self.source_valid}, "
            f"runtime_dir_ready={self.runtime_dir_ready}, "
            f"files_expected={self.files_expected}, "
            f"files_copied={self.files_copied}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _atomic_copy(src: Path, dst: Path) -> bool:
    """Copy src to dst atomically (tmp → rename), returning True on success."""
    try:
        # Create temp file in the destination directory
        fd, tmp_path = tempfile.mkstemp(
            dir=str(dst.parent),
            prefix="." + dst.name + ".",
            suffix=".tmp",
        )
        try:
            # Write via raw fd (avoid double-close with open())
            data = src.read_bytes()
            os.write(fd, data)
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False
        finally:
            os.close(fd)

        # Atomic rename
        os.replace(tmp_path, str(dst))

        # Best-effort fsync directory
        try:
            fd_dir = os.open(str(dst.parent), os.O_RDONLY)
            os.fsync(fd_dir)
            os.close(fd_dir)
        except OSError:
            pass

        return True
    except Exception:
        return False


def _validate_source(source_dir: Path) -> Optional[KsoRuntimeShellWorkspaceResult]:
    """Validate source directory and check required files. Returns error or None."""
    if not source_dir.exists():
        return KsoRuntimeShellWorkspaceResult(
            status=STATUS_ERROR,
            reason=REASON_SOURCE_DIR_MISSING,
            source_valid=False,
        )
    if not source_dir.is_dir():
        return KsoRuntimeShellWorkspaceResult(
            status=STATUS_ERROR,
            reason=REASON_SOURCE_DIR_NOT_DIR,
            source_valid=False,
        )

    # Check required files exist
    missing = []
    for fname in sorted(SHELL_WHITELIST):
        fpath = source_dir / fname
        if not fpath.is_file():
            missing.append(fname)

    if missing:
        return KsoRuntimeShellWorkspaceResult(
            status=STATUS_ERROR,
            reason=REASON_REQUIRED_FILES_MISSING,
            source_valid=False,
            files_expected=len(SHELL_WHITELIST),
        )

    return None  # Source is valid


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def prepare_kso_runtime_shell_workspace(
    source_shell_dir,
    runtime_shell_dir,
) -> KsoRuntimeShellWorkspaceResult:
    """Prepare a runtime copy of the HTML shell workspace.

    Copies whitelist shell files (index.html, styles.css, player.js,
    bootstrap_snapshot.js, bootstrap.js) from the immutable source
    directory to the mutable runtime directory using atomic writes.

    Ignores extra files, subdirectories, and non-whitelist content.
    NEVER modifies the source directory.

    Args:
        source_shell_dir: Path to the immutable shell source directory.
        runtime_shell_dir: Path to the mutable runtime shell directory.

    Returns:
        KsoRuntimeShellWorkspaceResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    try:
        source_dir = Path(source_shell_dir)
    except (TypeError, ValueError):
        return KsoRuntimeShellWorkspaceResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        runtime_dir = Path(runtime_shell_dir)
    except (TypeError, ValueError):
        return KsoRuntimeShellWorkspaceResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Validate source ──────────────────────────────────────────
    err = _validate_source(source_dir)
    if err is not None:
        return err

    # ── Create runtime directory ─────────────────────────────────
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return KsoRuntimeShellWorkspaceResult(
            status=STATUS_ERROR,
            reason=REASON_COPY_FAILED,
            source_valid=True,
            files_expected=len(SHELL_WHITELIST),
        )

    # ── Copy whitelist files atomically ──────────────────────────
    copied = 0
    expected = len(SHELL_WHITELIST)

    for fname in sorted(SHELL_WHITELIST):
        src = source_dir / fname
        dst = runtime_dir / fname

        try:
            if not _atomic_copy(src, dst):
                return KsoRuntimeShellWorkspaceResult(
                    status=STATUS_ERROR,
                    reason=REASON_COPY_FAILED,
                    source_valid=True,
                    files_expected=expected,
                    files_copied=copied,
                )
        except Exception:
            return KsoRuntimeShellWorkspaceResult(
                status=STATUS_ERROR,
                reason=REASON_COPY_FAILED,
                source_valid=True,
                files_expected=expected,
                files_copied=copied,
            )

        copied += 1

    return KsoRuntimeShellWorkspaceResult(
        status=STATUS_OK,
        prepared=True,
        source_valid=True,
        runtime_dir_ready=True,
        files_expected=expected,
        files_copied=copied,
        reason=REASON_PREPARED,
    )


def format_kso_runtime_shell_workspace_result(
    result: KsoRuntimeShellWorkspaceResult,
) -> str:
    """Format result as a safe human-readable string.

    Never contains paths, filenames, exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"prepared: {str(result.prepared).lower()}",
        f"source_valid: {str(result.source_valid).lower()}",
        f"runtime_dir_ready: {str(result.runtime_dir_ready).lower()}",
        f"files_expected: {result.files_expected}",
        f"files_copied: {result.files_copied}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
