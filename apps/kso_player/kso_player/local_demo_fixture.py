"""KSO Player Local Demo Fixture — safe demo root generator.

Creates a minimal demo root with:
  - state/kso_state.json       (idle state from future UKM 4 adapter)
  - manifest/current_manifest.json (1 item: demo image, 5s)
  - media/current/ad_demo.png      (valid 1×1 PNG)
  - media/current/ad_demo.png.sha256

This is NOT production — purely for local smoke demo and tests.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

REASON_READY = "ready"
REASON_WRITE_FAILED = "write_failed"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"

# Manifest schema constants
MANIFEST_ID = "demo-fixture-v1"
MANIFEST_SCHEMA_VERSION = 1

MANIFEST_ITEM_ID = "demo-item-001"  # NOT a UUID — demo fixture marker
DEMO_ORDER = 0
DEMO_CONTENT_TYPE = "image/png"
DEMO_DURATION_MS = 5000
DEMO_FILENAME = "ad_demo.png"

# State constants
DEMO_STATE_VALUE = "idle"
DEMO_STATE_SOURCE = "ukm4_state_adapter"

# Valid 1×1 blue PNG (minimal, no scripts, no external refs)
DEMO_PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1×1
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE,
    0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41, 0x54,  # IDAT
    0x78, 0x9C, 0x62, 0x60, 0x60, 0x60, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x01, 0x27, 0x34, 0x07, 0x1E,
    0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,  # IEND
    0xAE, 0x42, 0x60, 0x82,
])
DEMO_PNG_SHA = hashlib.sha256(DEMO_PNG).hexdigest()

# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoLocalDemoFixtureResult:
    """Safe result of local demo fixture creation.

    NEVER contains paths, filenames, mediaRef values, IDs,
    raw JSON, exception text, stacktraces, or forbidden substrings.
    """

    status: str = STATUS_ERROR
    fixture_ready: bool = False
    state_ready: bool = False
    manifest_ready: bool = False
    media_ready: bool = False
    reason: str = REASON_INVALID_ARGS

    def __repr__(self) -> str:
        return (
            f"KsoLocalDemoFixtureResult("
            f"status={self.status!r}, "
            f"fixture_ready={self.fixture_ready}, "
            f"state_ready={self.state_ready}, "
            f"manifest_ready={self.manifest_ready}, "
            f"media_ready={self.media_ready}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def prepare_kso_local_demo_fixture(
    root,
    now: Optional[datetime] = None,
) -> KsoLocalDemoFixtureResult:
    """Create a minimal demo root with idle state, manifest, and media.

    Writes:
      state/kso_state.json          — idle state from future UKM 4 adapter
      manifest/current_manifest.json — 1 item (image/png, 5s)
      media/current/ad_demo.png      — valid 1×1 blue PNG
      media/current/ad_demo.png.sha256

    If any file already exists, it is NOT overwritten (safe non-destructive).

    Args:
        root: Path to create demo files under.
        now: Optional datetime for test time injection.

    Returns:
        KsoLocalDemoFixtureResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoLocalDemoFixtureResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if now is None:
        now = datetime.now(timezone.utc)

    # ── Step 1: Write state ──────────────────────────────────────
    state_ready = False
    try:
        state_dir = root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "kso_state.json"

        state_obj = {
            "state": DEMO_STATE_VALUE,
            "updated_at_utc": now.isoformat(),
            "source": DEMO_STATE_SOURCE,
        }
        state_file.write_text(json.dumps(state_obj, sort_keys=True))
        state_ready = True
    except Exception:
        return KsoLocalDemoFixtureResult(
            status=STATUS_ERROR,
            reason=REASON_WRITE_FAILED,
            state_ready=state_ready,
        )

    # ── Step 2: Write manifest ───────────────────────────────────
    manifest_ready = False
    try:
        manifest_dir = root / "manifest"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = manifest_dir / "current_manifest.json"

        manifest_obj = {
            "manifest_id": MANIFEST_ID,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "items": [
                {
                    "manifest_item_id": MANIFEST_ITEM_ID,
                    "order": DEMO_ORDER,
                    "content_type": DEMO_CONTENT_TYPE,
                    "duration_ms": DEMO_DURATION_MS,
                    "filename": DEMO_FILENAME,
                    "sha256": DEMO_PNG_SHA,
                }
            ],
        }
        manifest_file.write_text(json.dumps(manifest_obj, sort_keys=True))
        manifest_ready = True
    except Exception:
        return KsoLocalDemoFixtureResult(
            status=STATUS_ERROR,
            reason=REASON_WRITE_FAILED,
            state_ready=state_ready,
            manifest_ready=manifest_ready,
        )

    # ── Step 3: Write media ──────────────────────────────────────
    media_ready = False
    try:
        media_dir = root / "media" / "current"
        media_dir.mkdir(parents=True, exist_ok=True)
        media_file = media_dir / DEMO_FILENAME
        sha_file = media_dir / (DEMO_FILENAME + ".sha256")

        media_file.write_bytes(DEMO_PNG)
        sha_file.write_text(DEMO_PNG_SHA + "\n")
        media_ready = True
    except Exception:
        return KsoLocalDemoFixtureResult(
            status=STATUS_ERROR,
            reason=REASON_WRITE_FAILED,
            state_ready=state_ready,
            manifest_ready=manifest_ready,
            media_ready=media_ready,
        )

    return KsoLocalDemoFixtureResult(
        status=STATUS_OK,
        fixture_ready=True,
        state_ready=True,
        manifest_ready=True,
        media_ready=True,
        reason=REASON_READY,
    )


def format_kso_local_demo_fixture_result(
    result: KsoLocalDemoFixtureResult,
) -> str:
    """Format result as a safe human-readable string.

    Never contains paths, filenames, mediaRef, IDs, raw JSON,
    exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"fixture_ready: {str(result.fixture_ready).lower()}",
        f"state_ready: {str(result.state_ready).lower()}",
        f"manifest_ready: {str(result.manifest_ready).lower()}",
        f"media_ready: {str(result.media_ready).lower()}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
