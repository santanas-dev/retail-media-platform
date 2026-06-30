"""
B.5.2 — Universal Manifest Builder: targeted tests.

Tests for universal_builder.py functions.
No DB writes, no API, no side effects.
"""

import pytest
from datetime import datetime, timezone

from app.domains.manifests.universal_schema import (
    UniversalManifestV1,
    ManifestContentItem,
    ManifestIssue,
    ManifestSignatureStatus,
    ManifestStatus,
)
from app.domains.manifests.universal_builder import (
    build_universal_manifest_from_draft,
    validate_universal_manifest,
    _now,
)
from app.domains.orchestrator.contracts import (
    OrchestratorContext,
    AdapterPayloadDraft,
    DeviceInfo,
    SurfaceInfo,
)


def _make_context(**overrides) -> OrchestratorContext:
    """Build a minimal OrchestratorContext for testing."""
    kwargs = {
        "placement_id": "11111111-1111-1111-1111-111111111111",
        "placement_code": "PLC-TEST-001",
        "campaign_id": "22222222-2222-2222-2222-222222222222",
        "channel_code": "mock",
        "channel_name": "Mock Channel",
        "devices": [
            DeviceInfo(
                device_id="dev-001",
                device_code="DEV-001",
                store_id="store-042",
                status="active",
                surfaces=[
                    SurfaceInfo(
                        surface_id="DS-MAIN",
                        resolution="768x1024",
                        orientation="portrait",
                        formats=["image/png", "image/jpeg", "video/mp4"],
                        proof_type="real_playback",
                        max_file_size=10485760,
                        max_duration=86400000,
                        interactive=False,
                    ),
                ],
            ),
        ],
    }
    kwargs.update(overrides)
    return OrchestratorContext(**kwargs)


def _make_payload(**overrides) -> AdapterPayloadDraft:
    """Build a minimal AdapterPayloadDraft for testing."""
    kwargs = {
        "channel_code": "mock",
        "adapter_name": "mock_adapter",
        "payload": {"slot_order": 0},
    }
    kwargs.update(overrides)
    return AdapterPayloadDraft(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# Builder basic tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBuilderBasic:
    """Basic builder construction."""

    def test_build_from_draft_success(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert isinstance(manifest, UniversalManifestV1)

    def test_manifest_version_is_1_0(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.manifest_version == "1.0"

    def test_signature_status_is_unsigned(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.security.signature_status == ManifestSignatureStatus.UNSIGNED

    def test_metadata_dry_run_is_true(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.metadata.dry_run is True

    def test_status_is_draft(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.status == ManifestStatus.DRAFT

    def test_manifest_id_generated(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.manifest_id is not None
        assert manifest.manifest_id.startswith("m-")

    def test_generated_at_set(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.generated_at is not None
        assert isinstance(manifest.generated_at, datetime)


# ═══════════════════════════════════════════════════════════════════════════
# Mapping tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMappingCampaign:
    """Campaign block mapping."""

    def test_maps_campaign_block(self):
        ctx = _make_context(placement_code="CAMP-SUMMER")
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.campaign is not None
        assert manifest.campaign.campaign_code == "CAMP-SUMMER"

    def test_maps_campaign_id(self):
        ctx = _make_context(campaign_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.campaign.campaign_id is not None


class TestMappingPlacement:
    """Placement block mapping."""

    def test_maps_placement_block(self):
        ctx = _make_context(placement_code="PLC-MAIN")
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.placement.placement_code == "PLC-MAIN"

    def test_maps_channel_code(self):
        ctx = _make_context(channel_code="android_tv")
        payload = _make_payload(channel_code="android_tv")
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.placement.channel_code == "android_tv"

    def test_maps_dates(self):
        ctx = _make_context(start_date="2026-07-01", end_date="2026-07-31")
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.placement.start_date == "2026-07-01"
        assert manifest.placement.end_date == "2026-07-31"


class TestMappingTargets:
    """Targets list mapping."""

    def test_maps_targets_list(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert len(manifest.targets) > 0
        assert manifest.targets[0].physical_device_code == "DEV-001"

    def test_targets_channel_agnostic(self):
        """Targets work for any channel, not just KSO."""
        for ch in ("kso", "esl", "led_shelf"):
            ctx = _make_context(channel_code=ch)
            payload = _make_payload(channel_code=ch)
            manifest = build_universal_manifest_from_draft(ctx, payload)
            assert len(manifest.targets) > 0

    def test_no_devices_returns_placement_target(self):
        """When no devices resolved, builder adds a minimal placement-level target."""
        ctx = _make_context(devices=[])
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert len(manifest.targets) == 1
        assert manifest.targets[0].target_type == "placement"


class TestMappingCapability:
    """Capability block mapping."""

    def test_maps_capability_block(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.capability is not None
        assert manifest.capability.proof_type == "real_playback"

    def test_maps_resolution_and_formats(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.capability is not None
        assert manifest.capability.resolution == "768x1024"
        assert "image/png" in manifest.capability.supported_formats

    def test_no_proof_type_no_capability(self):
        ctx = _make_context(devices=[
            DeviceInfo(
                device_id="dev-x",
                surfaces=[
                    SurfaceInfo(surface_id="DS-X", proof_type=None),
                ],
            ),
        ])
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        # No proof_type → builder skips capability
        assert manifest.capability is None


class TestMappingAdapter:
    """Adapter payload mapping."""

    def test_maps_adapter_payload_block(self):
        ctx = _make_context()
        payload = _make_payload(
            channel_code="mock",
            adapter_name="mock_adapter",
            payload={"key": "value"},
        )
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.adapter_payload is not None
        assert manifest.adapter_payload.channel_code == "mock"
        assert manifest.adapter_payload.adapter_name == "mock_adapter"
        assert manifest.adapter_payload.payload == {"key": "value"}

    def test_adapter_payload_isolated(self):
        """Adapter payload is isolated — main manifest doesn't leak KSO fields."""
        ctx = _make_context(channel_code="esl")
        payload = _make_payload(
            channel_code="esl",
            adapter_name="esl_adapter",
            payload={"template_id": "T-001", "update_interval": 60},
        )
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.adapter_payload is not None
        assert manifest.adapter_payload.payload["template_id"] == "T-001"
        # Main manifest should not have template_id at top level
        manifest_dict = manifest.model_dump()
        assert "template_id" not in manifest_dict


class TestMappingSchedulePlayback:
    """Schedule and playback mapping."""

    def test_maps_schedule_from_dates(self):
        ctx = _make_context(start_date="2026-07-01", end_date="2026-07-31")
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.schedule is not None
        assert manifest.schedule.start == "2026-07-01"
        assert manifest.schedule.end == "2026-07-31"

    def test_no_dates_no_schedule(self):
        ctx = _make_context(start_date=None, end_date=None)
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.schedule is None

    def test_maps_playback_proof_type(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest.playback is not None
        assert manifest.playback.proof_type == "real_playback"


# ═══════════════════════════════════════════════════════════════════════════
# Validation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidation:
    """validate_universal_manifest tests."""

    def test_validate_returns_no_critical_issues_for_valid(self):
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        issues = validate_universal_manifest(manifest)
        critical = [i for i in issues if i.severity == "error" and i.code != "missing_campaign_code"]
        # Campaign code mismatch is expected since context doesn't have real campaign_code
        assert len(critical) == 0, f"Unexpected critical issues: {critical}"

    def test_no_secrets_validation_passes(self):
        ctx = _make_context()
        payload = _make_payload(payload={"safe_key": "safe_value"})
        manifest = build_universal_manifest_from_draft(ctx, payload)
        from app.domains.manifests.universal_schema import validate_no_secrets
        issues = validate_no_secrets(manifest)
        assert len(issues) == 0

    def test_token_in_storage_ref_detected(self):
        """Token in storage_ref should be detected by no-secrets validator."""
        ctx = _make_context()
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        # Override content with a token-containing storage_ref
        manifest.content = [
            ManifestContentItem(
                media_type="image/png",
                storage_ref="https://cdn.example.com/file.png?token=abc123",
            )
        ]
        from app.domains.manifests.universal_schema import validate_no_secrets
        issues = validate_no_secrets(manifest)
        assert len(issues) > 0, f"Expected secret detection for token in storage_ref. Got: {issues}"

    def test_password_in_adapter_payload_detected(self):
        ctx = _make_context()
        payload = _make_payload(payload={"password": "hunter2"})
        manifest = build_universal_manifest_from_draft(ctx, payload)
        issues = validate_universal_manifest(manifest)
        assert any("password" in i.message.lower() or i.code == "forbidden_key"
                   for i in issues), f"Expected password detection. Issues: {issues}"

    def test_channel_code_mismatch_returns_issue(self):
        ctx = _make_context(channel_code="kso")
        payload = _make_payload(channel_code="android_tv")
        # Channel code mismatch is caught by Pydantic model_validator
        with pytest.raises(ValueError, match="does not match"):
            build_universal_manifest_from_draft(ctx, payload)


# ═══════════════════════════════════════════════════════════════════════════
# Deferred content tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDeferredContent:
    """Missing content handling — creative integration is deferred."""

    def test_missing_content_does_not_crash_builder(self):
        ctx = _make_context(creative_codes=[])
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert manifest is not None
        assert manifest.content is not None

    def test_missing_content_creates_warning(self):
        ctx = _make_context(creative_codes=[])
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert any(
            "content_not_available" in w
            for w in manifest.metadata.warnings
        ), f"Expected content warning. Got: {manifest.metadata.warnings}"


# ═══════════════════════════════════════════════════════════════════════════
# No-devices warning test
# ═══════════════════════════════════════════════════════════════════════════

class TestBuilderWarnings:
    """Builder warning scenarios."""

    def test_no_devices_warns(self):
        ctx = _make_context(devices=[])
        payload = _make_payload()
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert any("no_devices" in w for w in manifest.metadata.warnings)

    def test_adapter_warnings_preserved(self):
        ctx = _make_context()
        payload = _make_payload(warnings=["test_warning_1", "test_warning_2"])
        manifest = build_universal_manifest_from_draft(ctx, payload)
        assert "test_warning_1" in manifest.metadata.warnings
        assert "test_warning_2" in manifest.metadata.warnings


# ═══════════════════════════════════════════════════════════════════════════
# Import boundary tests
# ═══════════════════════════════════════════════════════════════════════════

class TestB52ImportBoundary:
    """universal_builder.py must not import forbidden modules."""

    def _get_import_lines(self):
        from app.domains.manifests import universal_builder as ub
        lines = open(ub.__file__).readlines()
        return " ".join(
            l for l in lines
            if l.strip().startswith(("import ", "from "))
        ).lower()

    def test_no_db_writes(self):
        from app.domains.manifests import universal_builder as ub
        src = open(ub.__file__).read()
        assert "db.add" not in src
        assert "db.commit" not in src
        # "await db" is OK — only for read operations (build_manifest_context uses db for selects)

    def test_no_generated_manifests_import(self):
        imports = self._get_import_lines()
        assert "generated_manifest" not in imports, "universal_builder imports generated_manifests"

    def test_no_publications_import(self):
        imports = self._get_import_lines()
        assert "publications" not in imports, "universal_builder imports publications"

    def test_no_kso_placement_import(self):
        imports = self._get_import_lines()
        assert "kso_placement" not in imports, "universal_builder imports kso_placements"

    def test_no_device_gateway_import(self):
        imports = self._get_import_lines()
        assert "device_gateway" not in imports, "universal_builder imports device_gateway"

    def test_no_api_routes(self):
        from app.domains.manifests import universal_builder as ub
        src = open(ub.__file__).read()
        assert "APIRouter" not in src
        assert "@router" not in src
