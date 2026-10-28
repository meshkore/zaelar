"""Moved to `nucleo/llm/model_spec.py` (refactor2710-02): this name IS that module until the sections that import it land."""
import sys

from nucleo.llm import model_spec as _moved

sys.modules[__name__] = _moved
