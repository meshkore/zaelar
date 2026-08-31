#
# THE AGENT STATE IS A SINGLE TRUTH, AND “STOPPED” MEANS FROZEN — both literally and visibly.
#
# A REAL, costly FAILURE (operator session, 2026-08-10, with recording). They spent quite a while talking to a
# dead agent, and described it like this:
#
#   “Because I could see the microphone on, the speaker on, and the transcription on, I thought you were operational.
#    Also, observability showed the microphone capturing sound. Of course, when the agent is stopped, the microphone
#    is stopped.”
#   “Notice that the ECG is going full blast and the agent should be completely stopped.”
#
# It was not an audio failure: it was an INVISIBLE STATE. Each icon decided its appearance from a different signal,
# none meant “the agent is working”: `powerOff` is the persisted INTENT and `started` is reality, which nobody
# checked when rendering. With `powerOff=false` and the session down, everything stayed blue. And the thing on the
# entire screen that most says “I’m alive” — the electrocardiogram — beats to the SERVER’S pulse, which keeps beating
# with the voice turned off.
#
# It is tested by TEXT because this repo does not execute JS in tests (ES modules without a build). The deliberately
# crude assertions catch the typical regression (rendering from `powerOff` instead of reality) without pretending to
# understand the JS. The behavior was also verified live with Playwright.
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
    """CODE lines (excluding line comments): a comment explaining the fix cannot make or break the test."""
    return [s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
            if s and not s.startswith("//")]


# ── 1) the source of truth ────────────────────────────────────────────────────────────────────────────────────
def test_there_is_one_derived_answer_to_is_the_agent_alive():
    code = _code(STORE)
    assert any("agentState" in l for l in code), "el estado del agente tiene que existir como UNA respuesta"
    assert any("agentLive" in l for l in code), "…y un predicado único para las vistas"


def test_the_state_includes_should_be_on_but_isnt():
    """`stalled` is the state that did NOT exist and caused the damage. Without it, a down agent looks identical to a
    working one."""
    body = STORE.read_text(encoding="utf-8")
    assert '"stalled"' in body
    for other in ('"off"', '"live"', '"starting"'):
        assert other in body


def test_intent_alone_never_decides_whether_the_agent_is_alive():
    """`powerOff` is what the operator REQUESTED, not what is happening. `agentState` must check reality
    (`started`), or we bring back the failure."""
    body = STORE.read_text(encoding="utf-8")
    i = body.index("export const agentState")
    fn = body[i:i + 900]
    assert "started()" in fn, "sin mirar `started` esto vuelve a pintar la intención"


# ── 2) everything visible derives from that truth ─────────────────────────────────────────────────────────────
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
    """An amber icon without an explanation is useless: the operator must be able to read WHAT is happening."""
    import json
    for lang in ("en", "es"):
        b = json.loads((ENGINE / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        for st in ("off", "live", "starting", "stalled"):
            k = f"orb.power_{st}"
            assert k in b and b[k].strip(), f"falta {k} en {lang}"


# ── 3) stopped = FROZEN, not “stopped but moving” ────────────────────────────────────────────────────────────
def test_the_heartbeat_goes_flat_when_the_agent_is_not_alive():
    """The incoming pulse is from the SERVER, and the server keeps beating with the voice turned off. A full ECG on a
    stopped agent is the most misleading signal on the screen."""
    code = _code(ECG)
    assert any("agentLive()" in l for l in code), "el ECG debe consultar si el agente vive antes de latir"


def test_the_mic_meter_stops_writing_when_the_agent_is_not_alive():
    """The analyzer SURVIVES `stop()` (nobody calls `audio.reset()`), so the meter kept publishing a level with the
    agent stopped — and the operator saw it “capturing sound” in observability."""
    code = _code(VIZ)
    assert any("agentLive()" in l for l in code)
    assert any("setMicLevel(0)" in l for l in code), "al parar hay que dejar el nivel en 0, no en el último valor"


def test_stopping_retires_the_mic_blocked_ring_instead_of_freezing_it():
    body = VIZ.read_text(encoding="utf-8")
    assert 'setMicBlocked({ show: false' in body, \
        "parado no es «bloqueado»: el 🚫 se retira, no se queda clavado con el último valor"


def test_the_orb_itself_freezes():
    """The orb is what most personifies zaelar; seeing it ripple with the agent stopped says “I’m here”."""
    assert any("frozen" in l for l in _code(ORB))
    assert "canvas#orb.frozen" in (APP / "styles.css").read_text(encoding="utf-8")


# ── 4) the level meter the operator requested ─────────────────────────────────────────────────────────────────
def test_the_mic_icon_is_a_level_meter_while_listening():
    """“I want to be sure you’re listening when I speak… I want the microphone icon to blink, even get a little bigger
    and smaller as it detects the voice.”"""
    code = _code(ORB)
    assert any("--vu" in l for l in code), "el nivel real tiene que llegar al icono"
    assert any("micLevel()" in l for l in code)
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert ".orbic.vu" in css and "var(--vu" in css


def test_the_meter_cannot_move_when_nobody_is_listening():
    """A meter that moves with the microphone muted or the agent stopped would be the same lie, just subtler."""
    body = ORB.read_text(encoding="utf-8")
    i = body.index('"--vu"')
    expr = body[i:body.index("\n", i)]
    assert "agentLive()" in expr and "micMuted()" in expr, f"el vúmetro debe estar acotado: {expr}"


def test_custom_properties_actually_reach_the_dom():
    """`el.style["--x"] = v` does NOTHING, silently: it must go through setProperty. Without this, the level meter
    would be dead code that looks correct."""
    body = DOM.read_text(encoding="utf-8")
    assert "setProperty" in body and 'startsWith("--")' in body


# ── 5) what must NOT change ───────────────────────────────────────────────────────────────────────────────────
def test_the_power_button_remains_clickable_in_every_state():
    """Freezing is VISUAL. If ⏻ were disabled when the session went down, the operator would be unable to restart it
    — trapped by the warning itself."""
    body = ORB.read_text(encoding="utf-8")
    i = body.index("pwr-")
    block = body[i - 400:i + 1200]
    assert "disabled" not in block


@pytest.mark.parametrize("signal", ["micMuted", "botMuted", "captionsOn", "chatOpen"])
def test_each_control_keeps_its_own_state_underneath(signal):
    """The shutdown is a LAYER on top: when power returns, each control shows what it was again. If someone “fixed”
    this by forcing the signals to false, the operator would lose their preferences every time it stopped."""
    assert any(signal in l for l in _code(ORB)), f"{signal} sigue siendo el estado real del control"


# ── 6) …AND IT IS ALSO LOGGED: the client state enters the log (2026-08-10) ─────────────────────────────────────
# Seeing it on screen fixes the operator’s situation in front of the computer. But the AFTER-THE-FACT diagnosis was
# still blind: the
# log only contained INTENT (`orb:power` when pressing ⏻), never REALITY. A down agent rendered as alive, a
# zombie speaker, or a microphone that is not released left not even one line. Now client TRANSITIONS use the channel
# that already existed (`api.uiState` → `/api/ui-event`, `src="frontend"`).
#
# Rule protected by these tests: these are STATE events, not activity events — only on transition, never in a render
# loop. Hence the guard against re-emission with the same value.
MAIN = APP / "main.js"
AUDIO = APP / "services" / "audio.js"
API = APP / "services" / "api.js"
SESSIONS_STOP = [APP / "services" / "session-lk.js",   # the one that SERVES the LiveKit engine (the one running today)
                 APP / "services" / "session.js"]      # the Pipecat one (same contract, cannot diverge)
VOICE_API = ENGINE / "server" / "voice_api.py"


def test_the_client_has_its_own_door_for_state():
    """`src="frontend"` separates “what the operator did” from “what happened to the client”. Without that
    distinction, `agent:state stalled` would be read as an operator action, which is the opposite of what it says."""
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
    """The bot track attach was already visible (🔈 TrackSubscribed); RELEASE was not, so a zombie speaker was
    undetectable. For the microphone, only the icon turning off was visible."""
    code = _code(AUDIO)
    assert any('uiState("mic:analyser"' in l and '"open"' in l for l in code)
    assert any('uiState("mic:analyser"' in l and '"closed"' in l for l in code)
    assert any('uiState("audio:out"' in l and '"attached"' in l for l in code)
    assert any('uiState("audio:out"' in l and '"released"' in l for l in code)
    assert any("reason" in l for l in code), "un cierre sin motivo no se puede interpretar"


@pytest.mark.parametrize("path", SESSIONS_STOP, ids=lambda p: p.name)
def test_stopping_really_releases_the_audio_graph(path):
    """The event must be able to ASSERT something. `stop()` released only the bot analyzer: the microphone analyzer
    and its AudioContext survived, so “closed” would never have occurred and the log would have told half the truth.
    Closing the entire graph also kills a real leak (Chrome cuts off at ~6 AudioContexts per page: after a few
    reconnections, `new AudioContext()` starts throwing)."""
    code = _code(path)
    assert any("audio.reset(" in l for l in code), f"{path.name} debe soltar el grafo de audio al parar"
    assert not any("audio.dropBot()" in l for l in code), \
        f"{path.name} suelta solo el bot: el analizador de micro sobreviviría a stop()"


def test_a_background_tab_is_distinguishable_from_a_freeze():
    """`requestAnimationFrame` does not run in the background, and the visualizer and several guards depend on it.
    Without this line, “it froze” and “you were in another application” are the same snapshot in the log."""
    code = _code(MAIN)
    assert any('uiState("tab:visibility"' in l for l in code)
    assert any("visibilitychange" in l for l in code)


def test_the_endpoint_forwards_what_makes_a_transition_readable():
    """Fields not in the list are DISCARDED silently: an event with `prev`/`reason`/`cause` that the server throws
    away is worse than not having it, because it looks instrumented."""
    body = VOICE_API.read_text(encoding="utf-8")
    i = body.index('@router.post("/api/ui-event")')
    block = body[i:i + 2200]
    for k in ("prev", "reason", "cause", "state"):
        assert f'"{k}"' in block, f"el endpoint descarta `{k}`"


# ── 6) A RESET LEAVES THE SYSTEM READY — not `stalled` waiting for a click ────────────────────────────────────
# Same family as everything above, measured live on 2026-08-12: the operator pressed Reset at 13:21:46 “so that
# everything would stop and we could start from scratch”, and the voice did not return until 13:22:49 — **61 seconds**
# with ⏻ blinking amber. It was not a slow startup: there was no startup. `resetFull()`/`resetHard()` called `stop()`
# and NOBODY brought the session back up; the only thing that re-arms it is `ensureVoice()` in main.js, which runs when
# the page loads and on every `pointerdown` — and the click that triggers reset arrives BEFORE `stop()`, so that
# re-arming is lost. The voice waited for the NEXT click. The amber state was HONEST (`stalled` = it should be up and
# is not); what was broken was leaving the system that way after a reset.
SESSION_LK = APP / "services" / "session-lk.js"


def _reset_paths() -> str:
    """The two reset paths for the LiveKit client (the module that is ACTUALLY served: the server publishes it at the
    session.js URL — see server/livekit_api.py)."""
    body = SESSION_LK.read_text(encoding="utf-8")
    return body[body.index("export async function resetHard()"):body.index("export function toggle()")]


def test_a_reset_brings_the_voice_back_by_itself():
    block = _reset_paths()
    assert block.count("_rearmVoiceAfterReset()") >= 2, \
        "los DOS caminos de reset (resetHard y el resetFull sin borrados) tienen que re-armar la voz"


def test_the_rearm_obeys_an_explicit_power_off():
    """Turning ⏻ off is a persisted operator command. A reset cannot disobey it by turning the voice on."""
    body = SESSION_LK.read_text(encoding="utf-8")
    fn = body[body.index("async function _rearmVoiceAfterReset()"):]
    fn = fn[:fn.index("\n}")]
    assert "store.powerOff()" in fn and "return" in fn
    assert "start()" in fn


def test_the_rearm_does_not_fight_the_server_restart():
    """When memory/credentials are deleted, the server RESTARTS: there is no session to return to, and the overlay +
    page reload are in charge. Re-arming the voice on that path would conflict with the restart."""
    body = SESSION_LK.read_text(encoding="utf-8")
    full = body[body.index("export async function resetFull("):body.index("export function toggle()")]
    restarting = full[full.index("store.setRestarting(true)"):]
    assert "_rearmVoiceAfterReset" not in restarting
    assert "location.reload()" in restarting


# ── 7) A STOP WITH A TURN IN FLIGHT DOESN'T LIE BY PAINTING ITSELF ALREADY OFF (V2-092 addenda, 2026-08-15) ─────
# The operator was explicit: if a request to the model is in flight, requesting a stop must WAIT for it to
# finish (never cut it mid-way), and ⏻ has to SHOW IT — amber blink — instead of painting itself off already,
# until the stop completes on its own or the operator cancels it by clicking again. `pausing` is a FIFTH state,
# not a variant of `off`: underneath, the agent keeps genuinely running while it lasts.
SSE = APP / "services" / "sse.js"


def test_pausing_is_a_real_fifth_state_checked_before_off():
    """If checked AFTER `powerOff`, a click that already optimistically set `powerOff=true` would paint "off"
    instead of "pausing" — exactly the visual lie this state exists to avoid."""
    body = STORE.read_text(encoding="utf-8")
    i = body.index("export const agentState")
    fn = body[i:body.index("\n};", i)]
    assert 'pausing()' in fn and '"pausing"' in fn
    assert fn.index("pausing()") < fn.index("powerOff()"), \
        "pausing must be checked BEFORE powerOff, or an optimistic click would hide it"


def test_pausing_has_its_own_signal_not_a_reuse_of_power_off():
    code = _code(STORE)
    assert any("setPausing" in l for l in code), "pausing needs its own signal — it's not a powerOff alias"


def test_pausing_has_a_title_in_every_bundle():
    """Same contract as `test_every_agent_state_has_a_title_in_both_bundles`, extended to the new state — an
    amber icon with no explanation is useless."""
    import json
    for path in (ENGINE / "i18n" / "bundles" / "en.json", ENGINE / "i18n" / "bundles" / "es.json"):
        b = json.loads(path.read_text(encoding="utf-8"))
        assert b.get("orb.power_pausing", "").strip(), f"missing orb.power_pausing in {path.name}"


def test_pausing_looks_different_from_a_real_fault():
    """`stalled` is a FAULT (the agent should be up and isn't); `pausing` is the agent genuinely running while a
    requested stop waits its turn. Painting them the same would confuse "all fine, one moment" with "something
    broke" — the opposite of what this state exists to communicate."""
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert ".orbic.pwr-pausing" in css
    i = css.index(".orbic.pwr-pausing")
    rule = css[i:css.index("}", i) + 1]
    stalled_i = css.index(".orbic.pwr-stalled")
    stalled_rule = css[stalled_i:css.index("}", stalled_i) + 1]
    assert rule != stalled_rule, "pausing can't be a literal copy of the stalled rule"


def test_the_run_sse_event_resolves_pausing_and_resumed_before_falling_back_to_stop_start():
    """Before this change, ANY label that wasn't literally "stop" fell into the "start" branch — with the new
    "pausing"/"resumed" that would have cleared `pausing` on the spot and set `powerOff=false`, losing the
    signal entirely. They have to resolve FIRST, not slip through the usual else."""
    body = SSE.read_text(encoding="utf-8")
    i = body.index('d.kind === "run"')
    block = body[i:body.index('} else if (d.kind === "notify"', i)]
    assert '"pausing"' in block and "setPausing(true)" in block
    assert '"resumed"' in block and "setPausing(false)" in block
    assert block.index('"pausing"') < block.index("setPowerOff"), \
        "pausing/resumed must resolve before the branch that touches powerOff"
