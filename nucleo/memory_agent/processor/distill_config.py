"""Where the distiller (the write HEART) sends its call: titular endpoint, model, key and the relay chain.

Config `§memory.mem_processor_*` wins, then the env (power-user / headless), then a last resort that must equal
the checked-in config default — a default that only works on the author's machine is not a default. The FALLBACK
order lives once, in `llm_routes._FAILOVER["distill"]`; this module only owns the titular.
"""
from __future__ import annotations

import os

from loguru import logger

TIMEOUT = float(os.getenv("MEM_PROCESSOR_TIMEOUT", "30"))   # s per ATTEMPT; off the hot path but bounded
#: Browser UA: AIMLAPI sits behind Cloudflare and 403s aiohttp's default User-Agent. Harmless elsewhere.
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# A transient failure (timeout / connection / 429 / 5xx) is retried — writing is off the hot path and a lost turn is
# lost for good. An auth / bad-request 4xx is never retried.
RETRIES = max(0, int(os.getenv("MEM_PROCESSOR_RETRIES", "2")))           # retries (=> RETRIES+1 attempts)
RETRY_BACKOFF = float(os.getenv("MEM_PROCESSOR_RETRY_BACKOFF", "1.5"))   # s base, scaled by attempt
# Ceiling of a LOCAL (Ollama) rung, apart from TIMEOUT: a big local model was measured at 372 s for ONE
# distillation. High so a big local model can arrive, not because a write should take minutes.
LOCAL_TIMEOUT = float(os.getenv("MEM_PROCESSOR_LOCAL_TIMEOUT", "420"))

_FALLBACK_URL = "https://api.aimlapi.com/v1"
_FALLBACK_MODEL = "deepseek/deepseek-v4-flash"


def _memory_cfg(field: str) -> str:
    try:
        from config import v2 as _v2
        return (_v2.get("memory").get(field) or "").strip()
    except Exception:
        return ""


def _config_url() -> str:
    return _memory_cfg("mem_processor_base_url")


def url() -> str:
    return _config_url() or os.getenv("MEM_PROCESSOR_URL") or os.getenv("ZAELAR_LOCAL_LLM_URL") or _FALLBACK_URL


def model() -> str:
    # ⚠️ A LOCAL model shares the GPU with STT/TTS: a heavy one can cut the voice (measured 15-29 s stalls).
    return _memory_cfg("mem_processor_model") or os.getenv("MEM_PROCESSOR_MODEL") or _FALLBACK_MODEL


def endpoint_key(base_url: str) -> str:
    # The credential follows the URL, never the other way round — one resolver for the engine (V2-098).
    from nucleo.provider_keys import key_for_endpoint
    return key_for_endpoint(base_url, default="local")


def key() -> str:
    """Config inline key → by endpoint. The loose env `MEM_PROCESSOR_KEY` only pairs with an env URL: a stale env
    key sent to a config URL once meant a silent 401 and two days of lossy heuristic writes."""
    k = _memory_cfg("mem_processor_api_key")
    if k:
        return k
    if _config_url():
        return endpoint_key(url())
    return os.getenv("MEM_PROCESSOR_KEY") or endpoint_key(url())


def enabled() -> bool:
    """The LLM distiller can be switched off (env `MEM_PROCESSOR=0`) → everything falls to the cheap heuristic."""
    return os.getenv("MEM_PROCESSOR", "1").strip().lower() not in ("0", "false", "no", "off")


def rung_chain() -> list[tuple[str, str]]:
    """`(base_url, model)` in the operator's provider order: our titular, then the declared fallbacks. Fail-open to
    the titular alone — a bad day for the fallback catalogue must not become a bad day for every write."""
    titular = (url(), model())
    head = [titular]
    extra: list = []
    # PIN: one rung, no relay. Only a per-model BENCH sets it, so its number measures that model and not the chain.
    if os.getenv("MEM_PROCESSOR_PIN_TITULAR") == "1":
        return head
    try:
        from nucleo.memory_agent.processor import llm_rungs
        extra = llm_rungs.failover_rungs("distill", titular=titular)
        # A local titular that is not answering is stepped over (TTL-cached, fail-closed probe); a model named
        # without its endpoint can never answer and is skipped and said once. Only with somewhere to step TO.
        if llm_rungs.is_local_endpoint(titular[0]) and not llm_rungs.local_titular_ready(*titular):
            if extra:
                head = []
                logger.info(f"CORAZON: local titular {titular[1]} @ {titular[0]} unavailable -> "
                            f"writing through {extra[0][1]}")
        elif llm_rungs.pair_incoherent(*titular) and extra:
            head = []
            llm_rungs.note_incoherent_pair("CORAZON", titular[0], titular[1], served=extra[0][1])
    except Exception:  # noqa: BLE001
        extra = []
    return head + [(u, m) for u, m, _k, _dt in extra]
