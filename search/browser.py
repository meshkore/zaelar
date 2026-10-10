"""search/browser.py — FREE Google search via a persistent, WARM headless Chromium (V2-024; moved from
`nucleo/browser_search.py` by V2-782, which keeps that name as an alias).

Operator's idea: instead of paying for Perplexity/Tavily, use a private Chromium to search Google and leverage
its synthesis (AI Overview / featured snippet), parsing the result. Free "forever" — in exchange for fragility
(Google punishes scraping: intermittent CAPTCHA / "unusual traffic", a DOM that changes). That is why it is ONE
MORE LAYER of the `search/web.py` chain (quality first), ABOVE DuckDuckGo and **failing open to DDG** when Google
blocks. With a Perplexity/Tavily/Gemini/Z.ai key, those win (paid, maintenance-free).

Design:
  - **ONE persistent Chromium context** (its own profile in `memory/_data/search_browser/`, isolated from the
    operator's Chrome and from the browser widget) that lives on the server loop and is **warmed at boot** (while
    the frontend renders the loader) → the first real search is already fast (~2-3s), without a cold browser start.
  - `search_google()` is async (runs on the server loop, which owns the browser). `search_sync()` is the bridge for
    `web.search` (which runs in a thread via `asyncio.to_thread`): it schedules the coroutine on the server loop with
    `run_coroutine_threadsafe`. If the browser is not ready or Google blocks → raises → the chain falls to DDG.
  - Persistent profile + consent accepted once → less friction and a better chance of an AI Overview.
"""
from __future__ import annotations

import asyncio
import os
from urllib.parse import quote_plus

from loguru import logger

from nucleo import workspace as _workspace

# `<workspace>/memory/_data/search_browser` — unset `ZAELAR_WORKSPACE` is byte-identical to the old
# `_HERE/../memory/_data/search_browser` (workspace.root() falls back to the engine repo root).
_PROFILE = os.path.join(str(_workspace.root()), "memory", "_data", "search_browser")
_TIMEOUT_MS = int(float(os.getenv("BROWSER_SEARCH_TIMEOUT", "12")) * 1000)
# WHERE THE SEARCH THINKS IT IS. These were pinned to "es" and only an env var could move them, so every
# search — from any account, in any language — asked Google as if it were being made from Spain. Measured
# 2026-08-27 on the first US round of `find-best-hotel-city__us`: twelve real New Orleans hotels came back
# priced in EUROS (€271) against a $150 budget, because the site reads the browser's locale, not the words in
# the query. The candidates were right and unusable, which reads as a filtering bug and is a geography one.
#
# So they FOLLOW THE ENGINE'S LANGUAGE, resolved through the same map the site catalogue already uses
# (`site_catalog.resolve_locale`: es→es, anything else→us) so a Spanish engine keeps searching from Spain and
# an English one searches from the US. Read per call rather than frozen at import: the operator can change
# language while the engine runs, and a browser stuck in the old country would be the same bug again.
# The env vars still win — they are the escape hatch for an engine whose language and country differ.
_HL_ENV = os.getenv("BROWSER_SEARCH_HL", "")
_GL_ENV = os.getenv("BROWSER_SEARCH_GL", "")


def _where() -> tuple[str, str]:
    """`(hl, gl)` — interface language and country for the search, from the engine's own language."""
    if _HL_ENV and _GL_ENV:
        return _HL_ENV, _GL_ENV
    try:
        from i18n import langs as _langs
        code = (_langs.current_code() or "es").lower()
    except Exception:  # noqa: BLE001 — a search must never die because the language is unreadable
        code = "es"
    hl = _HL_ENV or code
    gl = _GL_ENV or ("es" if code == "es" else "us")
    return hl, gl

# singleton state (lives on the server loop)
_pw = None            # the async_playwright object
_ctx = None           # persistent BrowserContext
_loop = None          # the server loop (for the sync→async bridge)
_start_lock: asyncio.Lock | None = None
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def set_loop(loop) -> None:
    """Captures the server loop (called from the lifespan, synchronously) so `search_sync` can schedule on it."""
    global _loop
    _loop = loop


def enabled() -> bool:
    """The Google layer is ON unless disabled through env (BROWSER_SEARCH=0)."""
    return os.getenv("BROWSER_SEARCH", "1") == "1"


async def ensure_started() -> bool:
    """Starts (idempotently) the persistent Chromium context and warms it with google.com. True when ready.
    Fire-and-forget from boot; never raises into the lifespan."""
    global _pw, _ctx, _start_lock
    if not enabled():
        return False
    if _ctx is not None:
        return True
    if _start_lock is None:
        _start_lock = asyncio.Lock()
    async with _start_lock:
        if _ctx is not None:
            return True
        try:
            from playwright.async_api import async_playwright
            os.makedirs(_PROFILE, exist_ok=True)
            _pw = await async_playwright().start()
            _hl, _gl = _where()
            _ctx = await _pw.chromium.launch_persistent_context(
                _PROFILE,
                headless=os.getenv("BROWSER_SEARCH_HEADLESS", "1") == "1",
                user_agent=_UA,
                locale=f"{_hl}-{_gl.upper()}",
                viewport={"width": 1280, "height": 900},
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage"],
            )
            _ctx.set_default_timeout(_TIMEOUT_MS)
            # warm: open google once (brings the network up, accepts consent, which stays in the profile)
            try:
                page = await _ctx.new_page()
                await page.goto(f"https://www.google.com/?hl={_hl}", wait_until="domcontentloaded",
                                timeout=_TIMEOUT_MS)
                await _dismiss_consent(page)
                await page.close()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"browser_search warm-visit falló (seguimos): {e}")
            logger.info("browser_search: Chromium de búsqueda CALIENTE (perfil persistente)")
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"browser_search no pudo arrancar (búsqueda caerá a DDG): {e}")
            _ctx = None
            return False


async def _dismiss_consent(page) -> None:
    """Accepts/rejects Google's consent wall (once; it stays in the profile). Best-effort, multilingual."""
    labels = ["Aceptar todo", "Rechazar todo", "Accept all", "Reject all", "Acepto", "I agree",
              "Aceptar", "Estoy de acuerdo"]
    for lab in labels:
        try:
            btn = page.get_by_role("button", name=lab)
            if await btn.count() > 0:
                await btn.first.click(timeout=2500)
                await page.wait_for_timeout(400)
                return
        except Exception:
            continue


async def _looks_blocked(page) -> bool:
    try:
        body = (await page.inner_text("body"))[:2000].lower()
    except Exception:
        return False
    needles = ["unusual traffic", "tráfico inusual", "not a robot", "no soy un robot", "recaptcha",
               "detected unusual", "systems have detected"]
    return any(n in body for n in needles)


# Extraction JS — deliberately CONSERVATIVE: `answer` (which the brain adapts almost verbatim) is only given when it
# is RELIABLE — Google's WEATHER widget (`#wob_*` ids, stable for years) or a real featured snippet. The generic
# knowledge panel / AI overview was DISCARDED: it recorded the wrong text (the tourist description of "Soria" instead
# of the temperature, the results carousel in F1) and a WRONG answer is worse than none. For everything else the
# strength is in the organic SNIPPETS (Aemet/ESPN/Marca…) — far better than DDG's — which the brain synthesises.
_EXTRACT_JS = r"""
() => {
  const clean = s => (s||'').replace(/\s+/g,' ').trim();
  const txt = el => el ? clean(el.innerText) : '';
  let answer = '';
  // ---- 1) WIDGET DEL TIEMPO (respuesta exacta, IDs estables) ----
  const wt = document.querySelector('#wob_tm');
  if (wt) {
    const loc = txt(document.querySelector('#wob_loc'));
    const cond = txt(document.querySelector('#wob_dc'));
    const unit = (document.querySelector('.wob_t[style*="inline"]') ? '' : '');
    answer = clean(`${loc ? loc + ': ' : ''}${txt(wt)}°C${cond ? ', ' + cond : ''}`);
  }
  // ---- 2) RESULTADO DEPORTIVO (tarjeta de partido: "Real Madrid 4 - 2 Athletic, Finalizado") ----
  if (!answer) {
    const sp = document.querySelector('.imso-hov');
    const t = txt(sp);
    if (t && t.length >= 8 && t.length <= 240 && /\d/.test(t)) answer = t;
  }
  // ---- 3) FRAGMENTO DESTACADO real (answer box con data-attrid de respuesta) ----
  if (!answer) {
    const fs = document.querySelector('[data-tts="answers"], .hgKELc, .ILfuVd .hgKELc, .LGOjhe[aria-level]');
    const t = txt(fs);
    if (t && t.length >= 8 && t.length <= 320) answer = t;
  }
  // ---- 4) organic results: <a> que contiene un <h3> (estructura estable pese a las clases aleatorias) ----
  const out = []; const seen = new Set();
  for (const h3 of document.querySelectorAll('a h3')) {
    const a = h3.closest('a');
    if (!a || !a.href) continue;
    if (/^https?:\/\/(www\.)?google\./.test(a.href)) continue;
    if (seen.has(a.href)) continue; seen.add(a.href);
    let blk = a;
    for (let i=0;i<5 && blk.parentElement;i++){ blk = blk.parentElement; if ((blk.innerText||'').length > (h3.innerText||'').length + 40) break; }
    const snip = clean((blk.innerText||'').replace(h3.innerText||'','')).slice(0,320);
    out.push({title: clean(h3.innerText), url: a.href, snippet: snip});
    if (out.length >= 8) break;
  }
  return {answer: answer.slice(0,600), results: out};
}
"""


async def search_google(query: str, k: int = 5) -> dict:
    """Searches Google in the persistent Chromium and returns the chain's contract. Raises when there is no browser or
    Google blocks (→ the chain falls to DDG)."""
    if not await ensure_started():
        raise RuntimeError("browser_search no disponible")
    page = await _ctx.new_page()
    try:
        url = (f"https://www.google.com/search?q={quote_plus(query)}"
               f"&hl={_where()[0]}&gl={_where()[1]}&num=10&pws=0")
        await page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
        await _dismiss_consent(page)
        if await _looks_blocked(page):
            raise RuntimeError("google: bloqueado (captcha/tráfico inusual)")
        # let the featured snippet / AI overview render for a moment
        try:
            await page.wait_for_selector("a h3", timeout=6000)
        except Exception:
            pass
        data = await page.evaluate(_EXTRACT_JS)
        results = [{"title": r.get("title", ""), "snippet": r.get("snippet", ""), "url": r.get("url", "")}
                   for r in (data.get("results") or [])[:k]]
        answer = (data.get("answer") or "").strip()
        if not results and not answer:
            raise RuntimeError("google: sin resultados parseables")
        return {"query": query, "answer": answer, "results": results, "source": "google",
                "ai": bool(answer)}   # Google's answer (AI Overview/featured) → the brain only adapts it to speech
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def search_images(query: str, k: int = 12) -> dict:
    """PICTURES for a query, through the same warm Chromium. `{query, items, source, blocked}` (V2-457).

    This rides the existing browser instead of starting one for images because the warm profile is the whole
    reason the fast path is fast: it has already taken Google's consent wall and it is already running, so a
    picture search costs a page load (~3s) instead of a browser boot (~2.3s more, measured by the prewarm).

    Fail-soft, never raising: a picture request that finds nothing still has to come back and say so. Google
    blocking is reported as `blocked` rather than swallowed, because the caller's answer differs — a blocked
    search should try Bing, an empty one should not.
    """
    if not await ensure_started():
        return {"query": query, "items": [], "source": "", "blocked": False, "error": "browser no disponible"}
    from search import images as _imgs
    hl, gl = _where()
    page = await _ctx.new_page()
    try:
        # `udm=2` is the images vertical. `pws=0` turns off personalisation so two operators asking the same
        # thing see the same pictures — a search whose results depend on the engine's browsing history is not
        # reproducible, and this suite's whole job is measuring it.
        url = (f"https://www.google.com/search?q={quote_plus(query)}&udm=2"
               f"&hl={hl}&gl={gl}&pws=0")
        await page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
        await _dismiss_consent(page)
        if await _looks_blocked(page):
            return {"query": query, "items": [], "source": "google", "blocked": True}
        # The payload is in inline scripts, not the DOM, so there is no element to wait for — the tiles render
        # from it afterwards. A short settle beats a selector wait that would succeed on a skeleton page.
        await page.wait_for_timeout(1200)
        blob = await page.evaluate(
            "() => Array.from(document.querySelectorAll('script')).map(s => s.textContent || '').join('\\n')")
        items = _imgs.parse_google_images(blob or "", k)
        return {"query": query, "items": items, "source": "google", "blocked": False}
    except Exception as e:  # noqa: BLE001
        return {"query": query, "items": [], "source": "google", "blocked": False, "error": str(e)[:200]}
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def search_images_yandex(query: str, k: int = 12) -> dict:
    """The SECOND index of the chain, added because Google is not always available (V2-466).

    Measured 2026-08-28 from this machine, same query on all of them: Google answered a captcha, Ecosia too
    (it proxies the big ones), DuckDuckGo/Brave/Startpage/Qwant only render their gallery after interaction,
    and Yandex returned 30 usable tiles with the right car. Bing answers too and stays LAST on purpose: asked
    for a Ferrari Amalfi it returned an SF90, an F8 and two F80s — right brand, wrong car, nine times out of
    ten.

    Its known cost: the TITLES come back in the index's own language (Russian for a Spanish query). The
    picture is right and the caption may not be readable, which is why `source` travels with every result.

    The tiles are read from the DOM (Yandex has no payload in a script like Google's), and the brittle half —
    the full-size URL inside the tile link's `img_url` — is parsed by a PURE function next door, so it can be
    tested without a network."""
    if not await ensure_started():
        return {"query": query, "items": [], "source": "", "blocked": False, "error": "browser no disponible"}
    from search import images as _imgs
    page = await _ctx.new_page()
    try:
        await page.goto(f"https://yandex.com/images/search?text={quote_plus(query)}",
                        wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
        await _dismiss_consent(page)
        if await _looks_blocked(page):
            return {"query": query, "items": [], "source": "yandex", "blocked": True}
        await page.wait_for_timeout(2500)      # the grid is painted by JS; there is no stable selector to wait for
        rows = await page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('img').forEach(i => {
            const s = i.currentSrc || i.src || '';
            const w = i.naturalWidth || i.width, h = i.naturalHeight || i.height;
            if (!s.startsWith('http') || w < 100) return;
            const a = i.closest('a');
            if (!a || !a.href) return;
            out.push({href: a.href, alt: i.alt || '', thumb: s, w: w, h: h});
          });
          return out;
        }""")
        return {"query": query, "items": _imgs.parse_yandex_rows(rows or [], k),
                "source": "yandex", "blocked": False}
    except Exception as e:  # noqa: BLE001
        return {"query": query, "items": [], "source": "yandex", "blocked": False, "error": str(e)[:200]}
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def search_images_bing(query: str, k: int = 12) -> dict:
    """The fallback index, used only when Google is blocked — and labelled, because it is measurably worse.

    Asked for a Ferrari Amalfi on 2026-08-28 it returned an SF90, an F8 and two F80s: right brand, wrong car,
    nine times out of ten. It is here so a captcha degrades the answer instead of removing it, and `source`
    travels with the result so whoever reads the run can tell which index answered.
    """
    if not await ensure_started():
        return {"query": query, "items": [], "source": "", "blocked": False, "error": "browser no disponible"}
    from search import images as _imgs
    page = await _ctx.new_page()
    try:
        await page.goto(f"https://www.bing.com/images/search?q={quote_plus(query)}",
                        wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
        try:
            await page.wait_for_selector("a.iusc", timeout=6000)
        except Exception:
            pass
        html = await page.content()
        return {"query": query, "items": _imgs.parse_bing_images(html or "", k),
                "source": "bing", "blocked": False}
    except Exception as e:  # noqa: BLE001
        return {"query": query, "items": [], "source": "bing", "blocked": False, "error": str(e)[:200]}
    finally:
        try:
            await page.close()
        except Exception:
            pass


#: The image indexes, in the order they are tried. Ordered by MEASURED quality on 2026-08-28, not by
#: reputation: Google is the best answer when it answers (cdn.ferrari.com originals, 3128x2333 masters);
#: Yandex is the best of the rest that works headless without interaction; Bing answers reliably but got the
#: WRONG CAR nine times out of ten for the query that started this, so it is the last resort, never the
#: default. Adding one is adding a row here plus its `search_images_*` leg — the chain itself does not change.
_IMAGE_ENGINES = ("google", "yandex", "bing")


#: The last good answer of the FIRST index, per query — served when that index is blocked. Demo pass 36
#: (2026-09-29, B1): Google answered a captcha for a few minutes (workers and the pass share one profile), the
#: chain fell to Yandex, and «the wallpaper cosmic eye in the sky by tyler young» came back as six Pinterest
#: nebulas, none of them his; minutes later Google answered it again, first tile the right one. A captcha is
#: about our traffic, not about the pictures: what Google answered for this query an hour ago is still the
#: better answer, and serving it is one request fewer against the index that just blocked us.
_IMAGE_CACHE = os.path.join(str(_workspace.root()), "memory", "_data", "image_answers.json")
_IMAGE_CACHE_TTL_S = 7 * 86400
_IMAGE_CACHE_MAX = 300


def _query_key(query: str) -> str:
    """Word order, case and punctuation do not change a picture search — the model words the same request a
    little differently every time («… by Tyler Young, Orion Nebula wallpaper» / «… Tyler Young Orion Nebula»)."""
    import re as _re
    return " ".join(sorted(set(w for w in _re.findall(r"\w+", (query or "").lower()) if len(w) > 2)))


def _cache_load() -> dict:
    import json as _json
    try:
        with open(_IMAGE_CACHE, encoding="utf-8") as f:
            d = _json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def remember_answer(query: str, res: dict) -> None:
    import json as _json
    import time as _t
    key = _query_key(query)
    if not key or not (res or {}).get("items"):
        return
    d = _cache_load()
    d[key] = {"ts": _t.time(), "source": res.get("source") or "", "items": list(res["items"])}
    if len(d) > _IMAGE_CACHE_MAX:
        for old in sorted(d, key=lambda k: d[k].get("ts", 0))[: len(d) - _IMAGE_CACHE_MAX]:
            d.pop(old, None)
    try:
        os.makedirs(os.path.dirname(_IMAGE_CACHE), exist_ok=True)
        tmp = _IMAGE_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, _IMAGE_CACHE)
    except Exception:  # noqa: BLE001
        pass


def remembered_answer(query: str, k: int = 12) -> dict | None:
    import time as _t
    hit = _cache_load().get(_query_key(query))
    if not isinstance(hit, dict) or _t.time() - float(hit.get("ts") or 0) > _IMAGE_CACHE_TTL_S:
        return None
    items = list(hit.get("items") or [])[:k]
    if not items:
        return None
    return {"query": query, "items": items, "source": hit.get("source") or "", "blocked": False,
            "remembered_s": round(_t.time() - float(hit.get("ts") or 0))}


async def images(query: str, k: int = 12) -> dict:
    """Pictures for a query, trying the indexes in order until one answers. One entry point for both channels.

    A CHAIN and not a fallback pair (V2-466, operator's request): «no podemos confiar todo el rato en Google».
    Google's captcha was blocking whole afternoons and every round silently landed on Bing, which is the
    weakest index — the wrong-car photos then read as a product defect. Now each engine is tried in turn, and
    what the answer carries is not just WHICH one served it but WHY the previous ones did not:
    `degraded_from` (who was tried first) and `degraded_because` (`blocked` = captcha, wait; `empty` = no
    results, rephrase — two different actions, so they are never collapsed into one flag).

    An engine that raises or comes back empty costs one page load and the chain moves on; only if ALL of them
    fail does the caller get an empty answer, and then it is a fact about the world, not about one index.
    """
    _legs = {"google": search_images, "yandex": search_images_yandex, "bing": search_images_bing}
    primero: dict = {}
    intentados: list[str] = []
    for name in _IMAGE_ENGINES:
        leg = _legs.get(name)
        if leg is None:
            continue
        res = await leg(query, k)
        res = res if isinstance(res, dict) else {}
        if not primero:
            primero = res
            if res.get("items") and len(res["items"]) >= min(k, 3):
                remember_answer(query, res)
            elif res.get("blocked"):
                kept = remembered_answer(query, k)
                if kept:
                    kept.update({"degraded_from": name, "degraded_because": "blocked", "tried": [name],
                                 "blocked": True})
                    return kept
        if res.get("items"):
            if intentados:
                res["degraded_from"] = intentados[0]
                res["degraded_because"] = "blocked" if primero.get("blocked") else "empty"
                res["tried"] = list(intentados)
                if primero.get("blocked"):
                    res["blocked"] = True
            return res
        intentados.append(name)
    # Nobody answered: return the FIRST result (its error/block is what explains the turn), saying how many
    # were queried — “there are no photos of that” and “all three indexes are down” call for different responses.
    primero = dict(primero or {"query": query, "items": [], "source": "", "blocked": False})
    primero["tried"] = list(intentados)
    return primero


def search_sync(query: str, k: int = 5) -> dict:
    """Bridge for `web.search` (which runs in a thread): schedules `search_google` on the server loop. Raises if the
    loop is not linked (startup has not happened yet) or if the search fails → the chain falls back to DDG."""
    if not enabled():
        raise RuntimeError("browser_search off")
    if _loop is None or not _loop.is_running():
        raise RuntimeError("browser_search: loop del server no enlazado todavía")
    fut = asyncio.run_coroutine_threadsafe(search_google(query, k), _loop)
    return fut.result(timeout=(_TIMEOUT_MS / 1000) + 6)


def images_sync(query: str, k: int = 12) -> dict:
    """The image chain from a THREAD (the service's `find()` runs blocking): schedules `images()` on the server
    loop. Raises when the loop is not linked — a standalone process has no warm Chromium, and says so."""
    if not enabled():
        raise RuntimeError("browser_search off")
    if _loop is None or not _loop.is_running():
        raise RuntimeError("browser_search: loop del server no enlazado todavía")
    fut = asyncio.run_coroutine_threadsafe(images(query, k), _loop)
    return fut.result(timeout=3 * (_TIMEOUT_MS / 1000) + 10)


async def stop() -> None:
    """Closes the context and playwright (on the lifespan shutdown)."""
    global _pw, _ctx
    try:
        if _ctx is not None:
            await _ctx.close()
    except Exception:
        pass
    try:
        if _pw is not None:
            await _pw.stop()
    except Exception:
        pass
    _ctx = None
    _pw = None
