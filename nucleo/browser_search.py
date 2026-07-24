"""nucleo/browser_search.py — búsqueda GRATIS en Google vía un Chromium headless persistente y CALIENTE (V2-024).

Idea del operador: en vez de pagar Perplexity/Tavily, usar un Chromium propio para buscar en Google y aprovechar
su síntesis (AI Overview / featured snippet), parseando el resultado. Gratis "para siempre" — a cambio de fragilidad
(Google castiga el scraping: CAPTCHA / "tráfico inusual" intermitente, DOM que cambia). Por eso es una CAPA MÁS de la
cadena de `nucleo/websearch.py` (calidad primero), por ENCIMA de DuckDuckGo y con **fail-open a DDG** si Google
bloquea. Con key de Perplexity/Tavily, esas ganan (respuesta-IA de pago, sin mantenimiento).

Diseño:
  - **UN contexto Chromium persistente** (perfil propio en `memory/_data/search_browser/`, aislado del Chrome del
    operador y del navegador-widget) que vive en el loop del servidor y se **calienta en el arranque** (mientras el
    frontend pinta el loader) → la primera búsqueda real ya es rápida (~2-3s), sin arrancar el navegador en frío.
  - `search_google()` es async (corre en el loop del server, dueño del browser). `search_sync()` es el puente para
    `websearch` (que corre en un hilo vía `asyncio.to_thread`): agenda la corrutina en el loop del server con
    `run_coroutine_threadsafe`. Si el browser no está listo o Google bloquea → lanza → `websearch` cae a DDG.
  - Perfil persistente + consentimiento aceptado una vez → menos fricción y más probabilidad de AI Overview.
"""
from __future__ import annotations

import asyncio
import os
from urllib.parse import quote_plus

from loguru import logger

from . import workspace as _workspace

# `<workspace>/memory/_data/search_browser` — unset `ZAELAR_WORKSPACE` is byte-identical to the old
# `_HERE/../memory/_data/search_browser` (workspace.root() falls back to the engine repo root).
_PROFILE = os.path.join(str(_workspace.root()), "memory", "_data", "search_browser")
_TIMEOUT_MS = int(float(os.getenv("BROWSER_SEARCH_TIMEOUT", "12")) * 1000)
_HL = os.getenv("BROWSER_SEARCH_HL", "es")
_GL = os.getenv("BROWSER_SEARCH_GL", "es")

# estado del singleton (vive en el loop del server)
_pw = None            # el objeto async_playwright
_ctx = None           # BrowserContext persistente
_loop = None          # el loop del server (para el puente sync→async)
_start_lock: asyncio.Lock | None = None
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def set_loop(loop) -> None:
    """Captura el loop del servidor (llamado desde el lifespan, síncrono) para que `search_sync` pueda agendar."""
    global _loop
    _loop = loop


def enabled() -> bool:
    """La capa google está ON salvo que se apague por env (BROWSER_SEARCH=0)."""
    return os.getenv("BROWSER_SEARCH", "1") == "1"


async def ensure_started() -> bool:
    """Arranca (idempotente) el contexto Chromium persistente y lo calienta con google.com. Devuelve True si listo.
    Fire-and-forget desde el arranque; nunca lanza hacia el lifespan."""
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
            _ctx = await _pw.chromium.launch_persistent_context(
                _PROFILE,
                headless=os.getenv("BROWSER_SEARCH_HEADLESS", "1") == "1",
                user_agent=_UA,
                locale=f"{_HL}-{_GL.upper()}",
                viewport={"width": 1280, "height": 900},
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage"],
            )
            _ctx.set_default_timeout(_TIMEOUT_MS)
            # warm: abrir google una vez (monta red + acepta consentimiento y queda en el perfil)
            try:
                page = await _ctx.new_page()
                await page.goto(f"https://www.google.com/?hl={_HL}", wait_until="domcontentloaded",
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
    """Acepta/rechaza el muro de consentimiento de Google (una vez; queda en el perfil). Best-effort, multi-idioma."""
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


# JS de extracción — CONSERVADOR a propósito: solo damos `answer` (que el cerebro adaptará casi tal cual) cuando es
# FIABLE — el widget del TIEMPO de Google (IDs `#wob_*`, estables desde hace años) o un fragmento destacado real. El
# knowledge-panel/AI-overview genérico se DESCARTÓ: grababa texto equivocado (la descripción turística de "Soria" en
# vez de la temperatura, el carrusel de resultados en F1) y una respuesta MAL es peor que ninguna. Para el resto, la
# fuerza está en los SNIPPETS orgánicos (Aemet/ESPN/Marca…) — de mucha más calidad que DDG — que sintetiza el cerebro.
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
    """Busca en Google en el Chromium persistente y devuelve el contrato de websearch. Lanza si no hay browser o si
    Google bloquea (→ websearch cae a DDG)."""
    if not await ensure_started():
        raise RuntimeError("browser_search no disponible")
    page = await _ctx.new_page()
    try:
        url = (f"https://www.google.com/search?q={quote_plus(query)}"
               f"&hl={_HL}&gl={_GL}&num=10&pws=0")
        await page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
        await _dismiss_consent(page)
        if await _looks_blocked(page):
            raise RuntimeError("google: bloqueado (captcha/tráfico inusual)")
        # deja renderizar el featured snippet / AI overview un momento
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
                "ai": bool(answer)}   # answer de Google (AI Overview/featured) → el cerebro solo lo adapta a voz
    finally:
        try:
            await page.close()
        except Exception:
            pass


def search_sync(query: str, k: int = 5) -> dict:
    """Puente para `websearch` (corre en un hilo): agenda `search_google` en el loop del server. Lanza si el loop no
    está enlazado (arranque aún no hecho) o si la búsqueda falla → websearch degrada a DDG."""
    if not enabled():
        raise RuntimeError("browser_search off")
    if _loop is None or not _loop.is_running():
        raise RuntimeError("browser_search: loop del server no enlazado todavía")
    fut = asyncio.run_coroutine_threadsafe(search_google(query, k), _loop)
    return fut.result(timeout=(_TIMEOUT_MS / 1000) + 6)


async def stop() -> None:
    """Cierra el contexto y playwright (en el shutdown del lifespan)."""
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
