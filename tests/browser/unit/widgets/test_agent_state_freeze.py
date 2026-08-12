#
# EL ESTADO DEL AGENTE ES UNA SOLA VERDAD, Y «PARADO» SIGNIFICA CONGELADO — de verdad y a la vista.
#
# FALLO REAL, y caro (sesión del operador, 2026-08-10, con captura). Estuvo un buen rato hablándole a un agente
# muerto, y lo contó así:
#
#   «Como yo veía el micrófono encendido, el del altavoz encendido y el de la transcripción encendida, pensaba que
#    estabas operativo. Además, en la observabilidad se veía cómo el micrófono estaba captando sonido. Claro, cuando
#    el agente está parado, el micrófono está parado.»
#   «Fíjate que está el ECG a tope y el agente debería estar completamente parado.»
#
# No era un fallo de audio: era un ESTADO INVISIBLE. Cada icono decidía su aspecto a partir de una señal distinta y
# ninguna significaba «el agente funciona»: `powerOff` es la INTENCIÓN persistida y `started` es la realidad, que no
# la miraba nadie para pintar. Con `powerOff=false` y la sesión caída, todo seguía azul. Y lo que más dice «estoy
# vivo» de toda la pantalla —el electrocardiograma— late con el pulso del SERVIDOR, que sigue latiendo con la voz
# apagada.
#
# Se prueba por TEXTO porque este repo no ejecuta JS en los tests (módulos ES sin build). Aserciones groseras a
# propósito: cazan la regresión típica (volver a pintar desde `powerOff` en vez de desde la realidad) sin fingir que
# entienden el JS. El comportamiento se verificó además en vivo con Playwright.
#
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
STORE = APP / "core" / "store.js"
ORB = APP / "components" / "Orb.js"
ECG = APP / "lib" / "ecg.js"
VIZ = APP / "services" / "visualizer.js"
DOM = APP / "core" / "dom.js"


def _code(p: Path) -> list[str]:
    """Líneas de CÓDIGO (sin comentarios de línea): un comentario que explica el arreglo no puede aprobar el test
    ni romperlo."""
    return [s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
            if s and not s.startswith("//")]


# ── 1) la fuente de verdad ────────────────────────────────────────────────────────────────────────────────────
def test_there_is_one_derived_answer_to_is_the_agent_alive():
    code = _code(STORE)
    assert any("agentState" in l for l in code), "el estado del agente tiene que existir como UNA respuesta"
    assert any("agentLive" in l for l in code), "…y un predicado único para las vistas"


def test_the_state_includes_should_be_on_but_isnt():
    """`stalled` es el estado que NO existía y el que causó el daño. Sin él, un agente caído se ve idéntico a uno
    funcionando."""
    body = STORE.read_text(encoding="utf-8")
    assert '"stalled"' in body
    for other in ('"off"', '"live"', '"starting"'):
        assert other in body


def test_intent_alone_never_decides_whether_the_agent_is_alive():
    """`powerOff` es lo que el operador PIDIÓ, no lo que está pasando. `agentState` tiene que consultar la realidad
    (`started`), o volvemos al fallo."""
    body = STORE.read_text(encoding="utf-8")
    i = body.index("export const agentState")
    fn = body[i:i + 900]
    assert "started()" in fn, "sin mirar `started` esto vuelve a pintar la intención"


# ── 2) todo lo que se ve deriva de esa verdad ─────────────────────────────────────────────────────────────────
def test_the_icon_crown_dims_from_reality_not_from_the_persisted_flag():
    body = ORB.read_text(encoding="utf-8")
    i = body.index("const lidClass")
    line = body[i:body.index("\n", i + 40)]
    assert "agentLive()" in line, f"lidClass debe derivar de la realidad, y dice: {line}"
    assert "powerOff()" not in line, "volver a `powerOff` reabre el fallo (sesión caída = iconos azules)"


def test_the_power_icon_shows_the_four_real_states():
    code = _code(ORB)
    assert any("agentState()" in l and "pwr-" in l for l in code), \
        "el ⏻ es el icono que se mira para saber si hay alguien al otro lado: no puede pintar un flag"


def test_every_agent_state_has_a_title_in_both_bundles():
    """Un icono en ámbar sin explicación no sirve de nada: el operador tiene que poder leer QUÉ pasa."""
    import json
    for lang in ("en", "es"):
        b = json.loads((ENGINE / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        for st in ("off", "live", "starting", "stalled"):
            k = f"orb.power_{st}"
            assert k in b and b[k].strip(), f"falta {k} en {lang}"


# ── 3) parado = CONGELADO, no «parado pero moviéndose» ────────────────────────────────────────────────────────
def test_the_heartbeat_goes_flat_when_the_agent_is_not_alive():
    """El pulso que llega es del SERVIDOR y el servidor sigue latiendo con la voz apagada. Un ECG a tope sobre un
    agente detenido es la señal más engañosa de la pantalla."""
    code = _code(ECG)
    assert any("agentLive()" in l for l in code), "el ECG debe consultar si el agente vive antes de latir"


def test_the_mic_meter_stops_writing_when_the_agent_is_not_alive():
    """El analizador SOBREVIVE a `stop()` (nadie llama a `audio.reset()`), así que el medidor seguía publicando
    nivel con el agente parado — y el operador lo veía «captando sonido» en observabilidad."""
    code = _code(VIZ)
    assert any("agentLive()" in l for l in code)
    assert any("setMicLevel(0)" in l for l in code), "al parar hay que dejar el nivel en 0, no en el último valor"


def test_stopping_retires_the_mic_blocked_ring_instead_of_freezing_it():
    body = VIZ.read_text(encoding="utf-8")
    assert 'setMicBlocked({ show: false' in body, \
        "parado no es «bloqueado»: el 🚫 se retira, no se queda clavado con el último valor"


def test_the_orb_itself_freezes():
    """El orbe es lo que más personifica a zaelar; verlo ondular con el agente parado dice «estoy aquí»."""
    assert any("frozen" in l for l in _code(ORB))
    assert "canvas#orb.frozen" in (APP / "styles.css").read_text(encoding="utf-8")


# ── 4) el vúmetro que pidió el operador ───────────────────────────────────────────────────────────────────────
def test_the_mic_icon_is_a_level_meter_while_listening():
    """«Quiero estar seguro de que me estás escuchando cuando hablo… que el icono del micrófono hiciera blinking,
    incluso se hiciera un poquito más grande y más pequeño a medida que detecta la voz.»"""
    code = _code(ORB)
    assert any("--vu" in l for l in code), "el nivel real tiene que llegar al icono"
    assert any("micLevel()" in l for l in code)
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert ".orbic.vu" in css and "var(--vu" in css


def test_the_meter_cannot_move_when_nobody_is_listening():
    """Un medidor que se mueve con el micro silenciado o el agente parado sería la misma mentira, más fina."""
    body = ORB.read_text(encoding="utf-8")
    i = body.index('"--vu"')
    expr = body[i:body.index("\n", i)]
    assert "agentLive()" in expr and "micMuted()" in expr, f"el vúmetro debe estar acotado: {expr}"


def test_custom_properties_actually_reach_the_dom():
    """`el.style["--x"] = v` NO hace nada, en silencio: hay que pasar por setProperty. Sin esto el vúmetro sería
    código muerto que parece correcto."""
    body = DOM.read_text(encoding="utf-8")
    assert "setProperty" in body and 'startsWith("--")' in body


# ── 5) lo que NO debe cambiar ─────────────────────────────────────────────────────────────────────────────────
def test_the_power_button_remains_clickable_in_every_state():
    """Congelar es VISUAL. Si el ⏻ se deshabilitara al caerse la sesión, el operador se quedaría sin poder
    rearrancarla — encerrado por el propio aviso."""
    body = ORB.read_text(encoding="utf-8")
    i = body.index("pwr-")
    block = body[i - 400:i + 1200]
    assert "disabled" not in block


@pytest.mark.parametrize("signal", ["micMuted", "botMuted", "captionsOn", "chatOpen"])
def test_each_control_keeps_its_own_state_underneath(signal):
    """El apagón es una CAPA encima: al volver la corriente, cada control vuelve a mostrar lo que era. Si alguien
    «arreglara» esto forzando los signals a false, el operador perdería sus preferencias en cada parada."""
    assert any(signal in l for l in _code(ORB)), f"{signal} sigue siendo el estado real del control"


# ── 6) …Y ADEMÁS SE REGISTRA: el estado del cliente entra en el log (2026-08-10) ───────────────────────────────
# Verlo en pantalla arregla al operador delante del ordenador. Pero el diagnóstico A POSTERIORI seguía ciego: en el
# log solo estaba la INTENCIÓN (`orb:power` al pulsar ⏻), nunca la REALIDAD. Un agente caído que se pinta vivo, un
# altavoz zombi o un micro que no se libera no dejaban ni una línea. Ahora las TRANSICIONES del cliente van por el
# canal que ya existía (`api.uiState` → `/api/ui-event`, `src="frontend"`).
#
# Regla que estos tests protegen: son eventos de ESTADO, no de actividad — solo en transición, nunca en un bucle de
# render. De ahí el guarda contra re-emisión con el mismo valor.
MAIN = APP / "main.js"
AUDIO = APP / "services" / "audio.js"
API = APP / "services" / "api.js"
SESSIONS_STOP = [APP / "services" / "session-lk.js",   # el que SIRVE el motor LiveKit (el que corre hoy)
                 APP / "services" / "session.js"]      # el de Pipecat (mismo contrato, no puede divergir)
VOICE_API = ENGINE / "server" / "voice_api.py"


def test_the_client_has_its_own_door_for_state():
    """`src="frontend"` separa «lo que hizo el operador» de «lo que le pasó al cliente». Sin esa distinción, un
    `agent:state stalled` se leería como una acción del operador, que es lo contrario de lo que dice."""
    assert any('uiState' in l and '"frontend"' in l for l in _code(API)), \
        "api.uiState debe estampar src=frontend"
    body = VOICE_API.read_text(encoding="utf-8")
    assert '"frontend"' in body, "el endpoint debe admitir src=frontend"


def test_every_agent_state_transition_is_logged_once():
    code = _code(MAIN)
    assert any('uiState("agent:state"' in l for l in code), "falta el evento de estado del agente"
    assert any("agentState()" in l for l in code), "…derivado de la verdad única, no de powerOff"
    assert any('prev' in l and 'uiState("agent:state"' in l for l in code), \
        "sin `prev` no se distingue «se ha caído» (live→stalled) de «no llegó a subir» (starting→stalled)"
    body = MAIN.read_text(encoding="utf-8")
    assert "_prevAgentState) return" in body, (
        "un efecto sobre una señal DERIVADA se re-ejecuta con el mismo valor: sin guarda esto pasa de ser un evento "
        "de estado a ser ruido de render")


def test_releasing_the_audio_graph_leaves_a_trace():
    """El attach de la pista del bot ya se veía (🔈 TrackSubscribed); el RELEASE no, así que un altavoz zombi era
    indetectable. Y del micro solo se veía apagarse el icono."""
    code = _code(AUDIO)
    assert any('uiState("mic:analyser"' in l and '"open"' in l for l in code)
    assert any('uiState("mic:analyser"' in l and '"closed"' in l for l in code)
    assert any('uiState("audio:out"' in l and '"attached"' in l for l in code)
    assert any('uiState("audio:out"' in l and '"released"' in l for l in code)
    assert any("reason" in l for l in code), "un cierre sin motivo no se puede interpretar"


@pytest.mark.parametrize("path", SESSIONS_STOP, ids=lambda p: p.name)
def test_stopping_really_releases_the_audio_graph(path):
    """El evento tiene que poder AFIRMAR algo. `stop()` soltaba solo el analizador del bot: el del micro y su
    AudioContext sobrevivían, así que «cerrado» nunca habría ocurrido y el log habría dicho la verdad a medias.
    Cerrar el grafo entero también mata una fuga real (Chrome corta a ~6 AudioContext por página: unas cuantas
    reconexiones y `new AudioContext()` empieza a lanzar)."""
    code = _code(path)
    assert any("audio.reset(" in l for l in code), f"{path.name} debe soltar el grafo de audio al parar"
    assert not any("audio.dropBot()" in l for l in code), \
        f"{path.name} suelta solo el bot: el analizador de micro sobreviviría a stop()"


def test_a_background_tab_is_distinguishable_from_a_freeze():
    """`requestAnimationFrame` no corre en segundo plano y de él dependen el visualizador y varios guardas. Sin esta
    línea, «se congeló» y «estabas en otra aplicación» son la misma foto en el log."""
    code = _code(MAIN)
    assert any('uiState("tab:visibility"' in l for l in code)
    assert any("visibilitychange" in l for l in code)


def test_the_endpoint_forwards_what_makes_a_transition_readable():
    """Los campos que no están en la lista se DESCARTAN en silencio: un evento con `prev`/`reason`/`cause` que el
    server tira es peor que no tenerlo, porque parece instrumentado."""
    body = VOICE_API.read_text(encoding="utf-8")
    i = body.index('@router.post("/api/ui-event")')
    block = body[i:i + 2200]
    for k in ("prev", "reason", "cause", "state"):
        assert f'"{k}"' in block, f"el endpoint descarta `{k}`"


# ── 6) UN RESET DEJA EL SISTEMA LISTO — no `stalled` esperando un clic ────────────────────────────────────────
# Misma familia que todo lo de arriba, medido en vivo el 2026-08-12: el operador apretó Reset a las 13:21:46 «para
# que se pare todo y podamos empezar de cero» y la voz no volvió hasta las 13:22:49 — **61 segundos** con el ⏻
# parpadeando en ámbar. No era un arranque lento: no había arranque. `resetFull()`/`resetHard()` llamaban a `stop()`
# y NADIE levantaba la sesión; el único que re-arma es `ensureVoice()` de main.js, que corre al cargar la página y en
# cada `pointerdown` — y el clic que dispara el reset llega ANTES del `stop()`, así que ese re-armado se pierde. La
# voz esperaba el SIGUIENTE clic. El estado ámbar era HONESTO (`stalled` = debería estar arriba y no lo está); lo que
# estaba roto era que un reset dejase el sistema así.
SESSION_LK = APP / "services" / "session-lk.js"


def _reset_paths() -> str:
    """Los dos caminos de reset del cliente LiveKit (el módulo que se sirve DE VERDAD: el server lo publica en la
    URL de session.js — ver server/livekit_api.py)."""
    body = SESSION_LK.read_text(encoding="utf-8")
    return body[body.index("export async function resetHard()"):body.index("export function toggle()")]


def test_a_reset_brings_the_voice_back_by_itself():
    block = _reset_paths()
    assert block.count("_rearmVoiceAfterReset()") >= 2, \
        "los DOS caminos de reset (resetHard y el resetFull sin borrados) tienen que re-armar la voz"


def test_the_rearm_obeys_an_explicit_power_off():
    """El ⏻ apagado es una orden del operador, persistida. Un reset no puede desobedecerla encendiendo la voz."""
    body = SESSION_LK.read_text(encoding="utf-8")
    fn = body[body.index("async function _rearmVoiceAfterReset()"):]
    fn = fn[:fn.index("\n}")]
    assert "store.powerOff()" in fn and "return" in fn
    assert "start()" in fn


def test_the_rearm_does_not_fight_the_server_restart():
    """Con borrado de memoria/credenciales el server SE REINICIA: ahí no hay sesión a la que volver y quien manda es
    el overlay + la recarga de la página. Re-armar la voz en ese camino sería pelearse con el reinicio."""
    body = SESSION_LK.read_text(encoding="utf-8")
    full = body[body.index("export async function resetFull("):body.index("export function toggle()")]
    restarting = full[full.index("store.setRestarting(true)"):]
    assert "_rearmVoiceAfterReset" not in restarting
    assert "location.reload()" in restarting
