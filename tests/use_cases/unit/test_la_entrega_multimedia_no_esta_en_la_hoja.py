"""V2-445 · a video or music request delivers in the player's LIST, not in the sheet.

V2-402 set the boundary: what is SEEN or HEARD is routed through its dedicated widget—including searching for
it—and the results sheet is for INFORMATION. The harness never learned this and kept measuring delivery against
`results_sheet`, which is empty BY DESIGN for that family.

Measured in `find-videos-on-a-topic-no-ai-slop` (2026-08-28, 24/7 studio): `widget_ops` records
`youtube.search ×4`—meaning V2-402's routing worked—and the report published `results_sheet: 0 items`.
The judge concluded that zaelar “announced 2 videos without support in the system” and scored result 1. The
claim could have been true, and the report had nowhere to verify it.

This is not one round: it is a CLASS of scenario (`find-videos-*`, `build-a-video-playlist-*`,
`play-music-and-build-playlist`) being measured against the surface it deliberately does not use. The fifth case
of an instrument accusing the product on the same night.
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
    """The half that keeps the fix from being an amnesty: in a multimedia request, an empty list is
    exactly the failure, and without saying so the judge is unable to score the entire family."""
    l = _linea({"media_list": {"read": True, "n_items": 0, "widgets": {}, "titles": []}})
    assert "VACÍA" in l and "sí es no haber" in l


def test_si_no_se_pudo_LEER_no_se_dice_nada():
    """“I couldn't look” is not “there was nothing”: publishing a zero there is the reassuring answer."""
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
    """Both have a list since V2-366; looking at only one leaves half the family unmeasured.

    Each with its OWN real shape (V2-468): this test gave `{"list": …}` to both, and `musica` does not have that
    key—it passed in green while certifying a fiction, which is exactly how the defect reached production.
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
    """Wiring guard: the five above pass intact with the line from `run.py` deleted."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["media_list"] = verifymod.media_list()' in src


def test_con_el_reproductor_LLENO_la_hoja_vacia_no_acusa_entrega_ausente():
    """V2-469 · the prompt contradicted itself and the judge picked the wrong half (measured, round 8 of
    `find-videos`, 22:47): “sheet WITHOUT candidates → absent delivery on the only surface that stores it”
    stated flatly, four lines above a player list holding 5 named videos—and the judge invented “an explicit
    mandate to use the RESULTS SHEET,” the exact opposite of V2-402's design. When the player has items, the
    empty-sheet line DEFERS to it instead of accusing."""
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
