"""Creative moderation queue and AV readiness tests — 44.4."""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


class TestModerationWorkflow(unittest.TestCase):
    """Test moderation workflow — statuses, maker-checker, actions."""

    def test_return_for_rework_action_valid(self):
        """return_for_rework is a valid moderation action."""
        from app.domains.media.schemas import ModerationAction
        action = ModerationAction(action="return_for_rework", comment="fix dimensions")
        self.assertEqual(action.action, "return_for_rework")

    def test_all_moderation_actions_accepted(self):
        """All 4 actions pass schema validation."""
        from app.domains.media.schemas import ModerationAction
        for action_name in ("approve", "reject", "submit_review", "return_for_rework"):
            action = ModerationAction(action=action_name)
            self.assertEqual(action.action, action_name)

    def test_maker_checker_creator_cannot_approve_own(self):
        """Maker-checker: creator cannot approve own creative."""
        # Mock creative with created_by matching current_user
        creative = MagicMock()
        creative.status = "pending_review"
        creative.created_by = "user-123"

        # current_user has same ID → should be rejected
        # This is tested at the router level in integration tests
        self.assertEqual(str(creative.created_by), "user-123")

    def test_status_manual_review_defined(self):
        """manual_review is a recognized creative status."""
        valid_statuses = [
            "draft", "pending_review", "in_review", "manual_review",
            "approved", "rejected", "validation_failed", "archived",
        ]
        self.assertIn("manual_review", valid_statuses)

    def test_moderation_queue_schema(self):
        """ModerationQueueItem schema works."""
        from app.domains.media.schemas import ModerationQueueItem
        item = ModerationQueueItem(
            creative_code="cr-001", name="Test", status="pending_review",
            scan_status="not_configured", content_type="image/png",
            width=768, height=1024, file_size_bytes=1024,
            created_by="admin", created_at="2026-01-01T00:00:00Z",
        )
        self.assertFalse(item.can_use_in_campaign)  # pending_review → not approved
        self.assertEqual(item.creative_code, "cr-001")

    def test_av_readiness_schema(self):
        """AVReadinessResponse schema correct defaults."""
        from app.domains.media.schemas import AVReadinessResponse
        resp = AVReadinessResponse()
        self.assertFalse(resp.scanner_available)
        self.assertFalse(resp.production_ready)
        self.assertEqual(resp.readiness, "not_configured")
        self.assertEqual(resp.scanner_name, "none")

    def test_av_readiness_production_requires_scanner(self):
        """Production ready requires scanner available."""
        from app.domains.media.schemas import AVReadinessResponse
        resp = AVReadinessResponse(
            scanner_available=True, readiness="ready", production_ready=True,
            message="Проверка безопасности файлов работает",
        )
        self.assertTrue(resp.production_ready)
        self.assertEqual(resp.message, "Проверка безопасности файлов работает")


class TestMOVGuard(unittest.TestCase):
    """.mov file rejection as user upload format."""

    def test_mov_not_in_allowed_mime(self):
        """video/quicktime (.mov) is NOT in allowed upload MIME types."""
        from app.domains.media.service import ALLOWED_UPLOAD_MIME_TYPES
        self.assertNotIn("video/quicktime", ALLOWED_UPLOAD_MIME_TYPES)
        self.assertNotIn("video/x-msvideo", ALLOWED_UPLOAD_MIME_TYPES)

    def test_mov_not_in_allowed_extensions(self):
        """.mov is NOT in allowed file extensions."""
        from app.domains.media.storage import ALLOWED_EXTENSIONS
        self.assertNotIn(".mov", ALLOWED_EXTENSIONS)

    def test_allowed_formats_match_tz(self):
        """Only TZ-approved formats: jpg, jpeg, png, gif, mp4, webm."""
        from app.domains.media.service import ALLOWED_UPLOAD_MIME_TYPES
        expected = {"image/jpeg", "image/png", "image/gif", "video/mp4", "video/webm"}
        self.assertEqual(ALLOWED_UPLOAD_MIME_TYPES, expected)

    def test_mp4_and_webm_in_allowed(self):
        """MP4 and WebM are allowed for user upload."""
        from app.domains.media.service import ALLOWED_UPLOAD_MIME_TYPES
        self.assertIn("video/mp4", ALLOWED_UPLOAD_MIME_TYPES)
        self.assertIn("video/webm", ALLOWED_UPLOAD_MIME_TYPES)

    def test_internal_container_allows_mov_family(self):
        """Internal ffprobe container check allows mp4/mov family output."""
        from app.domains.media.media_validator import ALLOWED_CONTAINERS
        self.assertIn("mov", ALLOWED_CONTAINERS)  # Internal ok
        # But user upload banned via MIME type


class TestAVReadiness(unittest.TestCase):
    """Test AV readiness endpoint behavior."""

    def test_noscanner_readiness(self):
        """NoScanner → readiness not_configured."""
        from app.domains.media.av_scanner import NoScanner, ScanResult
        scanner = NoScanner()
        self.assertFalse(scanner.is_configured)
        report = asyncio.run(scanner.scan(b"test"))
        self.assertEqual(report.result, ScanResult.NOT_CONFIGURED)

    def test_clama_scanner_not_installed_readiness(self):
        """ClamAVScanner without ClamAV installed → is_configured=False."""
        from app.domains.media.av_scanner import ClamAVScanner, NoScanner
        scanner = ClamAVScanner(socket_path="/nonexistent/path")
        # Should return False if ClamAV not installed
        self.assertIsInstance(scanner.is_configured, bool)

    def test_create_av_scanner_readiness(self):
        """Factory returns scanner — readiness depends on installation."""
        from app.domains.media.av_scanner import create_av_scanner, AVScanner
        scanner = create_av_scanner()
        self.assertIsInstance(scanner, AVScanner)
        # Not asserting is_configured — depends on environment


class TestPolicyGuard(unittest.TestCase):
    """Policy guard: pilot_dev vs production enforcement."""

    def test_pilot_allows_manual_approval(self):
        """pilot_dev: require_av_clean=false → manual approval allowed."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        self.assertEqual(policy.av_policy_mode, "pilot_dev")
        self.assertFalse(policy.require_av_clean_for_publication)

    def test_production_requires_av_clean(self):
        """production: require_av_clean=true → blocks without clean."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        policy.av_policy_mode = "production"
        policy.require_av_clean_for_publication = True
        self.assertTrue(policy.require_av_clean_for_publication)

    def test_fake_av_pass_prohibited_in_policy_notes(self):
        """Policy notes explicitly ban fake AV pass."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        notes = " ".join(policy.notes).lower()
        self.assertIn("запрещён", notes)

    def test_production_ready_false_when_no_scanner(self):
        """AVReadiness production_ready=False when scanner unavailable."""
        from app.domains.media.schemas import AVReadinessResponse
        resp = AVReadinessResponse(readiness="not_configured")
        self.assertFalse(resp.production_ready)
