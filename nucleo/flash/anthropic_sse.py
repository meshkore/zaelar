"""Moved to `nucleo/llm/anthropic_sse.py` (refactor2710-02): this name IS that module until the sections that import it land."""
import sys
from nucleo.llm import anthropic_sse as _moved
sys.modules[__name__] = _moved
