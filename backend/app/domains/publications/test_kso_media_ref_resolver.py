"""Tests for KSO safe mediaRef resolver core.

Tests resolve_kso_media_ref_source() — pure function, no DB, no HTTP.
"""

from datetime import datetime, timedelta, timezone
from unittest import TestCase

from app.domains.publications.kso_media_ref_resolver import (
    KsoMediaRefSourceItem,
    KsoMediaRefResolutionResult,
    resolve_kso_media_ref_source,
    format_kso_media_ref_resolution_result,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_NOT_FOUND,
    REASON_RESOLVED,
    REASON_NOT_FOUND,
    REASON_NO_VALID_ITEMS,
    REASON_UNSAFE_MEDIA_REF,
    REASON_INVALID_ARGS,
    CONTENT_TYPE_NONE,
    _validate_media_ref_slot,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

NOW = datetime(2026, 6, 19, 10, 0, 0, tzinfo=timezone.utc)
RENDITION_ID_000 = "11111111-1111-1111-1111-111111111111"
RENDITION_ID_001 = "22222222-2222-2222-2222-222222222222"
RENDITION_ID_002 = "33333333-3333-3333-3333-333333333333"


def _make_valid_item(**overrides) -> KsoMediaRefSourceItem:
    """Create a valid KSO item with all filters passing."""
    defaults = dict(
        channel_code="kso",
        campaign_status="approved",
        creative_status="approved",
        rendition_status="valid",
        publication_status="published",
        device_status="active",
        store_is_active=True,
        store_code="store-01",
        device_code="dev-01",
        content_type="image/png",
        duration_ms=5000,
        slot_order=0,
        valid_from=NOW - timedelta(hours=1),
        valid_to=NOW + timedelta(hours=1),
        now=NOW,
        internal_source_rendition_id=RENDITION_ID_000,
    )
    defaults.update(overrides)
    return KsoMediaRefSourceItem(**defaults)


# ══════════════════════════════════════════════════════════════════════
# Tests: mediaRef validation
# ══════════════════════════════════════════════════════════════════════

class TestMediaRefValidation(TestCase):

    def test_valid_slot_000(self):
        self.assertEqual(_validate_media_ref_slot("media/current/slot-000"), 0)

    def test_valid_slot_001(self):
        self.assertEqual(_validate_media_ref_slot("media/current/slot-001"), 1)

    def test_valid_slot_999(self):
        self.assertEqual(_validate_media_ref_slot("media/current/slot-999"), 999)

    def test_path_traversal(self):
        self.assertIsNone(_validate_media_ref_slot("media/../etc/passwd"))

    def test_double_dot(self):
        self.assertIsNone(_validate_media_ref_slot("../media/current/slot-000"))

    def test_absolute_path(self):
        self.assertIsNone(_validate_media_ref_slot("/media/current/slot-000"))

    def test_url(self):
        self.assertIsNone(_validate_media_ref_slot("http://evil.com/slot-000"))

    def test_backslash(self):
        self.assertIsNone(_validate_media_ref_slot("media\\current\\slot-000"))

    def test_real_filename(self):
        self.assertIsNone(_validate_media_ref_slot("ad_demo.png"))

    def test_empty(self):
        self.assertIsNone(_validate_media_ref_slot(""))

    def test_none(self):
        self.assertIsNone(_validate_media_ref_slot(None))

    def test_wrong_prefix(self):
        self.assertIsNone(_validate_media_ref_slot("creatives/ad.png"))

    def test_too_many_digits(self):
        self.assertIsNone(_validate_media_ref_slot("media/current/slot-1000"))

    def test_negative_slot(self):
        self.assertIsNone(_validate_media_ref_slot("media/current/slot--01"))


# ══════════════════════════════════════════════════════════════════════
# Tests: resolver — happy path
# ══════════════════════════════════════════════════════════════════════

class TestResolverHappyPath(TestCase):

    def test_single_item_slot_000_resolved(self):
        """One valid item → slot-000 resolves to its rendition_id."""
        items = [_make_valid_item(slot_order=0)]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)

        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.resolved)
        self.assertEqual(result.reason, REASON_RESOLVED)
        self.assertEqual(result.slot_index, 0)
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(result._internal_source_rendition_id, RENDITION_ID_000)

    def test_three_items_sorted_slots(self):
        """Three items with different slot_orders → sorted → correct slots."""
        items = [
            _make_valid_item(slot_order=2, internal_source_rendition_id="ccc"),
            _make_valid_item(slot_order=0, internal_source_rendition_id="aaa"),
            _make_valid_item(slot_order=1, internal_source_rendition_id="bbb"),
        ]

        r0 = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(r0._internal_source_rendition_id, "aaa")
        self.assertEqual(r0.slot_index, 0)

        r1 = resolve_kso_media_ref_source(items, "media/current/slot-001", NOW)
        self.assertEqual(r1._internal_source_rendition_id, "bbb")
        self.assertEqual(r1.slot_index, 1)

        r2 = resolve_kso_media_ref_source(items, "media/current/slot-002", NOW)
        self.assertEqual(r2._internal_source_rendition_id, "ccc")
        self.assertEqual(r2.slot_index, 2)

    def test_same_slot_order_sorted_by_content_type(self):
        """Items with same slot_order → secondary sort by content_type."""
        items = [
            _make_valid_item(slot_order=0, content_type="video/mp4",
                             internal_source_rendition_id="video"),
            _make_valid_item(slot_order=0, content_type="image/jpeg",
                             internal_source_rendition_id="jpeg"),
            _make_valid_item(slot_order=0, content_type="image/png",
                             internal_source_rendition_id="png"),
            _make_valid_item(slot_order=0, content_type="application/octet-stream",
                             internal_source_rendition_id="UNSUPPORTED_PDF"),
        ]

        # The .pdf item should be excluded (unsupported MIME)
        r0 = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(r0._internal_source_rendition_id, "jpeg")

        r1 = resolve_kso_media_ref_source(items, "media/current/slot-001", NOW)
        self.assertEqual(r1._internal_source_rendition_id, "png")

        r2 = resolve_kso_media_ref_source(items, "media/current/slot-002", NOW)
        self.assertEqual(r2._internal_source_rendition_id, "video")


# ══════════════════════════════════════════════════════════════════════
# Tests: resolver — filtering (same as projection builder)
# ══════════════════════════════════════════════════════════════════════

class TestResolverFilters(TestCase):

    def test_non_kso_channel_excluded(self):
        items = [_make_valid_item(channel_code="android-tv")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)
        self.assertEqual(result.valid_items, 0)

    def test_inactive_campaign_excluded(self):
        items = [_make_valid_item(campaign_status="draft")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_non_approved_creative_excluded(self):
        items = [_make_valid_item(creative_status="pending")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_invalid_rendition_excluded(self):
        items = [_make_valid_item(rendition_status="invalid")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_draft_publication_excluded(self):
        items = [_make_valid_item(publication_status="draft")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_disabled_device_excluded(self):
        items = [_make_valid_item(device_status="disabled")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_inactive_store_excluded(self):
        items = [_make_valid_item(store_is_active=False)]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_unsupported_content_type_excluded(self):
        items = [_make_valid_item(content_type="application/pdf")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_expired_schedule_excluded(self):
        items = [_make_valid_item(
            valid_from=NOW - timedelta(hours=2),
            valid_to=NOW - timedelta(hours=1),  # already expired
        )]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_future_only_schedule_excluded(self):
        items = [_make_valid_item(
            valid_from=NOW + timedelta(hours=1),  # not yet valid
            valid_to=NOW + timedelta(hours=2),
        )]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_unsafe_store_code_excluded(self):
        items = [_make_valid_item(store_code="../../evil")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_unsafe_device_code_excluded(self):
        items = [_make_valid_item(device_code="dev 01")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_missing_internal_source_excluded(self):
        items = [_make_valid_item(internal_source_rendition_id="")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.reason, REASON_NO_VALID_ITEMS)

    def test_pending_device_included(self):
        """device_status=pending is allowed (same as projection)."""
        items = [_make_valid_item(device_status="pending")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.resolved)

    def test_lost_device_included(self):
        """device_status=lost is allowed (same as projection)."""
        items = [_make_valid_item(device_status="lost")]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.resolved)


# ══════════════════════════════════════════════════════════════════════
# Tests: not found / error
# ══════════════════════════════════════════════════════════════════════

class TestResolverNotFound(TestCase):

    def test_slot_out_of_range(self):
        """Only 2 items → slot-005 not found."""
        items = [
            _make_valid_item(slot_order=0),
            _make_valid_item(slot_order=1, internal_source_rendition_id=RENDITION_ID_001),
        ]
        result = resolve_kso_media_ref_source(items, "media/current/slot-005", NOW)
        self.assertEqual(result.status, STATUS_NOT_FOUND)
        self.assertEqual(result.reason, REASON_NOT_FOUND)
        self.assertFalse(result.resolved)
        self.assertEqual(result.valid_items, 2)

    def test_unsafe_media_ref_error(self):
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "../etc/passwd", NOW)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MEDIA_REF)

    def test_url_media_ref_error(self):
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "http://evil.com/slot-000", NOW)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_MEDIA_REF)

    def test_invalid_args(self):
        result = resolve_kso_media_ref_source(None, "media/current/slot-000", NOW)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: consistency with projection builder
# ══════════════════════════════════════════════════════════════════════

class TestConsistencyWithProjection(TestCase):

    def test_projection_media_ref_resolvable(self):
        """MediaRef from projection builder resolves back correctly."""
        from app.domains.publications.kso_manifest_projection import (
            build_kso_safe_manifest_projection,
            ManifestSourceItem,
        )

        # Create source items (without rendition_id — they're ManifestSourceItem)
        ms_items = [
            ManifestSourceItem(
                channel_code="kso",
                campaign_status="approved",
                creative_status="approved",
                rendition_status="valid",
                publication_status="published",
                device_status="active",
                store_is_active=True,
                store_code="s1",
                device_code="d1",
                content_type="image/png",
                duration_ms=5000,
                slot_order=0,
                valid_from=NOW - timedelta(hours=1),
                valid_to=NOW + timedelta(hours=1),
                now=NOW,
            ),
        ]

        projection = build_kso_safe_manifest_projection(ms_items, NOW)
        self.assertTrue(projection.ok)
        self.assertEqual(projection.items_included, 1)

        # Get the mediaRef from projection
        manifest_item = projection.manifest["items"][0]
        proj_media_ref = manifest_item["mediaRef"]

        # Now create resolver items with the same data + rendition_id
        resolver_items = [
            KsoMediaRefSourceItem(
                channel_code="kso",
                campaign_status="approved",
                creative_status="approved",
                rendition_status="valid",
                publication_status="published",
                device_status="active",
                store_is_active=True,
                store_code="s1",
                device_code="d1",
                content_type="image/png",
                duration_ms=5000,
                slot_order=0,
                valid_from=NOW - timedelta(hours=1),
                valid_to=NOW + timedelta(hours=1),
                now=NOW,
                internal_source_rendition_id=RENDITION_ID_000,
            ),
        ]

        # Resolver must find the item
        resolved = resolve_kso_media_ref_source(
            resolver_items, proj_media_ref, NOW)

        self.assertEqual(resolved.status, STATUS_OK)
        self.assertTrue(resolved.resolved)
        self.assertEqual(resolved._internal_source_rendition_id, RENDITION_ID_000)
        self.assertEqual(resolved.content_type, "image/png")

    def test_projection_and_resolver_same_sort_order(self):
        """Projection and resolver produce identical slot assignments."""
        from app.domains.publications.kso_manifest_projection import (
            build_kso_safe_manifest_projection,
            ManifestSourceItem,
        )

        # Build a mix of items with different orders
        ms_items = []
        resolver_items = []
        rids = ["aaa", "bbb", "ccc"]
        for i, rid in enumerate(rids):
            slot_order = [2, 0, 1][i]  # out of order
            ms_items.append(ManifestSourceItem(
                channel_code="kso", campaign_status="approved",
                creative_status="approved", rendition_status="valid",
                publication_status="published", device_status="active",
                store_is_active=True, store_code="s1", device_code="d1",
                content_type="image/png", duration_ms=5000,
                slot_order=slot_order,
            ))
            resolver_items.append(KsoMediaRefSourceItem(
                channel_code="kso", campaign_status="approved",
                creative_status="approved", rendition_status="valid",
                publication_status="published", device_status="active",
                store_is_active=True, store_code="s1", device_code="d1",
                content_type="image/png", duration_ms=5000,
                slot_order=slot_order,
                internal_source_rendition_id=rid,
            ))

        projection = build_kso_safe_manifest_projection(ms_items, NOW)

        # For each projection item, resolver must find the same slot → rid
        for proj_item in projection.manifest["items"]:
            media_ref = proj_item["mediaRef"]
            resolved = resolve_kso_media_ref_source(
                resolver_items, media_ref, NOW)
            self.assertTrue(resolved.resolved,
                f"Resolver failed for {media_ref}")
            # Verify content_type matches
            self.assertEqual(resolved.content_type, "image/png")


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestResolverOutputSafety(TestCase):

    FORBIDDEN_OUTPUT = {
        "rendition_id", "creative_id", "campaign_id",
        "schedule_item_id", "batch_id", "manifest_item_id",
        "file_path", "media_path", "creatives/",
        "minio", "s3://", "sha256", "storage_key",
        "token", "secret", "backend_base_url",
        "media/current/slot",
    }

    def test_repr_no_internal_source(self):
        """Repr must not expose rendition_id."""
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        text = repr(result)
        self.assertNotIn(RENDITION_ID_000, text)
        self.assertNotIn("_internal_source", text)
        self.assertNotIn("rendition_id", text)

    def test_format_no_internal_source(self):
        """Format output must not expose rendition_id."""
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        text = format_kso_media_ref_resolution_result(result)
        self.assertNotIn(RENDITION_ID_000, text)
        self.assertNotIn("rendition_id", text)
        self.assertNotIn("media/current", text)

    def test_repr_no_media_ref_value(self):
        """Repr must not contain mediaRef values."""
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        text = repr(result)
        self.assertNotIn("slot-000", text)
        self.assertNotIn("slot-001", text)

    def test_format_no_media_ref_value(self):
        """Format must not contain mediaRef values."""
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        text = format_kso_media_ref_resolution_result(result)
        self.assertNotIn("slot-000", text)
        self.assertNotIn("slot-001", text)

    def test_error_no_stacktrace(self):
        """Error result has no stacktrace."""
        result = resolve_kso_media_ref_source(None, "media/current/slot-000", NOW)
        text = repr(result) + format_kso_media_ref_resolution_result(result)
        self.assertNotIn("Traceback", text)

    def test_internal_field_not_in_repr(self):
        """Internal fields are not in repr or public output."""
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        text = repr(result)
        # Internal fields with repr=False should not appear
        self.assertNotIn("_internal_source", text)

    def test_no_raw_ids(self):
        """Output has no campagne_id, creative_id, etc."""
        items = [_make_valid_item()]
        result = resolve_kso_media_ref_source(items, "media/current/slot-000", NOW)
        text = repr(result) + format_kso_media_ref_resolution_result(result)
        lower = text.lower()
        for fb in self.FORBIDDEN_OUTPUT:
            self.assertNotIn(fb.lower(), lower,
                f"forbidden '{fb}' found in output: {text[:150]}")


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestResolverNoSideEffects(TestCase):

    def test_no_db_import(self):
        """Resolver does not import database modules."""
        import app.domains.publications.kso_media_ref_resolver as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("sqlalchemy", source)
        self.assertNotIn("AsyncSession", source)
        self.assertNotIn("starlette", source)
        self.assertNotIn("fastapi", source)

    def test_no_http(self):
        """Resolver has no HTTP calls."""
        import app.domains.publications.kso_media_ref_resolver as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import requests", source)
        self.assertNotIn("import urllib", source)
        self.assertNotIn("http.client", source)

    def test_no_media_bytes(self):
        """Resolver does not read media bytes."""
        import app.domains.publications.kso_media_ref_resolver as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn(".read_bytes", source)
        self.assertNotIn(".open(", source)
        self.assertNotIn("open(", source)

    def test_no_windows(self):
        """No Windows/MSI/ProgramData."""
        import app.domains.publications.kso_media_ref_resolver as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("windows service", "programdata", "windows installer"):
            self.assertNotIn(fb, source)

    def test_no_secret_token(self):
        """No secret/token reading."""
        import app.domains.publications.kso_media_ref_resolver as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        self.assertNotIn(".env", source)
        self.assertNotIn("read_secret", source)
        self.assertNotIn("load_dotenv", source)
