"""Moved to `nucleo/llm/tool_drops.py` (refactor2710-02): this name IS that module until the sections that import it land."""
import sys
from nucleo.llm import tool_drops as _moved
sys.modules[__name__] = _moved
