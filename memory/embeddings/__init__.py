"""memory/embeddings — the memory's embeddings (V2-002 · T46; CLOUD provider since V2-501).

Computed **on insert** (writer) and **on query** (retriever). Backends, titular first, resolved lazily and cached:
  1. **cloud** (`cloud.py`, OpenAI `/embeddings` protocol) — the TITULAR, `text-embedding-3-small` at 768 dims.
     The only one that runs identically on a laptop and in a container: *local must measure what a container
     deployment measures*.
  2. **Ollama** (`local.py`, `embeddinggemma`) — a self-hoster's choice; databases sealed with its signature exist.
  3. **fastembed** (`local.py`) — a safety net, not a titular: its default model is English-only.
  4. **hashing** (`vectors.py`) — always available, lexical signal only; tests and bare environments.

Every vector is L2-normalised (sqlite-vec's L2 then behaves like cosine) and has the ACTIVE backend's dimension.
**A titular failure NEVER changes the space**: the call fails, `last_degraded` says so, the writer defers the vector
(`embed_pending`, repaired by REM) and the reader drops to lexical (V2-103). This module holds the state and the
resolution; the provider modules read it through the package, so a patch here governs them.
"""
import logging
import os
import time
import urllib.request  # noqa: F401 — the stdlib door the suite patches as `embeddings.urllib.request`

from ..schema import EMBED_DIM
from .cloud import (  # noqa: F401
    _MATRYOSHKA, _cloud_base_url, _cloud_dims, _cloud_embed, _cloud_key, _cloud_model, _post_json, last_error)
from .health import _HEALTHY, _report_degraded, _warn_if_degraded  # noqa: F401
from .local import (  # noqa: F401
    _BUSY_MARKERS, _PROBE_DEFAULT_S, _PROBE_ENV, _error_body, _fastembed_embed, _indexed_space_to_defend,
    _looks_busy, _ollama_embed, _ollama_host, _ollama_model, probe_budget_s)
from .vectors import _TOKEN_RE, _fit_dim, _hash_embed, _l2_normalize  # noqa: F401

logger = logging.getLogger("zaelar.memory.embeddings")

_backend: str | None = None      # 'cloud' | 'ollama' | 'fastembed' | 'hash'
_fastembed_model = None
_active_dim: int | None = None   # dim of the ACTIVE model (V2-031: provider-driven)
_resolved_at: float = 0.0        # when `_backend` was last resolved (for the re-check)
_forced: bool = False            # True = explicit config/env → never re-checked (the operator's choice stands)
_ollama_busy = False             # last outcome was «alive but saturated», not «absent»
_ollama_timeout = False          # last outcome was «did not answer in time» — not «absent» either
# A DEGRADED automatic resolution is re-probed after this TTL (V2-103: a boot-time hiccup used to pin fastembed
# for the life of the process). A healthy backend is never re-probed.
_BACKEND_RECHECK_S = float(os.getenv("ZAELAR_EMBED_RECHECK_S", "300"))
#: Observable flag of the LAST call: a hot fall to hash must never reach the persistent index (the writer reads it).
last_degraded: bool = False
_last_live_degraded: bool | None = None

# Known dim by model (saves a network probe), substring-matched; unknown ones use the REAL first vector's length.
# A family whose sizes differ in width (one name, 1024 to 4096 dims) is left to the probe on purpose.
_MODEL_DIMS = {
    "embeddinggemma": 768, "nomic-embed-text": 768, "all-minilm": 384,
    "bge-m3": 1024, "bge-large": 1024, "multilingual-e5-large": 1024, "e5-large": 1024,
    "snowflake-arctic-embed-l": 1024, "arctic-embed-l": 1024, "mxbai-embed-large": 1024,
}


def _mem_cfg() -> dict:
    """The memory section of config/v2 (store > env); without config (isolated tests), empty."""
    try:
        from config import v2 as _v2
        return _v2.get("memory")
    except Exception:
        return {}


def _resolve_backend():
    global _backend, _resolved_at, _forced, _ollama_busy, _ollama_timeout
    if _backend is not None:
        # Re-check only an AUTOMATIC, DEGRADED resolution past its TTL — never an explicit choice or a healthy one.
        if _forced or _backend in _HEALTHY or (time.time() - _resolved_at) < _BACKEND_RECHECK_S:
            return
    # store (`memory.embed_provider`) > env `ZAELAR_EMBED_BACKEND` > autodetection. Each source normalises
    # «auto»/"" to empty BEFORE the `or`, or a factory «auto» in config would hide the env var.
    cfg_val = str(_mem_cfg().get("embed_provider") or "").strip()
    if cfg_val == "auto":
        cfg_val = ""
    forced = cfg_val or os.getenv("ZAELAR_EMBED_BACKEND")
    if forced in ("auto", ""):
        forced = None
    # The table names the PROVIDER ('openai', its protocol); the backend is 'cloud' because any compatible endpoint
    # serves. One alias here, so the `.embedsig` signature does not depend on the panel's spelling.
    if forced in ("openai", "cloud", "azure", "voyage"):
        forced = "cloud"
    if forced:
        _backend, _forced, _resolved_at = forced, True, time.time()
        _warn_if_degraded(_backend, forced=True)
        return
    _forced = False
    prev = _backend
    _ollama_busy = _ollama_timeout = False     # the verdict flags describe THIS probe only
    # The PROBE has its own clock (V2-349): with a real call's 20 s, a fresh process's first memory access cost 20.8 s.
    if _cloud_key() and _cloud_embed(["ping"], timeout=probe_budget_s()) is not None:
        _backend = "cloud"
    elif _ollama_embed(["ping"], timeout=probe_budget_s()) is not None:
        _backend = "ollama"
    elif (timed_out := _ollama_timeout and _indexed_space_to_defend()) or _ollama_busy:
        # A TIMEOUT or a SATURATED queue is not an absence: demoting would CHANGE THE VECTOR SPACE (fastembed is 384
        # dims padded to 768 against an index sealed with embeddinggemma at 768 — V2-103's 51.6% vector-less rows). The
        # space is kept, the call's vector deferred, and the very next call re-probes (`_resolved_at` in the past).
        _backend = "ollama"
        logger.info("memoria: Ollama %s (no ausente) — se conserva el espacio vectorial y se re-sondea en la "
                    "próxima llamada", f"no respondió a la sonda en {probe_budget_s():.1f}s" if timed_out
                    else "SATURADO")
        _resolved_at = 0.0
        _warn_if_degraded(_backend, forced=False)
        return
    elif _fastembed_embed(["ping"]) is not None:
        _backend = "fastembed"
    else:
        _backend = "hash"
    _resolved_at = time.time()
    if prev is not None and prev != _backend:
        logger.info("memoria: backend de embeddings pasó de '%s' a '%s' tras re-intento", prev, _backend)
    _warn_if_degraded(_backend, forced=False)


def active_backend() -> str:
    """Backend in use ('cloud'|'ollama'|'fastembed'|'hash'). Resolved lazily. For tests/diagnostics."""
    _resolve_backend()
    return _backend  # type: ignore


def reset():
    """Forget the resolved backend (tests that change env). The verdict flags go with it: an inherited
    `_ollama_timeout` would leave REAL calls on the short clock forever."""
    global _backend, _fastembed_model, _active_dim, _resolved_at, _forced, _ollama_busy, _ollama_timeout
    _backend, _fastembed_model, _active_dim, _resolved_at, _forced = None, None, None, 0.0, False
    _ollama_busy = _ollama_timeout = False


def _active_model_name() -> str:
    if _backend == "cloud":
        return _cloud_model()
    if _backend == "ollama":
        return _ollama_model()
    # ⚠️ KNOWN MISLABEL, left alone on purpose: for fastembed this names the config's (Ollama) model, not the loaded
    # `bge-small-en-v1.5`. `dim()` matches this string against `_MODEL_DIMS`, so the truthful name would move the
    # dimension 768 → 384 — a vector-space MIGRATION, its own task. Nothing that decides behaviour reads it wrong.
    if _backend == "fastembed":
        return str(_mem_cfg().get("embed_model") or os.getenv("ZAELAR_EMBED_MODEL") or "")
    return ""


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embeddings of a list of texts, always `dim()`-wide and L2-normalised. A live failure of the real backend
    degrades to hashing ONLY as the return value, flagged in `last_degraded` — never for the persistent index."""
    global last_degraded
    if not texts:
        return []
    _resolve_backend()
    d = dim()
    out: list[list[float]] | None = None
    if _backend == "cloud":
        out = _cloud_embed(texts)
    elif _backend == "ollama":
        out = _ollama_embed(texts)
    elif _backend == "fastembed":
        out = _fastembed_embed(texts)
    # Only a HOT fall is degradation; a CONFIGURED 'hash' is its own consistent space (governed by the signature).
    last_degraded = out is None and _backend != "hash"
    _report_live_outcome(degraded=last_degraded)
    if out is None:
        out = [_hash_embed(t, d) for t in texts]
    return [_l2_normalize(_fit_dim(v, d)) for v in out]


def _report_live_outcome(*, degraded: bool) -> None:
    """Amber while the titular fails LIVE calls, cleared on the first success — only on CHANGE (this runs on every
    insert and query). (V2-758) There is deliberately no second MODEL to fail over to: an embedding model DEFINES
    the space every stored pill lives in, so a stand-in answers in coordinates comparable with nothing stored —
    moving it is a re-embed, never a failover. So the degradation is made visible instead."""
    global _last_live_degraded
    if degraded == _last_live_degraded:
        return
    _last_live_degraded = degraded
    try:
        from voice import health_state
        if degraded:
            health_state.record("memory", "degraded",
                                f"embeddings: «{_active_model_name()}» no contestó — el recuerdo se guarda SIN "
                                f"vector y la búsqueda por significado cae a léxica (no se cambia de espacio)")
        else:
            # The light is shared with the heart, REM, the retriever and the recall budget: only OUR amber goes.
            _cur = health_state.get("memory") or {}
            if str(_cur.get("text") or "").startswith("embeddings:"):
                health_state.clear("memory")
    except Exception:  # noqa: BLE001
        pass  # observability NEVER breaks the memory


def embed(text: str) -> list[float]:
    """Embedding of one text → an L2-normalised vector of the active dimension."""
    return embed_batch([text])[0]


def dim() -> int:
    """Dimension of the ACTIVE embedding (V2-031): registry by name → real probe → default. Cached (`reset()`
    forgets it); the `vec_memories` schema and `reembed` create the vector table with it."""
    global _active_dim
    if _active_dim is not None:
        return _active_dim
    _resolve_backend()
    if _backend == "hash":
        _active_dim = EMBED_DIM
        return _active_dim
    if _backend == "cloud":
        # A matryoshka model's dim is the one WE request; a registry by name would guess the native 1536.
        d = _cloud_dims()
        if d:
            _active_dim = d
            return _active_dim
    name = _active_model_name().lower()
    for k, d in _MODEL_DIMS.items():
        if k in name:
            _active_dim = d
            return _active_dim
    probe = (_cloud_embed(["x"]) if _backend == "cloud"
             else _ollama_embed(["x"]) if _backend == "ollama"
             else _fastembed_embed(["x"]) if _backend == "fastembed" else None)
    _active_dim = len(probe[0]) if probe else EMBED_DIM
    return _active_dim
