#
# The /events → desktop channel must live as long as the APPLICATION does, not as long as the voice session does.
#
# REAL BUG (2026-08-09, found while live-testing the proposals sheet with Playwright). `openSSE` was called
# ONLY during voice-session startup, and `stop()` CLOSED it. The two consequences were silent:
#   · without a microphone (the browser denies it, or in a headless environment), voice does not start → the desktop received
#     NO widget event: an open card froze on the snapshot from its first render;
#   · when voice was stopped MANUALLY (⏻ / store.powerOff, which the operator deliberately uses since chat and voice are
#     independent), the same thing happened, and `stop()` also killed any stream that was already open.
# This is the opposite of what this surface is supposed to provide —seeing the report fill up LIVE while a worker
# finds proposals— and it produced no symptom: the screen simply did not know.
#
# It is tested through TEXT because this repo does not execute JS in tests (the frontend consists of unbuilt ES modules). These are
# deliberately crude assertions: they catch the typical regression (tying the stream back to voice) without pretending to
# understand the JS.
#
# ⚠️ FILE TRAP (bit us during the fix): with the LiveKit engine, `server/livekit_api.py` serves
# `session-lk.js` AT the URL for `session.js`. Editing `session.js` changes nothing at runtime. That is why the test
# checks BOTH files: the one running today and the one that would run if we switched back to the Pipecat engine.
#
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
MAIN = APP / "main.js"
SSE = APP / "services" / "sse.js"
SESSIONS = [APP / "services" / "session-lk.js",   # the one SERVED by the LiveKit engine (the one running today)
            APP / "services" / "session.js"]      # the Pipecat one (same contract, cannot diverge)


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code_lines(p: Path):
    """CODE lines (without line comments): a comment mentioning `closeSSE` and explaining why it is no longer
    called must not make the test fail — otherwise documenting the fix would break it."""
    for raw in _txt(p).splitlines():
        s = raw.strip()
        if s and not s.startswith("//"):
            yield s


def test_the_app_opens_the_event_stream_at_boot():
    """`main.js` (app startup), not the voice session, is what opens the channel."""
    code = list(_code_lines(MAIN))
    assert any("openSSE(" in l for l in code), "main.js debe abrir el stream de /events en el arranque"
    assert any(re.search(r"import\s*\{[^}]*\bopenSSE\b", l) for l in code), "…y por tanto importarlo"


def test_opening_the_stream_twice_does_not_kill_the_live_one():
    """`session.start()` still calls `openSSE` (it is a free retry if startup failed). If that second
    call CLOSED and reopened it, it would kill the live stream and in-flight events would be lost."""
    body = _txt(SSE)
    m = re.search(r"export function openSSE\([^)]*\)\s*\{(.*?)\n\}", body, re.S)
    assert m, "no encuentro openSSE en sse.js"
    head = m.group(1).strip().splitlines()[0]
    assert "return" in head and "es.close" not in head, (
        "openSSE debe ser IDEMPOTENTE (salir si ya hay stream), no cerrar y reabrir: " + head)


@pytest.mark.parametrize("path", SESSIONS, ids=lambda p: p.name)
def test_stopping_the_voice_does_not_close_the_event_stream(path):
    """The case that froze the screen. Stopping voice (or having it fail because there is no microphone) must NOT cut off widget
    events: this is the channel through which the operator sees results arrive."""
    assert not any("closeSSE(" in l for l in _code_lines(path)), (
        f"{path.name} vuelve a cerrar el stream de /events al parar la voz — la pantalla se queda congelada "
        "(un worker puede seguir empujando resultados y no se verán)")


# ── NEW SESSION on reset (2026-08-10) ────────────────────────────────────────────────────────────────────────
# The backend rotates the id and resets its observability (voice/observer.py::rotate_session), but the observability
# column renders its rows MANUALLY (it does not re-render from data), so it must be notified or it keeps showing
# the history of a session that no longer exists. `clearDebugBuffer()` —which the reset already called— empties the RING, not
# the DOM: it was exactly half the job.
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


# ── NEWEST AT THE TOP, AND SCROLL BELONGS TO THE OPERATOR (2026-08-10) ──────────────────────────────────────
# History: the column “followed” the latest event by pinning the bottom, and the operator reported that after 10–15 messages
# it stopped following without them touching anything. It was hardened twice (an rAF guard that hung with the background
# tab, `stick` that any scroll—including ours—would release), and even then the state could still lie.
#
# The operator proposed removing the problem instead of hardening it: **the list grows UPWARD**. The newest item is attached
# to the header, so there is nothing to chase; scrolling becomes 100% manual. This removed ALL the machinery
# (following, gestures, rAF, indicator, and its two i18n keys) — these tests prevent it from returning.
def test_the_newest_event_goes_on_top():
    """Insertion at the top IS the mechanism: if someone uses `appendChild` on the list again, the column will once more
    need someone to chase the bottom."""
    code = list(_code_lines(DEBUG_PANEL))
    assert any("insertBefore" in l and "firstChild" in l for l in code), \
        "las filas entran por ARRIBA (prepend), no por el final"
    assert not any("listEl.appendChild" in l for l in code), \
        "una fila añadida al final resucita el problema del seguimiento"
    # MAX_ROWS trimming must remove the OLD rows, which are now at the end
    assert any("lastElementChild" in l for l in code), "el recorte debe podar por el final (las más viejas)"


def test_no_scroll_following_machinery_comes_back():
    """No following state: neither the flag, nor the indicator, nor the gestures, nor the rAF that used to hang. Invisible
    state that can lie about what you are seeing does not return to this panel."""
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
    """Growing upward shifts the content below. It is compensated manually —and browser anchoring is disabled— so
    what the operator has beneath their eyes does not move, and so behavior is the SAME in Safari
    (which does not implement scroll anchoring) as in Chrome (where its adjustment would be added to ours)."""
    body = DEBUG_PANEL.read_text(encoding="utf-8")
    assert "el.scrollTop +=" in body, "sin compensar, cada evento le empuja el texto al operador"
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert "overflow-anchor:none" in css.replace(" ", ""), \
        "con el anclaje del navegador activo la compensación se aplicaría DOS veces"


def test_the_filter_config_survives_a_reload():
    """The key that was written (`hb_dbg_kinds_off`) was not the one that was read (`…_v2`): the operator’s filter configuration
    was lost on every reload and the default values were re-applied as if it were the first time."""
    body = DEBUG_PANEL.read_text(encoding="utf-8")
    claves = set(re.findall(r"hb_dbg_kinds_off\w*", body))
    assert claves == {"hb_dbg_kinds_off_v2"}, f"la clave de lectura y la de escritura deben ser UNA: {claves}"
