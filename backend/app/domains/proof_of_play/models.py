"""Proof-of-Play KSO models — test KSO technical validation bridge table.

KsoProofOfPlayEvent stores PoP events correlated through safe codes
(device_code, placement_code, campaign_code, creative_code) — NOT raw UUIDs.
This is NOT the enterprise PoP model.  Enterprise PoP is:
  device_gateway.models.ProofOfPlayEvent + ProofOfPlayBatch.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base

from app.core.database import Base


def _pk():
    return uuid4()


def _now():
    return datetime.now(timezone.utc)


class KsoProofOfPlayEvent(Base):
    """Test KSO PoP event — minimal safe-code correlation bridge.

    Links a PoP event to its placement chain via stable codes.
    Never stores: receipt, payment, fiscal, customer, phone, email,
    card, pan, sha256, storage_ref, file_path, tokens, secrets.
    """

    __tablename__ = "kso_proof_of_play_events"

    # ── Primary / identity ────────────────────────────────────────
    id = Column(PGUUID, primary_key=True, default=_pk)
    event_code = Column(String(128), unique=True, nullable=False, index=True)

    # ── Safe-code correlation (FK on stable codes, not UUIDs) ────
    device_code = Column(
        String(64),
        ForeignKey("kso_devices.device_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    placement_code = Column(
        String(64),
        ForeignKey("kso_placements.placement_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_code = Column(
        String(64),
        ForeignKey("campaigns.campaign_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creative_code = Column(
        String(64),
        ForeignKey("creatives.creative_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Manifest reference (safe codes) ──────────────────────────
    manifest_code = Column(
        String(64),
        ForeignKey("generated_manifests.manifest_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    media_ref = Column(String(128), nullable=False)

    # ── Event data ───────────────────────────────────────────────
    event_type = Column(String(32), nullable=False, default="impression")
    status = Column(String(32), nullable=False, default="accepted", index=True)
    played_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
