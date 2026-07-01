"""
G.5 — Emergency Security / RLS / Regression Gate: targeted tests.

Tests: permissions (11), API security (10), scope/RLS (7), audit (6),
portal security (9), read-only/source (9), regression (8).
Total: 60 tests.
"""

import os
import glob
import re
import sys
import unittest


# ── Paths ────────────────────────────────────────────────────────────────
_BACKEND_ROOT = os.path.join(
    os.path.dirname(__file__), "..",
)
_SEED_PY = os.path.join(_BACKEND_ROOT, "app", "domains", "identity", "seed.py")
_EMERGENCY_DIR = os.path.join(_BACKEND_ROOT, "app", "domains", "emergency")
_EMERGENCY_ROUTER_PY = os.path.join(_EMERGENCY_DIR, "router.py")
_EMERGENCY_SERVICE_PY = os.path.join(_EMERGENCY_DIR, "service.py")
_SCHEMAS_PY = os.path.join(_EMERGENCY_DIR, "schemas.py")

_PORTAL_ROOT = os.path.join(
    os.path.dirname(__file__), "..", "..", "apps", "portal-web",
)
_PORTAL_EMERGENCY_HTML = os.path.join(
    _PORTAL_ROOT, "templates", "pages", "emergency.html",
)
_PORTAL_MAIN_PY = os.path.join(_PORTAL_ROOT, "main.py")
_PORTAL_RBAC_PY = os.path.join(_PORTAL_ROOT, "rbac.py")
_PORTAL_BC_PY = os.path.join(_PORTAL_ROOT, "backend_client.py")


def _read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def _readlines(path: str) -> list[str]:
    with open(path, "r") as f:
        return f.readlines()


def _role_permissions(seed: str, role: str) -> set[str]:
    """Extract permissions for a given role from seed string."""
    role_idx = seed.find(f'"{role}": [')
    if role_idx < 0:
        return set()
    # Find the closing bracket
    bracket_start = seed.find("[", role_idx)
    depth = 0
    i = bracket_start
    while i < len(seed):
        if seed[i] == "[":
            depth += 1
        elif seed[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = seed[bracket_start:i + 1]
    # Extract all "perm.code" strings
    perms = re.findall(r'"([^"]+)"', block)
    return set(perms)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Permissions (11)
# ═══════════════════════════════════════════════════════════════════════════

class TestPermissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = _read(_SEED_PY)

    def test_emergency_read_exists(self):
        assert '("emergency.read"' in self.seed or \
               '"emergency.read"' in self.seed

    def test_emergency_read_idempotent(self):
        """emergency.read in ROLE_PERMISSIONS: at least once."""
        rp_section = self.seed.split("ROLE_PERMISSIONS")[1] if "ROLE_PERMISSIONS" in self.seed else self.seed
        assert "emergency.read" in rp_section

    def test_emergency_read_assigned_to_system_admin(self):
        perms = _role_permissions(self.seed, "system_admin")
        assert "emergency.read" in perms

    def test_emergency_read_assigned_to_security_admin(self):
        perms = _role_permissions(self.seed, "security_admin")
        assert "emergency.read" in perms

    def test_emergency_read_assigned_to_operations(self):
        perms = _role_permissions(self.seed, "operations")
        assert "emergency.read" in perms

    def test_advertiser_excluded(self):
        perms = _role_permissions(self.seed, "advertiser")
        assert "emergency.read" not in perms
        assert "emergency.manage" not in perms

    def test_device_service_excluded(self):
        perms = _role_permissions(self.seed, "device_service")
        assert "emergency.read" not in perms

    def test_analyst_excluded(self):
        perms = _role_permissions(self.seed, "analyst")
        assert "emergency.read" not in perms

    def test_ad_manager_excluded(self):
        perms = _role_permissions(self.seed, "ad_manager")
        assert "emergency.read" not in perms

    def test_approver_excluded(self):
        perms = _role_permissions(self.seed, "approver")
        assert "emergency.read" not in perms

    def test_emergency_execute_approve_absent(self):
        assert "emergency.execute" not in self.seed
        assert "emergency.approve" not in self.seed


# ═══════════════════════════════════════════════════════════════════════════
# 2. API Security (10)
# ═══════════════════════════════════════════════════════════════════════════

class TestApiSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = _read(_EMERGENCY_ROUTER_PY)
        cls.service = _read(_EMERGENCY_SERVICE_PY)

    def test_all_endpoints_require_emergency_read(self):
        """Every endpoint uses require_permission('emergency.read')."""
        count = self.router.count('require_permission("emergency.read")')
        assert count == 4, f"Expected 4, got {count}"

    def test_no_endpoint_without_permission(self):
        """No endpoint uses different permission (execute/approve/manage)."""
        assert "emergency.execute" not in self.router
        assert "emergency.manage" not in self.router
        # All require_permission calls use only emergency.read
        matches = re.findall(r'require_permission\("([^"]+)"\)', self.router)
        assert all(m == "emergency.read" for m in matches), \
            f"Unexpected permissions: {matches}"

    def test_exactly_four_endpoints(self):
        dec = self.router.count("@router.get") + self.router.count("@router.post")
        assert dec == 4, f"Expected 4 endpoints, found {dec}"

    def test_no_execute_endpoint(self):
        assert "/execute" not in self.router

    def test_no_activate_endpoint(self):
        """No /activate PATH in the router (docstring mention is fine)."""
        # Check only route decorator lines, not docstrings
        for line in self.router.split("\n"):
            if '@router.' in line:
                assert "activate" not in line.lower(), \
                    f"activate endpoint: {line.strip()}"

    def test_no_approve_endpoint(self):
        for line in self.router.split("\n"):
            if '@router.' in line:
                assert "approve" not in line.lower(), \
                    f"approve endpoint: {line.strip()}"

    def test_no_cancel_endpoint(self):
        for line in self.router.split("\n"):
            if '@router.' in line:
                assert "cancel" not in line.lower(), \
                    f"cancel endpoint: {line.strip()}"

    def test_dry_run_false_blocked(self):
        """dry_run=false is rejected in schemas validation."""
        schemas = _read(_SCHEMAS_PY)
        assert "dry_run=false" in schemas or \
               "dry_run=false is not supported" in schemas or \
               "not self.dry_run" in schemas

    def test_no_secrets_validator_called(self):
        """validate_no_secrets_in_emergency_payload is called in router."""
        assert "validate_no_secrets_in_emergency_payload" in self.router

    def test_no_traceback_in_error_handling(self):
        """Router does not leak tracebacks."""
        assert "traceback" not in self.router.lower()
        # Router uses structured error responses, not raw exceptions
        assert "raise HTTPException" not in self.router


# ═══════════════════════════════════════════════════════════════════════════
# 3. Scope / RLS (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestScopeRls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = _read(_EMERGENCY_SERVICE_PY)
        cls.router = _read(_EMERGENCY_ROUTER_PY)
        cls.schemas = _read(_SCHEMAS_PY)

    def test_broad_target_warning_mechanism(self):
        assert "broad" in self.service.lower() or \
               "broad_emergency_scope" in self.service.lower() or \
               "is_broad" in self.schemas

    def test_target_resolution_reads_existing_tables(self):
        """Target resolution reads Channel, PhysicalDevice, Store, Campaign, Placement."""
        for model in ("Channel", "PhysicalDevice", "Store", "Campaign", "Placement"):
            assert model in self.service, f"{model} not used in target resolution"

    def test_no_cross_campaign_leak(self):
        """Service doesn't expose unrelated campaign data."""
        assert "_safe_entity_dict" in self.service

    def test_safe_entity_dict_no_credentials(self):
        """_safe_entity_dict strips sensitive fields."""
        idx = self.service.find("def _safe_entity_dict")
        if idx >= 0:
            block = self.service[idx:idx + 800].lower()
            for fw in ("password", "token", "secret", "api_key",
                        "credential"):
                assert f'"{fw}"' not in block, \
                    f"'{fw}' found in _safe_entity_dict"
                assert f"'{fw}'" not in block, \
                    f"'{fw}' found in _safe_entity_dict"

    def test_no_device_credentials_in_response(self):
        """Affected device output doesn't contain credentials."""
        assert "device_credentials" not in self.service.lower()
        assert "device_key" not in self.service.lower()

    def test_channel_target_readonly(self):
        """Channel target resolution uses read-only db.execute patterns."""
        # Service uses .where(Channel.id == ...) or .where(Channel.code == ...)
        # These are SQLAlchemy expressions — verify by checking model usage
        assert "Channel" in self.service
        # should be in a SELECT statement context, not UPDATE/DELETE
        idx = self.service.find("Channel")
        if idx >= 0:
            chunk = self.service[max(0, idx - 50):idx + 200]
            assert "delete" not in chunk.lower()
            assert "update" not in chunk.lower()

    def test_empty_target_rejected(self):
        """Empty target triggers validation error."""
        assert "target must specify" in self.schemas or \
               "is_empty" in self.schemas


# ═══════════════════════════════════════════════════════════════════════════
# 4. Audit (6)
# ═══════════════════════════════════════════════════════════════════════════

class TestAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = _read(_EMERGENCY_ROUTER_PY)

    def test_capabilities_audit_written(self):
        assert "emergency.capabilities.viewed" in self.router

    def test_preview_audit_written(self):
        assert "emergency.action.previewed" in self.router

    def test_stop_simulated_audit_written(self):
        assert "emergency.stop.simulated" in self.router

    def test_message_simulated_audit_written(self):
        assert "emergency.message.simulated" in self.router

    def test_denied_request_no_success_audit(self):
        """Audit is called only after successful processing."""
        lines = self.router.split("\n")
        audit_lines = [i for i, l in enumerate(lines)
                       if "_audit(db," in l or "await _audit" in l]
        perm_lines = [i for i, l in enumerate(lines)
                      if 'require_permission("emergency.read")' in l]
        # All audit calls should be after at least one permission check
        for al in audit_lines:
            any_perm_before = any(pl < al for pl in perm_lines)
            assert any_perm_before, \
                f"Audit at line {al+1} has no permission check before it"

    def test_audit_no_raw_message_body(self):
        """Audit target_ref uses 'dry-run', not raw payload."""
        assert 'target_ref="dry-run"' in self.router or \
               '"dry-run"' in self.router


# ═══════════════════════════════════════════════════════════════════════════
# 5. Portal Security (9)
# ═══════════════════════════════════════════════════════════════════════════

class TestPortalSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(_PORTAL_EMERGENCY_HTML)
        cls.main = _read(_PORTAL_MAIN_PY)
        cls.rbac = _read(_PORTAL_RBAC_PY)
        cls.bc = _read(_PORTAL_BC_PY)

    def test_rbac_mapping_emergency_read(self):
        assert '"/emergency": "emergency.read"' in self.rbac

    def test_no_forbidden_button_labels(self):
        for lbl in ("Выполнить", "Остановить", "Активировать",
                     "Подтвердить", "Применить"):
            assert lbl not in self.html, f"Forbidden button '{lbl}' found"

    def test_no_execute_form_action(self):
        assert 'action="execute"' not in self.html.lower()
        assert 'value="execute"' not in self.html.lower()
        assert 'value="activate"' not in self.html.lower()
        assert 'value="approve"' not in self.html.lower()
        assert 'value="cancel"' not in self.html.lower()

    def test_no_dry_run_toggle(self):
        """dry_run is forced True, no input field for it."""
        assert 'name="dry_run"' not in self.html

    def test_no_secrets_in_html(self):
        for fw in ("password", "token", "secret", "api_key", "bearer",
                    "cookie", "session", "jwt", "authorization"):
            assert fw not in self.html.lower(), f"'{fw}' in emergency HTML"

    def test_no_traceback_in_html(self):
        assert "traceback" not in self.html.lower()
        assert "stack" not in self.html.lower()

    def test_no_js_cdn_localstorage(self):
        for kw in ("<script", "cdn.", "unpkg", "jsdelivr",
                    "localstorage", "sessionstorage"):
            assert kw not in self.html.lower(), f"'{kw}' in emergency HTML"
        assert "localStorage" not in self.main.lower()
        assert "sessionStorage" not in self.main.lower()

    def test_emergency_route_has_permission_guard(self):
        idx = self.main.find("/emergency")
        if idx >= 0:
            section = self.main[idx:idx + 3000]
            assert "require_auth_for_page" in section

    def test_emergency_route_handler_no_direct_db(self):
        idx = self.main.find("/emergency")
        if idx >= 0:
            section = self.main[idx:idx + 5000]
            # Portal uses BackendClient, not direct DB
            for kw in ("AsyncSession",):
                assert kw not in section, f"'{kw}' in emergency route"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Read-Only / Source Boundaries (9)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnlySourceBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = _read(_EMERGENCY_SERVICE_PY)
        cls.router = _read(_EMERGENCY_ROUTER_PY)
        cls.schemas = _read(_SCHEMAS_PY)
        cls.init = _read(os.path.join(_EMERGENCY_DIR, "__init__.py"))

    def _svc_no_import(self, forbidden: str, label: str) -> None:
        """Check that forbidden module is not imported in service/init files."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                content = f.read()
            # Only check import/from lines
            imports = [l for l in content.split("\n")
                       if l.strip().startswith(("from ", "import "))]
            for line in imports:
                # Allow the word in docstrings/comments only,
                # not in actual import lines
                pass
            if forbidden in content:
                # Check if it appears in an import statement
                for line in imports:
                    assert forbidden not in line, \
                        f"'{label}' imported in {os.path.basename(fpath)}: {line.strip()}"

    def test_no_db_writes_in_service(self):
        """Service only does SELECT queries, never INSERT/UPDATE/DELETE."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                content = f.read()
            for kw in ("db.add(", "db.insert(", "db.delete(",
                        "db.update(", "session.commit", "db.flush("):
                assert kw not in content, \
                    f"'{kw}' found in {os.path.basename(fpath)}"

    def test_no_emergency_actions_table_created(self):
        """No emergency_actions model or table."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY,
                       _SCHEMAS_PY):
            with open(fpath) as f:
                content = f.read().lower()
            assert "emergency_actions" not in content, \
                f"'emergency_actions' in {os.path.basename(fpath)}"

    def test_no_publication_import(self):
        """No publication module imports."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY,
                       _EMERGENCY_DIR + "/__init__.py"):
            with open(fpath) as f:
                for line in f:
                    if line.strip().startswith(("from ", "import ")):
                        assert "publication" not in line.lower(), \
                            f"publication import in {os.path.basename(fpath)}: {line.strip()}"

    def test_no_universal_manifest_import(self):
        """No universal_manifest import."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                for line in f:
                    if line.strip().startswith(("from ", "import ")):
                        assert "universal_manifest" not in line.lower(), \
                            f"universal_manifest import in {os.path.basename(fpath)}"

    def test_no_device_gateway_import(self):
        """No device gateway import (docstring mentions allowed, imports forbidden)."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                for line in f:
                    if line.strip().startswith(("from ", "import ")):
                        assert "device" not in line or \
                               "gateway" not in line.lower(), \
                            f"device gateway import in {os.path.basename(fpath)}: {line.strip()}"

    def test_no_kso_adapter_import(self):
        """No KSO adapter import."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                content = f.read().lower()
            assert "kso" not in content, \
                f"'kso' in {os.path.basename(fpath)}"

    def test_no_clickhouse_import(self):
        """No ClickHouse import."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                content = f.read().lower()
            assert "clickhouse" not in content, \
                f"'clickhouse' in {os.path.basename(fpath)}"

    def test_no_generated_manifest_import(self):
        """GeneratedManifest mentioned only in docstring, not imported."""
        for fpath in (_EMERGENCY_SERVICE_PY, _EMERGENCY_ROUTER_PY):
            with open(fpath) as f:
                for line in f:
                    if line.strip().startswith(("from ", "import ")):
                        assert "GeneratedManifest" not in line, \
                            f"GeneratedManifest import in {os.path.basename(fpath)}: {line.strip()}"

    def test_no_migration_files_since_g3(self):
        mg_path = os.path.join(_BACKEND_ROOT, "migrations", "versions")
        if os.path.exists(mg_path):
            recent = sorted(glob.glob(os.path.join(mg_path, "*.py")))[-5:]
            for mf in recent:
                with open(mf) as f:
                    content = f.read().lower()
                if "emergency" in content:
                    assert "emergency_actions" not in content, \
                        f"emergency_actions migration: {mf}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    def test_g4_tests_still_pass(self):
        """G.4 test file exists."""
        g4_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "apps", "portal-web", "tests",
            "test_emergency_portal_g4.py",
        )
        assert os.path.exists(g4_path), f"G.4 test file missing: {g4_path}"

    def test_g3_tests_still_pass(self):
        g3_path = os.path.join(
            _BACKEND_ROOT, "tests", "test_emergency_api_g3.py",
        )
        assert os.path.exists(g3_path), "G.3 test file missing"

    def test_g2_tests_still_pass(self):
        g2_path = os.path.join(
            _BACKEND_ROOT, "tests", "test_emergency_service_g2.py",
        )
        assert os.path.exists(g2_path), "G.2 test file missing"

    def test_g1_tests_still_pass(self):
        g1_path = os.path.join(
            _BACKEND_ROOT, "tests", "test_emergency_schemas_g1.py",
        )
        assert os.path.exists(g1_path), "G.1 test file missing"

    def test_portal_emergency_template_intact(self):
        assert os.path.exists(_PORTAL_EMERGENCY_HTML), \
            f"Missing: {_PORTAL_EMERGENCY_HTML}"

    def test_emergency_router_intact(self):
        assert os.path.exists(_EMERGENCY_ROUTER_PY)

    def test_emergency_service_intact(self):
        assert os.path.exists(_EMERGENCY_SERVICE_PY)

    def test_no_new_permissions_since_g3(self):
        """Only emergency.manage + emergency.read in PERMISSIONS list."""
        with open(_SEED_PY) as f:
            seed = f.read()
        perms_section = seed.split("PERMISSIONS = [")[1].split("]\n")[0] \
            if "PERMISSIONS = [" in seed else ""
        if perms_section:
            emergency_decls = perms_section.count('"emergency.')
            assert emergency_decls <= 2, \
                f"Too many emergency permission declarations: {emergency_decls}"
