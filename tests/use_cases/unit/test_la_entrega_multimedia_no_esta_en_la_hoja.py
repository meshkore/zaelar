"""V2-445 · un encargo de vídeo o música entrega en la LISTA del reproductor, no en la hoja.

V2-402 fijó la frontera: lo que se VE u OYE se canaliza por su widget dedicado —buscarlo incluido— y la hoja
de resultados es para INFORMACIÓN. El arnés nunca se enteró y siguió midiendo la entrega contra
`results_sheet`, que para esa familia está vacía POR DISEÑO.

Medido en `find-videos-on-a-topic-no-ai-slop` (2026-08-28, plató 24/7): `widget_ops` registra
`youtube.search ×4` —o sea que el enrutado de V2-402 funcionó— y el informe publicó `results_sheet: 0 items`.
El juez concluyó que zaelar «anunció 2 vídeos sin respaldo en el sistema» y puntuó resultado 1. La afirmación
podía ser cierta y el informe no tenía dónde comprobarlo.

No es una ronda: es una CLASE de escenario (`find-videos-*`, `build-a-video-playlist-*`,
`play-music-and-build-playlist`) midiéndose contra la superficie que deliberadamente no usa. Quinto caso de
un instrumento acusando al producto en la misma noche.
"""
from tests.use_cases.e2e.agent import judge, verify


def _linea(mech):
    for l in judge.mechanism_facts(mech).splitlines():
        if "REPRODUCTOR" in l:
            return l
    return ""


def test_con_lista_llena_se_le_dice_al_juez_que_ahi_esta_la_entrega():
    l = _linea({"media_list": {"read": True, "n_items": 2,
                               "widgets": {"youtube": {"n": 2, "n_named": 2, "titles": ["A", "B"]}},
                               "titles": ["A", "B"]}})
    assert "2 elemento(s)" in l and "youtube ×2" in l
    assert "NO prueba" in l and "hoja" in l


def test_con_lista_VACIA_se_dice_que_eso_SI_es_no_entregar():
    """La mitad que impide que el arreglo sea una amnistía: en un encargo multimedia la lista vacía es
    exactamente el fallo, y sin decirlo el juez se queda sin poder puntuar la familia entera."""
    l = _linea({"media_list": {"read": True, "n_items": 0, "widgets": {}, "titles": []}})
    assert "VACÍA" in l and "sí es no haber" in l


def test_si_no_se_pudo_LEER_no_se_dice_nada():
    """«No pude mirar» no es «no había nada»: publicar un cero ahí es la respuesta tranquilizadora."""
    assert _linea({"media_list": {"read": False, "n_items": 0}}) == ""


def test_el_lector_distingue_VACIO_de_NADIE_MIRO(monkeypatch):
    from tests.use_cases.e2e.agent import probe_client
    monkeypatch.setattr(probe_client, "widget_data", lambda w, q="": None)
    assert verify.media_list()["read"] is False
    monkeypatch.setattr(probe_client, "widget_data",
                        lambda w, q="": {"list": []} if w == "youtube" else None)
    out = verify.media_list()
    assert out["read"] is True and out["n_items"] == 0


def test_el_lector_cuenta_las_filas_de_los_DOS_reproductores():
    """Los dos tienen lista desde V2-366; mirar solo uno deja media familia sin medir.

    Cada uno con SU forma real (V2-468): este test daba `{"list": …}` a los dos, y `musica` no tiene esa
    clave — pasaba en verde certificando una ficción, que es exactamente cómo el defecto llegó a producción.
    """
    from tests.use_cases.e2e.agent import probe_client
    orig = probe_client.widget_data
    try:
        probe_client.widget_data = lambda w, q="": (
            {"list": [{"title": "yt-1"}, {"title": "yt-2"}]} if w == "youtube" else
            {"playlists": [{"name": "Curro", "tracks": [{"title": "m-1"}, {"title": "m-2"}]}]})
        out = verify.media_list()
        assert out["n_items"] == 4 and set(out["widgets"]) == {"youtube", "musica"}
    finally:
        probe_client.widget_data = orig


def test_run_lo_CALCULA_o_el_campo_no_existe():
    """Guarda de cableado: los cinco de arriba pasan enteros con la línea de `run.py` borrada."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["media_list"] = verifymod.media_list()' in src


def test_con_el_reproductor_LLENO_la_hoja_vacia_no_acusa_entrega_ausente():
    """V2-469 · the prompt contradicted itself and the judge picked the wrong half (measured, round 8 of
    `find-videos`, 22:47): «hoja SIN candidatos → entrega ausente en la única superficie que la guarda»
    stated flatly, four lines above a player list holding 5 named videos — and the judge invented «un
    mandato explícito de usar la HOJA DE RESULTADOS», the exact opposite of V2-402's design. When the
    player has items, the empty-sheet line DEFERS to it instead of accusing."""
    out = judge.mechanism_facts({
        "results_sheet": {"read": True, "n_items": 0, "n_named": 0, "titles": []},
        "media_list": {"read": True, "n_items": 5,
                       "widgets": {"youtube": {"n": 5, "n_named": 5, "titles": ["A", "B"], "lists": []}},
                       "titles": ["A", "B"]},
    })
    assert "única superficie que la guarda" not in out
    assert "REPRODUCTOR" in out
    assert "lo esperado" in out


def test_sin_reproductor_la_hoja_vacia_SIGUE_acusando():
    """The half that keeps the fix from being an amnesty: with nothing in any player, an empty sheet on a
    search errand is still absent delivery, said exactly as before."""
    out = judge.mechanism_facts({
        "results_sheet": {"read": True, "n_items": 0, "n_named": 0, "titles": []},
        "media_list": {"read": True, "n_items": 0, "widgets": {}, "titles": []},
    })
    assert "única superficie que la guarda" in out
