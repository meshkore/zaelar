#
# test_the_gate_reads_the_order_not_the_words.py — V2-509.
#
# The confirm-gate is applied to the TEXT of the escalated request, and that text is written by the BRAIN, not
# by the operator. Measured on `cheapest-monitor__us`: the person said «my work monitor is dying and I need a
# new one, something decent without spending a fortune»; our own brief composer wrote «…available for purchase
# in San Francisco». `purchase` sits bare in `_DANGER_RE`, so the engine tripped its own confirmation gate
# with a word it had just written itself — and with it the whole chain (V2-507/V2-508): session parked, record
# popped, ghost sheet, blind dedup, and a question the operator should never have been asked.
#
# The fix is the MIRROR of V2-128 and works the same way: ask which clause is the ORDER. There, «recuérdame
# PAGAR la factura» orders REMINDING. Here, «investiga monitores EN VENTA» orders LOOKING UP, and the purchase
# only describes the thing being looked for. NOT ONE DETECTION PATTERN WAS LOOSENED.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/test_the_gate_reads_the_order_not_the_words.py
#
import pytest

from nucleo import danger

# The real briefs, verbatim from the rounds.
_LOOKUPS = [
    "Research the current best value desktop monitors available for purchase in San Francisco",
    "Investiga y compara monitores de ordenador para TRABAJO (productividad, oficina) y dime cual comprar",
    "Find and compare 27-inch monitors and tell me which one to buy",
    "Busca un monitor para comprar por menos de 300 euros",
    "Find a used motorcycle for sale under 3000",
    "Compara portatiles en venta y recomiendame uno",
]

# Everything that MUST keep stopping. This half is the whole reason the fix is shaped the way it is: a false
# negative here costs money, a false positive costs a question.
_ORDERS = [
    "Paga la factura de la luz",
    "Compra el monitor Dell S2722QC",
    "comprame el monitor",
    "¿puedes pagarla antes del dia 5?",
    "Renueva mi cuota del gimnasio de este mes",
    "cancela mi suscripcion a Netflix",
    "borra la cuenta",
    "tramitar pedido",
]


@pytest.mark.parametrize("brief", _LOOKUPS)
def test_an_errand_that_orders_LOOKING_does_not_ask_to_pay(brief):
    assert danger.is_dangerous(brief) is False, brief


@pytest.mark.parametrize("order", _ORDERS)
def test_an_order_to_buy_or_pay_still_stops(order):
    assert danger.is_dangerous(order) is True, order


# ── the conjunction: neither half is safe on its own ─────────────────────────────────────────────────────

def test_a_lookup_HEAD_does_not_excuse_a_real_order_inside():
    """«busca el IBAN y PAGA la factura» starts with a lookup verb and orders a payment. If the head alone
    decided, this would walk straight through the gate."""
    assert danger.is_dangerous("busca el IBAN y paga la factura de la luz") is True


def test_a_purpose_clause_is_not_an_adjunct_when_the_errand_ORDERS():
    """«ve a la tienda PARA COMPRAR leche» wears the shape of an adjunct and is an order to buy. If the
    complement alone decided, stripping it would leave a harmless-looking errand."""
    assert danger.is_dangerous("ve a la tienda para comprar leche") is True


def test_the_reminder_clipping_it_mirrors_still_works():
    """V2-128, the case this fix is the mirror of — it must not be disturbed."""
    assert danger.is_dangerous("recuerdame pagar la factura antes del dia 5") is False


# ── the invariant the docstring states and nothing enforced ──────────────────────────────────────────────

@pytest.mark.parametrize("text", _LOOKUPS + _ORDERS)
def test_moves_money_is_a_SUBSET_of_is_dangerous(text):
    """`moves_money` is documented as «Subconjunto de is_dangerous». It clips the same way for the same
    reason, so it had to learn this too — a subset that fires where its superset does not is a new bug, and
    it would ask for money confirmation on an errand the gate itself let through."""
    if danger.moves_money(text):
        assert danger.is_dangerous(text), f"moves_money fired and is_dangerous did not: {text}"


def test_the_detection_patterns_were_not_loosened():
    """The guard on the fix itself. The safe way to do this was to correct WHICH CLAUSE rules, never to
    weaken what counts as a purchase — deleting a word from a safety pattern is how a guard becomes a hole."""
    import inspect
    src = inspect.getsource(danger)
    for verbo in ("comprar", "pagar", "purchase", "buy", "checkout", "delete account"):
        assert verbo in src, f"desapareció «{verbo}» del catálogo de irreversibles"
