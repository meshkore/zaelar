"""nucleo/websearch.py — BÚSQUEDA WEB de datos, COMPARTIDA por los dos cerebros (V2-022).

Capacidad de búsqueda **model-agnóstica** (no dependemos de que el modelo traiga búsqueda nativa — Grok/GLM/Z.AI
no la tienen; Claude Code sí): un primitivo propio que cualquier parte del sistema puede llamar.

TRES modalidades de "buscar", que NO se confunden:
  1. **Dato directo + SÍNTESIS** (este módulo) — "¿quién ganó el partido?", el tiempo, un precio, una previsión.
     Ruta ligera; el FlashBrain la usa por la tool `web_search`, resuelta EN el turno; el SlowBrain la usa para
     alimentar informes con datos actuales. La calidad manda: si hay un proveedor de **respuesta-IA** (Perplexity /
     Tavily / Brave summarizer / grounding de Gemini) la respuesta llega YA sintetizada y citada; si no, caemos a
     snippets crudos (DuckDuckGo/Brave) y el cerebro los sintetiza con el modelo que ya paga por turno.
  2. **Navegación de una web / marketplace** (Amazon, Wallapop…) — NO es esto: no hay un buscador que devuelva ese
     dato, hay que ENTRAR y navegar. Lo hace el **navegador** (`widgets/navegador/`, `automate_web`, SlowBrain).
  3. **Investigación profunda / informe** (estudio con muchos datos actuales) — el SlowBrain (CodeAgent) con
     `WebSearch`/`WebFetch` nativos (Claude Code) y/o este primitivo en bucle; síntesis en el propio agente.

DISEÑO por CAPAS (calidad primero, coste después; auto-upgrade por key):
  - Orden de proveedores: **respuesta-IA** (Perplexity → Tavily, si hay key) → **snippets** (Brave, si hay key) →
    **gratis** (DuckDuckGo HTML, sin key, siempre disponible). Override explícito con `WEBSEARCH_PROVIDER`.
  - SIEMPRE fuera del event loop (el llamador usa `asyncio.to_thread`): es I/O de red bloqueante.
  - Fail-open: ante error degrada al siguiente proveedor; si todo falla, vacío — el cerebro lo dice, nunca revienta.

Claves (env / `.meshkore/credentials/zaelar.env`, gestionable por UI más adelante):
  `PERPLEXITY_API_KEY` · `TAVILY_API_KEY` · `BRAVE_SEARCH_KEY`. Sin ninguna → funciona gratis con DuckDuckGo.
"""
from __future__ import annotations

import html as _html
import os
import re as _re
import time as _time
from urllib.parse import parse_qs, unquote, urlparse

from loguru import logger
from nucleo.errors import brief as _brief

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0"))
_MAX_RESULTS = 5


# ── keys / selección de proveedor ────────────────────────────────────────────────────────────────────────
def _key(*names: str) -> str:
    for n in names:
        v = (os.getenv(n) or "").strip()
        if v:
            return v
    return ""


def perplexity_key() -> str: return _key("PERPLEXITY_API_KEY", "PPLX_API_KEY")
def tavily_key() -> str: return _key("TAVILY_API_KEY")
def brave_key() -> str: return _key("BRAVE_SEARCH_KEY", "BRAVE_API_KEY")


def _google_on() -> bool:
    """La capa GRATIS de Google-vía-navegador (V2-024). ON salvo BROWSER_SEARCH=0."""
    try:
        from nucleo import browser_search
        return browser_search.enabled()
    except Exception:
        return False


def provider() -> str:
    """Proveedor activo, CALIDAD primero. Override con WEBSEARCH_PROVIDER (perplexity|tavily|brave|google|ddg).
    Sin keys de pago, el DEFAULT es **google** (gratis vía Chromium propio, mejor que DDG); DDG queda de último
    recurso (fallback si Google bloquea)."""
    forced = (os.getenv("WEBSEARCH_PROVIDER") or "").strip().lower()
    if forced:
        return forced
    if perplexity_key():
        return "perplexity"
    if tavily_key():
        return "tavily"
    if brave_key():
        return "brave"
    if _google_on():
        return "google"
    return "ddg"


def is_ai_answer(src: str | None = None) -> bool:
    """¿La fuente devuelve ya una respuesta sintetizada (no solo snippets)?"""
    return (src or provider()) in ("perplexity", "tavily", "google")


# ── IS THE SEARCH LAYER ALIVE? (V2-176, 2026-08-20) ──────────────────────────────────────────────────────────
# When every backend in the chain fails, `search()` returns `results: []` with `source: "none"` — which is
# INDISTINGUISHABLE from «I searched fine and there is nothing». The only trace of the collapse was a
# `logger.warning`, so the brain composing the next turn could not tell the two apart and said the only thing it
# had: «sigo con ello».
#
# Measured on `cheapest-monitor`: twenty search events, no candidates, and ten turns of «te aviso en cuanto lo
# tenga» ending in «Hecho, te aviso al momento». The watchdog fired `stuck/nudge` while it happened. The search
# chain was down (quota exhausted plus a CAPTCHA) — so the outcome was never reachable, and the ONE thing that
# was reachable, saying so, was impossible: nothing carried the fact.
#
# Same remedy as the LLM side (`provider_chain.note_failure` + `health_state.record`): the layer records its own
# health, and the turn reads it. Classified into engine-native buckets — deliberately NOT by importing the test
# harness's needle list, which reads the same reality from the other end and must stay independent.
_FAILURE_MEMORY_S = 600.0
_last_failure: dict = {}

_FAIL_KINDS = (
    ("quota", ("limit exhausted", "quota", "rate limit", "429", "too many requests", "insufficient")),
    # The needles have to be the words the CHALLENGE PAGE actually uses, not the words we would use to
    # describe it. Measured 2026-08-27 against a live DuckDuckGo block: the page says «Unfortunately, bots use
    # DuckDuckGo too… Select all squares containing a duck» and the string "captcha" appears NOWHERE in it, so
    # a list built out of plausible names classified a hard block as a generic "error".
    ("captcha", ("captcha", "unusual traffic", "/sorry/", "are you a robot", "recaptcha", "access denied",
                 "made by a human", "squares containing", "bots use duckduckgo")),
    ("credential", ("api key", "unauthorized", "401", "403", "forbidden", "invalid key")),
    ("network", ("timeout", "timed out", "connection", "dns", "unreachable", "ssl")),
)


def _classify_failure(text: str) -> str:
    low = (text or "").lower()
    for kind, needles in _FAIL_KINDS:
        if any(n in low for n in needles):
            return kind
    return "error"


def note_failure(detail: str) -> None:
    """The whole chain came back with nothing → remember it, and light the operator's semaphore.

    «Estado visible, no silencioso»: a search layer that is down and shows green is indistinguishable from an
    agent that will not search, and the operator debugs the wrong thing.
    """
    global _last_failure
    kind = _classify_failure(detail)
    _last_failure = {"at": _time.time(), "kind": kind, "detail": (detail or "")[:200],
                     "n": int((_last_failure or {}).get("n") or 0) + 1}
    try:
        from voice import health_state
        health_state.record("search", kind, (detail or "")[:200] or "search chain down")
    except Exception:
        pass


def note_success() -> None:
    """A backend answered → the layer is alive again and the fact stops being told."""
    global _last_failure
    _last_failure = {}


def recent_failure(now: float | None = None) -> dict:
    """The chain's last collapse if it is still recent, else {}. Read by the turn state, never by the searcher."""
    f = _last_failure or {}
    if not f:
        return {}
    now = _time.time() if now is None else now
    if (now - float(f.get("at") or 0)) > _FAILURE_MEMORY_S:
        return {}
    return dict(f)


def search(query: str, k: int = _MAX_RESULTS) -> dict:
    """Busca y devuelve `{query, answer, results:[{title,snippet,url}], source, ai}`.

    `answer` = respuesta ya sintetizada si la fuente es de respuesta-IA (Perplexity/Tavily); si no, cadena vacía y
    la compone el cerebro desde `results`. `ai` = True si `answer` viene pre-sintetizado (el cerebro solo lo adapta
    a voz/idioma). BLOQUEANTE (red): llamar SIEMPRE con `asyncio.to_thread`. Fail-open (degrada por la cadena)."""
    q = (query or "").strip()
    if not q:
        return {"query": q, "answer": "", "results": [], "source": "none", "ai": False}
    _why: list[str] = []
    for src in _order():
        try:
            r = _BACKENDS[src](q, k)
            if r["results"] or r["answer"]:
                # respeta el flag `ai` que ponga el backend (google marca ai=True si trae AI Overview/featured);
                # el resto por defecto = solo los de respuesta-IA de pago.
                r["ai"] = bool(r.get("ai")) or src in ("perplexity", "tavily")
                _meter_search(src)
                note_success()
                return r
            _why.append(f"{src}: sin resultados")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"websearch backend '{src}' falló, siguiente: {e}")
            _why.append(f"{src}: {_brief(e, 120)}")
    # THE CHAIN COLLAPSED. Recorded, not just logged — see `note_failure`. An empty result on its own cannot tell
    # the brain whether the world has nothing or our searching is broken, and those two deserve opposite replies.
    detail = " · ".join(_why)
    note_failure(detail)
    # THE REASON TRAVELS WITH THE RESULT. `note_failure` lights the operator's semaphore, but the observability
    # row for this search carried only `n: 0` — no word anywhere about why — so anything reading the stream
    # afterwards (the use-case harness's `search_health`, the operator auditing a round) could not tell a hard
    # block from an empty world, and graded the agent for not finding what nobody let us look for.
    return {"query": q, "answer": "", "results": [], "source": "none", "ai": False,
            "failure": {"kind": _classify_failure(detail), "detail": detail[:200]}}


# Los de PAGO, por nombre de backend. `google` (nuestro Chromium) y `ddg` NO están y por eso no se
# cobran — la gratuidad es una propiedad del proveedor, no una tarifa de cero que alguien pueda
# equivocarse al mirar. Añadir un buscador de pago obliga a meterlo aquí Y a darle tarifa en
# `energy_meter._SEARCH_USD_PER_REQUEST`; el gate de cobertura de Energy falla si no.
_PAID_BACKENDS = frozenset({"perplexity", "tavily", "brave"})


def _meter_search(src: str) -> None:
    """A ENERGY (2026-08-13). Esta familia se factura POR PETICIÓN, no por tokens. Hoy la cadena cae
    casi siempre en Google/DDG (gratis) porque las keys de pago no se aprovisionan, así que en la
    práctica no cobra nada — pero sin esto, poner una key sería gasto invisible. Solo se cobra lo que
    RESPONDIÓ: un backend que revienta antes de contestar no se factura (si lo hiciera después de que
    el proveedor ya lo contara, se detectaría en la reconciliación)."""
    if src not in _PAID_BACKENDS:
        return
    from nucleo import energy_meter as _energy
    _energy.report_search_usage(provider=src)   # el contador no lanza: `@_never_raises` vive en el módulo


def _order() -> list[str]:
    """Cadena de proveedores a intentar: el elegido primero, luego degradación por calidad hasta el gratis.
    `google` (gratis, navegador) va por encima de `ddg` (último recurso sin key ni navegador)."""
    chain = [provider()]
    for fb in ("perplexity", "tavily", "brave", "google", "ddg"):
        if fb not in chain and _usable(fb):
            chain.append(fb)
    if "ddg" not in chain:
        chain.append("ddg")               # último recurso, sin key
    return chain


def _usable(src: str) -> bool:
    return bool({"perplexity": perplexity_key(), "tavily": tavily_key(), "brave": brave_key(),
                 "google": ("1" if _google_on() else ""), "ddg": "1"}.get(src, ""))


# ── Perplexity Sonar (respuesta-IA sintetizada + citaciones) ─────────────────────────────────────────────
def _perplexity(q: str, k: int) -> dict:
    import httpx
    if not perplexity_key():
        return {"query": q, "answer": "", "results": [], "source": "perplexity"}
    model = os.getenv("PERPLEXITY_MODEL", "sonar")
    headers = {"Authorization": f"Bearer {perplexity_key()}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [
        {"role": "system", "content": "Be precise and concise. Answer with the latest facts."},
        {"role": "user", "content": q}]}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    answer = _clean(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    cites = data.get("citations") or []
    results = [{"title": "", "snippet": "", "url": u} for u in cites[:k] if isinstance(u, str)]
    return {"query": q, "answer": answer, "results": results, "source": "perplexity"}


# ── Tavily (search API para agentes: answer + fuentes limpias) ────────────────────────────────────────────
def _tavily(q: str, k: int) -> dict:
    import httpx
    if not tavily_key():
        return {"query": q, "answer": "", "results": [], "source": "tavily"}
    payload = {"api_key": tavily_key(), "query": q, "search_depth": "advanced",
               "include_answer": True, "max_results": max(1, min(k, 10))}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        data = resp.json()
    results = [{"title": _clean(r.get("title") or ""), "snippet": _clean(r.get("content") or ""),
                "url": (r.get("url") or "").strip()} for r in (data.get("results") or [])[:k]]
    return {"query": q, "answer": _clean(data.get("answer") or ""), "results": results, "source": "tavily"}


# ── Brave Search API (snippets limpios, opcional con key) ─────────────────────────────────────────────────
def _brave(q: str, k: int) -> dict:
    import httpx
    if not brave_key():
        return {"query": q, "answer": "", "results": [], "source": "brave"}
    headers = {"X-Subscription-Token": brave_key(), "Accept": "application/json", "User-Agent": _UA}
    params = {"q": q, "count": max(1, min(k, 10))}
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
        resp = c.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    results = [{"title": _clean(it.get("title") or ""), "snippet": _clean(it.get("description") or ""),
                "url": (it.get("url") or "").strip()} for it in ((data.get("web") or {}).get("results") or [])[:k]]
    ib = data.get("infobox") or {}
    answer = _clean(ib.get("long_desc") or ib.get("description") or "") if isinstance(ib, dict) else ""
    return {"query": q, "answer": answer, "results": results, "source": "brave"}


# ── Google vía Chromium propio (GRATIS, AI Overview + snippets; V2-024) ───────────────────────────────────
def _google(q: str, k: int) -> dict:
    """Búsqueda en Google en el navegador headless persistente (`nucleo/browser_search`). BLOQUEANTE desde el hilo
    de `to_thread`: el puente `search_sync` agenda la corrutina en el loop del server. Lanza si el browser no está
    listo o Google bloquea → la cadena degrada a DDG (fail-open)."""
    if not _google_on():
        return {"query": q, "answer": "", "results": [], "source": "google"}
    from nucleo import browser_search
    return browser_search.search_sync(q, k)


# ── DuckDuckGo HTML (gratis, sin key, siempre disponible) ─────────────────────────────────────────────────
_SNIPPET_RE = _re.compile(r'result__snippet[^>]*>(.*?)</a>', _re.S)
_LINK_RE = _re.compile(r'result__a[^>]*href="(.*?)"[^>]*>(.*?)</a>', _re.S)



def _accept_language() -> str:
    """The header that tells a site which country it is serving. It was pinned to `es-ES` for everybody, and a
    header outranks the words of the query: measured 2026-08-27, a US search for hotels under $150 came back
    priced in euros. Follows the engine's own language, with Spanish as the fallback when it cannot be read —
    the behaviour of always, for the deployment that had it right."""
    try:
        from voice.engine.core import langs as _langs
        code = (_langs.current_code() or "es").lower()
    except Exception:  # noqa: BLE001 — a web search must never die because the language is unreadable
        code = "es"
    if code == "es":
        return "es-ES,es;q=0.9,en;q=0.8"
    return f"{code}-US,{code};q=0.9" if code == "en" else f"{code},{code};q=0.9,en;q=0.8"

_CHALLENGE = ("made by a human", "squares containing", "bots use duckduckgo", "captcha",
              "unusual traffic", "are you a robot")


def _challenge_reason(body: str) -> str:
    """Non-empty when the page we were served is a bot CHALLENGE rather than a result list.

    It exists because the block does not arrive as an error. Measured 2026-08-27: a blocked DuckDuckGo answers
    **HTTP 202** with a challenge page, and 202 is a success status — `raise_for_status()` waves it through,
    the link regex finds nothing, and the caller gets `results: []`. "We were blocked" and "the world has
    nothing" then look identical, which are opposite facts deserving opposite replies (the same reason
    `note_failure` exists at all). `browser_search._looks_blocked` already does this for Google; DDG, the last
    rung of the chain and the one that runs when everything else is missing, had nothing.
    """
    low = (body or "")[:4000].lower()
    hit = next((n for n in _CHALLENGE if n in low), "")
    return f"captcha: DuckDuckGo sirvió un desafío anti-bot («{hit}»)" if hit else ""


def _ddg(q: str, k: int) -> dict:
    import httpx
    answer = _ddg_instant(q)
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
        resp = c.post("https://html.duckduckgo.com/html/", data={"q": q},
                      headers={"User-Agent": _UA, "Accept-Language": _accept_language()})
        resp.raise_for_status()      # NOT enough on its own: a block comes back as 202, a success status
        body = resp.text
    blocked = _challenge_reason(body)
    if blocked:
        raise RuntimeError(blocked)      # so the chain's reason string SAYS it instead of "sin resultados"
    links = _LINK_RE.findall(body)
    snippets = _SNIPPET_RE.findall(body)
    results = []
    for i in range(min(len(snippets), k)):
        href, title = (links[i] if i < len(links) else ("", ""))
        results.append({"title": _clean(title), "snippet": _clean(snippets[i]), "url": _ddg_href(href)})
    return {"query": q, "answer": answer, "results": results, "source": "ddg"}


def _ddg_instant(q: str) -> str:
    import httpx
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
            resp = c.get("https://api.duckduckgo.com/",
                         params={"q": q, "format": "json", "no_html": "1", "skip_disambig": "1"},
                         headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.json()
        return _clean(data.get("AbstractText") or data.get("Answer") or "")
    except Exception:
        return ""


def _ddg_href(href: str) -> str:
    href = _html.unescape(href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        u = urlparse(href)
        if "duckduckgo.com" in (u.netloc or "") and u.path.startswith("/l/"):
            uddg = parse_qs(u.query).get("uddg", [""])[0]
            if uddg:
                return unquote(uddg)
    except Exception:
        pass
    return href


_BACKENDS = {"perplexity": _perplexity, "tavily": _tavily, "brave": _brave, "google": _google, "ddg": _ddg}


def _clean(s: str) -> str:
    s = _re.sub(r"<[^>]+>", "", s or "")
    s = _html.unescape(s)
    return _re.sub(r"\s+", " ", s).strip()


def format_results(res: dict, limit: int = _MAX_RESULTS) -> str:
    """Empaqueta la búsqueda como contexto para que el cerebro componga la respuesta (o la adapte a voz si ya
    viene sintetizada). Si `answer` viene de un proveedor de respuesta-IA, va destacado como respuesta principal."""
    parts: list[str] = []
    if res.get("answer"):
        label = "RESPUESTA (ya sintetizada por el buscador IA)" if res.get("ai") else "Respuesta directa del buscador"
        parts.append(f"{label}: {res['answer'][:1200]}")
    for i, r in enumerate(res.get("results", [])[:limit], 1):
        line = f"[{i}] {r.get('title', '')} — {r.get('snippet', '')}".strip(" —")
        if line and line != f"[{i}]":
            parts.append(line[:400])
    return "\n".join(parts)
