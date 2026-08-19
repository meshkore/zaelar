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
