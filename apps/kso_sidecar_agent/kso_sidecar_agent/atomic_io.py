"""Atomic JSON read/write with path-safety enforcement.

Securely writes JSON files: .tmp in the same directory, then os.replace().
Rejects symlink targets. Enforces paths stay inside the agent root.
"""

import json
import os
from pathlib import Path


# ── Atomic write ──────────────────────────────────────────────────────

def atomic_write_json(target: Path, data: dict) -> None:
    """Write JSON atomically: write to .tmp, then os.replace().

    Rules:
    - target MUST NOT be a symlink
    - parent directory MUST exist
    - temp file is written in the SAME directory (atomic within one FS)
    - uses ensure_ascii=False for human readability
    """

    target = target.resolve()

    # Reject symlinks — cannot safely replace them
    if target.is_symlink():
        raise ValueError(f"Refusing to write to symlink: {target}")

    parent = target.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"Parent directory does not exist: {parent}")

    # Write temp file in the same directory
    tmp = parent / f".{target.name}.tmp"
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(content, encoding="utf-8")

    try:
        os.replace(tmp, target)
    except OSError:
        # Clean up tmp on failure
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ── Simple read ───────────────────────────────────────────────────────

def read_json(path: Path) -> dict:
    """Read and parse a JSON file.

    Raises FileNotFoundError if missing, ValueError on invalid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


# ── Path safety ───────────────────────────────────────────────────────

def ensure_relative_to_root(root: Path, path: Path) -> Path:
    """Resolve path and verify it stays inside root.

    Returns the resolved Path.
    Raises ValueError if the path escapes root.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path escapes root: {path} → {resolved} (root: {root})"
        )
    return resolved
