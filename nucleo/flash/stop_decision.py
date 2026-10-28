"""Moved to `nucleo/request/stop.py` (refactor2710-02): this name IS that module until the sections that import it land."""
import sys

from nucleo.request import stop as _moved

sys.modules[__name__] = _moved
