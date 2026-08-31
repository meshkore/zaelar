#
# test_producers.py — the widget production CONTRACT (V2-092).
#
# It stems from a real failure reported by the operator (2026-08-13) with the agent STOPPED: a YouTube video
# kept playing, restarted on its own when the page was reloaded, and also played at the same time as the music
# player. What was missing was not an `if` for YouTube: it was a contract that any widget—including those the agent
# GENERATES tomorrow—can declare, so global stopping and speaker exclusivity come for free.
#
# The THREE capabilities that contract must provide are tested, plus a fourth that prevents regressions:
# the catalog's REAL manifests must declare it correctly (a contract nobody declares protects against nothing).
#
# Run: .venv/bin/pytest tests/browser/unit/widgets/test_producers.py
#
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from widgets import producers

ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── contract reading ───────────────────────────────────────────────────────────────────────────────────────
def test_spec_normaliza_el_manifest():
    sp = producers.spec({"id": "w", "runtime": {"output": "audio", "produce": ["play", "load"],
                                               "suspend": "pause", "active_when": {"paused": False}}})
    assert sp["id"] == "w"
    assert sp["output"] == "audio"
    assert sp["produce"] == {"play", "load"}          # set: the real question is «does it belong?»
    assert sp["suspend"] == "pause"
    assert sp["active_when"] == [{"paused": False}]   # a standalone dict is a list containing one condition


def test_sin_runtime_no_hay_contrato():
    assert producers.spec({"id": "w"}) is None
    assert producers.spec({"id": "w", "runtime": "audio"}) is None      # malformed, does not crash


def test_runtime_sin_suspend_se_descarta():
    """A widget that declares that it produces but not HOW it stops is worse than one that declares nothing: it would
    enter the global-stop inventory and keep playing while the system believed it had shut it down."""
    assert producers.spec({"id": "w", "runtime": {"output": "audio", "produce": ["play"]}}) is None


def test_produce_admite_un_solo_string():
    sp = producers.spec({"id": "w", "runtime": {"produce": "play", "suspend": "pause"}})
    assert sp["produce"] == {"play"}


# ── is it producing? (PURE function: it decides whom to silence) ────────────────────────────────────────────
def _sp(active_when, **kw):
    return producers.spec({"id": "w", "runtime": {"suspend": "pause", "active_when": active_when, **kw}})


def test_is_producing_verdad_no_identidad():
    """`{"paused": false}` means «the field is falsy», not «it is exactly False»: a widget writes `0`, `""`, or
    does not write the field at all, and all three things mean the same."""
    sp = _sp({"videoId": True, "paused": False})
    assert producers.is_producing({"videoId": "abc", "paused": False}, sp) is True
    assert producers.is_producing({"videoId": "abc"}, sp) is True            # absent = falsy
    assert producers.is_producing({"videoId": "abc", "paused": 0}, sp) is True
    assert producers.is_producing({"videoId": "abc", "paused": True}, sp) is False
    assert producers.is_producing({"videoId": "", "paused": False}, sp) is False   # no video means nothing plays


def test_is_producing_ruta_con_puntos():
    sp = _sp({"yt.videoId": True, "yt.paused": False})
    assert producers.is_producing({"yt": {"videoId": "x"}}, sp) is True
    assert producers.is_producing({"yt": {"videoId": "x", "paused": True}}, sp) is False
    assert producers.is_producing({"yt": None}, sp) is False                 # missing branch = does not produce


def test_is_producing_varias_vias_es_un_O():
    """Music can play through Spotify (remote device) or YouTube-audio (hidden iframe). They are two distinct states
    and one is enough: with `active_when` as a single AND, half the cases went uncovered."""
    sp = _sp([{"yt.videoId": True, "yt.paused": False}, {"now_playing.playing": True}])
    assert producers.is_producing({"yt": {"videoId": "x"}}, sp) is True
    assert producers.is_producing({"now_playing": {"playing": True}}, sp) is True
    assert producers.is_producing({"yt": {}, "now_playing": {"playing": False}}, sp) is False


def test_is_producing_igualdad_de_texto():
    sp = _sp({"mode": "youtube"})
    assert producers.is_producing({"mode": "youtube"}, sp) is True
    assert producers.is_producing({"mode": "idle"}, sp) is False


def test_sin_active_when_no_produce_nunca():
    """Guessing would suspend things that were not playing. Whoever wants to enter global stopping must say how it
    is checked."""
    assert producers.is_producing({"paused": False}, _sp({})) is False


def test_view_data_degradado_no_produce():
    """A widget that returns `{"error": …}` cannot even read itself: sending it commands fixes nothing."""
    sp = _sp({"paused": False})
    assert producers.is_producing({"error": "timed out", "paused": False}, sp) is False


# ── the GATE: with the agent stopped, nothing starts producing ───────────────────────────────────────────────
@pytest.fixture
def catalogo(monkeypatch):
    """Synthetic catalog of two widgets on the SAME channel (the speaker) + one that does not produce."""
    man = [
        {"id": "vid", "runtime": {"output": "audio", "produce": ["play", "load"], "suspend": "pause",
                                  "active_when": {"paused": False}}},
        {"id": "mus", "runtime": {"output": "audio", "produce": ["play"], "suspend": "pause",
                                  "active_when": {"paused": False}}},
        {"id": "reloj"},
    ]
    monkeypatch.setattr(producers.runtime, "catalog", lambda: man)
    monkeypatch.setattr(producers.runtime, "get", lambda wid: next((w for w in man if w["id"] == wid), None))
    return man


def test_gate_bloquea_solo_lo_que_produce(catalogo, monkeypatch):
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    denied = producers.gate("vid", "play")
    assert denied and denied["error"] == "agent_stopped"
    assert "⏻" in denied["message"]                       # the message says HOW to leave the state, not merely that it cannot
    # Stopping the agent does NOT freeze the interface: navigating the card, changing views, or lowering the volume still work.
    assert producers.gate("vid", "pause") is None
    assert producers.gate("vid", "volume_down") is None
    assert producers.gate("reloj", "cualquiera") is None   # a widget without a contract is never gated


def test_gate_no_estorba_con_el_agente_en_marcha(catalogo, monkeypatch):
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    assert producers.gate("vid", "play") is None


def test_starts_production_es_declarado(catalogo):
    assert producers.starts_production("vid", "load") is True
    assert producers.starts_production("vid", "mute") is False


# ── global stopping and channel exclusivity ─────────────────────────────────────────────────────────────────
class _Bus:
    """Replaces producers' two I/O seams: reading a widget's state and sending it an action."""

    def __init__(self, playing: set[str]):
        self.playing = set(playing)
        self.sent: list[tuple[str, str]] = []

    async def view(self, wid):
        return {"paused": wid not in self.playing}

    async def dispatch(self, wid, action, payload):
        self.sent.append((wid, action))
        if action == "pause":
            self.playing.discard(wid)
        return {"ok": True}


@pytest.fixture
def bus(catalogo, monkeypatch):
    b = _Bus(playing={"vid", "mus"})
    monkeypatch.setattr(producers, "_view_data", b.view)
    import widgets.server_api as sapi
    monkeypatch.setattr(sapi, "dispatch_raw", b.dispatch)
    return b


def test_producing_lista_solo_a_los_que_suenan(bus):
    bus.playing = {"mus"}
    assert asyncio.run(producers.producing()) == ["mus"]


def test_suspend_all_para_a_todos_por_su_accion_declarada(bus):
    got = asyncio.run(producers.suspend_all(reason="agent_stopped"))
    assert sorted(got) == ["mus", "vid"]
    assert sorted(bus.sent) == [("mus", "pause"), ("vid", "pause")]
    assert not bus.playing


def test_suspend_all_no_toca_a_quien_no_suena(bus):
    bus.playing = set()
    assert asyncio.run(producers.suspend_all()) == []
    assert bus.sent == []                                  # not even one extra command to an idle widget


def test_exclusividad_el_ultimo_en_sonar_calla_al_otro(bus):
    """The failure exactly as the operator saw it: music and video playing at once. There is ONE speaker."""
    callados = asyncio.run(producers.enforce_exclusive("vid", "play"))
    assert callados == ["mus"]
    assert bus.playing == {"vid"}                          # the one that took the channel keeps playing


def test_exclusividad_no_se_aplica_a_una_accion_que_no_produce(bus):
    assert asyncio.run(producers.enforce_exclusive("vid", "mute")) == []
    assert bus.sent == []


def test_sin_canal_no_hay_exclusividad(monkeypatch):
    """A widget can produce WITHOUT competing (a process, a recording): declaring production does not impose
    exclusivity by accident."""
    man = [{"id": "grab", "runtime": {"produce": ["start"], "suspend": "stop", "active_when": {"on": True}}}]
    monkeypatch.setattr(producers.runtime, "catalog", lambda: man)
    monkeypatch.setattr(producers.runtime, "get", lambda wid: man[0] if wid == "grab" else None)
    assert asyncio.run(producers.enforce_exclusive("grab", "start")) == []


def test_un_widget_roto_no_tumba_la_parada_global(catalogo, monkeypatch):
    """A partial stop is worse than none: the operator thinks it stopped and something keeps playing. If a widget
    crashes when queried, it is treated as stopped and the OTHERS are stopped anyway."""
    async def view(wid):
        if wid == "vid":
            raise RuntimeError("data.py roto")
        return {"paused": False}
    sent = []
    async def dispatch(wid, action, payload):
        sent.append((wid, action))
        return {"ok": True}
    monkeypatch.setattr(producers, "_view_data", view)
    import widgets.server_api as sapi
    monkeypatch.setattr(sapi, "dispatch_raw", dispatch)
    assert asyncio.run(producers.suspend_all()) == ["mus"]
    assert sent == [("mus", "pause")]


def test_una_suspension_rechazada_no_se_cuenta_como_hecha(bus, monkeypatch):
    async def dispatch(wid, action, payload):
        return {"ok": False, "error": "no se pudo"}
    import widgets.server_api as sapi
    monkeypatch.setattr(sapi, "dispatch_raw", dispatch)
    assert asyncio.run(producers.suspend_all()) == []      # what is reported to the operator are FACTS


# ── the FUNNEL: ensure the policy is truly wired into the path used by the UI and the brain ─────────────────
def test_el_embudo_rechaza_sin_llegar_al_widget(catalogo, monkeypatch):
    """The gate acts BEFORE applying the action. Applying it and undoing it afterward would leave a strange trace in
    the store and, for something like `load`, would already have done the network work."""
    import widgets.server_api as sapi
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    llegó = []
    async def raw(wid, action, payload):
        llegó.append((wid, action))
        return {"ok": True}
    monkeypatch.setattr(sapi, "dispatch_raw", raw)
    res = asyncio.run(sapi._dispatch("vid", "play", {}))
    assert res["error"] == "agent_stopped"
    assert llegó == [], "the action must not reach the widget"


def test_el_embudo_aplica_la_exclusividad_despues_de_la_accion(bus, monkeypatch):
    """And in that order: who occupies the channel is read from the REAL state, not from what we thought the action would do."""
    import widgets.server_api as sapi
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    asyncio.run(sapi._dispatch("vid", "play", {}))
    assert ("mus", "pause") in bus.sent                    # the other owner of the speaker is silenced
    assert bus.playing == {"vid"}


def test_una_data_op_normal_no_paga_nada(bus, monkeypatch):
    """Stopping the agent does not freeze the interface, and the policy cannot interfere with the 20 actions that do not produce."""
    import widgets.server_api as sapi
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    res = asyncio.run(sapi._dispatch("vid", "volume_down", {}))
    assert res == {"ok": True} and bus.sent == [("vid", "volume_down")]


# ── the REAL manifests ──────────────────────────────────────────────────────────────────────────────────────
def _manifest(wid):
    return json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("wid", ["youtube", "musica"])
def test_los_widgets_que_suenan_declaran_su_contrato(wid):
    """The two widgets that produce audio TODAY must be in the contract, or the operator's bug returns."""
    man = _manifest(wid)
    sp = producers.spec(man)
    assert sp is not None, f"{wid} debe declarar 'runtime'"
    assert sp["output"] == "audio"
    assert sp["produce"], "debe declarar qué acciones lo ponen a producir"
    assert sp["active_when"], "debe declarar cómo se lee que está produciendo"


@pytest.mark.parametrize("wid", ["youtube", "musica"])
def test_el_contrato_solo_nombra_acciones_QUE_EXISTEN(wid):
    """`suspend` and `produce` must be actions actually declared in the manifest. A typo here
    (`"suspend": "stop"` in a widget that only understands `pause`) would be a stop that stops nothing—and would fail
    silently, at the worst possible moment."""
    man = _manifest(wid)
    declared = set((man.get("actions") or {}).keys())
    sp = producers.spec(man)
    assert sp["suspend"] in declared, f"{wid}: 'suspend' apunta a una acción inexistente"
    assert sp["produce"] <= declared, f"{wid}: 'produce' nombra acciones inexistentes: {sp['produce'] - declared}"
