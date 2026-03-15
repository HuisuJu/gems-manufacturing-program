import sys
from pathlib import Path


def metadata_folder() -> Path:
    """Return metadata directory path, creating it if needed."""
    if getattr(sys, "frozen", False):
        root_path = Path(sys.executable).resolve().parent
    else:
        root_path = Path(sys.argv[0]).resolve().parent

    metadata_folder = root_path / "metadata"
    metadata_folder.mkdir(parents=True, exist_ok=True)

    return metadata_folder
