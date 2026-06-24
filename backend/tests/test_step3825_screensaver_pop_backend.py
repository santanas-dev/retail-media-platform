"""Step 38.2.5 — Backend PoP Ingest + Portal Report Integration Tests.

Extends existing TestKsoPoPServiceMock with screensaver-specific scenarios:
  - creative_code preserved through ingest
  - duplicate event_code idempotency
  - list with creative_code filter
  - blocked/draft handling
  - no forbidden fields in response/report

Uses mock DB session — no real backend server, no PostgreSQL.
"""

import asyncio
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.domains.proof_of_play.schemas import (
    KsoPoPIngestRequest,
    KsoPoPIngestResponse,
    KsoPoPListResponse,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers (consistent with existing test_z_proof_of_play_kso.py)
# ══════════════════════════════════════════════════════════════════════

def _make_mock_row(**kwargs):
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def _make_device(code="a-05954"):
    return _make_mock_row(id="kd1", device_code=code)


def _make_manifest(manifest_id="gm-uuid-1234", manifest_code="test-manifest",
                   device_code="a-05954", placement_code="test-place",
                   campaign_code="test-camp", manifest_body=None):
    body = manifest_body or {
        "items": [{"slotOrder": 0, "contentType": "image/png",
                    "mediaRef": "media/current/slot-000"}],
    }
    return _make_mock_row(
        id=manifest_id, manifest_code=manifest_code,
        device_code=device_code, placement_code=placement_code,
        campaign_code=campaign_code, manifest_body_json=body,
        published_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
        status="published",
    )


def _make_placement(placement_code="test-place", campaign_code="test-camp",
                    creative_code="test-creative"):
    return _make_mock_row(
        placement_code=placement_code, campaign_code=campaign_code,
        creative_code=creative_code,
    )


def _make_campaign_creative(campaign_id="c1", creative_code="test-creative"):
    return _make_mock_row(campaign_id=campaign_id, creative_code=creative_code)


def _build_happy_db(device_code="a-05954", creative_code="test-creative",
                    manifest_body=None, manifest_id="gm-uuid-1234"):
    """Build a happy-path mock DB with device→manifest→placement→campaign chain."""
    db = AsyncMock()
    call_count = [0]

    async def _execute(stmt, *args, **kwargs):
        call_count[0] += 1
        n = call_count[0]
        result = AsyncMock()

        if n == 1:  # KsoDevice
            result.scalar_one_or_none = MagicMock(
                return_value=_make_device(device_code))
        elif n == 2:  # GeneratedManifest
            result.scalar_one_or_none = MagicMock(
                return_value=_make_manifest(
                    manifest_id=manifest_id,
                    device_code=device_code,
                    manifest_body=manifest_body,
                ))
        elif n == 3:  # KsoPlacement
            result.scalar_one_or_none = MagicMock(
                return_value=_make_placement(creative_code=creative_code))
        elif n == 4:  # CampaignCreative
            result.scalar_one_or_none = MagicMock(
                return_value=_make_campaign_creative(creative_code=creative_code))
        elif n == 5:  # Duplicate check
            result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _run_ingest(db, device_code="a-05954", event_code="pop-001",
                media_ref="media/current/slot-000",
                event_type="playback_completed",
                manifest_version_id=None, manifest_hash=None):
    """Run ingest_kso_pop synchronously."""
    from app.domains.proof_of_play.service import ingest_kso_pop

    async def _do():
        req = KsoPoPIngestRequest(
            event_code=event_code, media_ref=media_ref,
            event_type=event_type, manifest_version_id=manifest_version_id,
            manifest_hash=manifest_hash,
        )
        return await ingest_kso_pop(db, device_code, req)
    return asyncio.get_event_loop().run_until_complete(_do())


# ══════════════════════════════════════════════════════════════════════
# Happy Path: creative_code preserved
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverPoPIngest(unittest.TestCase):
    """Backend ingest accepts screensaver PopPayloadEvent-compatible requests."""

    @classmethod
    def setUpClass(cls):
        from app.domains.identity.models import User  # noqa: F401

    def test_ingest_returns_creative_code(self):
        """Response must include creative_code from placement chain."""
        db = _build_happy_db(creative_code="summer-promo-v3")
        resp, err = _run_ingest(db, event_code="scr-e2e-001")
        self.assertIsNone(err)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, "summer-promo-v3")
        self.assertEqual(resp.device_code, "a-05954")
        self.assertEqual(resp.placement_code, "test-place")
        self.assertEqual(resp.campaign_code, "test-camp")

    def test_ingest_with_playback_completed_event_type(self):
        """playback_completed event_type accepted by backend."""
        db = _build_happy_db(creative_code="promo-playback")
        resp, err = _run_ingest(db, event_code="scr-playback-001",
                                event_type="playback_completed")
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, "promo-playback")

    def test_ingest_with_impression_event_type(self):
        """impression event_type accepted."""
        db = _build_happy_db(creative_code="promo-impression")
        resp, err = _run_ingest(db, event_code="scr-imp-001",
                                event_type="impression")
        self.assertIsNone(err)
        self.assertEqual(resp.creative_code, "promo-impression")

    def test_ingest_with_blocked_event_type(self):
        """blocked event_type — backend stores it (accepted, not rejected)."""
        db = _build_happy_db(creative_code="promo-blocked")
        resp, err = _run_ingest(db, event_code="scr-blocked-001",
                                event_type="blocked")
        self.assertIsNone(err)
        self.assertEqual(resp.creative_code, "promo-blocked")


# ══════════════════════════════════════════════════════════════════════
# Idempotency
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverIdempotency(unittest.TestCase):
    """Duplicate event_code → idempotent accepted, not duplicate INSERT."""

    @classmethod
    def setUpClass(cls):
        from app.domains.identity.models import User  # noqa: F401

    def test_duplicate_event_code_accepted(self):
        """Second POST with same event_code returns existing record."""
        db = AsyncMock()
        call_count = [0]

        async def _execute(stmt, *args, **kwargs):
            call_count[0] += 1
            n = call_count[0]
            result = AsyncMock()

            if n == 1:  # KsoDevice
                result.scalar_one_or_none = MagicMock(
                    return_value=_make_device())
            elif n == 2:  # GeneratedManifest
                result.scalar_one_or_none = MagicMock(
                    return_value=_make_manifest())
            elif n == 3:  # KsoPlacement
                result.scalar_one_or_none = MagicMock(
                    return_value=_make_placement(creative_code="idempotent-creative"))
            elif n == 4:  # CampaignCreative
                result.scalar_one_or_none = MagicMock(
                    return_value=_make_campaign_creative(creative_code="idempotent-creative"))
            elif n == 5:  # Duplicate check → found!
                existing = _make_mock_row(
                    event_code="scr-idem-001", device_code="a-05954",
                    placement_code="test-place", campaign_code="test-camp",
                    creative_code="idempotent-creative",
                    received_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
                )
                result.scalar_one_or_none = MagicMock(return_value=existing)
            return result

        db.execute = AsyncMock(side_effect=_execute)
        resp, err = _run_ingest(db, event_code="scr-idem-001")
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, "idempotent-creative")
        self.assertEqual(resp.event_code, "scr-idem-001")


# ══════════════════════════════════════════════════════════════════════
# List service with creative_code filter
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverListService(unittest.TestCase):
    """list_kso_pop_events with creative_code filter."""

    @classmethod
    def setUpClass(cls):
        from app.domains.identity.models import User  # noqa: F401

    def _run_list(self, db, **filters):
        from app.domains.proof_of_play.service import list_kso_pop_events

        async def _do():
            return await list_kso_pop_events(db, **filters)
        return asyncio.get_event_loop().run_until_complete(_do())

    def test_list_filters_by_creative_code(self):
        db = AsyncMock()
        result = AsyncMock()

        row = _make_mock_row(
            event_code="scr-list-001", device_code="a-05954",
            placement_code="test-place", campaign_code="test-camp",
            creative_code="filter-me", media_ref="media/current/slot-000",
            event_type="playback_completed", status="accepted",
            played_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=10000,
            received_at=datetime(2026, 6, 24, 12, 0, 10, tzinfo=timezone.utc),
        )
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        db.execute = AsyncMock(return_value=result)

        rows = self._run_list(db, creative_code="filter-me")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].creative_code, "filter-me")
        self.assertEqual(rows[0].event_type, "playback_completed")

    def test_list_filters_by_device_code(self):
        db = AsyncMock()
        result = AsyncMock()
        row = _make_mock_row(
            event_code="scr-dev-001", device_code="dev-filter",
            placement_code="p1", campaign_code="c1",
            creative_code="cr1", media_ref="m1",
            event_type="impression", status="accepted",
            played_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=5000,
            received_at=datetime(2026, 6, 24, 12, 0, 10, tzinfo=timezone.utc),
        )
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        db.execute = AsyncMock(return_value=result)

        rows = self._run_list(db, device_code="dev-filter")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].device_code, "dev-filter")

    def test_list_filters_by_campaign_code(self):
        db = AsyncMock()
        result = AsyncMock()
        row = _make_mock_row(
            event_code="scr-camp-001", device_code="d1",
            placement_code="p1", campaign_code="camp-filter",
            creative_code="cr1", media_ref="m1",
            event_type="impression", status="accepted",
            played_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=5000,
            received_at=datetime(2026, 6, 24, 12, 0, 10, tzinfo=timezone.utc),
        )
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        db.execute = AsyncMock(return_value=result)

        rows = self._run_list(db, campaign_code="camp-filter")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].campaign_code, "camp-filter")

    def test_list_filters_by_placement_code(self):
        db = AsyncMock()
        result = AsyncMock()
        row = _make_mock_row(
            event_code="scr-place-001", device_code="d1",
            placement_code="place-filter", campaign_code="c1",
            creative_code="cr1", media_ref="m1",
            event_type="impression", status="accepted",
            played_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=5000,
            received_at=datetime(2026, 6, 24, 12, 0, 10, tzinfo=timezone.utc),
        )
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        db.execute = AsyncMock(return_value=result)

        rows = self._run_list(db, placement_code="place-filter")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].placement_code, "place-filter")

    def test_list_empty_result(self):
        db = AsyncMock()
        result = AsyncMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result)

        rows = self._run_list(db, creative_code="no-such-creative")
        self.assertEqual(len(rows), 0)


# ══════════════════════════════════════════════════════════════════════
# Safety: no forbidden fields in response or report
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverResponseSafety(unittest.TestCase):
    """Ingest and list responses must NOT contain forbidden fields."""

    FORBIDDEN = [
        "id", "manifest_version_id", "manifest_hash",
        "backend_url", "token", "secret", "password", "api_key",
        "device_secret", "client_secret", "access_token",
        "file_path", "absolute_path", "local_path",
        "sha256", "storage_ref", "minio", "s3",
        "barcode", "scanner", "key_value", "key_payload",
        "receipt", "payment", "fiscal",
        "customer", "card", "pan", "phone", "email",
        "stacktrace",
    ]

    @classmethod
    def setUpClass(cls):
        from app.domains.identity.models import User  # noqa: F401

    def test_ingest_response_no_forbidden(self):
        db = _build_happy_db(creative_code="safe-creative")
        resp, err = _run_ingest(db, event_code="scr-safe-001")
        self.assertIsNone(err)
        data = resp.model_dump(mode="json")
        data_str = json.dumps(data).lower()
        for fb in self.FORBIDDEN:
            self.assertNotIn(fb, data_str,
                             f"Ingest response contains forbidden '{fb}'")

    def test_list_response_no_forbidden(self):
        """KsoPoPListResponse projection must be clean."""
        now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
        resp = KsoPoPListResponse(
            event_code="scr-proj-001", device_code="a-05954",
            placement_code="test-place", campaign_code="test-camp",
            creative_code="safe-creative", media_ref="media/current/slot-000",
            event_type="playback_completed", status="accepted",
            played_at=now, duration_ms=10000, received_at=now,
        )
        data = resp.model_dump(mode="json")
        data_str = json.dumps(data).lower()
        for fb in self.FORBIDDEN:
            self.assertNotIn(fb, data_str,
                             f"List response contains forbidden '{fb}'")

    def test_ingest_response_has_safe_fields_only(self):
        db = _build_happy_db()
        resp, err = _run_ingest(db, event_code="scr-fields-001")
        self.assertIsNone(err)
        data = resp.model_dump()
        allowed = {"status", "event_code", "device_code",
                   "placement_code", "campaign_code", "creative_code",
                   "received_at"}
        for key in data:
            self.assertIn(key, allowed, f"Unexpected key '{key}' in response")

    def test_list_response_has_safe_fields_only(self):
        now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
        resp = KsoPoPListResponse(
            event_code="scr-safe", device_code="d1",
            placement_code="p1", campaign_code="c1",
            creative_code="cr1", media_ref="m1",
            event_type="impression", status="accepted",
            received_at=now,
        )
        data = resp.model_dump()
        allowed = {"event_code", "device_code", "placement_code",
                   "campaign_code", "creative_code", "media_ref",
                   "event_type", "status", "played_at", "duration_ms",
                   "received_at"}
        for key in data:
            self.assertIn(key, allowed, f"Unexpected key '{key}' in list response")

    def test_ingest_response_no_raw_uuid(self):
        import re
        uuid_pat = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )
        db = _build_happy_db()
        resp, err = _run_ingest(db, event_code="scr-nouuid-001")
        self.assertIsNone(err)
        data_str = json.dumps(resp.model_dump(mode="json"))
        self.assertIsNone(
            uuid_pat.search(data_str),
            "Ingest response contains raw UUID"
        )


# ══════════════════════════════════════════════════════════════════════
# Blocked / draft event handling
# ══════════════════════════════════════════════════════════════════════

class TestBlockedDraftHandling(unittest.TestCase):
    """Blocked/draft events managed safely — not treated as playback."""

    @classmethod
    def setUpClass(cls):
        from app.domains.identity.models import User  # noqa: F401

    def test_blocked_event_accepted_not_rejected(self):
        """Backend accepts 'blocked' event_type — it stores it as-is."""
        db = _build_happy_db(creative_code="blocked-safe")
        resp, err = _run_ingest(db, event_code="scr-blocked-test",
                                event_type="blocked")
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, "blocked-safe")

    def test_ingest_request_minimal_fields(self):
        """KsoPoPIngestRequest requires only event_code + media_ref."""
        req = KsoPoPIngestRequest(
            event_code="scr-minimal",
            media_ref="media/current/slot-000",
        )
        self.assertEqual(req.event_code, "scr-minimal")
        self.assertEqual(req.event_type, "impression")  # default
        self.assertIsNone(req.manifest_version_id)  # optional

    def test_ingest_request_no_forbidden_in_dump(self):
        req = KsoPoPIngestRequest(
            event_code="scr-forbidden-test",
            media_ref="media/current/slot-000",
            event_type="playback_completed",
        )
        data = req.model_dump()
        data_str = json.dumps(data).lower()
        forbidden = ["receipt", "payment", "fiscal", "customer",
                     "phone", "email", "card", "pan", "sha256",
                     "token", "secret", "file_path", "backend_url",
                     "barcode", "scanner"]
        for fb in forbidden:
            self.assertNotIn(fb, data_str, f"Ingest request contains '{fb}'")
