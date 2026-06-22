"""
Hierarchy domain: KSO device registry models (Step 37.1).

KsoDevice — KSO-specific device registration record.
Links to stores. Contains KSO-constrained display parameters.

Forbidden fields (NEVER stored):
  - IP, MAC, hostname, serial number
  - device_secret / client_secret raw
  - filesystem paths
  - real store IDs / external IDs
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

# KSO hardware constraints — fixed for Sherman-J 5.1 / UKM 4 kiosk
KSO_SCREEN_WIDTH = 1920
KSO_SCREEN_HEIGHT = 1080
KSO_AD_ZONE_WIDTH = 1440
KSO_AD_ZONE_HEIGHT = 1080
KSO_CHANNEL = "kso"

# Valid device statuses
DEVICE_STATUSES = frozenset({
    "active", "inactive", "blocked", "maintenance", "lost",
})


class KsoDevice(Base):
    """KSO-specific device registered in the hierarchy.

    Links to a store. Contains display geometry and version info.
    Does NOT store secrets, IP, MAC, hostname, or serial.
    """

    __tablename__ = "kso_devices"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_code = Column(
        String(64), unique=True, nullable=False,
    )
    display_name = Column(String(255), nullable=True)
    status = Column(
        String(20), nullable=False, server_default="inactive",
    )
    channel = Column(
        String(20), nullable=False, server_default=KSO_CHANNEL,
    )

    # Version tracking
    runtime_version = Column(String(32), nullable=True)
    player_version = Column(String(32), nullable=True)
    sidecar_version = Column(String(32), nullable=True)
    state_adapter_version = Column(String(32), nullable=True)
    manifest_version = Column(String(64), nullable=True)

    # Display geometry — KSO-constrained defaults
    screen_width = Column(
        Integer, nullable=False, server_default=str(KSO_SCREEN_WIDTH),
    )
    screen_height = Column(
        Integer, nullable=False, server_default=str(KSO_SCREEN_HEIGHT),
    )
    ad_zone_width = Column(
        Integer, nullable=False, server_default=str(KSO_AD_ZONE_WIDTH),
    )
    ad_zone_height = Column(
        Integer, nullable=False, server_default=str(KSO_AD_ZONE_HEIGHT),
    )

    # Metadata
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
