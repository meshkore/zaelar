"""nucleo/workflows — «for this kind of errand, what is the fastest channel, and is that still true?» (V2-583).

The public seam is this package: `domain_of`, `plan`, `learn`, `note_empty`, `forget`.
"""
from .domains import domain_of
from .store import Plan, forget, learn, note_empty, plan

__all__ = ["domain_of", "plan", "learn", "note_empty", "forget", "Plan"]

from . import store  # noqa: E402  — `workflows.store.CH_MESH` etc. without a second import at call sites
