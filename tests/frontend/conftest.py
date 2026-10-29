import sys
from pathlib import Path

RAIZ_FRONT = str(Path(__file__).resolve().parents[2] / "frontend")
if RAIZ_FRONT not in sys.path:
    sys.path.insert(0, RAIZ_FRONT)
