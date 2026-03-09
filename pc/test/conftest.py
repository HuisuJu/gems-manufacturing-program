import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Backward-compatible import alias used by current app modules.
import stream  # noqa: E402

sys.modules.setdefault("connection", stream)
