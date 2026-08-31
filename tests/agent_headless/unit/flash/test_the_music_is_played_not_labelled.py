"""The text channel labelled the music instead of playing it (V2-380).

Measured in the FIRST round that `play-music-and-build-playlist` had ever had (2026-08-27), and it scored **1/5**,
the worst of the day:

    missing families: ['widget']    · zero widget operations · zero events with evidence
    tester  Ponme algo de música tranquila para trabajar.
    zaelar  Hecho.
    tester  ¿Qué has puesto?

«Hecho.» is `data_ack`, our canned ack, and it was the ONLY thing this channel did with `play_music`: it
resolved it to the «music» label and stopped there. Then the turn invented «Painkiller» by Judas Priest and
«Stairway to Heaven» for someone who had asked for calm, instrumental music.

The judge filed it as narrating a fictional music session. It was — and **the case could not pass by
construction**: it was measuring an UNREACHABLE mechanism, so the score says nothing about the product.

Third time for the same family in this file, and its own code repeats it at every backstop: it is the
PARALLEL implementation of the voice provider, «wire it in BOTH». It already happened with cron tags (V2-121) and with
login handoff (V2-176).

The rail is the SAME one that executes voice (`music_flow.run`), so this does not add a second way to play
music: it plugs it in.
"""
import pytest

from nucleo.flash import probe as P


class _Res:
    def __init__(self, ok=True, message=""):
        self.ok, self.message = ok, message


@pytest.fixture
def rail(monkeypatch):
    """Replace the rail with a witness: this measures the WIRING, not the music connector."""
    visto = {}
    import nucleo.flash.music_flow as _mf

    async def _run(action, query, *, extract=None):
        visto.update({"action": action, "query": query, "extract": extract})
        return visto.get("_res") or _Res(True, "Suena «Music for Airports» de Brian Eno")
    monkeypatch.setattr(_mf, "run", _run)
    return visto


# ── the wiring ────────────────────────────────────────────────────────────────────────────────────────────

def test_el_rail_de_musica_ESTA_enchufado_en_este_canal():
    """The guard that would have been enough: the branch existed and executed nothing."""
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text()
    assert "from nucleo.flash import music_turn as _music_turn" in src
    assert "await _music_turn.execute(music_req[" in src
    assert "from nucleo.flash import music_flow as _mflow" in Path("nucleo/flash/music_turn.py").read_text()


def test_la_rama_de_musica_va_DENTRO_del_bloque_de_ejecucion():
    """Outside `if execute:`, it would become a label again — and that is exactly the defect being closed."""
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text()
    i_exec, i_music = src.index("    if execute:"), src.index('elif action == "music" and music_req:')
    assert i_exec < i_music


def test_los_argumentos_del_modelo_llegan_al_rail():
    """`play_music` carries `action` and `query`; losing either one plays something else or nothing at all."""
    from nucleo.flash import music_turn as MT
    req = MT.request_from([{"name": "play_music", "args": {"action": "QUEUE", "query": "  Brian Eno  "}}])
    assert req == {"action": "queue", "query": "Brian Eno"}


def test_sin_accion_se_asume_PONER():
    """An empty `action` cannot go unexecuted: it would be this same defect in another form."""
    from nucleo.flash import music_turn as MT
    assert MT.request_from([{"name": "play_music", "args": {"query": "algo tranquilo"}}])["action"] == "play"


def test_sin_llamada_a_play_music_no_se_inventa_una():
    from nucleo.flash import music_turn as MT
    assert MT.request_from([{"name": "web_search", "args": {}}]) == {"action": "play", "query": ""}


def test_el_rail_recibe_lo_que_pidio_el_modelo(rail):
    import asyncio

    from nucleo.flash import music_turn as MT
    parte = asyncio.run(MT.execute("queue", "Music for Airports"))
    assert rail["action"] == "queue" and rail["query"] == "Music for Airports"
    assert rail["extract"] is None, "un 2º pase de modelo se paga en cada ronda del plató"
    assert parte["executed"] == "play_music" and parte["ok"] is True


def test_una_averia_del_reproductor_devuelve_parte_y_no_lanza(monkeypatch):
    import asyncio

    import nucleo.flash.music_flow as _mf
    from nucleo.flash import music_turn as MT

    async def _boom(*a, **k):
        raise RuntimeError("el reproductor no responde")
    monkeypatch.setattr(_mf, "run", _boom)
    parte = asyncio.run(MT.execute("play", "algo tranquilo"))
    assert parte["ok"] is False and "no responde" in parte["execute_error"]


# ── la boca dice lo que PASÓ ───────────────────────────────────────────────────────────────────────────────

def _boca(extra):
    """The REAL decision, not a copy: reimplementing it here would prove that my copy works (V2-199)."""
    from nucleo.flash import music_turn as MT
    return MT.spoken_for(extra, "Hecho.")


def test_si_SUENA_se_dice_lo_que_suena():
    assert "Brian Eno" in _boca({"executed": "play_music", "ok": True,
                                 "message": "Suena «Music for Airports» de Brian Eno"})


def test_si_NO_suena_se_DICE_en_vez_de_Hecho():
    """The heart of the defect: «Hecho.» for playback that does not exist. The fourth time one of our canned
    phrases is the one doing the lying (V2-176, V2-209, V2-377)."""
    salida = _boca({"executed": "play_music", "ok": False, "message": "no hay ningún reproductor conectado"})
    assert salida.startswith("No he podido ponerlo")
    assert "Hecho." not in salida


def test_un_fallo_SIN_motivo_no_se_queda_mudo():
    assert "el reproductor no ha arrancado" in _boca({"executed": "play_music", "ok": False})


def test_un_turno_que_NO_es_de_musica_conserva_su_ack():
    assert _boca({"executed": "widget_data", "ok": True}) == "Hecho."


# ── what is NOT done, and is a decision ───────────────────────────────────────────────────────────────────

def test_NO_se_paga_un_segundo_pase_de_modelo():
    """`extract` is a 2nd model pass that resolves an ambiguous request, and the caller provides it. Here we
    measure the MECHANISM, not ambiguous-request resolution, and an extra call is paid for in EVERY studio round."""
    from pathlib import Path
    cuerpo = Path("nucleo/flash/music_turn.py").read_text()
    # ⚠️ About the CALL, not the comment: the comment itself names «extract=None», so a
    # substring guard passed with a real `extract` in place. It read the explanation, not the code.
    assert "_mflow.run(action, query, extract=None)" in cuerpo
    assert "extract=lambda" not in cuerpo and "extract=_extract" not in cuerpo


def test_una_averia_del_rail_no_tumba_el_turno():
    """Fail-soft like the rest of the block: the turn must complete even if the player is broken."""
    from pathlib import Path
    cuerpo = Path("nucleo/flash/music_turn.py").read_text()
    assert "except Exception" in cuerpo and "execute_error" in cuerpo


# ── V2-463 — the player card opens on the SHARED rail ───────────────────────────────────
def test_poner_musica_ABRE_la_tarjeta_y_pararla_no_la_reabre(monkeypatch):
    """Same hole as images/youtube in the probe channel. And the subtle part: a stop on an already
    closed card cannot reopen it — stopping is stopping (V2-092)."""
    import asyncio
    emitted: list[tuple] = []

    class _R:
        ok = True
        message = ""

    async def _run(action, query, extract=None):
        return _R()

    monkeypatch.setattr("nucleo.flash.music_flow.run", _run, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, extra or {})))
    from nucleo.flash import music_turn
    asyncio.run(music_turn.execute("play", "jazz"))
    shows = [e for e in emitted if e[0] == "widget" and e[1] == "show"]
    assert shows and shows[0][2].get("id") == "musica"
    emitted.clear()
    asyncio.run(music_turn.execute("stop", ""))
    assert not [e for e in emitted if e[0] == "widget" and e[1] == "show"]
