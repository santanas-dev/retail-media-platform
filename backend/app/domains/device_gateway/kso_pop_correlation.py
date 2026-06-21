"""KSO PoP Server-Side Correlation Core.

Given a KSO device + PoP event (with selected_order, selected_content_type),
finds the matching published manifest item and returns internal IDs
for populating ProofOfPlayEvent FK fields.

This is a BACKEND-ONLY module — never exposed to player or sidecar.
Never carries raw IDs, paths, hashes, or secrets in public output.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.device_gateway import models as gw_models
from app.domains.publications.kso_manifest_projection import (
    ALLOWED_CONTENT_TYPES,
    KSO_CHANNEL_CODE,
    ManifestSourceItem,
    _validate_content_type,
    _validate_duration_ms,
)
from app.domains.publications.models import (
    ManifestItem,
    ManifestVersion,
    PublicationBatch,
    PublicationTarget,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MAX_ITEMS = 1000


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════


@dataclass
class KsoPopCorrelationResult:
    """Result of server-side KSO PoP correlation.

    Public fields — safe for logging/audit. Internal IDs are repr=False.
    """

    correlated: bool = False
    reason: Optional[str] = None

    # Internal IDs — never exposed in API responses
    _manifest_item_id: Optional[UUID] = field(default=None, repr=False)
    _manifest_version_id: Optional[UUID] = field(default=None, repr=False)
    _publication_target_id: Optional[UUID] = field(default=None, repr=False)
    _schedule_item_id: Optional[UUID] = field(default=None, repr=False)
    _campaign_id: Optional[UUID] = field(default=None, repr=False)
    _campaign_rendition_id: Optional[UUID] = field(default=None, repr=False)
    _rendition_id: Optional[UUID] = field(default=None, repr=False)
    _creative_version_id: Optional[UUID] = field(default=None, repr=False)

    # Safe public aggregates
    items_total: int = 0
    items_filtered: int = 0
    matched_index: Optional[int] = None

    def __repr__(self) -> str:
        return (
            f"KsoPopCorrelationResult("
            f"correlated={self.correlated}, "
            f"reason={self.reason!r}, "
            f"items_total={self.items_total}, "
            f"items_filtered={self.items_filtered}, "
            f"matched_index={self.matched_index})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _filter_source_items(
    source_items: List[ManifestSourceItem],
    now: Optional[datetime] = None,
) -> List[ManifestSourceItem]:
    """Apply KSO projection filters to source items.

    Same filtering logic as build_kso_safe_manifest_projection():
    - channel_code == "kso"
    - campaign_status == "approved"
    - creative_status == "approved"
    - rendition_status == "valid"
    - publication_status == "published"
    - device_status in (pending, active, lost)
    - store_is_active == True
    - content_type in allowlist
    - valid_to > now (if set)
    - valid_from <= now (if set)
    - duration_ms in safe range
    """
    if now is None:
        now = datetime.now(timezone.utc)

    filtered: List[ManifestSourceItem] = []

    for src in source_items:
        if not isinstance(src, ManifestSourceItem):
            continue

        if src.channel_code.strip().lower() != KSO_CHANNEL_CODE:
            continue

        if src.campaign_status.strip().lower() != "approved":
            continue

        if src.creative_status.strip().lower() != "approved":
            continue

        if src.rendition_status.strip().lower() != "valid":
            continue

        if src.publication_status.strip().lower() != "published":
            continue

        dev_status = src.device_status.strip().lower()
        if dev_status not in ("pending", "active", "lost"):
            continue

        if not src.store_is_active:
            continue

        if not _validate_content_type(src.content_type):
            continue

        now_ref = src.now or now
        if src.valid_to is not None and src.valid_to < now_ref:
            continue
        if src.valid_from is not None and src.valid_from > now_ref:
            continue

        filtered.append(src)

        if len(filtered) >= MAX_ITEMS:
            break

    # Sort by (slot_order, content_type) — same as projection
    filtered.sort(key=lambda it: (it.slot_order, it.content_type))

    return filtered


# ══════════════════════════════════════════════════════════════════════
# Core API
# ══════════════════════════════════════════════════════════════════════


async def correlate_kso_pop_event(
    db: AsyncSession,
    device: gw_models.GatewayDevice,
    selected_order: Optional[int],
    selected_content_type: Optional[str],
    now: Optional[datetime] = None,
) -> KsoPopCorrelationResult:
    """Server-side correlate a KSO PoP event with a published manifest item.

    This is the CORE correlation function. It:
    1. Verifies the device is KSO channel
    2. Finds the current published manifest for the device
    3. Collects source items with internal IDs
    4. Applies KSO projection filters
    5. Looks up the item at index = selected_order
    6. Validates content_type matches
    7. Returns internal IDs for FK population

    Args:
        db: Active async DB session.
        device: The authenticated gateway device.
        selected_order: Slot order from the PoP event (0-based index).
        selected_content_type: Content type from PoP event.
        now: Optional reference timestamp for validity checks.

    Returns:
        KsoPopCorrelationResult — always safe, never raises.
        If correlated=True, internal IDs are populated.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # ── 0. Guard: KSO channel only ──────────────────────────────────
    from app.domains.channels.models import Channel

    ch_result = await db.execute(
        select(Channel.code).where(Channel.id == device.channel_id)
    )
    ch_code = ch_result.scalar_one_or_none()
    if ch_code != KSO_CHANNEL_CODE:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="not_kso_channel",
        )

    # ── 1. selected_order is required for correlation ──────────────
    if selected_order is None:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="selected_order_missing",
        )

    if not isinstance(selected_order, int) or selected_order < 0:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="selected_order_invalid",
        )

    # ── 2. Find matching publication targets for the device ────────
    from app.domains.device_gateway.service import _match_publication_targets

    target_ids = await _match_publication_targets(device, db)
    if not target_ids:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="no_matching_publication_target",
        )

    # ── 3. Find current published manifest ─────────────────────────
    result = await db.execute(
        select(ManifestVersion)
        .join(PublicationTarget, ManifestVersion.publication_target_id == PublicationTarget.id)
        .join(PublicationBatch, ManifestVersion.publication_batch_id == PublicationBatch.id)
        .where(
            ManifestVersion.status == "published",
            PublicationTarget.status == "published",
            PublicationBatch.status == "published",
            PublicationTarget.id.in_(target_ids),
        )
        .order_by(ManifestVersion.published_at.desc().nullslast())
        .order_by(ManifestVersion.manifest_version.desc())
        .limit(50)  # Scan enough to find one with items
    )
    manifest_versions = result.scalars().all()

    manifest = None
    for mv in manifest_versions:
        item_count_result = await db.execute(
            select(ManifestItem).where(ManifestItem.manifest_version_id == mv.id).limit(1)
        )
        if item_count_result.scalar_one_or_none():
            manifest = mv
            break

    if not manifest:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="no_published_manifest",
        )

    # ── 4. Collect source items with internal IDs ──────────────────
    from app.domains.device_gateway.service import _collect_kso_source_items

    source_items = await _collect_kso_source_items(manifest, db)

    items_total = len(source_items)
    if items_total == 0:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="manifest_empty",
            items_total=0,
        )

    # ── 5. Apply projection filters ────────────────────────────────
    filtered = _filter_source_items(source_items, now=now)
    items_filtered = len(filtered)

    if items_filtered == 0:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="all_items_filtered_out",
            items_total=items_total,
            items_filtered=0,
        )

    # ── 6. Look up by index ────────────────────────────────────────
    if selected_order >= items_filtered:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="selected_order_out_of_range",
            items_total=items_total,
            items_filtered=items_filtered,
        )

    matched_src = filtered[selected_order]

    # ── 7. Content type validation ─────────────────────────────────
    if selected_content_type:
        ct_clean = selected_content_type.strip().lower()
        src_ct = matched_src.content_type.strip().lower()
        if ct_clean != src_ct:
            return KsoPopCorrelationResult(
                correlated=False,
                reason="content_type_mismatch",
                items_total=items_total,
                items_filtered=items_filtered,
                matched_index=selected_order,
            )

    # ── 8. Build correlated result with internal IDs ───────────────
    def _to_uuid(val: Optional[str]) -> Optional[UUID]:
        if val:
            try:
                return UUID(val)
            except (ValueError, TypeError):
                return None
        return None

    mi_id = _to_uuid(matched_src._internal_manifest_item_id)
    if not mi_id:
        return KsoPopCorrelationResult(
            correlated=False,
            reason="manifest_item_id_missing_in_source",
            items_total=items_total,
            items_filtered=items_filtered,
            matched_index=selected_order,
        )

    return KsoPopCorrelationResult(
        correlated=True,
        items_total=items_total,
        items_filtered=items_filtered,
        matched_index=selected_order,
        _manifest_item_id=mi_id,
        _manifest_version_id=_to_uuid(matched_src._internal_manifest_version_id),
        _publication_target_id=_to_uuid(matched_src._internal_publication_target_id),
        _schedule_item_id=_to_uuid(matched_src._internal_schedule_item_id),
        _campaign_id=_to_uuid(matched_src._internal_campaign_id),
        _campaign_rendition_id=_to_uuid(matched_src._internal_campaign_rendition_id),
        _rendition_id=_to_uuid(matched_src._internal_rendition_id),
        _creative_version_id=_to_uuid(matched_src._internal_creative_version_id),
    )
