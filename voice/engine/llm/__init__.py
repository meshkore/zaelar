"""LLM family — vendor-agnostic providers behind one registry.

The pipeline depends only on ``build_llm``; each vendor is a builder function in
``providers/`` returning a LiveKit ``llm.LLM``. Adding a vendor = one file there.

zaelar note (INI-012): the hermes/duo/direct providers are added later by another
change; ``providers/__init__`` only imports the vendor providers ported here.
"""
from __future__ import annotations

from livekit.agents.llm import LLM

from ..core.registry import Registry

registry = Registry("LLM")


def build_llm(provider: str, model: str = "") -> LLM:
    return registry.create(provider, model=model)  # type: ignore[return-value]


def available() -> list[str]:
    return registry.names()


from . import providers  # noqa: E402,F401  (import side effect: register builders)

__all__ = ["build_llm", "available", "registry"]
