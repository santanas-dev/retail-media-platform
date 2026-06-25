"""Step 39.1.2 — Campaign / Placement Production API Tests.

Tests for:
- Campaign code-based CRUD
- CampaignCreative binding
- Placement production CRUD
All tests use mocked DB — no live server.
"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ══════════════════════════════════════════════════════════════════════
# Campaign Code-Based Lookup + Archive Tests
# ══════════════════════════════════════════════════════════════════════

class TestCampaignCodeLookup(unittest.TestCase):
    """Test get_campaign_by_code service function."""

    def test_finds_campaign_by_code(self):
        from app.domains.campaigns.service import get_campaign_by_code
        from app.domains.campaigns import models

        db = AsyncMock()
        mock_campaign = MagicMock(spec=models.Campaign)
        mock_campaign.campaign_code = "test-camp-001"
        mock_campaign.name = "Test"

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = mock_campaign
            return m
        db.execute = mock_execute

        import asyncio
        result = asyncio.run(get_campaign_by_code(db, "test-camp-001"))
        self.assertIsNotNone(result)
        self.assertEqual(result.campaign_code, "test-camp-001")

    def test_returns_none_for_unknown_code(self):
        from app.domains.campaigns.service import get_campaign_by_code

        db = AsyncMock()
        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            return m
        db.execute = mock_execute

        import asyncio
        result = asyncio.run(get_campaign_by_code(db, "nonexistent"))
        self.assertIsNone(result)


class TestCampaignArchive(unittest.TestCase):
    """Test archive_campaign service function."""

    def test_archives_active_campaign(self):
        from app.domains.campaigns.service import archive_campaign
        from app.domains.campaigns import models

        db = AsyncMock()
        campaign = MagicMock(spec=models.Campaign)
        campaign.status = "active"
        campaign.campaign_code = "test-camp"

        async def mock_get(model, obj_id):
            return campaign
        db.get = mock_get

        import asyncio
        result = asyncio.run(archive_campaign(db, uuid4()))
        self.assertEqual(result.status, "archived")

    def test_already_archived_raises(self):
        from app.domains.campaigns.service import archive_campaign
        from app.domains.campaigns import models
        from fastapi import HTTPException

        db = AsyncMock()
        campaign = MagicMock(spec=models.Campaign)
        campaign.status = "archived"

        async def mock_get(model, obj_id):
            return campaign
        db.get = mock_get

        import asyncio
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(archive_campaign(db, uuid4()))
        self.assertEqual(ctx.exception.status_code, 400)


# ══════════════════════════════════════════════════════════════════════
# CampaignCreative Binding Tests
# ══════════════════════════════════════════════════════════════════════

class TestCampaignCreativeBinding(unittest.TestCase):
    """Test bind/unbind campaign creative service functions."""

    def test_bind_creative_idempotent(self):
        """Binding same creative twice returns existing — idempotent."""
        from app.domains.campaigns.service import bind_campaign_creative
        from app.domains.campaigns import models

        db = AsyncMock()
        campaign = MagicMock(spec=models.Campaign)
        binding = MagicMock(spec=models.CampaignCreative)
        binding.creative_code = "test-creative-001"
        binding.is_active = True
        binding.created_at = datetime.now(timezone.utc)

        creative = MagicMock()
        creative.creative_code = "test-creative-001"

        async def mock_get(model, obj_id):
            if "Campaign" in str(model):
                return campaign
            return None

        call_count = [0]
        async def mock_execute(stmt):
            m = MagicMock()
            if "Creatives" in str(stmt) or "creative_code" in str(stmt):
                if call_count[0] == 0:
                    m.scalar_one_or_none.return_value = creative
                    call_count[0] += 1
                else:
                    m.scalar_one_or_none.return_value = binding
            else:
                m.scalar_one_or_none.return_value = None
            return m

        db.get = mock_get
        db.execute = mock_execute

        import asyncio
        result = asyncio.run(bind_campaign_creative(db, uuid4(), "test-creative-001"))
        self.assertEqual(result["creative_code"], "test-creative-001")
        self.assertTrue(result["is_active"])

    def test_unbind_deactivates(self):
        """Unbinding sets is_active=False."""
        from app.domains.campaigns.service import unbind_campaign_creative
        from app.domains.campaigns import models

        db = AsyncMock()
        binding = MagicMock(spec=models.CampaignCreative)
        binding.creative_code = "test-creative-001"
        binding.is_active = True
        binding.created_at = datetime.now(timezone.utc)

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = binding
            return m
        db.execute = mock_execute

        import asyncio
        result = asyncio.run(unbind_campaign_creative(db, uuid4(), "test-creative-001"))
        self.assertFalse(result["is_active"])


# ══════════════════════════════════════════════════════════════════════
# Placement Production API Tests
# ══════════════════════════════════════════════════════════════════════

class TestPlacementUpdate(unittest.TestCase):
    """Test update_placement service function."""

    def test_updates_fields(self):
        from app.domains.scheduling.service import update_placement
        from app.domains.scheduling import models, schemas

        db = AsyncMock()
        p = MagicMock(spec=models.KsoPlacement)
        p.placement_code = "test-place-001"
        p.status = "draft"
        p.campaign_code = "test-camp"
        p.creative_code = "test-creative"
        p.device_code = "test-device"
        p.starts_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        p.ends_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        p.slot_order = 0
        p.created_at = datetime.now(timezone.utc)
        p.updated_at = datetime.now(timezone.utc)

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = p
            return m
        db.execute = mock_execute

        import asyncio
        new_ends = datetime(2026, 12, 1, tzinfo=timezone.utc)
        data = schemas.KsoPlacementUpdate(ends_at=new_ends, slot_order=1)
        result = asyncio.run(update_placement(db, "test-place-001", data))
        self.assertEqual(result["slot_order"], 1)

    def test_archived_placement_cannot_update(self):
        from app.domains.scheduling.service import update_placement
        from app.domains.scheduling import models, schemas
        from fastapi import HTTPException

        db = AsyncMock()
        p = MagicMock(spec=models.KsoPlacement)
        p.status = "archived"

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = p
            return m
        db.execute = mock_execute

        import asyncio
        data = schemas.KsoPlacementUpdate(slot_order=1)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_placement(db, "test-place-001", data))
        self.assertEqual(ctx.exception.status_code, 400)


class TestPlacementArchive(unittest.TestCase):
    """Test archive_placement service function."""

    def test_archives_active_placement(self):
        from app.domains.scheduling.service import archive_placement
        from app.domains.scheduling import models

        db = AsyncMock()
        p = MagicMock(spec=models.KsoPlacement)
        p.placement_code = "test-place"
        p.status = "draft"
        p.campaign_code = "test-camp"
        p.creative_code = "test-creative"
        p.device_code = "test-device"
        p.starts_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        p.ends_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        p.slot_order = 0
        p.created_at = datetime.now(timezone.utc)
        p.updated_at = datetime.now(timezone.utc)

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = p
            return m
        db.execute = mock_execute

        import asyncio
        result = asyncio.run(archive_placement(db, "test-place"))
        self.assertEqual(result["status"], "archived")
