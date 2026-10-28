"""Moved to `nucleo/llm/fast_client.py` (refactor2710-02): this name IS that module until the sections that import it land."""
import sys
from nucleo.llm import fast_client as _moved
sys.modules[__name__] = _moved
