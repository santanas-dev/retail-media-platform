"""
B.5.3 — Universal Manifest Validation: targeted tests.

Tests for enhanced validators (campaign, targets, capability, content,
schedule, adapter_payload) + stronger no-secrets + preview vs final.
No DB writes, no API, no side effects.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID

from app.domains.manifests.universal_schema import (
    UniversalManifestV1,
    ManifestCampaign,
    ManifestPlacement,
    ManifestTarget,
    ManifestContentItem,
    ManifestSchedule,
    ManifestPlayback,
    ManifestAdapterPayload,
    ManifestSecurity,
    ManifestCapability,
    ManifestMetadata,
    ManifestIssue,
    ManifestSignatureStatus,
    ManifestStatus,
    # Validators
    validate_required_fields,
    validate_no_secrets,
    validate_manifest_schema,
    validate_campaign,
    validate_targets,
    validate_capability,
    validate_content,
    validate_schedule,
    validate_adapter_payload,
    validate_manifest_for_preview,
    validate_manifest_for_final_publish,
)
from app.domains.manifests.universal_builder import (
    build_universal_manifest_from_draft,
)
from app.domains.orchestrator.contracts import (
    OrchestratorContext,
    AdapterPayloadDraft,
    DeviceInfo,
    SurfaceInfo,
)


def _make_minimal_manifest(**overrides) -> UniversalManifestV1:
    """Build a minimal valid manifest."""
    kwargs = {
        "campaign": ManifestCampaign(campaign_code="TEST-001"),
        "placement": ManifestPlacement(
            placement_code="PLC-001",
            channel_code="mock",
        ),
        "targets": [
            ManifestTarget(
                target_type="surface",
                physical_device_code="DEV-001",
                capability_profile_code="CP-001",
            )
        ],
    }
    kwargs.update(overrides)
    return UniversalManifestV1(**kwargs)


def _make_context(**overrides) -> OrchestratorContext:
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
                surfaces=[
                    SurfaceInfo(
                        surface_id="DS-MAIN",
                        resolution="768x1024",
                        orientation="portrait",
                        formats=["image/png", "video/mp4"],
                        proof_type="real_playback",
                    ),
                ],
            ),
        ],
    }
    kwargs.update(overrides)
    return OrchestratorContext(**kwargs)


def _make_payload(**overrides) -> AdapterPayloadDraft:
    kwargs = {"channel_code": "mock", "adapter_name": "mock_adapter", "payload": {"slot": 0}}
    kwargs.update(overrides)
    return AdapterPayloadDraft(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# Required fields
# ═══════════════════════════════════════════════════════════════════════════

class TestRequiredFields:
    def test_missing_manifest_version(self):
        m = UniversalManifestV1.model_construct(manifest_version="")
        issues = validate_required_fields(m)
        assert any(i.code == "missing_manifest_version" for i in issues)

    def test_missing_placement_code(self):
        m = UniversalManifestV1.model_construct(
            placement=ManifestPlacement.model_construct(placement_code="", channel_code="mock"),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_placement_code" for i in issues)

    def test_missing_channel_code(self):
        m = UniversalManifestV1.model_construct(
            placement=ManifestPlacement.model_construct(placement_code="PLC", channel_code=""),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_channel_code" for i in issues)

    def test_empty_targets(self):
        m = _make_minimal_manifest(targets=[])
        issues = validate_required_fields(m)
        assert any(i.code == "missing_targets" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# Campaign validation
# ═══════════════════════════════════════════════════════════════════════════

class TestCampaignValidation:
    def test_campaign_code_not_equal_placement_code(self):
        """campaign_code must not be placement_code proxy."""
        m = _make_minimal_manifest(
            campaign=ManifestCampaign(campaign_code="PLC-001"),
            placement=ManifestPlacement(placement_code="PLC-001", channel_code="mock"),
        )
        issues = validate_campaign(m)
        assert any(i.code == "campaign_equals_placement_code" for i in issues)

    def test_incomplete_campaign_warning_for_preview(self):
        m = _make_minimal_manifest(
            campaign=ManifestCampaign(),  # no campaign_code
            status=ManifestStatus.DRAFT,
        )
        issues = validate_campaign(m)
        incomplete = [i for i in issues if i.code == "campaign_data_incomplete"]
        assert len(incomplete) > 0
        assert incomplete[0].severity == "warning"

    def test_incomplete_campaign_error_for_final(self):
        m = _make_minimal_manifest(
            campaign=ManifestCampaign(),
            status=ManifestStatus.PUBLISHED,
        )
        issues = validate_campaign(m)
        incomplete = [i for i in issues if i.code == "campaign_data_incomplete"]
        assert len(incomplete) > 0
        assert incomplete[0].severity == "error"

    def test_builder_does_not_use_placement_as_campaign_proxy(self):
        """Builder must NOT set campaign_code = placement_code."""
        ctx = _make_context(placement_code="PLC-PROXY")
        payload = _make_payload()
        m = build_universal_manifest_from_draft(ctx, payload)
        assert m.campaign.campaign_code is None
        assert "campaign_data_incomplete" in m.metadata.warnings


# ═══════════════════════════════════════════════════════════════════════════
# Target validation
# ═══════════════════════════════════════════════════════════════════════════

class TestTargetValidation:
    def test_valid_multi_target_passes(self):
        m = _make_minimal_manifest(targets=[
            ManifestTarget(target_type="surface", physical_device_code="D1"),
            ManifestTarget(target_type="store", store_code="S1"),
        ])
        issues = validate_targets(m)
        assert len(issues) == 0

    def test_invalid_target_type_rejected(self):
        m = _make_minimal_manifest(targets=[
            ManifestTarget(target_type="invalid_xyz", physical_device_code="D1"),
        ])
        issues = validate_targets(m)
        assert any(i.code == "invalid_target_type" for i in issues)

    def test_playable_target_without_surface_or_device(self):
        m = _make_minimal_manifest(targets=[
            ManifestTarget(target_type="surface"),
        ])
        issues = validate_targets(m)
        assert any(i.code == "playable_target_missing_surface_or_device" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# Capability validation
# ═══════════════════════════════════════════════════════════════════════════

class TestCapabilityValidation:
    def test_content_format_within_supported_formats_passes(self):
        m = _make_minimal_manifest(
            capability=ManifestCapability(
                proof_type="real_playback",
                supported_formats=["image/png", "video/mp4"],
            ),
            content=[
                ManifestContentItem(media_type="image/png", format="image/png"),
            ],
        )
        issues = validate_capability(m)
        assert len(issues) == 0

    def test_unsupported_content_format_rejected(self):
        m = _make_minimal_manifest(
            capability=ManifestCapability(
                proof_type="real_playback",
                supported_formats=["image/png"],
            ),
            content=[
                ManifestContentItem(media_type="video/mp4", format="video/mp4"),
            ],
        )
        issues = validate_capability(m)
        assert any(i.code == "unsupported_content_format" for i in issues)

    def test_empty_supported_formats_rejected_when_content_exists(self):
        m = _make_minimal_manifest(
            capability=ManifestCapability(proof_type="real_playback", supported_formats=[]),
            content=[ManifestContentItem(media_type="image/png")],
        )
        issues = validate_capability(m)
        assert any(i.code == "empty_supported_formats" for i in issues)

    def test_playback_proof_type_mismatch_rejected(self):
        m = _make_minimal_manifest(
            capability=ManifestCapability(proof_type="real_playback", supported_formats=[]),
            playback=ManifestPlayback(proof_type="idle_impression"),
        )
        issues = validate_capability(m)
        assert any(i.code == "proof_type_mismatch" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# Content validation
# ═══════════════════════════════════════════════════════════════════════════

class TestContentValidation:
    def test_empty_content_warning_for_preview(self):
        m = _make_minimal_manifest(content=[], status=ManifestStatus.DRAFT)
        issues = validate_content(m)
        assert any(i.code == "content_not_available" and i.severity == "warning" for i in issues)

    def test_empty_content_error_for_final(self):
        m = _make_minimal_manifest(content=[], status=ManifestStatus.PUBLISHED)
        issues = validate_content(m)
        assert any(i.code == "missing_content" and i.severity == "error" for i in issues)

    def test_missing_media_type(self):
        m = _make_minimal_manifest(
            content=[ManifestContentItem.model_construct(media_type="")],
        )
        issues = validate_content(m)
        assert any(i.code == "missing_media_type" for i in issues)

    def test_missing_storage_ref_for_final(self):
        m = _make_minimal_manifest(
            status=ManifestStatus.PUBLISHED,
            content=[ManifestContentItem(media_type="image/png")],
        )
        issues = validate_content(m)
        assert any(i.code == "missing_storage_ref" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# Schedule validation
# ═══════════════════════════════════════════════════════════════════════════

class TestScheduleValidation:
    def test_valid_schedule_passes(self):
        m = _make_minimal_manifest(
            schedule=ManifestSchedule(start="2026-07-01", end="2026-07-31"),
        )
        issues = validate_schedule(m)
        assert len(issues) == 0

    def test_inverted_schedule_rejected(self):
        m = _make_minimal_manifest(
            schedule=ManifestSchedule(start="2026-12-31", end="2026-01-01"),
        )
        issues = validate_schedule(m)
        # String comparison may or may not catch this — depends on format
        # For ISO dates "2026-12-31" > "2026-01-01" is True (string lexicographic)
        if m.schedule and m.schedule.start and m.schedule.end:
            assert m.schedule.start > m.schedule.end  # confirms inversion
            inv = [i for i in issues if i.code == "schedule_inverted"]
            assert len(inv) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Adapter payload validation
# ═══════════════════════════════════════════════════════════════════════════

class TestAdapterPayloadValidation:
    def test_missing_adapter_payload_for_final(self):
        m = _make_minimal_manifest(status=ManifestStatus.PUBLISHED)
        issues = validate_adapter_payload(m)
        assert any(i.code == "missing_adapter_payload" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# No-secrets validation — enhanced patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecretsEnhanced:
    def test_token_in_storage_ref_detected(self):
        m = _make_minimal_manifest(
            content=[ManifestContentItem(media_type="image/png", storage_ref="?token=abc123")],
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_password_in_adapter_payload_detected(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock", adapter_name="mock",
                payload={"password": "hunter2"},
            ),
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_api_key_in_nested_payload_detected(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock", adapter_name="mock",
                payload={"config": {"api_key": "sk-secret"}},
            ),
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_bearer_token_detected(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock", adapter_name="mock",
                payload={"auth": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc"},
            ),
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_x_amz_signature_detected(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock", adapter_name="mock",
                payload={"url": "https://s3.amazonaws.com/bucket/file?X-Amz-Signature=abc123"},
            ),
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_signature_status_allowed(self):
        """security.signature_status is an allowed controlled field."""
        m = _make_minimal_manifest(
            security=ManifestSecurity(signature_status=ManifestSignatureStatus.UNSIGNED),
        )
        issues = validate_no_secrets(m)
        assert len(issues) == 0

    def test_signature_algorithm_allowed(self):
        """security.signature_algorithm is allowed without secret values."""
        m = _make_minimal_manifest(
            security=ManifestSecurity(signature_algorithm="HS256"),
        )
        issues = validate_no_secrets(m)
        assert len(issues) == 0

    def test_safe_storage_ref_passes(self):
        m = _make_minimal_manifest(
            content=[ManifestContentItem(
                media_type="image/png",
                storage_ref="creative/CR-001/v1/rendition.png",
            )],
        )
        issues = validate_no_secrets(m)
        assert len(issues) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Serialization
# ═══════════════════════════════════════════════════════════════════════════

class TestSerialization:
    def test_model_dump_works(self):
        m = _make_minimal_manifest(
            generated_at=datetime.now(timezone.utc),
        )
        d = m.model_dump(mode="json")
        assert "manifest_version" in d
        assert d["manifest_version"] == "1.0"

    def test_serialized_manifest_no_secrets(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock", adapter_name="mock",
                payload={"slot": 0},
            ),
        )
        d = m.model_dump(mode="json")
        issues = validate_no_secrets(m)
        assert len(issues) == 0

    def test_datetime_serialization(self):
        now = datetime.now(timezone.utc)
        m = _make_minimal_manifest(generated_at=now)
        d = m.model_dump(mode="json")
        assert "generated_at" in d
        assert d["generated_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# Preview vs Final validation
# ═══════════════════════════════════════════════════════════════════════════

class TestPreviewVsFinal:
    def test_preview_allows_missing_content(self):
        m = _make_minimal_manifest(content=[], status=ManifestStatus.DRAFT)
        issues = validate_manifest_for_preview(m)
        # Preview should not have "missing_content" error
        assert not any(i.code == "missing_content" and i.severity == "error" for i in issues)

    def test_final_rejects_missing_content(self):
        m = _make_minimal_manifest(content=[], status=ManifestStatus.PUBLISHED)
        issues = validate_manifest_for_final_publish(m)
        assert any(i.code == "missing_content" and i.severity == "error" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# Import boundaries
# ═══════════════════════════════════════════════════════════════════════════

class TestB53ImportBoundary:
    def _imports_of(self, module_name):
        import importlib
        mod = importlib.import_module(module_name)
        fname = getattr(mod, "__file__", None)
        if not fname:
            return ""
        lines = open(fname).readlines()
        return " ".join(
            l for l in lines
            if l.strip().startswith(("import ", "from "))
        ).lower()

    def test_universal_builder_no_publication(self):
        imports = self._imports_of("app.domains.manifests.universal_builder")
        assert "publications" not in imports

    def test_universal_schema_no_publication(self):
        imports = self._imports_of("app.domains.manifests.universal_schema")
        assert "publications" not in imports

    def test_no_generated_manifests(self):
        for mod in ("app.domains.manifests.universal_schema", "app.domains.manifests.universal_builder"):
            imports = self._imports_of(mod)
            assert "generated_manifest" not in imports, f"{mod} imports generated_manifests"

    def test_no_kso_placements(self):
        for mod in ("app.domains.manifests.universal_schema", "app.domains.manifests.universal_builder"):
            imports = self._imports_of(mod)
            assert "kso_placement" not in imports, f"{mod} imports kso_placements"

    def test_no_device_gateway(self):
        for mod in ("app.domains.manifests.universal_schema", "app.domains.manifests.universal_builder"):
            imports = self._imports_of(mod)
            assert "device_gateway" not in imports, f"{mod} imports device_gateway"
