"""El canal de texto rotulaba la música en vez de ponerla (V2-380).

Medido en la PRIMERA ronda que `play-music-and-build-playlist` ha tenido nunca (2026-08-27), y salió **1/5**,
el peor del día:

    familias faltantes: ['widget']    · cero operaciones de widget · cero eventos con evidencia
    tester  Ponme algo de música tranquila para trabajar.
    zaelar  Hecho.
    tester  ¿Qué has puesto?

«Hecho.» es `data_ack`, nuestro ack enlatado, y era lo ÚNICO que este canal hacía con `play_music`: lo
resolvía a la etiqueta «music» y ahí acababa. Después el turno se inventó «Painkiller» de Judas Priest y
«Stairway to Heaven» para quien había pedido música tranquila e instrumental.

El juez lo archivó como narrar una sesión de música ficticia. Lo era — y **el caso no podía pasar por
construcción**: estaba midiendo un mecanismo INALCANZABLE, así que la nota no dice nada del producto.

Tercera vez de la misma familia en este fichero, y su propio código lo repite en cada backstop: es la
implementación PARALELA del provider de voz, «cablear en AMBOS». Ya pasó con las tags de cron (V2-121) y con
el traspaso de login (V2-176).

El rail es el MISMO que ejecuta la voz (`music_flow.run`), así que esto no añade una segunda forma de poner
música: la enchufa.
"""
import pytest

from nucleo.flash import probe as P


class _Res:
    def __init__(self, ok=True, message=""):
        self.ok, self.message = ok, message


@pytest.fixture
def rail(monkeypatch):
    """Sustituye el rail por un testigo: aquí se mide el CABLEADO, no el conector de música."""
    visto = {}
    import nucleo.flash.music_flow as _mf

    async def _run(action, query, *, extract=None):
        visto.update({"action": action, "query": query, "extract": extract})
        return visto.get("_res") or _Res(True, "Suena «Music for Airports» de Brian Eno")
    monkeypatch.setattr(_mf, "run", _run)
    return visto


# ── el cableado ────────────────────────────────────────────────────────────────────────────────────────────

def test_el_rail_de_musica_ESTA_enchufado_en_este_canal():
    """El guarda que habría bastado: la rama existía y no ejecutaba nada."""
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text()
    assert "from nucleo.flash import music_turn as _music_turn" in src
    assert "await _music_turn.execute(music_req[" in src
    assert "from nucleo.flash import music_flow as _mflow" in Path("nucleo/flash/music_turn.py").read_text()


def test_la_rama_de_musica_va_DENTRO_del_bloque_de_ejecucion():
    """Fuera del `if execute:` volvería a ser una etiqueta — y ese es exactamente el defecto que se cierra."""
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text()
    i_exec, i_music = src.index("    if execute:"), src.index('elif action == "music" and music_req:')
    assert i_exec < i_music


def test_los_argumentos_del_modelo_llegan_al_rail():
    """`play_music` lleva `action` y `query`; perder cualquiera de los dos pone otra cosa o no pone nada."""
    from nucleo.flash import music_turn as MT
    req = MT.request_from([{"name": "play_music", "args": {"action": "QUEUE", "query": "  Brian Eno  "}}])
    assert req == {"action": "queue", "query": "Brian Eno"}


def test_sin_accion_se_asume_PONER():
    """Un `action` vacío no puede quedarse sin ejecutar: sería este mismo defecto con otra cara."""
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
    """La decisión REAL, no una copia: reimplementarla aquí probaría que mi copia funciona (V2-199)."""
    from nucleo.flash import music_turn as MT
    return MT.spoken_for(extra, "Hecho.")


def test_si_SUENA_se_dice_lo_que_suena():
    assert "Brian Eno" in _boca({"executed": "play_music", "ok": True,
                                 "message": "Suena «Music for Airports» de Brian Eno"})


def test_si_NO_suena_se_DICE_en_vez_de_Hecho():
    """El corazón del defecto: «Hecho.» sobre una reproducción que no existe. Cuarta vez que una frase
    enlatada nuestra es la que miente (V2-176, V2-209, V2-377)."""
    salida = _boca({"executed": "play_music", "ok": False, "message": "no hay ningún reproductor conectado"})
    assert salida.startswith("No he podido ponerlo")
    assert "Hecho." not in salida


def test_un_fallo_SIN_motivo_no_se_queda_mudo():
    assert "el reproductor no ha arrancado" in _boca({"executed": "play_music", "ok": False})


def test_un_turno_que_NO_es_de_musica_conserva_su_ack():
    assert _boca({"executed": "widget_data", "ok": True}) == "Hecho."


# ── lo que NO se hace, y es una decisión ───────────────────────────────────────────────────────────────────

def test_NO_se_paga_un_segundo_pase_de_modelo():
    """El `extract` es un 2º pase del modelo que resuelve una petición difusa, y lo presta el llamante. Aquí se
    mide el MECANISMO, no la resolución difusa, y una llamada extra se paga en CADA ronda del plató."""
    from pathlib import Path
    cuerpo = Path("nucleo/flash/music_turn.py").read_text()
    # ⚠️ Sobre la LLAMADA, no sobre el comentario: el propio comentario nombra «extract=None», así que un
    # guarda por substring salía VERDE con un `extract` de verdad puesto. Leía la explicación, no el código.
    assert "_mflow.run(action, query, extract=None)" in cuerpo
    assert "extract=lambda" not in cuerpo and "extract=_extract" not in cuerpo


def test_una_averia_del_rail_no_tumba_el_turno():
    """Fail-soft como el resto del bloque: el turno tiene que salir aunque el reproductor esté roto."""
    from pathlib import Path
    cuerpo = Path("nucleo/flash/music_turn.py").read_text()
    assert "except Exception" in cuerpo and "execute_error" in cuerpo


# ── V2-463 — la tarjeta del reproductor se abre en el rail COMPARTIDO ───────────────────────────────────
def test_poner_musica_ABRE_la_tarjeta_y_pararla_no_la_reabre(monkeypatch):
    """Mismo agujero que imagenes/youtube en el canal probe. Y la mitad fina: un stop sobre una tarjeta ya
    cerrada no puede volver a abrirla — parar es parar (V2-092)."""
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
