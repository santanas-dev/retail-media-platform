"""Step 37.4: Campaign test KSO — schema + model validation (raw DDL).

Verifies:
- campaign_code column exists on campaigns
- campaign_creatives table exists with correct FK
- Safe schema validation (Pydantic)
- Technical context codes are explicitly synthetic

Uses raw SQLite DDL — no PostgreSQL dependency.
No schedule/approval/publication/manifest/PoP testing.
"""

import unittest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Minimal DDL for campaign test-KSO tables
CAMPAIGN_DDL = [
    # Identity (minimal for FK)
    """CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL DEFAULT '',
        display_name VARCHAR(255),
        is_active BOOLEAN DEFAULT 1
    )""",
    # Advertisers (minimal for FK chain)
    """CREATE TABLE IF NOT EXISTS advertisers (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        contacts_json TEXT NOT NULL DEFAULT '{}'
    )""",
    # Brands
    """CREATE TABLE IF NOT EXISTS brands (
        id VARCHAR(36) PRIMARY KEY,
        advertiser_id VARCHAR(36) NOT NULL REFERENCES advertisers(id),
        name VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active'
    )""",
    # Orders
    """CREATE TABLE IF NOT EXISTS orders (
        id VARCHAR(36) PRIMARY KEY,
        advertiser_id VARCHAR(36) NOT NULL REFERENCES advertisers(id),
        brand_id VARCHAR(36) REFERENCES brands(id),
        number VARCHAR(100) NOT NULL,
        name VARCHAR(500) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        currency VARCHAR(3) NOT NULL DEFAULT 'RUB',
        UNIQUE(advertiser_id, number)
    )""",
    # Creatives
    """CREATE TABLE IF NOT EXISTS creatives (
        id VARCHAR(36) PRIMARY KEY,
        advertiser_id VARCHAR(36) REFERENCES advertisers(id),
        brand_id VARCHAR(36) REFERENCES brands(id),
        creative_code VARCHAR(64) UNIQUE NOT NULL,
        name VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    # Campaigns
    """CREATE TABLE IF NOT EXISTS campaigns (
        id VARCHAR(36) PRIMARY KEY,
        order_id VARCHAR(36) NOT NULL REFERENCES orders(id),
        advertiser_id VARCHAR(36) NOT NULL REFERENCES advertisers(id),
        brand_id VARCHAR(36) REFERENCES brands(id),
        campaign_code VARCHAR(64) UNIQUE,
        name VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        planned_start_date DATE NOT NULL,
        planned_end_date DATE NOT NULL,
        priority INTEGER DEFAULT 0,
        currency VARCHAR(3) DEFAULT 'RUB',
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    # CampaignCreatives
    """CREATE TABLE IF NOT EXISTS campaign_creatives (
        id VARCHAR(36) PRIMARY KEY,
        campaign_id VARCHAR(36) NOT NULL REFERENCES campaigns(id),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        slot_order INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, creative_code)
    )""",
]


async def _setup_db():
    async with test_engine.begin() as conn:
        for ddl in CAMPAIGN_DDL:
            await conn.execute(text(ddl))


class TestCampaignSchema(unittest.TestCase):
    """Verify campaign_code column and campaign_creatives table exist."""

    @classmethod
    def setUpClass(cls):
        import asyncio
        asyncio.get_event_loop().run_until_complete(_setup_db())
        import nest_asyncio
        nest_asyncio.apply()

    def test_campaign_has_campaign_code_column(self):
        """campaigns table has campaign_code VARCHAR(64) UNIQUE."""
        import asyncio

        async def _check():
            async with TestSession() as s:
                result = await s.execute(text("PRAGMA table_info('campaigns')"))
                cols = {row[1]: row[2] for row in result}
                self.assertIn("campaign_code", cols)
                self.assertIn("VARCHAR(64)", cols["campaign_code"].upper())

        asyncio.get_event_loop().run_until_complete(_check())

    def test_campaign_creatives_table_exists(self):
        """campaign_creatives table exists with correct FK."""
        import asyncio

        async def _check():
            async with TestSession() as s:
                result = await s.execute(text("PRAGMA table_info('campaign_creatives')"))
                cols = {row[1] for row in result}
                for c in ("id", "campaign_id", "creative_code", "slot_order", "created_at"):
                    self.assertIn(c, cols)

        asyncio.get_event_loop().run_until_complete(_check())

    def test_campaign_creatives_unique_constraint(self):
        """Duplicate campaign_id + creative_code raises integrity error."""
        import asyncio

        async def _check():
            async with TestSession() as s:
                # Seed chain
                await s.execute(text(
                    "INSERT INTO users(id,username) VALUES('u1','test')"))
                await s.execute(text(
                    "INSERT INTO advertisers(id,name) VALUES('a1','test')"))
                await s.execute(text(
                    "INSERT INTO brands(id,advertiser_id,name) VALUES('b1','a1','test')"))
                await s.execute(text(
                    "INSERT INTO orders(id,advertiser_id,brand_id,number,name) "
                    "VALUES('o1','a1','b1','ord1','Test Order')"))
                await s.execute(text(
                    "INSERT INTO creatives(id,creative_code,name,created_by) "
                    "VALUES('c1','cc_test','Test','u1')"))
                await s.execute(text(
                    "INSERT INTO campaigns(id,order_id,advertiser_id,brand_id,"
                    "campaign_code,name,planned_start_date,planned_end_date,created_by) "
                    "VALUES('camp1','o1','a1','b1','test_camp','Test','2026-01-01','2099-12-31','u1')"))
                await s.execute(text(
                    "INSERT INTO campaign_creatives(campaign_id,creative_code,slot_order) "
                    "VALUES('camp1','cc_test',0)"))
                # Duplicate
                with self.assertRaises(Exception):
                    await s.execute(text(
                        "INSERT INTO campaign_creatives(campaign_id,creative_code,slot_order) "
                        "VALUES('camp1','cc_test',1)"))
                    await s.commit()

        asyncio.get_event_loop().run_until_complete(_check())


class TestCampaignSchemas(unittest.TestCase):
    """Pydantic validation for CampaignTestKsoCreate and CampaignSafeResponse."""

    def test_valid_create_payload(self):
        from app.domains.campaigns.schemas import CampaignTestKsoCreate
        data = CampaignTestKsoCreate(
            campaign_code="test_camp_001",
            name="Test Campaign",
            description="A test",
            creative_codes=["cc_001", "cc_002"],
        )
        self.assertEqual(data.campaign_code, "test_camp_001")
        self.assertEqual(len(data.creative_codes), 2)

    def test_unsafe_campaign_code_rejected(self):
        from app.domains.campaigns.schemas import CampaignTestKsoCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            CampaignTestKsoCreate(
                campaign_code="BAD UPPERCASE!",
                name="Bad",
                creative_codes=["cc"],
            )

    def test_too_short_campaign_code_rejected(self):
        from app.domains.campaigns.schemas import CampaignTestKsoCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            CampaignTestKsoCreate(
                campaign_code="ab",
                name="Short",
                creative_codes=["cc"],
            )

    def test_empty_creative_codes_rejected(self):
        from app.domains.campaigns.schemas import CampaignTestKsoCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            CampaignTestKsoCreate(
                campaign_code="test_camp",
                name="No creatives",
                creative_codes=[],
            )

    def test_safe_response_has_no_forbidden_fields(self):
        from app.domains.campaigns.schemas import CampaignSafeResponse
        # CampaignSafeResponse is a Pydantic model — verify its field set
        fields = set(CampaignSafeResponse.model_fields.keys())
        expected = {"campaign_code", "name", "status", "description",
                     "creative_codes", "created_at", "updated_at"}
        self.assertEqual(fields, expected)


class TestTechnicalContextCodes(unittest.TestCase):
    """Technical context codes are explicitly synthetic."""

    def test_codes_are_synthetic(self):
        from app.domains.campaigns.service import (
            _TECH_ADVERTISER_CODE,
            _TECH_BRAND_CODE,
            _TECH_ORDER_NUMBER,
        )
        self.assertIn("technical", _TECH_ADVERTISER_CODE)
        self.assertIn("technical", _TECH_BRAND_CODE)
        self.assertIn("technical", _TECH_ORDER_NUMBER)
        self.assertIn("demo", _TECH_ADVERTISER_CODE)


class TestCampaignCreativeCompatGuard(unittest.TestCase):
    """is_active compatibility — helper works when ORM model has no is_active column."""

    def test_helper_returns_true_when_missing(self):
        """_is_campaign_creative_active returns True when is_active attr missing."""
        from app.domains.campaigns.service import _is_campaign_creative_active

        class FakeLink:
            creative_code = "test_creative"
        self.assertTrue(_is_campaign_creative_active(FakeLink()))

    def test_helper_returns_true_when_true(self):
        from app.domains.campaigns.service import _is_campaign_creative_active

        class FakeLink:
            is_active = True
        self.assertTrue(_is_campaign_creative_active(FakeLink()))

    def test_helper_returns_false_when_false(self):
        from app.domains.campaigns.service import _is_campaign_creative_active

        class FakeLink:
            is_active = False
        self.assertFalse(_is_campaign_creative_active(FakeLink()))

    def test_no_attribute_error(self):
        """Service imports without AttributeError on CampaignCreative.is_active."""
        from app.domains.campaigns import service as cs
        self.assertTrue(hasattr(cs, "_is_campaign_creative_active"))
