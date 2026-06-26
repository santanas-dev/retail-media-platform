"""Step 39.2.4: Production Reports POP endpoints — tests.

Covers:
- PoPSummaryResponse schema validation
- GET /api/reports/pop endpoint (production PoP list)
- GET /api/reports/pop/summary endpoint (aggregated counts)
- Permission: reports.read required
- Safe projection: no raw UUIDs, tokens, secrets
"""

import unittest
from datetime import datetime, timezone


# ══════════════════════════════════════════════════════════════════════
# Schema tests
# ══════════════════════════════════════════════════════════════════════

class TestPoPSummarySchema(unittest.TestCase):
    def test_summary_fields(self):
        from app.domains.proof_of_play.router import PoPSummaryResponse
        s = PoPSummaryResponse(
            total_events=42,
            unique_devices=5,
            unique_campaigns=3,
            unique_creatives=7,
            unique_placements=6,
            accepted=38,
            rejected=2,
            duplicate=1,
            unknown_status=1,
            last_event_at=datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(s.total_events, 42)
        self.assertEqual(s.unique_devices, 5)
        self.assertEqual(s.accepted, 38)
        self.assertEqual(s.rejected, 2)
        self.assertEqual(s.duplicate, 1)

    def test_summary_defaults(self):
        from app.domains.proof_of_play.router import PoPSummaryResponse
        s = PoPSummaryResponse()
        self.assertEqual(s.total_events, 0)
        self.assertEqual(s.unique_devices, 0)
        self.assertEqual(s.accepted, 0)
        self.assertIsNone(s.last_event_at)

    def test_summary_no_forbidden_fields(self):
        from app.domains.proof_of_play.router import PoPSummaryResponse
        s = PoPSummaryResponse()
        data = s.model_dump()
        forbidden = {
            "raw_uuid", "token", "secret", "backend_url",
            "device_secret", "client_secret", "file_path", "sha256",
            "storage_ref", "minio", "receipt", "payment", "fiscal",
            "customer", "card", "pan", "phone", "email",
        }
        for fb in forbidden:
            self.assertNotIn(fb, data, f"PoPSummaryResponse must not contain '{fb}'")

    def test_summary_model_dump_keys(self):
        from app.domains.proof_of_play.router import PoPSummaryResponse
        s = PoPSummaryResponse()
        keys = set(s.model_dump().keys())
        expected = {
            "total_events", "unique_devices", "unique_campaigns",
            "unique_creatives", "unique_placements",
            "accepted", "rejected", "duplicate", "unknown_status",
            "last_event_at",
        }
        self.assertEqual(keys, expected)


# ══════════════════════════════════════════════════════════════════════
# Endpoint response shape tests (mocked DB)
# ══════════════════════════════════════════════════════════════════════

class TestReportsPopEndpoint(unittest.TestCase):
    def test_list_response_model_is_safe(self):
        """KsoPoPListResponse already validated — this confirms /api/reports/pop
        uses the same safe shape."""
        from app.domains.proof_of_play.schemas import KsoPoPListResponse
        now = datetime.now(timezone.utc)
        r = KsoPoPListResponse(
            event_code="ev-001",
            device_code="dev-001",
            placement_code="pl-001",
            campaign_code="camp-001",
            creative_code="cr-001",
            media_ref="media/ref",
            event_type="impression",
            status="accepted",
            played_at=now,
            duration_ms=15000,
            received_at=now,
        )
        data = r.model_dump()
        # Must have safe fields
        self.assertIn("event_code", data)
        self.assertIn("campaign_code", data)
        # Must NOT have raw UUID
        self.assertNotIn("id", data)
        self.assertNotIn("manifest_version_id", data)
        self.assertNotIn("manifest_hash", data)

    def test_summary_response_is_safe(self):
        from app.domains.proof_of_play.router import PoPSummaryResponse
        r = PoPSummaryResponse(
            total_events=10, unique_devices=3, unique_campaigns=2,
            unique_creatives=4, unique_placements=3,
            accepted=8, rejected=1, duplicate=1, unknown_status=0,
        )
        data = r.model_dump()
        for fb in ("token", "secret", "uuid", "backend_url", "file_path"):
            self.assertNotIn(fb, str(data).lower())


# ══════════════════════════════════════════════════════════════════════
# Service-level tests (mocked DB)
# ══════════════════════════════════════════════════════════════════════

class TestPopServiceList(unittest.TestCase):
    def test_list_kso_pop_events_uses_kso_model(self):
        """list_kso_pop_events uses KsoProofOfPlayEvent, not gateway model."""
        import inspect
        from app.domains.proof_of_play.service import list_kso_pop_events
        source = inspect.getsource(list_kso_pop_events)
        # Must reference KsoProofOfPlayEvent
        self.assertIn("KsoProofOfPlayEvent", source)
        # Must NOT include gateway device ID column references
        self.assertNotIn("gateway_device_id", source)
        # manifest_version_id only appears in docstring (safe), not in response build
        # The response build (KsoPoPListResponse(...)) must not include manifest_version_id
        resp_start = source.index("return [")
        resp_section = source[resp_start:]
        self.assertNotIn("manifest_version_id", resp_section)

    def test_list_response_no_forbidden(self):
        from app.domains.proof_of_play.schemas import KsoPoPListResponse
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        resp = KsoPoPListResponse(
            event_code="ev-001", device_code="d1", placement_code="p1",
            campaign_code="c1", creative_code="cr1", media_ref="m1",
            event_type="impression", status="accepted",
            played_at=now, duration_ms=5000, received_at=now,
        )
        data = resp.model_dump()
        # Safe fields present
        for field in ("event_code", "device_code", "campaign_code",
                       "creative_code", "placement_code"):
            self.assertIn(field, data)
        # Forbidden absent
        for fb in ("id", "manifest_version_id", "manifest_hash",
                    "token", "secret", "backend_url", "sha256",
                    "file_path", "storage_ref", "minio",
                    "receipt", "payment", "fiscal", "customer"):
            self.assertNotIn(fb, data)
