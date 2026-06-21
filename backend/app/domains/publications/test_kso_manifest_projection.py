"""Tests for KSO Safe Manifest Projection Builder.

Pure unit tests — no DB, no HTTP, no FastAPI.
"""

import json
from datetime import datetime, timezone, timedelta

import pytest

from app.domains.publications.kso_manifest_projection import (
    ManifestSourceItem,
    KsoSafeManifestItem,
    KsoSafeManifestProjectionResult,
    build_kso_safe_manifest_projection,
    _validate_safe_code,
    _validate_content_type,
    _validate_duration_ms,
    _build_media_ref,
    _validate_manifest_forbidden,
    MAX_ITEMS,
    MAX_MANIFEST_BYTES,
    FORBIDDEN_KEYS,
    ALLOWED_CONTENT_TYPES,
    KSO_CHANNEL_CODE,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _make_item(
    channel="kso",
    campaign="approved",
    creative="approved",
    rendition="valid",
    publication="published",
    device="active",
    store_active=True,
    store_code="store-001",
    device_code="a-05954",
    content_type="image/png",
    duration_ms=5000,
    slot_order=0,
    valid_from=None,
    valid_to=None,
    now=None,
):
    return ManifestSourceItem(
        channel_code=channel,
        campaign_status=campaign,
        creative_status=creative,
        rendition_status=rendition,
        publication_status=publication,
        device_status=device,
        store_is_active=store_active,
        store_code=store_code,
        device_code=device_code,
        content_type=content_type,
        duration_ms=duration_ms,
        slot_order=slot_order,
        valid_from=valid_from,
        valid_to=valid_to,
        now=now or NOW,
    )


def _manifest_json(result):
    return result.manifest


def _items(result):
    return result.manifest.get("items", [])


# ══════════════════════════════════════════════════════════════════════
# Tests: valid KSO input → safe manifest
# ══════════════════════════════════════════════════════════════════════

class TestValidKsoManifest:
    def test_single_image_item(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(content_type="image/png")], NOW)
        assert result.ok
        assert result.items_included == 1
        m = result.manifest
        assert m["schemaVersion"] == 1
        assert m["channel"] == "kso"
        assert m["storeCode"] == "store-001"
        assert m["deviceCode"] == "a-05954"
        assert len(m["items"]) == 1
        item = m["items"][0]
        assert item["slotOrder"] == 0
        assert item["contentType"] == "image/png"
        assert item["durationMs"] == 5000
        assert item["mediaRef"] == "media/current/slot-000"

    def test_single_video_item(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(content_type="video/mp4", duration_ms=30000)], NOW)
        assert result.ok
        assert _items(result)[0]["contentType"] == "video/mp4"

    def test_jpeg_item(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(content_type="image/jpeg")], NOW)
        assert result.ok
        assert _items(result)[0]["contentType"] == "image/jpeg"

    def test_multiple_items_sorted(self):
        result = build_kso_safe_manifest_projection(
            [
                _make_item(slot_order=3, content_type="image/png"),
                _make_item(slot_order=1, content_type="video/mp4"),
                _make_item(slot_order=0, content_type="image/jpeg"),
            ], NOW)
        assert result.ok
        assert result.items_included == 3
        items_list = _items(result)
        assert [i["slotOrder"] for i in items_list] == [0, 1, 3]

    def test_media_ref_deterministic_after_sort(self):
        result = build_kso_safe_manifest_projection(
            [
                _make_item(slot_order=5, content_type="image/png"),
                _make_item(slot_order=2, content_type="video/mp4"),
            ], NOW)
        items_list = _items(result)
        assert items_list[0]["mediaRef"] == "media/current/slot-000"
        assert items_list[1]["mediaRef"] == "media/current/slot-001"

    def test_empty_result_when_no_valid_items(self):
        result = build_kso_safe_manifest_projection([], NOW)
        assert result.ok
        assert result.items_included == 0
        assert _items(result) == []


# ══════════════════════════════════════════════════════════════════════
# Tests: exclusions
# ══════════════════════════════════════════════════════════════════════

class TestExclusions:
    def test_non_kso_channel_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(channel="android_tv")], NOW)
        assert result.items_included == 0

    def test_inactive_campaign_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(campaign="draft")], NOW)
        assert result.items_included == 0

    def test_non_approved_creative_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(creative="in_review")], NOW)
        assert result.items_included == 0

    def test_invalid_rendition_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(rendition="invalid")], NOW)
        assert result.items_included == 0

    def test_unpublished_publication_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(publication="draft")], NOW)
        assert result.items_included == 0

    def test_disabled_device_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(device="disabled")], NOW)
        assert result.items_included == 0

    def test_retired_device_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(device="retired")], NOW)
        assert result.items_included == 0

    def test_inactive_store_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(store_active=False)], NOW)
        assert result.items_included == 0

    def test_unsupported_content_type_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(content_type="text/html")], NOW)
        assert result.items_included == 0

    def test_svg_excluded(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(content_type="image/svg+xml")], NOW)
        assert result.items_included == 0

    def test_expired_schedule_excluded(self):
        past = NOW - timedelta(days=10)
        result = build_kso_safe_manifest_projection(
            [_make_item(valid_to=past)], NOW)
        assert result.items_included == 0

    def test_future_only_schedule_excluded(self):
        future = NOW + timedelta(days=30)
        result = build_kso_safe_manifest_projection(
            [_make_item(valid_from=future)], NOW)
        assert result.items_included == 0

    def test_expired_and_future_mixed_only_current_included(self):
        past = NOW - timedelta(days=10)
        future = NOW + timedelta(days=30)
        result = build_kso_safe_manifest_projection(
            [
                _make_item(slot_order=0, valid_to=past),
                _make_item(slot_order=1, content_type="video/mp4"),
                _make_item(slot_order=2, valid_from=future),
            ], NOW)
        assert result.items_included == 1
        assert _items(result)[0]["slotOrder"] == 1  # original slot_order preserved
        assert _items(result)[0]["contentType"] == "video/mp4"


# ══════════════════════════════════════════════════════════════════════
# Tests: forbidden fields
# ══════════════════════════════════════════════════════════════════════

class TestForbiddenFieldsNotInManifest:
    def test_no_raw_ids_in_manifest(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m = result.manifest
        m_json = json.dumps(m, sort_keys=True)
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "rendition_id", "schedule_item_id", "batch_id",
                    "booking_id", "target_id"):
            assert fb not in m_json

    def test_no_paths_in_manifest(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m_json = json.dumps(result.manifest, sort_keys=True)
        for fb in ("file_path", "media_path", "creatives/", "minio", "s3://"):
            assert fb not in m_json

    def test_no_urls_in_manifest(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m_json = json.dumps(result.manifest, sort_keys=True)
        for fb in ("http://", "https://", "ws://", "file://"):
            assert fb not in m_json

    def test_no_financial_fields(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m_json = json.dumps(result.manifest, sort_keys=True).lower()
        for fb in ("budget", "currency", "price"):
            assert fb not in m_json

    def test_no_pii(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m_json = json.dumps(result.manifest, sort_keys=True).lower()
        for fb in ("customer_id", "phone", "email", "receipt_data",
                    "card_number", "pan", "fiscal_data"):
            assert fb not in m_json

    def test_no_auth_fields(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m_json = json.dumps(result.manifest, sort_keys=True).lower()
        for fb in ("token", "jwt", "secret", "api_key", "password",
                    "credential", "authorization", "cookie"):
            assert fb not in m_json

    def test_no_backend_fields(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        m_json = json.dumps(result.manifest, sort_keys=True).lower()
        for fb in ("backend_base_url", "127.0.0.1", "device_secret"):
            assert fb not in m_json

    def test_forbidden_key_validator_catches_infiltration(self):
        bad = {"schemaVersion": 1, "token": "leaked", "items": []}
        hits = _validate_manifest_forbidden(bad)
        assert len(hits) > 0
        assert any("token" in h for h in hits)

    def test_forbidden_key_validator_catches_nested(self):
        bad = {"items": [{"api_key": "secret123"}]}
        hits = _validate_manifest_forbidden(bad)
        assert len(hits) > 0

    def test_forbidden_value_validator_catches(self):
        bad = {"reason": "backend_base_url is https://evil.com"}
        hits = _validate_manifest_forbidden(bad)
        assert len(hits) > 0


# ══════════════════════════════════════════════════════════════════════
# Tests: mediaRef generation
# ══════════════════════════════════════════════════════════════════════

class TestMediaRef:
    def test_media_ref_format(self):
        assert _build_media_ref(0) == "media/current/slot-000"
        assert _build_media_ref(5) == "media/current/slot-005"
        assert _build_media_ref(42) == "media/current/slot-042"
        assert _build_media_ref(999) == "media/current/slot-999"

    def test_media_ref_clamps_negative(self):
        assert _build_media_ref(-1) == "media/current/slot-000"

    def test_media_ref_no_real_filename(self):
        ref = _build_media_ref(0)
        assert "ad_" not in ref
        assert ".png" not in ref
        assert "/" in ref  # has alias path prefix only

    def test_media_ref_no_id_no_hash(self):
        ref = _build_media_ref(0)
        for fb in ("uuid", "sha256", "manifest_item_id", "batch_id"):
            assert fb not in ref


# ══════════════════════════════════════════════════════════════════════
# Tests: cap / limits
# ══════════════════════════════════════════════════════════════════════

class TestCaps:
    def test_cap_max_items(self):
        items = [_make_item(slot_order=i) for i in range(MAX_ITEMS + 50)]
        result = build_kso_safe_manifest_projection(items, NOW)
        assert result.items_included == MAX_ITEMS
        assert len(_items(result)) == MAX_ITEMS

    def test_warning_on_cap(self):
        items = [_make_item(slot_order=i) for i in range(MAX_ITEMS + 10)]
        result = build_kso_safe_manifest_projection(items, NOW)
        assert any("Capped" in w for w in result.warnings)


# ══════════════════════════════════════════════════════════════════════
# Tests: validation helpers
# ══════════════════════════════════════════════════════════════════════

class TestValidationHelpers:
    def test_validate_safe_code_ok(self):
        assert _validate_safe_code("store-001", "store_code") is None
        assert _validate_safe_code("a_05954", "device_code") is None

    def test_validate_safe_code_rejects_path_traversal(self):
        assert _validate_safe_code("../etc", "store_code") is not None
        assert _validate_safe_code("a/b", "store_code") is not None

    def test_validate_safe_code_rejects_spaces(self):
        assert _validate_safe_code("store 001", "store_code") is not None

    def test_validate_safe_code_rejects_empty(self):
        assert _validate_safe_code("", "store_code") is not None

    def test_validate_content_type(self):
        assert _validate_content_type("image/png")
        assert _validate_content_type("image/jpeg")
        assert _validate_content_type("video/mp4")
        assert not _validate_content_type("text/html")
        assert not _validate_content_type("video/webm")

    def test_validate_duration_clamp(self):
        assert _validate_duration_ms(5000) == 5000
        assert _validate_duration_ms(0) == 1
        assert _validate_duration_ms(-100) == 1

    def test_validate_duration_max_clamp(self):
        from app.domains.publications.kso_manifest_projection import MAX_DURATION_MS
        assert _validate_duration_ms(MAX_DURATION_MS + 1) == MAX_DURATION_MS


# ══════════════════════════════════════════════════════════════════════
# Tests: edge cases
# ══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_missing_store_code_error(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(store_code="")], NOW)
        assert not result.ok
        assert len(result.errors) > 0

    def test_unsafe_store_code_error(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(store_code="../etc")], NOW)
        assert not result.ok
        assert len(result.errors) > 0

    def test_non_list_input_error(self):
        result = build_kso_safe_manifest_projection(None, NOW)
        assert not result.ok
        assert any("list" in e for e in result.errors)

    def test_non_manifest_source_item_skipped(self):
        result = build_kso_safe_manifest_projection(
            ["not_an_item", _make_item()], NOW)
        assert result.items_included == 1
        assert any("Non-ManifestSourceItem" in w for w in result.warnings)

    def test_stable_output_order(self):
        """Same input twice → same output."""
        items = [
            _make_item(slot_order=3, content_type="image/png"),
            _make_item(slot_order=1, content_type="video/mp4"),
            _make_item(slot_order=0, content_type="image/jpeg"),
        ]
        r1 = build_kso_safe_manifest_projection(items, NOW)
        r2 = build_kso_safe_manifest_projection(items, NOW)
        assert r1.manifest == r2.manifest

    def test_device_status_pending_allowed(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(device="pending")], NOW)
        assert result.items_included == 1

    def test_device_status_lost_allowed(self):
        result = build_kso_safe_manifest_projection(
            [_make_item(device="lost")], NOW)
        assert result.items_included == 1


# ══════════════════════════════════════════════════════════════════════
# Tests: generated_at
# ══════════════════════════════════════════════════════════════════════

class TestGeneratedAt:
    def test_generated_at_set(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        assert "generatedAt" in result.manifest
        assert result.manifest["generatedAt"] == NOW.isoformat()

    def test_generated_at_defaults_to_now(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()])
        assert "generatedAt" in result.manifest
        assert result.manifest["generatedAt"]  # non-empty


# ══════════════════════════════════════════════════════════════════════
# Tests: repr safety
# ══════════════════════════════════════════════════════════════════════

class TestReprSafety:
    def test_result_repr_no_ids(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        text = repr(result)
        for fb in ("campaign_id", "creative_id", "rendition_id",
                    "manifest_item_id", "schedule_item_id"):
            assert fb not in text

    def test_result_repr_no_paths(self):
        result = build_kso_safe_manifest_projection(
            [_make_item()], NOW)
        text = repr(result)
        assert "file_path" not in text
        assert "media_path" not in text
        assert "creatives/" not in text
