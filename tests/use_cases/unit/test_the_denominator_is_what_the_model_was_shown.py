"""“Did it deliver what it HAD?” was measured against the sheet, even though the model is not shown the entire sheet.

`delivery_completeness` (V2-332) promised in its first line to measure “the VALID rows that the system **put
in front of it**,” and divided by the ENTIRE sheet. When it was written, the sheet for the measured round had
five rows and the two things were the same; they stopped being the same as soon as the sheets grew.

`live_blocks._sheet_top_rows` pushes **at most 5** rows into the prompt (“bounded hard, because this lands in a
prompt, not on a screen”). Measured on 2026-08-28 in `search-buy-used-car`: sheet of 28, prompt with 5, the model
named 3—and the report published it as **“massive information retention, 11%”** with a `missed` list
full of cars that were never in any prompt. PERFECT compliance would have yielded 18%. An agent
reading that chases retention that does not exist: the instrument accusing the product again.

The difference between the two figures is not discarded—it is published separately (`in_sheet`), because “how
much of what we have we did not show it” is a finding about US, and a valuable one.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V

_HEAD = "LO QUE YA HA ENTREGADO (nombre y precio, de la hoja): "


def _turno(*filas: str) -> dict:
    """A turn exactly as returned by `prompt_context`: the rows travel INSIDE `live_line`."""
    return {"turn": 0, "live_line": ("TAREAS DE FONDO EN CURSO · la tarea YA HA ENCONTRADO algo. " + _HEAD
                                     + "; ".join(filas) + ". OJO: la hoja guarda TODO lo que dio la página")}


def test_lee_del_prompt_las_filas_que_tuvo_delante():
    got = V.shown_candidates([_turno("MINI Cooper F55 2016 — 11.700 €", "Audi Q5 2015 — 11.990 €")])
    assert got == ["MINI Cooper F55 2016", "Audi Q5 2015"]


def test_un_turno_sin_filas_no_aporta_ninguna():
    """Half the sensitivity: without this, “reads the rows” and “invents rows” pass equally."""
    assert V.shown_candidates([{"live_line": "TAREAS DE FONDO EN CURSO · sigue buscando"}]) == []
    assert V.shown_candidates([]) == []
    assert V.shown_candidates(None) == []


def test_las_filas_se_unen_entre_turnos_sin_repetirse():
    got = V.shown_candidates([_turno("MINI Cooper — 11.700 €"), _turno("MINI Cooper — 11.700 €",
                                                                       "FIAT Panda 4x4 — 6.900 €")])
    assert got == ["MINI Cooper", "FIAT Panda 4x4"]


def test_el_denominador_es_lo_mostrado_no_la_hoja():
    """THE REAL CASE: sheet of 28, prompt with 5, named 3. 60%, not 11%."""
    hoja = {"n_named": 28, "titles": [f"coche {i}" for i in range(28)]}
    dichas = {"n": 3, "names": ["coche 0", "coche 1", "coche 2"]}
    got = V.delivery_completeness(dichas, hoja, ["coche 0", "coche 1", "coche 2", "coche 3", "coche 4"])
    assert got["available"] == 5 and got["pct"] == 60
    assert got["in_sheet"] == 28, "lo que TENEMOS y no le enseñamos se publica aparte, no se tira"
    assert got["shown_to_model"] is True


def test_no_se_acusa_de_saltarse_lo_que_nunca_estuvo_en_un_prompt():
    hoja = {"n_named": 28, "titles": [f"coche {i}" for i in range(28)]}
    dichas = {"n": 1, "names": ["coche 0"]}
    got = V.delivery_completeness(dichas, hoja, ["coche 0", "coche 1"])
    assert got["missed"] == ["coche 1"], "solo lo que tuvo delante y no dijo"


def test_sin_contexto_de_prompt_se_comporta_como_antes():
    """Backward compatibility: an old round or a failure to read the prompt cannot be left without a metric.
    It is marked with `shown_to_model=False` so no one confuses the two denominators."""
    hoja = {"n_named": 5, "titles": [f"coche {i}" for i in range(5)]}
    got = V.delivery_completeness({"n": 3, "names": ["coche 0", "coche 1", "coche 2"]}, hoja, None)
    assert got["available"] == 5 and got["pct"] == 60 and got["shown_to_model"] is False


def test_la_linea_viva_se_captura_entera_para_que_las_filas_quepan():
    """At 400 characters the truncation cut off exactly where the rows begin, so `shown_candidates`
    always returns empty—which is read as “nothing was shown to it” and is the opposite of the truth."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    assert '"live_line": live[:1200]' in src


# ── And make sure the JUDGE knows, since it is half of what determines the score ───────────────────────────
def test_al_juez_se_le_dice_que_hay_filas_que_nunca_vio():
    """Fixing the number without telling the judge fixes nothing: it assigns the score.

    Without this sentence it would write “massive retention of 11%” about a model that had named 3 of the 5 we
    showed it, with a list of “what it skipped” full of cars that were never in any prompt.
    """
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"delivery_completeness": {"named": 3, "available": 5, "in_sheet": 28,
                                                          "pct": 60, "missed": ["coche 3", "coche 4"]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "TUVO DELANTE 5" in txt and "60 %" in txt
    assert "28" in txt and "23 NUNCA llegaron a su prompt" in txt
    assert "límite NUESTRO" in txt


def test_y_no_se_le_avisa_cuando_lo_vio_todo():
    """Half the sensitivity: a warning that always appears stops being a warning."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"delivery_completeness": {"named": 3, "available": 5, "in_sheet": 5,
                                                          "pct": 60, "missed": ["coche 3"]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NUNCA llegaron a su prompt" not in txt


# ── And make sure truncation does not eat it, which is how the fix remained INERT ──────────────────────────
def test_las_filas_se_leen_de_su_CAMPO_y_no_de_la_prosa_recortada():
    """Measured on 2026-08-28, with V2-420 already deployed and measuring: `shown_to_model` was **False in all six
    rounds**. The cause was not the denominator—it was that the rows lived inside `live_line`, which is
    truncated to 1200 characters, and the TASK list already reaches that limit on its own: the row block begins
    beyond the cut. `shown_candidates` always returned empty, meaning “nothing was shown to it,” which is the
    opposite of the truth and looks exactly like a functioning fix.

    Raising the limit only moves the problem to the next long prompt. A field is not accidentally truncated.
    """
    # The REAL shape of the truncated data: the row header is NOT in `live_line`, because the cut happened
    # earlier. A fixture that leaves it inside reproduces nothing—as shown when dismantling it: with the header
    # present, the test stayed green while reading only the prose, thereby testing the restored defect.
    turno = {"live_line": "TAREAS DE FONDO EN CURSO: " + ("x" * 1174),      # 1200 justos, sin llegar a filas
             "sheet_rows": ["MINI Cooper"]}
    assert _HEAD not in turno["live_line"]
    assert V.shown_candidates([turno]) == ["MINI Cooper"]


def test_un_informe_ANTERIOR_al_campo_se_sigue_leyendo():
    """The prose branch is not discarded: already-saved reports do not have `sheet_rows` and remain the
    only evidence for their rounds."""
    viejo = {"live_line": "TAREAS DE FONDO EN CURSO. " + _HEAD + "FIAT Panda 4x4 — 6.900 €. OJO: la hoja"}
    assert V.shown_candidates([viejo]) == ["FIAT Panda 4x4"]


def test_el_campo_lo_escribe_prompt_context_desde_la_linea_ENTERA():
    """The plumbing: if `prompt_context` does not populate it, the field exists and is always empty."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    # V2-451—rewritten, NOT reverted. The property is the same: the field is written from the COMPLETE TEXT,
    # never from the truncated version saved for reading. What changed is WHICH text that is: there used to be
    # one block with rows (the browser one, in `live`) and now there are two, and in all four rounds after the fix
    # `navegador_task_id` was EMPTY—the four of them; reading only that line would have yielded “nothing was shown”
    # forever. `sp` is the entire prompt, which is where both fit.
    assert '"sheet_rows": _rows_in(sp),' in src, "el campo no se escribe desde el prompt completo"
    assert src.index('"sheet_rows": _rows_in(sp),') > src.index("def _rows_in(")


def test_la_cabecera_que_buscamos_es_la_que_el_MOTOR_escribe():
    """TEXT coupling between two files, and one that breaks silently.

    `shown_candidates` locates the pushed rows by searching for a literal prompt phrase. If someone
    rewrites that phrase in `live_blocks`—a comma, a “from the sheet” that disappears—the read returns empty
    **forever**, and empty here is read as “nothing was shown to it,” which is the opposite of the truth and
    looks exactly like a functioning fix. It already happened once that same night for another reason (the
    truncation of `live_line`), and cost four hours of rounds measured with the old denominator.

    This is not elegant and is the correct option available: while the data travels inside a phrase, someone
    has to monitor the phrase.
    """
    from pathlib import Path
    motor = Path("nucleo/flash/live_blocks.py").read_text(encoding="utf-8")
    assert V._ROWS_HEAD in motor, (
        "la cabecera de filas del prompt cambió y el arnés sigue buscando la vieja: `shown_candidates` "
        "devolverá vacío en todas las rondas, que se lee como «no se le mostró nada»")
