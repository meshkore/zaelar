# V2-689 — the operator's FIRST successful Google Calendar connect, 2026-09-14, and everything AROUND it
# misbehaved. His own words, after authorizing in the Google popup:
#
#   «ahora sí ha funcionado la conexión a Google, pero fíjate que en pantalla la agenda no se ha alterado,
#    sigue saliendo el conector como pendiente de conectar, entonces obviamente eso no tiene sentido»
#   «se actualiza en tiempo real en mi pantalla, lo cual es muy bueno, pero ya te digo que a veces me salta
#    el conector directamente sin que yo toque nada. Estoy mirando la pantalla, pum, me salta el conector»
#
# Measured in his own event log before touching anything, and the second one had a cause nobody would have
# guessed from the screen — the `connect` action was being called by a BRAIN WORKER:
#
#     +44 s   widget action  id=agenda action=connect  src=user       ← him, pressing the button
#     +112 s  widget action  id=agenda action=connect  src=worker:3   ← nobody pressed anything
#     +198 s  widget action  id=agenda action=connect  src=worker:3   ← nor here
#
# `worker:3` had been asked whether the calendar was connected, reached for `hbwidget data agenda …`, and
# `connect` is a declared action, so it was allowed — and every call pushed the setup wizard over the week he
# was reading. The worker did nothing wrong. **An action that ASKS FOR something already granted had no
# reason to exist**, and that is what is fixed: `connect` on a linked calendar answers «ya está conectado»
# and moves no screen. `force` — which only a human pressing the button sends — keeps re-linking possible.
#
# The first report is the same defect from the other side, plus a second one underneath it. The push expires
# by TTL (180 s), and `widget.js` applies it when the counter MOVES — but the element's own `connN` starts at
# null on a FRESH mount, so any repaint that rebuilt the card during those three minutes re-applied a token
# that had not moved at all. Nothing cleared the push when the consent actually succeeded either. So the
# operator finished authorizing Google and was immediately handed the «Connect Google Calendar» button back,
# over a calendar that was by then fully synced.
#
# ── 2026-10-04 — the action itself is gone ───────────────────────────────────────────────────────────
#
# The agenda's `connect`/`disconnect` actions and its in-card setup screen were removed with every other
# widget's connect screen: connecting lives in the ⚙ Conectores section alone, so neither a worker nor the
# voice can push a setup wizard over the week he is reading — there is no action to call. What this file
# still pins from that incident: the connected hook retires a pushed screen a pre-2026-10-04 store may still
# hold, the card reads no pushed screen at all, and `connected()` reads the REAL facade shape.
#
# ── And the two events for one sentence ──────────────────────────────────────────────────────────────
#
#   «cuando le he pedido que añadiéramos una cita para el dentista … inmediatamente ha añadido una cita sin
#    nombre en Google Calendar cuando aún todavía no había terminado yo ni siquiera de hablar»
#
# Flows `T13·6948` and `T14·ea37`, one sentence, two `add_meeting` writes:
#
#   T13  «Add me add me one item to my agenda on Okay. Add me add me one item to my agenda on Thursday
#         seventeenth.»                        → date present, NO title  → wrote an all-day «Cita» on the 17th
#   T14  «… At five o'clock saying that I got a dentist.»  → the real one → «Dentist», 17:00
#
# The guard above this line already refuses a payload with NOTHING in it (V2-473), and the hour already
# refuses to be defaulted (V2-652). The TITLE was still defaulted to «Cita» — and a word we chose is not a
# title he said. Once it reaches Google it is a row in HIS calendar that only he can delete.
from __future__ import annotations

import json
import pathlib

import pytest

from widgets.agenda import data as agenda
from widgets.agenda import gcal


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path, raising=False)
    # V2-778 F0: «connect» needs an OAuth client. It is DECLARED here — the suite no longer reads the operator's.
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    return tmp_path


# ── A connected calendar is never asked to connect ───────────────────────────────────────────────────

def test_there_is_no_connect_action_a_worker_could_call():
    """The `worker:3` case, closed at the root: an action that asks for something already granted had no
    reason to exist, and since 2026-10-04 it does not — not on a linked calendar, not on an unlinked one."""
    man = json.loads((pathlib.Path(__file__).resolve().parents[4] / "widgets" / "agenda" / "manifest.json")
                     .read_text("utf-8"))
    assert not {"connect", "disconnect"} & set(man["actions"])
    assert gcal.ui_action("connect", {"provider": "google"}, {}) is None, "not one of the card's actions"
    assert gcal.ui_action("connect", {"provider": "google", "force": True}, {}) is None


# ── The consent SUCCEEDS, so the setup screen is over ────────────────────────────────────────────────

def test_the_connected_hook_retires_a_pushed_screen_BEFORE_it_risks_anything_else():
    """His first report: he finished authorizing Google and was handed the «Connect» button back over a synced
    calendar. A store written before 2026-10-04 may still hold that pushed screen, and the hook retires it at
    the TOP, before the sync — so even a sync that fails leaves him looking at his calendar. Read from the
    source, because the ORDER is the whole property and it is invisible from the outside."""
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "agenda" / "gcal.py").read_text("utf-8")
    body = "\n".join(L for L in src.splitlines() if not L.strip().startswith("#"))
    hook = body[body.index("def on_calendar_connected"):]
    assert 'db.pop("connect", None)' in hook, "the hook never retires the screen"
    assert hook.index('db.pop("connect", None)') < hook.index("s.sync(db)"), (
        "the screen must be retired before the sync, or a failed sync leaves it standing")


def test_the_card_reads_no_pushed_connect_screen_at_all():
    """The second half, and the one the backend alone could not fix: a stale token in the store re-fired on
    every fresh mount because the element's counter started at null. The card no longer has a connect screen
    to push: its plug and its Google icon open the ⚙ Conectores section through the host (`ctx.openConnector`)."""
    js = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "agenda" / "widget.js").read_text("utf-8")
    body = "\n".join(L for L in js.splitlines() if not L.strip().startswith("//"))
    assert "data.connect" not in body and "pushedConn" not in body
    assert 'ctx.openConnector("google")' in body
    assert 'c.id === "google" && c.status === "connected"' in body, "the card still knows whether it is linked"


# ── The agenda does not name an appointment for him ──────────────────────────────────────────────────

def test_an_add_with_a_date_and_NO_title_is_refused_instead_of_called_Cita():
    """The two-events-for-one-sentence case. The fragment carried a date, so the older guard — which only
    refuses a payload with nothing at all in it — let it straight through to a defaulted title."""
    res = agenda.apply_action("add_meeting", {"date": "2026-09-17"})
    assert res.get("ok") is False, res
    assert agenda.load_db().get("meetings") in (None, []), "nothing may be written"


def test_the_refusal_has_the_operators_half_and_the_models_half():
    """V2-652's two audiences, which is what keeps a retry possible without the operator hearing our prose:
    `error` coaches the model, `message` is the only half `report_failure` ever voices."""
    res = agenda.apply_action("add_meeting", {"date": "2026-09-17", "startTime": "17:00"})
    assert "title" in str(res.get("error") or ""), res
    assert res.get("message") and "title" not in str(res.get("message")), (
        "the spoken half must be a sentence for a person, not a field name")


@pytest.mark.parametrize("title", ["   ", "", None])
def test_whitespace_is_not_a_title_either(title):
    assert agenda.apply_action("add_meeting", {"title": title, "date": "2026-09-17"}).get("ok") is False


def test_a_real_appointment_still_lands_untouched():
    """The counterweight that decides whether any of this is safe: the ordinary write must be byte-for-byte
    the behaviour it had, title and all."""
    agenda.apply_action("add_meeting", {"title": "Dentist", "date": "2026-09-17", "startTime": "17:00"})
    rows = agenda.load_db().get("meetings") or []
    assert [m["title"] for m in rows] == ["Dentist"]
    assert rows[0].get("startTime") == "17:00"


def test_the_engine_never_writes_the_word_Cita_into_a_calendar_row():
    """The ratchet behind the case: `Cita` survives as a LABEL for a row that has no title (a rendering
    fallback, and a reminder's wording), and must never again be what gets STORED. Anchored on the write
    path so the two uses cannot be confused for each other again."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "agenda" / "data.py").read_text("utf-8")
    body = "\n".join(L for L in src.splitlines() if not L.strip().startswith("#"))
    assert 'payload.get("title", "Cita")' not in body, "the write defaults the title again"


# ── What he HEARS follows the language he chose ──────────────────────────────────────────────────────

def test_the_refusal_is_spoken_in_the_operators_language(monkeypatch):
    """His standing rule, and V2-676's receipt: every text the operator can hear lives in ONE table that
    gets translated when a language is initialised. A refusal written in Spanish inside a widget is a defect
    for every operator who is not speaking Spanish — which is how he came to hear «esa tarea no ha podido
    completarse» in the middle of an English session."""
    said = {}
    for code in ("es", "en"):
        monkeypatch.setenv("ZAELAR_LANGUAGE", code)
        said[code] = agenda.apply_action("add_meeting", {"date": "2026-09-17"})["message"]
    assert said["es"] != said["en"], "the same sentence in both languages means the table is not being read"
    assert "apuntado" in said["es"] and "put it in" in said["en"], said


def test_it_reads_the_TABLE_and_not_a_two_way_branch():
    """The difference that decides whether «or any language» is true. An `_en` ternary is correct for the two
    languages this repo ships and wrong for the third, and a generated pack can never reach it."""
    import inspect
    from widgets.agenda import data as _ad
    # V2-778 F1-12: each action is its own function in the ACTIONS table; its body is what the branch was
    # V2-781 T513: the table entry is `_a_add_meeting_noticed`, which wraps the write with the asked notice; the
    # write's body (where the sentences are) is still `_a_add_meeting`.
    assert _ad.ACTIONS["add_meeting"].__name__ == "_a_add_meeting_noticed"
    src = inspect.getsource(_ad._a_add_meeting)
    body = "\n".join(L for L in src.splitlines() if not L.strip().startswith("#"))
    add = body[:3000]
    assert '_spoken("agenda_no_title")' in add and '_spoken("agenda_no_data")' in add
    assert '"message": "No' not in add, "a spoken sentence is written inline again"


def test_both_sentences_exist_in_BOTH_shipped_languages():
    """The counterweight to putting them in the table: a field with no English override answers in Spanish
    and nothing complains, which is exactly the failure this is supposed to end."""
    from i18n import langs
    for field in ("agenda_no_data", "agenda_no_title"):
        es = getattr(langs.LANGUAGES["es"], field, "") or getattr(langs.LangSpec, field, "")
        en = getattr(langs.LANGUAGES["en"], field, "")
        assert es and en and es != en, f"{field}: {es!r} / {en!r}"


# ── The double that measured nothing ─────────────────────────────────────────────────────────────────

def test_connected_reads_the_REAL_facade_shape(monkeypatch):
    """⚠️ The case that refuses to use the double, and the only one that could have caught this.

    `connected()` first shipped iterating `service.status()` directly — but that facade answers
    `{"ok": …, "providers": [ … ]}`, a DICT. Iterating it walks the KEYS, calls `.get` on a string, raises,
    and the function's own `except` turns that into False. It returned False for a linked account, every
    time, and the guard it feeds could never fire.

    Every other case in this file monkeypatches `gcal.connected`, so all of them stayed green over a
    function that measured nothing — «a test double with the wrong shape», paid again. This one patches the
    CONNECTOR underneath instead, in the shape the real module actually returns."""
    real = gcal.svc()
    assert real is not None, "the calendar connector must be importable for this case to mean anything"

    class _Facade:
        answer: dict = {}

        def status(self):
            return self.answer

    fake = _Facade()
    monkeypatch.setattr(gcal, "svc", lambda: fake)

    fake.answer = {"ok": True, "providers": [{"id": "google", "connected": True}]}
    assert gcal.connected() is True, "a linked account read through the REAL facade shape"

    fake.answer = {"ok": True, "providers": [{"id": "google", "connected": False}]}
    assert gcal.connected() is False

    fake.answer = {"ok": True, "providers": []}
    assert gcal.connected() is False, "no providers is not a linked account"


def test_the_bare_LIST_shape_still_works_too():
    """`oauth.status()` answers a plain list of rows and is the shape a future caller may hand in. Accepting
    both costs three lines and removes a whole class of the failure above."""
    class _Rows:
        def status(self):
            return [{"id": "google", "connected": True}]

    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(gcal, "svc", lambda: _Rows())
    try:
        assert gcal.connected() is True
    finally:
        mp.undo()


def test_an_unreadable_connector_answers_NOT_connected():
    """Fail-safe direction, stated: refusing to offer the connect button to somebody who needs it is worse
    than offering it to somebody who does not."""
    class _Broken:
        def status(self):
            raise RuntimeError("boom")

    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(gcal, "svc", lambda: _Broken())
    try:
        assert gcal.connected() is False
    finally:
        mp.undo()
    mp2 = _p.MonkeyPatch()
    mp2.setattr(gcal, "svc", lambda: None)
    try:
        assert gcal.connected() is False
    finally:
        mp2.undo()


def test_this_suite_cannot_reach_the_operators_real_token_store():
    """The guard that has to exist because its absence cost him a real connection. A `disconnect` case in
    this directory reached `oauth.forget()` against `.meshkore/credentials/calendar_oauth.json` and unlinked
    the Google account he had just spent an afternoon getting — invisible until the day there was finally an
    account to delete. Asserted here, permanently, instead of trusted to whoever writes the next case."""
    from connectors.calendar import oauth
    assert "credentials" not in str(oauth.STORE), f"the suite points at the REAL store: {oauth.STORE}"
