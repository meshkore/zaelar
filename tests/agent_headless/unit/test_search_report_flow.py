"""The three brain decisions that wrecked the 2026-08-02 session (search + on-screen report).

Each block captures a regression observed in the real trace (`.meshkore/logs/timeline-latest.jsonl`, 12:51→13:08):

  · `_classify_kind`   — «reflejando el cambio en el widget de informes» was dispatched to the CODE GENERATOR, which
                         spent 3.5 min rewriting `widget.js` for something that was a data op. Filling ≠ programming.
  · `danger`           — «(proyecto compra y venta de motos)» triggered the irreversible-action confirmation gate on
                         a RESEARCH task, which stalled asking for a pointless OK.
  · `dialog.push_user` — STT split the request into 6 chunks; each turn overwrote the previous one and the `raise` of
                         CancelledError carried off the operator's sentence → the brain never saw the word "piscina".
"""
import pytest as _pytest

from nucleo import danger
from nucleo.dispatch import _classify_kind
from nucleo.flash import dialog


# ── filling a widget with data is NOT rewriting its code ─────────────────────────────────────────────────
def test_filling_a_widget_with_data_is_not_code_work():
    # the EXACT brief that Whisper escalated and that ended up in the generator
    assert _classify_kind(
        "finaliza y muestra inmediatamente el informe con los resultados de la búsqueda ampliada de piscinas, "
        "reflejando el cambio en el widget de informes para que el operador pueda verlo") != "code"
    for req in (
        "rellena el widget de resultados con las piscinas encontradas",
        "actualiza la lista del widget de resultados y muéstrala",
        "puebla el widget results con los coches y sus fotos",
    ):
        assert _classify_kind(req) != "code", req


def test_real_code_work_still_routes_to_the_generator():
    for req in (
        "modifica el widget de meteo para que muestre la humedad",
        "añade una columna al widget de agenda",
        "rediseña el panel de resultados con otro layout",
    ):
        assert _classify_kind(req) == "code", req


# ── the confirmation gate is for irreversible ORDERS, not topics mentioned in passing ────────────────────
def test_research_task_is_not_gated_as_irreversible():
    assert not danger.is_dangerous(
        "Termina la búsqueda ampliada del operador (proyecto compra y venta de motos): completa el informe con "
        "los resultados y puebla el widget results con lo encontrado")
    assert not danger.is_dangerous("busca opciones de compra y venta de motos y ponme un informe")
    assert not danger.is_dangerous("prepara una lista de sitios de compraventa de coches")


def test_a_real_irreversible_order_still_asks_for_ok():
    assert danger.is_dangerous("compra la moto que te he dicho")
    assert danger.is_dangerous("paga la factura de la luz")
    assert danger.is_dangerous("publica el anuncio en Wallapop")
    assert danger.is_dangerous("borra la cuenta")
    # context in parentheses cannot HIDE a real order that is present in the main text
    assert danger.is_dangerous("compra el billete (viaje de trabajo, proyecto compra y venta)")


# ── RECURRING commitments and cancellations (V2-133, use-case batch from 2026-08-18) ───────────────────────
def test_a_recurring_charge_asks_for_ok_even_without_the_word_pay():
    """`renew-gym-membership__es`: «renuévame la cuota del gimnasio» moves real money and did NOT contain the verb
    pagar, so it passed without a gate. The TESTER had to stop it live — «no me has dicho cuánto vas
    a pagar ni me has pedido confirmación»."""
    assert danger.is_dangerous("renuévame la cuota del gimnasio")          # REAL imperative: renuev-, not renov-
    assert danger.is_dangerous("renueva mi membresía del gimnasio de este mes")
    assert danger.is_dangerous("contrata la tarifa nueva de la luz")
    assert danger.is_dangerous("renew my gym membership")


def test_unsubscribing_asks_for_ok_because_it_is_irreversible():
    """`cancel-subscription-before-charge__es` states explicitly that asking for confirmation here is the
    CORRECT behavior, not a defect."""
    assert danger.is_dangerous("cancela mi suscripción de Netflix antes de que me cobren")
    assert danger.is_dangerous("dame de baja de Netflix")
    assert danger.is_dangerous("anula el pedido de Amazon")
    assert danger.is_dangerous("cancel my Netflix subscription")


def test_the_commitment_gate_does_not_fire_on_things_that_cost_nothing():
    """A gate that fires where it should not leaves the task stalled waiting for an OK the operator does not understand — the
    2026-08-02 incident that already motivated the two precision fixes to `_order_text`."""
    for req in ("resérvame mesa para 2 esta noche en Casa Lucio",   # reserving a table does not move money
                "cancela la búsqueda que estabas haciendo",         # cancelling ≠ cancelling a commitment
                "renueva el gráfico del widget",
                "búscame un monitor barato de segunda mano"):
        assert not danger.is_dangerous(req), req


def test_a_reminder_about_a_charge_is_a_note_not_an_order():
    """«Apúntame que el jueves tengo que renovar el seguro» (the `remember-and-remind-deadline` case) asks for a
    NOTE. The order is «apúntame», and it does not move money: gating it would leave the reminder waiting for an OK for
    something no one was going to execute."""
    assert not danger.is_dangerous("apúntame que el jueves tengo que renovar el seguro del coche")
    assert not danger.is_dangerous("recuérdame que tengo que renovar la cuota del gimnasio")


# ── lo que el operador dijo no se pierde porque su turno se pisara ────────────────────────────────────────
def test_overlapped_turns_keep_what_the_operator_said():
    """The REAL sequence: 6 STT chunks, 5 cancelled turns. Before the fix only the last reached the model."""
    window: list[dict] = []
    for chunk in (
        "Estamos buscando una piscina Tarragona,",
        "Estamos buscando una piscina Tarragona, que sea especial.",          # STT re-emits with accumulated text
        "Pero que sea pública, o de pago, pero que podamos entrar hoy domingo",
        "sin ser socios, que sea chula, muy grande, con toboganes",
        "me da igual si está en un hotel, en un camping",
        "Dime a ver qué encuentras cerca de Tarragona.",
    ):
        dialog.push_user(window, chunk)

    said = " ".join(m["content"] for m in window if m["role"] == "user").lower()
    for must in ("piscina", "toboganes", "camping", "domingo"):
        assert must in said, f"«{must}» se perdió: el cerebro decidiría sin ese contexto"


def test_accumulating_stt_chunks_do_not_duplicate_the_phrase():
    window: list[dict] = []
    dialog.push_user(window, "Estamos buscando una piscina")
    dialog.push_user(window, "Estamos buscando una piscina en Tarragona")
    dialog.push_user(window, "Estamos buscando una piscina en Tarragona, que sea especial")
    # one entry, the COMPLETE one — repeating the prefix N times is exactly what degrades the small model (V2-032)
    assert len(window) == 1
    assert window[0]["content"] == "Estamos buscando una piscina en Tarragona, que sea especial"


def test_shorter_rechunk_does_not_truncate_what_we_already_have():
    window: list[dict] = []
    dialog.push_user(window, "busca piscinas en Tarragona con toboganes")
    dialog.push_user(window, "busca piscinas")                 # late, shorter chunk
    assert window[0]["content"] == "busca piscinas en Tarragona con toboganes"


def test_a_new_sentence_is_a_new_turn():
    window: list[dict] = []
    dialog.push_user(window, "busca piscinas cerca de Tarragona")
    dialog.push_user(window, "y ponme el informe en pantalla")
    assert len(window) == 2


def test_empty_input_is_not_recorded():
    window: list[dict] = []
    dialog.push_user(window, "   ")
    assert window == []


# ── researching ≠ driving a browser ────────────────────────────────────────────────────────────────────
def test_research_does_not_drive_a_browser():
    """«en internet»/«en la web» say WHERE the data lives, not that Chromium must be opened.

    Observed live on 2026-08-02 with the worker narration already visible: «Investiga EN INTERNET y prepárame un
    informe» matched `_WEB_RE` → the worker spent 7 min clicking coordinates to get around aquopolis.es's cookie
    banner, retrieving a price that `web_search`+`fetch` had returned in seconds in the previous run."""
    for req in (
        "Investiga en internet y prepárame un informe con 3 parques acuáticos cerca de Tarragona",
        "busca en la web cuánto cuesta la entrada y ponme el informe en pantalla",
        "prepara una lista de cuentos infantiles de código abierto",
    ):
        assert _classify_kind(req) == "generic", req


def test_entering_a_real_site_still_goes_to_the_browser():
    """Mode 2 remains unchanged: when a site must be ENTERED and operated, use the browser."""
    for req in (
        "busca motos naked de segunda mano en Wallapop",
        "abre la web del ayuntamiento y descarga el formulario",
        "inicia sesión en LinkedIn y mira los mensajes",
        "automatiza la reserva en el sitio de la ITV",
    ):
        assert _classify_kind(req) == "web", req


# ── A WIDGET AS A DESTINATION IS NOT A WIDGET TO PROGRAM (2026-08-13) ─────────────────────────────────────────
@_pytest.mark.parametrize("text,is_create", [
    # DELIVERY DESTINATION → NOT code. The first is the REAL case that wrecked an entire investigation.
    ("Entrega el resultado montado en el widget results con las 3 secciones claras y los enlaces", False),
    ("pon los hoteles en el widget de resultados", False),
    ("muestra el informe en el panel de resultados", False),
    ("deliver the result into the widget results", False),
    # …and the SAME case with an INDEFINITE article (2026-08-18). The article list only contained the
    # definite articles, so these four slipped through to the generator. The first is verbatim from production.
    ("Monta el resultado en un widget del canvas para que el operador pueda VERLO en pantalla", False),
    ("presenta los datos en una tarjeta", False),
    ("vuelca el informe en unos paneles", False),
    ("render the findings into a widget", False),
    # NOTE: «añade una columna al widget de agenda» is NOT listed here. It is not a create (and `looks_like_create_widget`
    # says False), but it IS code: changing a widget's columns modifies its UI, and `_classify_kind` sends it to the
    # generator via `_MODIFY_CODE_RE`, which is correct. It is checked separately below.
    # A real CREATE → code
    ("créame un widget del tiempo de Soria", True),
    ("hazme un panel con la cotización del bitcoin", True),
    ("monta un widget nuevo para las mareas", True),
    ("build me a widget that tracks my steps", True),          # ojo: «a widget» ≠ preposición castellana «a»
    ("create a new panel for the tides", True),
    ("créame un panel de mareas y entrégalo en el widget results", True),   # las DOS: gana el create real
])
def test_a_widget_named_as_a_destination_is_not_code(text, is_create):
    """A travel investigation (ferry+hotel+restaurant) ended up in the WIDGET GENERATOR, writing the code
    for a new `prepara-ricart-viaje` widget instead of searching. Sole cause: the escalation ended with «Entrega
    el resultado MONTADO en el widget results», and `mont\\w*` is a creation verb with `widget` nine characters away.

    In other words, asking for delivery IN THE RESULTS SHEET diverted the task to the generator — and the results
    sheet is precisely the delivery surface for every investigation: the failure lived on the product's busiest path.

    The distinction is not a list of exceptions: it is GRAMMAR. After a destination preposition («en el
    widget», «al panel», «into the widget») the widget is the PLACE where the result goes, not the thing being
    built. Same family as V2-081 (mostrar→construir) and «proyecto» alone (2026-08-12)."""
    from nucleo.flash import router as _router
    assert _router.looks_like_create_widget(text) is is_create
    if not is_create:
        # and the important consequence: the dispatcher does NOT send it to the generator backend
        assert _classify_kind(text) != "code"


def test_gather_and_show_never_reaches_the_widget_generator():
    """THE REAL CASE, verbatim from production (session 82e2ba11, 2026-08-18). The operator asked by voice for «muéstrame una
    ficha técnica y una foto» of a car; FlashBrain reformulated the escalation, ending it with «Monta el resultado
    en UN widget del canvas…», and it fell into the GENERATOR again: three minutes writing a
    `investiga-ferrari-f80` de un solo uso, en vez de buscar y entregar en la hoja de resultados.

    It is the SAME failure as on 2026-08-13 (above), with the article changed: the neutralization list contained
    `el|la|los|las`, not `un|una|unos|unas`. The grammar does not depend on the article — «en un widget» is still the
    PLACE where the result goes. And the model itself writes the phrase, so the operator cannot avoid it."""
    from nucleo.flash import router as _router
    req = ("Investiga el Ferrari F80 (último modelo de Ferrari lanzado al mercado) y prepara una FICHA TÉCNICA "
           "completa (motor, potencia, 0-100, velocidad máxima, prestaciones, precio) junto con una FOTO REAL del "
           "coche. Monta el resultado en un widget del canvas para que el operador pueda VERLO en pantalla: la "
           "ficha técnica con los datos y al menos una fotografía del Ferrari F80. El operador quiere ver cómo es "
           "el coche.")
    assert _router.looks_like_create_widget(req) is False
    assert _classify_kind(req) != "code"          # → generic → research brief → `results` sheet


@_pytest.mark.parametrize("text", [
    "monta esto en un widget nuevo",
    "pon el informe en una tarjeta nueva",
])
def test_an_explicit_new_widget_survives_the_destination_rule(text):
    """The ONLY real exception to the destination rule, which must be preserved: «en un widget NUEVO» does request a
    new one. Here the destination preposition and the create coexist in the same sentence, and the create wins — if
    neutralization swallowed it, expanding the article list would have changed a false positive into a false negative."""
    from nucleo.flash import router as _router
    assert _router.looks_like_create_widget(text) is True
    assert _classify_kind(text) == "code"


def test_modifying_a_widgets_ui_is_still_code():
    """The other side: the DESTINATION fix must not swallow a real modification. Changing a widget's columns touches
    its UI, that is, code, even if the phrase contains «al widget» — `_MODIFY_CODE_RE` routes it, not the create
    detector."""
    from nucleo.flash import router as _router
    t = "añade una columna al widget de agenda"
    assert _router.looks_like_create_widget(t) is False       # it is not CREATE
    assert _classify_kind(t) == "code"                        # but it is CODE


# ── the imperative with a CLITIC, and the reminder that is not an order (V2-128, 2026-08-18) ──────────────────────────
def test_an_imperative_with_a_clitic_still_asks_for_ok():
    """In Spanish, the form that REALLY gives an order has the pronoun attached. `_DANGER_RE` compared
    bare forms with `\\b`, so they all escaped the gate. This is the third place where the same oversight bites
    (it already happened with «resérvame» and «renuévame»): the pattern is written with the infinitive, while the
    operator speaks in the imperative."""
    for req in ("págala tú antes del día 5", "cómpralo ya", "bórralo de mi cuenta",
                "cancélala antes del día 15", "publícalo en Wallapop", "págamelo con la tarjeta"):
        assert danger.is_dangerous(req), req


def test_a_clitic_is_REQUIRED_so_ordinary_conjugations_do_not_gate():
    """Without requiring a clitic, «compras»/«publicas»/«cancelan» —which are not orders— would enter through the same door."""
    for req in ("¿cuánto compras al mes?", "normalmente publicas los lunes", "cancelan el vuelo mañana"):
        assert not danger.is_dangerous(req), req


def test_asking_to_be_REMINDED_of_a_payment_is_not_an_order_to_pay():
    """The reminder trimming was only handled by `_COMMITMENT_RE`: «recuérdame PAGAR la factura» triggered the gate through
    `_DANGER_RE` and left a confirmation waiting for an OK for a payment no one was going to execute."""
    assert not danger.is_dangerous("recuérdame pagar la factura de la luz antes del día 5")
    assert not danger.is_dangerous("apúntame que tengo que pagar el IBI")


def test_a_real_order_AFTER_a_reminder_clause_is_not_swallowed():
    """The trimming extends to the end of the SENTENCE, not the end of the text: with `.*`, the real order
    that followed was lost."""
    assert danger.is_dangerous("recuérdame pagar la factura. Y de paso págala tú")
