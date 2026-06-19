"""KSO Sidecar Run Cycle — Manifest Step.

Fetches manifest from backend via ManifestClient and writes to local store.
Only called in backend_enabled mode with a valid TokenState.
Manifest retry is NOT connected at this step.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import time as _time
from dataclasses import dataclass
from typing import Optional

from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.manifest_client import ManifestClient, ManifestSnapshot
from kso_sidecar_agent.manifest_store import write_current_manifest
from kso_sidecar_agent.run_cycle import (
    RunCycleStepResult,
    _check_forbidden,
    _redact_forbidden,
    _validate_safe_details,
)
from kso_sidecar_agent.token_state import TokenState


# ── Result ────────────────────────────────────────────────────────────

@dataclass
class CycleManifestResult:
    """Result of manifest sync step in a run cycle. No secrets, no full manifest."""

    step: RunCycleStepResult
    manifest_status: str = "skipped"  # updated | not_modified | no_manifest | error | skipped
    manifest_version_id: Optional[str] = None
    manifest_hash_short: Optional[str] = None
    items_count: int = 0
    write_status: Optional[str] = None  # written | not_modified | no_manifest | error

    def __post_init__(self) -> None:
        _check_forbidden(self.manifest_status, "manifest_status")
        if self.manifest_version_id:
            _check_forbidden(self.manifest_version_id, "manifest_version_id")
        if self.manifest_hash_short:
            _check_forbidden(self.manifest_hash_short, "manifest_hash_short")
        if self.write_status:
            _check_forbidden(self.write_status, "write_status")


# ── Safe helpers ─────────────────────────────────────────────────────

def _hash_short(sha256: Optional[str]) -> Optional[str]:
    """Return first 12 chars of sha256 or None."""
    if isinstance(sha256, str) and len(sha256) >= 12:
        return sha256[:12]
    return sha256 or None


# ── Main ─────────────────────────────────────────────────────────────

def sync_manifest_for_cycle(
    root,
    token_state: TokenState,
    now: Optional[float] = None,
    http_client: Optional[SafeHttpClient] = None,
) -> CycleManifestResult:
    """Fetch current manifest from backend and write to local store.

    Args:
        root: Agent root path.
        token_state: Valid TokenState.
        now: Current timestamp.
        http_client: SafeHttpClient (builds from config if None).

    Returns:
        CycleManifestResult with safe step and manifest status.
    """
    if now is None:
        now = _time.time()

    # ── Validate token ────────────────────────────────────────────
    try:
        if not token_state.is_valid(now=now):
            return CycleManifestResult(
                step=RunCycleStepResult(
                    name="manifest",
                    status="error",
                    fatal=False,
                    message="Token expired before manifest fetch",
                ),
                manifest_status="error",
            )
    except Exception as e:
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="error",
                fatal=False,
                message=f"Token validation error — {_redact_forbidden(str(e))}",
            ),
            manifest_status="error",
        )

    # ── Build HTTP client if not provided ─────────────────────────
    if http_client is None:
        try:
            from kso_sidecar_agent import local_config as _lc
            cfg = _lc.read_config(root)
            backend_base_url = cfg.get("backend_base_url", "")
            if not backend_base_url:
                return CycleManifestResult(
                    step=RunCycleStepResult(
                        name="manifest", status="error", fatal=False,
                        message="Config missing backend_base_url",
                    ),
                    manifest_status="error",
                )
            http_config = HttpClientConfig(
                base_url=backend_base_url,
                timeout_sec=cfg.get("request_timeout_sec", 10),
                tls_verify=cfg.get("tls_verify", True),
            )
            http_client = SafeHttpClient(http_config)
        except Exception as e:
            return CycleManifestResult(
                step=RunCycleStepResult(
                    name="manifest", status="error", fatal=False,
                    message=f"Config error — {_redact_forbidden(str(e))}",
                ),
                manifest_status="error",
            )

    # ── Fetch manifest ────────────────────────────────────────────
    manifest_client = ManifestClient(http_client=http_client)

    try:
        snapshot: ManifestSnapshot = manifest_client.fetch_current(token_state, now=now)
    except HttpClientError as e:
        status_code = getattr(e, "status_code", 0)
        retryable = getattr(e, "retryable", False)
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="error",
                fatal=False,
                retryable=retryable,
                message=f"Manifest fetch failed ({status_code}) — {_redact_forbidden(str(e))}",
                safe_details={"status_code": status_code},
            ),
            manifest_status="error",
        )
    except (ValueError, RuntimeError) as e:
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="error",
                fatal=False,
                message=f"Manifest fetch failed — {_redact_forbidden(str(e))}",
            ),
            manifest_status="error",
        )

    # ── Handle not_modified / no_manifest ─────────────────────────
    snap_status = getattr(snapshot, "status", "served")

    if snap_status == "not_modified":
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="ok",
                message="Manifest not modified, local file unchanged",
                safe_details={"not_modified": True},
            ),
            manifest_status="not_modified",
            manifest_version_id=getattr(snapshot, "manifest_version_id", None),
            write_status="not_modified",
        )

    if snap_status == "no_manifest":
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="ok",
                message="No manifest available, local file unchanged",
                safe_details={"no_manifest": True},
            ),
            manifest_status="no_manifest",
            write_status="no_manifest",
        )

    # ── Write to local store (served) ─────────────────────────────
    try:
        write_result = write_current_manifest(root, snapshot)
    except (ValueError, RuntimeError) as e:
        # Invalid manifest (forbidden key, sha256, path traversal)
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="error",
                fatal=False,
                message=f"Manifest rejected — {_redact_forbidden(str(e))}",
            ),
            manifest_status="error",
        )
    except OSError as e:
        return CycleManifestResult(
            step=RunCycleStepResult(
                name="manifest",
                status="error",
                fatal=False,
                message=f"Manifest write failed — {_redact_forbidden(str(e))}",
            ),
            manifest_status="error",
        )

    # ── Build safe result ─────────────────────────────────────────
    ws = write_result.get("status", "written")
    mvid = write_result.get("manifest_version_id", "")
    items_count = write_result.get("items_count", 0)
    mhash = getattr(snapshot, "manifest_hash", None)

    manifest_status = ws if ws in ("written", "not_modified", "no_manifest") else "error"
    # Map "written" → "updated" for consistency with _cycle.manifest_status
    if manifest_status == "written":
        manifest_status = "updated"

    return CycleManifestResult(
        step=RunCycleStepResult(
            name="manifest",
            status="ok",
            safe_details={
                "items_count": items_count,
                "manifest_hash_short": _hash_short(mhash) or "",
            },
        ),
        manifest_status=manifest_status,
        manifest_version_id=mvid if mvid else None,
        manifest_hash_short=_hash_short(mhash),
        items_count=items_count,
        write_status=ws,
    )
