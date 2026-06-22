"""Proof-of-Play KSO schemas — test KSO technical validation.

Safe request/response models.  Never expose: raw UUIDs, backend URLs,
tokens, file_path, sha256, storage_ref, minio keys, device/client secrets.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════
# Request
# ══════════════════════════════════════════════════════════════════════

class KsoPoPIngestRequest(BaseModel):
    """PoP event from sidecar via TEST_ONLY endpoint.

    manifest_version_id and manifest_hash are optional — sidecar
    may or may not include them.  When present they are verified
    against the latest published manifest; when absent the chain
    proceeds without that check (behaviour tracked in tests).
    """

    event_code: str = Field(min_length=1, max_length=128)
    manifest_version_id: Optional[str] = Field(default=None, max_length=128)
    manifest_hash: Optional[str] = Field(default=None, max_length=128)
    media_ref: str = Field(min_length=1, max_length=128)
    event_type: str = Field(default="impression", max_length=32)
    played_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)


# ══════════════════════════════════════════════════════════════════════
# Response (safe — no UUIDs, no secrets)
# ══════════════════════════════════════════════════════════════════════

class KsoPoPIngestResponse(BaseModel):
    """Safe response after PoP ingest.

    Deliberately OMITS: id, manifest_version_id, manifest_hash,
    backend_url, tokens, file_path, sha256, storage_ref, minio,
    device_secret, client_secret.
    """

    status: str
    event_code: str
    device_code: str
    placement_code: str
    campaign_code: str
    creative_code: str
    received_at: datetime
