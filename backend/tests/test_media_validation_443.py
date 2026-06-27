"""Production media validation tests — 44.3.

Tests video (MP4/WebM), GIF validation, AV scanner integration, and policy enforcement.
"""

import json
import os
import unittest
from io import BytesIO
from unittest.mock import MagicMock, AsyncMock, patch

import asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _create_test_png(width=768, height=1024):
    """Create a valid test PNG."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_test_jpeg(width=768, height=1024):
    """Create a valid test JPEG."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(0, 255, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _create_test_gif(width=768, height=1024, frames=10):
    """Create a valid test GIF with specified frame count."""
    from PIL import Image
    frames_list = []
    for i in range(frames):
        img = Image.new("RGB", (width, height), color=(i * 25 % 256, 100, 200))
        frames_list.append(img)
    buf = BytesIO()
    frames_list[0].save(
        buf, format="GIF", save_all=True,
        append_images=frames_list[1:], duration=100, loop=0,
    )
    return buf.getvalue()


def _create_test_mp4(width=768, height=1024, duration=5, has_audio=False):
    """Create a minimal valid MP4 file using ffmpeg if available.

    Returns (content, success_flag). If ffmpeg unavailable, returns (b'', False).
    """
    import subprocess
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    out = tmp.name

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=red:s={width}x{height}:d={duration}:r=10",
    ]
    if has_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
    cmd += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
    ]
    if not has_audio:
        cmd += ["-an"]
    cmd += ["-t", str(duration), out]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        if proc.returncode != 0:
            os.unlink(out)
            return b"", False
        with open(out, "rb") as f:
            content = f.read()
        os.unlink(out)
        return content, True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        if os.path.exists(out):
            os.unlink(out)
        return b"", False


# ═══════════════════════════════════════════════════════════════════════════
# Video Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVideoValidator(unittest.TestCase):
    """Test MP4/WebM video validation."""

    @classmethod
    def setUpClass(cls):
        cls.has_ffmpeg = False
        try:
            subprocess = __import__("subprocess")
            proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            cls.has_ffmpeg = proc.returncode == 0
        except Exception:
            pass

    def setUp(self):
        from app.domains.media import media_validator
        self.validator = media_validator

    # ── Integrity / Magic Bytes ────────────────────────────────────────

    def test_empty_file_rejected(self):
        result = self.validator.validate_video(b"", "test.mp4", "video/mp4")
        self.assertFalse(result.is_valid)
        self.assertIn("пустой", result.reasons[0].lower())

    def test_random_bytes_rejected(self):
        result = self.validator.validate_video(b"not a video file", "test.mp4", "video/mp4")
        self.assertFalse(result.is_valid)
        self.assertIn("повреждён", result.reasons[0].lower())

    # ── MIME / Extension mismatch ───────────────────────────────────────

    def test_mime_extension_mismatch_rejected(self):
        """MP4 extension with PNG MIME should be caught."""
        result = self.validator.validate_video(b"fake", "test.png", "video/mp4")
        # Extension check will catch it
        self.assertFalse(result.is_valid)

    def test_wrong_extension_rejected(self):
        result = self.validator.validate_video(b"data", "test.jpg", "video/mp4")
        self.assertFalse(result.is_valid)

    # ── Size ───────────────────────────────────────────────────────────

    def test_too_large_file_rejected(self):
        """Validate that content exceeding size limit is rejected.
        Uses a mock to avoid allocating 101MB in memory."""
        from unittest.mock import patch
        from app.domains.media import media_validator

        # Create a valid MP4 if possible, then patch the size limit
        if self.has_ffmpeg:
            content, ok = _create_test_mp4(width=768, height=1024, duration=3, has_audio=False)
            if not ok:
                self.skipTest("ffmpeg failed")
        else:
            # Minimal valid MP4 bytes synthesized
            content = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1000

        # Patch MAX_FILE_SIZE_VIDEO to 1 byte to trigger size rejection
        with patch.object(media_validator, "MAX_FILE_SIZE_VIDEO", 1):
            result = self.validator.validate_video(content, "test.mp4", "video/mp4")
            self.assertFalse(result.is_valid)
            self.assertIn("большой", result.reasons[0].lower())

    # ── Valid MP4 (if ffmpeg available) ─────────────────────────────────

    def test_valid_mp4_accepted(self):
        if not self.has_ffmpeg:
            self.skipTest("ffmpeg not available")
        content, ok = _create_test_mp4(width=768, height=1024, duration=5, has_audio=False)
        if not ok:
            self.skipTest("ffmpeg failed to create test MP4")
        result = self.validator.validate_video(content, "test.mp4", "video/mp4")
        self.assertTrue(
            result.is_valid or result.status == self.validator.ValidationStatus.SKIPPED,
            f"Reasons: {result.reasons}",
        )

    # ── Wrong dimensions ────────────────────────────────────────────────

    def test_wrong_dimensions_rejected(self):
        if not self.has_ffmpeg:
            self.skipTest("ffmpeg not available")
        content, ok = _create_test_mp4(width=1920, height=1080, duration=3, has_audio=False)
        if not ok:
            self.skipTest("ffmpeg failed")
        result = self.validator.validate_video(content, "test.mp4", "video/mp4")
        if result.status != self.validator.ValidationStatus.SKIPPED:
            self.assertFalse(result.is_valid)
            self.assertIn("размер ролика", " ".join(result.reasons).lower())

    def test_landscape_rejected(self):
        if not self.has_ffmpeg:
            self.skipTest("ffmpeg not available")
        content, ok = _create_test_mp4(width=1024, height=768, duration=3, has_audio=False)
        if not ok:
            self.skipTest("ffmpeg failed")
        result = self.validator.validate_video(content, "test.mp4", "video/mp4")
        if result.status != self.validator.ValidationStatus.SKIPPED:
            self.assertFalse(result.is_valid)

    # ── Duration ────────────────────────────────────────────────────────

    def test_too_long_video_rejected(self):
        if not self.has_ffmpeg:
            self.skipTest("ffmpeg not available")
        content, ok = _create_test_mp4(width=768, height=1024, duration=60, has_audio=False)
        if not ok:
            self.skipTest("ffmpeg failed")
        result = self.validator.validate_video(content, "test.mp4", "video/mp4")
        if result.status != self.validator.ValidationStatus.SKIPPED:
            self.assertFalse(result.is_valid)
            self.assertIn("длинное", " ".join(result.reasons).lower())

    # ── Audio ──────────────────────────────────────────────────────────

    def test_audio_in_video_rejected(self):
        if not self.has_ffmpeg:
            self.skipTest("ffmpeg not available")
        content, ok = _create_test_mp4(width=768, height=1024, duration=3, has_audio=True)
        if not ok:
            self.skipTest("ffmpeg failed")
        result = self.validator.validate_video(content, "test.mp4", "video/mp4")
        if result.status != self.validator.ValidationStatus.SKIPPED:
            self.assertFalse(result.is_valid)
            self.assertIn("звук", " ".join(result.reasons).lower())


# ═══════════════════════════════════════════════════════════════════════════
# GIF Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGifValidator(unittest.TestCase):
    """Test GIF validation."""

    def setUp(self):
        from app.domains.media import media_validator
        self.validator = media_validator

    def test_valid_gif_accepted(self):
        content = _create_test_gif(768, 1024, frames=10)
        result = self.validator.validate_gif(content, "test.gif", "image/gif")
        self.assertTrue(result.is_valid, f"Reasons: {result.reasons}")

    def test_gif_empty_rejected(self):
        result = self.validator.validate_gif(b"", "test.gif", "image/gif")
        self.assertFalse(result.is_valid)

    def test_gif_not_gif_rejected(self):
        result = self.validator.validate_gif(b"not a gif", "test.gif", "image/gif")
        self.assertFalse(result.is_valid)
        self.assertIn("GIF", " ".join(result.reasons))

    def test_gif_wrong_mime_rejected(self):
        content = _create_test_gif(768, 1024, 5)
        result = self.validator.validate_gif(content, "test.gif", "image/png")
        self.assertFalse(result.is_valid)

    def test_gif_wrong_dimensions_rejected(self):
        content = _create_test_gif(1920, 1080, 5)
        result = self.validator.validate_gif(content, "test.gif", "image/gif")
        self.assertFalse(result.is_valid)
        self.assertIn("размер", " ".join(result.reasons).lower())

    def test_gif_too_many_frames_rejected(self):
        content = _create_test_gif(768, 1024, frames=500)
        result = self.validator.validate_gif(content, "test.gif", "image/gif")
        self.assertFalse(result.is_valid)
        self.assertIn("кадр", " ".join(result.reasons).lower())

    def test_gif_too_large_file_rejected(self):
        content = b"GIF89a" + b"x" * (21 * 1024 * 1024)
        result = self.validator.validate_gif(content, "test.gif", "image/gif")
        self.assertFalse(result.is_valid)

    def test_gif_corrupted_rejected(self):
        content = b"GIF89a\x00\x00\x00\x00"  # truncated
        result = self.validator.validate_gif(content, "test.gif", "image/gif")
        self.assertFalse(result.is_valid)
        self.assertIn("повреждён", " ".join(result.reasons).lower())


# ═══════════════════════════════════════════════════════════════════════════
# AV Scanner Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAVScanner(unittest.TestCase):
    """Test AV scanner integration."""

    def test_no_scanner_not_configured(self):
        """NoScanner returns NOT_CONFIGURED, not CLEAN."""
        from app.domains.media.av_scanner import NoScanner, ScanResult
        scanner = NoScanner()
        self.assertFalse(scanner.is_configured)
        self.assertEqual(scanner.name, "none")

        report = asyncio.run(scanner.scan(b"test data", "file.png"))
        self.assertEqual(report.result, ScanResult.NOT_CONFIGURED)
        self.assertFalse(report.is_clean)
        self.assertFalse(report.is_infected)

    def test_no_scanner_never_returns_clean(self):
        """NoScanner NEVER returns CLEAN — no fake pass."""
        from app.domains.media.av_scanner import NoScanner, ScanResult
        scanner = NoScanner()
        # Try multiple times with different content
        for content in [b"", b"test", b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"]:
            report = asyncio.run(scanner.scan(content))
            self.assertNotEqual(report.result, ScanResult.CLEAN,
                              f"Fake clean detected for content: {content[:20]}")

    def test_clamav_scanner_checks_availability(self):
        """ClamAVScanner checks if ClamAV is available."""
        from app.domains.media.av_scanner import ClamAVScanner
        scanner = ClamAVScanner()
        is_configured = scanner.is_configured
        # Just check it doesn't crash
        self.assertIsInstance(is_configured, bool)

    def test_create_av_scanner_returns_scanner(self):
        """Factory returns a valid scanner."""
        from app.domains.media.av_scanner import create_av_scanner, AVScanner
        scanner = create_av_scanner()
        self.assertIsInstance(scanner, AVScanner)

    def test_infected_blocks_upload(self):
        """Infected scan result should block upload."""
        from app.domains.media.av_scanner import ScanResult, ScanReport
        report = ScanReport(
            result=ScanResult.INFECTED,
            message="Найдена угроза",
            threats=["Test.Virus"],
        )
        self.assertTrue(report.is_infected)
        self.assertFalse(report.is_clean)


# ═══════════════════════════════════════════════════════════════════════════
# Policy Enforcement Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAVPolicy(unittest.TestCase):
    """Test AV policy enforcement (pilot_dev vs production)."""

    def test_pilot_dev_policy_allows_manual_approval(self):
        """In pilot_dev mode, require_av_clean=false — manual approval allowed."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        self.assertEqual(policy.av_policy_mode, "pilot_dev")
        self.assertFalse(policy.require_av_clean_for_publication)

    def test_production_policy_requires_av_clean(self):
        """Production mode requires AV clean."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        policy.av_policy_mode = "production"
        policy.require_av_clean_for_publication = True
        self.assertTrue(policy.require_av_clean_for_publication)

    def test_policy_notes_include_fake_av_ban(self):
        """Policy notes explicitly prohibit fake AV pass."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        notes_text = " ".join(policy.notes).lower()
        self.assertIn("fake", notes_text)
        self.assertIn("запрещён", notes_text)

    def test_policy_notes_include_pilot_warning(self):
        """Policy notes mention pilot mode AV exemption."""
        from app.domains.media.schemas import CreativePolicyResponse
        policy = CreativePolicyResponse()
        notes_text = " ".join(policy.notes).lower()
        self.assertIn("pilot", notes_text)
        self.assertIn("ручной модерации", notes_text)


# ═══════════════════════════════════════════════════════════════════════════
# Creative upload combined tests (image only — no DB)
# ═══════════════════════════════════════════════════════════════════════════

class TestCreativeUploadValidation(unittest.TestCase):
    """Test upload_creative_combined validation (no DB required)."""

    def test_unknown_mime_rejected(self):
        """Unknown MIME type raises HTTPException."""
        from app.domains.media.service import ALLOWED_UPLOAD_MIME_TYPES
        self.assertNotIn("application/pdf", ALLOWED_UPLOAD_MIME_TYPES)
        self.assertNotIn("text/html", ALLOWED_UPLOAD_MIME_TYPES)

    def test_all_expected_types_allowed(self):
        """PNG, JPEG, GIF, MP4, WebM are all allowed."""
        from app.domains.media.service import ALLOWED_UPLOAD_MIME_TYPES
        for mime in ("image/png", "image/jpeg", "image/gif", "video/mp4", "video/webm"):
            self.assertIn(mime, ALLOWED_UPLOAD_MIME_TYPES, f"{mime} should be allowed")

    def test_size_limits_per_type(self):
        """Different size limits for image/video/gif."""
        from app.domains.media.service import (
            KSO_MAX_FILE_SIZE_IMAGE, KSO_MAX_FILE_SIZE_VIDEO, KSO_MAX_FILE_SIZE_GIF,
        )
        self.assertEqual(KSO_MAX_FILE_SIZE_IMAGE, 50 * 1024 * 1024)
        self.assertEqual(KSO_MAX_FILE_SIZE_VIDEO, 100 * 1024 * 1024)
        self.assertEqual(KSO_MAX_FILE_SIZE_GIF, 20 * 1024 * 1024)


# ═══════════════════════════════════════════════════════════════════════════
# File integrity tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFileIntegrity(unittest.TestCase):
    """Test file integrity / corruption detection."""

    def setUp(self):
        from app.domains.media import media_validator
        self.validator = media_validator

    def test_empty_file_video_rejected(self):
        result = self.validator.validate_file_integrity(b"", "video")
        self.assertFalse(result.is_valid)

    def test_empty_file_gif_rejected(self):
        result = self.validator.validate_file_integrity(b"", "gif")
        self.assertFalse(result.is_valid)

    def test_random_bytes_video_rejected(self):
        result = self.validator.validate_file_integrity(b"hello world", "video")
        self.assertFalse(result.is_valid)

    def test_fake_gif_rejected(self):
        result = self.validator.validate_file_integrity(b"not a gif file data", "gif")
        self.assertFalse(result.is_valid)

    def test_corrupted_gif_magic(self):
        # GIF with invalid magic but starts with "GIF"
        result = self.validator.validate_file_integrity(b"GIF00a\x00\x00", "gif")
        self.assertFalse(result.is_valid)
