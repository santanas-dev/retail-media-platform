"""Timestamp parsing — Python 3.6 compatible (NO datetime.fromisoformat).

Python 3.6 does not have datetime.fromisoformat (added in 3.7).
This module provides a drop-in replacement that handles all common
ISO-8601 formats used in the KSO runtime path.

Formats handled:
    - "2024-06-24T14:30:00Z"
    - "2024-06-24T14:30:00.573421Z"
    - "2024-06-24T14:30:00+00:00"
    - "2024-06-24T14:30:00.573421+00:00"
    - "2024-06-24T14:30:00"  (no timezone, treated as UTC)

Returns naive UTC datetime or None on failure.
Never raises — invalid timestamps return None (safe stale/unknown default).
"""

from datetime import datetime


def parse_iso_utc(ts_str):
    """Parse ISO-8601 timestamp string to naive UTC datetime.

    Python 3.6 compatible — uses strptime, NOT fromisoformat.
    Returns naive UTC datetime or None on failure.
    """
    if not ts_str or not isinstance(ts_str, str):
        return None

    ts = ts_str.strip()

    # Strip timezone suffix
    if ts.endswith("Z"):
        ts = ts[:-1]
    elif "+" in ts[10:]:  # +00:00 offset
        ts = ts.rsplit("+", 1)[0]
    elif ts.count("-") > 2:  # -00:00 offset (rare)
        # Find last '-' after 'T'
        t_pos = ts.find("T")
        if t_pos > 0:
            after_t = ts[t_pos + 1:]
            if after_t.count("-") > after_t.count(":"):
                ts = ts.rsplit("-", 1)[0]

    # Try with microseconds first
    if "." in ts:
        try:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            pass

    # Try without microseconds
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
