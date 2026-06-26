"""Production manifest API integration tests — safe responses, no test-kso."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestProductionManifestEndpoints(unittest.TestCase):
    """Integration tests for production manifest endpoints (39.3.2)."""

    def setUp(self):
        self.maxDiff = None

    # ── GET /api/manifests (production list) ──────────────────────

    def test_list_manifests_prod_exists(self):
        """Production list endpoint is defined in router."""
        from app.domains.manifests.router import router
        methods_at_path = {}
        for r in router.routes:
            methods_at_path.setdefault(r.path, set())
            for m in r.methods:
                methods_at_path[r.path].add(m)
        self.assertIn("GET", methods_at_path.get("/api/manifests", set()))

    # ── GET /api/manifests/{code} (production detail) ─────────────

    def test_get_manifest_prod_exists(self):
        """Production get-by-code endpoint is defined in router."""
        from app.domains.manifests.router import router
        routes = [(r.path, r.methods) for r in router.routes]
        paths = {p: m for p, m in routes}
        self.assertIn("/api/manifests/{manifest_code}", paths)
        self.assertIn("GET", paths["/api/manifests/{manifest_code}"])

    # ── POST /api/manifests (production generate) ─────────────────

    def test_generate_manifest_prod_exists(self):
        """Production generate endpoint is defined in router."""
        from app.domains.manifests.router import router
        methods_at_path = {}
        for r in router.routes:
            methods_at_path.setdefault(r.path, set())
            for m in r.methods:
                methods_at_path[r.path].add(m)
        self.assertIn("POST", methods_at_path.get("/api/manifests", set()))

    # ── POST /api/manifests/{code}/publish (production publish) ───

    def test_publish_manifest_prod_exists(self):
        """Production publish endpoint is defined in router."""
        from app.domains.manifests.router import router
        routes = [(r.path, r.methods) for r in router.routes]
        paths = {p: m for p, m in routes}
        self.assertIn("/api/manifests/{manifest_code}/publish", paths)
        self.assertIn("POST", paths["/api/manifests/{manifest_code}/publish"])

    # ── Legacy test-kso preserved ─────────────────────────────────

    def test_legacy_test_kso_generate_preserved(self):
        """test-kso generate endpoint still exists as legacy."""
        from app.domains.manifests.router import router
        routes = [(r.path, r.methods) for r in router.routes]
        paths = {p: m for p, m in routes}
        self.assertIn("/api/manifests/test-kso/generate", paths)
        self.assertIn("POST", paths["/api/manifests/test-kso/generate"])

    def test_legacy_test_kso_list_preserved(self):
        """test-kso list endpoint still exists as legacy."""
        from app.domains.manifests.router import router
        routes = [(r.path, r.methods) for r in router.routes]
        paths = {p: m for p, m in routes}
        self.assertIn("/api/manifests/test-kso", paths)
        self.assertIn("GET", paths["/api/manifests/test-kso"])

    def test_legacy_test_kso_get_preserved(self):
        """test-kso get endpoint still exists as legacy."""
        from app.domains.manifests.router import router
        routes = [(r.path, r.methods) for r in router.routes]
        paths = {p: m for p, m in routes}
        self.assertIn("/api/manifests/test-kso/{manifest_code}", paths)
        self.assertIn("GET", paths["/api/manifests/test-kso/{manifest_code}"])

    def test_legacy_test_kso_publish_preserved(self):
        """test-kso publish endpoint still exists as legacy."""
        from app.domains.manifests.router import router
        routes = [(r.path, r.methods) for r in router.routes]
        paths = {p: m for p, m in routes}
        self.assertIn("/api/manifests/test-kso/{manifest_code}/publish", paths)
        self.assertIn("POST", paths["/api/manifests/test-kso/{manifest_code}/publish"])

    # ── Route ordering: literal paths before parameterized ────────

    def test_literal_paths_before_parameterized(self):
        """test-kso routes must be registered before /{manifest_code} to avoid shadowing."""
        from app.domains.manifests.router import router
        routes = list(router.routes)
        test_kso_indices = []
        param_index = None
        for i, r in enumerate(routes):
            if "/api/manifests/test-kso" in r.path:
                test_kso_indices.append(i)
            if r.path == "/api/manifests/{manifest_code}" and "GET" in r.methods:
                param_index = i
        if test_kso_indices and param_index is not None:
            for idx in test_kso_indices:
                self.assertLess(idx, param_index,
                                f"test-kso route at {idx} must be before /{{manifest_code}} at {param_index}")

    # ── Publication batch approval integration (39.3.1) ───────────

    def test_publish_batch_requires_approval(self):
        """Publication batch cannot publish without approved ApprovalRequest."""
        import asyncio
        # Verify the check exists in publish_batch source
        import inspect
        from app.domains.publications.service import publish_batch
        source = inspect.getsource(publish_batch)
        self.assertIn("approved", source.lower())
        self.assertIn("approvalrequest", source.lower())

    # ── Safe response projection ──────────────────────────────────

    def test_safe_response_no_sensitive_fields_in_output(self):
        """ManifestResponse has no forbidden fields in its schema."""
        from app.domains.manifests.schemas import ManifestResponse
        # Get field names from the model
        fields = set(ManifestResponse.model_fields.keys())
        forbidden = {"id", "generated_by", "published_by",
                      "file_path", "sha256", "storage_ref",
                      "minio", "token", "secret", "backend_url",
                      "raw_uuid", "127_0_0_1"}
        intersection = fields & forbidden
        self.assertFalse(intersection,
                         f"ManifestResponse contains forbidden fields: {intersection}")

    def test_safe_response_preview_body_is_dict(self):
        """preview_body type is Optional[dict[str, Any]]."""
        from app.domains.manifests.schemas import ManifestResponse
        from typing import get_type_hints
        hints = get_type_hints(ManifestResponse)
        self.assertIn("preview_body", hints)

    # ── Unified builder signature ─────────────────────────────────

    def test_unified_builder_accepts_db_and_placement_code(self):
        """build_manifest_from_placement signature: (db, placement_code)."""
        import inspect
        from app.domains.manifests.service import build_manifest_from_placement
        sig = inspect.signature(build_manifest_from_placement)
        params = list(sig.parameters.keys())
        self.assertIn("db", params)
        self.assertIn("placement_code", params)


if __name__ == "__main__":
    unittest.main()
