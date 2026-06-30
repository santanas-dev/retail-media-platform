"""
B.5.1 — Universal Manifest Schema Contracts: targeted tests.

Tests for universal_schema.py models and validation helpers.
No DB, no API, no side effects.
"""

import pytest
from datetime import datetime, timezone

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
    # Validation helpers
    validate_required_fields,
    validate_no_secrets,
    validate_manifest_schema,
    FORBIDDEN_SECRET_KEYS,
)


def _make_minimal_manifest(**overrides) -> UniversalManifestV1:
    """Build a minimal valid UniversalManifestV1 for testing."""
    kwargs = {
        "campaign": ManifestCampaign(campaign_code="TEST-001"),
        "placement": ManifestPlacement(
            placement_code="PLC-001",
            channel_code="mock",
        ),
        "targets": [
            ManifestTarget(
                target_type="store",
                physical_device_code="DEV-001",
                capability_profile_code="CP-001",
            )
        ],
    }
    kwargs.update(overrides)
    return UniversalManifestV1(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# Model construction tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMinimalManifest:
    """Minimal manifest construction."""

    def test_create_minimal(self):
        m = _make_minimal_manifest()
        assert m.manifest_version == "1.0"
        assert m.campaign.campaign_code == "TEST-001"
        assert m.placement.placement_code == "PLC-001"

    def test_manifest_version_defaults_to_1_0(self):
        m = _make_minimal_manifest()
        assert m.manifest_version == "1.0"

    def test_schema_version_defaults_to_1(self):
        m = _make_minimal_manifest()
        assert m.schema_version == 1

    def test_signature_status_defaults_to_unsigned(self):
        m = _make_minimal_manifest()
        assert m.security.signature_status == ManifestSignatureStatus.UNSIGNED

    def test_status_defaults_to_draft(self):
        m = _make_minimal_manifest()
        assert m.status == ManifestStatus.DRAFT


class TestRequiredFields:
    """Required field validation."""

    def test_campaign_required(self):
        # Pydantic enforces required fields — validate_required_fields catches
        # issues when model is constructed with model_construct() bypass
        m = UniversalManifestV1.model_construct(
            placement=ManifestPlacement.model_construct(placement_code="X", channel_code="mock"),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_campaign" for i in issues)

    def test_placement_required(self):
        m = UniversalManifestV1.model_construct(
            campaign=ManifestCampaign.model_construct(campaign_code="X"),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_placement" for i in issues)

    def test_campaign_code_required(self):
        m = UniversalManifestV1.model_construct(
            campaign=ManifestCampaign.model_construct(campaign_code=""),
            placement=ManifestPlacement.model_construct(placement_code="X", channel_code="mock"),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_campaign_code" for i in issues)

    def test_target_list_required_non_empty(self):
        m = UniversalManifestV1.model_construct(
            campaign=ManifestCampaign.model_construct(campaign_code="TEST"),
            placement=ManifestPlacement.model_construct(placement_code="PLC", channel_code="mock"),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_targets" for i in issues)

    def test_channel_code_required(self):
        m = UniversalManifestV1.model_construct(
            campaign=ManifestCampaign.model_construct(campaign_code="TEST"),
            placement=ManifestPlacement.model_construct(placement_code="PLC", channel_code=""),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_channel_code" for i in issues)

    def test_placement_code_required(self):
        m = UniversalManifestV1.model_construct(
            campaign=ManifestCampaign.model_construct(campaign_code="TEST"),
            placement=ManifestPlacement.model_construct(placement_code="", channel_code="mock"),
            targets=[],
        )
        issues = validate_required_fields(m)
        assert any(i.code == "missing_placement_code" for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# No-secrets validation
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecrets:
    """No-secrets validation."""

    def test_no_secrets_detects_token(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock",
                adapter_name="mock",
                payload={"token": "secret123"},
            )
        )
        issues = validate_no_secrets(m)
        assert any("token" in i.message.lower() or i.code == "forbidden_key" for i in issues)

    def test_no_secrets_detects_password(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock",
                adapter_name="mock",
                payload={"password": "hunter2"},
            )
        )
        issues = validate_no_secrets(m)
        assert any("password" in i.message.lower() or i.code == "forbidden_key" for i in issues)

    def test_no_secrets_detects_access_key(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock",
                adapter_name="mock",
                payload={"access_key": "AKIA..."},
            )
        )
        issues = validate_no_secrets(m)
        assert any("access_key" in i.message.lower() or i.code == "forbidden_key" for i in issues)

    def test_safe_storage_ref_passes(self):
        """storage_ref with safe path should pass no-secrets check."""
        m = _make_minimal_manifest(
            content=[
                ManifestContentItem(
                    media_type="image/png",
                    storage_ref="creative/CR-001/v1/rendition.png",
                )
            ]
        )
        issues = validate_no_secrets(m)
        assert len(issues) == 0, f"Expected no issues, got: {issues}"

    def test_storage_ref_with_token_fails(self):
        """storage_ref containing 'token' should be flagged."""
        m = _make_minimal_manifest(
            content=[
                ManifestContentItem(
                    media_type="image/png",
                    storage_ref="https://cdn.example.com/file.png?token=abc123",
                )
            ]
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_no_secrets_detects_secret_in_nested_payload(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock",
                adapter_name="mock",
                payload={"config": {"secret": "nested-secret"}},
            )
        )
        issues = validate_no_secrets(m)
        assert any("secret" in i.message.lower() or i.code == "forbidden_key" for i in issues)

    def test_no_secrets_detects_private_key(self):
        m = _make_minimal_manifest(
            adapter_payload=ManifestAdapterPayload(
                channel_code="mock",
                adapter_name="mock",
                payload={"private_key": "-----BEGIN RSA..."},
            )
        )
        issues = validate_no_secrets(m)
        assert len(issues) > 0

    def test_clean_manifest_no_secret_issues(self):
        m = _make_minimal_manifest()
        issues = validate_no_secrets(m)
        assert len(issues) == 0, f"Expected no issues on clean manifest, got: {issues}"


# ═══════════════════════════════════════════════════════════════════════════
# Channel-agnostic tests
# ═══════════════════════════════════════════════════════════════════════════

class TestChannelAgnostic:
    """Target is channel-agnostic — no KSO-specific required fields."""

    def test_target_is_channel_agnostic(self):
        """Target should work with any channel_code, not just KSO."""
        for channel in ("kso", "android_tv", "esl", "led_shelf", "price_checker"):
            t = ManifestTarget(
                target_type="store",
                physical_device_code=f"DEV-{channel}",
                capability_profile_code=f"CP-{channel}",
            )
            assert t.target_type == "store"
            assert t.physical_device_code == f"DEV-{channel}"

    def test_adapter_payload_is_isolated(self):
        """Adapter payload should be isolated dict, not schema-mandated."""
        payload = ManifestAdapterPayload(
            channel_code="android_tv",
            adapter_name="android_tv_adapter",
            payload={"apk_package": "com.example.app", "min_sdk": 26},
        )
        assert payload.channel_code == "android_tv"
        assert payload.adapter_name == "android_tv_adapter"
        assert payload.payload["apk_package"] == "com.example.app"


class TestNoKsoReferences:
    """Universal manifest must not require KSO-specific fields."""

    def test_kso_device_code_not_required(self):
        """ManifestTarget schema doesn't have kso_device_code field."""
        t = ManifestTarget(target_type="store")
        # Should not have kso_device_code as a field
        assert not hasattr(t, "kso_device_code")

    def test_generated_manifest_code_not_required(self):
        """universal_schema module does not import generated_manifests."""
        from app.domains.manifests import universal_schema as us
        import_lines = [l for l in open(us.__file__).readlines()
                       if l.strip().startswith(("import ", "from "))]
        src = " ".join(import_lines).lower()
        assert "generated_manifest" not in src, "universal_schema imports generated_manifests"

    def test_kso_placements_not_referenced(self):
        """universal_schema does not import kso_placements."""
        from app.domains.manifests import universal_schema as us
        import_lines = [l for l in open(us.__file__).readlines()
                       if l.strip().startswith(("import ", "from "))]
        src = " ".join(import_lines).lower()
        assert "kso_placement" not in src, "universal_schema imports kso_placements"


# ═══════════════════════════════════════════════════════════════════════════
# Channel code consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestChannelCodeConsistency:
    """adapter_payload.channel_code must match placement.channel_code."""

    def test_matching_channel_codes(self):
        m = _make_minimal_manifest(
            placement=ManifestPlacement(placement_code="PLC", channel_code="kso"),
            adapter_payload=ManifestAdapterPayload(
                channel_code="kso",
                adapter_name="kso_adapter",
            ),
        )
        assert m.placement.channel_code == "kso"
        assert m.adapter_payload is not None
        assert m.adapter_payload.channel_code == "kso"

    def test_mismatched_channel_codes_raises(self):
        with pytest.raises(ValueError, match="does not match"):
            _make_minimal_manifest(
                placement=ManifestPlacement(placement_code="PLC", channel_code="kso"),
                adapter_payload=ManifestAdapterPayload(
                    channel_code="android_tv",
                    adapter_name="android_tv_adapter",
                ),
            )

    def test_no_adapter_payload_is_fine(self):
        """Missing adapter_payload should not cause channel code error."""
        m = _make_minimal_manifest(
            placement=ManifestPlacement(placement_code="PLC", channel_code="mock"),
        )
        assert m.adapter_payload is None


# ═══════════════════════════════════════════════════════════════════════════
# Serialization
# ═══════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """Serialization to dict and JSON."""

    def test_model_dump_works(self):
        m = _make_minimal_manifest()
        d = m.model_dump()
        assert d["manifest_version"] == "1.0"
        assert d["campaign"]["campaign_code"] == "TEST-001"
        assert d["security"]["signature_status"] == "unsigned"

    def test_model_dump_json_works(self):
        m = _make_minimal_manifest()
        d = m.model_dump(mode="json")
        assert d["manifest_version"] == "1.0"
        assert d["security"]["signature_status"] == "unsigned"

    def test_roundtrip_dict_to_model(self):
        m1 = _make_minimal_manifest()
        d = m1.model_dump()
        m2 = UniversalManifestV1(**d)
        assert m2.manifest_version == m1.manifest_version
        assert m2.campaign.campaign_code == m1.campaign.campaign_code


# ═══════════════════════════════════════════════════════════════════════════
# Validation helper tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationHelpers:
    """validate_manifest_schema and structured issues."""

    def test_validate_returns_manifest_issue_list(self):
        m = _make_minimal_manifest()
        issues = validate_manifest_schema(m)
        assert isinstance(issues, list)
        # Clean manifest should have no errors
        error_issues = [i for i in issues if i.severity == "error"]
        assert len(error_issues) == 0, f"Expected 0 errors on clean manifest, got: {error_issues}"

    def test_invalid_signature_status_rejected(self):
        # Use model_construct to bypass Pydantic enum validation
        # and test our validate_manifest_schema() catches it
        m = _make_minimal_manifest()
        m.security = ManifestSecurity.model_construct(signature_status="invalid_value")
        issues = validate_manifest_schema(m)
        assert any(i.code == "invalid_signature_status" for i in issues)

    def test_dry_run_metadata_supported(self):
        m = _make_minimal_manifest(
            metadata=ManifestMetadata(dry_run=True, source="orchestrator"),
        )
        assert m.metadata.dry_run is True
        assert m.metadata.source == "orchestrator"

    def test_full_schema_clean_manifest(self):
        """Full manifest with all optional blocks should validate clean."""
        m = _make_minimal_manifest(
            manifest_id="m-test-001",
            generated_at=datetime.now(timezone.utc),
            campaign=ManifestCampaign(
                campaign_code="CAMP-SUMMER",
                campaign_name="Летняя акция",
            ),
            placement=ManifestPlacement(
                placement_code="PLC-KSO-001",
                placement_name="Размещение КСО",
                channel_code="kso",
                status="approved",
                start_date="2026-07-01",
                end_date="2026-07-31",
            ),
            targets=[
                ManifestTarget(
                    target_type="store",
                    store_code="STORE-042",
                    display_surface_code="DS-MAIN",
                    physical_device_code="test-dev-seed",
                    device_type_code="kso_checkout",
                    capability_profile_code="kso_portrait",
                )
            ],
            content=[
                ManifestContentItem(
                    creative_code="CR-BANNER",
                    media_type="image/png",
                    storage_ref="creative/CR-BANNER/v1/banner.png",
                )
            ],
            schedule=ManifestSchedule(
                start="2026-07-01T00:00:00+03:00",
                end="2026-07-31T23:59:59+03:00",
                timezone="Europe/Moscow",
            ),
            adapter_payload=ManifestAdapterPayload(
                channel_code="kso",
                adapter_name="kso_adapter",
                payload={"slot_order": 0},
            ),
            capability=ManifestCapability(
                proof_type="real_playback",
                resolution="768x1024",
                orientation="portrait",
                supported_formats=["image/png", "image/jpeg", "video/mp4"],
            ),
            metadata=ManifestMetadata(dry_run=True, source="orchestrator"),
        )
        issues = validate_manifest_schema(m)
        error_issues = [i for i in issues if i.severity == "error"]
        assert len(error_issues) == 0, f"Full clean manifest has errors: {error_issues}"
        assert m.capability is not None
        assert m.capability.proof_type == "real_playback"
        assert len(m.targets) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Import boundary tests
# ═══════════════════════════════════════════════════════════════════════════

class TestB51ImportBoundary:
    """universal_schema.py must not import forbidden modules."""

    def test_no_generated_manifests_import(self):
        from app.domains.manifests import universal_schema as us
        import sys
        assert "app.domains.manifests" in sys.modules
        # Check the module source for forbidden imports
        src = open(us.__file__).read()
        forbidden = [
            "from app.domains.publications",
            "import app.domains.publications",
            "from app.domains.scheduling",
            "from app.domains.hierarchy",
            "from app.domains.orchestrator",
            "from sqlalchemy",
            "from app.core.database",
        ]
        for f in forbidden:
            assert f not in src, f"universal_schema.py has forbidden import: {f}"

    def test_no_db_writes(self):
        """universal_schema module is pure schema — no DB writes."""
        from app.domains.manifests import universal_schema as us
        src = open(us.__file__).read()
        assert "db.add" not in src
        assert "db.commit" not in src
        assert "await db" not in src

    def test_no_api_routes(self):
        """universal_schema has no FastAPI route definitions."""
        from app.domains.manifests import universal_schema as us
        src = open(us.__file__).read()
        assert "APIRouter" not in src
        assert "@router" not in src
        assert "fastapi" not in src.lower()
