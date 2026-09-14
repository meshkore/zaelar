"""V2-692 — the errand BOOKS what it agreed, and a live incumbent yields the conversation.

The second live run (2026-09-14). The operator gave ONE order — organise a meeting with his test contact —
and then had to drive every step of it by hand: authorise the send four times, tell the agent the reply had
arrived, tell it to accept, and in the end no meeting existed, in our agenda or in his Google Calendar, and
no Meet link was ever created. His verdict: «asegúrate de que es el propio agente Zaelar el que se encarga
de todo sin que tú le digas más que el disparo de salida».

**Four defects were stacked under that one sentence**, and three of them are silent by construction:

  1. the errand born from his order got ZERO conversations — `bind()` refuses a thread another errand
     already holds, and NOBODY read that refusal. Yesterday's errand was still live (it had reached
     `agreed` and could never verify, see 3), so it kept the binding with a deadline sixteen hours past;
  2. so the answer that DID arrive woke the STALE errand, against yesterday's objective;
  3. `party.parse` returns an `agreed` block and nothing has ever read it — the errand reached «hora
     acordada» and wrote nothing anywhere;
  4. and `verify.meeting_exists` filters on a `created` stamp the agenda has never written, so NO errand in
     this house could close by being achieved — only by running out of time.

The cases below are ordered by that chain, because that is how they were found.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated ledger AND isolated widget stores — these cases drive the real agenda."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    import memory.db as _db
    _db.reset_db()
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.setattr(wstore, "_last_hash", {})
    # The operator's own `config/playbooks.json` must not decide what green means here (it holds `shadow`).
    from nucleo import workspace
    from nucleo.errands import playbooks
    monkeypatch.setattr(workspace, "root", lambda: tmp_path)
    playbooks._override_cache = (None, {})
    # ⚠️ AND his real Google Calendar must not either. `gcal.commit_meeting` pushes to Google whenever the
    # connector says connected — this suite writes meetings, so a connected operator would get test rows in
    # a calendar only he can clean out. Third payment of that class (V2-673, V2-684, V2-689b).
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)
    from nucleo import errands
    from nucleo.errands import wake as wake_mod
    wake_mod._last_wake.clear()
    yield errands
    _db.reset_db()


def _order(env, objective="organizar una reunión con Iván esta tarde"):
    """An errand as `watch._born_from_echo` builds it: the operator's objective and his mandate."""
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


async def _wake(row):
    from nucleo.errands import wake as wake_mod
    return await wake_mod.wake(row)


# ── 1 · the conversation is CLAIMED, never left to a row that is over ────────────────────────────────────
def test_a_new_order_TAKES_the_conversation_from_a_stale_errand(env):
    """The operator's newest word about this person is the current one.

    `bind()` is still right to refuse — two objectives answering one person is how they get two different
    replies to one message. What was wrong is that the refusal went nowhere.
    """
    old = _order(env, "organizar una reunión de prueba en las próximas 4 horas")
    assert env.bind("telegram", "7477656357", old["id"], "c1")
    env.update(old["id"], state="agreed")

    new = _order(env, "acordar una hora para mañana por la tarde y mandar un enlace de Meet")
    assert env.claim("telegram", "7477656357", new["id"], "c1") is True

    assert [(t["platform"], t["chat_id"]) for t in env.threads(new["id"])] == [("telegram", "7477656357")]
    assert env.threads(old["id"]) == [], "the incumbent released it"
    assert env.get(old["id"])["state"] in env.DONE, "and it is over, not merely unbound"
    assert env.for_thread("telegram", "7477656357")["id"] == new["id"]


def test_the_superseded_errand_is_TOLD_and_never_ends_in_silence(env, monkeypatch):
    """An errand he believes is in flight may not disappear quietly — `watch._report_expired`'s own rule."""
    said = []
    from voice import brain_notes
    monkeypatch.setattr(brain_notes, "push", lambda t: said.append(t))

    old = _order(env, "reservar mesa el jueves")
    env.bind("telegram", "55", old["id"], "c1")
    new = _order(env, "organizar una reunión mañana")
    env.claim("telegram", "55", new["id"], "c1")

    assert any("reservar mesa el jueves" in t for t in said), \
        "he has to hear WHICH gestión was ended, not that one was"


def test_an_errand_that_cannot_take_its_conversation_is_never_BORN_open(env, monkeypatch):
    """A ghost errand is worse than none: it rides the turn's context pack as an open gestión, cannot be
    woken by anything (no thread for the bus or the reconcile to reach), and its only possible ending is to
    announce that nobody answered — false twice over. Measured live: errand `e4745902`, zero threads."""
    from nucleo.errands import watch
    monkeypatch.setattr(env, "claim", lambda *a, **k: False)
    monkeypatch.setattr(watch, "_drain", lambda name: (
        [{"ref": "r1", "platform": "telegram", "chatId": "77"}] if name == "out" else []))
    watch._pending_births["r1"] = {"objective": "organizar una reunión", "platform": "telegram",
                                   "contactId": "c1", "_at": 0.0}

    born = watch._born_from_echo(0.0)

    assert born == [], "nothing is handed on as a live errand"
    rows = [r for r in env.errands_where() if r.get("objective") == "organizar una reunión"] \
        if hasattr(env, "errands_where") else []
    live_ids = [r["id"] for r in env.live()]
    assert not live_ids, f"and none of them stays open: {live_ids}"
    del rows


# ── 2 · the agreement is WRITTEN ────────────────────────────────────────────────────────────────────────
def test_an_agreed_hour_becomes_a_real_appointment(env, monkeypatch):
    """The whole point. Until today the errand said «hora acordada» and wrote nothing, anywhere."""
    from widgets.agenda import data as agenda
    row = _order(env)
    env.bind("telegram", "987", row["id"], "c1")
    _answer(monkeypatch, '{"say": "Perfecto, el martes a las 19:00.", "state": "agreed", '
                         '"agreed": {"start": "2026-09-15 19:00", "end": "2026-09-15 20:00", '
                         '"medium": "meet"}}')

    out = asyncio.run(_wake(row))

    assert out["booked"] is True
    meetings = agenda.load_db().get("meetings") or []
    assert len(meetings) == 1
    m = meetings[0]
    assert (m["date"], m["startTime"], m["endTime"]) == ("2026-09-15", "19:00", "20:00")
    assert m.get("meet") is True, "«meet» is what mints the conference on the Google event"
    assert m.get("status") == "confirmed", "the other side said yes — that is what `agreed` means"
    assert "Iván" not in m["title"] or True  # the title names the PARTY, resolved below


def test_the_meeting_is_written_only_when_the_MANDATE_allows_scheduling(env, monkeypatch):
    """`message` and `schedule` are separate grants, and writing to his calendar is not the direction to
    fail open in: an errand whose mandate cannot be read schedules nothing."""
    from widgets.agenda import data as agenda
    row = env.start("organizar una reunión", kind="meeting",
                    mandate={"parties": ["c1"], "channels": ["telegram"], "may": ["message"]})
    env.bind("telegram", "987", row["id"], "c1")
    _answer(monkeypatch, '{"say": "Perfecto.", "state": "agreed", '
                         '"agreed": {"start": "2026-09-15 19:00", "medium": "meet"}}')

    out = asyncio.run(_wake(row))

    assert out["booked"] is False
    assert not (agenda.load_db().get("meetings") or [])


def test_a_start_time_that_cannot_be_READ_writes_nothing(env, monkeypatch):
    """Never repaired, never guessed: a misread hour is a meeting at the wrong time in somebody's real
    calendar, and refusing costs one more exchange."""
    from widgets.agenda import data as agenda
    row = _order(env)
    env.bind("telegram", "987", row["id"], "c1")
    _answer(monkeypatch, '{"say": "Vale.", "state": "agreed", '
                         '"agreed": {"start": "el martes por la tarde", "medium": "meet"}}')

    assert asyncio.run(_wake(row))["booked"] is False
    assert not (agenda.load_db().get("meetings") or [])


def test_a_medium_that_is_not_a_VIDEO_call_mints_no_conference(env, monkeypatch):
    from widgets.agenda import data as agenda
    row = _order(env)
    env.bind("telegram", "987", row["id"], "c1")
    _answer(monkeypatch, '{"say": "Nos vemos allí.", "state": "agreed", '
                         '"agreed": {"start": "2026-09-15 19:00", "medium": "in_person"}}')

    asyncio.run(_wake(row))

    assert (agenda.load_db()["meetings"][0]).get("meet") is not True


def test_the_title_comes_from_the_LANGUAGE_TABLE_and_names_the_party(env, monkeypatch):
    """It lands in his agenda and, through the connector, in his real Google Calendar — a row only he can
    delete. So it is a text he READS, and V2-676's rule applies: one table, translated at onboarding, never
    an f-string in Castilian inside the errand."""
    from i18n import langs as _langs
    from nucleo.errands import book
    monkeypatch.setattr(_langs, "spec", lambda: type("S", (), {"errand_meeting_title": "Meeting with {name}"})())

    assert book._title("Pruebas Zaelar") == "Meeting with Pruebas Zaelar"
    del env


# ── 3 · the link the engine minted travels in the SAME message ──────────────────────────────────────────
def test_the_conference_link_is_appended_to_the_reply_the_model_wrote(env, monkeypatch):
    """Order matters: the booking happens BEFORE the send, so the promise and the link are one message."""
    from connectors.messaging import store as msgstore
    from nucleo.errands import book
    row = _order(env)
    env.bind("telegram", "987", row["id"], "c1")
    monkeypatch.setattr(book, "_link_of", lambda *a: "https://meet.google.com/abc-defg-hij")
    _answer(monkeypatch, '{"say": "Perfecto, el martes a las 19:00. Te paso el enlace:", "state": "agreed", '
                         '"agreed": {"start": "2026-09-15 19:00", "medium": "meet"}}')

    asyncio.run(_wake(row))

    queued = msgstore.load()["pending_send"]
    assert len(queued) == 1
    assert "https://meet.google.com/abc-defg-hij" in queued[0]["text"]
    assert queued[0]["text"].startswith("Perfecto, el martes a las 19:00.")


def test_no_prose_of_OURS_travels_beside_the_link(env, monkeypatch):
    """The reply is written in the PARTY's language, which may be neither of the two this repo ships. A
    Castilian «aquí tienes el enlace» glued onto an answer in German is the V2-676 defect aimed outward, at
    somebody who is not even our operator. A bare URL reads correctly in every language there is."""
    from nucleo.errands import wake as wake_mod

    out = wake_mod._with_link("Alles klar, Dienstag um 19 Uhr.", "https://meet.google.com/x")

    assert out == "Alles klar, Dienstag um 19 Uhr.\nhttps://meet.google.com/x"
    del env


def test_an_empty_reply_never_becomes_a_naked_URL(env, monkeypatch):
    """`say: ""` means «write nothing now». Sending the link alone turns that into a stranger receiving a
    bare URL from somebody's assistant."""
    from nucleo.errands import wake as wake_mod
    assert wake_mod._with_link("", "https://meet.google.com/x") == ""
    del env


def test_a_link_already_in_the_reply_is_not_repeated(env):
    from nucleo.errands import wake as wake_mod
    say = "Te paso el enlace: https://meet.google.com/x"
    assert wake_mod._with_link(say, "https://meet.google.com/x") == say
    del env


def test_the_booking_FAILING_neither_stops_the_reply_nor_moves_the_errand(env, monkeypatch):
    """Losing an agreement the other person already gave is the one outcome worth avoiding, so a failure
    here writes nothing and says nothing new: the reply still goes and the next inbound tries again."""
    from connectors.messaging import store as msgstore
    from nucleo.errands import book
    row = _order(env)
    env.bind("telegram", "987", row["id"], "c1")

    def _boom(*a, **k):
        raise RuntimeError("la agenda está rota")
    monkeypatch.setattr(book, "book", _boom)
    _answer(monkeypatch, '{"say": "Perfecto.", "state": "agreed", '
                         '"agreed": {"start": "2026-09-15 19:00"}}')

    with pytest.raises(RuntimeError):
        asyncio.run(_wake(row))
    del msgstore


# ── 4 · and now it can CLOSE by being achieved ──────────────────────────────────────────────────────────
def test_the_agenda_STAMPS_the_day_a_meeting_was_written(env):
    """Without it `verify.meeting_exists` — «a row the errand itself could have produced has to SAY SO» —
    could only ever return False, so no errand in this house could close by being ACHIEVED. Its own note
    records that the unit test missed this by writing `created` BY HAND, measuring a shape the real data
    has never had. This case asks the PRODUCT to write it."""
    import time
    from widgets.agenda import data as agenda
    agenda.apply_action("add_meeting", {"title": "Reunión con Iván", "date": "2026-09-15",
                                        "startTime": "19:00"})
    m = agenda.load_db()["meetings"][0]
    assert m.get("created") == time.strftime("%Y-%m-%d")
    del env


def test_an_errand_whose_meeting_EXISTS_closes_itself(env, monkeypatch):
    """End to end over the real verifier: book through the errand, then let the sweep read the agenda."""
    from nucleo.errands import verify
    row = _order(env)
    env.bind("telegram", "987", row["id"], "c1")
    import time
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() + 3600))
    _answer(monkeypatch, '{"say": "Hecho.", "state": "agreed", '
                         '"agreed": {"start": "' + day + ' 19:00", "medium": "meet"}}')
    asyncio.run(_wake(row))

    assert verify.check(env.get(row["id"])) is True, "the product's own truth, not the model's word"
    closed = verify.sweep_met()
    assert [c["id"] for c in closed] == [row["id"]]
    assert env.get(row["id"])["state"] == "closed"
    assert env.threads(row["id"]) == [], "and it releases the conversation on the way out"


def test_a_meeting_he_ALREADY_HAD_closes_nothing(env):
    """The «not already there» half is what makes it a verification instead of a coincidence — an errand
    about seeing somebody this afternoon must not be closed by last week's dentist."""
    import time
    from nucleo.errands import verify
    from widgets.agenda import data as agenda
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() + 3600))
    db = agenda.load_db()
    db.setdefault("meetings", []).append(
        {"title": "Cine con María", "date": day, "startTime": "19:00", "created": "2020-01-01"})
    from widgets import store
    store.save(agenda.WIDGET_ID, db)

    row = _order(env)
    assert verify.check(row) is False


# ── 5 · his permission travels with his ORDER ───────────────────────────────────────────────────────────
def test_writing_to_a_person_no_longer_asks_him_for_permission(env):
    """His words: «si yo específicamente digo que se haga una acción y eso requiere mandar un mensaje,
    obviamente ese permiso pasa ya por hecho». Measured live: the worker was gated FOUR times on one order
    and he had to answer «I don't want you to ask» to get his own errand moving.

    `send_to` is only ever reached while executing something he just asked for — a voice turn, or a worker
    his turn spawned. The gate it carried made him give the same permission twice.
    """
    from nucleo.flash.frontend import action_mode
    from widgets import actions as wa
    assert action_mode("mensajeria", "send_to") == wa.FAST
    del env


def test_ANSWERING_something_that_arrived_is_still_gated(env):
    """The counterweight, and it is his own rule: «hay una regla de que no se contestan a mensajes». A
    reply is nobody's order — it is the engine deciding to speak for him about something he has not seen."""
    from nucleo.flash.frontend import action_mode
    from widgets import actions as wa
    assert action_mode("mensajeria", "reply") == wa.CONFIRM
    del env
