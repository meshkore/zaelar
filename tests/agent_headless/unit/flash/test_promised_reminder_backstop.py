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
def _n(text: str) -> str:
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text) if not _ud.combining(c)).lower()


REPLY_T1 = "Voy a apuntarlo en tu agenda para el jueves y configurar un recordatorio para el miércoles."
REPLY_T2 = "De nada. Queda anotado y te aviso el miércoles para que no se te olvide."
ACK = "Perfecto, gracias. Así no se me pasa."


def test_the_first_promise_schedules_the_notice(fresh_db):
    cron = g.dated_reminder_backstop(REPLY_T1, ASK)
    assert cron and cron["schedule"]
    # V2-167 cambió esta línea A PROPÓSITO. Antes el prompt era la PETICIÓN literal, y lo que se midió al
    # dispararse es que al agente se le pedía «Apúntame que el jueves… y recuérdamelo el miércoles» — o sea,
    # PROGRAMAR el aviso otra vez, no darlo. Un cron cuyo texto reabre el encargo no es un recordatorio.
    assert cron["prompt"].lower().startswith("avisa al operador")
    assert "seguro del coche" in cron["prompt"]      # y sigue llevando el QUÉ, que es lo que se perdía
    assert "recuerdamelo" not in _n(cron["prompt"])  # sin la petición de programar dentro


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


# ── V2-159: el aviso ya estaba; faltaba la OTRA mitad ─────────────────────────────────────────────────────────
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


def test_the_note_lands_on_the_day_the_commitment_is_for(monkeypatch):
    """Jueves para la cita, NO el miércoles del aviso: la frase lleva los dos días y la posición los separa.

    Reloj FIJO: «el jueves» es una fecha relativa al día en que corre el test, así que la fecha literal de la
    aserción solo era cierta de lunes a miércoles — medido barriendo los siete días."""
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    note = g.dated_note_backstop(REPLY_BOTH, ASK)
    assert note is not None
    assert note["date"] == "2026-08-20"          # jueves; el aviso es el 26, miércoles


def test_and_the_entry_says_what_it_is():
    """Una cita que pone «el jueves» no es una cita. El título sale de lo que hay entre el verbo y la fecha."""
    note = g.dated_note_backstop(REPLY_BOTH, ASK)
    assert "seguro" in note["title"]
    assert "jueves" not in note["title"]


def test_a_promise_to_note_with_no_resolvable_day_writes_nothing():
    """Misma cobardía que el backstop del aviso: una cita mal fechada es del mismo tamaño que un aviso mal
    fechado."""
    assert g.dated_note_backstop("Te lo apunto en tu agenda.", ASK) is None
    assert g.dated_note_backstop("Queda anotado, no te preocupes.", ASK) is None


def test_the_note_no_longer_depends_on_how_the_model_words_it():
    """V2-167 MUEVE esta frontera, y conviene decir por qué en vez de cambiar la aserción y callar.

    V2-159 disparaba con el verbo de la RESPUESTA («te apunto»). La corrida siguiente dijo «la cita ESTÁ EN TU
    AGENDA para el jueves» —afirma el estado en vez de prometer el acto— y la agenda volvió a quedar vacía. Eso
    es la cinta de correr que V2-151 ya pagó: perseguir cómo lo formula el modelo. Lo que NO cambia entre
    corridas es lo que pidió el OPERADOR, así que de ahí sale la obligación.

    Consecuencia directa, y es deseada: si él pidió apuntarlo y el turno solo promete el aviso, la mitad del
    encargo se quedaba sin hacer. El backstop la cubre — y no puede duplicar nada, porque el llamante solo lo
    consulta cuando el turno NO hizo la data-op.
    """
    assert g.dated_note_backstop("Vale, te aviso el miércoles.", ASK) is not None
    assert g.dated_note_backstop("La cita está en tu agenda para el jueves.", ASK) is not None


def test_but_with_nothing_asked_there_is_nothing_to_note():
    """La frontera que SÍ sigue en pie: sin petición de apunte del operador, no se apunta nada."""
    assert g.dated_note_backstop("Vale, te aviso el miércoles.", "¿qué tiempo hace el jueves?") is None
    assert g.dated_note_backstop("De nada, aquí ando.", "gracias") is None


def test_and_a_question_is_not_a_confirmation():
    """Si el turno todavía PREGUNTA, no ha fijado nada: apuntar una fecha que aún se está negociando es
    exactamente el daño que este backstop existe para evitar."""
    assert g.dated_note_backstop("¿El jueves a qué hora te viene bien?", ASK) is None


def test_the_two_halves_are_independent(fresh_db, monkeypatch):
    """El encargo pide las dos y cada backstop resuelve la suya, con días distintos.

    El reloj se FIJA (como ya hacían sus hermanos con `NOW`) porque «el jueves» y «el miércoles» son fechas
    RELATIVAS al día en que corre el test: escrito contra el reloj real, este pasó desde el 2026-08-19 y se
    puso rojo solo al cambiar la fecha —los dos backstops resolvían al mismo día—, que es la peor clase de
    test: uno que se cae un día de cada N sin que nadie haya tocado nada."""
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    cron = g.dated_reminder_backstop(REPLY_BOTH, ASK)
    note = g.dated_note_backstop(REPLY_BOTH, ASK)
    assert cron and note
    assert cron["schedule"].split(" ")[0] != note["date"]


# ── V2-167: un aviso llega ANTES de aquello de lo que avisa ───────────────────────────────────────────────
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


def test_the_whole_case_end_to_end(fresh_db, monkeypatch):
    """Los tres defectos medidos en un objeto de cuatro campos, los tres en la misma aserción.

    Reloj FIJO al mismo `NOW` que el resto del fichero: las tres aserciones llevan fechas literales y «el
    jueves»/«el miércoles» se resuelven contra el día en que corre el test."""
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    reply = "Todo listo: la cita está en tu agenda para el jueves y te aviso el miércoles."
    cron = g.dated_reminder_backstop(reply, ASK)
    note = g.dated_note_backstop(reply, ASK)
    assert cron and note
    # (1) el aviso cae ANTES del compromiso
    assert cron["schedule"].split(" ")[0] <= note["date"]
    assert cron["schedule"].split(" ")[0] != "2026-08-26"
    # (2) lo que dispara es un AVISO, no la petición de programarlo otra vez
    assert cron["prompt"].lower().startswith("avisa al operador")
    # (3) y existe el apunte, que era la mitad que no se hacía
    assert "seguro" in note["title"] and note["date"] == "2026-08-20"


# ── el mismo encargo, los SIETE días de la semana ─────────────────────────────────────────────────────────
#
# Estos tests se escribieron un miércoles y estaban verdes… de lunes a miércoles. El 2026-08-20, un jueves,
# tres de ellos se pusieron rojos SIN que nadie tocara el código: «el jueves» y «el miércoles» son fechas
# relativas al día en que corre el test. Debajo de la flakiness había DOS defectos de verdad:
#
#   · `reminder_before` tomaba su «ahora» de `datetime.now()` mientras las fechas que corregía venían de
#     `scheduler.parse_when`, que lee `scheduler.time.time()`. Dos relojes en la misma cuenta.
#   · el dedup daba por NO cubierto un aviso que ya había saltado (`_still_ahead`), así que cuando la
#     corrección mandaba el aviso a «ahora mismo», el turno siguiente —un simple «gracias»— programaba un
#     SEGUNDO aviso para la fecha sin corregir. Es exactamente el doble aviso que V2-153 existe para impedir,
#     reabierto por el arreglo de V2-167 y visible solo cuatro días de cada siete.
@pytest.mark.parametrize("dom", [17, 18, 19, 20, 21, 22, 23])   # lunes … domingo de esa semana
def test_the_backstop_behaves_the_same_on_every_day_of_the_week(fresh_db, monkeypatch, dom):
    now = time.mktime((2026, 8, dom, 2, 0, 0, 0, 1, -1))
    monkeypatch.setattr(scheduler.time, "time", lambda: now)

    first = g.dated_reminder_backstop(REPLY_T1, ASK)
    assert first, "el encargo pide un aviso: siempre tiene que salir uno"

    # (1) el aviso NUNCA cae después de aquello de lo que avisa
    note = g.dated_note_backstop(REPLY_BOTH, ASK)
    assert note and first["schedule"].split(" ")[0] <= note["date"]

    # (2) y reafirmarlo al turno siguiente no programa un segundo, ningún día
    scheduler.create(first["prompt"], first["schedule"], name=first["name"])
    assert g.dated_reminder_backstop(REPLY_T2, ACK) is None
    assert len(scheduler.list_jobs(active_only=True)) == 1

    # (3) pero una petición NUEVA sigue entrando — el dedup no puede convertirse en un tapón
    assert g.dated_reminder_backstop("Te aviso el viernes a las 18:30.", "recuérdame lo del taller") is not None


# ── V2-176: el QUÉ no está en el turno que fija el CUÁNDO ──────────────────────────────────────────────────
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


def test_the_reminder_carries_the_commitment_and_not_the_apology(fresh_db, monkeypatch):
    monkeypatch.setattr(scheduler.time, "time", lambda: time.mktime((2026, 8, 20, 9, 0, 0, 0, 1, -1)))
    cron = g.dated_reminder_backstop(_W_R4, _W_T4, window=_window(_W_T1, _W_T3, _W_T4))
    assert cron
    assert "seguro" in cron["prompt"]
    assert "liado" not in cron["prompt"] and "perdona" not in cron["prompt"].lower()


def test_and_the_agenda_entry_happens_even_though_the_ask_was_two_turns_back(fresh_db, monkeypatch):
    """La otra mitad del mismo encargo. Una petición de apuntar no CADUCA porque el operador necesitara otro
    turno para acertar la fecha."""
    monkeypatch.setattr(scheduler.time, "time", lambda: time.mktime((2026, 8, 20, 9, 0, 0, 0, 1, -1)))
    note = g.dated_note_backstop(_W_R4, _W_T4, window=_window(_W_T1, _W_T3, _W_T4))
    assert note and "seguro" in note["title"]
    assert note["date"] == "2026-08-27"        # el jueves QUE VIENE, que es el que el operador acabó fijando


def test_without_a_window_nothing_changes(fresh_db, monkeypatch):
    """La compatibilidad es parte del arreglo: los dos canales son implementaciones paralelas y uno podría
    quedarse sin cablear. Sin ventana, la conducta es EXACTAMENTE la de antes — mala para este caso, pero
    igual, así que un canal sin cablear no cambia de comportamiento por sorpresa."""
    monkeypatch.setattr(scheduler.time, "time", lambda: time.mktime((2026, 8, 20, 9, 0, 0, 0, 1, -1)))
    cron = g.dated_reminder_backstop(_W_R4, _W_T4)
    assert cron and "liado" in cron["prompt"]


def test_and_a_turn_that_asks_for_nothing_does_not_inherit_an_old_subject(fresh_db, monkeypatch):
    """La guarda que impide que esto se convierta en «todo hereda de todo»: solo se mira atrás cuando un turno
    ANTERIOR también pidió aviso o apunte, que es lo que hace de este turno una CONTINUACIÓN."""
    monkeypatch.setattr(scheduler.time, "time", lambda: time.mktime((2026, 8, 20, 9, 0, 0, 0, 1, -1)))
    win = _window("¿qué tiempo hace mañana?", "gracias")
    assert g.commitment_from_window(win, "Recuérdame el viernes lo del taller") == \
        g.commitment_clause("Recuérdame el viernes lo del taller")


def test_the_helper_is_wired_into_BOTH_channels():
    """El fallo que este motor repite: una decisión cableada en un canal y ausente en el otro. `probe.py` y el
    provider de voz son implementaciones paralelas del MISMO turno."""
    import inspect

    from nucleo.flash import probe as _probe
    from voice.engine.llm.providers import nucleo as _provider
    for src in (inspect.getsource(_probe.run_turn), inspect.getsource(_provider)):
        assert "dated_reminder_backstop(" in src and "window=" in src


# ── V2-194: el apunte tampoco puede escribirse dos veces ──────────────────────────────────────────────────
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
# El chequeo vive JUNTO A LA ESCRITURA (`probe.py`) y no dentro de `dated_note_backstop`, que es una decisión
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


def test_and_the_write_path_actually_consults_it():
    """El chequeo no sirve de nada si el sitio que escribe no lo llama."""
    import inspect

    from nucleo.flash import probe
    assert "already_in_agenda(" in inspect.getsource(probe.run_turn)
