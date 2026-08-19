"""V2-146 (`remember-and-remind-deadline`) — «te avisaré el miércoles» con `scheduled_jobs.created` VACÍO.

Tres turnos, y los dos que zaelar dijo prometen el aviso: «voy a… programar el recordatorio para el miércoles» y
«sí, ya está… te avisaré el miércoles». No había ningún cron. El ejecutor de tags funciona —lo verificó V2-134
con sus propios tests— y el prompt lo pide con todas las letras desde V2-121; lo que faltaba era hacerlo cuando
el modelo promete en prosa y no emite la tag.

Un backstop que programa avisos tiene que ser cobarde con las fechas: un aviso mal fechado no se nota hasta el
día que no suena (V2-121). Por eso `scheduler.parse_when` devuelve "" ante cualquier expresión que no sea
inequívoca, y ante DOS días en la misma frase — «el JUEVES tengo que renovar… y recuérdamelo el MIÉRCOLES» los
tiene los dos — se niega en vez de elegir. En la respuesta sí se puede desempatar, y no por adivinación sino por
posición: lo que viene DESPUÉS de «te avisaré» es cuándo va el aviso.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo import scheduler
from nucleo.flash import probe
from nucleo.flash import router_guards as g


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


# ── end to end on the channel the use cases run on ──────────────────────────────────────────────────────────
class _PromisesInProse:
    async def stream(self, *_a, **_kw):
        yield REPLY


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    for job in scheduler.list_jobs(active_only=True):
        scheduler.cancel(job.get("name") or "")
    memdb.reset_db()


def test_a_reminder_promised_in_prose_gets_scheduled_anyway(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _PromisesInProse)
    res = asyncio.run(probe.run_turn(ASK, sid="t-v146", ingest=False, execute=True))
    probe._SESSIONS.pop("t-v146", None)
    assert res["ok"] is True
    assert [j for j in scheduler.list_jobs(active_only=True) if j.get("name") == "aviso"]


class _AsksForTheCron:
    async def stream(self, *_a, **_kw):
        yield "Hecho, te aviso el jueves."
        yield ('[[cron.create]]{"schedule":"2026-09-03 09:00","prompt":"renovar el seguro",'
               '"name":"seguro"}[[/cron.create]]')


def test_and_it_does_not_duplicate_one_the_model_did_ask_for(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _AsksForTheCron)
    asyncio.run(probe.run_turn(ASK, sid="t-v146b", ingest=False, execute=True))
    probe._SESSIONS.pop("t-v146b", None)
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


# ── V2-153: el mismo aviso, prometido en dos turnos, se programaba DOS veces ──────────────────────────────────
#
# La corrida de las 16:56 dejó el mecanismo por fin NO vacío —que era lo que V2-151 perseguía— y con dos crons
# idénticos dentro: `2026-08-26 09:00` los dos, uno con la petición real de prompt y otro con «Perfecto, gracias.
# Así no se me pasa.», porque el backstop disparó en el turno que prometía y otra vez en el que lo reafirmaba.
# Medido contra el scheduler real: dos `create()` con la misma spec devuelven ok las dos y dejan dos jobs vivos.
REPLY_T1 = "Voy a apuntarlo en tu agenda para el jueves y configurar un recordatorio para el miércoles."
REPLY_T2 = "De nada. Queda anotado y te aviso el miércoles para que no se te olvide."
ACK = "Perfecto, gracias. Así no se me pasa."


def test_the_first_promise_schedules_the_notice(fresh_db):
    cron = g.dated_reminder_backstop(REPLY_T1, ASK)
    assert cron and cron["schedule"]
    assert cron["prompt"] == ASK          # el prompt es la PETICIÓN, no el turno que la reafirma


def test_and_reaffirming_it_next_turn_does_not_schedule_a_second_one(fresh_db):
    """El caso de uso pide UN aviso. Dos es un defecto que el operador VE: le suena dos veces."""
    first = g.dated_reminder_backstop(REPLY_T1, ASK)
    scheduler.create(first["prompt"], first["schedule"], name=first["name"])
    assert g.dated_reminder_backstop(REPLY_T2, ACK) is None
    assert len(scheduler.list_jobs(active_only=True)) == 1


def test_but_a_moment_nobody_has_covered_yet_still_gets_its_notice(fresh_db):
    """El dedup mira el INSTANTE, no el hecho de que ya exista algo: un aviso para otro día sigue entrando, o el
    backstop dejaría de servir en cuanto hubiera un solo cron vivo."""
    first = g.dated_reminder_backstop(REPLY_T1, ASK)
    scheduler.create(first["prompt"], first["schedule"], name=first["name"])
    other = g.dated_reminder_backstop("Te aviso el viernes a las 18:30.", "recuérdame lo del taller")
    assert other is not None
    assert other["schedule"] != first["schedule"]


def test_and_a_promise_with_no_resolvable_moment_still_schedules_nothing(fresh_db):
    """La frontera de V2-146 sigue en pie después de meter el dedup por delante."""
    assert g.dated_reminder_backstop("Te aviso en cuanto lo tenga.", "busca un hotel") is None
