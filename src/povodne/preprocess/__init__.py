"""Preprocess step (M2): raw/ -> aligned/ + masks/ on the 10 m reference grid (docs/ARCHITECTURE.md, D-X-06)."""
from .pipeline import run

__all__ = ["run"]
