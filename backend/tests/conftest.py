"""Configuration pytest : rend importables `app` (backend) et `data_gen` (racine)."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
for p in (BACKEND, ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
