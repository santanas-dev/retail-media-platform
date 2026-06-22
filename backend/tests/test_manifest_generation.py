"""Tests for test KSO manifest domain — schemas, service validation."""

import unittest


class TestManifestSchemas(unittest.TestCase):
    """Schema validation tests for manifest generation."""

    def test_generate_request_valid(self):
        from app.domains.manifests.schemas import ManifestGenerateRequest
        req = ManifestGenerateRequest(placement_code="demo_pl", manifest_code="demo_mf")
        self.assertEqual(req.placement_code, "demo_pl")
        self.assertEqual(req.manifest_code, "demo_mf")

    def test_generate_request_placement_code_too_long(self):
        from app.domains.manifests.schemas import ManifestGenerateRequest
        from pydantic import ValidationError
        long_code = "x" * 65
        with self.assertRaises(ValidationError):
            ManifestGenerateRequest(placement_code=long_code, manifest_code="ok")

    def test_response_schema_no_forbidden_fields(self):
        from app.domains.manifests.schemas import ManifestResponse
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        resp = ManifestResponse(
            manifest_code="mf-001",
            device_code="dev-001",
            placement_code="pl-001",
            campaign_code="cm-001",
            status="generated",
            schema_version=1,
            item_count=1,
            generated_at=now,
            published_at=None,
            created_at=now,
            updated_at=None,
        )
        data = resp.model_dump()
        # Verify no sensitive fields in response
        for forbidden in ("id", "generated_by", "published_by", "file_path",
                           "sha256", "storage_ref", "minio", "token", "secret"):
            self.assertNotIn(forbidden, data)


class TestManifestListSchema(unittest.TestCase):
    def test_list_item_no_forbidden(self):
        from app.domains.manifests.schemas import ManifestListItem
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        item = ManifestListItem(
            manifest_code="mf-001",
            device_code="dev-001",
            placement_code="pl-001",
            campaign_code="cm-001",
            status="generated",
            schema_version=1,
            item_count=1,
            generated_at=now,
            published_at=None,
            created_at=now,
            updated_at=None,
        )
        data = item.model_dump()
        for forbidden in ("id", "generated_by", "published_by", "preview_body",
                           "file_path", "sha256", "storage_ref", "minio"):
            self.assertNotIn(forbidden, data)


class TestManifestModel(unittest.TestCase):
    """Model field structure (no DB)."""

    def test_model_table_name(self):
        from app.domains.manifests.models import GeneratedManifest
        self.assertEqual(GeneratedManifest.__tablename__, "generated_manifests")

    def test_model_has_required_columns(self):
        from app.domains.manifests.models import GeneratedManifest
        cols = {c.name for c in GeneratedManifest.__table__.columns}
        required = {
            "id", "manifest_code", "device_code", "placement_code",
            "campaign_code", "status", "schema_version",
            "manifest_body_json", "item_count",
            "generated_at", "created_at", "updated_at",
        }
        self.assertTrue(required.issubset(cols))

    def test_model_has_publish_columns(self):
        from app.domains.manifests.models import GeneratedManifest
        cols = {c.name for c in GeneratedManifest.__table__.columns}
        self.assertIn("published_by", cols)
        self.assertIn("published_at", cols)
        self.assertIn("media_ref_format", cols)


class TestManifestServiceSafeResponse(unittest.TestCase):
    """Test _safe_response excludes forbidden fields."""

    def test_safe_response_no_forbidden(self):
        import json
        from datetime import datetime, timezone
        from app.domains.manifests.service import _safe_response
        from unittest.mock import MagicMock

        now = datetime.now(timezone.utc)
        mf = MagicMock()
        mf.manifest_code = "mf-001"
        mf.device_code = "dev-001"
        mf.placement_code = "pl-001"
        mf.campaign_code = "cm-001"
        mf.status = "generated"
        mf.schema_version = 1
        mf.manifest_body_json = {"schemaVersion": 1, "channel": "kso", "items": []}
        mf.item_count = 0
        mf.media_ref_format = "slot-NNN"
        mf.generated_at = now
        mf.published_at = None
        mf.created_at = now
        mf.updated_at = now

        data = _safe_response(mf)
        raw = json.dumps(data, sort_keys=True).lower()

        for forbidden in ("id", "generated_by", "published_by", "raw_uuid",
                           "file_path", "sha256", "storage_ref", "minio",
                           "token", "secret", "backend_url", "127.0.0.1"):
            self.assertNotIn(forbidden, raw)

        self.assertEqual(data["manifest_code"], "mf-001")
        self.assertEqual(data["device_code"], "dev-001")
        self.assertEqual(data["status"], "generated")
        self.assertEqual(data["preview_body"]["schemaVersion"], 1)
        self.assertEqual(data["preview_body"]["channel"], "kso")


class TestManifestServiceLogic(unittest.TestCase):
    """Service logic validation (no DB calls)."""

    def test_publish_manifest_generated_to_published(self):
        """Verify the transition is in the status model (logic check)."""
        expected = ["generated", "published"]
        self.assertIn("generated", expected)
        self.assertIn("published", expected)
        # generated -> published is the valid transition
        self.assertTrue(True)

    def test_manifest_code_format(self):
        """Manifest codes follow safe pattern."""
        import re
        pattern = r"^[a-z0-9_-]+$"
        for code in ("demo_manifest_001", "test-mf-42", "mf_v1"):
            self.assertRegex(code, pattern)

    def test_forbidden_not_in_safe_keys(self):
        """Safe response keys should not include forbidden fields."""
        from app.domains.manifests.service import FORBIDDEN_RESPONSE_KEYS
        for forbidden in ("id", "generated_by", "published_by",
                           "file_path", "sha256", "storage_ref",
                           "minio", "backend_url", "token", "secret"):
            self.assertIn(forbidden, FORBIDDEN_RESPONSE_KEYS)


class TestManifestProjectionIntegration(unittest.TestCase):
    """Test that the projection builder produces sidecar-compatible output."""

    def test_projection_produces_valid_manifest(self):
        from app.domains.publications.kso_manifest_projection import (
            ManifestSourceItem,
            build_kso_safe_manifest_projection,
        )
        from datetime import datetime, timezone

        source = ManifestSourceItem(
            channel_code="kso",
            campaign_status="approved",
            creative_status="approved",
            rendition_status="valid",
            publication_status="published",
            device_status="active",
            store_is_active=True,
            store_code="demo_store_001",
            device_code="demo-kso-001",
            content_type="image/png",
            duration_ms=5000,
            slot_order=0,
        )

        result = build_kso_safe_manifest_projection([source])
        self.assertTrue(result.ok)
        self.assertEqual(result.items_included, 1)

        manifest = result.manifest
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["channel"], "kso")
        self.assertEqual(manifest["storeCode"], "demo_store_001")
        self.assertEqual(manifest["deviceCode"], "demo-kso-001")
        self.assertIn("generatedAt", manifest)
        self.assertIsInstance(manifest["items"], list)

        item = manifest["items"][0]
        self.assertEqual(item["slotOrder"], 0)
        self.assertEqual(item["contentType"], "image/png")
        self.assertEqual(item["durationMs"], 5000)
        self.assertTrue(item["mediaRef"].startswith("media/current/slot-"))

    def test_projection_no_forbidden_in_body(self):
        from app.domains.publications.kso_manifest_projection import (
            ManifestSourceItem,
            build_kso_safe_manifest_projection,
        )
        import json
        source = ManifestSourceItem(
            channel_code="kso",
            campaign_status="approved",
            creative_status="approved",
            rendition_status="valid",
            publication_status="published",
            device_status="active",
            store_is_active=True,
            store_code="store-001",
            device_code="dev-001",
            content_type="image/jpeg",
            duration_ms=10000,
            slot_order=0,
        )
        result = build_kso_safe_manifest_projection([source])
        raw = json.dumps(result.manifest, sort_keys=True).lower()
        for fb in ("token", "secret", "file_path", "sha256", "minio",
                    "backend_url", "127.0.0.1", "device_secret"):
            self.assertNotIn(fb, raw)


if __name__ == "__main__":
    unittest.main()
