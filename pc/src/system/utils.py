import sys

from pathlib import Path


def program_metadata_path() -> Path:
    if getattr(sys, 'frozen', False):
        root_path = Path(sys.executable).resolve().parent
    else:
        root_path = Path(sys.argv[0]).resolve().parent

    return root_path / 'metadata'
