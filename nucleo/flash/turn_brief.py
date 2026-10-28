"""Moved to `nucleo/turn/brief.py` (refactor2710-07): this name IS that module until the sections that import it land."""
import sys

from nucleo.turn import brief as _moved

sys.modules[__name__] = _moved
