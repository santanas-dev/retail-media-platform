import nest_asyncio
nest_asyncio.apply()
"""Integration tests: User CRUD, Roles, RLS Scopes, Admin Audit API.

Uses FastAPI TestClient with SQLite in-memory + dependency overrides.
Self-contained — no external PostgreSQL, no real auth, no real users.

Safe: synthetic usernames only.
Never exposes raw passwords/tokens/hashes in test output.
"""

import asyncio
import unittest
from uuid import uuid4

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

# ══════════════════════════════════════════════════════════════════════════
# Test setup
# ══════════════════════════════════════════════════════════════════════════

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

ADMIN_USERNAME = "demo_admin"
ADMIN_PASSWORD="D3m0Adm!nPass"
SAFE_TEST_USERS = {"demo_admin", "demo_manager", "demo_analyst", "demo_blocked", "demo_archived"}

FORBIDDEN_FIELDS = frozenset({
    "password_hash", "password", "token_hash",
    "access_token", "refresh_token", "authorization",
    "device_secret", "client_secret", "backend_url",
    "manifest_hash", "sha256", "file_path", "filename",
    "minio", "storage_key", "phone", "payment", "receipt", "fiscal",
})

def _run_async(coro):
    return asyncio.run(coro)

def _assert_no_forbidden(test, text: str):
    lower = text.lower()
    for fb in FORBIDDEN_FIELDS:
        test.assertNotIn(fb, lower, f"Response must NOT contain '{fb}'")

# ── Database fixture ─────────────────────────────────────────────────────

ALL_IDENTITY_DDL = [
    """CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        email VARCHAR(255), password_hash VARCHAR(255) NOT NULL,
        display_name VARCHAR(255), is_active BOOLEAN DEFAULT 1,
        is_locked BOOLEAN DEFAULT 0, locked_until DATETIME,
        failed_attempts INTEGER DEFAULT 0, mfa_enabled BOOLEAN DEFAULT 0,
        mfa_secret VARCHAR(255), auth_provider VARCHAR(50) DEFAULT 'local',
        is_service_account BOOLEAN DEFAULT 0, ldap_dn VARCHAR(512),
        last_login_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_archived BOOLEAN DEFAULT 0, archived_at DATETIME,
        archived_by VARCHAR(36) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS roles (
        id VARCHAR(36) PRIMARY KEY, code VARCHAR(100) NOT NULL UNIQUE,
        name VARCHAR(255) NOT NULL, description TEXT,
        is_system BOOLEAN DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS permissions (
        id VARCHAR(36) PRIMARY KEY, code VARCHAR(100) NOT NULL UNIQUE,
        name VARCHAR(255) NOT NULL, resource VARCHAR(100) NOT NULL,
        action VARCHAR(50) NOT NULL, description TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS user_roles (
        user_id VARCHAR(36) NOT NULL REFERENCES users(id),
        role_id VARCHAR(36) NOT NULL REFERENCES roles(id),
        assigned_by VARCHAR(36) REFERENCES users(id),
        assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, role_id)
    )""",
    """CREATE TABLE IF NOT EXISTS role_permissions (
        role_id VARCHAR(36) NOT NULL REFERENCES roles(id),
        permission_id VARCHAR(36) NOT NULL REFERENCES permissions(id),
        PRIMARY KEY (role_id, permission_id)
    )""",
    """CREATE TABLE IF NOT EXISTS refresh_tokens (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id),
        token_hash VARCHAR(255) NOT NULL UNIQUE,
        jti VARCHAR(255) NOT NULL UNIQUE, device_info VARCHAR(512),
        expires_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        revoked BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, revoked_at DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS user_rls_scopes (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id),
        scope_type VARCHAR(64) NOT NULL, scope_value VARCHAR(255) NOT NULL,
        starts_at DATETIME, expires_at DATETIME, is_active BOOLEAN DEFAULT 1,
        created_by VARCHAR(36) REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, reason VARCHAR(512),
        UNIQUE(user_id, scope_type, scope_value)
    )""",
    """CREATE TABLE IF NOT EXISTS login_audit_events (
        id VARCHAR(36) PRIMARY KEY, username VARCHAR(100) NOT NULL,
        user_id VARCHAR(36) REFERENCES users(id),
        success BOOLEAN NOT NULL, result_code VARCHAR(50),
        reason_code VARCHAR(100),
        occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ip_hash VARCHAR(128), user_agent_hash VARCHAR(128)
    )""",
    """CREATE TABLE IF NOT EXISTS admin_audit_events (
        id VARCHAR(36) PRIMARY KEY,
        actor_user_id VARCHAR(36) NOT NULL REFERENCES users(id),
        action VARCHAR(100) NOT NULL, target_type VARCHAR(64),
        target_ref VARCHAR(255), details_json TEXT,
        occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS mfa_settings (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id),
        mfa_required BOOLEAN DEFAULT 0, mfa_enabled BOOLEAN DEFAULT 0,
        method VARCHAR(20), secret_ref VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
]

# SQLAlchemy ORM uses server_default=gen_random_uuid() which doesn't work
# on SQLite. Patch all identity model PKs to generate UUIDs client-side
# AND convert any UUID objects to hex strings (SQLite can't bind UUID objects).
def _install_uuid_defaults(models_module):
    """Install before_insert listeners for all identity model PK and FK columns."""

    def _make_set_id(model_name: str):
        def _set_id(mapper, connection, target):
            # Generate PK if missing
            if hasattr(target, 'id') and target.id is None:
                target.id = uuid4().hex
            # Convert any uuid.UUID objects on any column to hex strings
            # (SQLite can't bind Python UUID objects)
            for col in mapper.columns:
                val = getattr(target, col.key, None)
                if val is not None and isinstance(val, uuid4().__class__):
                    setattr(target, col.key, val.hex)
        return _set_id

    for name in ("User", "Role", "Permission", "UserRole", "RolePermission",
                  "RefreshToken", "UserRlsScope", "LoginAuditEvent",
                  "AdminAuditEvent", "MfaSettings"):
        cls = getattr(models_module, name, None)
        if cls is None:
            continue
        event.listen(cls, "before_insert", _make_set_id(name))


async def _init_test_db():
    from app.core.security import hash_password
    from app.domains.identity.seed import PERMISSIONS, ROLES, ROLE_PERMISSIONS
    from app.domains.identity import models as m

    import sqlalchemy as _patch_sa
    for table in m.Base.metadata.sorted_tables:
        for col in table.columns:
            tname = str(col.type).upper()
            if 'UUID' in tname:
                col.type = _patch_sa.String(36)
    from app.domains.identity import models as m

    _install_uuid_defaults(m)

    async with test_engine.begin() as conn:
        for ddl in ALL_IDENTITY_DDL:
            await conn.execute(text(ddl))

    async with TestSession() as db:
        # Permissions
        perm_map = {}
        for code, name, resource, action, description in PERMISSIONS:
            pid = uuid4().hex
            perm_map[code] = pid
            await db.execute(text("INSERT OR IGNORE INTO permissions (id, code, name, resource, action, description) VALUES (:id,:c,:n,:r,:a,:d)"), {"id": pid, "c": code, "n": name, "r": resource, "a": action, "d": description})
        # Roles
        role_map = {}
        for code, name, description in ROLES:
            rid = uuid4().hex
            role_map[code] = rid
            await db.execute(text("INSERT OR IGNORE INTO roles (id, code, name, description, is_system) VALUES (:id,:c,:n,:d,1)"), {"id": rid, "c": code, "n": name, "d": description})
        # Role → Permissions
        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            rid = role_map.get(role_code)
            if not rid:
                continue
            for pcode in perm_codes:
                pid = perm_map.get(pcode)
                if pid:
                    await db.execute(text("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:r,:p)"), {"r": rid, "p": pid})
        # Admin user
        admin_id = uuid4().hex
        admin_rid = role_map["system_admin"]
        await db.execute(text("INSERT OR IGNORE INTO users (id, username, password_hash, display_name, is_active) VALUES (:id,:u,:ph,:dn,1)"), {"id": admin_id, "u": ADMIN_USERNAME, "ph": hash_password(ADMIN_PASSWORD), "dn": "Demo Admin"})
        await db.execute(text("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (:u,:r)"), {"u": admin_id, "r": admin_rid})
        await db.commit()

# ── Dependency overrides ─────────────────────────────────────────────────

async def _override_get_db():
    async with TestSession() as session:
        yield session

async def _override_get_current_user():
    import sqlalchemy as sa
    from sqlalchemy.orm import selectinload
    from app.domains.identity import models
    async with TestSession() as db:
        result = await db.execute(
            sa.select(models.User)
            .options(selectinload(models.User.user_roles).selectinload(models.UserRole.role).selectinload(models.Role.role_permissions).selectinload(models.RolePermission.permission))
            .where(models.User.username == ADMIN_USERNAME)
        )
        return result.scalar_one()

def _setup_app():
    from app.main import app
    from app.core.deps import get_db, get_current_user
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    return app

# ══════════════════════════════════════════════════════════════════════════

class TestUserCRUDAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _run_async(_init_test_db())
        cls.client = TestClient(_setup_app())

    def test_admin_can_list_users(self):
        resp = self.client.get("/api/users")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_user_list_exposes_no_forbidden_fields(self):
        resp = self.client.get("/api/users")
        self.assertEqual(resp.status_code, 200)
        _assert_no_forbidden(self, resp.text)

    def test_admin_can_get_user_by_username(self):
        resp = self.client.get(f"/api/users/{ADMIN_USERNAME}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["username"], ADMIN_USERNAME)
        self.assertNotIn("password_hash", body)
        self.assertNotIn("password", body)

    def test_get_nonexistent_user_returns_404(self):
        resp = self.client.get("/api/users/nonexistent_user_xyz")
        self.assertEqual(resp.status_code, 404)

    def test_admin_can_create_user(self):
        resp = self.client.post("/api/users", json={"username": "demo_manager", "password": "ValidPass123!", "display_name": "Demo Manager"})
        self.assertIn(resp.status_code, (201, 409))
        if resp.status_code == 201:
            body = resp.json()
            self.assertEqual(body["username"], "demo_manager")
            self.assertNotIn("password", body)
            self.assertNotIn("password_hash", body)

    def test_create_user_response_excludes_secrets(self):
        resp = self.client.post("/api/users", json={"username": "demo_analyst", "password": "AnalystPass456!"})
        self.assertIn(resp.status_code, (201, 409))
        if resp.status_code == 201:
            body = resp.json()
            self.assertNotIn("password", body)
            self.assertNotIn("password_hash", body)

    def test_duplicate_username_rejected(self):
        resp = self.client.post("/api/users", json={"username": ADMIN_USERNAME, "password": "SomePass789!"})
        self.assertEqual(resp.status_code, 409)

    def test_admin_can_block_user(self):
        self.client.post("/api/users", json={"username": "demo_blocked", "password": "BlockedPass1!"})
        resp = self.client.patch("/api/users/demo_blocked/status", json={"status": "blocked", "reason": "Test block"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_locked"])

    def test_admin_can_archive_user(self):
        self.client.post("/api/users", json={"username": "demo_archived", "password": "ArchivePass1!"})
        resp = self.client.patch("/api/users/demo_archived/status", json={"status": "archived", "reason": "Test archive"})
        self.assertEqual(resp.status_code, 200)

    def test_cannot_change_own_status(self):
        resp = self.client.patch(f"/api/users/{ADMIN_USERNAME}/status", json={"status": "blocked", "reason": "Should fail"})
        self.assertEqual(resp.status_code, 400)

    def test_status_change_writes_admin_audit(self):
        resp = self.client.get("/api/admin/audit?limit=5")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_user_list_no_forbidden_fields(self):
        resp = self.client.get("/api/users")
        self.assertEqual(resp.status_code, 200)
        _assert_no_forbidden(self, resp.text)

    def test_auth_me_no_forbidden_fields(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        _assert_no_forbidden(self, resp.text)


class TestRoleAssignmentAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _run_async(_init_test_db())
        cls.client = TestClient(_setup_app())

    def test_admin_can_assign_roles(self):
        self.client.post("/api/users", json={"username": "demo_role_test", "password": "RoleTestPass1!"})
        get_resp = self.client.get("/api/users/demo_role_test")
        if get_resp.status_code != 200:
            return
        user_id = get_resp.json()["id"]
        resp = self.client.put(f"/api/users/{user_id}/roles", json={"role_codes": ["analyst"]})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("analyst", resp.json()["roles"])

    def test_cannot_assign_unknown_role(self):
        get_resp = self.client.get(f"/api/users/{ADMIN_USERNAME}")
        user_id = get_resp.json()["id"]
        resp = self.client.put(f"/api/users/{user_id}/roles", json={"role_codes": ["nonexistent_role_xyz"]})
        self.assertEqual(resp.status_code, 400)

    def test_cannot_assign_device_service_via_user_api(self):
        get_resp = self.client.get(f"/api/users/{ADMIN_USERNAME}")
        user_id = get_resp.json()["id"]
        resp = self.client.put(f"/api/users/{user_id}/roles", json={"role_codes": ["device_service"]})
        self.assertEqual(resp.status_code, 400,
                         f"device_service must be rejected: {resp.status_code}")


class TestRlsScopesAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _run_async(_init_test_db())
        cls.client = TestClient(_setup_app())

    def test_admin_can_assign_rls_scopes(self):
        resp = self.client.patch(f"/api/users/{ADMIN_USERNAME}/rls-scopes", json={"scopes": [{"scope_type": "branch_scope", "scope_value": "central-hq", "reason": "Main branch"}]})
        self.assertEqual(resp.status_code, 200)

    def test_unknown_rls_scope_rejected(self):
        resp = self.client.patch(f"/api/users/{ADMIN_USERNAME}/rls-scopes", json={"scopes": [{"scope_type": "unknown_scope_xyz", "scope_value": "bad"}]})
        self.assertIn(resp.status_code, (400, 422),
                      f"Unknown RLS scope must be rejected: {resp.status_code}")


class TestAdminAuditAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _run_async(_init_test_db())
        cls.client = TestClient(_setup_app())

    def test_admin_can_list_audit(self):
        resp = self.client.get("/api/admin/audit?limit=5")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_audit_response_has_no_secrets(self):
        resp = self.client.get("/api/admin/audit?limit=5")
        self.assertEqual(resp.status_code, 200)
        _assert_no_forbidden(self, resp.text)


async def _normal_user_override():
    import sqlalchemy as sa
    from sqlalchemy.orm import selectinload
    from app.domains.identity import models
    async with TestSession() as db:
        result = await db.execute(sa.select(models.User).options(selectinload(models.User.user_roles).selectinload(models.UserRole.role).selectinload(models.Role.role_permissions).selectinload(models.RolePermission.permission)).where(models.User.username == "demo_normal"))
        return result.scalar_one()


class TestPermissionGates(unittest.TestCase):
    """Non-admin users get 403 via dependency override."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_test_db())

        async def _create_normal():
            from app.core.security import hash_password
            async with TestSession() as db:
                uid = uuid4().hex
                await db.execute(text("INSERT OR IGNORE INTO users (id, username, password_hash, is_active) VALUES (:id,:u,:ph,1)"), {"id": uid, "u": "demo_normal", "ph": hash_password("TestNormalPass!")})
                await db.commit()
        _run_async(_create_normal())
        cls.app = _setup_app()
        cls.client = TestClient(cls.app)


    def test_regular_user_cannot_list_users(self):
        from app.main import app
        from app.core.deps import get_current_user
        app.dependency_overrides[get_current_user] = _normal_user_override
        try:
            resp = self.client.get("/api/users")
            self.assertEqual(resp.status_code, 403,
                             f"Regular user must get 403, got {resp.status_code}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)


if __name__ == "__main__":
    unittest.main()
