"""Local filesystem operations: folder creation."""

from pathlib import Path


FOLDERS = [
    "config",
    "manifest",
    "media/current",
    "media/staging",
    "media/quarantine",
    "pop",
    "status",
    "logs",
]


def create_folders(root: str | Path) -> None:
    """Create the full kso-adapter folder structure under root."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for folder in FOLDERS:
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
