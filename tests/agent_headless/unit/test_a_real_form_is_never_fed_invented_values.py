"""V2-652 — recon ends at a validated field: a REAL form is never advanced with invented values.

Measured live (session 7f77e2cc, 2026-09-10, «pide cita previa en Hacienda»): the worker searched memory
for the operator's DNI, found nothing, and then typed the canonical placeholder NIF «12345678Z» into the
Agencia Tributaria's real appointment form — TWICE — grinding the census-validation modal for minutes,
with `worker_bridge ask` (the exact door section 3b already teaches) never called. The RECON/ASK
discipline existed; what was missing is the rule that a VALIDATED personal field is where recon STOPS:
you cannot look past it with fake data, and a real form submits for real.

Source-level on purpose (the shape of every dispatch_prompts teaching test): the prompt is the mechanism.
"""
from nucleo import dispatch_prompts


def _web_prompt() -> str:
    return dispatch_prompts._web_prompt("pedir cita previa en Hacienda", "")


def test_the_web_prompt_forbids_invented_values_on_a_real_form():
    p = _web_prompt()
    assert "JAMÁS lo avances con valores inventados" in p
    assert "12345678Z" in p, "the measured placeholder is named — it is the exact string workers reach for"


def test_the_rule_says_where_recon_ends_and_what_to_do_instead():
    p = _web_prompt()
    assert "el RECON acaba AHÍ" in p
    assert "nombrando el dato" in p, "the way out is asking or delivering the blocker BY NAME, not retrying"


def test_the_rule_lives_next_to_the_ask_discipline_it_completes():
    """The teaching must sit inside section 3 (RECON → ASK → EXECUTE), after the ask step it points at —
    a rule far from its mechanism is a rule nobody connects."""
    p = _web_prompt()
    assert p.index("PIDE DE GOLPE") < p.index("JAMÁS lo avances") < p.index("EJECUTA hasta el FINAL")
