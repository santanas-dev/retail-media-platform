"""Step 37.10: Test KSO Proof of Play ingest — schemas, models, logic."""

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Import User to satisfy GeneratedManifest's relationship("User") mapper dep
from app.domains.identity.models import User  # noqa: F401


# ══════════════════════════════════════════════════════════════════════
# Model tests (no DB needed — just column introspection)
# ══════════════════════════════════════════════════════════════════════


class TestKsoPoPModel(unittest.TestCase):
    def test_table_name(self):
        from app.domains.proof_of_play.models import KsoProofOfPlayEvent
        self.assertEqual(
            KsoProofOfPlayEvent.__tablename__,
            "kso_proof_of_play_events",
        )

    def test_has_required_columns(self):
        from app.domains.proof_of_play.models import KsoProofOfPlayEvent
        cols = {c.name for c in KsoProofOfPlayEvent.__table__.columns}
        required = {
            "id", "event_code", "device_code", "placement_code",
            "campaign_code", "creative_code", "manifest_code",
            "media_ref", "event_type", "status",
            "played_at", "duration_ms", "received_at", "created_at",
        }
        self.assertTrue(required.issubset(cols))

    def test_no_forbidden_columns(self):
        from app.domains.proof_of_play.models import KsoProofOfPlayEvent
        cols = {c.name for c in KsoProofOfPlayEvent.__table__.columns}
        forbidden = {
            "receipt_data", "payment_data", "fiscal_data",
            "customer_id", "customer_phone", "customer_email",
            "card_number", "pan", "file_path", "sha256",
            "storage_ref", "minio_key", "backend_url",
            "token", "device_secret", "client_secret",
        }
        intersection = cols & forbidden
        self.assertEqual(
            intersection, set(),
            f"Forbidden columns found: {intersection}",
        )


# ══════════════════════════════════════════════════════════════════════
# Schema tests
# ══════════════════════════════════════════════════════════════════════


class TestKsoPoPSchemas(unittest.TestCase):
    def test_request_valid_minimal(self):
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        req = KsoPoPIngestRequest(
            event_code="demo_pop_001",
            media_ref="media/current/slot-000",
        )
        self.assertEqual(req.event_code, "demo_pop_001")
        self.assertEqual(req.event_type, "impression")

    def test_request_no_forbidden_in_dump(self):
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        req = KsoPoPIngestRequest(
            event_code="ok", media_ref="media/current/slot-000")
        data = req.model_dump()
        for fb in ("receipt_data", "payment", "fiscal", "customer",
                     "phone", "email", "card", "pan", "sha256",
                     "token", "secret", "file_path", "backend_url"):
            self.assertNotIn(fb, data)

    def test_response_no_forbidden(self):
        from app.domains.proof_of_play.schemas import KsoPoPIngestResponse
        now = datetime.now(timezone.utc)
        resp = KsoPoPIngestResponse(
            status="accepted", event_code="e1", device_code="d1",
            placement_code="p1", campaign_code="c1", creative_code="cr1",
            received_at=now)
        data = resp.model_dump()
        for fb in ("id", "manifest_version_id", "manifest_hash",
                     "backend_url", "token", "file_path", "sha256",
                     "storage_ref", "minio", "device_secret", "client_secret"):
            self.assertNotIn(fb, data)

    def test_response_has_expected_fields(self):
        from app.domains.proof_of_play.schemas import KsoPoPIngestResponse
        now = datetime.now(timezone.utc)
        resp = KsoPoPIngestResponse(
            status="accepted", event_code="e1", device_code="d1",
            placement_code="p1", campaign_code="c1", creative_code="cr1",
            received_at=now)
        data = resp.model_dump()
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(data["device_code"], "d1")
        self.assertEqual(data["placement_code"], "p1")
        self.assertEqual(data["campaign_code"], "c1")
        self.assertEqual(data["creative_code"], "cr1")


# ══════════════════════════════════════════════════════════════════════
# Media ref helper tests
# ══════════════════════════════════════════════════════════════════════


class TestMediaRefInManifest(unittest.TestCase):
    def setUp(self):
        from app.domains.proof_of_play.service import _media_ref_in_manifest
        self._check = _media_ref_in_manifest

    def test_media_ref_found(self):
        body = {"items": [
            {"slotOrder": 0, "mediaRef": "media/current/slot-000"},
            {"slotOrder": 1, "mediaRef": "media/current/slot-001"},
        ]}
        self.assertTrue(self._check(body, "media/current/slot-000"))
        self.assertTrue(self._check(body, "media/current/slot-001"))

    def test_media_ref_not_found(self):
        body = {"items": [
            {"slotOrder": 0, "mediaRef": "media/current/slot-000"},
        ]}
        self.assertFalse(self._check(body, "media/current/slot-999"))

    def test_no_items_key(self):
        self.assertFalse(self._check({}, "media/current/slot-000"))

    def test_items_not_a_list(self):
        self.assertFalse(self._check({"items": "not-a-list"}, "x"))


# ══════════════════════════════════════════════════════════════════════
# Manifest hash helper tests
# ══════════════════════════════════════════════════════════════════════


class TestManifestHash(unittest.TestCase):
    def test_hash_deterministic(self):
        from app.domains.proof_of_play.service import _compute_manifest_hash
        body = {"schemaVersion": 1, "items": []}
        h1 = _compute_manifest_hash(body)
        h2 = _compute_manifest_hash(body)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_hash_differs_on_content(self):
        from app.domains.proof_of_play.service import _compute_manifest_hash
        h1 = _compute_manifest_hash({"a": 1})
        h2 = _compute_manifest_hash({"a": 2})
        self.assertNotEqual(h1, h2)


# ══════════════════════════════════════════════════════════════════════
# Service logic tests (mock DB — no real tables)
# ══════════════════════════════════════════════════════════════════════


def _make_mock_row(**kwargs):
    """Create a mock row with attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


class TestKsoPoPServiceMock(unittest.TestCase):
    """Test ingest_kso_pop with mocked database session."""

    def setUp(self):
        self.now = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
        self.manifest_body = {
            "items": [
                {"slotOrder": 0, "contentType": "image/png",
                 "mediaRef": "media/current/slot-000"},
            ]
        }
        self.manifest_id = "gm-uuid-1234"
        self.manifest_hash = (
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd"
        )

    def _build_db(self, *, device_exists=True, manifest_published=True,
                  manifest_body=None, placement_exists=True,
                  creative_in_campaign=True):
        """Build a mock db session."""
        db = AsyncMock()

        # We need to track which query is being called
        call_count = [0]

        async def _execute_side_effect(stmt, *args, **kwargs):
            call_count[0] += 1
            n = call_count[0]

            result = AsyncMock()

            if n == 1:  # KsoDevice query
                if device_exists:
                    row = _make_mock_row(
                        id="kd1", device_code="a-05954")
                    result.scalar_one_or_none = MagicMock(return_value=row)
                else:
                    result.scalar_one_or_none = MagicMock(return_value=None)

            elif n == 2:  # GeneratedManifest query
                if manifest_published:
                    body = manifest_body or self.manifest_body
                    row = _make_mock_row(
                        id=self.manifest_id,
                        manifest_code="test-manifest",
                        device_code="a-05954",
                        placement_code="test-place",
                        campaign_code="test-camp",
                        manifest_body_json=body,
                        published_at=self.now,
                        status="published",
                    )
                    result.scalar_one_or_none = MagicMock(return_value=row)
                else:
                    result.scalar_one_or_none = MagicMock(return_value=None)

            elif n == 3:  # KsoPlacement query
                if placement_exists:
                    row = _make_mock_row(
                        placement_code="test-place",
                        campaign_code="test-camp",
                        creative_code="test-creative",
                    )
                    result.scalar_one_or_none = MagicMock(return_value=row)
                else:
                    result.scalar_one_or_none = MagicMock(return_value=None)

            elif n == 4:  # CampaignCreative query
                if creative_in_campaign:
                    row = _make_mock_row(
                        campaign_id="c1", creative_code="test-creative")
                    result.scalar_one_or_none = MagicMock(return_value=row)
                else:
                    result.scalar_one_or_none = MagicMock(return_value=None)

            elif n == 5:  # KsoProofOfPlayEvent duplicate check
                result.scalar_one_or_none = MagicMock(return_value=None)

            else:
                result.scalar_one_or_none = MagicMock(return_value=None)

            return result

        db.execute = AsyncMock(side_effect=_execute_side_effect)
        return db

    def _ingest(self, db, device_code="a-05954", event_code="pop-001",
                media_ref="media/current/slot-000",
                manifest_version_id=None, manifest_hash=None):
        import asyncio
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        from app.domains.proof_of_play.service import ingest_kso_pop

        async def _do():
            req = KsoPoPIngestRequest(
                event_code=event_code, media_ref=media_ref,
                manifest_version_id=manifest_version_id,
                manifest_hash=manifest_hash,
            )
            return await ingest_kso_pop(db, device_code, req)
        return asyncio.get_event_loop().run_until_complete(_do())

    def test_valid_ingest_succeeds(self):
        db = self._build_db()
        resp, err = self._ingest(db)
        self.assertIsNone(err)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.device_code, "a-05954")
        self.assertEqual(resp.placement_code, "test-place")
        self.assertEqual(resp.campaign_code, "test-camp")
        self.assertEqual(resp.creative_code, "test-creative")

    def test_device_not_found(self):
        db = self._build_db(device_exists=False)
        resp, err = self._ingest(db)
        self.assertIsNone(resp)
        self.assertEqual(err, "device_not_found")

    def test_no_published_manifest(self):
        db = self._build_db(manifest_published=False)
        resp, err = self._ingest(db)
        self.assertIsNone(resp)
        self.assertEqual(err, "no_published_manifest")

    def test_manifest_version_mismatch(self):
        db = self._build_db()
        resp, err = self._ingest(db, manifest_version_id="wrong-id")
        self.assertIsNone(resp)
        self.assertEqual(err, "manifest_version_mismatch")

    def test_manifest_version_match_succeeds(self):
        db = self._build_db()
        resp, err = self._ingest(db, manifest_version_id=self.manifest_id)
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")

    def test_manifest_hash_mismatch(self):
        db = self._build_db()
        resp, err = self._ingest(db, manifest_hash="deadbeef")
        self.assertIsNone(resp)
        self.assertEqual(err, "manifest_hash_mismatch")

    def test_manifest_hash_match_succeeds(self):
        db = self._build_db()
        from app.domains.proof_of_play.service import _compute_manifest_hash
        correct_hash = _compute_manifest_hash(self.manifest_body)
        resp, err = self._ingest(db, manifest_hash=correct_hash)
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")

    def test_unknown_media_ref(self):
        db = self._build_db()
        resp, err = self._ingest(db, media_ref="media/current/slot-999")
        self.assertIsNone(resp)
        self.assertEqual(err, "unknown_media_ref")

    def test_placement_not_found(self):
        db = self._build_db(placement_exists=False)
        resp, err = self._ingest(db)
        self.assertIsNone(resp)
        self.assertEqual(err, "placement_not_found")

    def test_creative_not_in_campaign(self):
        db = self._build_db(creative_in_campaign=False)
        resp, err = self._ingest(db)
        self.assertIsNone(resp)
        self.assertEqual(err, "creative_not_in_campaign")

    def test_duplicate_idempotent_accepted(self):
        db = AsyncMock()
        call_count = [0]

        async def _execute(stmt, *args, **kwargs):
            call_count[0] += 1
            n = call_count[0]
            result = AsyncMock()

            if n == 1:  # KsoDevice
                result.scalar_one_or_none = MagicMock(return_value=_make_mock_row(
                    id="kd1", device_code="a-05954"))
            elif n == 2:  # GeneratedManifest
                result.scalar_one_or_none = MagicMock(return_value=_make_mock_row(
                    id=self.manifest_id, manifest_code="test-manifest",
                    device_code="a-05954", placement_code="test-place",
                    campaign_code="test-camp",
                    manifest_body_json=self.manifest_body,
                    published_at=self.now, status="published"))
            elif n == 3:  # KsoPlacement
                result.scalar_one_or_none = MagicMock(return_value=_make_mock_row(
                    placement_code="test-place", campaign_code="test-camp",
                    creative_code="test-creative"))
            elif n == 4:  # CampaignCreative
                result.scalar_one_or_none = MagicMock(return_value=_make_mock_row(
                    campaign_id="c1", creative_code="test-creative"))
            elif n == 5:  # Duplicate check → existing row!
                existing = _make_mock_row(
                    event_code="pop-dup", device_code="a-05954",
                    placement_code="test-place", campaign_code="test-camp",
                    creative_code="test-creative",
                    received_at=self.now)
                result.scalar_one_or_none = MagicMock(return_value=existing)
            return result

        db.execute = AsyncMock(side_effect=_execute)
        resp, err = self._ingest(db, event_code="pop-dup")
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.event_code, "pop-dup")

    def test_response_no_raw_uuid(self):
        db = self._build_db()
        resp, err = self._ingest(db)
        self.assertIsNone(err)
        data = resp.model_dump()
        for fb in ("id", "manifest_version_id", "manifest_hash",
                     "backend_url", "token", "file_path", "sha256",
                     "storage_ref", "minio", "device_secret"):
            self.assertNotIn(fb, data)


# ══════════════════════════════════════════════════════════════════════
# Sidecar payload compatibility test
# ══════════════════════════════════════════════════════════════════════


class TestSidecarPayloadCompat(unittest.TestCase):
    """Verify that the sidecar's existing PopPayloadEvent shape is compatible."""

    def test_sidecar_fields_map_to_backend_request(self):
        """The minimal fields sidecar sends should fit KsoPoPIngestRequest."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest

        # Simulate what sidecar pop_payload.PopPayloadEvent produces
        # (event_code, manifest_version_id, manifest_hash, media_ref, ...)
        req = KsoPoPIngestRequest(
            event_code="demo_pop_001",
            manifest_version_id="gm-uuid-1234",
            manifest_hash="a1b2c3d4e5f6abcd",
            media_ref="media/current/slot-000",
            event_type="impression",
            played_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
            duration_ms=5000,
        )
        self.assertEqual(req.event_code, "demo_pop_001")
        self.assertEqual(req.event_type, "impression")
        self.assertEqual(req.duration_ms, 5000)

    def test_sidecar_forbidden_not_in_request(self):
        """No receipt/payment/customer/secret fields in request schema."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        fields = KsoPoPIngestRequest.model_fields
        for fb in ("receipt_data", "payment", "fiscal", "customer",
                     "phone", "email", "card", "pan", "sha256",
                     "token", "secret", "file_path", "backend_url",
                     "device_secret"):
            self.assertNotIn(fb, fields)

    def test_sidecar_forbidden_not_in_response(self):
        """No forbidden fields leak in response schema."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestResponse
        fields = KsoPoPIngestResponse.model_fields
        for fb in ("id", "manifest_version_id", "manifest_hash",
                     "backend_url", "token", "file_path", "sha256",
                     "storage_ref", "minio", "device_secret",
                     "client_secret", "receipt_data", "payment",
                     "fiscal", "customer", "phone", "email",
                     "card", "pan"):
            self.assertNotIn(fb, fields)
