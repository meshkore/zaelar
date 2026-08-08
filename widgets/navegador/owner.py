#
# owner.py — el BACKEND vivo del widget "navegador" (kind:"backed", INI-016). Es el ÚNICO escritor de
# widgets/_data/navegador/ (contrato de widget-app: zaelar-modules.md §Widget-apps). El supervisor
# (widgets/supervisor.py) lo arranca en el loop del server y le pasa las órdenes del buzón por handle().
#
# Por qué un backend y no un iframe: casi ninguna web (Google, Wallapop, la RAE, tiendas…) se deja incrustar en
# un <iframe> (mandan X-Frame-Options/CSP frame-ancestors). Así que el navegador REAL vive aquí (Chromium
# headless por Playwright): navega la página de verdad en el servidor, la fotografía y el widget muestra esa
# captura. Los clics/scroll/tecleo del operador se mapean de vuelta a coordenadas de la página → Chromium →
# nueva captura. Como el backend conduce la página por código, la VOZ y la AUTOMATIZACIÓN se enchufan encima
# más adelante (ese es el objetivo: "abre Wallapop y búscame una moto <5000€ de 2020 para arriba").
#
# YouTube es la EXCEPCIÓN: una captura estática no reproduce vídeo/audio → se resuelve el id del vídeo y el
# widget monta el reproductor embed real (youtube-nocookie) en cliente. Todo lo demás va por captura.
#
# Arranque PEREZOSO: start() es barato (no lanza Chromium); el navegador se levanta en la primera orden, de modo
# que un navegador que nunca se abre no cuesta un proceso Chromium. Resiliente: un fallo de UNA página (URL mala,
# timeout) escribe un error en el estado y NO tira el backend; el navegador se auto-relanza si Chromium muere.
#
import asyncio
import os
import random
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote_plus

from loguru import logger

from .. import store

WID = "navegador"
VIEWPORT = {"width": 1280, "height": 800}
HOME = {"mode": "blank", "url": "", "title": "Nuevo navegador"}
_NAV_TIMEOUT = 20_000   # ms — tope de goto; una web lenta no debe colgar el buzón

# Selectores de banners de cookies/consentimiento para auto-dismiss tras navegar (mejor esfuerzo).
# Cualquier selector que falle es un no-op rápido. Ordenados de más específico a más genérico.
_COOKIE_SELECTORS = [
    # OneTrust (el sistema de consentimiento más común en Europa)
    "#onetrust-accept-btn-handler",
    "#onetrust-reject-all-handler",
    "#onetrust-group-btn #accept-recommended-btn-handler",
    # Didomi
    ".didomi-components-button--accept",
    "#didomi-notice-agree-button",
    # Botones por texto — variantes en español que cubren Wallapop, El País, etc.
    "button:has-text(\"Aceptar y continuar\")",
    "button:has-text(\"Aceptar todas\")",
    "button:has-text(\"Aceptar cookies\")",
    "button:has-text(\"Aceptar\")",
    "button:has-text(\"Acepto\")",
    "button:has-text(\"Permitir\")",
    "button:has-text(\"Permitir cookies\")",
    "button:has-text(\"Permitir todas\")",
    "button:has-text(\"Continuar\")",
    "button:has-text(\"Cerrar\")",
    # Enlaces que actúan como botón de aceptar
    "a:has-text(\"Aceptar\")",
    "a:has-text(\"Acepto\")",
    # Selectores de clase/id genéricos con 'cookie' o 'consent'
    "[class*=\"cookie\"] button",
    "[class*=\"consent\"] button",
    "[id*=\"cookie\"] button",
    "[data-testid*=\"cookie\"] button",
    # Selector específico Wallapop: su banner personalizado (no OneTrust)
    "button:has-text(\"Configurar\")",
    "[class*=\"CookieConsent\"] button",
    "[class*=\"cookie-consent\"] button",
    "[class*=\"cookieBanner\"] button",
    "[class*=\"consent-modal\"] button",
    # Cualquier botón que esté DENTRO de un banner/dialog con texto de cookies
    "[class*=\"cookie-banner\"] button",
    "[class*=\"cookies-banner\"] button",
    "[role=\"dialog\"] button:has-text(\"Aceptar\")",
    "[role=\"dialog\"] button:has-text(\"Continuar\")",
    "[aria-label*=\"cookie\" i] button",
    # Wallapop: su capa modal con botones específicos
    "div[class*=\"modal\"] button:has-text(\"Aceptar\")",
    "div[class*=\"modal\"] button:has-text(\"Continuar\")",
    # Wallapop banner de app/store
    "button[aria-label=\"Cerrar\"]",
]

# Motor de búsqueda: Google CAPTCHEA a Chromium headless (/sorry/index) y DuckDuckGo lo bloquea (418) → una
# búsqueda saldría rota justo cuando los testers más la usan. Bing renderiza una página de resultados NORMAL de
# forma fiable headless. Google sigue accesible con `open google.com`. Configurable por env por si cambia.
_SEARCH_URL = os.environ.get("NAVEGADOR_SEARCH", "https://www.bing.com/search?q={q}")

# Estado vivo del backend (un solo Chromium compartido). El buzón serializa las órdenes → sin concurrencia aquí.
_pw = None
_browser = None
_context = None
_page = None
_hist: list[str] = []   # historial propio para los flags atrás/adelante (Chromium mueve; nosotros derivamos)
_idx = -1
_rev = 0
_refs: dict = {}        # ref numérica → ElementHandle del ÚLTIMO snapshot (el automatizador resuelve refs aquí)
_mouse = {"x": 0.0, "y": 0.0}   # posición simulada del ratón, para mover con trayectoria humana entre puntos
_automating = False             # True mientras corre una tarea del automatizador → pinta el cursor en la captura


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> dict:
    return store.load(WID, {**HOME, "rev": 0, "loading": False, "error": "",
                            "can_back": False, "can_forward": False, "youtube_id": "", "youtube_title": ""})


def _write(**changes) -> None:
    """El ÚNICO punto de escritura del estado → store.save emite el refresco SSE de la tarjeta abierta."""
    db = _read()
    db.update(changes)
    db["updated"] = _now()
    db["can_back"] = _idx > 0
    db["can_forward"] = 0 <= _idx < len(_hist) - 1
    store.save(WID, db)


def _emit(label: str, text: str = "", **extra) -> None:
    try:
        from voice.observer import emit
        emit("navegador", label, text=text, extra={"id": WID, **extra})
    except Exception:
        pass


# ── utilidades de página ─────────────────────────────────────────────────────────────────────────────────────
# Botones de ACEPTAR de los CMP más comunes (id/clase estables). consentmanager.net (lo usa Wallapop) pinta un
# <a class="cmpboxbtnyes">Aceptar todo</a>; OneTrust/Didomi tienen sus ids. Se ESPERA a que el CMP los inyecte
# (llegan por JS DESPUÉS de domcontentloaded — por eso el intento inmediato no encontraba nada y el muro se quedaba).
_CMP_ACCEPT = (".cmpboxbtnyes", "#onetrust-accept-btn-handler", "#didomi-notice-agree-button",
               ".didomi-components-button--accept")


async def _dismiss_overlays(page) -> None:
    """Acepta el banner de cookies/consentimiento que TAPA la web. Los CMP inyectan el banner por JS tras cargar →
    esperamos a que aparezca el botón de aceptar (bounded) y lo pulsamos; si no, un barrido rápido por texto en
    todos los frames. Best-effort: nunca lanza, no-op si no hay banner (paga el timeout una vez por navegación)."""
    # 1) CMP conocido: wait_for_selector devuelve EN CUANTO aparece (o corta al timeout si la web no tiene banner).
    try:
        combined = ", ".join(_CMP_ACCEPT)
        btn = await page.wait_for_selector(combined, timeout=2500, state="visible")
        if btn:
            await btn.click(timeout=2000)
            _emit("dismiss_overlay", "cmp-accept")
            # ESPERA a que el banner se CIERRE del todo antes de devolver (si no, la captura sale con el muro aún
            # puesto — el cierre de consentmanager tarda ~1-2s, más que el sleep fijo anterior de 0.4s).
            try:
                await page.wait_for_selector(combined, state="hidden", timeout=2500)
            except Exception:
                await asyncio.sleep(1.0)
            return
    except Exception:
        pass
    # 2) Fallback por texto/selectores genéricos, en TODOS los frames (algunos CMP viven en un iframe), sin esperas.
    for fr in page.frames:
        for sel in _COOKIE_SELECTORS:
            try:
                btn = await fr.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=2000)
                    await asyncio.sleep(0.3)
                    _emit("dismiss_overlay", sel)
                    return
            except Exception:
                continue


# ── ciclo de vida ────────────────────────────────────────────────────────────────────────────────────────────
async def start() -> None:
    """Barato a propósito: no lanza Chromium (arranque perezoso en el primer handle). Deja el estado en 'listo'."""
    _write(loading=False, error="")
    _emit("ready", "navegador listo (Chromium se lanza al primer uso)")
    # RECUPERACIÓN tras reinicio: las tareas viven en RAM y mueren con el proceso, pero un login A MEDIAS deja una
    # miga DURABLE en memoria → al arrancar se lo recordamos al operador una vez (no podemos reanudarlo solos porque
    # la tarea ya no existe; él decide si lo retoma). Best-effort: nunca rompe el arranque del widget.
    try:
        from . import auth_memory
        pend = auth_memory.read_auth_pending()
        if pend and pend.get("sitio"):
            from voice import proactive
            await proactive.notify("navegador", f"Antes dejaste a medias el inicio de sesión en "
                                   f"{pend['sitio']}. Si quieres, lo retomamos.", kind="notify")
            auth_memory.clear_auth_pending()          # ya avisado → no repetir el recordatorio en cada arranque
    except Exception:
        pass


async def stop() -> None:
    global _pw, _browser, _context, _page
    for closer in (lambda: _context and _context.close(),
                   lambda: _browser and _browser.close(),
                   lambda: _pw and _pw.stop()):
        try:
            r = closer()
            if r is not None:
                await r
        except Exception:
            pass
    _pw = _browser = _context = _page = None
    _emit("stopped")


async def _close_browser() -> None:
    """Cierra la VENTANA del navegador a petición del operador ("cierra el navegador"), SIN borrar el perfil →
    cookies/sesión se conservan y al volver a navegar se relanza con la sesión intacta. Deja el escritorio limpio."""
    await stop()                                      # cierra la única ventana; el perfil persiste en disco
    _write(mode="blank", url="", title="Navegador cerrado", loading=False, error="",
           youtube_id="", youtube_title="")
    _emit("closed_window", "ventana cerrada (sesión guardada)")


_visible_override = None   # None = normal; True = forzar visible (login); False = forzar headless. Lo usa authenticate.


def _headless() -> bool:
    """HEADLESS por DEFECTO (2026-07-08): corre POR DETRÁS, sin ventana → no roba el foco/cursor del operador
    (podía escribir en su ordenador mientras el bot automatiza) y no hay que verlo — bastan las capturas. Para
    VERLO (conducir a mano / LOGIN), activa modo visible: store `navegador_visible=true` o env
    ZAELAR_NAVEGADOR_VISIBLE=1, o el override runtime de authenticate."""
    if _visible_override is not None:      # authenticate fuerza visible para el login, luego vuelve a headless
        return not _visible_override
    if os.environ.get("ZAELAR_NAVEGADOR_VISIBLE", "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        import json as _json
        from config.settings import SETTINGS_FILE
        if SETTINGS_FILE.is_file():
            if (_json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {}).get("navegador_visible"):
                return False
    except Exception:
        pass
    if os.environ.get("ZAELAR_NAVEGADOR_HEADLESS", "").strip().lower() in ("0", "false", "no"):
        return False
    return True   # por defecto: headless (por detrás)


def _profile_dir() -> str:
    """Perfil PERSISTENTE y AISLADO (cookies/sesión/logins se guardan en disco → no re-meter credenciales cada vez).
    Vive dentro del widget, separado de tu Chrome y de tu automatización del 9222: NO comparte perfil con nada tuyo."""
    d = os.path.join(store.data_dir(WID), "profile")
    os.makedirs(d, exist_ok=True)
    return d


def _remote_port() -> str:
    """Puerto de depuración remota del navegador — CONTROLABLE POR CONFIGURACIÓN (la UI escribe config/settings.json).
    Orden: store `navegador_remote_port` → env `NAVEGADOR_REMOTE_PORT` → vacío (pipe interno, sin puerto TCP).
    NUNCA usa 9222/9200 (puertos típicos de la automatización del operador): si alguien los pone, se ignoran y se
    vuelve a pipe, para no pisar jamás su navegador. Best-effort: cualquier fallo de lectura → env/vacío."""
    val = ""
    try:
        import json as _json
        from config.settings import SETTINGS_FILE
        if SETTINGS_FILE.is_file():
            val = str((_json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {})
                      .get("navegador_remote_port") or "").strip()
    except Exception:
        val = ""
    val = val or os.environ.get("NAVEGADOR_REMOTE_PORT", "").strip()
    return "" if val in ("9222", "9200") else val


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled",
                "--window-size=1296,900", "--window-position=60,60"]

# NAVEGAR COMO UN HUMANO, no scrapear (regla del operador 2026-07-21): un asistente DISCRETO que hace búsquedas
# como una persona y pasa los filtros anti-bot de forma NATURAL — nunca patrones de scraper. Este init-script borra
# las huellas que delatan a un Chromium automatizado (DataDome/idealista, PerimeterX, Cloudflare las miran):
# navigator.webdriver, objeto chrome ausente, plugins/idiomas vacíos, WebGL "SwiftShader" del headless. Se combina
# con el Chrome REAL (channel), el ratón Bézier+jitter y el tecleo con delay que YA existen. No hackea nada: hace
# que un navegador de verdad, conducido despacio, parezca lo que es — una persona navegando.
_STEALTH_JS = """
(() => {
  try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (e) {}
  try { window.chrome = window.chrome || { runtime: {}, app: {}, csi: () => {}, loadTimes: () => {} }; } catch (e) {}
  try { Object.defineProperty(navigator, 'languages', {get: () => ['es-ES','es','en']}); } catch (e) {}
  try { Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]}); } catch (e) {}
  try {
    const gp = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Intel Inc.';                      // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return 'Intel Iris OpenGL Engine';        // UNMASKED_RENDERER_WEBGL (no 'SwiftShader')
      return gp.call(this, p);
    };
  } catch (e) {}
  try {
    const q = navigator.permissions && navigator.permissions.query;
    if (q) navigator.permissions.query = (p) => (p && p.name === 'notifications')
      ? Promise.resolve({state: Notification.permission}) : q(p);
  } catch (e) {}
})();
"""


async def _ensure_page():
    """UNA SOLA ventana real (headed) con PERFIL PERSISTENTE, arranque perezoso. Reutiliza la ventana/pestaña que
    ya haya (nunca abre una ventana por petición → no llena el escritorio). Perfil aislado: no toca tu Chrome ni tu
    navegador del 9222/9200 (proceso e instancia propios). Si la ventana real falla (sin display), degrada a headless
    para no dejar el widget muerto. Import perezoso de playwright: si falta la dep, degrada este widget solo."""
    global _pw, _browser, _context, _page
    if _page is not None and not _page.is_closed():
        return _page
    from playwright.async_api import async_playwright
    if _pw is None:
        _pw = await async_playwright().start()
    if _context is None:
        # Puerto de depuración OPCIONAL y elegido por env — NUNCA los tuyos (9222/9200). Vacío = pipe interno de
        # Playwright (cero puerto, cero colisión). Si quieres engancharte tú, pon NAVEGADOR_REMOTE_PORT a otro puerto.
        args = list(_LAUNCH_ARGS)
        port = _remote_port()                         # configurable por UI (settings.json) / env; nunca 9222/9200
        if port:
            args.append(f"--remote-debugging-port={port}")
            _emit("remote_port", f"puerto de depuración {port}")

        async def _launch(headless: bool, channel: str | None):
            # channel="chrome" = el Chrome REAL instalado (fingerprint de navegador de verdad, no el Chromium
            # de Playwright que los anti-bot reconocen). timezone_id fija la zona coherente con locale es-ES.
            kw = dict(headless=headless, viewport=VIEWPORT, locale="es-ES",
                      timezone_id="Europe/Madrid", user_agent=_UA, args=args)
            if channel:
                kw["channel"] = channel
            return await _pw.chromium.launch_persistent_context(_profile_dir(), **kw)

        # Preferimos el Chrome REAL (menos detectable). Si no está instalado, caemos al Chromium de Playwright;
        # si no hay display (headed falla), caemos a headless. Nunca dejamos el widget muerto.
        _context = None
        for _ch in ("chrome", None):
            try:
                _context = await _launch(_headless(), _ch)
                break
            except Exception as e:
                logger.warning(f"navegador: launch channel={_ch or 'chromium'} falló "
                               f"({str(e).splitlines()[0][:100]})")
        if _context is None:
            try:
                _context = await _launch(True, None)      # último recurso: chromium headless
            except Exception as e:
                logger.warning(f"navegador: headless también falló ({str(e).splitlines()[0][:100]})")
                raise
        _browser = None                               # el contexto persistente ES el navegador (no hay objeto aparte)
        try:
            await _context.add_init_script(_STEALTH_JS)   # sigilo: navegar como humano, no como scraper
        except Exception:
            pass
        _context.set_default_navigation_timeout(_NAV_TIMEOUT)
        _context.set_default_timeout(_NAV_TIMEOUT)
        # Consent de Google/YouTube en la UE: coockies que evitan el muro (mejor esfuerzo). Con perfil persistente,
        # además, una vez que se acepta un banner una vez queda guardado → deja de salir en visitas siguientes.
        try:
            await _context.add_cookies([
                {"name": "SOCS", "value": "CAI", "domain": ".youtube.com", "path": "/"},
                {"name": "SOCS", "value": "CAI", "domain": ".google.com", "path": "/"},
                {"name": "CONSENT", "value": "YES+", "domain": ".youtube.com", "path": "/"},
                {"name": "CONSENT", "value": "YES+", "domain": ".google.com", "path": "/"},
                # Wallapop: OptanonConsent (OneTrust) + cookie propia del consentimiento UE
                {"name": "OptanonConsent",
                 "value": "isGpcEnabled=0&datestamp=Tue+Jul+2026+12%3A00%3A00+GMT%2B0200&version=6.29.0&isIABGlobal=false&hosts=&consentId=&interactionCount=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1%2CC0005%3A1",
                 "domain": ".wallapop.com", "path": "/"},
                {"name": "euconsent-v2",
                 "value": "CQ...",  # placeholder — el auto-click es el mecanismo real
                 "domain": ".wallapop.com", "path": "/"},
                # Wallapop: marcador de banner aceptado (cubre su propio sistema cuando OneTrust no está)
                {"name": "wp_consent", "value": "1", "domain": ".wallapop.com", "path": "/"},
                {"name": "_consent", "value": "1", "domain": ".wallapop.com", "path": "/"},
                {"name": "user_consent", "value": "true", "domain": ".wallapop.com", "path": "/"},
                {"name": "cookie_consent", "value": "accepted", "domain": ".wallapop.com", "path": "/"},
            ])
        except Exception:
            pass
    # UNA pestaña: reutiliza la que el contexto persistente ya trae en vez de abrir otra → sin pestañas de sobra.
    _page = _context.pages[0] if _context.pages else await _context.new_page()
    _emit("launched", f"navegador {'headless' if _headless() else 'ventana real'} · perfil persistente")
    return _page


# ── utilidades ───────────────────────────────────────────────────────────────────────────────────────────────
_YT_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([0-9A-Za-z_-]{11})")
_YT_ID_RE = re.compile(r'"videoId":"([0-9A-Za-z_-]{11})"')


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip()
    if not s or " " in s:
        return False
    if s.startswith(("http://", "https://")):
        return True
    return bool(re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/.*)?$", s, re.I))   # dominio con TLD


def _normalize_url(s: str) -> str:
    s = (s or "").strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def _youtube_id(s: str) -> str:
    m = _YT_RE.search(s or "")
    return m.group(1) if m else ""


def _draw_cursor(path: str, x: float, y: float) -> None:
    """Dibuja un cursor de ratón (flecha estilo SO) sobre la captura, en la posición del ratón VIRTUAL, para que
    el operador VEA dónde actúa el automatizador (el ratón vive dentro del Chromium del servidor, invisible en la
    foto; esto lo hace visible). Best-effort: si Pillow falla, deja la captura tal cual."""
    try:
        from PIL import Image, ImageDraw
        img = Image.open(path).convert("RGBA")
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        x, y = int(x), int(y)
        arrow = [(x, y), (x, y + 18), (x + 5, y + 13), (x + 9, y + 20),
                 (x + 12, y + 18), (x + 8, y + 12), (x + 14, y + 12)]
        d.polygon(arrow, fill=(250, 250, 250, 255))     # relleno claro
        d.line(arrow + [arrow[0]], fill=(20, 20, 20, 255), width=2, joint="curve")   # contorno oscuro (visible en todo fondo)
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(255, 70, 70, 230), width=2)  # halo para captar la vista
        img.alpha_composite(ov)
        img.convert("RGB").save(path)
    except Exception:
        pass


async def _capture() -> None:
    """Fotografía la viewport → widgets/_data/navegador/shot.png y sube rev (cache-bust del <img> en cliente)."""
    global _rev
    page = _page
    shot = f"{store.data_dir(WID)}/shot.png"
    await page.screenshot(path=shot, type="png", full_page=False)
    if _automating:                                     # tarea en curso → pinta el cursor virtual donde está actuando
        # OFF-LOOP (V2-035): el composite PIL es CPU síncrono que retenía el GIL en el loop de uvicorn y hambreaba
        # el pump de audio del TTS (voz entrecortada). A un hilo → no bloquea la voz.
        await asyncio.to_thread(_draw_cursor, shot, _mouse["x"], _mouse["y"])
    _rev += 1
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    _write(mode="page", url=page.url, title=title or page.url, rev=_rev, loading=False, error="",
           youtube_id="", youtube_title="")
    _emit("screenshot", page.url, rev=_rev)


async def _goto(url: str, push: bool = True) -> None:
    global _idx, _hist
    page = await _ensure_page()
    _write(loading=True, error="", url=url)
    _emit("navigate", url)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await _dismiss_overlays(page)                    # cierra banners de cookies que bloquean la web
        await asyncio.sleep(0.35)                     # deja pintar el above-the-fold antes de la foto
    except Exception as e:
        _write(loading=False, error=f"No pude abrir la página: {str(e).splitlines()[0][:200]}")
        _emit("nav_error", url, error=str(e)[:200])
        return
    if push:
        _hist = _hist[:_idx + 1] + [page.url]
        _idx = len(_hist) - 1
    await _capture()


# ── órdenes del buzón ────────────────────────────────────────────────────────────────────────────────────────
async def handle(action: str, payload: dict) -> None:
    payload = payload or {}
    if action == "open":
        raw = str(payload.get("url") or "").strip()
        if not raw:
            return
        yid = _youtube_id(raw)
        if yid:
            await _show_youtube(yid, "")
        elif _looks_like_url(raw):
            await _goto(_normalize_url(raw))
        else:
            await _search(raw)                        # texto suelto en la barra → búsqueda en Google
    elif action == "search":
        await _search(str(payload.get("q") or payload.get("url") or "").strip())
    elif action == "youtube":
        await _youtube(str(payload.get("q") or "").strip(), str(payload.get("url") or "").strip())
    elif action in ("back", "forward"):
        await _step(action)
    elif action == "reload":
        page = await _ensure_page()
        _write(loading=True)
        try:
            await page.reload(wait_until="domcontentloaded")
            await _dismiss_overlays(page)
            await asyncio.sleep(0.3)
        except Exception:
            pass
        await _capture()
    elif action == "scroll":
        await _scroll(float(payload.get("dy") or 0))
    elif action == "click":
        await _click(float(payload.get("x") or 0), float(payload.get("y") or 0))
    elif action == "type":
        await _type(str(payload.get("text") or ""))
    elif action == "press":
        await _press(str(payload.get("key") or ""))
    elif action in ("close", "quit", "close_browser"):
        await _close_browser()
    elif action == "automate":
        # SPAWN (no await): el buzón del owner es SERIAL — si esperáramos el bucle entero, las tareas no correrían
        # en PARALELO. Lanzamos la tarea en segundo plano y liberamos el buzón para el siguiente comando → N tareas
        # concurrentes, cada una en su pestaña. Guardamos la ref para que no la recoja el GC.
        _t = asyncio.create_task(_automate(str(payload.get("goal") or payload.get("task") or ""),
                                           str(payload.get("plan") or ""), str(payload.get("task_id") or "")))
        _running.add(_t)
        _t.add_done_callback(_running.discard)
    elif action == "browse":
        # Navegación SIMPLE de una tarea/tab (sin bucle): abre/busca/youtube en SU pestaña → tarjeta vertical.
        _t = asyncio.create_task(_browse(str(payload.get("task_id") or ""), str(payload.get("mode") or "open"),
                                         str(payload.get("url") or ""), str(payload.get("q") or "")))
        _running.add(_t)
        _t.add_done_callback(_running.discard)
    elif action == "authenticate":
        await _authenticate(str(payload.get("task_id") or ""), str(payload.get("url") or ""))
    elif action == "auth_done":
        await _auth_done(str(payload.get("task_id") or ""))
    elif action == "cancel_task":
        await _close_task(str(payload.get("task_id") or ""))
    elif action == "answer_task":
        from . import tasks
        tasks.answer(str(payload.get("task_id") or ""), str(payload.get("text") or ""))
    else:
        logger.debug(f"navegador: orden desconocida {action!r}")


_task_browsers: dict = {}   # task_id -> TaskBrowser (para cerrar la pestaña al cerrar la tarjeta / cancelar)
_running: set = set()       # tareas asyncio en vuelo (evita que el GC las recoja)
_shot_lock = asyncio.Lock()  # serializa bring_to_front+captura entre tareas paralelas (headed pinta 1 tab a la vez)

# AUTENTICACIÓN — estado de control (una sola ventana → un solo login a la vez; reanudación tras auth_done).
_LOGIN_TIMEOUT = float(os.environ.get("NAVEGADOR_LOGIN_TIMEOUT", "600"))  # 10 min sin terminar → recordatorio (no mata)
_LOGIN_POLL = float(os.environ.get("NAVEGADOR_LOGIN_POLL", "2.5"))        # cada cuánto vigila la ventana de login
_auth_resume: dict = {}     # task_id -> {"goal","plan","site"} de tareas a REANUDAR tras el login (la que lo pidió + las pausadas)
_auth_active: str = ""      # sitio del login EN CURSO ("" = ninguno) — serializa: no abrimos dos ventanas de login
_login_timeouts: dict = {}  # task_id -> asyncio.Task del watcher/poller de login (auto-detección + timeout)
_auth_baseline_cookies: dict = {}  # task_id -> set((domain,name)) al abrir el login → detectar cookies NUEVAS = sesión dada

# Reaching-the-login es DISTINTO en cada web → enfoque VERSÁTIL: (1) URL de login conocida para los sitios comunes;
# (2) si no hay o no acierta, se abre el dominio y se BUSCA en la página el enlace/botón de "iniciar sesión" (por
# texto, multi-idioma) EVITANDO el de registro, y se clica. Nunca aterriza en la página de REGISTRO.
_LOGIN_URLS = {
    "google.com": "https://accounts.google.com/signin",
    "gmail.com": "https://accounts.google.com/signin/v2/identifier?service=mail",
    "youtube.com": "https://accounts.google.com/signin",
    "wallapop.com": "https://es.wallapop.com/login",
    "linkedin.com": "https://www.linkedin.com/login",
    "amazon.es": "https://www.amazon.es/ap/signin",
    "amazon.com": "https://www.amazon.com/ap/signin",
    "github.com": "https://github.com/login",
    "x.com": "https://x.com/i/flow/login",
    "twitter.com": "https://x.com/i/flow/login",
    "instagram.com": "https://www.instagram.com/accounts/login/",
    "facebook.com": "https://www.facebook.com/login",
    "outlook.com": "https://login.live.com/",
    "microsoft.com": "https://login.microsoftonline.com/",
}
_LOGIN_TEXT_RE = re.compile(r"(iniciar sesi[oó]n|inicia sesi[oó]n|log ?in|log ?on|sign ?in|acceder|entrar|mi cuenta)", re.I)
_REGISTER_TEXT_RE = re.compile(r"(regist|reg[ií]strate|sign ?up|crear cuenta|cr[eé]ate|new account|\b[úu]nete\b|join now)", re.I)


async def _automate(goal: str, plan: str = "", task_id: str = "") -> None:
    """Ejecuta el bucle HÍBRIDO DOM+visión (agent.py) para UNA tarea, en SU PROPIA pestaña (TaskBrowser). El
    progreso va al feed de la tarea (tasks.add_event vía TaskBrowser._emit) y su tarjeta se refresca sola; al
    terminar, resultados + aviso proactivo (voz+UI). La pestaña queda ABIERTA para que el operador la vea; se
    cierra al cerrar la tarjeta. `plan` = guía de alto nivel de Hermes (best-effort)."""
    if not goal:
        return
    from . import agent, tasks
    if not task_id:
        task_id = tasks.create(goal)
    tasks.set_status(task_id, "working")
    tasks.set_phase(task_id, "buscando resultados", True)     # FASE (spinner): el operador ve el PROCESO, no clics
    tb = TaskBrowser(task_id)
    _task_browsers[task_id] = tb
    # ROBUSTEZ (V2-035): si el plan trae una URL de resultados ya FILTRADA (primera línea `URL: …`, la compone el
    # planificador con las keywords depuradas + precio), arranca el navegador DIRECTO en la rejilla de resultados
    # en vez de teclear en la caja y navegar a mano (lo frágil que se atascaba en Wallapop). El resto del plan
    # sigue como guía del bucle.
    start_url = ""
    if plan:
        _m = re.match(r"\s*URL:\s*(\S+)", plan, re.I)
        if _m:
            start_url = _m.group(1).strip()
            plan = plan[_m.end():].lstrip("\n ")
    if start_url:
        try:
            tasks.milestone(task_id, f"➡️ voy directo a la rejilla de resultados filtrada")
            await tb.agent_act("navigate", {"url": start_url})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"navegador: navigate inicial a resultados falló: {e}")
    try:
        res = await agent.run_task(goal, tb, plan=plan)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "summary": f"error del automatizador: {str(e).splitlines()[0][:160]}"}
    # MURO DE LOGIN: el bucle chocó con un inicio de sesión y NO tecleó credenciales. Abrimos la ventana real para
    # que el operador entre a mano; la tarea NO se cierra — queda pausada y se reanuda sola tras auth_done.
    if res.get("needs_login"):
        await _begin_login(task_id, res.get("site", ""), res.get("login_url", ""), goal, plan)
        return
    summary = str(res.get("summary") or "")
    ok, success = bool(res.get("ok")), bool(res.get("success"))
    results = res.get("results")
    # Resultados RICOS: rasca los anuncios de la página final + el modelo barato elige los mejores + conclusión.
    # Fases visibles: recopilando → (N anuncios) → investigando los mejores. Best-effort.
    if not results and ok:
        try:
            tasks.set_phase(task_id, "recopilando anuncios", True)
            items = await tb.extract_listings()
            if items:
                # OBSERVABILIDAD (V2-035): deja en el feed QUÉ candidatos se extrajeron (para poder revisar después
                # si la búsqueda trajo lo pedido —p.ej. enduro— o categoría equivocada), no solo "N anuncios".
                _sample = "; ".join(
                    f"{(it.get('title') or '')[:40]}{(' · '+it.get('price')) if it.get('price') else ''}"
                    for it in items[:6])
                tasks.milestone(task_id, f"📋 {len(items)} anuncios encontrados: {_sample}")
                tasks.set_phase(task_id, "investigando los mejores", True)
                results = await agent.summarize_results(goal, items)
                if results and results.get("discarded"):
                    # OBSERVABILIDAD (V2-035): qué se DESCARTÓ y POR QUÉ (p.ej. "moto de trial — no es enduro"),
                    # para poder revisar que el filtro de relevancia hizo lo correcto.
                    _dis = "; ".join(f"{d.get('title', '')[:32]} ({d.get('reason', '')[:40]})"
                                     for d in results["discarded"][:5])
                    tasks.milestone(task_id, f"🚫 descartados {len(results['discarded'])} por no encajar: {_dis}")
                if results and results.get("items"):
                    _sel = "; ".join((it.get("title") or "")[:40] for it in results["items"][:5])
                    tasks.milestone(task_id, f"⭐ seleccionados {len(results['items'])}: {_sel}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"extracción de resultados falló: {e}")
    # ÉXITO por RESULTADO, no por lo que reporte el modelo: si conseguimos anuncios rankeados, la tarea SÍ se
    # completó (el bucle a veces cierra con done {} vacío → success False aunque llegó a la rejilla). Fix del
    # "no pude completar del todo" pese a traer resultados.
    if results and results.get("items"):
        success = True
        if not summary:
            summary = results.get("conclusion") or f"{len(results['items'])} resultados"
    if results:
        tasks.set_results(task_id, results)
    tasks.set_phase(task_id, "listo" if (ok and success) else ("terminado" if ok else "no pude completarlo"), False)
    tasks.finish(task_id, "done" if (ok and success) else ("done" if ok else "failed"),
                 ("✅ " if (ok and success) else "") + (summary or "sin resumen"))
    try:
        from voice import brain_notes
        head = "completé" if (ok and success) else "no pude completar del todo"
        brain_notes.push(f"[SISTEMA] Navegador (tarea {task_id}): {head} «{goal}». {summary} Está en su tarjeta "
                         f"'{tasks.inst_id(task_id)}'.")
    except Exception:
        pass
    try:
        from voice import proactive
        # La notificación proactiva se DICE EN VOZ tal cual (no pasa por el FlashBrain que la puliría): NUNCA
        # debe filtrar el fraseo INTERNO de la tarea («{goal}» viene en 3ª persona de ingeniería, "Alex quiere
        # buscar casas…") — se oía "Lo intenté con «Alex quiere buscar…»: …", exponiendo las tripas (hallazgo del
        # juez, conv navegador). Mensaje user-facing = solo el resumen (que ya es de cara al usuario); el objetivo
        # crudo se queda en la nota [SISTEMA] (contexto para el cerebro), no en la voz.
        tail_ = (summary or "").strip()
        if (ok and success):
            msg = f"Listo. {tail_}" if tail_ and tail_ != "sin resumen" else "Listo, lo tienes en su tarjeta."
        else:
            msg = (f"No pude terminarla del todo. {tail_}" if tail_ and tail_ != "sin resumen"
                   else "No pude terminarla del todo; lo dejé en su tarjeta por si quieres verlo.")
        await proactive.notify("navegador", msg, kind="notify")
    except Exception:
        pass


async def _browse(task_id: str, mode: str, url: str, q: str) -> None:
    """Navegación simple de una tarea/tab (browse, sin bucle de automatización) → su tarjeta vertical muestra la
    captura + barra. Reutiliza TaskBrowser (una pestaña por tarea, misma ventana). No lanza."""
    if not task_id:
        return
    from . import tasks
    tb = _task_browsers.get(task_id) or TaskBrowser(task_id)
    _task_browsers[task_id] = tb
    tasks.set_status(task_id, "working")
    tasks.set_phase(task_id, "abriendo", True)
    try:
        if mode == "search":
            await tb.search(q or url)
        elif mode == "youtube":
            await tb.open_youtube(q, url)
        else:
            await tb.open_target(url or q)
    except Exception as e:  # noqa: BLE001
        tasks.milestone(task_id, f"⚠️ {str(e).splitlines()[0][:120]}")
    tasks.set_status(task_id, "open")
    tasks.set_phase(task_id, "abierto", False)


def _login_url_for(site: str) -> str | None:
    """URL de login CONOCIDA para `site` (dominio), o None. Empareja por dominio base (sub.dominio.tld → dominio.tld)."""
    host = (site or "").strip().lower()
    host = host.replace("https://", "").replace("http://", "").split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    for key, u in _LOGIN_URLS.items():
        if host == key or host.endswith("." + key):
            return u
    return None


async def _click_login_affordance(page) -> bool:
    """VERSÁTIL: busca en la página el enlace/botón que lleva al LOGIN (por texto, multi-idioma) EVITANDO el de
    registro, y lo clica. Devuelve True si clicó algo. Así llegamos al login aunque no tengamos su URL exacta."""
    try:
        cands = await page.query_selector_all("a, button, [role=button]")
    except Exception:
        return False
    best = None
    for el in cands[:400]:
        try:
            txt = ((await el.inner_text()) or "").strip()
            blob = f"{txt} {(await el.get_attribute('aria-label')) or ''} {(await el.get_attribute('href')) or ''}"
        except Exception:
            continue
        if not blob.strip() or not _LOGIN_TEXT_RE.search(blob):
            continue
        # es de REGISTRO (y el texto propio no dice login) → sáltalo, nunca aterrizamos en registro
        if _REGISTER_TEXT_RE.search(blob) and not _LOGIN_TEXT_RE.search(txt):
            continue
        best = el
        if _LOGIN_TEXT_RE.search(txt):                # prioriza el que dice "iniciar sesión" en su propio texto
            break
    if best is None:
        return False
    try:
        await best.click(timeout=4000)
        await page.wait_for_load_state("domcontentloaded", timeout=6000)
        return True
    except Exception:
        return False


async def _reach_login(tb, site: str) -> None:
    """Lleva la pestaña a la página de LOGIN de `site`, VERSÁTIL (cada web es distinta) y NUNCA a registro:
    (1) URL de login conocida; (2) si no acierta, abre el dominio y clica el enlace/botón de iniciar sesión."""
    from . import agent
    known = _login_url_for(site)
    target = known or (site if site.startswith("http") else f"https://{site.strip('/')}")
    try:
        await tb.open_target(target)
    except Exception:
        pass
    if tb.page is None:
        return
    await _dismiss_overlays(tb.page)
    try:
        state = await tb.snapshot_for_agent()
    except Exception:
        state = {"url": tb.page.url, "elements": ""}
    if agent._looks_like_login(state.get("url", ""), state.get("elements", "")):
        return                                        # la URL conocida ya nos dejó en el login
    await _click_login_affordance(tb.page)            # versátil: encuentra y clica "iniciar sesión"
    await _dismiss_overlays(tb.page)


async def _cookie_fingerprint(tb) -> set:
    """Huella (domain,name) de las cookies actuales del perfil — para detectar cookies NUEVAS tras el login."""
    try:
        cookies = await tb.page.context.cookies()
        return {(c.get("domain", ""), c.get("name", "")) for c in cookies}
    except Exception:
        return set()


async def _authenticate(task_id: str, url: str, *, site: str = "", goal: str = "", plan: str = "") -> None:
    """Abre la VENTANA REAL (visible) directamente en el LOGIN del sitio y se queda VIGILÁNDOLA: cuando detecta que
    la sesión ya está dada (dejó el login/registro + aparecieron cookies nuevas), cierra sola y vuelve a headless —
    CERO pasos manuales. La sesión se guarda en el perfil PERSISTENTE (no hay que copiar cookies del Chrome del
    sistema). `url` = URL de login ya detectada (ruta need_login) o el sitio/dominio a resolver (authenticate_web)."""
    global _visible_override, _auth_active
    from . import agent, auth_memory, tasks
    url = (url or "wallapop.com").strip()
    site = (site or _login_site_of(url)).strip().lower()
    if not task_id:
        task_id = tasks.create(f"Iniciar sesión · {site or url}", title=f"Login · {site or url}")
    _auth_resume.setdefault(task_id, {"goal": goal, "plan": plan, "site": site})
    # GUARDA: ¿YA hay sesión? entonces NO abras ningún login — confírmalo y sigue con la tarea (bug: reabría el
    # login de Wallapop estando ya autenticado). Comprobación headless, sin ventana.
    if await _already_authenticated(site):
        auth_memory.record_session_established(site)
        # objetivo de búsqueda a retomar: el de la tarea, o el que quedó en el checkpoint de memoria (auth_pendiente).
        pend = auth_memory.read_auth_pending() or {}
        goal_to_run = ((_auth_resume.get(task_id) or {}).get("goal") or goal or pend.get("objetivo") or "").strip()
        auth_memory.clear_auth_pending()
        tasks.set_login_wait(task_id, False)
        tasks.milestone(task_id, f"✅ Ya había sesión en «{site}» — no hace falta iniciar sesión")
        try:
            from voice import proactive
            await proactive.notify("navegador", f"Ya estabas dentro de {site}, no hace falta iniciar sesión. Sigo.",
                                   kind="notify")
        except Exception:
            pass
        if goal_to_run:                                          # hay búsqueda que retomar → lánzala ya (autenticado)
            tasks.set_phase(task_id, "retomando la búsqueda", True)
            _auth_resume.pop(task_id, None)
            _t = asyncio.create_task(_automate(goal_to_run, "", task_id))
            _running.add(_t)
            _t.add_done_callback(_running.discard)
        else:                                                     # sin objetivo (login suelto) → cierra la tarjeta, no colgada
            tasks.set_phase(task_id, "ya tenías sesión", False)
            tasks.finish(task_id, "done", "Ya tenías sesión iniciada.")
        await _resume_paused_tasks()                              # reanuda OTRAS tareas pausadas por el login (si las hubo)
        return
    if _in_container():
        # 2026-08-03: en un contenedor headless (cloud) no hay display → el relanzado "headed" de más abajo
        # SIEMPRE degrada a headless en silencio (`_ensure_page`), y la tarea se queda esperando un login que
        # nunca puede pasar — antes esto se quedaba embuclado para siempre (voz Y widget colgados, visto en vivo
        # con Wallapop). Cortar aquí, ANTES de intentarlo, con un mensaje claro en vez de un intento fantasma.
        msg = (f"Para entrar en {site or url} hace falta iniciar sesión, y eso todavía no lo puedo hacer desde la "
               "nube — necesitaría abrir una ventana de navegador que aquí no existe. Instala la versión local "
               "(desde GitHub) si quieres usar sitios que exigen iniciar sesión.")
        await _fail_paused_tasks(msg)
        try:
            from voice import proactive
            await proactive.notify("navegador", msg, speak=True)
        except Exception:
            pass
        return
    _auth_active = site
    auth_memory.checkpoint_auth_pending(site, task_id, goal)       # miga durable (sobrevive a crash/reinicio)
    _visible_override = True                                       # fuerza VISIBLE para el login
    await stop()                                                  # relanza headed (el perfil/cookies persisten)
    _task_browsers.pop(task_id, None)
    tb = TaskBrowser(task_id)
    _task_browsers[task_id] = tb
    tasks.set_status(task_id, "needs_input")
    tasks.set_phase(task_id, "esperando tu inicio de sesión", True)
    tasks.set_login_wait(task_id, True)
    try:
        if agent._LOGIN_URL_RE.search(url.lower()):               # ya ES una URL de login (ruta need_login) → ábrela
            await tb.open_target(url)
            if tb.page is not None:
                await _dismiss_overlays(tb.page)
        else:                                                     # es un sitio/dominio → RESUELVE el login (versátil)
            await _reach_login(tb, site or url)
    except Exception as e:  # noqa: BLE001
        tasks.milestone(task_id, f"⚠️ {str(e).splitlines()[0][:100]}")
    _auth_baseline_cookies[task_id] = await _cookie_fingerprint(tb)
    tasks.milestone(task_id, "🔓 Inicia sesión en la ventana; lo detecto solo cuando entres — no tienes que hacer nada más")
    try:
        from voice import proactive
        await proactive.notify("navegador", "Te abrí el login. Entra con tu cuenta; en cuanto vea que estás dentro, "
                               "sigo yo solo.", speak=True)
    except Exception:
        pass
    _arm_login_watch(task_id, site)                               # VIGILA la ventana → auto-detecta el login


async def _begin_login(task_id: str, site: str, login_url: str, goal: str = "", plan: str = "") -> None:
    """Un muro de login paró una tarea. PAUSA las demás tareas activas (una sola ventana → el relanzado headed mata
    sus pestañas) apuntándolas para reanudar, y abre la ventana de login (que ya vigila sola). Se reanudan en auth_done."""
    from . import tasks
    site = (site or _login_site_of(login_url)).strip().lower()
    _auth_resume[task_id] = {"goal": goal, "plan": plan, "site": site}
    for other in list(tasks.active_ids()):
        if other == task_id:
            continue
        ot = tasks.get(other)
        if ot.get("goal"):
            _auth_resume.setdefault(other, {"goal": ot["goal"], "plan": "", "site": site})
        tasks.set_status(other, "needs_input")
        tasks.milestone(other, "⏸ en pausa mientras inicias sesión; la reanudo al terminar")
    await _authenticate(task_id, login_url, site=site, goal=goal, plan=plan)


def _arm_login_watch(task_id: str, site: str) -> None:
    """(Re)arma el POLLER que vigila la ventana de login (auto-detección + timeout suave)."""
    old = _login_timeouts.pop(task_id, None)
    if old:
        old.cancel()
    t = asyncio.create_task(_login_watch(task_id, site))
    _login_timeouts[task_id] = t
    _running.add(t)
    t.add_done_callback(_running.discard)


async def _is_logged_in(task_id: str, tb, site: str) -> bool:
    """¿La sesión ya está dada? Señal VERSÁTIL (sin adivinar nombres de cookie por sitio): la página YA NO es un
    login/registro Y han aparecido cookies NUEVAS respecto al momento de abrir el login (el navegar el login por sí
    solo no crea sesión; el login sí deja cookies y redirige fuera del formulario)."""
    from . import agent
    try:
        state = await tb.snapshot_for_agent()
    except Exception:
        return False
    url = state.get("url", "")
    if agent._looks_like_login(url, state.get("elements", "")) or _REGISTER_TEXT_RE.search(url):
        return False                                              # sigue en login/registro
    new_cookies = await _cookie_fingerprint(tb) - _auth_baseline_cookies.get(task_id, set())
    return len(new_cookies) >= 1


async def _login_watch(task_id: str, site: str) -> None:
    """VIGILA la ventana de login: cada `_LOGIN_POLL`s captura la página (la tarjeta la muestra en vivo) y comprueba
    si la sesión ya está dada; con 2 lecturas seguidas positivas dispara `_auth_done` SOLO (cero pasos manuales).
    `_LOGIN_TIMEOUT` sin terminar → recordatorio suave, sin matar. El botón/voz siguen como red de seguridad."""
    from . import tasks
    stable = 0
    waited = 0.0
    reminded = False
    try:
        while True:
            await asyncio.sleep(_LOGIN_POLL)
            waited += _LOGIN_POLL
            t = tasks.get(task_id)
            if not t or not t.get("awaiting_login"):
                return                                            # resuelto por otra vía (botón/voz/cancel)
            tb = _task_browsers.get(task_id)
            if tb is None:
                return
            try:
                await tb._capture()                               # refresca la captura viva en la tarjeta
            except Exception:
                pass
            stable = stable + 1 if await _is_logged_in(task_id, tb, site) else 0
            if stable >= 2:                                       # confirmado en 2 lecturas → cierra solo
                tasks.milestone(task_id, "✅ Detecté que ya iniciaste sesión")
                await _auth_done(task_id)
                return
            if not reminded and waited >= _LOGIN_TIMEOUT:
                reminded = True
                tasks.milestone(task_id, "⏰ Sigo vigilando la ventana de login; tómate tu tiempo.")
                try:
                    from voice import proactive
                    await proactive.notify("navegador", f"Sigo pendiente de tu login en {site}, sin prisa.",
                                           kind="notify")
                except Exception:
                    pass
    except asyncio.CancelledError:
        return


async def _auth_done(task_id: str) -> None:
    """El operador terminó de loguearse → vuelve a HEADLESS; la sesión queda en el perfil persistente (cookies en
    disco). SONDA que la sesión cuajó de verdad; si sí, graba la miga de ALTA en memoria, limpia el checkpoint de
    'a medias' y REANUDA (automático) las tareas que quedaron pausadas. Cierra la ventana visible (escritorio limpio)."""
    global _visible_override, _auth_active
    from . import auth_memory, tasks
    w = _login_timeouts.pop(task_id, None)
    if w and w is not asyncio.current_task():
        w.cancel()                                    # para el poller (salvo que sea él quien nos llama)
    _auth_baseline_cookies.pop(task_id, None)
    _visible_override = False                         # vuelve a headless
    if task_id:
        tasks.set_login_wait(task_id, False)
        tasks.set_phase(task_id, "sesión guardada", False)
        tasks.milestone(task_id, "✅ Sesión guardada en el perfil")
        _task_browsers.pop(task_id, None)
    await stop()                                      # cierra la ventana; el perfil (cookies) persiste → relanza headless
    site = _auth_active or (_auth_resume.get(task_id) or {}).get("site") or ""
    # SONDA POST-LOGIN: ¿la sesión cuajó o rebotamos al login? (best-effort → ante duda asume OK, no bloquea).
    if site and not await _probe_logged_in(site):
        tasks.milestone(task_id, "⚠️ No detecté la sesión iniciada; puede que el login no se completara.")
        auth_memory.checkpoint_auth_pending(site, task_id, (_auth_resume.get(task_id) or {}).get("goal", ""))
        _auth_active = ""
        try:
            from voice import proactive
            await proactive.notify("navegador", f"No me quedó guardada la sesión de {site}. ¿Reintentamos el "
                                   f"inicio de sesión?", kind="notify")
        except Exception:
            pass
        return
    if site:
        auth_memory.record_session_established(site)  # ALTA recallable (el secreto sigue solo en el perfil)
    auth_memory.clear_auth_pending()
    _auth_active = ""
    await _resume_paused_tasks()
    try:
        from voice import proactive
        await proactive.notify("navegador", "Sesión guardada, sigo con lo tuyo.", kind="notify")
    except Exception:
        pass


async def _resume_paused_tasks() -> None:
    """Reanuda (re-encola `automate`) TODAS las tareas apuntadas al empezar el login: la que lo pidió + las que se
    pausaron. Drena `_auth_resume`. Las canceladas o sin objetivo se descartan."""
    from . import tasks
    items = list(_auth_resume.items())
    _auth_resume.clear()
    for tid, info in items:
        goal = (info or {}).get("goal", "")
        if not goal or tasks.is_cancelled(tid):
            continue
        tasks.set_status(tid, "queued")
        tasks.milestone(tid, "▶️ reanudo la tarea, ya autenticado")
        _t = asyncio.create_task(_automate(goal, (info or {}).get("plan", ""), tid))
        _running.add(_t)
        _t.add_done_callback(_running.discard)


def _in_container() -> bool:
    """¿Corremos en un contenedor headless (cloud), sin display para una ventana real? Mismo accessor que
    `nucleo/workers/providers.py::_is_container()` — la licencia local de Claude Code y la ventana de login
    comparten la misma limitación: ninguna de las dos existe dentro de un contenedor."""
    try:
        from config import doctor
        return bool(doctor.hardware().get("container"))
    except Exception:
        return False


async def _fail_paused_tasks(message: str) -> None:
    """Cierra en LIMPIO la tarea que pidió el login + las que se pausaron esperándolo — hermana de
    `_resume_paused_tasks`, para cuando el login NO puede resolverse en este entorno (en vez de dejarlas
    colgadas para siempre esperando un login que nunca va a llegar)."""
    from . import tasks
    items = list(_auth_resume.items())
    _auth_resume.clear()
    for tid, _info in items:
        if tasks.is_cancelled(tid):
            continue
        tasks.set_login_wait(tid, False)
        tasks.finish(tid, "failed", message)


# Solo intención FUERTE de login para detectar "hay que iniciar sesión" (no ambiguos como "mi cuenta"/"entrar",
# que también salen ESTANDO logueado → falsos positivos).
_LOGIN_STRICT_RE = re.compile(r"(iniciar sesi[oó]n|inicia sesi[oó]n|log ?in|sign ?in)", re.I)


async def _find_login_affordance(page) -> bool:
    """¿Hay en la página un enlace/botón VISIBLE de 'iniciar sesión'? Presencia = NO hay sesión (la web te invita a
    entrar); ausencia (en una página que no es login) = ya estás dentro (te muestra tu menú de cuenta)."""
    try:
        cands = await page.query_selector_all("a, button, [role=button]")
    except Exception:
        return False
    for el in cands[:400]:
        try:
            txt = ((await el.inner_text()) or "").strip() or ((await el.get_attribute("aria-label")) or "")
        except Exception:
            continue
        if txt and _LOGIN_STRICT_RE.search(txt) and not _REGISTER_TEXT_RE.search(txt):
            try:
                if await el.is_visible():
                    return True
            except Exception:
                return True
    return False


async def _already_authenticated(site: str) -> bool:
    """¿YA hay sesión en `site`? Navega headless y comprueba que NO es una pantalla de login Y que NO hay un botón
    de 'iniciar sesión' visible (la web ya te muestra tu cuenta). Evita reabrir el login cuando ya estás dentro
    (bug 2026-07-10: reanudó la búsqueda y reabrió el login de Wallapop estando ya autenticado). Best-effort: ante
    duda devuelve False (mejor comprobar el login que actuar sin cuenta)."""
    if not site:
        return False
    from . import agent
    try:
        page = await _ensure_page()
        url = site if site.startswith("http") else f"https://{site.strip('/')}"
        await page.goto(url, wait_until="domcontentloaded")
        await _dismiss_overlays(page)
        await asyncio.sleep(0.5)
        if agent._looks_like_login(page.url or "", ""):
            return False
        return not await _find_login_affordance(page)
    except Exception:
        return False


async def _probe_logged_in(site: str) -> bool:
    """Navega al sitio (headless) y comprueba que NO rebota a una pantalla de login → la sesión cuajó. Reutiliza el
    detector de `agent._looks_like_login`. Best-effort: cualquier fallo → True (no bloquea por una sonda dudosa)."""
    if not site:
        return True
    from . import agent
    try:
        page = await _ensure_page()
        url = site if site.startswith("http") else f"https://{site}"
        await page.goto(url, wait_until="domcontentloaded")
        await _dismiss_overlays(page)
        await asyncio.sleep(0.4)
        return not agent._looks_like_login(page.url or "", "")
    except Exception:
        return True


def _login_site_of(url: str) -> str:
    """Host legible (sin www) de una URL de login, para nombrar el sitio si el bucle no lo pasó."""
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host or "el sitio"
    except Exception:
        return "el sitio"


async def _close_task(task_id: str) -> None:
    """Cierra la pestaña de una tarea y la marca cancelada (al cerrar su tarjeta o por orden del operador)."""
    from . import tasks
    tb = _task_browsers.pop(task_id, None)
    if tb:
        await tb.close()
    if not tasks.is_cancelled(task_id) and tasks.get(task_id).get("status") in ("queued", "working", "needs_input"):
        tasks.cancel(task_id)


async def _search(q: str) -> None:
    if not q:
        return
    await _goto(_SEARCH_URL.replace("{q}", quote_plus(q)))


async def _step(direction: str) -> None:
    global _idx
    page = await _ensure_page()
    _write(loading=True)
    try:
        if direction == "back":
            await page.go_back(wait_until="domcontentloaded")
            _idx = max(0, _idx - 1)
        else:
            await page.go_forward(wait_until="domcontentloaded")
            _idx = min(len(_hist) - 1, _idx + 1)
        await asyncio.sleep(0.3)
    except Exception:
        pass
    await _capture()


async def _scroll(dy: float) -> None:
    page = await _ensure_page()
    try:
        await page.mouse.wheel(0, dy)
        await asyncio.sleep(0.2)
    except Exception:
        pass
    await _capture()


async def _click(x: float, y: float) -> None:
    global _idx, _hist
    page = await _ensure_page()
    _write(loading=True)
    _emit("click", f"{int(x)},{int(y)}")
    try:
        await page.mouse.click(x, y)
        await asyncio.sleep(0.6)                       # deja que un clic que navega asiente
    except Exception as e:
        _write(loading=False, error=f"No pude hacer clic: {str(e).splitlines()[0][:160]}")
        return
    if page.url and (not _hist or page.url != _hist[_idx if 0 <= _idx < len(_hist) else -1]):
        _hist = _hist[:_idx + 1] + [page.url]          # un clic que navegó empuja al historial
        _idx = len(_hist) - 1
    await _capture()


async def _type(text: str) -> None:
    page = await _ensure_page()
    try:
        await page.keyboard.type(text, delay=15)
    except Exception:
        pass
    await _capture()


async def _press(key: str) -> None:
    page = await _ensure_page()
    _write(loading=True)
    try:
        await page.keyboard.press(key or "Enter")
        await asyncio.sleep(0.6)
    except Exception:
        pass
    await _capture()


# ── YouTube (reproductor embed, no captura) ──────────────────────────────────────────────────────────────────
async def _youtube(q: str, url: str) -> None:
    yid = _youtube_id(url) or (url if re.fullmatch(r"[0-9A-Za-z_-]{11}", url or "") else "")
    if yid:
        await _show_youtube(yid, "")
        return
    if not q:
        return
    # Resuelve el primer vídeo de la búsqueda con Chromium (sin API key): raspa "videoId" del HTML de resultados.
    page = await _ensure_page()
    _write(loading=True, error="")
    _emit("yt_search", q)
    try:
        await page.goto(f"https://www.youtube.com/results?search_query={quote_plus(q)}",
                        wait_until="domcontentloaded")
        await _dismiss_overlays(page)
        await asyncio.sleep(0.5)
        html = await page.content()
    except Exception as e:
        _write(loading=False, error=f"No pude buscar en YouTube: {str(e)[:160]}")
        return
    m = _YT_ID_RE.search(html)
    if m:
        await _show_youtube(m.group(1), q)
    else:
        await _capture()                               # sin id → al menos muestra los resultados como página


async def _show_youtube(video_id: str, title: str) -> None:
    global _idx, _hist
    url = f"https://www.youtube.com/watch?v={video_id}"
    _hist = _hist[:_idx + 1] + [url]
    _idx = len(_hist) - 1
    _write(mode="youtube", url=url, title=title or "YouTube", youtube_id=video_id,
           youtube_title=title, loading=False, error="")
    _emit("youtube", video_id, title=title)


# Acciones IRREVERSIBLES que exigen OK del operador antes de ejecutarse (confirm-gate). Conservador a propósito
# (no gatear navegación normal): solo compra/pago/publicación/borrado explícitos.
_DANGER_RE = re.compile(
    r"\b(comprar|pagar|pagó|finalizar compra|realizar pedido|tramitar pedido|confirmar pedido|confirmar compra|"
    r"proceder al pago|publicar|eliminar cuenta|borrar cuenta|eliminar|borrar|checkout|buy now|buy|pay|purchase|"
    r"place order|confirm order|complete purchase|publish|delete account|delete)\b", re.I)

# ── Automatizador: snapshot de accesibilidad + input humano + ejecutor de acciones (agent.py) ────────────────
_INTERACTIVE = ("a, button, input, textarea, select, [role=button], [role=link], [role=textbox], "
                "[role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=combobox], [role=option]")

# Extractor de ANUNCIOS reales de una rejilla de resultados (corre en la página) → {title,price,url,image}.
# Endurecido (TASK 4): EXIGE precio (un anuncio tiene precio → fuera logos/nav/menús), EXCLUYE anuncios/tracking
# (doubleclick/googleads/…/utm de campaña), y **dedup por FICHA** (mismo /item/ o mismo pathname → 1 sola vez, así
# 30 tabs del mismo anuncio colapsan a uno). Prioriza enlaces de ficha (/item/, /p/, /producto, /anuncio). El
# filtrado FINO por relevancia (esto es una moto de enduro, no un móvil "Moto G") lo hace el modelo en summarize.
_JS_EXTRACT = r"""
(limit) => {
  const out=[], seen=new Set();
  const priceRe=/(\d[\d.]{0,9}\s*€)|(€\s*\d[\d.]{0,9})|(\d[\d.]{0,9}\s?(EUR|eur))/;
  const AD=/(doubleclick|googlead|googlesyndication|adservice|adnxs|criteo|taboola|outbrain|\/ads?\/|utm_source=|banner)/i;
  const ITEM=/(\/item\/|\/p\/|\/producto|\/anuncio|\/product|\/listing|\/ad\/)/i;
  const cands=[];
  for(const a of document.querySelectorAll('a[href]')){
    let href; try{ href=a.href; }catch(_){ continue; }
    if(!href || href.startsWith('javascript:') || AD.test(href)) continue;
    if(a.closest('ins, iframe, [class*="ad-" i], [id*="google_ads" i], [aria-label*="anuncio" i]')) continue;
    const img=a.querySelector('img');
    const text=(a.innerText||'').trim();
    const pm=text.match(priceRe);
    if(!pm) continue;                                   // SIN precio no es un anuncio (fuera logo/nav/banners sin €)
    let title=((img&&(img.alt||''))||text.split('\n').map(s=>s.trim()).find(s=>s.length>2 && !priceRe.test(s))||'').slice(0,90);
    // clave de dedup: la FICHA (pathname sin query) → 30 enlaces al mismo anuncio = 1
    let key; try{ const u=new URL(href); key=u.origin+u.pathname; }catch(_){ key=href; }
    if(seen.has(key)) continue;
    let image=''; if(img){ try{ image=img.currentSrc||img.src||''; }catch(_){} }
    cands.push({title, price: pm[0].replace(/\s+/g,' ').trim(), url:href, image, _item: ITEM.test(href)});
    seen.add(key);
  }
  // Si hay enlaces de FICHA de verdad, quédate solo con esos (descarta el resto de ruido con precio).
  const items = cands.filter(c=>c._item);
  const list = (items.length ? items : cands).map(({_item, ...c})=>c);
  return list.slice(0, limit);
}
"""


async def _describe_el(h) -> tuple[str, str]:
    """Rol + nombre accesible de un elemento, para el snapshot de texto que lee el modelo."""
    tag = (await h.evaluate("e => e.tagName ? e.tagName.toLowerCase() : ''")) or ""
    role = await h.get_attribute("role")
    typ = (await h.get_attribute("type") or "").lower()
    if not role:
        if tag == "a":
            role = "link"
        elif tag == "button" or typ in ("button", "submit"):
            role = "button"
        elif tag == "input":
            role = "checkbox" if typ in ("checkbox", "radio") else "textbox"
        elif tag == "textarea":
            role = "textbox"
        elif tag == "select":
            role = "combobox"
        else:
            role = tag or "element"
    name = (await h.get_attribute("aria-label")) or (await h.get_attribute("placeholder")) or ""
    if not name:
        try:
            name = (await h.inner_text()) or ""
        except Exception:
            name = ""
    if not name:
        name = (await h.get_attribute("value")) or (await h.get_attribute("name")) \
            or (await h.get_attribute("title")) or ""
    return role, " ".join((name or "").split())


# Descripción en BLOQUE (V2-036, fix de rendimiento #1): el `_describe_el` per-elemento hacía ~7 `await` por cada
# uno × hasta 60 = cientos de round-trips que RETIENEN el GIL en el loop de uvicorn → hambreaban el pump de audio de
# la voz (entrecortada). Este JS calcula rol+nombre+visibilidad de TODOS los interactivos en UNA sola llamada.
_JS_DESCRIBE = r"""
els => els.map(e => {
  const tag = e.tagName ? e.tagName.toLowerCase() : '';
  const typ = (e.getAttribute('type')||'').toLowerCase();
  let role = e.getAttribute('role');
  if(!role){
    if(tag==='a') role='link';
    else if(tag==='button'||typ==='button'||typ==='submit') role='button';
    else if(tag==='input') role=(typ==='checkbox'||typ==='radio')?'checkbox':'textbox';
    else if(tag==='textarea') role='textbox';
    else if(tag==='select') role='combobox';
    else role = tag || 'element';
  }
  let name = e.getAttribute('aria-label') || e.getAttribute('placeholder') || '';
  if(!name) name = (e.innerText||'').trim();
  if(!name) name = e.getAttribute('value') || e.getAttribute('name') || e.getAttribute('title') || '';
  const r = e.getBoundingClientRect();
  const cs = window.getComputedStyle(e);
  const vis = !!(r.width>0 && r.height>0) && cs.visibility!=='hidden' && cs.display!=='none';
  return {role, name:(name||'').replace(/\s+/g,' ').trim(), vis};
})
"""


async def _bulk_metas(page) -> list:
    """rol+nombre+visible de todos los interactivos en UNA llamada, alineado por índice con
    query_selector_all(_INTERACTIVE) (mismo selector → mismo orden de documento). Fail-open a []."""
    try:
        return await page.eval_on_selector_all(_INTERACTIVE, _JS_DESCRIBE)
    except Exception:
        return []


def _snapshot_lines(handles: list, metas: list, refmap: dict) -> list:
    """Compone las líneas [ref] rol \"nombre\" a partir de los handles + sus metas en bloque, y rellena refmap
    (ref→handle) para que agent_act resuelva la ref de ESTE paso. Cap a 60. Sin awaits (todo el I/O ya se hizo)."""
    lines: list = []
    ref = 0
    for i, h in enumerate(handles):
        m = metas[i] if i < len(metas) else None
        if not m or not m.get("vis"):
            continue
        role = m.get("role") or "element"
        name = m.get("name") or ""
        if not name and role not in ("textbox", "combobox", "checkbox", "radio"):
            continue
        ref += 1
        refmap[ref] = h
        lines.append(f'[{ref}] {role} "{name[:80]}"')
        if ref >= 60:
            break
    return lines


async def snapshot_for_agent() -> dict:
    """Devuelve {url, title, elements} — la lista compacta de elementos interactivos VISIBLES con ref numérica,
    y rellena _refs (ref → handle) para que agent_act resuelva la ref de ESTE paso. Cap a 60 para acotar tokens.
    ANTES del snapshot, cierra banners de cookies que puedan bloquear la interacción — el automatizador llama a
    esto en cada paso, así que es el punto único y fiable de limpieza."""
    global _refs
    page = await _ensure_page()
    await _dismiss_overlays(page)
    _refs = {}
    try:
        handles = await page.query_selector_all(_INTERACTIVE)
    except Exception:
        handles = []
    metas = await _bulk_metas(page)          # UNA llamada (no ~7×N) → no hambrea la voz por GIL
    lines = _snapshot_lines(handles, metas, _refs)
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    return {"url": page.url, "title": title or "", "elements": "\n".join(lines)}


async def _human_move(page, tx: float, ty: float, mouse: dict | None = None) -> None:
    """Mueve el ratón de la posición actual a (tx,ty) por una curva Bézier con jitter y micro-pausas — parece
    humano y NO cuesta tokens (vive aquí, no en el modelo). `mouse` = dict de posición POR PESTAÑA (cada tarea
    tiene su ratón); por defecto el del tab principal (browse_web)."""
    m = mouse if mouse is not None else _mouse
    sx, sy = m["x"], m["y"]
    steps = random.randint(8, 18)
    cx = (sx + tx) / 2 + random.uniform(-60, 60)       # punto de control aleatorio → trayectoria curva
    cy = (sy + ty) / 2 + random.uniform(-40, 40)
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
        try:
            await page.mouse.move(x, y)
        except Exception:
            break
        await asyncio.sleep(random.uniform(0.006, 0.02))
    m["x"], m["y"] = tx, ty


async def _human_click_handle(page, h, mouse: dict | None = None) -> None:
    await h.scroll_into_view_if_needed(timeout=5000)
    box = await h.bounding_box()
    if box:
        tx = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
        ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
        await _human_move(page, tx, ty, mouse)
        await asyncio.sleep(random.uniform(0.05, 0.18))
        await page.mouse.click(tx, ty, delay=random.randint(40, 110))
    else:
        await h.click(timeout=5000)                    # fallback si no hay caja (elemento sin layout)


async def _human_type_handle(page, h, text: str, submit: bool, mouse: dict | None = None) -> None:
    await _human_click_handle(page, h, mouse)          # enfoca haciendo clic, como un humano
    try:
        await h.fill("")                               # limpia el campo antes de teclear
    except Exception:
        pass
    await page.keyboard.type(text, delay=random.randint(40, 120))   # tecleo con jitter
    if submit:
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await page.keyboard.press("Enter")


async def screenshot_b64() -> str:
    """Captura FRESCA del viewport (1280×800) en base64 — la usa el modo VISIÓN del automatizador cuando el DOM no
    basta (need_vision). No escribe a disco (eso lo hace _capture para el widget); aquí solo se necesitan los bytes."""
    import base64
    page = await _ensure_page()
    png = await page.screenshot(type="png", full_page=False)
    return base64.b64encode(png).decode()


async def _human_click_at(page, x: float, y: float, mouse: dict | None = None) -> None:
    """Clic humano en coordenadas ABSOLUTAS del viewport (modo visión: el modelo mira la captura y da píxeles)."""
    m = mouse if mouse is not None else _mouse
    await _human_move(page, x + random.uniform(-3, 3), y + random.uniform(-3, 3), m)
    await asyncio.sleep(random.uniform(0.05, 0.18))
    await page.mouse.click(m["x"], m["y"], delay=random.randint(40, 110))


async def agent_act(action: str, args: dict) -> tuple[bool, str]:
    """Ejecuta UNA acción del automatizador con comportamiento humano. Devuelve (ok, nota). No lanza.
    Acciones DOM (ref del snapshot): click/type. Acciones VISIÓN (coordenadas de la captura): click_at/type_at."""
    page = await _ensure_page()
    try:
        if action == "navigate":
            await _goto(_normalize_url(str(args.get("url", ""))))
            return True, f"navegado a {page.url}"
        if action == "scroll":
            await _scroll(float(args.get("dy", 600)))
            return True, "desplazado"
        if action == "press":
            await _press(str(args.get("key", "Enter")))
            return True, "tecla pulsada"
        if action in ("click_at", "type_at"):                  # modo VISIÓN — coordenadas de la captura
            x, y = float(args.get("x", 0)), float(args.get("y", 0))
            _write(loading=True)
            _emit("vision_" + ("click" if action == "click_at" else "type"), f"{int(x)},{int(y)}")
            await _human_click_at(page, x, y)
            if action == "type_at":
                await page.keyboard.type(str(args.get("text", "")), delay=random.randint(40, 120))
                if bool(args.get("submit")):
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await page.keyboard.press("Enter")
            await asyncio.sleep(0.7)
            await _capture()
            return True, ("clic" if action == "click_at" else "texto") + " (visión) hecho"
        ref = int(args.get("ref", 0))
        h = _refs.get(ref)
        if h is None:
            return False, f"ref {ref} no existe en el snapshot actual"
        if action == "click":
            _write(loading=True)
            await _human_click_handle(page, h)
            await asyncio.sleep(0.7)
            await _capture()
            return True, "clic hecho"
        if action == "type":
            _write(loading=True)
            await _human_type_handle(page, h, str(args.get("text", "")), bool(args.get("submit")))
            await asyncio.sleep(0.6)
            await _capture()
            return True, "texto escrito"
    except Exception as e:
        _write(loading=False)
        return False, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
    return False, f"acción desconocida: {action}"


# ── TaskBrowser: UNA PESTAÑA dedicada a una tarea ────────────────────────────────────────────────────────────
# Encapsula su page + ratón + refs y expone la MISMA interfaz que agent.py espera de `owner` (snapshot_for_agent /
# agent_act / screenshot_b64 / _emit), para conducir SU pestaña sin tocar el estado del tab principal (browse_web).
# Correspondencia 1:1  tarea ↔ pestaña ↔ tarjeta del canvas. Todas las pestañas viven en la MISMA ventana (contexto
# persistente compartido). Reutiliza los helpers page-paramétricos (_human_*, _dismiss_overlays, _describe_el).
class TaskBrowser:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.page = None
        self.mouse = {"x": 0.0, "y": 0.0}   # ratón PROPIO de esta pestaña
        self.refs: dict = {}
        self.rev = 0

    async def ensure(self):
        if self.page is not None and not self.page.is_closed():
            return self.page
        await _ensure_page()                 # garantiza la ventana (contexto persistente) + tab principal
        self.page = await _context.new_page()   # nueva PESTAÑA en la MISMA ventana
        self._emit("tab_open", f"pestaña de la tarea {self.task_id}")
        return self.page

    def _emit(self, label: str, text: str = "", **extra) -> None:
        # SOLO observador (/debug). Los clics/navegaciones/capturas NO van al feed de la tarjeta: el feed cuenta el
        # PROCESO (fases + hitos), no cada acción. Los hitos los empuja el flujo (_automate) con tasks.milestone.
        # V2-044: cada paso de navegación se encadena a la frase que pidió la tarea (el owner corre en el loop del
        # server, sin contexto del turno → el trace vive en el registro de tareas).
        if "trace" not in extra:
            try:
                from widgets.navegador import tasks as _tasks
                _tid = _tasks.trace_of(self.task_id)
                if _tid:
                    extra["trace"] = _tid
                    extra["span"] = f"web:{self.task_id}"
            except Exception:
                pass
        _emit(label, text, task=self.task_id, **extra)

    async def _capture(self) -> None:
        page = self.page
        shot = f"{store.data_dir(WID)}/shot-{self.task_id}.png"
        async with _shot_lock:               # serializa capturas entre tareas paralelas
            # SIN bring_to_front: en headless (por defecto) todas las pestañas pintan; y traerla al frente robaba
            # el foco/cursor del operador (no podía escribir en su ordenador). Playwright fotografía tabs de fondo.
            await page.screenshot(path=shot, type="png", full_page=False)
        # OFF-LOOP (V2-035): el composite PIL del cursor a un hilo → no roba GIL al pump de audio del TTS (voz).
        await asyncio.to_thread(_draw_cursor, shot, self.mouse["x"], self.mouse["y"])
        self.rev += 1
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        from . import tasks
        tasks.update_view(self.task_id, url=page.url, page_title=title or page.url, shot_rev=self.rev)
        self._emit("screenshot", page.url)

    async def _goto(self, url: str) -> None:
        page = await self.ensure()
        self._emit("navigate", url)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await _dismiss_overlays(page)
            await asyncio.sleep(0.35)
        except Exception as e:
            self._emit("nav_error", str(e).splitlines()[0][:160])
            return
        await self._capture()

    async def _reap_popups(self) -> None:
        """TASK 3 — no acumular pestañas: cierra los popups (target=_blank) que la web abre al hacer clic (visto:
        30 pestañas en un estudio). Si el popup era la ficha que íbamos a ver, ABSORBE su URL en NUESTRA pestaña y
        lo cierra → una ficha = misma pestaña, se procesa y se descarta. Nunca toca la pestaña de otra tarea."""
        try:
            ctx = self.page.context
        except Exception:
            return
        owned = {tb.page for tb in _task_browsers.values() if getattr(tb, "page", None)}
        absorb = ""
        for p in list(ctx.pages):
            if p is self.page or p in owned:
                continue
            try:
                if p.url and p.url != "about:blank" and not absorb:
                    absorb = p.url
                await p.close()
            except Exception:
                pass
        if absorb and absorb != self.page.url:
            try:
                await self.page.goto(absorb, wait_until="domcontentloaded")
                await _dismiss_overlays(self.page)
                await asyncio.sleep(0.3)
            except Exception:
                pass

    async def open_target(self, raw: str) -> None:
        """Navegación simple (browse, sin bucle): abre una URL/dominio, o busca si es texto suelto, o YouTube."""
        raw = (raw or "").strip()
        if not raw:
            return
        yid = _youtube_id(raw)
        if yid:
            await self._goto(f"https://www.youtube.com/watch?v={yid}")
        elif _looks_like_url(raw):
            await self._goto(_normalize_url(raw))
        else:
            await self.search(raw)

    async def search(self, q: str) -> None:
        q = (q or "").strip()
        if q:
            await self._goto(_SEARCH_URL.replace("{q}", quote_plus(q)))

    async def open_youtube(self, q: str, url: str = "") -> None:
        yid = _youtube_id(url) or (url if re.fullmatch(r"[0-9A-Za-z_-]{11}", url or "") else "")
        if not yid and q:
            page = await self.ensure()
            try:
                await page.goto(f"https://www.youtube.com/results?search_query={quote_plus(q)}",
                                wait_until="domcontentloaded")
                await asyncio.sleep(0.5)
                m = _YT_ID_RE.search(await page.content())
                yid = m.group(1) if m else ""
            except Exception:
                pass
        await self._goto(f"https://www.youtube.com/watch?v={yid}" if yid
                         else f"https://www.youtube.com/results?search_query={quote_plus(q)}")

    async def snapshot_for_agent(self) -> dict:
        page = await self.ensure()
        await _dismiss_overlays(page)
        self.refs = {}
        try:
            handles = await page.query_selector_all(_INTERACTIVE)
        except Exception:
            handles = []
        metas = await _bulk_metas(page)          # UNA llamada (no ~7×N) → no hambrea la voz por GIL (V2-036 fix #1)
        lines = _snapshot_lines(handles, metas, self.refs)
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        return {"url": page.url, "title": title or "", "elements": "\n".join(lines)}

    async def screenshot_b64(self) -> str:
        import base64
        page = await self.ensure()
        png = await page.screenshot(type="png", full_page=False)
        return base64.b64encode(png).decode()

    async def agent_act(self, action: str, args: dict) -> tuple[bool, str]:
        page = await self.ensure()
        try:
            if action == "navigate":
                await self._goto(_normalize_url(str(args.get("url", ""))))
                return True, f"navegado a {page.url}"
            if action == "scroll":
                try:
                    await page.mouse.wheel(0, float(args.get("dy", 600)))
                    await asyncio.sleep(0.2)
                except Exception:
                    pass
                await self._capture()
                return True, "desplazado"
            if action == "press":
                try:
                    await page.keyboard.press(str(args.get("key", "Enter")) or "Enter")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                await self._capture()
                return True, "tecla pulsada"
            if action in ("click_at", "type_at"):
                x, y = float(args.get("x", 0)), float(args.get("y", 0))
                self._emit("vision_" + ("click" if action == "click_at" else "type"), f"{int(x)},{int(y)}")
                await _human_click_at(page, x, y, self.mouse)
                if action == "type_at":
                    await page.keyboard.type(str(args.get("text", "")), delay=random.randint(40, 120))
                    if bool(args.get("submit")):
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        await page.keyboard.press("Enter")
                await asyncio.sleep(0.7)
                await self._reap_popups()
                await self._capture()
                return True, ("clic" if action == "click_at" else "texto") + " (visión) hecho"
            ref = int(args.get("ref", 0))
            h = self.refs.get(ref)
            if h is None:
                return False, f"ref {ref} no existe en el snapshot actual"
            if action == "click":
                # CONFIRM-GATE (seguridad): si el botón parece IRREVERSIBLE (comprar/pagar/publicar/borrar…), PARA
                # y pide OK al operador ANTES de pulsar. El automatizador nunca compra/publica/borra a ciegas.
                try:
                    _, _name = await _describe_el(h)
                except Exception:
                    _name = ""
                if _DANGER_RE.search((_name or "").lower()):
                    if not await self._confirm(_name):
                        return False, f"acción «{_name[:40]}» NO confirmada por el operador"
                await _human_click_handle(page, h, self.mouse)
                await asyncio.sleep(0.7)
                await self._reap_popups()                     # TASK 3: absorbe/cierra popups → sin acumular tabs
                await self._capture()
                return True, "clic hecho"
            if action == "type":
                await _human_type_handle(page, h, str(args.get("text", "")), bool(args.get("submit")), self.mouse)
                await asyncio.sleep(0.6)
                await self._capture()
                return True, "texto escrito"
            if action == "select_option":
                # <select> NATIVO: no se rellena con type/click_at (el popup nativo no es scrapeable). Playwright
                # `select_option` lo resuelve por LABEL (texto visible), value o índice. Sin esto, un desplegable
                # obligatorio de un formulario (motivo de anulación ITV, fechas…) BLOQUEA al worker → timeout.
                val = str(args.get("value") or args.get("text") or args.get("label") or "").strip()
                idx = args.get("index")
                try:
                    if idx is not None:
                        await h.select_option(index=int(idx))
                    else:
                        try:
                            await h.select_option(label=val)
                        except Exception:
                            await h.select_option(val)   # value o label genérico (fallback)
                except Exception as e:  # noqa: BLE001
                    return False, f"no pude seleccionar «{val or idx}» en el desplegable: {str(e).splitlines()[0][:80]}"
                await asyncio.sleep(0.4)
                await self._capture()
                return True, f"opción «{val or idx}» seleccionada"
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
        return False, f"acción desconocida: {action}"

    async def _confirm(self, label: str) -> bool:
        """Pide OK al operador para una acción irreversible y ESPERA su respuesta (por voz, enrutada a esta tarea).
        Devuelve True si la aprueba. Timeout ~60s → no ejecuta (fail-safe). Cancelable."""
        from . import tasks
        tasks.ask(self.task_id, f"Voy a pulsar «{label[:50]}». ¿Lo confirmo? (dime sí o no)")
        try:
            from voice import proactive
            await proactive.notify("navegador", f"La tarea {self.task_id} necesita tu OK para pulsar "
                                   f"«{label[:40]}». ¿Confirmo?", kind="notify")
        except Exception:
            pass
        for _ in range(120):                              # ~60s
            if tasks.is_cancelled(self.task_id):
                return False
            ans = tasks.take_answer(self.task_id)
            if ans:
                aff = any(w in ans.lower() for w in
                          ("sí", "si", "ok", "vale", "dale", "confirm", "adelante", "hazlo", "yes", "claro"))
                tasks.set_status(self.task_id, "working")
                tasks.add_event(self.task_id, "✅ confirmado" if aff else "🚫 no confirmado")
                return aff
            await asyncio.sleep(0.5)
        tasks.set_status(self.task_id, "working")
        tasks.add_event(self.task_id, "⏱ sin confirmación → no ejecuto la acción")
        return False

    async def extract_listings(self, limit: int = 14) -> list:
        """Raspa la página ACTUAL en busca de 'anuncios'/resultados: enlaces con imagen y/o precio (genérico —
        Wallapop, Idealista, tiendas). Devuelve [{title, price, url, image}]. No lanza."""
        try:
            return await self.page.evaluate(_JS_EXTRACT, limit) or []
        except Exception:
            return []

    async def close(self) -> None:
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        self.page = None
