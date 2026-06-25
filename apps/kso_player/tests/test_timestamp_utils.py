"""Tests for Python 3.6-compatible timestamp parser."""

from datetime import datetime
from unittest import TestCase

from kso_player.timestamp_utils import parse_iso_utc


class TestParseIsoUtc(TestCase):
    """Python 3.6-compatible ISO-8601 timestamp parsing."""

    def test_timestamp_with_Z_suffix(self):
        """'2024-06-24T14:30:00Z' → datetime."""
        dt = parse_iso_utc("2024-06-24T14:30:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 24)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)
        self.assertEqual(dt.second, 0)

    def test_timestamp_with_microseconds_Z(self):
        """'2024-06-24T14:30:00.573421Z' → datetime with microseconds."""
        dt = parse_iso_utc("2024-06-24T14:30:00.573421Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.microsecond, 573421)

    def test_timestamp_with_offset(self):
        """'+00:00' offset handled."""
        dt = parse_iso_utc("2024-06-24T14:30:00+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 14)

    def test_timestamp_with_microseconds_offset(self):
        """'.573421+00:00' handled."""
        dt = parse_iso_utc("2024-06-24T14:30:00.573421+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.microsecond, 573421)

    def test_timestamp_no_timezone(self):
        """No timezone suffix → treated as UTC."""
        dt = parse_iso_utc("2024-06-24T14:30:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 14)

    def test_timestamp_no_timezone_microseconds(self):
        """No timezone with microseconds."""
        dt = parse_iso_utc("2024-06-24T14:30:00.123456")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.microsecond, 123456)

    def test_invalid_timestamp_returns_none(self):
        """Garbage input → None (safe stale/hidden default)."""
        self.assertIsNone(parse_iso_utc("not-a-date"))
        self.assertIsNone(parse_iso_utc(""))
        self.assertIsNone(parse_iso_utc("2024-13-01T00:00:00Z"))

    def test_none_returns_none(self):
        """None input → None."""
        self.assertIsNone(parse_iso_utc(None))

    def test_non_string_returns_none(self):
        """Non-string → None."""
        self.assertIsNone(parse_iso_utc(12345))
        self.assertIsNone(parse_iso_utc(["2024-06-24"]))

    def test_no_fromisoformat_usage(self):
        """Verify the module does NOT call datetime.fromisoformat in code."""
        import inspect
        import kso_player.timestamp_utils as mod
        # Get source lines, skip docstring and comments
        source_lines = inspect.getsource(mod).split("\n")
        code_lines = [l for l in source_lines
                      if not l.strip().startswith('"""')
                      and not l.strip().startswith("#")
                      and not l.strip().startswith("Python 3.6")
                      and "fromisoformat" not in l[:20]]  # allow in docstring start
        code = "\n".join(code_lines)
        self.assertNotIn("fromisoformat", code)

    def test_result_is_naive_datetime(self):
        """Result is naive UTC datetime (no tzinfo)."""
        dt = parse_iso_utc("2024-06-24T14:30:00Z")
        self.assertIsNone(dt.tzinfo)

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace handled."""
        dt = parse_iso_utc("  2024-06-24T14:30:00Z  ")
        self.assertIsNotNone(dt)

    def test_real_kso_format(self):
        """Real KSO timestamp format from state observer: '2026-06-25T12:34:56.789012Z'."""
        dt = parse_iso_utc("2026-06-25T12:34:56.789012Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.microsecond, 789012)
