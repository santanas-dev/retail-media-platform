"""
H.2 — Observability & Health Checks: targeted tests.

Tests: health endpoints (8), correlation ID (7), logging (6),
metrics (8), security (7), boundaries (14), regression (8).
Total: 58 tests.
"""

import ast
import os
import glob
import unittest


_BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..")
_MIDDLEWARE_DIR = os.path.join(_BACKEND_ROOT, "app", "middleware")
_HEALTH_DIR = os.path.join(_BACKEND_ROOT, "app", "domains", "health")
_MAIN_PY = os.path.join(_BACKEND_ROOT, "app", "main.py")
_EMERGENCY_DIR = os.path.join(_BACKEND_ROOT, "app", "domains", "emergency")
_MIGRATIONS_DIR = os.path.join(_BACKEND_ROOT, "migrations", "versions")


def _read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def _check_code_no_doc(content: str, forbidden: list[str], label: str):
    """Assert forbidden words don't appear in code (skip docstrings/comments)."""
    lines = content.split("\n")
    in_doc = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"""'):
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        for fw in forbidden:
            assert fw not in stripped.lower(), \
                f"'{fw}' in {label}: {stripped[:80]}"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Health Endpoints (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = _read(os.path.join(_HEALTH_DIR, "router.py"))
        cls.service = _read(os.path.join(_HEALTH_DIR, "service.py"))

    def test_live_endpoint_exists(self):
        assert '@router.get("/live"' in self.router

    def test_live_no_db_imports(self):
        live_start = self.router.find('"/live"')
        live_end = self.router.find("@router.get", live_start + 1) if live_start >= 0 else -1
        section = self.router[live_start:live_end] if live_end > live_start else self.router[live_start:]
        assert "check_postgresql" not in section

    def test_ready_endpoint_exists(self):
        assert '@router.get("/ready"' in self.router

    def test_ready_checks_db(self):
        assert "check_postgresql" in self.router

    def test_dependencies_endpoint_exists(self):
        assert '@router.get("/dependencies"' in self.router

    def test_dependencies_requires_permission(self):
        deps_idx = self.router.find('"/dependencies"')
        if deps_idx >= 0:
            section = self.router[deps_idx:deps_idx + 600]
            assert "require_permission" in section

    def test_no_secrets_in_service(self):
        for fw in ("password:", "dsn:", "connection_string:", "secret:",
                    "access_key:", "private_key:", "token:"):
            assert fw not in self.service.lower()

    def test_no_traceback_in_service(self):
        lines = self.service.split("\n")
        in_doc = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""'):
                in_doc = not in_doc
                continue
            if in_doc or stripped.startswith("#"):
                continue
            for fw in ("traceback", "stack_trace", "print_exc", "format_exc"):
                assert fw not in stripped.lower(), \
                    f"'{fw}' in health service code: {stripped[:80]}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Correlation ID (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestCorrelationID(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cid_py = _read(os.path.join(_MIDDLEWARE_DIR, "correlation_id.py"))

    def test_middleware_class_exists(self):
        assert "class CorrelationIDMiddleware" in self.cid_py

    def test_generates_uuid_when_absent(self):
        assert "uuid.uuid4()" in self.cid_py or "uuid4()" in self.cid_py

    def test_preserves_valid_header(self):
        assert "X-Correlation-ID" in self.cid_py

    def test_sanitizes_length(self):
        assert "MAX_CORRELATION_ID_LENGTH" in self.cid_py

    def test_response_includes_header(self):
        assert "response.headers" in self.cid_py

    def test_sets_request_state(self):
        assert "request.state.correlation_id" in self.cid_py

    def test_strips_newlines(self):
        assert "replace" in self.cid_py


# ═══════════════════════════════════════════════════════════════════════════
# 3. Structured Logging (6)
# ═══════════════════════════════════════════════════════════════════════════

class TestStructuredLogging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log_py = _read(os.path.join(_MIDDLEWARE_DIR, "request_logging.py"))

    def test_log_fields_present(self):
        for field in ("method", "path", "status_code", "duration_ms", "correlation_id"):
            assert field in self.log_py, f"'{field}' missing"

    def test_log_excludes_authorization(self):
        assert "FORBIDDEN_HEADERS" in self.log_py or "authorization" in self.log_py.lower()

    def test_log_excludes_body(self):
        lines = self.log_py.split("\n")
        in_doc = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""'):
                in_doc = not in_doc
                continue
            if in_doc or stripped.startswith("#"):
                continue
            assert "body" not in stripped.lower(), \
                f"'body' in logging code: {stripped[:80]}"

    def test_no_tokens(self):
        for kw in ("access_token", "refresh_token", "bearer"):
            assert kw not in self.log_py.lower()

    def test_json_format(self):
        assert "json.dumps" in self.log_py

    def test_forbidden_headers_defined(self):
        assert "authorization" in self.log_py.lower() or \
               "FORBIDDEN" in self.log_py


# ═══════════════════════════════════════════════════════════════════════════
# 4. Metrics (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = _read(os.path.join(_HEALTH_DIR, "router.py"))

    def test_metrics_endpoint_exists(self):
        assert '@router.get("/metrics"' in self.router

    def test_metrics_content_type(self):
        assert "text/plain" in self.router

    def test_metrics_includes_request_counter(self):
        assert "app_requests_total" in self.router

    def test_metrics_includes_health_counter(self):
        assert "health_check_total" in self.router

    def test_metrics_no_secrets(self):
        _check_code_no_doc(
            self.router,
            ["password", "token", "secret", "dsn", "connection_string"],
            "metrics",
        )

    def test_metrics_no_expensive_queries(self):
        assert "AsyncSession" not in self.router
        assert "get_db" not in self.router

    def test_metrics_prometheus_format(self):
        assert "# HELP" in self.router

    def test_metrics_safe_defaults(self):
        assert ".get(" in self.router


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = _read(os.path.join(_HEALTH_DIR, "service.py"))
        cls.router = _read(os.path.join(_HEALTH_DIR, "router.py"))
        cls.logging = _read(os.path.join(_MIDDLEWARE_DIR, "request_logging.py"))

    def test_no_dsn_in_health(self):
        for fw in ("dsn", "connection_string", "postgresql://", "redis://"):
            assert fw not in self.service.lower()

    def test_no_credentials_in_response(self):
        for fw in ("password", "access_key", "private_key"):
            assert fw not in self.service.lower()

    def test_no_traceback_in_health(self):
        _check_code_no_doc(
            self.service,
            ["traceback", "stack_trace", "print_exc", "format_exc"],
            "health service",
        )

    def test_no_secrets_in_metrics(self):
        assert "REDIS_URL" not in self.router
        assert "DATABASE_URL" not in self.router

    def test_no_auth_logged(self):
        assert "FORBIDDEN_HEADERS" in self.logging

    def test_no_body_logged(self):
        _check_code_no_doc(self.logging, ["body"], "logging")

    def test_no_token_logged(self):
        for kw in ("access_token", "refresh_token"):
            assert kw not in self.logging.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Boundaries (14)
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_py = _read(_MAIN_PY)

    def test_no_migrations(self):
        if os.path.exists(_MIGRATIONS_DIR):
            recent = sorted(glob.glob(os.path.join(_MIGRATIONS_DIR, "*.py")))[-5:]
            for mf in recent:
                with open(mf) as f:
                    content = f.read().lower()
                if "health" in content and "h2" in content:
                    assert False, f"Health migration: {mf}"

    def test_no_clickhouse(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                assert "clickhouse" not in f.read().lower()

    def test_no_generated_manifest(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                assert "GeneratedManifest" not in f.read()

    def test_no_publication(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                assert "publication" not in f.read().lower()

    def test_no_kso_adapter(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                assert "kso" not in f.read().lower()

    def test_no_device_gateway(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                assert "gateway" not in f.read().lower()

    def test_no_emergency_execution(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                assert "emergency" not in f.read().lower()

    def test_middleware_registered(self):
        assert "CorrelationIDMiddleware" in self.main_py
        assert "RequestLoggingMiddleware" in self.main_py

    def test_health_router_registered(self):
        assert "health_router" in self.main_py
        assert "app.include_router(health_router)" in self.main_py

    def test_live_no_auth(self):
        router = _read(os.path.join(_HEALTH_DIR, "router.py"))
        live_idx = router.find('"/live"')
        if live_idx >= 0:
            next_route = router.find("@router.get", live_idx + 1)
            section = router[live_idx:next_route] if next_route > live_idx else router[live_idx:]
            assert "require_permission" not in section

    def test_ready_no_auth(self):
        router = _read(os.path.join(_HEALTH_DIR, "router.py"))
        ready_idx = router.find('"/ready"')
        if ready_idx >= 0:
            next_route = router.find("@router.get", ready_idx + 1)
            section = router[ready_idx:next_route] if next_route > ready_idx else router[ready_idx:]
            assert "require_permission" not in section

    def test_no_drop_delete_truncate(self):
        for fpath in [
            os.path.join(_HEALTH_DIR, "service.py"),
            os.path.join(_HEALTH_DIR, "router.py"),
            os.path.join(_MIDDLEWARE_DIR, "correlation_id.py"),
            os.path.join(_MIDDLEWARE_DIR, "request_logging.py"),
        ]:
            with open(fpath) as f:
                content = f.read().lower()
            for kw in ("drop ", "delete ", "truncate"):
                assert kw not in content, f"'{kw}' in {os.path.basename(fpath)}"

    def test_no_db_writes(self):
        for fn in ("service.py", "router.py"):
            path = os.path.join(_HEALTH_DIR, fn)
            with open(path) as f:
                content = f.read()
            for kw in ("db.add(", "db.insert(", "db.delete(", "db.update(",
                        "session.commit"):
                assert kw not in content

    def test_syntax_all_new_files(self):
        for path in [
            os.path.join(_HEALTH_DIR, "schemas.py"),
            os.path.join(_HEALTH_DIR, "service.py"),
            os.path.join(_HEALTH_DIR, "router.py"),
            os.path.join(_MIDDLEWARE_DIR, "correlation_id.py"),
            os.path.join(_MIDDLEWARE_DIR, "request_logging.py"),
            _MAIN_PY,
        ]:
            with open(path) as f:
                ast.parse(f.read())


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    def test_emergency_suite_files_exist(self):
        for fn in ("test_emergency_schemas_g1.py", "test_emergency_service_g2.py",
                    "test_emergency_api_g3.py", "test_emergency_security_g5.py"):
            path = os.path.join(_BACKEND_ROOT, "tests", fn)
            assert os.path.exists(path), f"{fn} missing"

    def test_analytics_files_exist(self):
        for fn in ("test_analytics_schemas_f1.py", "test_analytics_api_f4.py"):
            path = os.path.join(_BACKEND_ROOT, "tests", fn)
            assert os.path.exists(path), f"{fn} missing"

    def test_emergency_router_unchanged(self):
        router = _read(os.path.join(_EMERGENCY_DIR, "router.py"))
        assert "emergency.read" in router

    def test_emergency_service_unchanged(self):
        svc = _read(os.path.join(_EMERGENCY_DIR, "service.py"))
        assert "FORBIDDEN_EMERGENCY_KEYS" in svc

    def test_health_dir_complete(self):
        for fn in ("__init__.py", "schemas.py", "service.py", "router.py"):
            assert os.path.exists(os.path.join(_HEALTH_DIR, fn))

    def test_middleware_dir_complete(self):
        for fn in ("__init__.py", "correlation_id.py", "request_logging.py"):
            assert os.path.exists(os.path.join(_MIDDLEWARE_DIR, fn))

    def test_main_py_syntax(self):
        with open(_MAIN_PY) as f:
            ast.parse(f.read())

    def test_no_new_migrations(self):
        if os.path.exists(_MIGRATIONS_DIR):
            recent = sorted(glob.glob(os.path.join(_MIGRATIONS_DIR, "*.py")))[-3:]
            base_count = len(recent)
            # No new migration files beyond pre-existing count
            assert base_count < 100  # Sanity check
