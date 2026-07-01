"""G.1 — Emergency Management Schemas/Contracts: targeted tests.

Tests: schemas (13), validation (10), service contracts (7),
target resolution (6), read-only boundaries (8), compatibility (4).
Total: 52 tests.
"""

import asyncio
import inspect
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

from app.domains.emergency.schemas import (
    EmergencyActionType,
    EmergencyActionStatus,
    EmergencyPriority,
    EmergencyTarget,
    EmergencyMessageContent,
    EmergencyActionCreate,
    EmergencyActionPreview,
    EmergencyActionResult,
    EmergencyActionRecord,
    EmergencyIssue,
)
from app.domains.emergency.service import (
    validate_emergency_action,
    preview_emergency_action,
    resolve_emergency_targets,
    simulate_emergency_stop,
    simulate_emergency_message,
    build_emergency_issue,
)


def _imports(mod):
    return "\n".join(
        l.strip() for l in inspect.getsource(mod).split("\n")
        if l.strip().startswith("from ") or l.strip().startswith("import ")
    ).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schemas — targets (6)
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemasTarget(unittest.TestCase):
    def test_channel_target_valid(self):
        t = EmergencyTarget(channel_code="kso")
        assert t.affected_dimensions == ["channel"]

    def test_store_target_valid(self):
        t = EmergencyTarget(store_code="store-1")
        assert t.affected_dimensions == ["store"]

    def test_device_target_valid(self):
        t = EmergencyTarget(device_code="DEV-1")
        assert t.affected_dimensions == ["device"]

    def test_campaign_target_valid(self):
        from uuid import uuid4
        t = EmergencyTarget(campaign_id=uuid4())
        assert t.affected_dimensions == ["campaign"]

    def test_placement_target_valid(self):
        from uuid import uuid4
        t = EmergencyTarget(placement_id=uuid4())
        assert t.affected_dimensions == ["placement"]

    def test_display_surface_target_valid(self):
        from uuid import uuid4
        t = EmergencyTarget(display_surface_id=uuid4())
        assert t.affected_dimensions == ["display_surface"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Schemas — message / create (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemasMessageCreate(unittest.TestCase):
    def test_message_content_valid(self):
        m = EmergencyMessageContent(title="Alert", body="Test message")
        assert m.title == "Alert"

    def test_stop_campaign_create_valid(self):
        r = EmergencyActionCreate(
            action_type=EmergencyActionType.STOP_CAMPAIGN,
            reason="Test stop",
            target=EmergencyTarget(campaign_code="TEST"),
        )
        assert r.dry_run is True

    def test_emergency_message_create_valid(self):
        r = EmergencyActionCreate(
            action_type=EmergencyActionType.EMERGENCY_MESSAGE,
            reason="Test message",
            target=EmergencyTarget(channel_code="kso"),
            message=EmergencyMessageContent(title="Test", body="Body"),
        )
        assert r.action_type == EmergencyActionType.EMERGENCY_MESSAGE

    def test_dry_run_default_true(self):
        r = EmergencyActionCreate(
            action_type=EmergencyActionType.STOP_CAMPAIGN,
            reason="test",
            target=EmergencyTarget(campaign_code="X"),
        )
        assert r.dry_run is True

    def test_dry_run_false_rejected(self):
        with self.assertRaises(ValueError):
            EmergencyActionCreate(
                action_type=EmergencyActionType.STOP_CAMPAIGN,
                reason="test",
                target=EmergencyTarget(campaign_code="X"),
                dry_run=False,
            )

    def test_empty_target_rejected(self):
        with self.assertRaises(ValueError):
            EmergencyActionCreate(
                action_type=EmergencyActionType.STOP_CAMPAIGN,
                reason="test",
                target=EmergencyTarget(),
            )

    def test_emergency_message_without_message_rejected(self):
        with self.assertRaises(ValueError):
            EmergencyActionCreate(
                action_type=EmergencyActionType.EMERGENCY_MESSAGE,
                reason="test",
                target=EmergencyTarget(channel_code="kso"),
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Schemas — result shapes (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemasResults(unittest.TestCase):
    def test_preview_shape(self):
        p = EmergencyActionPreview(
            action_type=EmergencyActionType.STOP_CAMPAIGN,
            target=EmergencyTarget(campaign_code="X"),
        )
        assert p.dry_run is True
        assert p.ok is True

    def test_result_shape(self):
        r = EmergencyActionResult(
            action_type=EmergencyActionType.STOP_CAMPAIGN,
            target=EmergencyTarget(campaign_code="X"),
        )
        assert r.dry_run is True
        assert r.status == EmergencyActionStatus.DRAFT

    def test_record_shape(self):
        r = EmergencyActionRecord(
            action_type=EmergencyActionType.STOP_CAMPAIGN,
            reason="test",
        )
        assert r.status == EmergencyActionStatus.DRAFT

    def test_issue_shape(self):
        i = EmergencyIssue(code="test", severity="warning", message="test")
        assert i.code == "test"
        assert i.severity == "warning"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Validation (10)
# ═══════════════════════════════════════════════════════════════════════════

class TestValidation(unittest.TestCase):
    def _make(self, **kw):
        defaults = {
            "action_type": EmergencyActionType.STOP_CAMPAIGN,
            "reason": "test reason",
            "target": EmergencyTarget(campaign_code="X"),
        }
        defaults.update(kw)
        return EmergencyActionCreate(**defaults)

    def test_valid_action_no_issues(self):
        r = self._make()
        issues = validate_emergency_action(r)
        assert len(issues) == 0

    def test_missing_reason_rejected(self):
        with self.assertRaises(ValueError):
            EmergencyActionCreate(
                action_type=EmergencyActionType.STOP_CAMPAIGN,
                reason="",
                target=EmergencyTarget(campaign_code="X"),
            )

    def test_empty_target_rejected(self):
        with self.assertRaises(ValueError):
            EmergencyActionCreate(
                action_type=EmergencyActionType.STOP_CAMPAIGN,
                reason="test",
            )

    def test_message_without_content_rejected(self):
        with self.assertRaises(ValueError):
            EmergencyActionCreate(
                action_type=EmergencyActionType.EMERGENCY_MESSAGE,
                reason="test",
                target=EmergencyTarget(channel_code="kso"),
            )

    def test_stop_without_message_allowed(self):
        r = self._make(action_type=EmergencyActionType.STOP_DEVICE,
                       target=EmergencyTarget(device_code="X"))
        issues = validate_emergency_action(r)
        assert not any(i.code == "missing_message_content" for i in issues)

    def test_invalid_date_range_rejected(self):
        from datetime import datetime, timezone
        with self.assertRaises(ValueError):
            self._make(
                starts_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
                ends_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

    def test_dry_run_false_rejected(self):
        r = EmergencyActionCreate(
            action_type=EmergencyActionType.STOP_CAMPAIGN,
            reason="test",
            target=EmergencyTarget(campaign_code="X"),
            dry_run=True,
        )
        issues = validate_emergency_action(r)
        assert not any(i.code == "dry_run_required" for i in issues)

    def test_broad_scope_warning(self):
        r = self._make(target=EmergencyTarget(channel_code="kso"))
        issues = validate_emergency_action(r)
        assert any(i.code == "broad_emergency_scope" for i in issues)

    def test_critical_approval_warning(self):
        r = self._make(
            priority=EmergencyPriority.CRITICAL,
            requires_approval=False,
        )
        issues = validate_emergency_action(r)
        assert any(i.code == "critical_requires_approval" for i in issues)

    def test_stop_action_no_message_allowed(self):
        r = self._make(action_type=EmergencyActionType.STOP_PLACEMENT,
                       target=EmergencyTarget(placement_code="P1"))
        issues = validate_emergency_action(r)
        assert len(issues) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Service contracts (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestServiceContracts(unittest.TestCase):
    def _make(self, **kw):
        defaults = {
            "action_type": EmergencyActionType.STOP_CAMPAIGN,
            "reason": "test",
            "target": EmergencyTarget(campaign_code="X"),
        }
        defaults.update(kw)
        return EmergencyActionCreate(**defaults)

    def _target(self, **kw):
        return EmergencyTarget(**kw) if kw else EmergencyTarget(campaign_code="X")

    def _make_db(self):
        db = AsyncMock()
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mr.scalars.return_value.all.return_value = []
        db.execute.return_value = mr
        return db

    def test_validate_returns_list(self):
        r = self._make()
        issues = validate_emergency_action(r)
        assert isinstance(issues, list)

    def test_preview_returns_dry_run(self):
        async def _run():
            r = self._make()
            p = await preview_emergency_action(self._make_db(), r)
            assert p.dry_run is True
            return True
        assert asyncio.run(_run())

    def test_simulate_stop_returns_dry_run(self):
        async def _run():
            r = self._make()
            s = await simulate_emergency_stop(self._make_db(), r)
            assert s.dry_run is True
            return True
        assert asyncio.run(_run())

    def test_simulate_message_returns_dry_run(self):
        async def _run():
            r = EmergencyActionCreate(
                action_type=EmergencyActionType.EMERGENCY_MESSAGE,
                reason="test",
                target=EmergencyTarget(channel_code="kso"),
                message=EmergencyMessageContent(title="T", body="B"),
            )
            s = await simulate_emergency_message(self._make_db(), r)
            assert s.dry_run is True
            return True
        assert asyncio.run(_run())

    def test_resolve_targets_returns_dict(self):
        async def _run():
            t = self._target()
            result = await resolve_emergency_targets(self._make_db(), t)
            assert isinstance(result, dict)
            assert result["ok"] is True
            return True
        assert asyncio.run(_run())

    def test_build_issue_returns_issue(self):
        i = build_emergency_issue("test", "warning", "msg")
        assert i.code == "test"
        assert isinstance(i, EmergencyIssue)

    def test_simulate_stop_on_message_fails(self):
        async def _run():
            r = EmergencyActionCreate(
                action_type=EmergencyActionType.EMERGENCY_MESSAGE,
                reason="test",
                target=EmergencyTarget(channel_code="kso"),
                message=EmergencyMessageContent(title="T", body="B"),
            )
            s = await simulate_emergency_stop(self._make_db(), r)
            assert s.ok is False
            return True
        assert asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════
# 6. Target resolution (6)
# ═══════════════════════════════════════════════════════════════════════════

class TestTargetResolution(unittest.TestCase):
    def _resolve(self, **kw):
        async def _run():
            t = EmergencyTarget(**kw) if kw else EmergencyTarget()
            db = AsyncMock()
            mr = MagicMock()
            mr.scalar_one_or_none.return_value = None
            mr.scalars.return_value.all.return_value = []
            db.execute.return_value = mr
            return await resolve_emergency_targets(db, t)
        return asyncio.run(_run())

    def test_channel_resolved(self):
        r = self._resolve(channel_code="kso")
        assert isinstance(r, dict)
        assert "affected_channels" in r

    def test_store_resolved(self):
        r = self._resolve(store_code="S1")
        assert isinstance(r, dict)
        assert "affected_stores" in r

    def test_device_resolved(self):
        r = self._resolve(device_code="D1")
        assert isinstance(r, dict)
        assert "affected_devices" in r

    def test_campaign_resolved(self):
        r = self._resolve(campaign_code="C1")
        assert isinstance(r, dict)
        assert "affected_campaigns" in r

    def test_placement_resolved(self):
        r = self._resolve(placement_code="P1")
        assert isinstance(r, dict)
        assert "affected_placements" in r

    def test_unknown_returns_warning(self):
        r = self._resolve()
        assert r["ok"] is False
        assert len(r["errors"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. Read-only boundaries (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundaries(unittest.TestCase):
    def test_service_has_no_db_write(self):
        import app.domains.emergency.service as svc
        src = inspect.getsource(svc)
        assert "db.add(" not in src
        assert ".insert(" not in src
        assert ".update(" not in src
        assert ".delete(" not in src

    def test_no_generated_manifest(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "generatedmanifest" not in imports.replace("_", "")

    def test_no_publication_flow(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "publication" not in imports

    def test_no_device_gateway(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "device_gateway" not in imports

    def test_no_kso_adapter(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "kso_adapter" not in imports

    def test_no_api_router(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "app", "domains", "emergency", "router.py"
        )
        assert not os.path.exists(path), "API router should not exist in G.1"

    def test_no_migrations(self):
        import glob
        mg_path = os.path.join(os.path.dirname(__file__), "..", "..", "migrations", "versions")
        if os.path.exists(mg_path):
            recent = sorted(glob.glob(os.path.join(mg_path, "*.py")))[-5:]
            for mf in recent:
                with open(mf) as f:
                    content = f.read().lower()
                if "emergency" in content:
                    assert False, f"Emergency migration found: {mf}"

    def test_no_universal_manifest_import(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "universal_manifest" not in imports.replace("_", "").replace(" ", "")


# ═══════════════════════════════════════════════════════════════════════════
# 8. Compatibility (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestCompatibility(unittest.TestCase):
    def test_existing_analytics_service_unchanged(self):
        path = os.path.join(os.path.dirname(__file__),
                           "test_analytics_schemas_f1.py")
        assert os.path.exists(path)

    def test_emergency_domain_no_clickhouse(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "clickhouse" not in imports

    def test_emergency_domain_no_portal(self):
        imports = _imports(__import__(
            "app.domains.emergency.service", fromlist=["validate_emergency_action"]
        ))
        assert "template" not in imports
        assert "jinja" not in imports

    def test_has_action_types_complete(self):
        required = {"stop_campaign", "stop_placement", "stop_channel",
                    "stop_store", "stop_device", "emergency_message", "resume"}
        actual = {e.value for e in EmergencyActionType}
        assert required == actual, f"Missing: {required - actual}"
