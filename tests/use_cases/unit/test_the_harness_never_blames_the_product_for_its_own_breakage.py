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
