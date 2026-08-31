"""V2-440 · the point-in-time census separates the two causes that looked identical.

The face says “it has already found something” and the sheet yields not even one row. This has TWO causes that
call for opposite fixes: **lag** (the worker has not delivered yet—the alert is correct and there is nothing to
change) and **wrong box** (the rows are on another sheet—there is a defect there). From the outside they look the same.

On 2026-08-28, an attempt was made to separate them by comparing against the round’s FINAL state, producing a
FALSE POSITIVE: `search-buy-bicycle__es` marked `e84138-2` as wrong, and that box ended up with 35 rows. The
final state cannot answer a question about a point in time—by then, the box that was checked already had what it
was missing when it was checked.
"""
from tests.use_cases.e2e.agent.verify import _censo_dice, unresolved_errand_sheets

_AVISO = "🧾 la cara dice que hay filas y la hoja no las da"


def _ev(cajas, censo):
    return {"kind": "perf", "label": _AVISO, "payload": {"cajas": cajas, "censo": censo}}


def test_ninguna_hoja_con_filas_es_DESFASE_y_no_un_defecto():
    """The healthy case: the alert appeared before the worker delivered. Counting it as a defect sends someone to
fix something that never happened—the kind of error a measuring instrument cannot afford."""
    assert _censo_dice("e84138-1:0 e84138-2:0", "e84138-2") == ("desfase", "")


def test_otra_hoja_CON_filas_se_reporta_como_HECHO_y_dice_CUAL():
    """And NOT as “wrong box”: the census lists the entire warehouse, and the sheet from a previous errand has
rows there legitimately. Calling it a defect turns a healthy round into a finding as soon as there are two
errands—the same error this node exists to prevent. Naming which one it is avoids having to infer it by hand,
which is what cost hours that night."""
    v, donde = _censo_dice("e84138-1:12 e84138-2:0", "e84138-2")
    assert v == "otras_con_filas" and donde == "e84138-1:12"


def test_mirar_donde_estan_las_filas_no_es_ninguna_de_las_dos():
    """The sheet had rows and we checked them: if this flagged anything, the instrument would accuse the engine of
a failure it did not commit precisely when it got things right."""
    assert _censo_dice("e84138-2:12", "e84138-2") == ("", "")


def test_un_censo_ILEGIBLE_es_un_HUECO_y_nunca_un_hallazgo():
    """“I could not check” is not “there was nothing.” Confusing them publishes an invented cause with the same
certainty as a measurement."""
    assert _censo_dice("?", "e84138-2") == ("", "")
    assert _censo_dice("", "e84138-2") == ("", "")


def test_las_filas_en_la_hoja_DESNUDA_son_su_propia_categoria():
    """The GHOST box is not lag, and putting it there would be the convenient choice: in a lag case nothing is
written, whereas here the rows exist, right next to the errand’s sheet. `_sheet_of_tab` documents this—without a
resolved sheet, findings land in bare `results`, “the one that belongs to no one.” The fix is DIFFERENT: the engine
looked correctly and the writer delivered incorrectly. Measured in `search-buy-bicycle__es`, whose `written_ids`
contains both."""
    assert _censo_dice("(base):9 e84138-2:0", "e84138-2") == ("fantasma", "(base)")


def test_la_hoja_DESNUDA_no_se_confunde_con_una_caja_de_encargo_equivocada():
    """If it were counted as a wrong box, the report would send someone to fix RESOLUTION when DELIVERY is what is
broken—and whoever reads it would waste time in the wrong place."""
    v, _ = _censo_dice("(base):9 e84138-1:0", "e84138-1")
    assert v == "fantasma"


def test_el_informe_PUBLICA_el_veredicto_y_no_solo_las_cajas():
    """Half the wiring: emitting the signal without bringing it into the report leaves the data where no one looks."""
    out = unresolved_errand_sheets([_ev("e84138-2", "e84138-1:12 e84138-2:0"),
                                    _ev("e84138-2", "e84138-1:0 e84138-2:0")])
    assert out["n_face_without_rows"] == 2
    assert out["n_with_other_sheets"] == 1 and out["other_sheets"] == ["e84138-1:12"]
    assert out["n_lag"] == 1


def test_el_MOTOR_emite_el_censo_y_no_solo_las_cajas(monkeypatch, tmp_path):
    """The other half, and without it the five above pass with the emitter MUTED—verified by dismantling it.

An interpreter that knows how to interpret a field nobody writes measures nothing: it publishes zeroes that read as
“nothing happened,” which is the reassuring answer. The check follows the real path (`aviso_sin_filas`) and
requires the event to carry the census inside it.
    """
    monkeypatch.setenv("ZAELAR_HOME", str(tmp_path))
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    from nucleo.flash import errand_sheet
    from widgets import store
    from widgets.results import data as sheet, intake
    # OWN WAREHOUSE. The census lists ALL sheets and is bounded, so in the full suite the ones left by other cases
    # push ours outside the cutoff and the check fails for the wrong reason—measured. What is tested here is the
    # WIRING, not how many sheets fit.
    _wd = tmp_path / "wdata"
    _wd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "DATA_DIR", str(_wd), raising=False)

    sheet.begin_task("bicis", fresh=True, sheet="cen-1")
    intake.push([{"title": "Rockrider ST 100", "price": "150€", "url": "http://x/1"}], sheet="cen-1")

    visto = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda *a, **k: visto.append(k.get("extra") or {}), raising=False)
    errand_sheet.aviso_sin_filas("7", ["cen-2"])

    assert visto, "el motor no emitió nada"
    censo = str(visto[-1].get("censo") or "")
    assert censo and censo != "?", f"el aviso salió sin censo: {visto[-1]!r}"
    # And the census must be READABLE by the same parser that consumes it, or the wiring is still broken.
    v, _ = _censo_dice(censo, "cen-2")
    assert v == "otras_con_filas"
    # What proves the WIRING is that our sheet is in the RAW census with its count: the report summary is
    # deliberately bounded, so in the full suite—with the sheets left by other tests—ours may fall outside the
    # cutoff without anything being broken. Verified: it fails only there.
    assert "cen-1:1" in censo, censo


def test_al_juez_se_le_da_la_causa_del_CENSO_y_no_la_del_estado_final():
    """`n_wrong_box` compares against the round’s FINAL state and therefore marked the ELEVEN alerts from
    `find-theatre-tickets__us` (2026-08-28) as wrong box, when the census says all eleven were LAG: nobody had rows
    at that point in time. Telling the judge a false cause eleven times is worse than telling it none—it will
    believe it and lower the mechanism score for a nonexistent failure."""
    from tests.use_cases.e2e.agent import judge
    mech = {"sheet_hidden_from_the_prompt": {"n": 2, "turns": [{"turn": 5}]},
            "unresolved_errand_sheets": {"n_wrong_box": 11, "wrong_boxes": {"86f804-2": 11},
                                         "n_lag": 11, "n_ghost": 0, "n_with_other_sheets": 0}}
    txt = judge.mechanism_facts(mech)
    assert "caja que NO era" not in txt and "86f804-2" not in txt


def test_y_si_el_CENSO_dice_que_habia_filas_en_otra_hoja_SI_se_le_dice():
    """The half that keeps the fix from being silence: when the census does find rows elsewhere, that is the right
clue and it must get through—with the notice that a previous sheet legitimately has them."""
    from tests.use_cases.e2e.agent import judge
    mech = {"sheet_hidden_from_the_prompt": {"n": 2, "turns": [{"turn": 5}]},
            "unresolved_errand_sheets": {"n_lag": 0, "n_ghost": 0,
                                         "n_with_other_sheets": 3, "other_sheets": ["e84138-1:12"]}}
    txt = judge.mechanism_facts(mech)
    assert "e84138-1:12" in txt and "encargo ANTERIOR" in txt
