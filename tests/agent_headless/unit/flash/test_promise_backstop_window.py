"""V2-132 — a promise whose request was made a turn or two earlier.

`find-theatre-tickets__es` described the task across TWO turns: «get me two tickets for the musical The Lion
King» and then, after zaelar correctly asked for the missing detail, «this Saturday, the afternoon show». The
promise («give me a moment while I look into it») landed on the second one, whose text on its own describes no
task — so the promise backstop, which only ever looked at THIS turn, could not fire. Eight turns of narrating a
search that had never started, with `signals: empty` in the mechanism report.

Two independent gaps, both measured on the transcript before touching anything:
  · `_PROMISE_RE` did not know «me pongo A», «estoy con ello», «sigo con ello» — the plainest ways to say it.
  · buying tickets had no category in the site catalog, so the task classified as `generic`: a worker with NO
    browser, which is why the `widget` signal could not possibly fire.
"""
import pytest

from nucleo.flash import router_guards as g
from nucleo.flash import site_catalog as sc
from nucleo import dispatch


@pytest.mark.parametrize("reply", [
    "Vale, dame un momento que lo miro.",
    "Me pongo a buscarte las dos entradas para El Rey León en Madrid este sábado.",
    "Todavía estoy con ello. La búsqueda de entradas lleva su tiempo.",
    "Vale, tranquilo. Sigo con ello y te digo cuando tenga algo.",
    "Perfecto, te aviso en cuanto tenga novedades.",
])
def test_the_plainest_promises_are_recognised_as_promises(reply):
    assert g.promises_action(reply) is True


def test_the_goal_is_recovered_from_the_window_when_this_turn_has_none():
    window = [
        {"role": "user", "content": "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado."},
        {"role": "assistant", "content": "¿Qué sábado? ¿Qué sesión prefieres? ¿Presupuesto por entrada?"},
    ]
    goal = g.escalate_goal_from_window(window, "Este sábado, la sesión de tarde si hay. Dos entradas en zona media.")
    assert "El Rey León" in goal          # the request itself
    assert "sesión de tarde" in goal      # and the detail that completes it


def test_plain_small_talk_recovers_no_goal():
    """The resolver must come back empty on a conversation that describes no task — it gates an ESCALATION."""
    window = [{"role": "user", "content": "hola, qué tal"}, {"role": "assistant", "content": "bien, ¿y tú?"}]
    assert g.escalate_goal_from_window(window, "vale, gracias") == ""


def test_this_turns_own_request_still_wins():
    window = [{"role": "user", "content": "Consígueme dos entradas para el musical de El Rey León."}]
    assert g.escalate_goal_from_window(window, "busca coches de segunda mano en coches.net") == \
        "busca coches de segunda mano en coches.net"


@pytest.mark.parametrize("text", [
    "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado.",
    "busca entradas para el concierto del sábado",
    "compra dos entradas para el teatro",
    "get me two tickets for the show on Saturday",
])
def test_buying_tickets_needs_a_browser(text):
    assert sc.category_of(text) == "event_tickets"
    assert sc.category_of(text) in sc.TRANSACTIONAL_CATEGORIES
    assert dispatch._classify_kind(text) == "web"
    assert g.looks_like_escalate_task(text) is True


@pytest.mark.parametrize("text", [
    "de primero pedimos entradas para compartir",   # a starter on a menu
    "guárdame el ticket de la compra",              # a receipt
])
def test_the_other_meanings_of_entrada_and_ticket_stay_out(text):
    assert sc.category_of(text) is None


def test_the_escalate_guard_reuses_the_catalog_instead_of_a_second_verb_list():
    """The `kind` classifier and this guard decide the same thing (does this need a browser?) — two lists is
    how they end up disagreeing, which is exactly what this case measured."""
    for text in ["reserva mesa en Casa Lucio esta noche",
                 "resérvame una noche de hotel en Burgos el 20 de septiembre",
                 "consígueme dos entradas para el musical del sábado"]:
        assert g.looks_like_escalate_task(text) is True
        assert dispatch._classify_kind(text) == "web"


# ── V2-147: three «any news?» checks erased the request from the scope ───────────────────────────────────────
#
# The `find-theatre-tickets__es` run (17:04): zaelar proposes stopping the stuck task and trying another
# approach, the operator agrees, zaelar replies «Okay, give me a moment while I look into it» — and nothing
# moves. `promises_action` DID detect the promise; the empty result was the goal. The request was in the window
# and `_needs_real_work` recognised it: the problem was that `max_back` counted ENTRIES, so each status check
# cost two units of the budget and after three checks the original request was out of view.
TEATRO = [
    {"role": "user", "content": "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado."},
    {"role": "assistant", "content": "¿A qué hora te vendría bien? ¿Y qué presupuesto?"},
    {"role": "user", "content": "La sesión de tarde si hay, y en zona media de precio."},
    {"role": "assistant", "content": "Me pongo con ello — busco disponibilidad."},
    {"role": "user", "content": "Vale, avísame."},
    {"role": "assistant", "content": "Sigue en ello — todavía no ha abierto ninguna página."},
    {"role": "user", "content": "Dale un poco más, y si ves que sigue atascado prueba de otra forma."},
    {"role": "assistant", "content": "Te propongo pararlo y probar de otra forma. ¿Vamos con eso?"},
]
ASSENT = "Sí, prueba así. A ver si por esa vía sale algo."


def test_asking_how_it_is_going_does_not_erase_what_was_asked_for():
    goal = g.escalate_goal_from_window(TEATRO, ASSENT)
    assert "El Rey León" in goal


def test_and_the_budget_is_counted_in_the_operators_own_turns():
    """The unit is what matters: with tickets, a normal conversation—asking how it is going—costs twice as much."""
    assert g.escalate_goal_from_window(TEATRO, ASSENT, max_back=4) != ""
    assert g.escalate_goal_from_window(TEATRO, ASSENT, max_back=3) == ""


def test_but_a_conversation_with_no_task_in_it_still_finds_nothing():
    """A longer budget cannot turn a chat into a task."""
    charla = [{"role": "user", "content": "hola, buenas"},
              {"role": "assistant", "content": "¡hola!"},
              {"role": "user", "content": "¿qué tal todo?"},
              {"role": "assistant", "content": "bien"},
              {"role": "user", "content": "me alegro"},
              {"role": "assistant", "content": "gracias"}]
    assert g.escalate_goal_from_window(charla, "vale") == ""


# ── V2-534 open item #1, closed (2026-09-01): a NEGATED clause is not a promise ──────────────────────────────
# Measured over every firing of the promise gate in the operator's sessions (2026-08-17 → 2026-09-01): four of
# ten were a negation next to the matched span («ahora mismo NO tengo ninguna tarea corriendo») — a status
# report, read as a commitment. The rule is structural (a negator inside the SAME clause), never a phrase list.

@pytest.mark.parametrize("reply", [
    "Ahora mismo no tengo ninguna tarea corriendo.",
    "Ahora mismo no hay nada en marcha, tranquilo.",
    "Tampoco voy a abrir nada más por ahora.",
    "Nunca me pongo con eso sin avisarte antes.",
])
def test_a_negated_clause_is_a_status_report_not_a_promise(reply):
    assert g.promises_action(reply) is False


@pytest.mark.parametrize("reply", [
    # The negation lives in ANOTHER clause: clause-bounded on purpose, in both directions.
    "No, ahora mismo lo miro.",
    "Me pongo con ello, no te preocupes.",
    # «nada» is deliberately NOT a negator: «en nada» is a time idiom, and losing a real promise is the
    # expensive direction (six measured minutes of silence, V2-049).
    "En nada te lo busco.",
])
def test_a_negation_in_a_NEIGHBOURING_clause_does_not_unpromise(reply):
    assert g.promises_action(reply) is True


def test_the_voice_gate_reads_the_same_negation_rule():
    """`promise_backstop.committed` (the V2-049 spending gate) shares the clause arithmetic — two copies of
    this decision is how the last one drifted (V2-252). Driven, not grepped."""
    from voice.engine.llm.providers import promise_backstop as pb
    assert pb.committed("Ahora mismo no tengo ninguna tarea corriendo.") is False
    assert pb.committed("Me pongo con ello, no te preocupes.") is True
