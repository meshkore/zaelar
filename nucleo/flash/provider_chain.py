"""Moved to `nucleo/llm/provider_chain.py` (refactor2710-02): this name IS that module until the sections that import it land."""
import sys
from nucleo.llm import provider_chain as _moved
sys.modules[__name__] = _moved
