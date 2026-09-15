"""V2-706 · the party who agreed to a meeting may call it off, and the conversation remembers the gestión.

Measured 2026-09-15, at the end of the run that finally closed the Thursday meeting end to end. The meeting
was booked, the Meet link sent, the errand closed «hecha y verificada» — and forty seconds later the
operator wrote, from the other side of the conversation:

    «Now cancel the meet and appointment. I'll let you know when i am available»

and got SILENCE. Three things had to be true at once for that, and all three were:
  · `close()` DELETED the conversation↔errand binding, so the thread no longer knew a gestión had existed;
  · `for_thread` is the only lookup the inbound path had, and it hides finished errands on purpose;
  · the message therefore fell through to the ordinary inbox, whose notify policy is `never` (his own
    setting since 2026-09-07), so nobody was even told.

In his words: «no es capaz de conectar una tarea con otra». It was not interpretation — we had deleted the
link that connects them.

His direction on what should happen, verbatim: «no depende de mí que personas de un grupo, de una llamada o
de una cita quieran cancelar las cosas, con lo cual no hay que autorizar nada… depende únicamente de nuestro
interlocutor, que tiene potestad suficiente como para unilateralmente cancelar eso. Entonces lo cancelas y
lo borras de la agenda. Como mucho a veces se tiene que notificar al usuario para que te dé una siguiente
instrucción». And on how long the link should last: «mientras el compromiso esté por llegar».
"""
from __future__ import annotations

import asyncio
import time

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    import memory.db as _db
    _db.reset_db()
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from nucleo import workspace
    from nucleo.errands import playbooks
    monkeypatch.setattr(workspace, "root", lambda: tmp_path)
    playbooks._override_cache = (None, {})
    # His real Google Calendar is never touched by a test (V2-673 / V2-684 / V2-689b).
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)
    from nucleo import errands
    from nucleo.errands import wake as wake_mod
    wake_mod._last_wake.clear()
    yield errands
    _db.reset_db()


def _order(env, objective="quedar con Cryptonite esta semana"):
    return env.start(objective, kind="meeting",
                     mandate={"parties": ["c1"], "channels": ["telegram"], "may": ["message", "schedule"]})


def _answer(monkeypatch, payload: str):
    from nucleo.errands import wake as wake_mod

    async def _fake(system, dossier, **kw):
        _fake.seen = {"system": system, "dossier": dossier}
        return payload
    _fake.seen = {}
    monkeypatch.setattr(wake_mod, "_ask_model", _fake)
    return _fake


def _tomorrow(hh="17:00", days=2):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + days * 86400)) + " " + hh


def _booked(env, monkeypatch, when=None):
    """An errand that has really written its meeting, through the product's own path."""
    when = when or _tomorrow()
    row = _order(env)
    env.bind("telegram", "777", row["id"], "c1")
    _answer(monkeypatch, '{"say": "Hecho.", "state": "agreed", '
                         f'"agreed": {{"start": "{when}", "medium": "meet"}}}}')
    from nucleo.errands import wake as wake_mod
    asyncio.run(wake_mod.wake(env.get(row["id"]), reason="inbound"))
    wake_mod._last_wake.clear()      # the per-errand coalesce window is not what these cases are about
    return env.get(row["id"])


# ── 1 · the meeting an errand wrote is the only one it can unwrite ──────────────────────────────────────

def test_the_errand_removes_the_meeting_it_wrote(env, monkeypatch):
    from nucleo.errands import book
    from widgets.agenda import data as agenda
    row = _booked(env, monkeypatch)
    assert any(m.get("title", "").lower().startswith("reunión") or "telegram" in str(m)
               for m in agenda.load_db().get("meetings") or []), "the fixture must really have booked"
    out = book.unbook(row, "telegram")
    assert out["ok"] is True, out
    left = [m for m in agenda.load_db().get("meetings") or []]
    assert left == [], f"the row it wrote must be gone, not another one: {left}"


def test_it_can_only_remove_ITS_OWN_row(env, monkeypatch):
    """Somebody else's appointment that merely shares the hour is not this errand's to delete — the five
    «Dentista» at 17:00 that broke V2-692d's slot check are why the key is the RECORD, not the clock."""
    from nucleo.errands import book
    from widgets.agenda import data as agenda
    when = _tomorrow()
    date, hh = when.split(" ")
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": date, "startTime": hh})
    row = _booked(env, monkeypatch, when)
    assert len(agenda.load_db().get("meetings") or []) == 2
    assert book.unbook(row, "telegram")["ok"] is True
    left = [m.get("title") for m in agenda.load_db().get("meetings") or []]
    assert left == ["Dentista"], left


def test_an_errand_that_wrote_NOTHING_removes_nothing(env):
    from nucleo.errands import book
    out = book.unbook(_order(env), "telegram")
    assert out["ok"] is False and "cita" in out["why"]


def test_without_the_schedule_grant_it_removes_nothing(env, monkeypatch):
    from nucleo.errands import book
    row = dict(_booked(env, monkeypatch))
    row["mandate"] = {"parties": ["c1"], "channels": ["telegram"], "may": ["message"]}
    out = book.unbook(row, "telegram")
    assert out["ok"] is False and "mandato" in out["why"]


def test_it_leaves_through_the_agendas_OWN_door_with_the_selector_filled():
    """The V2-705 contract from the inside: `cancel_meeting` is called with its selector, never empty, so
    the incident that started V2-705 cannot be re-entered through the door we built afterwards."""
    import inspect
    from nucleo.errands import book
    src = inspect.getsource(book.unbook)
    assert 'apply_action("cancel_meeting"' in src
    assert '"title": mine.get("title")' in src, "the selector travels; an empty one is what deleted 100 events"


# ── 2 · the party may SAY it, and the engine is what does it ────────────────────────────────────────────

def test_the_party_profile_offers_the_word_and_parses_it():
    from nucleo.errands import party
    assert "cancelled" in party.SHAPE
    d = party.parse('{"say": "Entendido, lo quito.", "state": "cancelled", "reason": "se le ha complicado"}')
    assert d["state"] == "cancelled" and d["reason"] == "se le ha complicado"


def test_the_profile_DECLARES_the_capability_and_does_not_script_the_manner():
    """The operator, 2026-09-15: «necesitamos un sistema que no esté educado, es decir, que sea inteligente
    y que sepa qué hacer… no una banda de reglas predefinidas o de carriles preseteados».

    So this paragraph says what the model MAY do and who holds the authority — an undeclared capability is
    one it narrates instead of using (V2-540) — and says nothing about how to behave. The first version of
    it, written the same night, told the model «no discutas», «acúsale recibo en una frase» and where to
    put what the person said: three rails on its judgement, smuggled in as help. This case is the guard
    against re-inflating them."""
    from nucleo.errands import party
    sys = party.build_system("Johnny", "Ricart", "es", can_link=True)
    assert "`cancelled`" in sys, "the capability must be DECLARED or it gets narrated instead of used"
    assert "no hace falta el permiso" in sys, "who may call off a meeting is a fact, not a manner"
    assert "lo decides tú" in sys, "the judgement is handed back explicitly"
    for scripted in ("no discutas", "acúsale recibo", "en una frase", "no le pidas que lo confirme"):
        assert scripted not in sys, f"«{scripted}» is a rail on judgement, not a mechanism"


def test_a_cancellation_removes_the_meeting_closes_the_errand_and_TELLS_the_operator(env, monkeypatch):
    from widgets.agenda import data as agenda
    told = []
    from nucleo.errands import wake as wake_mod
    monkeypatch.setattr(wake_mod, "_tell_operator", lambda t: told.append(t))
    monkeypatch.setattr(wake_mod, "shadow", lambda: True)          # no real send in a test
    row = _booked(env, monkeypatch)
    told.clear()                     # the booking turn leaves its own notes; this case is about the NEXT one
    _answer(monkeypatch, '{"say": "Entendido.", "state": "cancelled", "reason": "no puede esta semana"}')
    out = asyncio.run(wake_mod.wake(env.get(row["id"]), reason="inbound"))

    assert out["cancelled"] is True
    assert (agenda.load_db().get("meetings") or []) == [], "the appointment must be gone from the agenda"
    assert env.get(row["id"])["state"] == "closed"
    note = "\n".join(told)
    assert "cancelado" in note
    assert "PREGÚNTALE" in note, "the operator is asked for the NEXT step, never for permission"
    assert "no puede esta semana" in note, "what they said travels — it is what he decides on"


def test_the_operator_is_told_even_when_the_agenda_REFUSED(env, monkeypatch):
    """Silence on a failed removal is how he ends up believing a meeting is off when it is still there."""
    told = []
    from nucleo.errands import book, wake as wake_mod
    monkeypatch.setattr(wake_mod, "_tell_operator", lambda t: told.append(t))
    monkeypatch.setattr(wake_mod, "shadow", lambda: True)
    row = _booked(env, monkeypatch)
    told.clear()
    monkeypatch.setattr(book, "unbook", lambda e, p="": {"ok": False, "why": "la agenda no la quitó"})
    _answer(monkeypatch, '{"say": "Ok.", "state": "cancelled"}')
    asyncio.run(wake_mod.wake(env.get(row["id"]), reason="inbound"))
    assert "NO he podido quitarla" in "\n".join(told)


# ── 3 · the conversation REMEMBERS the gestión while the commitment is ahead ────────────────────────────

def test_the_binding_outlives_the_close(env, monkeypatch):
    row = _booked(env, monkeypatch)
    env.close(row["id"], "closed", "hecha y verificada")
    assert env.for_thread("telegram", "777") is None, "a finished errand must never WAKE on a message"
    back = env.last_for_thread("telegram", "777")
    assert back and back["id"] == row["id"], "…and the conversation must still REMEMBER it"


def test_a_commitment_already_PAST_lets_the_conversation_go(env, monkeypatch):
    row = _booked(env, monkeypatch, when=_tomorrow(days=-3))
    env.close(row["id"], "closed", "hecha")
    assert env.commitment_ahead(env.get(row["id"])) is False
    # WHERE it is released is not the property — that it IS, is. `close` lets go immediately when nothing
    # is ahead (so an errand that arranged nothing never leaves a ghost) and `_sweep_bindings` is the
    # backstop for the ones that were still holding a commitment when they closed.
    env._sweep_bindings()
    assert env.last_for_thread("telegram", "777") is None


def test_a_commitment_still_AHEAD_keeps_it(env, monkeypatch):
    row = _booked(env, monkeypatch)
    env.close(row["id"], "closed", "hecha")
    assert env.commitment_ahead(env.get(row["id"])) is True
    env._sweep_bindings()
    assert env.last_for_thread("telegram", "777")["id"] == row["id"]


def test_an_errand_that_arranged_NOTHING_releases_its_conversation_at_once(env):
    row = _order(env)
    env.bind("telegram", "777", row["id"], "c1")
    env.close(row["id"], "abandoned", "nadie contestó")
    env._sweep_bindings()
    assert env.last_for_thread("telegram", "777") is None


def test_a_new_order_still_takes_a_conversation_held_by_a_FINISHED_errand(env, monkeypatch):
    """Keeping the binding must not lock the thread: a newborn would get no conversation at all, which is
    the V2-692 incident with the roles swapped."""
    old = _booked(env, monkeypatch)
    env.close(old["id"], "closed", "hecha")
    new = _order(env, "otra cosa con la misma persona")
    assert env.claim("telegram", "777", new["id"], "c1") is True
    assert env.for_thread("telegram", "777")["id"] == new["id"]


# ── 4 · a message about something still ahead brings its errand BACK ────────────────────────────────────

def test_an_inbound_on_a_live_commitment_REOPENS_the_errand(env, monkeypatch):
    import nucleo.errands.watch as w
    row = _booked(env, monkeypatch)
    env.close(row["id"], "closed", "hecha y verificada")
    now = time.time()
    monkeypatch.setattr(w, "_drain", lambda which: (
        [{"platform": "telegram", "chatId": "777", "messageId": "m9"}] if which == "msg" else []))
    w._pending_wakes.clear()
    w._note_inbound(now)
    assert env.get(row["id"])["state"] == "negotiating", "the gestión comes back to answer"
    assert row["id"] in w._pending_wakes
    w._pending_wakes.clear()


def test_an_inbound_after_the_commitment_has_PASSED_wakes_nothing(env, monkeypatch):
    import nucleo.errands.watch as w
    row = _booked(env, monkeypatch, when=_tomorrow(days=-3))
    env.close(row["id"], "closed", "hecha")
    monkeypatch.setattr(w, "_drain", lambda which: (
        [{"platform": "telegram", "chatId": "777", "messageId": "m9"}] if which == "msg" else []))
    w._pending_wakes.clear()
    w._note_inbound(time.time())
    assert w._pending_wakes == {}, "afterwards it is ordinary mail again"
    assert env.get(row["id"])["state"] == "closed"


def test_the_DURABLE_half_watches_it_too(env, monkeypatch):
    """The bus is an optimisation; the reconcile is the record. Continuity that only lives on the bus is
    lost to a restart — the exact hole V2-684 paid for."""
    import nucleo.errands.watch as w
    row = _booked(env, monkeypatch)
    env.close(row["id"], "closed", "hecha")
    watched = {r["id"] for r in w._watched(time.time())}
    assert row["id"] in watched


def test_the_sweep_retires_a_binding_once_its_commitment_has_PASSED(env, monkeypatch):
    """The backstop, and the only thing that retires a binding kept past a close: the errand closed while
    its meeting was still ahead, and the conversation must go back to being ordinary mail afterwards."""
    row = _booked(env, monkeypatch)
    env.close(row["id"], "closed", "hecha y verificada")
    assert env.last_for_thread("telegram", "777")["id"] == row["id"], "kept while the meeting is ahead"
    after = time.time() + 4 * 86400            # the meeting has now happened
    assert env._sweep_bindings(after) >= 1
    assert env.last_for_thread("telegram", "777") is None
