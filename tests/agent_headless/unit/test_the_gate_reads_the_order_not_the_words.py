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


# ── THE TABLE · every «is_dangerous(<phrase>) is True/False» case of the engine, one row per measured case ──
# Each row's `why` is `<file it came from>::<test it was>`, and its pytest id is `<test it was>[n]`, so a red
# still names the incident that regressed. The incident itself is told once per block below; the file named in
# `why` keeps the rest of that incident's tests (the wiring, the other readers of the same subtraction).

def _rows(why: str, dangerous: bool, phrases) -> list:
    test = why.rsplit("::", 1)[-1]
    return [pytest.param(p, dangerous, why, id=f"{test}[{i}]") for i, p in enumerate(phrases)]


_HERE = "test_the_gate_reads_the_order_not_the_words"

_TABLE = [
    # V2-509 (this file) — a brief that orders LOOKING, written by our own composer, does not ask to pay; a
    # real order to buy or pay still stops. Neither half is safe on its own: a lookup HEAD does not excuse a
    # real order inside it, and a purpose clause is not an adjunct when the errand ORDERS. The reminder
    # clipping (V2-128) is the case this fix mirrors and must not be disturbed.
    *_rows(f"{_HERE}::test_an_errand_that_orders_LOOKING_does_not_ask_to_pay", False, _LOOKUPS),
    *_rows(f"{_HERE}::test_an_order_to_buy_or_pay_still_stops", True, _ORDERS),
    *_rows(f"{_HERE}::test_a_lookup_HEAD_does_not_excuse_a_real_order_inside", True,
           ["busca el IBAN y paga la factura de la luz"]),
    *_rows(f"{_HERE}::test_a_purpose_clause_is_not_an_adjunct_when_the_errand_ORDERS", True,
           ["ve a la tienda para comprar leche"]),
    *_rows(f"{_HERE}::test_the_reminder_clipping_it_mirrors_still_works", False,
           ["recuerdame pagar la factura antes del dia 5"]),
    # V2-645 (this file) — the counterweight of the amount question: an imperative next to it still gates.
    *_rows(f"{_HERE}::test_the_counterweight_an_imperative_next_to_the_question_still_gates", True,
           ["averigua cuánto es y págalo", "transfiere 100 euros al grupo",
            "paga la cuota del viaje", "renueva la suscripción"]),
    # V2-710 T0.4 (this file) — «renovar», «contratar», «suscribir» are money verbs only NEXT TO a commitment
    # object; composing all of `_MONEY_ACT_RE` parked «renueva el gráfico del widget», an order to refresh a
    # chart. «renueva la suscripción del gráfico» DOES gate: verb + commitment object.
    *_rows(f"{_HERE}::test_a_money_VERB_over_a_thing_that_costs_nothing_still_parks_nobody", False,
           ["renueva el gráfico del widget", "cancela la búsqueda que estabas haciendo",
            "búscame un monitor barato de segunda mano"]),
    # V2-707 F0 (this file) — «borrar» gates on its OBJECT, never on the bare verb (the note is below, beside
    # the structural test that guards the pattern).
    *_rows(f"{_HERE}::test_deleting_a_row_we_own_does_not_park_the_worker", False, [
        "So I can see there is an item today at five There's a meeting. I want you to delete that meeting. "
        "And cancel that appointment. And notify the other person",
        "borra la cita de manana a las cinco",
        "delete the meeting tomorrow",
        "elimina ese contacto de la lista",
        "borra el recordatorio del dentista",
        "remove that appointment from my calendar",
    ]),
    *_rows(f"{_HERE}::test_deleting_something_with_no_undo_still_stops", True, [
        "borra la cuenta",
        "borra mi cuenta de Spotify",
        "elimina mi perfil de LinkedIn",
        "delete my account",
        "wipe my hard drive",
        "borra el repositorio",
        "elimina la base de datos",
        "delete everything",
    ]),

    # V2-707 F6 · test_a_complaint_is_not_an_errand — session 080b96a7: six turns complaining that nine agenda
    # rows had been deleted, each one opened a Brain Worker task parked at the irreversibles gate. A past act
    # (an accusation, or a question about whether it happened) is discussed, not ordered. The clause ends at
    # the next `. ! ? ; ,` — at the COMMA on purpose, so a complaint that ENDS IN AN ORDER keeps the order.
    *_rows("test_a_complaint_is_not_an_errand::test_a_past_act_is_discussed_not_ordered", False, [
        "Why did you buy that? I never asked you to.",
        "You did buy it without my permission.",
        "Are you stupid? You just did delete my account.",
        "I never told you to pay that",
        "why did you publish it",
        "Did you pay the bill?",                       # a QUESTION about the past is not an order either
        "You already deleted them",
        "You've paid it already",
        "Me has borrado la cuenta sin permiso",
        "por qué has pagado eso",
        "no te he dicho que pagues nada",
        "acabas de borrar mi cuenta",
        "nunca te he dicho que compres nada",
    ]),
    *_rows("test_a_complaint_is_not_an_errand::test_a_complaint_that_ENDS_IN_AN_ORDER_keeps_the_order", True, [
        "You did delete my account, now delete my Spotify account too",
        "Why did you delete my account? Now delete my Spotify account too",
        "You've already deleted it, now delete my account as well",
        "Me has borrado la cuenta sin permiso, borra la cuenta de Spotify también",
        "por qué has borrado eso, borra mi cuenta de Spotify",
    ]),

    # test_a_link_request_is_not_a_charge — session 81095d8d, «i want to buy Through the Moon (2020), gime the
    # amazon link»: three escalations, all parked as money. A verb under a negation is not an order, and a
    # first-person wish next to a lookup order is not one either; a bare wish with no lookup order keeps its
    # imperative, a negated cap does not disarm the order beside it, and the negation ends with its sentence.
    *_rows("test_a_link_request_is_not_a_charge::test_a_request_for_a_link_or_a_price_is_not_a_charge", False, [
        'Open amazon.es in a real browser for Richard and show it on screen. He just said "amazon.es" '
        "with no further instruction — open the site (Spanish Amazon storefront) and leave it at the "
        "homepage, ready for whatever he wants to do next. Do not search for or buy anything yet.",
        'Find the Amazon listing where Richard can BUY the book "Through the Moon (2020)" — and give him '
        "the direct product link. He wants the URL of the product page where he can buy it, not a "
        "confirmation, not a summary. Report the direct Amazon product link plus title, price and "
        "format. Do NOT make any purchase: just locate and report the link.",
        "i want to buy Through the Moon (2020), gime the amazon link",
        "quiero comprar el libro Through the Moon, dame el enlace de amazon",
        "quiero comprar una freidora de aire, búscame la más barata que llegue a España",
        "no pagues la factura sin avisarme",
        "find the cheapest original edition I can buy in Spain and tell me the delivery date",
        "I'd like to buy a 27 inch monitor — where is it cheapest?",
    ]),
    *_rows("test_a_link_request_is_not_a_charge::test_a_real_charge_still_parks", True, [
        "buy the book Through the Moon on amazon",
        "quiero comprar el libro Through the Moon",
        "paga la factura de la luz",
        "compra el libro y no pagues más de 20 euros",
        "transfiere 500 euros a la cuenta de Iván",
        "renuévame la cuota del gimnasio",
        "ve a la tienda para comprar leche",
    ]),
    *_rows("test_a_link_request_is_not_a_charge::test_the_negation_is_dropped_to_the_end_of_its_sentence_only",
           True, ["Do not buy anything yet. Then pay the invoice."]),

    # V2-778 F0-3 · test_a_negation_governs_only_its_own_act — the negation drop had two holes (self-audit
    # 2026-09-30): words between negation and verb that re-affirm the act (forget / delay / olvidar), and a
    # drop that ran past the comma and ate «compra este». It now ends at the clause boundary.
    *_rows("test_a_negation_governs_only_its_own_act::test_an_order_to_pay_beside_a_negation_still_parks", True, [
        "don't forget to pay the invoice",
        "without further delay pay the invoice",
        "no compres el barato, compra este",
        "no te olvides de pagar la factura",
        "do not buy the red one and buy the blue one",
    ]),
    *_rows("test_a_negation_governs_only_its_own_act::test_a_negated_act_is_still_dropped", False, [
        "do not buy anything yet",
        "Do not search for or buy anything yet.",
        "no pagues la factura sin avisarme",
    ]),

    # demo pass 31, A1 · test_a_modal_buy_inside_a_search_is_not_a_charge — inside a lookup a MODAL buy
    # describes what is looked for; a bare «buy it» keeps its imperative.
    *_rows("test_a_modal_buy_inside_a_search_is_not_a_charge::test_an_order_to_buy_still_stops", True, [
        "buy the cheapest one", "find a monitor and buy it for me",
        "find three models he can buy and then buy the cheapest",
    ]),

    # three-tasks-at-once · test_a_money_word_a_preposition_governs_is_a_topic — «coste DE recarga» in a report
    # errand was parked as «Esto mueve dinero». A money form a preposition governs (de / por / para / en / of /
    # per / for) is the TOPIC; the imperative it shares a spelling with keeps stopping.
    *_rows("test_a_money_word_a_preposition_governs_is_a_topic::"
           "test_a_money_noun_after_a_preposition_is_not_a_charge", False, [
               "Elaborar un informe completo sobre coches eléctricos para uso en ciudad: modelos disponibles, "
               "autonomía real en ciudad, precio, tamaño/manejabilidad, coste de recarga y mantenimiento, ventajas e "
               "inconvenientes frente a un urbano de combustión, y una recomendación razonada por perfiles de uso. "
               "Formato de informe escrito.",
               "Compara el coste por recarga de tres patinetes eléctricos",
               "Write a report on the cost per charge of the main city EVs",
               "Hazme un resumen de los puntos de recarga de Madrid y su precio",
               "Prepara una guía de compra de portátiles para estudiantes",
           ]),
    *_rows("test_a_money_word_a_preposition_governs_is_a_topic::"
           "test_the_imperative_that_shares_the_spelling_keeps_stopping", True, [
               "Recarga el móvil con 20 euros",
               "recarga la tarjeta del transporte",
               "transfiere 500 euros a la cuenta de Quinn",
               "Compra el pan",
               "paga por la compra del pedido",
               "confirma la compra",
               "finalizar compra",
               "charge my card for the order",
               "Haz un informe del coste de recarga y recarga el móvil con 10 euros",
           ]),

    # V2-748 · test_a_row_of_his_own_list_is_not_a_purchase — session 48e85cd5: «añade una nueva tarea, que sea
    # comprar el pan» was read as a purchase and the browser went shopping for bread. The row's TITLE is not the
    # order; «compra» is only excused after «de», and the drop clips at a bare «y» so a second order survives.
    *_rows("test_a_row_of_his_own_list_is_not_a_purchase::test_his_own_turn_is_not_an_irreversible_order", False, [
        "Y ahora añade una nueva tarea, que sea comprar el pan.",
        "Borra la tarea. Cuatro de compra del pan.",
    ]),
    *_rows("test_a_row_of_his_own_list_is_not_a_purchase::test_an_order_that_spends_still_stops", True, [
        "Paga la factura de la luz",
        "Compra el monitor Dell S2722QC",
        "cómprame el monitor",
        "¿puedes pagarla antes del día 5?",
        "Renueva mi cuota del gimnasio de este mes",
        "cancela mi suscripción a Netflix",
        "borra la cuenta",
        "borra mi cuenta de Spotify",
        "transfiere 500 euros a la cuenta de Iván",
        "pon la lista de la compra y paga la factura de la luz",
        "añade una tarea y paga la factura",
        "confirma la compra",
        "finalizar compra",
    ]),
]


def _check(phrase: str, dangerous: bool, why: str) -> None:
    assert danger.is_dangerous(phrase) is dangerous, f"{why}: {phrase}"


@pytest.mark.parametrize("phrase,dangerous,why", _TABLE)
def test_is_dangerous_reads_each_measured_phrase_as_its_incident_decided(phrase, dangerous, why):
    _check(phrase, dangerous, why)


@pytest.mark.parametrize("degenerate", [True, False])
def test_the_disarm_a_classifier_that_answers_one_thing_turns_the_other_half_red(monkeypatch, degenerate):
    """Disarm of the table: with `is_dangerous` answering the same thing for every phrase, exactly the rows that
    expect the other answer go red — so the table reads the live classifier, and both halves carry rows."""
    monkeypatch.setattr(danger, "is_dangerous", lambda text: degenerate)
    assert danger.is_dangerous("delete my account") is degenerate, "the disarm did not land"
    red = []
    for p in _TABLE:
        try:
            _check(*p.values)
        except AssertionError:
            red.append(p.id)
    expected_red = [p.id for p in _TABLE if p.values[1] is not degenerate]
    assert expected_red and red == expected_red


# ── the invariant the docstring states and nothing enforced ──────────────────────────────────────────────

@pytest.mark.parametrize("text", _LOOKUPS + _ORDERS)
def test_moves_money_is_a_SUBSET_of_is_dangerous(text):
    """`moves_money` is documented as «Subset of is_dangerous». It clips the same way for the same
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


# ── V2-645: an AMOUNT QUESTION is not a payment ────────────────────────────────────────────────────────────
# Measured live (the La Mella session, 2026-09-09): «revisa el grupo… y averigua cuánto hay que pagar»
# tripped the money gate three times over a task whose whole job was READING messages. Asking about money
# moves none; an imperative in the same sentence still gates.

def test_the_la_mella_escalation_reads_messages_and_moves_no_money():
    from nucleo import danger
    esc = ("El operador Raquel (también se llama a sí mismo Ricar) tiene en su mensajería un grupo donde "
           "se habla de un viaje a \"la Mella\". Revísalo y averigua cuánto hay que pagar ahora y a qué "
           "email hay que mandar el comprobante.")
    assert not danger.is_dangerous(esc)
    assert not danger.moves_money(esc)


def test_an_amount_question_is_not_a_charge_in_either_language():
    from nucleo import danger
    for t in ("dime cuánto hay que pagar", "cuánto cuesta la reserva",
              "how much do we have to pay for the trip?"):
        assert not danger.moves_money(t), t
        assert not danger.is_dangerous(t), t


# ── V2-710 T0.4 · the two answers of this module cannot contradict each other ───────────────────────────
# Measured 2026-09-16 on the product: `moves_money("transfiere 500 euros a la cuenta de Iván")` was True
# and `is_dangerous` was False, because `_DANGER_RE` is a list of verbs and «transferir» was not on it.
# `dispatch._run_session:1022` reads `is_dangerous`, so the worker started without asking. The fix is
# composition, NOT a longer list of verbs: every verb added to that list parks one more errand that did
# not need parking (V2-707 F0 paid exactly that bill with «borra»).

@pytest.mark.parametrize("text", [
    "transfiere 500 euros a la cuenta de Iván",
    "transfiere 100 euros al grupo",
    "abona la cuota de este mes",
    "recarga el móvil con 20 euros",
])
def test_spending_as_an_ACT_always_reaches_the_gate_that_parks_the_task(text):
    assert danger.moves_money(text) is True, text
    assert danger.is_dangerous(text) is True, (
        f"the two functions of this module disagree about the same sentence, and the one that decides "
        f"whether the task STOPS is the one saying no: {text}")


@pytest.mark.parametrize("text", [
    "cuánto es la factura de la luz",
    "mira mi factura de la luz",
    "enséñame el importe del recibo",
    "cuál es el cargo de ayer",
])
def test_spending_as_a_SUBJECT_is_still_only_a_ROUTING_signal(text):
    """The counterweight, and the reason the composition is by VERB and not by whole function. A bill
    LOOKUP has to reach the browser (`router_guards.money_work_needs_a_browser` reads `moves_money` for
    that), and it must NOT park an errand. Measured before shipping T0.4: composing the two functions
    whole would have parked all four of these."""
    assert danger.moves_money(text) is True, text
    assert danger.is_dangerous(text) is False, f"a lookup about money is not an irreversible act: {text}"


# ── V2-707 F0 · «borrar» gates on its OBJECT, never on the bare verb ───────────────────────────────────
# Same doctrine as everything above, applied to the one verb that had escaped it. Every other entry in
# `_DANGER_RE` names something irreversible WHEREVER it happens — paying moves money, publishing is
# outward-facing. «Borrar» does not: it means one thing on a bank account and another on a row of the
# operator's own agenda, and the bare verb decided for both.
#
# Measured 2026-09-16 (session cb0ac5da, i=7917→7923): «I want you to delete that meeting and notify the
# other person» tripped `delete`, so `dispatch._run_session` PARKED the task before starting anything and
# spoke «Before I go on I need your OK: this could be irreversible». The Brain Worker — which had
# `hbwidget read agenda`, the real row ids and `mensajeria.send_to` — never ran one step. Five minutes, undone.
#
# A widget row is not ungoverned: every mutation crosses `widgets/server_api._dispatch`, where the V2-705
# contract refuses a destructive action with an empty selector and `store.save` snapshots what it
# overwrites. This gate is for what has NO funnel — the open world reached through a browser — so it now
# asks the question that separates them: WHAT is being deleted.

# Its phrase cases are in the table above (the two `test_deleting_…` blocks).

def test_the_bare_verb_no_longer_decides_on_its_own():
    """Structural, and the disarm target: putting `borrar`/`delete` back as a bare alternative re-opens
    the incident. Read on the compiled pattern, not on the source, so a rename cannot hide it."""
    from nucleo.danger import _DANGER_RE
    for bare in ("borra", "borrar", "elimina", "eliminar", "delete"):
        assert not _DANGER_RE.fullmatch(bare), f"«{bare}» is back as a bare irreversible verb"
    assert _DANGER_RE.search("delete account"), "the NAMED object must stay in the pattern"
