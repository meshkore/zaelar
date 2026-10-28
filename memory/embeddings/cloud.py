"""The CLOUD embeddings backend (OpenAI `/embeddings` protocol) — the table's titular.

Every name a test or the panel can swap (`_mem_cfg`, `_cloud_key`, `_cloud_base_url`, `_post_json`…) is read
through the package (`_e()`), so a patch on `memory.embeddings` governs this module too.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request

from ..schema import EMBED_DIM

logger = logging.getLogger("zaelar.memory.embeddings")

# Models that accept `dimensions` (matryoshka): 768 dims scored 12/12 on ES+EN recall, the same as 1536, and fits
# the `EMBED_DIM` the vector table is created with — adopting the provider forces no schema migration.
_MATRYOSHKA = ("text-embedding-3",)

# ONE keep-alive connection for every cloud embed (refactor2710-11 T-03). The query of every turn's recall is
# embedded here, and a fresh connection per call paid DNS+TCP+TLS on each one: measured on real traffic, 1.4 s
# cold and 210-600 ms warm per call against 160-250 ms on a reused connection — the difference between closing
# the 0.8 s recall budget and every turn falling back to the lexical half. `keepalive_expiry` outlives the gap
# between two spoken turns; a connection the server closed meanwhile is discarded, not reused.
_HTTP = None        # httpx.Client (thread-safe) | False = httpx unavailable → urllib, one connection per call
_KEEPALIVE_S = float(os.getenv("ZAELAR_EMBED_KEEPALIVE_S", "120"))

#: The provider's own words for the last failed call (a whole demo pass ran on FTS and the diagnostic said «key,
#: quota or network» — it was `insufficient_quota`, sitting in the body).
_LAST_ERROR = {"v": ""}


def _e():
    from memory import embeddings
    return embeddings


def _cloud_base_url() -> str:
    return (str(_e()._mem_cfg().get("embed_base_url") or "").strip()
            or os.getenv("ZAELAR_EMBED_BASE_URL") or "https://api.openai.com/v1")


def _cloud_model() -> str:
    # store (panel) > env > default. Changing the model REQUIRES a re-embed (memory/reembed.py) — never mix spaces.
    return (str(_e()._mem_cfg().get("embed_model") or "").strip()
            or os.getenv("ZAELAR_EMBED_MODEL") or "text-embedding-3-small")


def _cloud_key() -> str:
    """The credential BY NAME, from the table's own row (`key_env` of `embeddings`), never inferred from the URL:
    memory does not import the brain's resolver, and guessing is how one provider's key reaches another's host.
    Pointing `embed_base_url` at another provider means putting its key in `embed_api_key` too."""
    inline = str(_e()._mem_cfg().get("embed_api_key") or "").strip()
    if inline:
        return inline
    env_name = "OPENAI_API_KEY"
    try:
        from config import models as _table
        env_name = str((_table.rungs("embeddings")[0] or {}).get("key_env") or "") or env_name
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(env_name, "")


def _cloud_dims() -> int | None:
    """Dims to REQUEST, or None if the model does not accept the parameter (then its native dim rules)."""
    return EMBED_DIM if any(m in _e()._cloud_model().lower() for m in _MATRYOSHKA) else None


def last_error() -> str:
    return _LAST_ERROR["v"]


def _note_failure(e: BaseException) -> None:
    _LAST_ERROR["v"] = str(_e()._error_body(e) or e)[:300]
    logger.debug("cloud embeddings failed: %s", _LAST_ERROR["v"])


def _post_json(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """POST JSON over the pooled connection and decode the reply. Raises on any HTTP or transport error."""
    global _HTTP
    if _HTTP is None:
        try:
            import httpx
            _HTTP = httpx.Client(limits=httpx.Limits(keepalive_expiry=_KEEPALIVE_S))
        except Exception:  # noqa: BLE001 — no httpx: the stdlib path below, exactly as before
            _HTTP = False
    if _HTTP is not False:
        r = _HTTP.post(url, content=json.dumps(body).encode("utf-8"), headers=headers, timeout=timeout)
        if r.status_code >= 400:                  # the provider's reason travels to `last_error()`
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cloud_embed(texts: list[str], *, timeout: float | None = None) -> list[list[float]] | None:
    """POST `{base_url}/embeddings`. Returns None on ANY failure — a decision, not an omission: the caller turns it
    into `last_degraded`, the writer defers the vector and the space stays as it is. A 429 must never become a
    change of vector space (V2-103)."""
    e = _e()
    key = e._cloud_key()
    if not key:
        return None
    # No energy lease → no paid request; None is the same deferred-vector path as a 429.
    from nucleo import energy_lease
    if not energy_lease.check("embed"):
        return None
    body: dict = {"model": e._cloud_model(), "input": list(texts)}
    dims = e._cloud_dims()
    if dims:
        body["dimensions"] = dims
    # EGRESS: a mediated deployment sends this through egress with its own credential; self-host is untouched.
    from nucleo import llm_egress
    url, key = llm_egress.route_url(e._cloud_base_url().rstrip("/") + "/embeddings", key)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
               "User-Agent": llm_egress.USER_AGENT}
    try:
        data = e._post_json(url, body, headers, timeout or float(os.getenv("ZAELAR_EMBED_TIMEOUT_S", "20")))
        rows = sorted(data["data"], key=lambda it: it.get("index", 0))
        out = [list(map(float, it["embedding"])) for it in rows]
        if len(out) != len(texts):
            return None
        # METERING — a deliberate exception to «memory/ does not import nucleo/»: this runs on every insert and
        # every query, and a register-a-callback design leaks unmetered usage for whoever forgets to register.
        # Metering never takes down the metered (V2-097), hence the swallow.
        try:
            from nucleo.energy_meter import meter_openai_response
            meter_openai_response(data, base_url=e._cloud_base_url(), model=e._cloud_model())
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception as ex:  # noqa: BLE001
        _note_failure(ex)
        return None
