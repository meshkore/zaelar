"""Ten minutes of browser time recorded as “the case fails,” when it was the JUDGE (V2-363).

Measured in `two-searches-two-sheets` (2026-08-27, supervisor round). The conversation ran to COMPLETION —641 s,
real browser, two jobs in flight— and the verdict was lost because the judge did not return valid JSON after
its three attempts. Two consequences, and both belong to the harness:

1. THE LOG RECORDED IT AS `FAIL`. The runner also prints “PASSED 0/1” when the round ran but there was no
   verdict, and the supervisor read that line. The log is the list used to decide where to work and
   to read the trends: a harness failure entered there is the instrument blaming the product —
   the same defect that V2-355 cut out of the retention clock, now in my own notebook.

2. AND IT COULD NOT BE DIAGNOSED. The error said “Expecting ',' delimiter: line 22 column 6 (char 1159)” and the
   message attached `raw[:200]` — the first two hundred characters, flawless JSON, one thousand characters before
   the failure location. To see the cause, ten minutes of browser time had to be run again. An instrument failure
   that does not show its cause repeats in full every time.

They are the same decision in two halves: the harness cannot turn its failure into a product verdict, nor
leave it without evidence needed to fix it.
"""
from tests.use_cases.e2e.agent import supervisor as S


def _veredicto(cola: str) -> str:
    """The classification the supervisor makes from the log tail, isolated from running a round."""
    if "PASSED 1/1" in cola:
        return "PASS"
    if "INFRA" in cola or "el juez no devolvió JSON" in cola:
        return "INFRA"
    if "PASSED 0/1" in cola:
        return "FAIL"
    return "INFRA"


def test_un_caso_que_de_verdad_falla_sigue_siendo_FAIL():
    assert _veredicto("  judging…\n✓ report → x.md\nPASSED 0/1 (overall>=4)") == "FAIL"


def test_un_caso_que_pasa_sigue_siendo_PASS():
    assert _veredicto("PASSED 1/1 (overall>=4)") == "PASS"


def test_el_juez_sin_JSON_es_INFRA_aunque_el_runner_imprima_PASSED_0_1():
    """The measured line: both phrases coexist in the same log, and the one below reached the classifier first."""
    cola = ("[judge] el juez no devolvió JSON válido tras 3 intentos\n"
            "✓ report → x.md\nPASSED 0/1 (overall>=4)")
    assert _veredicto(cola) == "INFRA", "una avería del arnés en el diario decide dónde NO se trabaja"


def test_la_clasificacion_del_supervisor_es_LA_MISMA_que_esta():
    """Guard against divergence: if the supervisor changes its order and this test does not, the test would be
    asserting behavior that the code no longer has.

    V2-448 — the classification moved to `_veredicto_de_cola`, so the guard checks THAT function instead of the
    round's individual lines. The property is unchanged, and the ORDER remains what is being protected: “PASSED
    0/1” also appears in the round that the judge could not score, so INFRA must come before FAIL —
    and BLOQUEADO before INFRA, because the tail of a future case contains no “PASSED” of any kind and
    would fall into the `else`, which is INFRA.
    """
    from pathlib import Path
    src = "\n".join(ln for ln in Path("tests/use_cases/e2e/agent/supervisor.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("def _veredicto_de_cola")
    cuerpo = src[i:i + 1400]
    assert "el juez no devolvió JSON" in cuerpo
    assert cuerpo.index('return "BLOQUEADO"') < cuerpo.index('return "INFRA"')
    assert cuerpo.index('return "INFRA"') < cuerpo.index('return "FAIL"'), \
        "el orden IMPORTA: «PASSED 0/1» aparece también en la ronda sin veredicto"


def test_el_error_del_juez_lleva_la_VENTANA_del_fallo_no_el_principio():
    """Without this, diagnosis costs another full browser run."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("tests/use_cases/e2e/agent/judge.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "alrededor del fallo" in src
    assert "raw[:200]" not in src, "el mensaje volvía a enseñar el principio, que es donde nunca está el error"
    assert "char (" in src or 'char (\\d+)' in src, "la posición sale del propio mensaje de la excepción"
