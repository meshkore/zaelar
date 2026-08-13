#
# test_producers.py — el CONTRATO de producción de un widget (V2-092).
#
# Nace de un fallo real reportado por el operador (2026-08-13) con el agente PARADO delante: un vídeo de YouTube
# seguía reproduciéndose, al recargar la página volvía a arrancar solo, y encima sonaba a la vez que el reproductor
# de música. Lo que faltaba no era un `if` para YouTube: era un contrato que cualquier widget —incluidos los que
# GENERA el agente mañana— pueda declarar, para que la parada global y la exclusividad del altavoz salgan gratis.
#
# Se prueban las TRES capacidades que ese contrato tiene que dar, y una cuarta que es la que evita regresiones:
# que los manifests REALES del catálogo la declaren bien (un contrato que nadie declara no protege de nada).
#
# Ejecutar: .venv/bin/pytest tests/browser/unit/widgets/test_producers.py
#
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from widgets import producers

ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── lectura del contrato ────────────────────────────────────────────────────────────────────────────────────
def test_spec_normaliza_el_manifest():
    sp = producers.spec({"id": "w", "runtime": {"output": "audio", "produce": ["play", "load"],
                                               "suspend": "pause", "active_when": {"paused": False}}})
    assert sp["id"] == "w"
    assert sp["output"] == "audio"
    assert sp["produce"] == {"play", "load"}          # set: la pregunta real es «¿pertenece?»
    assert sp["suspend"] == "pause"
    assert sp["active_when"] == [{"paused": False}]   # un dict suelto es una lista de una condición


def test_sin_runtime_no_hay_contrato():
    assert producers.spec({"id": "w"}) is None
    assert producers.spec({"id": "w", "runtime": "audio"}) is None      # malformado, no revienta


def test_runtime_sin_suspend_se_descarta():
    """Un widget que declara que produce pero no CÓMO se para es peor que uno que no declara nada: entraría en el
    inventario de la parada global y se quedaría sonando con el sistema convencido de haberlo apagado."""
    assert producers.spec({"id": "w", "runtime": {"output": "audio", "produce": ["play"]}}) is None


def test_produce_admite_un_solo_string():
    sp = producers.spec({"id": "w", "runtime": {"produce": "play", "suspend": "pause"}})
    assert sp["produce"] == {"play"}


# ── ¿está produciendo? (función PURA: es la que decide a quién se calla) ─────────────────────────────────────
def _sp(active_when, **kw):
    return producers.spec({"id": "w", "runtime": {"suspend": "pause", "active_when": active_when, **kw}})


def test_is_producing_verdad_no_identidad():
    """`{"paused": false}` significa «el campo es falsy», no «es exactamente False»: un widget escribe `0`, `""` o
    directamente no escribe el campo, y las tres cosas significan lo mismo."""
    sp = _sp({"videoId": True, "paused": False})
    assert producers.is_producing({"videoId": "abc", "paused": False}, sp) is True
    assert producers.is_producing({"videoId": "abc"}, sp) is True            # ausente = falsy
    assert producers.is_producing({"videoId": "abc", "paused": 0}, sp) is True
    assert producers.is_producing({"videoId": "abc", "paused": True}, sp) is False
    assert producers.is_producing({"videoId": "", "paused": False}, sp) is False   # sin vídeo no suena nada


def test_is_producing_ruta_con_puntos():
    sp = _sp({"yt.videoId": True, "yt.paused": False})
    assert producers.is_producing({"yt": {"videoId": "x"}}, sp) is True
    assert producers.is_producing({"yt": {"videoId": "x", "paused": True}}, sp) is False
    assert producers.is_producing({"yt": None}, sp) is False                 # rama ausente = no produce


def test_is_producing_varias_vias_es_un_O():
    """La música puede sonar por Spotify (dispositivo remoto) o por YouTube-audio (iframe oculto). Son dos estados
    distintos y basta uno: con `active_when` como Y único, la mitad de los casos quedaba sin cubrir."""
    sp = _sp([{"yt.videoId": True, "yt.paused": False}, {"now_playing.playing": True}])
    assert producers.is_producing({"yt": {"videoId": "x"}}, sp) is True
    assert producers.is_producing({"now_playing": {"playing": True}}, sp) is True
    assert producers.is_producing({"yt": {}, "now_playing": {"playing": False}}, sp) is False


def test_is_producing_igualdad_de_texto():
    sp = _sp({"mode": "youtube"})
    assert producers.is_producing({"mode": "youtube"}, sp) is True
    assert producers.is_producing({"mode": "idle"}, sp) is False


def test_sin_active_when_no_produce_nunca():
    """Adivinar sería suspender cosas que no estaban sonando. Quien quiere entrar en la parada global dice cómo se
    le mira."""
    assert producers.is_producing({"paused": False}, _sp({})) is False


def test_view_data_degradado_no_produce():
    """Un widget que devuelve `{"error": …}` no sabe ni leerse: mandarle comandos no arregla nada."""
    sp = _sp({"paused": False})
    assert producers.is_producing({"error": "timed out", "paused": False}, sp) is False


# ── la PUERTA: con el agente parado nada empieza a producir ─────────────────────────────────────────────────
@pytest.fixture
def catalogo(monkeypatch):
    """Catálogo sintético de dos widgets del MISMO canal (el altavoz) + uno que no produce."""
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
    assert "⏻" in denied["message"]                       # el mensaje dice CÓMO salir del estado, no solo que no
    # Parar el agente NO congela la interfaz: navegar la tarjeta, cambiar de vista o bajar el volumen siguen valiendo.
    assert producers.gate("vid", "pause") is None
    assert producers.gate("vid", "volume_down") is None
    assert producers.gate("reloj", "cualquiera") is None   # un widget sin contrato no se gatea jamás


def test_gate_no_estorba_con_el_agente_en_marcha(catalogo, monkeypatch):
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    assert producers.gate("vid", "play") is None


def test_starts_production_es_declarado(catalogo):
    assert producers.starts_production("vid", "load") is True
    assert producers.starts_production("vid", "mute") is False


# ── parada global y exclusividad de canal ───────────────────────────────────────────────────────────────────
class _Bus:
    """Sustituye las dos costuras de I/O de producers: leer el estado de un widget y mandarle una acción."""

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
    assert bus.sent == []                                  # ni un comando de más a un widget en reposo


def test_exclusividad_el_ultimo_en_sonar_calla_al_otro(bus):
    """El fallo tal cual lo vio el operador: música y vídeo sonando a la vez. El altavoz es UNO."""
    callados = asyncio.run(producers.enforce_exclusive("vid", "play"))
    assert callados == ["mus"]
    assert bus.playing == {"vid"}                          # el que tomó el canal sigue sonando


def test_exclusividad_no_se_aplica_a_una_accion_que_no_produce(bus):
    assert asyncio.run(producers.enforce_exclusive("vid", "mute")) == []
    assert bus.sent == []


def test_sin_canal_no_hay_exclusividad(monkeypatch):
    """Un widget puede producir SIN competir (un proceso, una grabación): declarar producción no impone
    exclusividad por accidente."""
    man = [{"id": "grab", "runtime": {"produce": ["start"], "suspend": "stop", "active_when": {"on": True}}}]
    monkeypatch.setattr(producers.runtime, "catalog", lambda: man)
    monkeypatch.setattr(producers.runtime, "get", lambda wid: man[0] if wid == "grab" else None)
    assert asyncio.run(producers.enforce_exclusive("grab", "start")) == []


def test_un_widget_roto_no_tumba_la_parada_global(catalogo, monkeypatch):
    """Una parada a medias es peor que ninguna: el operador cree que paró y algo sigue sonando. Si un widget
    revienta al ser consultado, se le da por parado y los DEMÁS se paran igual."""
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
    assert asyncio.run(producers.suspend_all()) == []      # lo que se reporta al operador son HECHOS


# ── el EMBUDO: que la política esté de verdad cableada en el camino que usan la UI y el cerebro ──────────────
def test_el_embudo_rechaza_sin_llegar_al_widget(catalogo, monkeypatch):
    """La puerta actúa ANTES de aplicar la acción. Aplicarla y deshacerla después dejaría rastro raro en el store
    y, en algo como `load`, habría hecho ya el trabajo de red."""
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
    assert llegó == [], "la acción no debe llegar al widget"


def test_el_embudo_aplica_la_exclusividad_despues_de_la_accion(bus, monkeypatch):
    """Y en ese orden: quién ocupa el canal se lee del estado REAL, no de lo que creíamos que la acción iba a hacer."""
    import widgets.server_api as sapi
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    asyncio.run(sapi._dispatch("vid", "play", {}))
    assert ("mus", "pause") in bus.sent                    # el otro dueño del altavoz se calla
    assert bus.playing == {"vid"}


def test_una_data_op_normal_no_paga_nada(bus, monkeypatch):
    """Parar el agente no congela la interfaz, y la política no puede estorbar a las 20 acciones que no producen."""
    import widgets.server_api as sapi
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    res = asyncio.run(sapi._dispatch("vid", "volume_down", {}))
    assert res == {"ok": True} and bus.sent == [("vid", "volume_down")]


# ── los manifests REALES ────────────────────────────────────────────────────────────────────────────────────
def _manifest(wid):
    return json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("wid", ["youtube", "musica"])
def test_los_widgets_que_suenan_declaran_su_contrato(wid):
    """Los dos widgets que HOY producen audio tienen que estar en el contrato, o el bug del operador vuelve."""
    man = _manifest(wid)
    sp = producers.spec(man)
    assert sp is not None, f"{wid} debe declarar 'runtime'"
    assert sp["output"] == "audio"
    assert sp["produce"], "debe declarar qué acciones lo ponen a producir"
    assert sp["active_when"], "debe declarar cómo se lee que está produciendo"


@pytest.mark.parametrize("wid", ["youtube", "musica"])
def test_el_contrato_solo_nombra_acciones_QUE_EXISTEN(wid):
    """`suspend` y `produce` tienen que ser acciones declaradas de verdad en el manifest. Una errata aquí
    (`"suspend": "stop"` en un widget que solo entiende `pause`) sería una parada que no para nada — y fallaría en
    silencio, en el peor momento posible."""
    man = _manifest(wid)
    declared = set((man.get("actions") or {}).keys())
    sp = producers.spec(man)
    assert sp["suspend"] in declared, f"{wid}: 'suspend' apunta a una acción inexistente"
    assert sp["produce"] <= declared, f"{wid}: 'produce' nombra acciones inexistentes: {sp['produce'] - declared}"
