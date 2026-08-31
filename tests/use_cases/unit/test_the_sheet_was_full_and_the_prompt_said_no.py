"""“It had results and replied that there was nothing new” — did it lie, or did we tell it there was nothing?

It is the question that determines the ATTRIBUTION of the board’s most frequently repeated blocker. Read from the transcript,
that turn looks like a product lie. If its prompt said that the task was still stuck, then
it replied **exactly what we put in front of it**, and the defect is ours.

Measured in `find-direct-flight-budget__es` (2026-08-28, 24/7 set): `sheet_named_ms` falls between turns 5 and
6; on turns **6, 7, and 8** the live block showed the “not progressing” face and ZERO rows, with four named flights
in the task sheet. The judge scored it 2/5 for “withholding the deliverable and denying what the system
showed it.” The system showed it the opposite.

Scan of the 353 saved reports: of the **48** runs whose sheet eventually had names, **45** have
at least one turn that was not told — **257 turns** total.

This does NOT say where the fault is (`_found_candidates` already falls through to `_sheet_has_rows`, so resolving the
task box is the suspect) and does not try to guess. It says how often it happens, which is what turns
an inference about one run into a number across many.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V

_T = {"sheet_named_ms": 1000.0}
_VIVO = "TAREAS DE FONDO EN CURSO (los brain workers las están resolviendo): «Busca vuelos» · sin avanzar"


def test_el_caso_MEDIDO_marca_sus_turnos():
    pc = [{"turn": 5, "at_ms": 900.0, "live_line": _VIVO, "sheet_rows": []},
          {"turn": 6, "at_ms": 1100.0, "live_line": _VIVO, "sheet_rows": []},
          {"turn": 7, "at_ms": 1200.0, "live_line": _VIVO, "sheet_rows": []}]
    got = V.sheet_hidden_from_the_prompt(pc, _T)
    assert got["n"] == 2 and [t["turn"] for t in got["turns"]] == [6, 7]


def test_un_turno_ANTERIOR_a_que_hubiera_filas_no_cuenta():
    """You cannot hide from it what does not yet exist."""
    pc = [{"turn": 0, "at_ms": 500.0, "live_line": _VIVO, "sheet_rows": []}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_si_el_prompt_SÍ_lo_dice_no_es_ceguera():
    """Even without giving it the names, telling it that something exists already changes what it can answer."""
    pc = [{"turn": 6, "at_ms": 1100.0, "sheet_rows": [],
           "live_line": "TAREAS DE FONDO EN CURSO · la tarea YA HA ENCONTRADO algo, pero sus nombres aún no"}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_si_le_dimos_las_FILAS_menos_todavía():
    pc = [{"turn": 6, "at_ms": 1100.0, "live_line": _VIVO, "sheet_rows": ["Iberia directo 21:50"]}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_sin_BLOQUE_VIVO_no_hay_ceguera():
    """The task is no longer in progress: its results were delivered or closed, and there was nothing to tell it
    on that turn. Five of the 262 turns in the scan were like this — counting them would have inflated the number with the
    kind of case that the finding itself says it is NOT."""
    pc = [{"turn": 6, "at_ms": 1100.0, "live_line": "", "sheet_rows": []}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_sin_filas_con_nombre_NUNCA_no_hay_pregunta_que_hacer():
    """It is also distinct from “zero blind turns”: not having the data is not the same as having it and ending up at zero."""
    got = V.sheet_hidden_from_the_prompt([{"turn": 0, "at_ms": 1.0, "live_line": _VIVO}], {})
    assert got["n"] == 0 and got["measurable"] is False
    assert V.sheet_hidden_from_the_prompt([], _T)["measurable"] is True


def test_al_JUEZ_se_le_dice_que_NO_lo_puntúe_como_negar():
    """Measuring this and not telling the judge leaves the verdict just as wrong: it is the one who assigns the score."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt":
                                {"n": 3, "measurable": True, "turns": [{"turn": 6}, {"turn": 7}, {"turn": 8}]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "6, 7, 8" in txt
    assert "NO lo puntúes como retener" in txt


def test_y_no_se_le_dice_nada_cuando_no_hubo_ceguera():
    """A notice that always appears stops being a notice."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 0, "measurable": True, "turns": []}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" not in txt


def test_la_CAUSA_se_lee_del_flujo_y_no_de_las_anomalias():
    """The engine notice is a `perf` event, not an error, so the auditor’s anomaly list —which
    only collects `is_error`— would NEVER see it. Emitting the signal and not bringing it into the report would have been the third
    half-finished job of the same night: the data exists, but it is not where we look."""
    import json
    ev = {"kind": "perf", "cat": "system",
          "payload": json.dumps({"kind": "perf", "cat": "system",
                                 "label": "🧾 hoja del encargo SIN RESOLVER", "nav_task": "6175ca-1"})}
    got = V.unresolved_errand_sheets([ev, ev])
    assert got["n"] == 2 and got["tabs"] == {"6175ca-1": 2}
    vacio = V.unresolved_errand_sheets([])
    assert vacio["n"] == 0 and vacio["tabs"] == {} and vacio["n_empty"] == 0


def test_la_causa_va_PEGADA_al_aviso_y_no_en_una_linea_suelta():
    """It tells the judge the same thing —do not blame the model—, so a second sentence repeating it would be noise."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 2, "measurable": True,
                                                                "turns": [{"turn": 6}, {"turn": 7}]},
                                "unresolved_errand_sheets": {"n": 3, "tabs": {"6175ca-1": 3}}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "se sabe POR QUÉ" in txt and "6175ca-1" in txt
    assert txt.index("NO SE LO DIJIMOS") < txt.index("se sabe POR QUÉ")


def test_y_sin_causa_conocida_no_se_inventa_una():
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 2, "measurable": True,
                                                                "turns": [{"turn": 6}, {"turn": 7}]},
                                "unresolved_errand_sheets": {"n": 0, "tabs": {}}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "se sabe POR QUÉ" not in txt


def test_resolver_a_la_caja_EQUIVOCADA_se_cuenta_aparte():
    """Failing to resolve was already counted; resolving to the wrong box looked **just like getting it right**. And it was
    the case of `search-buy-guitar__es`: `unresolved_errand_sheets.n` came out as 0 —meaning it resolved— yet
    there were six turns in which the model was not told that it had anything, with 15 candidates in the sheet."""
    import json
    def _ev(label, **extra):
        return {"kind": "perf", "cat": "system",
                "payload": json.dumps({"kind": "perf", "cat": "system", "label": label, **extra})}
    got = V.unresolved_errand_sheets([
        _ev("🧾 hoja del encargo SIN RESOLVER", nav_task="a-1"),
        _ev("🧾 hoja del encargo RESUELTA PERO VACÍA", nav_task="b-1", hoja="results", n_items=0),
        _ev("🧾 hoja del encargo RESUELTA PERO VACÍA", nav_task="b-1", hoja="results", n_items=0)])
    assert got["n"] == 1 and got["tabs"] == {"a-1": 1}
    assert got["n_empty"] == 2 and got["empty_sheets"] == {"results": 2}


def test_al_juez_se_le_dice_CUÁL_de_las_averías_fue():
    """Rewritten TWICE on 2026-08-28 and NEVER reversed. The property has never changed: each fault leads
    us to inspect a different place in the engine, so “fault” on its own is not enough.

    What changes is WHICH signal names it. First it was the empty box alone (that stopped being the case: in five of six
    runs it was the healthy path). Then the WRONG box, derived by comparing with `sheet_timing.sheet_box`
    — and that comparison was DISCREDITED by a live measurement: in `find-theatre-tickets__us` it marked all
    ELEVEN notices as the wrong box when the snapshot at that moment (V2-440) says all eleven were LAG,
    with nobody having rows. A FINAL state cannot answer a question about an INSTANT, and telling the judge
    about a nonexistent fault eleven times in one run lowers the mechanism score for something that did not happen.

    Today the census names it: `n_with_other_sheets` (there were rows in another sheet) and `n_ghost` (in the bare one).
    """
    from tests.use_cases.e2e.agent import judge as J
    base = {"sheet_hidden_from_the_prompt": {"n": 2, "measurable": True, "turns": [{"turn": 6}, {"turn": 7}]}}
    mala = J.mechanism_facts({**base, "unresolved_errand_sheets": {
        "n": 0, "tabs": {}, "n_empty": 3, "empty_sheets": {"f1743e-2": 3},
        "n_lag": 0, "n_ghost": 0, "n_with_other_sheets": 3, "other_sheets": ["f1743e-1:12"]}})
    txt = "\n".join(mala) if isinstance(mala, list) else str(mala)
    assert "filas en OTRA" in txt and "f1743e-1:12" in txt
    # …and an empty box because the task had not found anything yet tells the judge nothing
    sana = J.mechanism_facts({**base, "unresolved_errand_sheets": {
        "n": 0, "tabs": {}, "n_empty": 3, "empty_sheets": {"24cd96-1": 3},
        "n_lag": 3, "n_ghost": 0, "n_with_other_sheets": 0, "other_sheets": []}})
    txt2 = "\n".join(sana) if isinstance(sana, list) else str(sana)
    assert "NO era la de este encargo" not in txt2 and "se sabe POR QUÉ" not in txt2
    sin = J.mechanism_facts({**base, "unresolved_errand_sheets": {"n": 2, "tabs": {"a-1": 2},
                                                                 "n_empty": 0, "empty_sheets": {}}})
    txt3 = "\n".join(sin) if isinstance(sin, list) else str(sin)
    assert "no supo qué hoja" in txt3


def test_las_TRES_averías_se_cuentan_por_separado():
    """The three lead us to inspect different places in the engine: failing to resolve, resolving to the wrong box, and
    the read crashing. Putting them in the same bucket leaves the investigator where they started."""
    import json
    def _ev(label, **extra):
        return {"kind": "perf", "cat": "system",
                "payload": json.dumps({"kind": "perf", "cat": "system", "label": label, **extra})}
    got = V.unresolved_errand_sheets([
        _ev("🧾 hoja del encargo SIN RESOLVER", nav_task="a-1"),
        _ev("🧾 hoja del encargo RESUELTA PERO VACÍA", nav_task="b-1", hoja="results"),
        _ev("🧾 hoja del encargo ILEGIBLE", nav_task="c-1", error="KeyError: items")])
    assert got["n"] == 1 and got["n_empty"] == 1 and got["n_unreadable"] == 1
    assert got["errors"] == ["KeyError: items"]


def test_la_caja_VACÍA_a_secas_ya_no_es_una_avería():
    """Measured on 2026-08-28 across the six runs that produced the signal: in FIVE the engine looked in the
    CORRECT box and it was empty because the task had not found anything yet — the healthy path, not a defect.
    In ONE it read `f1743e-2` while the rows were in `f1743e-1`, and that one was a defect.

    Without separating them, the signal fires on the normal case and whoever reads it will conclude what I did: that there is a
    pattern where there is one case.
    """
    import json
    def _ev(**extra):
        return {"kind": "perf", "cat": "system",
                "payload": json.dumps({"kind": "perf", "cat": "system",
                                       "label": "🧾 hoja del encargo RESUELTA PERO VACÍA", **extra})}
    # the SAME box that ended up having the rows → healthy path
    sano = V.unresolved_errand_sheets([_ev(nav_task="a-1", hoja="24cd96-1")], sheet_box="24cd96-1")
    assert sano["n_empty"] == 1 and sano["n_wrong_box"] == 0
    # a DIFFERENT box → that is a defect
    malo = V.unresolved_errand_sheets([_ev(nav_task="a-2", hoja="f1743e-2")], sheet_box="f1743e-1")
    assert malo["n_wrong_box"] == 1 and malo["wrong_boxes"] == {"f1743e-2": 1}


def test_sin_saber_dónde_cayeron_las_filas_no_se_acusa():
    """Without `sheet_box` there is nothing to compare against, and calling a box wrong just in case is exactly the error
    this fixes."""
    import json
    ev = {"kind": "perf", "cat": "system",
          "payload": json.dumps({"kind": "perf", "cat": "system",
                                 "label": "🧾 hoja del encargo RESUELTA PERO VACÍA", "hoja": "x-1"})}
    assert V.unresolved_errand_sheets([ev])["n_wrong_box"] == 0


def test_al_juez_la_ILEGIBLE_le_llega_con_su_error():
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({
        "sheet_hidden_from_the_prompt": {"n": 4, "measurable": True, "turns": [{"turn": 9}]},
        "unresolved_errand_sheets": {"n": 0, "tabs": {}, "n_empty": 0, "empty_sheets": {},
                                     "n_unreadable": 2, "errors": ["KeyError: items"]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "REVENTÓ" in txt and "KeyError: items" in txt


def test_el_TABLERO_dice_en_qué_filas_no_le_dijimos_nada(tmp_path, monkeypatch):
    """The judge already says it in prose, run by run. Without the number on the board, reading it requires opening the
    report for each run one by one — and the board is where people look.

    It includes its number because “there were blind turns” and “there were fourteen” call for different readings of the same score.
    """
    from tests.use_cases.e2e.agent import status as S
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([{"scenario": "x__es", "tier": 2,
               "run": {"transcript": [], "mechanism_report": {"sheet_hidden_from_the_prompt": {"n": 6}}},
               "verdict": {"overall": 2, "scores": {"mecanismo": 3}, "veredicto": "flojo"}}], sandboxed=True)
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "NO le dijimos lo que ya tenía" in board
    assert "| `x__es` | 6 |" in board


def test_y_sin_turnos_ciegos_no_aparece_la_sección(tmp_path, monkeypatch):
    """A section that always appears stops being read, and the board already has six."""
    from tests.use_cases.e2e.agent import status as S
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([{"scenario": "x__es", "tier": 2,
               "run": {"transcript": [], "mechanism_report": {"sheet_hidden_from_the_prompt": {"n": 0}}},
               "verdict": {"overall": 4, "scores": {"mecanismo": 4}, "veredicto": "bien"}}], sandboxed=True)
    assert "NO le dijimos" not in (tmp_path / "STATUS.md").read_text(encoding="utf-8")


def test_la_CARA_se_lee_de_su_campo_y_no_de_la_línea_recortada():
    """The third time on the same night that truncation turns data into a false conclusion.

    `says_found` is calculated over the COMPLETE line, before truncating it to 1200. Searching for the phrase inside
    `live_line` marked four turns of `search-buy-camera__us` as blind even though their block said it —beyond
    the cutoff—, and those nearly led us to open a fourth hypothesis about a nonexistent defect.

    The other two times were the sheet rows (which begin past the cutoff) and the face classification
    (275 of 281 “question” turns were boilerplate). A field is not truncated by accident.
    """
    largo = "TAREAS DE FONDO EN CURSO: " + ("x" * 1400) + " · YA HA ENCONTRADO ALGO"
    ciego = V.sheet_hidden_from_the_prompt(
        [{"turn": 6, "at_ms": 1100.0, "live_line": largo[:1200], "says_found": True}], _T)
    assert ciego["n"] == 0, "el bloque se lo dijo y el recorte lo escondía"


def test_y_sin_el_campo_se_sigue_mirando_la_prosa():
    """Reports from before the field do not have it and remain the only evidence for their runs."""
    viejo = [{"turn": 6, "at_ms": 1100.0,
              "live_line": "TAREAS DE FONDO · la tarea YA HA ENCONTRADO algo"}]
    assert V.sheet_hidden_from_the_prompt(viejo, _T)["n"] == 0


def test_el_campo_lo_calcula_prompt_context_sobre_la_línea_ENTERA():
    """The plumbing: if `prompt_context` does not populate it from `live` —the complete line, before truncation—,
    the field exists, always comes out False, and the detector again marks as blind the turns that were notified.

    Caught by dismantling it: with the field manually set in the fixtures, removing it from the emitter left all 19 tests
    green while the defect was restored."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    # V2-444 — the property does not change (it is calculated over the ENTIRE prompt, `sp`, not the truncated line);
    # what changed is that BOTH phrases are accepted, because they are two different blocks and in the run that
    # exposed it, the second fired while the first did not appear even once.
    marca = '"says_found": ("YA HA ENCONTRADO" in sp) or ("DICE haber encontrado" in sp),'
    assert marca in src, (
        "se busca en `live` (la línea de tareas) y el imperativo de resultados es OTRA línea del prompt")
    assert src.index(marca) > src.index("sp = p.get(")
    # V2-451 — and the ROWS likewise. They were calculated from `live` (the BROWSER line), and since the fix there is
    # a second block carrying them; in the next four runs `navegador_task_id` was EMPTY, so a field read from that line
    # would have said “nothing was shown to it” forever. The question is whether rows reached it, and the answer cannot
    # depend on which block they landed in.
    assert '"sheet_rows": _rows_in(sp),' in src, "las filas vuelven a leerse de una sola línea del prompt"


# ── NOTIFIED AND WITHOUT ROWS ──────────────────────────────────────────────────────────────────────────
# The other half of the same question. `sheet_hidden_from_the_prompt` skips turns with `says_found` on
# purpose —the turn WAS told—, so nobody counted the trap that V2-330 named but did not close: the
# face says “TELL IT with name and price” and the prompt contains not a single row. Measured in `search-buy-bicycle__es`
# (2026-08-28): 10 notified turns, zero rows in all of them, with the results existing for the last 315 s.
from tests.use_cases.e2e.agent.verify import told_but_given_no_rows


def _t(turn, at_ms, says_found, rows):
    return {"turn": turn, "at_ms": at_ms, "says_found": says_found, "sheet_rows": rows, "live_line": "x"}


def test_avisado_y_con_CERO_filas_se_cuenta():
    out = told_but_given_no_rows([_t(4, 200.0, True, []), _t(5, 300.0, True, [])], {"sheet_named_ms": 100.0})
    assert out["n"] == 2 and [x["turn"] for x in out["turns"]] == [4, 5]


def test_avisado_y_CON_filas_no_se_cuenta():
    """The healthy path. If this were counted, the number would say we asked for the impossible just when we got it right."""
    out = told_but_given_no_rows([_t(4, 200.0, True, ["«Bici — 150€»"])], {"sheet_named_ms": 100.0})
    assert out["n"] == 0


def test_un_turno_al_que_NO_se_le_avisó_es_del_otro_contador():
    """Blindness and an impossible instruction are distinct failures with distinct fixes; counting them together erases the
    difference and sends us to look in the wrong place."""
    out = told_but_given_no_rows([_t(4, 200.0, False, [])], {"sheet_named_ms": 100.0})
    assert out["n"] == 0


def test_antes_de_que_la_hoja_tuviera_nombres_no_hay_nada_que_dar():
    """Without this cutoff the counter would mark every turn from the start of the run: it is not that we did not give it the
    rows; they did not exist yet."""
    out = told_but_given_no_rows([_t(2, 50.0, True, [])], {"sheet_named_ms": 100.0})
    assert out["n"] == 0


def test_sin_hoja_con_nombres_la_pregunta_NO_es_medible():
    """“Zero” and “cannot be determined” are not the same, and zero is the reassuring one."""
    assert told_but_given_no_rows([_t(2, 50.0, True, [])], {})["measurable"] is False


def test_al_juez_se_le_DICE_que_le_pedimos_lo_imposible():
    """The data was already in the transcript in the cases that were scored incorrectly; what was missing was the instruction.
    Without this, the judge keeps reading “did not provide names” as withholding."""
    from tests.use_cases.e2e.agent import judge
    txt = judge.mechanism_facts({"told_but_given_no_rows": {"n": 3, "turns": [{"turn": 7}]}})
    assert "IMPOSIBLE" in txt.upper() and "3" in txt


def test_run_lo_CALCULA_o_el_informe_sale_sin_el():
    """The wiring guard, which was missing in three nodes this week: the five cases above call the function directly,
    so they pass with the `run.py` line DELETED — and then the field does not exist, the judge receives nothing, and the
    board again scores as withholding what is ours.
    A counter nobody calls measures zero, and zero is read as “it did not happen.”"""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["told_but_given_no_rows"] = verifymod.told_but_given_no_rows(' in src
