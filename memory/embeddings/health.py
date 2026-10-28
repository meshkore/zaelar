"""Saying it when the embeddings DEGRADE — a memory failure never stays a log line.

This module logs with the stdlib (no timestamps, lost in the boot noise), so a demotion also turns the ◉ amber.
A FORCED backend (`ZAELAR_EMBED_BACKEND`, set by the suite) is a choice, not a fault, and is never reported.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.memory.embeddings")

#: Backends that are a legitimate operator CHOICE. Anything else is degradation: a WORSE signal than the one the
#: database is indexed with.
_HEALTHY = ("cloud", "ollama")


def _warn_if_degraded(backend: str, forced: bool) -> None:
    """T176 — recall BY MEANING holds up at scale on the cloud titular and embeddinggemma; fastembed collapses (and
    its default model is English-only) and 'hash' is lexical-only. Dropping to one is said, once."""
    if backend in _HEALTHY:
        return
    src = "forced by ZAELAR_EMBED_BACKEND" if forced else "the titular provider is NOT available"
    if backend == "hash":
        logger.warning("⚠️ memory: embeddings on 'hash' (%s) — SEMANTIC recall practically DISABLED (lexical FTS "
                       "only). Check the embedding provider's credential.", src)
    else:  # fastembed or other
        logger.warning("⚠️ memory: embeddings on '%s' (%s) — semantic recall DEGRADED (collapses at scale and its "
                       "default model is English-only, T176).", backend, src)
    _report_degraded(backend, forced)


def _report_degraded(backend: str, forced: bool) -> None:
    if forced:
        return
    try:
        from voice import health_state
        health_state.record("memory", "degraded",
                            f"embeddings on '{backend}': the titular provider is not available — "
                            f"recall by meaning {'DISABLED' if backend == 'hash' else 'degraded'}")
    except Exception:  # noqa: BLE001
        pass  # observability NEVER breaks the memory
