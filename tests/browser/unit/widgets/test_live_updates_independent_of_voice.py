#
# El canal /events → escritorio tiene que vivir lo que vive la APLICACIÓN, no lo que vive la sesión de voz.
#
# BUG REAL (2026-08-09, encontrado probando en vivo la hoja de propuestas con Playwright). `openSSE` se llamaba
# SOLO dentro del arranque de la sesión de voz, y `stop()` lo CERRABA. Consecuencias, las dos silenciosas:
#   · sin micrófono (el navegador lo deniega, o un entorno headless) la voz no arranca → el escritorio no recibía
#     NINGÚN evento de widget: una tarjeta abierta se quedaba congelada en la foto de su primer render;
#   · con la voz PARADA a mano (⏻ / store.powerOff, que el operador usa a propósito desde que chat y voz son
#     independientes) pasaba lo mismo, y además `stop()` mataba el stream que ya estuviera abierto.
# Es lo contrario de lo que se le pide a esta superficie —ver llenarse el informe EN VIVO mientras un worker
# encuentra propuestas— y no daba ningún síntoma: la pantalla simplemente no se enteraba.
#
# Se prueba por TEXTO porque este repo no ejecuta JS en los tests (el frontend son módulos ES sin build). Son
# aserciones groseras a propósito: cazan la deriva típica (volver a atar el stream a la voz) sin fingir que
# entienden el JS.
#
# ⚠️ TRAMPA DE FICHERO (mordió durante el arreglo): con el motor LiveKit, `server/livekit_api.py` sirve
# `session-lk.js` EN la URL de `session.js`. Editar `session.js` no cambia nada en ejecución. Por eso el test
# comprueba LOS DOS ficheros: el que corre hoy y el que correría al volver al motor Pipecat.
#
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
MAIN = APP / "main.js"
SSE = APP / "services" / "sse.js"
SESSIONS = [APP / "services" / "session-lk.js",   # el que SIRVE el motor LiveKit (el que corre hoy)
            APP / "services" / "session.js"]      # el de Pipecat (mismo contrato, no puede divergir)


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code_lines(p: Path):
    """Líneas de CÓDIGO (sin comentarios de línea): un comentario que menciona `closeSSE` explicando por qué ya no
    se llama no puede hacer fallar el test — si no, documentar el arreglo lo rompería."""
    for raw in _txt(p).splitlines():
        s = raw.strip()
        if s and not s.startswith("//"):
            yield s


def test_the_app_opens_the_event_stream_at_boot():
    """`main.js` (arranque de la app), no la sesión de voz, es quien abre el canal."""
    code = list(_code_lines(MAIN))
    assert any("openSSE(" in l for l in code), "main.js debe abrir el stream de /events en el arranque"
    assert any(re.search(r"import\s*\{[^}]*\bopenSSE\b", l) for l in code), "…y por tanto importarlo"


def test_opening_the_stream_twice_does_not_kill_the_live_one():
    """`session.start()` sigue llamando a `openSSE` (es un reintento gratis si el arranque falló). Si esa segunda
    llamada CERRARA y reabriera, tiraría el stream vivo y se perderían los eventos en vuelo."""
    body = _txt(SSE)
    m = re.search(r"export function openSSE\([^)]*\)\s*\{(.*?)\n\}", body, re.S)
    assert m, "no encuentro openSSE en sse.js"
    head = m.group(1).strip().splitlines()[0]
    assert "return" in head and "es.close" not in head, (
        "openSSE debe ser IDEMPOTENTE (salir si ya hay stream), no cerrar y reabrir: " + head)


@pytest.mark.parametrize("path", SESSIONS, ids=lambda p: p.name)
def test_stopping_the_voice_does_not_close_the_event_stream(path):
    """El caso que congelaba la pantalla. Parar la voz (o que falle por falta de micro) NO puede cortar los eventos
    de widget: es el canal por el que el operador ve llegar los resultados."""
    assert not any("closeSSE(" in l for l in _code_lines(path)), (
        f"{path.name} vuelve a cerrar el stream de /events al parar la voz — la pantalla se queda congelada "
        "(un worker puede seguir empujando resultados y no se verán)")


# ── SESIÓN NUEVA al resetear (2026-08-10) ────────────────────────────────────────────────────────────────────
# El backend rota el id y deja su observabilidad a cero (voice/observer.py::rotate_session), pero la columna de
# observabilidad pinta sus filas A MANO (no re-renderiza por datos), así que hay que avisarla o se queda mostrando
# el historial de una sesión que ya no existe. `clearDebugBuffer()` —que el reset ya llamaba— vacía el ANILLO, no
# el DOM: era exactamente la mitad del trabajo.
DEBUG_PANEL = APP / "components" / "DebugPanel.js"
STORE = APP / "core" / "store.js"


def test_the_store_exposes_a_new_session_signal():
    code = list(_code_lines(STORE))
    assert any("sessionEpoch" in l for l in code)
    assert any("newSession" in l for l in code)


def test_a_reset_announces_the_new_session_to_the_ui():
    code = list(_code_lines(SSE))
    assert any("newSession()" in l for l in code), (
        "el handler de session/RESET debe avisar de la sesión nueva; sin eso la observabilidad se queda con las "
        "filas de la sesión anterior")


def test_the_observability_column_empties_itself_on_a_new_session():
    code = list(_code_lines(DEBUG_PANEL))
    assert any("sessionEpoch()" in l for l in code), "el panel debe reaccionar a la sesión nueva"
    assert any("clearAll()" in l for l in code), "…vaciándose"


# ── LO ÚLTIMO ARRIBA, Y EL SCROLL ES DEL OPERADOR (2026-08-10) ───────────────────────────────────────────────
# Historia: la columna «seguía» al último evento fijando el fondo, y el operador reportó que a los 10-15 mensajes
# dejaba de seguir sin que él tocara nada. Se endureció dos veces (guarda de rAF que se colgaba con la pestaña de
# fondo, `stick` que lo soltaba cualquier scroll incluido el nuestro) y aun así el estado seguía pudiendo mentir.
#
# El operador propuso quitar el problema en vez de blindarlo: **la lista crece por ARRIBA**. Lo último está pegado
# a la cabecera, así que no hay a qué perseguir; el scroll pasa a ser 100% manual. Con eso se borró TODA la
# maquinaria (seguimiento, gestos, rAF, indicador, sus dos claves i18n) — estas pruebas impiden que vuelva.
def test_the_newest_event_goes_on_top():
    """La inserción por arriba ES el mecanismo: si alguien vuelve a `appendChild` en la lista, la columna vuelve a
    necesitar que alguien persiga el fondo."""
    code = list(_code_lines(DEBUG_PANEL))
    assert any("insertBefore" in l and "firstChild" in l for l in code), \
        "las filas entran por ARRIBA (prepend), no por el final"
    assert not any("listEl.appendChild" in l for l in code), \
        "una fila añadida al final resucita el problema del seguimiento"
    # el recorte de MAX_ROWS tiene que llevarse las VIEJAS, que ahora están al final
    assert any("lastElementChild" in l for l in code), "el recorte debe podar por el final (las más viejas)"


def test_no_scroll_following_machinery_comes_back():
    """Nada de estado de seguimiento: ni el flag, ni el indicador, ni los gestos, ni el rAF que se colgaba. Un
    estado invisible que puede mentir sobre lo que estás viendo no vuelve a este panel."""
    code = list(_code_lines(DEBUG_PANEL))
    for muerto in ("stick", "pinTail", "pinPending", "followBtn", "lastGesture",
                   "requestAnimationFrame", "scrollTop = el.scrollHeight"):
        assert not any(muerto in l for l in code), f"vuelve la maquinaria de seguimiento: «{muerto}»"
    assert not any('addEventListener("scroll"' in l for l in code), \
        "el scroll es del operador: no lo escuchamos para decidir nada"
    import json
    for lang in ("en", "es"):
        b = json.loads((ENGINE / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        for k in ("debug.follow_on", "debug.follow_off"):
            assert k not in b, f"{k} sigue en {lang}: ya no hay estado de seguimiento que rotular"


def test_reading_further_down_is_not_pushed_around():
    """Crecer por arriba desplaza lo de abajo. Se compensa a mano —y se desactiva el anclaje del navegador— para
    que lo que el operador tiene bajo los ojos no se mueva, y para que el comportamiento sea el MISMO en Safari
    (que no implementa scroll anchoring) que en Chrome (donde su ajuste se sumaría al nuestro)."""
    body = DEBUG_PANEL.read_text(encoding="utf-8")
    assert "el.scrollTop +=" in body, "sin compensar, cada evento le empuja el texto al operador"
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert "overflow-anchor:none" in css.replace(" ", ""), \
        "con el anclaje del navegador activo la compensación se aplicaría DOS veces"


def test_the_filter_config_survives_a_reload():
    """La clave que se escribía (`hb_dbg_kinds_off`) no era la que se leía (`…_v2`): la configuración de filtros del
    operador se perdía en cada recarga y los valores por defecto se re-aplicaban como si fuera la primera vez."""
    body = DEBUG_PANEL.read_text(encoding="utf-8")
    claves = set(re.findall(r"hb_dbg_kinds_off\w*", body))
    assert claves == {"hb_dbg_kinds_off_v2"}, f"la clave de lectura y la de escritura deben ser UNA: {claves}"
