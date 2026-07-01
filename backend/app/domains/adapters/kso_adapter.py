"""
E.1 — KSO Adapter: Dry-Run Payload Builder.

Implements AdapterContract for channel_code="kso".
Builds KSO-safe dry-run payload from OrchestratorContext.

No DB writes. No API. No publication/manifest/GeneratedManifest imports.
No KsoPlacement dependency. No Device Gateway calls.
No secrets, no signed URLs, no raw credentials.
"""
from typing import Any

from app.domains.orchestrator.contracts import (
    AdapterContract,
    AdapterPayloadDraft,
    AdapterSimulationResult,
    OrchestratorContext,
    DeviceInfo,
    SurfaceInfo,
)

# ── KSO-specific constants ──────────────────────────────────────────────

KSO_CHANNEL_CODE = "kso"
KSO_ADAPTER_NAME = "kso"
ALLOWED_PROOF_TYPES = frozenset({
    "real_playback", "idle_impression", "template_applied",
    "label_ack", "controller_ack", "delivery_ack",
})
FORBIDDEN_SECRET_WORDS = frozenset({
    "password", "secret", "token", "access_key", "private_key",
    "authorization", "bearer", "signed_url", "credential",
    "access_token", "refresh_token", "api_key",
})


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _pick_first_device(context: OrchestratorContext) -> DeviceInfo | None:
    """Pick the first device from context, or None."""
    if context.devices:
        return context.devices[0]
    return None


def _pick_surface(device: DeviceInfo) -> SurfaceInfo | None:
    """Pick the first surface from a device, or None."""
    if device.surfaces:
        return device.surfaces[0]
    return None


def _check_secret_words(value: str) -> list[str]:
    """Check a string for forbidden secret words. Returns error messages."""
    errors: list[str] = []
    lower = value.lower()
    for word in FORBIDDEN_SECRET_WORDS:
        if word in lower:
            errors.append(f"Forbidden word '{word}' found in value")
    return errors


def _recursive_check_forbidden(payload: dict[str, Any], path: str = "") -> list[str]:
    """Recursively check payload dict for forbidden secret words in keys and values."""
    errors: list[str] = []
    for key, value in payload.items():
        current = f"{path}.{key}" if path else key
        # Check keys
        lower_key = key.lower()
        for fw in FORBIDDEN_SECRET_WORDS:
            if fw in lower_key:
                errors.append(f"Forbidden key '{key}' at '{current}'")
        # Check string values
        if isinstance(value, str):
            for fw in FORBIDDEN_SECRET_WORDS:
                if fw in value.lower():
                    errors.append(f"Forbidden value for '{fw}' at '{current}'")
        elif isinstance(value, dict):
            errors.extend(_recursive_check_forbidden(value, current))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    errors.extend(_recursive_check_forbidden(item, f"{current}[{i}]"))
                elif isinstance(item, str):
                    for fw in FORBIDDEN_SECRET_WORDS:
                        if fw in item.lower():
                            errors.append(f"Forbidden '{fw}' at '{current}[{i}]'")
    return errors


# ═══════════════════════════════════════════════════════════════════════════
# KsoAdapter
# ═══════════════════════════════════════════════════════════════════════════

class KsoAdapter(AdapterContract):
    """KSO dry-run adapter — builds KSO-safe payload, no production writes."""

    @property
    def adapter_name(self) -> str:
        return KSO_ADAPTER_NAME

    @property
    def channel_code(self) -> str:
        return KSO_CHANNEL_CODE

    def supports(
        self, channel_code: str, capability_profile: dict[str, Any] | None = None,
    ) -> bool:
        """KSO adapter supports only channel_code='kso'."""
        return channel_code == KSO_CHANNEL_CODE

    async def build_payload(
        self, context: OrchestratorContext,
    ) -> AdapterPayloadDraft:
        """Build KSO-safe dry-run payload from orchestrator context.

        Returns structured AdapterPayloadDraft with warnings for missing data.
        Does NOT raise exceptions — all issues go into warnings/errors.
        """
        warnings: list[str] = []
        errors: list[str] = []

        # Validate required fields
        if not context.placement_code:
            errors.append("Missing placement_code in orchestrator context")

        device = _pick_first_device(context)
        if not device:
            errors.append("No devices found in orchestrator context")
        elif not device.device_code:
            errors.append("Missing device_code for device")

        surface = _pick_surface(device) if device else None

        # ── Build payload ──────────────────────────────────────────
        payload: dict[str, Any] = {
            "adapter_name": KSO_ADAPTER_NAME,
            "channel_code": KSO_CHANNEL_CODE,
            "dry_run": True,
        }

        if context.placement_code:
            payload["placement_code"] = context.placement_code

        if device and device.device_code:
            payload["device_code"] = device.device_code

        if context.campaign_id:
            payload["campaign_id"] = context.campaign_id

        if device and device.store_id:
            payload["store_id"] = device.store_id

        # ── Resolution / orientation from capability ───────────────
        if surface:
            if surface.resolution:
                parts = surface.resolution.lower().split("x")
                if len(parts) == 2:
                    try:
                        payload["resolution_width"] = int(parts[0])
                        payload["resolution_height"] = int(parts[1])
                    except ValueError:
                        warnings.append(f"Cannot parse resolution: {surface.resolution}")
                else:
                    payload["resolution"] = surface.resolution
            if surface.orientation:
                payload["orientation"] = surface.orientation
            if surface.proof_type:
                payload["proof_type"] = surface.proof_type

        if not payload.get("proof_type"):
            warnings.append("No proof_type in capability profile")
        if "resolution_width" not in payload and "resolution" not in payload:
            warnings.append("No resolution information available")

        # ── Schedule ───────────────────────────────────────────────
        schedule: dict[str, Any] = {}
        if context.start_date:
            schedule["date_from"] = context.start_date
        if context.end_date:
            schedule["date_to"] = context.end_date
        if schedule:
            payload["schedule"] = schedule
        else:
            warnings.append("No schedule (start_date/end_date) in context")

        # ── Items (creatives) ──────────────────────────────────────
        items: list[dict[str, Any]] = []
        if context.creative_codes:
            for idx, code in enumerate(context.creative_codes):
                items.append({
                    "creative_code": code,
                    "slot_order": idx,
                    "media_type": "unknown",  # resolved in E.2+
                })
        if items:
            payload["items"] = items
        else:
            warnings.append("No creative codes in orchestrator context")

        # ── Resolution warning ─────────────────────────────────────
        if surface and not surface.resolution:
            warnings.append("No resolution in surface capability profile")

        # Build errors list from warnings if critical
        if errors:
            return AdapterPayloadDraft(
                channel_code=KSO_CHANNEL_CODE,
                adapter_name=KSO_ADAPTER_NAME,
                payload=payload,
                warnings=errors + warnings,
            )

        return AdapterPayloadDraft(
            channel_code=KSO_CHANNEL_CODE,
            adapter_name=KSO_ADAPTER_NAME,
            payload=payload,
            warnings=warnings,
        )

    def validate_payload(self, payload: dict[str, Any]) -> list[str]:
        """Validate KSO payload structure. Returns list of error messages.

        Checks:
        - adapter_name == 'kso' and channel_code == 'kso'
        - dry_run == True
        - required fields: device_code, placement_code
        - no forbidden secret words
        - valid proof_type if present
        - valid resolution if present
        - positive duration_seconds if present
        """
        errors: list[str] = []

        # ── Identity checks ────────────────────────────────────────
        if payload.get("adapter_name") != KSO_ADAPTER_NAME:
            errors.append(f"adapter_name must be '{KSO_ADAPTER_NAME}'")
        if payload.get("channel_code") != KSO_CHANNEL_CODE:
            errors.append(f"channel_code must be '{KSO_CHANNEL_CODE}'")
        if payload.get("dry_run") is not True:
            errors.append("dry_run must be True for KSO adapter")

        # ── Required fields ────────────────────────────────────────
        if not payload.get("device_code"):
            errors.append("Missing required field: device_code")
        if not payload.get("placement_code"):
            errors.append("Missing required field: placement_code")

        # ── No secrets ─────────────────────────────────────────────
        secret_errors = _recursive_check_forbidden(payload)
        errors.extend(secret_errors)

        # ── proof_type validation ──────────────────────────────────
        pt = payload.get("proof_type")
        if pt and pt not in ALLOWED_PROOF_TYPES:
            errors.append(
                f"Invalid proof_type '{pt}'. Allowed: {', '.join(sorted(ALLOWED_PROOF_TYPES))}"
            )

        # ── Resolution validation ──────────────────────────────────
        rw = payload.get("resolution_width")
        rh = payload.get("resolution_height")
        if rw is not None and (not isinstance(rw, int) or rw <= 0):
            errors.append(f"resolution_width must be positive integer, got {rw}")
        if rh is not None and (not isinstance(rh, int) or rh <= 0):
            errors.append(f"resolution_height must be positive integer, got {rh}")

        # ── Duration validation per item ───────────────────────────
        items = payload.get("items", [])
        if isinstance(items, list):
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    dur = item.get("duration_seconds")
                    if dur is not None and (not isinstance(dur, (int, float)) or dur <= 0):
                        errors.append(
                            f"items[{idx}].duration_seconds must be positive, got {dur}"
                        )

        return errors

    async def simulate_delivery(
        self, payload: dict[str, Any],
    ) -> AdapterSimulationResult:
        """Dry-run simulation — does NOT contact devices or write to DB.

        Validates payload and returns structured result.
        """
        validation_errors = self.validate_payload(payload)

        if validation_errors:
            return AdapterSimulationResult(
                ok=False,
                adapter_name=KSO_ADAPTER_NAME,
                channel_code=KSO_CHANNEL_CODE,
                errors=validation_errors,
                details={"dry_run": True, "items_count": len(payload.get("items", []))},
            )

        return AdapterSimulationResult(
            ok=True,
            adapter_name=KSO_ADAPTER_NAME,
            channel_code=KSO_CHANNEL_CODE,
            details={
                "dry_run": True,
                "device_code": payload.get("device_code"),
                "placement_code": payload.get("placement_code"),
                "items_count": len(payload.get("items", [])),
            },
        )


# ── Auto-register ───────────────────────────────────────────────────────

def _register() -> None:
    from app.domains.adapters.registry import register_adapter
    register_adapter(KsoAdapter())


_register()
