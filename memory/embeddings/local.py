"""The LOCAL embeddings backends: Ollama (`embeddinggemma`, a self-hoster's choice) and fastembed (the safety net).

The verdict flags (`_ollama_busy`, `_ollama_timeout`) and the loaded fastembed model are package state — the
resolver reads them and `reset()` clears them — so this module reads and writes them through `_e()`.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.request

_BUSY_MARKERS = ("server busy", "maximum pending requests", "overloaded", "too many requests")

#: The resolution PROBE's clock, apart from a real call's (V2-349): «are you there?» blocks the FIRST memory access
#: of a fresh process (the vector table's DDL needs the dimension); a real embedding is on a turn's hot path,
#: where waiting beats degrading.
_PROBE_ENV = "ZAELAR_EMBED_PROBE_TIMEOUT"
_PROBE_DEFAULT_S = 1.5


def _e():
    from memory import embeddings
    return embeddings


def _ollama_host() -> str:
    return os.getenv("ZAELAR_EMBED_HOST") or os.getenv("OLLAMA_HOST") or "http://localhost:11434"


def _ollama_model() -> str:
    # store (UI) > env > default. Changing the model REQUIRES a re-embed (memory/reembed.py) — never mix spaces.
    return (str(_e()._mem_cfg().get("embed_model") or "").strip()
            or os.getenv("ZAELAR_EMBED_MODEL") or "embeddinggemma")


def probe_budget_s() -> float:
    try:
        return max(0.1, float(os.getenv(_PROBE_ENV, str(_PROBE_DEFAULT_S))))
    except Exception:
        return _PROBE_DEFAULT_S


def _looks_busy(detail) -> bool:
    return any(m in str(detail or "").lower() for m in _BUSY_MARKERS)


def _error_body(ex: Exception) -> str:
    """A provider's reason lives in the HTTPError's body, which is readable exactly once."""
    try:
        return ex.read().decode("utf-8", "replace")[:300]      # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return str(ex)


def _note_ollama_outcome(*, busy: bool) -> None:
    _e()._ollama_busy = bool(busy)


def _indexed_space_to_defend() -> bool:
    """Is there an INDEXED vector space to protect? (V2-350). «A timeout is not an absence» keeps `ollama` when the
    probe runs out of time — right when a sealed index would be corrupted by a demotion, wrong on an unsealed,
    vector-less DB where fastembed would give real semantic recall. The signature answers exactly that; in doubt,
    defend: over-demoting corrupts silently, over-keeping costs a visible lexical recall."""
    try:
        from memory import reembed as _reembed          # lazy: `reembed` imports this package
        return _reembed.stored_signature() is not None
    except Exception:  # noqa: BLE001
        return True


def _ollama_embed(texts: list[str], *, timeout: float | None = None) -> list[list[float]] | None:
    """`timeout=None` → a REAL call's budget (`ZAELAR_EMBED_TIMEOUT`, 20 s); the resolution probe passes its own,
    much shorter one — two different questions (V2-349)."""
    e = _e()
    try:
        # keep_alive: keep the embedding model RESIDENT — a local distiller can evict it from VRAM and the next
        # recall would pay the reload (~4 s measured).
        payload = {"model": e._ollama_model(), "input": texts,
                   "keep_alive": os.getenv("ZAELAR_EMBED_KEEP_ALIVE", "30m")}
        req = urllib.request.Request(e._ollama_host().rstrip("/") + "/api/embed", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            from voice.observer import mark_busy as _mb    # contention mark while the GPU embed blocks
        except Exception:
            _mb = None
        if _mb:
            _mb("embed", True)
        try:
            # A real call deserves its 20 s — but if Ollama last failed to answer in time, real calls use the short
            # clock too until a probe answers: the space is kept, THAT call's vector is deferred.
            budget = (timeout if timeout is not None
                      else (e.probe_budget_s() if e._ollama_timeout
                            else float(os.getenv("ZAELAR_EMBED_TIMEOUT", "20"))))
            with urllib.request.urlopen(req, timeout=budget) as r:
                data = json.load(r)
        finally:
            if _mb:
                _mb("embed", False)
        try:
            from voice.observer import perf
            perf(f"embed {e._ollama_model()} ×{len(texts)} {round((time.time() - t0) * 1000)}ms",
                 module="memory", func="embeddings._ollama_embed", ms=(time.time() - t0) * 1000)
        except Exception:
            pass
        embs = data.get("embeddings")
        if embs and len(embs) == len(texts):
            e._ollama_timeout = False          # it answered: the short clock is over
            _note_ollama_outcome(busy=False)
            return embs
        _note_ollama_outcome(busy=e._looks_busy(data.get("error")))
    except Exception as ex:  # noqa: BLE001
        # The HTTPError's body carries the reason: «server busy» is a queue that drains, «connection refused» a
        # server that is not there — and a TIMEOUT is a third answer («I don't know yet»), never an absence:
        # absence DEMOTES the process and demoting CHANGES THE VECTOR SPACE.
        e._ollama_timeout = isinstance(ex, (TimeoutError, socket.timeout)) or "timed out" in str(ex).lower()
        _note_ollama_outcome(busy=e._looks_busy(e._error_body(ex)))
        return None
    return None


def _fastembed_embed(texts: list[str]) -> list[list[float]] | None:
    e = _e()
    try:
        if e._fastembed_model is None:
            from fastembed import TextEmbedding  # type: ignore

            from memory import model_cache
            # Without `cache_dir` the model lands in the system TEMP, which is purged (see `model_cache.py`).
            cache = model_cache.models_dir()
            e._fastembed_model = TextEmbedding(**({"cache_dir": cache} if cache else {}))
        return [list(map(float, v)) for v in e._fastembed_model.embed(texts)]
    except Exception:
        return None
