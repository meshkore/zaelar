"""nucleo/websearch.py — ALIAS of `search.web` (V2-782 T5.1).

The search layer moved to its own package, `search/`. This module keeps the old import path alive for every
caller and every test that still says `from nucleo import websearch`: it binds the SAME module object, so an
attribute patched through either name is patched for both. New code imports `search.web` directly.
"""
import sys as _sys

from search import web as _target

_sys.modules[__name__] = _target
