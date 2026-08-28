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
    """Los dos tienen lista desde V2-366; mirar solo uno deja media familia sin medir."""
    from tests.use_cases.e2e.agent import probe_client
    orig = probe_client.widget_data
    try:
        probe_client.widget_data = lambda w, q="": {"list": [{"title": f"{w}-1"}, {"title": f"{w}-2"}]}
        out = verify.media_list()
        assert out["n_items"] == 4 and set(out["widgets"]) == {"youtube", "musica"}
    finally:
        probe_client.widget_data = orig


def test_run_lo_CALCULA_o_el_campo_no_existe():
    """Guarda de cableado: los cinco de arriba pasan enteros con la línea de `run.py` borrada."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["media_list"] = verifymod.media_list()' in src
