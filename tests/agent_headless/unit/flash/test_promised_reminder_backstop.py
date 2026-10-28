"""V2-146 (`remember-and-remind-deadline`) — “I’ll remind you on Wednesday” with `scheduled_jobs.created` EMPTY.

Three turns, and both in which zaelar says it promises the reminder: “I’m going to… schedule the reminder for
Wednesday” and “yes, it’s done… I’ll remind you on Wednesday.” There was no cron. The tag executor works —V2-134
verified it with its own tests— and the prompt has explicitly requested it since V2-121; what was missing was doing
it when the model promises it in prose and emits no tag.

An alert-scheduling backstop has to be cautious with dates: a wrongly dated alert is not noticed until the day it
does not ring (V2-121). That is why `scheduler.parse_when` returns "" for any expression that is not unambiguous,
and when there are TWO days in the same sentence — “I have to renew… on THURSDAY, and remind me on WEDNESDAY,” which
contains both — it refuses rather than choosing. In the reply, ties can be broken, not by guessing but by position:
what comes AFTER “I’ll remind you” is when the alert belongs.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import asyncio
import time

import pytest

from nucleo.pulse import scheduler
from nucleo.cli import turn
from nucleo.flash import router_guards as g
from tests.brain import harness as H


ASK = "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles."
REPLY = "Sí, ya está. Te he apuntado que el jueves renuevas el seguro del coche, y te avisaré el miércoles."
# Wednesday 19 Aug 2026, 02:00 — the default 09:00 has not gone by yet.
NOW = time.mktime((2026, 8, 19, 2, 0, 0, 0, 1, -1))


# ── resolving a spoken moment ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("recuérdamelo el miércoles", "2026-08-19 09:00"),      # today, hour still ahead
    ("recuérdamelo el jueves", "2026-08-20 09:00"),
    ("avísame mañana", "2026-08-20 09:00"),
    ("recuérdamelo mañana a las 8", "2026-08-20 08:00"),
    ("el viernes a las 18:30", "2026-08-21 18:30"),
    ("el día 15", "2026-09-15 09:00"),
    ("remind me tomorrow at 7", "2026-08-20 07:00"),
])
def test_an_unambiguous_moment_resolves(text, expected):
    assert scheduler.parse_when(text, NOW) == expected


@pytest.mark.parametrize("text", [
    "recuérdamelo esta tarde",
    "avísame pronto",
    "cuando puedas",
    "recuérdamelo el día 40",
    ASK,   # TWO weekdays: which one is the reminder is what we cannot know here
])
def test_and_an_ambiguous_one_refuses(text):
    """Refusing sends it back to whoever has the context. Scheduling on a guessed date is worse than not
    scheduling, because the operator believes it is set."""
    assert scheduler.parse_when(text, NOW) == ""


def test_a_resolved_moment_is_something_parse_schedule_accepts():
    """The two have to agree: whatever `parse_when` emits must be a spec the scheduler can actually take."""
    spec = scheduler.parse_when("recuérdamelo el jueves", NOW)
    assert scheduler.parse_schedule(spec, NOW)["type"] == "once"


# ── the promise, and where its day is ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("reply", [
    REPLY,
    "Voy a apuntarte la cita para el jueves y programar el recordatorio para el miércoles.",
    "Te lo recuerdo el viernes a las 18:30.",
])
def test_the_day_is_the_one_that_follows_the_promise(reply):
    assert g.promises_a_dated_reminder(reply, ASK) != ""


@pytest.mark.parametrize("reply,ask", [
    ("Te aviso en cuanto lo tenga.", "busca un hotel"),          # a worker finishing, not a scheduled notice
    ("Sigo con ello, te aviso cuando esté.", "busca un hotel"),
    ("Te aviso pronto.", "mira el precio"),
    ("Perfecto, hecho.", "pon música"),
    ("He apuntado que el jueves renuevas el seguro.", "apúntame el jueves"),   # noted, nothing promised
])
def test_and_these_promise_no_dated_reminder(reply, ask):
    assert g.promises_a_dated_reminder(reply, ask) == ""


@pytest.fixture
def fresh_db():
    """An isolated workspace, database and widget store (the typed turn's harness), with the REAL scheduler: the
    harness stubs it, and it is put back by hand INSIDE the isolation so the harness's own restore stays last."""
    real_create, real_cancel = scheduler.create, scheduler.cancel
    with H.Isolated("es"):
        stub_create, stub_cancel = scheduler.create, scheduler.cancel
        scheduler.create, scheduler.cancel = real_create, real_cancel
        try:
            yield
        finally:
            for job in scheduler.list_jobs(active_only=True):
                scheduler.cancel(job.get("name") or "")
            scheduler.create, scheduler.cancel = stub_create, stub_cancel


class _AsksForTheCron:
    async def stream(self, *_a, **_kw):
        yield "Hecho, te aviso el jueves."
        yield ('[[cron.create]]{"schedule":"2026-09-03 09:00","prompt":"renovar el seguro",'
               '"name":"seguro"}[[/cron.create]]')

    async def complete(self, *_a, **_kw):
        return ""


def test_and_it_does_not_duplicate_one_the_model_did_ask_for(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.llm.fast_client.FastClient", _AsksForTheCron)
    asyncio.run(turn.run_turn(ASK, sid="t-v146b", ingest=False, execute=True))
    turn.reset("t-v146b")
    names = [j.get("name") for j in scheduler.list_jobs(active_only=True)]
    assert "seguro" in names
    assert "aviso" not in names


# ── V2-151: the promise the pattern could not see, and the day it would have picked ──────────────────────────
#
# The run this came from said, in one turn: «Apunto la cita para el jueves y te programo UN recordatorio para el
# miércoles a media mañana» — and `scheduled_jobs.created` came back empty AGAIN. Two independent faults, and the
# second only becomes reachable once the first is fixed, which is why both are pinned here.
REPLY_151 = "Apunto la cita para el jueves y te programo un recordatorio para el miércoles a media mañana."


@pytest.mark.parametrize("reply", [
    REPLY_151,                                                    # the exact wording that got away
    "Te programo un recordatorio para el miércoles.",
    "Te pongo un recordatorio para el miércoles.",
    "Te creo un aviso para el miércoles.",
    "Te dejo puesto un aviso para el miércoles.",
    "Te dejo programado un aviso para el miércoles.",
    "I'll set a reminder for Wednesday.",
])
def test_a_promise_is_a_verb_plus_a_noun_not_a_particular_article(reply):
    """The first shape of `_REMIND_VERB_RE` spelled the article out («program\\w* el recordatorio»), so «te
    programo UN recordatorio» — the most natural way to say it — missed by one word. Five of seven natural
    phrasings missed when this was measured."""
    assert g.promises_a_dated_reminder(reply, ASK) != ""


def test_but_a_declined_reminder_is_not_a_promise():
    """The determiners are listed one by one instead of `\\w+` for this: a sentence that says it is NOT setting a
    reminder must never end up setting one."""
    assert g.promises_a_dated_reminder("No te pongo ningún recordatorio, apúntalo tú.", ASK) == ""


@pytest.mark.parametrize("text,expected", [
    ("el miércoles a media mañana", "2026-08-19 09:00"),
    ("para el miércoles a media mañana", "2026-08-19 09:00"),
    ("el jueves por la mañana", "2026-08-20 09:00"),
    ("el jueves a las 9 de la mañana", "2026-08-20 09:00"),
    ("mañana", "2026-08-20 09:00"),
    ("mañana por la mañana", "2026-08-20 09:00"),      # the ADVERB survives; only the noun is dropped
])
def test_the_noun_morning_does_not_hijack_the_day(text, expected):
    """«mañana» is two words in Spanish. The noun (always determined: la/media/esta/por la/de la) was matching
    the adverb branch and short-circuiting the weekday, so «el miércoles a media mañana» resolved to THURSDAY —
    a reminder that is set, reported as set, and rings on the wrong day."""
    assert scheduler.parse_when(text, NOW) == expected


@pytest.mark.parametrize("text", ["media mañana", "esta mañana", "por la mañana"])
def test_and_a_morning_with_no_day_still_refuses(text):
    """Dropping the noun must not turn a dayless expression into a resolvable one — it names an hour, not a day."""
    assert scheduler.parse_when(text, NOW) == ""


def test_the_whole_turn_end_to_end(monkeypatch):
    """Both faults on the one sentence: the promise is seen, and the day it resolves to is the one promised."""
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    assert g.promises_a_dated_reminder(REPLY_151, ASK) == "2026-08-19 09:00"


# ── V2-153: the same alert, promised in two turns, was scheduled TWICE ───────────────────────────────────────
#
# The 16:56 run finally left the mechanism NOT empty —which was what V2-151 was pursuing— and with two identical crons
# inside: both `2026-08-26 09:00`, one with the actual prompt request and the other with “Perfect, thanks.
# That way I won’t miss it,” because the backstop fired on the promising turn and again on the reaffirming turn.
# Measured against the real scheduler: two `create()` calls with the same spec both return ok and leave two live jobs.
def _n(text: str) -> str:
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text) if not _ud.combining(c)).lower()


REPLY_T1 = "Voy a apuntarlo en tu agenda para el jueves y configurar un recordatorio para el miércoles."
REPLY_T2 = "De nada. Queda anotado y te aviso el miércoles para que no se te olvide."
ACK = "Perfecto, gracias. Así no se me pasa."


# ── V2-159: the alert already existed; the OTHER half was missing ───────────────────────────────────────────
#
# La corrida del 18:56 dejó por fin UN solo cron, el miércoles correcto y con la petición del operador de prompt
# —los arreglos de V2-151 y V2-153 aterrizaron— y aun así falló: «el sistema solo recordó el CUÁNDO (el cron)
# pero perdió el QUÉ (la memoria durable), resultando en un aviso vacío». El caso exige LAS DOS mitades: el
# compromiso REGISTRADO y el aviso programado. zaelar dijo «Te apunto la renovación del seguro del coche para el
# jueves» y el mecanismo no mostró ni una data-op de agenda.
#
# La regla ya estaba en el prompt con todas las letras («si el compromiso tiene fecha, además apúntalo en su
# agenda… son dos cosas distintas, el apunte y el aviso, y el operador pide las dos»). Lo que faltaba era el
# backstop, igual que faltó el del aviso en V2-146.
REPLY_BOTH = ("Te apunto la renovación del seguro del coche para el jueves y te programo un recordatorio "
              "para el miércoles.")


# ── V2-167: an alert arrives BEFORE the thing it alerts about ─────────────────────────────────────────────
#
# La corrida del 19:46 dejó el caso «más limpio de los cinco» y aun así inútil: DOS turnos, todo comprobable, y
# el trabajo programado decía `2026-08-26 09:00` para avisar de algo del JUEVES 2026-08-20 — seis días TARDE.
# No es un fallo del parser: `parse_when("el miercoles")` en miércoles responde el miércoles QUE VIENE, que es
# la lectura correcta de esa frase suelta. Lo que el parser no puede saber es la única restricción que tiene un
# recordatorio, y por eso la corrección vive donde SÍ están las dos fechas.
import datetime as _dt


def test_a_reminder_that_lands_after_the_event_is_pulled_back_a_week():
    now = _dt.datetime(2026, 8, 19, 8, 0)                       # miércoles, antes de las nueve
    got = g.reminder_before("2026-08-26 09:00", "2026-08-20 09:00", now=now)
    assert got == "2026-08-19 09:00"                            # el miércoles ANTERIOR, que es hoy


def test_and_if_that_day_has_already_gone_by_it_fires_promptly():
    """Preguntado a las 19:46 del propio miércoles: el día que nombró es hoy y su hora pasó. Avisarle ahora es
    la lectura útil de lo que pidió; la alternativa medida —el miércoles siguiente— no avisa de nada."""
    now = _dt.datetime(2026, 8, 19, 19, 46)
    got = g.reminder_before("2026-08-26 09:00", "2026-08-20 09:00", now=now)
    assert _dt.datetime.strptime(got, "%Y-%m-%d %H:%M") > now
    assert _dt.datetime.strptime(got, "%Y-%m-%d %H:%M") < _dt.datetime(2026, 8, 20, 9, 0)


def test_but_a_reminder_that_was_already_early_is_left_alone():
    """El límite: sin esto, «corrige el aviso» y «adelántalo siempre» pasan igual."""
    now = _dt.datetime(2026, 8, 19, 8, 0)
    assert g.reminder_before("2026-08-19 09:00", "2026-08-20 09:00", now=now) == "2026-08-19 09:00"


def test_and_with_no_dated_commitment_there_is_nothing_to_be_before():
    assert g.reminder_before("2026-08-26 09:00", "") == "2026-08-26 09:00"


# ── V2-176: the WHAT is not in the turn that fixes the WHEN ───────────────────────────────────────────────
#
# Corrida real de `remember-and-remind-deadline`, 2026-08-20 01:01 (overall 1/5). El operador dice la
# obligación una vez y luego gasta dos turnos corrigiendo la fecha; para cuando la fija, el sujeto ya no está
# en su turno:
#
#   t1  «Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles»
#   t3  «El jueves de esta semana tengo que renovar el seguro del coche. Apúntalo y recuérdamelo el miércoles»
#   t4  «Sí, perdona, me he liado con las fechas. Me refiero al jueves que viene, 27. Recuérdamelo el 26…»
#
# Leyendo SOLO t4, el aviso quedó programado con el texto «Sí, perdona, me he liado con las fechas. Me refiero
# al jueves que viene, 27» — o sea que el miércoles el trabajo le lee al operador su propia disculpa. Y la
# agenda se quedó vacía (`n_after: 1`, solo el aviso) porque el «Apúntalo» iba en t3.
#
# Es la MISMA forma de fallo que V2-132 ya arregló para la escalada: el turno que completa una petición no es
# el que la describe.
_W_T1 = "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles."
_W_T3 = "El jueves de esta semana tengo que renovar el seguro del coche. Apúntalo y recuérdamelo el miércoles."
_W_T4 = ("Sí, perdona, me he liado con las fechas. Me refiero al jueves que viene, 27. "
         "Recuérdamelo el miércoles 26 por la mañana, porfa.")
_W_R4 = "Te lo dejo apuntado en la agenda y programado el aviso para el miércoles 26 por la mañana."


def _window(*user_turns):
    out = []
    for t in user_turns:
        out.append({"role": "user", "content": t})
        out.append({"role": "assistant", "content": "…"})
    return out


def test_and_a_turn_that_asks_for_nothing_does_not_inherit_an_old_subject(fresh_db, monkeypatch):
    """La guarda que impide que esto se convierta en «todo hereda de todo»: solo se mira atrás cuando un turno
    ANTERIOR también pidió aviso o apunte, que es lo que hace de este turno una CONTINUACIÓN."""
    monkeypatch.setattr(scheduler.time, "time", lambda: time.mktime((2026, 8, 20, 9, 0, 0, 0, 1, -1)))
    win = _window("¿qué tiempo hace mañana?", "gracias")
    assert g.commitment_from_window(win, "Recuérdame el viernes lo del taller") == \
        g.commitment_clause("Recuérdame el viernes lo del taller")


# ── V2-194: the agenda entry cannot be written twice either ──────────────────────────────────────────────
#
# Del sandbox de la corrida del 2026-08-20 02:34, leído de su propio workspace:
#
#   meetings: [{"title": "Renovar seguro del coche",    "date": "2026-08-27", …},
#              {"title": "Renovar el seguro del coche", "date": "2026-08-27", …}]
#
# El MISMO compromiso, el MISMO día, dos veces: una es la data-op del modelo y la otra el backstop, disparado
# en un turno posterior. Su puerta —«solo si ESTE turno no hizo ya la data-op»— no puede ver una data-op de un
# turno ANTERIOR. El hermano tiene esta protección desde V2-153, y aquí es peor sin ella: un aviso duplicado se
# oye dos veces, una cita duplicada se VE, y se queda.
#
# El chequeo vive JUNTO A LA ESCRITURA (`note_backstop.note_to_file`) y no dentro de `dated_note_backstop`, que es una decisión
# pura sobre dos cadenas y un reloj — meterle una lectura de estado global hizo que nueve de sus propios tests
# dependieran del orden en que corrieron los anteriores.
def _agenda(monkeypatch, meetings):
    from widgets import store as _store
    monkeypatch.setattr(_store, "load", lambda wid: {"meetings": meetings} if wid == "agenda" else {})


NOTA = {"title": "renovar el seguro del coche", "date": "2026-08-27"}


def test_a_commitment_already_in_the_agenda_is_not_written_again(monkeypatch):
    _agenda(monkeypatch, [{"title": "renovar el seguro del coche", "date": "2026-08-27"}])
    assert g.already_in_agenda(NOTA) is True


def test_and_an_article_does_not_defeat_the_comparison(monkeypatch):
    """Las dos entradas medidas se diferenciaban en un «el». Una comparación que un artículo derrota no es una
    comparación."""
    _agenda(monkeypatch, [{"title": "Renovar seguro del coche", "date": "2026-08-27"}])
    assert g.already_in_agenda(NOTA) is True


def test_but_the_same_thing_on_ANOTHER_day_is_a_different_commitment(monkeypatch):
    _agenda(monkeypatch, [{"title": "renovar el seguro del coche", "date": "2026-12-01"}])
    assert g.already_in_agenda(NOTA) is False


def test_and_something_else_the_same_day_does_not_block_it(monkeypatch):
    """La sensibilidad: sin esto, «no dupliques» y «no apuntes nada si ya hay algo ese día» pasan igual — y el
    segundo perdería la mitad de los encargos de un día ocupado."""
    _agenda(monkeypatch, [{"title": "cita con el dentista", "date": "2026-08-27"}])
    assert g.already_in_agenda(NOTA) is False


def test_and_an_unreadable_agenda_fails_OPEN(monkeypatch):
    """Respaldar la promesa gana a dejarla caer: si no se puede leer la agenda, se apunta."""
    from widgets import store as _store

    def _boom(_wid):
        raise RuntimeError("no se puede leer")
    monkeypatch.setattr(_store, "load", _boom)
    assert g.already_in_agenda(NOTA) is False


# ── V2-167 · the promise that does NOT name the day, and the day found only in the operator’s sentence ─────
#
# Ronda 11 de `remember-and-remind-deadline` (2026-08-20 10:26), tres turnos enteros:
#
#     TESTER  Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles.
#     ZAELAR  Voy a apuntarlo y programarte el aviso.
#
# Veredicto: «confirmó una acción que nunca ejecutó (ni guardó el dato, ni programó el aviso)», `resultado 1`
# `mecanismo 1`, `scheduled_jobs.created` vacío. El backstop de la NOTA disparaba; el del AVISO devolvía None.
#
# La causa: la respuesta promete el aviso sin nombrar día («programarte el aviso»), así que el desempate por
# POSICIÓN sobre la respuesta no tenía nada que leer, y la frase del operador se le entregaba ENTERA a
# `parse_when`, que ve dos días y se niega — con razón, como parser general. Pero esa frase no es ambigua para
# nadie: el día pertenece al verbo al que sigue. El módulo ya sabía la regla y la aplicaba solo a una de las dos
# voces.
REPLY_NO_DAY = "Voy a apuntarlo y programarte el aviso."


def test_the_day_can_live_only_in_what_the_OPERATOR_said(monkeypatch):
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    assert g.promises_a_dated_reminder(REPLY_NO_DAY, ASK) == "2026-08-19 09:00"


@pytest.mark.parametrize("reply", [
    "Voy a apuntarlo y programarte el aviso.",
    "Te programo el aviso.",
    "Vale, dejo puesto el recordatorio.",
])
def test_it_does_not_depend_on_how_the_model_words_the_promise(reply, monkeypatch):
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    assert g.promises_a_dated_reminder(reply, ASK) == "2026-08-19 09:00"


def test_a_date_BEFORE_the_ask_verb_still_refuses_here(monkeypatch):
    """El límite, escrito a propósito: leer por posición es leer por posición. «El martes recuérdame lo del
    seguro» pone la fecha ANTES del verbo, así que este camino no la ve y cae al de siempre (la frase entera),
    que sí la resuelve porque ahí solo hay un día. Adivinar el orden de las palabras es como un backstop empieza
    a programar cosas que nadie pidió."""
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    assert g._asked_reminder_moment("El martes recuérdame lo del seguro.") == ""
    assert g.promises_a_dated_reminder("Te lo recuerdo.", "El martes recuérdame lo del seguro.")


def test_and_a_reply_that_promises_nothing_resolves_nothing(monkeypatch):
    """Sin esto, «leer la frase del operador» y «programar siempre que el operador diga una fecha» pasan el
    mismo test. La promesa sigue siendo el disparador."""
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    assert g.promises_a_dated_reminder("Vale, entendido.", ASK) == ""
    assert g.promises_a_dated_reminder("No te lo puedo recordar, no tengo agenda.", ASK) == ""


@pytest.mark.parametrize("clause,only_a_date", [
    ("El martes", True),
    ("el jueves que viene", True),
    ("mañana", True),
    ("Apúntame que el jueves tengo que renovar el seguro del coche", False),
    ("llamar al taller", False),
])
def test_what_counts_as_only_a_date(clause, only_a_date):
    assert g.clause_is_only_a_date(clause) is only_a_date


# ── V2-167 round 12 (2026-08-20 12:39) · the operator requests the alert in the SUBJUNCTIVE ────────────────
#
# Conversación medida, cuatro turnos, `mecanismo 1` y `scheduled_jobs.created` VACÍO — con la auditoría del
# stream LIMPIA (cero `is_error`), o sea que no había ninguna excepción comiéndose nada: fallaba la lógica.
#
#   TESTER  Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles.
#   ZAELAR  Perfecto, lo anoto. ¿A qué hora del jueves te viene bien la renovación?
#   TESTER  El jueves de esta semana, por la mañana me vale para el aviso del miércoles.
#   ZAELAR  ¿el jueves al que te refieres es mañana? Hoy es jueves 20. ¿Quieres la cita para el jueves 27?
#   TESTER  Me refería al próximo jueves, el 27. Que me AVISES el miércoles 26 por la mañana.
#   ZAELAR  Claro, lo dejo apuntado y programo el aviso.
#   ZAELAR  ¡Hablamos! Ya lo tienes todo listo. 👋
#
# La causa: `_REMIND_ASK_RE` solo conocía el INDICATIVO («me avisas»). Pedir algo tras «que» pide subjuntivo en
# español —«que me avises», «que me lo recuerdes»— y esa no es una variante rara: es la forma natural de pedirlo.
# Sin reconocerla, el día del aviso no se podía leer por posición, la frase entera iba a `parse_when` (que ve
# «jueves 27» y «miércoles 26» y se niega, con razón) y no se programaba nada.
#
# Es el mismo fallo que V2-151 ya pagó en este módulo, por eso el ensanche es MORFOLÓGICO y no una frase más
# en una lista.
ASK_SUBJ = ("Perdona, me lié con el día. Me refería al próximo jueves, el 27. Que me avises el miércoles 26 "
            "por la mañana. ¿Me lo dejas apuntado y me mandas el recordatorio ese día?")
REPLY_R12 = "Claro, lo dejo apuntado y programo el aviso."
# Jueves 20 ago 2026, 09:00 — el día en que se midió la corrida.
NOW_R12 = time.mktime((2026, 8, 20, 9, 0, 0, 0, 1, -1))

WIN_R12 = [
    {"role": "user", "content": ASK},
    {"role": "assistant", "content": "Perfecto, lo anoto. ¿A qué hora del jueves te viene bien la renovación?"},
    {"role": "user", "content": "El jueves de esta semana, por la mañana me vale para el aviso del miércoles."},
    {"role": "assistant", "content": "¿el jueves al que te refieres es mañana? ¿Quieres la cita para el 27?"},
    {"role": "user", "content": ASK_SUBJ},
]


@pytest.mark.parametrize("text", [
    "Que me avises el miércoles 26 por la mañana.",
    "que me lo recuerdes el miércoles",
    "que me recuerdes lo del seguro el miércoles",
    "¿me mandas el recordatorio ese día?",
])
def test_the_operator_can_ask_in_the_subjunctive(text):
    assert g._REMIND_ASK_RE.search(g._norm_txt(text)), "pedirlo tras «que» es la forma natural en español"


@pytest.mark.parametrize("text", [
    "recuérdamelo el miércoles",
    "me avisas el martes",
    "avísame mañana",
    "remind me tomorrow",
])
def test_and_the_forms_that_already_worked_still_do(text):
    assert g._REMIND_ASK_RE.search(g._norm_txt(text))


def test_the_notice_day_now_resolves_from_the_subjunctive_ask(monkeypatch):
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW_R12)
    assert g._asked_reminder_moment(ASK_SUBJ) == "2026-08-26 09:00"


# ── V2-356: and the other field of the same tag ────────────────────────────────────────────────────────────
#
# V2-214 blindó el `prompt` de la tag del modelo porque «el backstop ya componía la forma segura y la tag del
# modelo entraba cruda por la otra puerta». Dejó el `schedule` entrando igual de crudo, y ése es el que
# decide si el aviso suena.
#
# Medido en `remember-and-remind-deadline` (2026-08-27, sexta ronda del supervisor, 2/5). El operador: «el
# jueves tengo que renovar el seguro… recuérdamelo el miércoles». El prompt del turno llevaba delante la lista
# fechada de los próximos días —«wednesday 2026-09-02»— y el trabajo salió con:
#
#     schedule "2026-08-27 08:08"   ← HOY, cinco minutos después de la conversación
#
# Seis días ANTES del evento y el mismo día de hablarlo. Un aviso que dispara en el turno siguiente no es un
# recordatorio, es ruido.
#
# NI EL PARSER NI EL BACKSTOP FALLARON, y comprobarlo fue lo que localizó el defecto: `parse_when('el
# miércoles')` da `2026-09-02 09:00`, `promises_a_dated_reminder` da lo mismo, y el backstop de arriba ni
# siquiera corre cuando el modelo SÍ emite la tag. La fecha la escribió el modelo con la buena delante — y
# ésta es la casa donde eso se responde con código, no con más prompt (V2-305).
#
# EL CORTE ES ESTRECHO A PROPÓSITO porque la evidencia es un caso: solo se corrige si la tag dispara HOY **y**
# el resolvedor determinista tiene una respuesta inequívoca que cae otro día. Una fecha futura no se toca
# aunque no coincida —el modelo puede estar entendiendo el encargo mejor que una regla—, y un RECURRENTE
# tampoco: ahí no hay una fecha, hay una cadencia.
ENCARGO = "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles."


@pytest.fixture
def jueves_27(monkeypatch):
    """Jueves 27 ago 2026, 08:03 — el instante de la ronda medida. El miércoles siguiente es el 2 de septiembre."""
    t = time.mktime((2026, 8, 27, 8, 3, 0, 0, 1, -1))
    monkeypatch.setattr(scheduler.time, "time", lambda: t)
    return t


def test_hoy_mas_cinco_minutos_se_corrige_al_dia_que_pidio(jueves_27):
    """El caso exacto de la ronda."""
    assert g.safe_reminder_schedule("2026-08-27 08:08", "", ENCARGO) == "2026-09-02 09:00"


def test_con_la_respuesta_delante_manda_la_POSICION(jueves_27):
    """La frase tiene DOS días; lo que va después de «te avisaré» es el del aviso."""
    resp = "Sí, ya está. Te he apuntado lo del seguro y te avisaré el miércoles."
    assert g.safe_reminder_schedule("2026-08-27 08:08", resp, ENCARGO) == "2026-09-02 09:00"


def test_una_fecha_FUTURA_no_se_toca(jueves_27):
    """El lado contrario, y el que protege del exceso de celo: el modelo puede entender el encargo mejor que
    una regla, y `parse_when` ya calla ante lo ambiguo. Solo se corrige el «ahora mismo»."""
    assert g.safe_reminder_schedule("2026-09-05 10:00", "", ENCARGO) == "2026-09-05 10:00"


def test_un_RECURRENTE_no_es_una_fecha(jueves_27):
    """«every 30m» y «0 9 * * 3» disparan hoy por naturaleza. Corregirlos convertiría un aviso semanal en uno
    solo — que es peor que el defecto que se está arreglando."""
    assert g.safe_reminder_schedule("every 30m", "", ENCARGO) == "every 30m"
    assert g.safe_reminder_schedule("0 9 * * 3", "", ENCARGO) == "0 9 * * 3"


def test_sin_un_momento_pedido_no_se_corrige_nada(jueves_27):
    """Sin encargo de aviso en la conversación no hay autoridad contra la que comparar, y adivinar una fecha
    es exactamente lo que `parse_when` se niega a hacer."""
    assert g.safe_reminder_schedule("2026-08-27 08:08", "", "hola qué tal") == "2026-08-27 08:08"


def test_una_fecha_que_NO_parsea_se_sustituye(jueves_27):
    """Sin corregir no se crea ningún trabajo —`scheduler.create` la rechaza— así que el resolvedor no compite
    con nada. Lo mismo con una fecha ya pasada, que `parse_schedule` rechaza igual."""
    assert g.safe_reminder_schedule("el próximo miércoles por la tarde-noche", "", ENCARGO) == "2026-09-02 09:00"
    # …y esa NORMALIZACIÓN es media corrección por sí sola: `scheduler.create` solo entiende las formas de
    # máquina, así que una expresión hablada que resuelve bien se quedaba sin crear el trabajo igualmente.
    assert g.safe_reminder_schedule("2026-08-01 09:00", "", ENCARGO) == "2026-09-02 09:00"


def test_vacio_sigue_vacio(jueves_27):
    assert g.safe_reminder_schedule("", "", ENCARGO) == ""


def test_the_turn_door_calls_it():
    """Wiring guard over the source without comments: the sibling defect (V2-214) was born from guarding ONE door
    and leaving the other raw. The turn's door is read whole (provider + the blocks it delegates to)."""
    from voice.engine.llm.providers import nucleo as _provider

    clean = "\n".join(ln for ln in _vts.getsource(_provider).splitlines() if not ln.strip().startswith("#"))
    assert "safe_reminder_schedule(" in clean, "the voice turn's door"


# ── Making sure the clock is truly FROZEN (2026-08-28) ─────────────────────────────────────────────────────
def test_la_correccion_no_depende_del_dia_en_que_se_corra_el_test():
    """Los dos tests de arriba cayeron al pasar la medianoche del 27 al 28 de agosto de 2026, y hasta entonces
    habían pasado **por coincidencia del calendario**: el fixture congelaba `time.time()`, pero la guarda
    resolvía «hoy» con `localtime()` SIN argumento, que va al reloj del sistema por debajo y no pasa por ahí.
    Dos relojes en una función que decide fechas.

    Esto lo fija por conducta y no por inspección: se congela un instante MUY lejos de cualquier día real en
    que alguien vaya a correr la suite, y la corrección tiene que salir igual. Si vuelve a colarse una lectura
    del reloj del sistema, este test cae el mismo día que se escriba, no un año después.
    """
    # MARTES a propósito: si «hoy» fuera miércoles, el encargo pediría HOY y la guarda no corrige (con razón),
    # así que el test pasaría sin medir nada. Primer intento fallido: el 10 de marzo de 2027 es miércoles.
    lejos = time.mktime((2027, 3, 9, 8, 3, 0, 0, 1, -1))         # martes 9 mar 2027
    real = scheduler.time.time
    try:
        scheduler.time.time = lambda: lejos
        # La tag dispara HOY (cinco minutos después) y el encargo nombraba el miércoles: mañana, día 10.
        assert g.safe_reminder_schedule("2027-03-09 08:08", "", ENCARGO) == "2027-03-10 09:00"
    finally:
        scheduler.time.time = real


def test_y_una_fecha_futura_sigue_sin_tocarse_con_el_reloj_lejos():
    """La mitad de sensibilidad del anterior: congelar lejos no puede volver corrector a la guarda."""
    lejos = time.mktime((2027, 3, 9, 8, 3, 0, 0, 1, -1))
    real = scheduler.time.time
    try:
        scheduler.time.time = lambda: lejos
        assert g.safe_reminder_schedule("2027-04-02 10:00", "", ENCARGO) == "2027-04-02 10:00"
    finally:
        scheduler.time.time = real
