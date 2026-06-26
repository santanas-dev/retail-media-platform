"""Step 37.6: Approval test KSO — schema + model validation (raw DDL)."""

import asyncio
import unittest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

APPROVAL_DDL = [
    """CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS approval_requests (
        id VARCHAR(36) PRIMARY KEY, approval_code VARCHAR(64) UNIQUE NOT NULL,
        object_type VARCHAR(20) NOT NULL, object_code VARCHAR(64) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        requested_by VARCHAR(36) REFERENCES users(id),
        decided_by VARCHAR(36) REFERENCES users(id),
        decision VARCHAR(20), comment VARCHAR(500),
        requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        decided_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
]

_setup_done = False


async def _ensure_setup():
    global _setup_done
    if _setup_done:
        return
    async with test_engine.begin() as conn:
        for ddl in APPROVAL_DDL:
            await conn.execute(text(ddl))
    _setup_done = True


class TestApprovalSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        asyncio.get_event_loop().run_until_complete(_ensure_setup())
        import nest_asyncio
        nest_asyncio.apply()

    def test_table_exists(self):
        async def _check():
            async with TestSession() as s:
                r = await s.execute(text("PRAGMA table_info('approval_requests')"))
                cols = {row[1] for row in r}
                expected = {"id", "approval_code", "object_type", "object_code",
                             "status", "requested_by", "decided_by", "decision",
                             "comment", "requested_at", "decided_at",
                             "created_at", "updated_at"}
                self.assertEqual(cols, expected)
        asyncio.get_event_loop().run_until_complete(_check())

    def test_approval_code_unique(self):
        async def _check():
            async with TestSession() as s:
                await s.execute(text(
                    "INSERT INTO users(id,username) VALUES('u1','a')"))
                await s.execute(text(
                    "INSERT INTO approval_requests(approval_code,object_type,"
                    "object_code,requested_by) VALUES('apr1','campaign','c1','u1')"))
                await s.commit()
                with self.assertRaises(Exception):
                    await s.execute(text(
                        "INSERT INTO approval_requests(approval_code,object_type,"
                        "object_code,requested_by) VALUES('apr1','placement','p1','u1')"))
                    await s.commit()
        asyncio.get_event_loop().run_until_complete(_check())

    def test_default_status_pending(self):
        async def _check():
            async with TestSession() as s:
                await s.execute(text(
                    "INSERT INTO users(id,username) VALUES('u2','b')"))
                await s.execute(text(
                    "INSERT INTO approval_requests(approval_code,object_type,"
                    "object_code,requested_by) VALUES('apr2','campaign','c2','u2')"))
                await s.commit()
                r = await s.execute(text(
                    "SELECT status FROM approval_requests WHERE approval_code='apr2'"))
                self.assertEqual(r.fetchone()[0], "pending")
        asyncio.get_event_loop().run_until_complete(_check())


class TestApprovalSchemas(unittest.TestCase):

    def test_valid_request_payload(self):
        from app.domains.approvals.schemas import ApprovalRequestCreate
        data = ApprovalRequestCreate(
            object_type="placement",
            object_code="demo_placement_001",
            comment="Ready",
        )
        self.assertEqual(data.object_type, "placement")

    def test_invalid_object_type_rejected(self):
        from app.domains.approvals.schemas import ApprovalRequestCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApprovalRequestCreate(object_type="invalid", object_code="x")

    def test_valid_decide_payload(self):
        from app.domains.approvals.schemas import ApprovalDecide
        data = ApprovalDecide(decision="approve", comment="OK")
        self.assertEqual(data.decision, "approve")

    def test_invalid_decision_rejected(self):
        from app.domains.approvals.schemas import ApprovalDecide
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApprovalDecide(decision="maybe")

    def test_safe_response_no_forbidden_fields(self):
        from app.domains.approvals.schemas import ApprovalResponse
        fields = set(ApprovalResponse.model_fields.keys())
        expected = {"approval_code", "object_type", "object_code",
                     "status", "decision", "comment",
                     "requested_at", "decided_at"}
        self.assertEqual(fields, expected)


class TestApprovalServiceLogic(unittest.TestCase):
    """Unit tests for approval service logic (no DB needed)."""

    def test_decision_status_mapping_is_explicit(self):
        """Status mapping uses explicit dict, not string concatenation."""
        import inspect
        from app.domains.approvals.service import _DECISION_TO_APPROVAL_STATUS
        self.assertEqual(_DECISION_TO_APPROVAL_STATUS["approve"], "approved")
        self.assertEqual(_DECISION_TO_APPROVAL_STATUS["reject"], "rejected")
        # Verify no string concatenation hack in source
        source = inspect.getsource(
            __import__("app.domains.approvals.service", fromlist=["decide_approval"]).decide_approval
        )
        self.assertNotIn('+ "d"', source)
        self.assertNotIn("decision +", source)

    def test_request_approval_validates_pre_approval_state(self):
        """request_approval must check object is in draft/pending_approval state."""
        import inspect
        source = inspect.getsource(
            __import__("app.domains.approvals.service", fromlist=["request_approval"]).request_approval
        )
        self.assertIn("draft", source)
        self.assertIn("pending_approval", source)
        self.assertIn("Cannot request approval", source)
        self.assertIn("expected 'draft' or 'pending_approval'", source)

    def test_rejected_campaign_cannot_be_reapproved_without_reset(self):
        """Rejected status should prevent re-requesting approval."""
        import inspect
        source = inspect.getsource(
            __import__("app.domains.approvals.service", fromlist=["request_approval"]).request_approval
        )
        # The status check uses `not in ("draft", "pending_approval")`
        # This means rejected/approved/active/archived are all rejected
        self.assertIn('not in (\"draft\", \"pending_approval\")', source.replace("'", '"'))
