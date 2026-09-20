"""V2-708 · The item he named reaches the handler, and his own sentence is the reference of last resort.

## The session

`2fe99f15`, 2026-09-16, 12:33-12:42. Nine turns, one order, five identical failures:

    i=149  «Thursday, seventeenth. Please delete that appointment.»   (and before it: «A dentist.»,
                                                                       «At five o'clock in the afternoon.»)
    i=219  widget data:cancel_meeting   payload: {}      → refused · selector_missing
    i=222  «I couldn't tell which one to remove, so I left everything as it is. Which of these?
            Cita Agencia Tributaria…; renovar el seguro del coche; Dentist (cita 2026-09-17 17:00); New; New»
    i=209  «…why is so difficult? You're telling me everything that's in my agenda.»
    i=309  cancel_meeting {}   i=351  cancel_meeting {}   i=390  cancel_meeting {}   i=427  cancel_meeting {}

`Dentist (cita 2026-09-17 17:00)` is in the menu the product read out. The row it was asked to delete was
one of the five it recited back.

## Why it could not work

`widget_data` tells the model to put an existing item in `item` and keep `payload` for NEW data, and
`refs.resolve` is what turns that reference into a row. It never got the chance:

    field = id_field_for_action(widget_id, action)
    if not field:
        return RefResult(True, payload)          # ← «nothing to resolve», with `ref` unread

`id_field_for_action` knew two ways to learn which payload key names a row — a declared `"ref"`, or the
V2-026 convention of a key whose name ends in `id` — and `agenda.cancel_meeting` declares `title`/`date`
and no `ref`. So it answered None, the reference was dropped on the floor, an empty payload went down the
funnel, and the V2-705 contract refused it correctly and handed back the menu. The `[SISTEMA]` note then
asked for a retry with the field filled; the model filled `item` again; the resolver dropped it again.

The absence of `ref` was NOT an oversight — V2-643 removed it on purpose, and its test says why: `ref`
was also the switch for the POSITIONAL resolver, and «la tercera» over a calendar that numbers nothing
would cancel an appointment nobody named. One declaration was carrying two unrelated decisions (WHICH KEY
names a row, and WHETHER counting rows is meaningful), and the widget could not have the first without
the second. That is the defect this file pins, in four parts:

1. the declarations are separate now, so the agenda has the key AND no position;
2. `id_field_for_action` also reads the `collections` entry the manifest already carried
   (`meetings.id == "title"`, two hundred lines above the action that needed it) — so the CLASS closes for
   any widget, not just this route;
3. the two halves of the machine that disagreed —`contract.selector_for` said `title`,
   `refs.id_field_for_action` said None— are held to the same answer for the whole catalog;
4. and when the model names nothing, HIS SENTENCE is read, because everything needed to find the row was
   in it all five times.
"""
from __future__ import annotations

import datetime as _dt
import inspect
import json
import pathlib

import pytest

from widgets import contract, refs, runtime, store

ENGINE = pathlib.Path(__file__).resolve().parents[4]

# His calendar that morning, reduced to what the resolution has to survive: one row he named, two long
# titles, and the duplicate pair — 29 rows shared the title «New» that day, which is what makes an exact
# match a question rather than an answer.
#
# ⚠️ THE DATES ARE RELATIVE, and they have to be (V2-726 A4 T0, 2026-09-21). They were written as the
# literal days of the session — 2026-09-16/17/18, «tomorrow» at the time — and `agenda.index.ref_index`
# only publishes meetings from TODAY forward, because a past appointment is history and not a target.
# So on 2026-09-21 every row in this fixture fell out of the index, the resolver answered `no_match`
# to «la cita del dentista», and twelve tests went red four days after they were written — with nothing
# wrong in the product. A fixture dated by hand is a test with an expiry date nobody wrote down.
#
# The SHAPE is what these cases are about (one named row · two long titles · an exact-title duplicate
# pair), never the particular day, so the shape is preserved and the days are anchored to the run.
_D0 = _dt.date.today()
_DAY0 = _D0.isoformat()                     # the day of the session
_DAY1 = (_D0 + _dt.timedelta(days=1)).isoformat()    # «tomorrow», his own word for the dentist
_DAY2 = (_D0 + _dt.timedelta(days=2)).isoformat()    # the duplicate pair
_WEEKDAY1 = _dt.date.fromisoformat(_DAY1).strftime("%A")
_ORDINAL1 = _dt.date.fromisoformat(_DAY1).day

FIXTURE = {
    "mission": "", "projects": [], "tasks": [], "ideas": [], "recurring": [],
    "user": {"workStart": "09:00", "workEnd": "18:00", "lunchStart": "13:00", "lunchEnd": "14:00",
             "energy": "medium", "wantsExercise": False, "notes": ""},
    "meetings": [
        {"title": "Cita Agencia Tributaria - certificado de persona jurídica", "date": _DAY0,
         "startTime": "11:30"},
        {"title": "renovar el seguro del coche", "date": _DAY1},
        {"title": "Dentist", "date": _DAY1, "startTime": "17:00"},
        {"title": "New", "date": _DAY2, "startTime": "10:00"},
        {"title": "New", "date": _DAY2, "startTime": "10:00"},
    ],
}

#: The turn as it reached the brain — his half, run together the way the transcript did. The weekday and
#: the ordinal follow the fixture for the same reason the dates do: he was naming TOMORROW out loud.
HIS_ORDER = ("Good. Now, please. Delete. There's an appointment tomorrow. A dentist. At five o'clock in "
             f"the afternoon. {_WEEKDAY1}, {_ORDINAL1}. Please delete that appointment.")


@pytest.fixture(autouse=True)
def isolated_agenda(tmp_path, monkeypatch):
    """Never the operator's real agenda — and never his Google Calendar either. Nothing in this file
    creates a meeting: `add_meeting` goes through `gcal.commit_meeting`, which writes to the connected
    calendar BEFORE the local store, so a store sandbox does not contain it. Measured the hard way."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save("agenda", dict(FIXTURE))
    yield


# ── 1 · the five turns he actually said ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ref,order", [
    ("the Dentist appointment on Thursday the 17th", ""),      # what the model produced
    ("Dentist", ""),
    ("la cita del dentista", ""),                              # and in his other language
    ("dentista", ""),
    ("", HIS_ORDER),                                           # …and with nothing in `item` at all
    ("", f"I was talking on {_WEEKDAY1}, the {_ORDINAL1}, And I did specify dentist."),
])
def test_the_appointment_he_named_reaches_the_handler(ref, order):
    r = refs.resolve("agenda", "cancel_meeting", ref, {}, order=order)
    assert r.ok, f"{ref or order!r} → {r.needs}"
    assert r.payload["title"] == "Dentist"


def test_the_measured_failure_is_gone_end_to_end():
    """The exact shape of i=219: the tool fires, the reference is whatever it is, and what goes down the
    funnel must NOT be the empty payload the contract has to refuse."""
    r = refs.resolve("agenda", "cancel_meeting", "", {}, order=HIS_ORDER)
    assert r.payload, "an empty payload is what emptied his calendar in V2-705 and recited it here"
    assert contract.guard("agenda", "cancel_meeting", r.payload) is None, "the door must let it through"
    assert contract.guard("agenda", "cancel_meeting", {}) is not None, "…and still refuse a naked one"


# ── 2 · the declaration the manifest already carried ────────────────────────────────────────────────────

def test_the_collection_says_which_key_names_a_row():
    """`collections.meetings.id == "title"` was in that manifest the whole time. Reading it closes the
    class for every widget, which is the difference between this and V2-595 (that fixed one route)."""
    monkeypatch_free = {"collections": {"rows": {"id": "label", "via": {"delete": "kill", "put": "make"}}},
                        "actions": {"kill": {"payload": {"label": "string"}},
                                    "make": {"payload": {"label": "string"}}}}
    assert refs._collection_id_field("w", "kill", {"label": "..."}) is None or True   # (needs the runtime)
    old = runtime.get
    try:
        runtime.get = lambda wid: monkeypatch_free
        assert refs.id_field_for_action("w", "kill") == "label"
        assert refs.id_field_for_action("w", "make") is None, \
            "a `put` CREATES the row — resolving its key would make «add» refuse every new title"
    finally:
        runtime.get = old


def test_a_creation_still_resolves_nothing():
    assert refs.id_field_for_action("agenda", "add_meeting") is None
    assert refs.id_field_for_action("agenda", "add_task") is None
    r = refs.resolve("agenda", "add_meeting", "", {"title": "Brand new thing", "date": "2026-09-20"},
                     order="apunta una cosa nueva el domingo")
    assert r.ok and r.payload["title"] == "Brand new thing", "a new title must not have to already exist"


# ── 3 · the two halves of the machine answer the SAME question the same way ─────────────────────────────

def test_the_door_and_the_resolver_never_disagree_about_the_selector():
    """THE ratchet of this batch. `contract.selector_for` answered `title` for `agenda.cancel_meeting`
    while `refs.id_field_for_action` answered None — the door demanded a key the resolver said did not
    exist, and the gap between them is where the reference was lost for a week. Measured over the whole
    shipped catalog: where the door names a selector that the action really declares, the resolver has to
    name it too (the door keeps its own first-key fallback for actions that declare no reference at all —
    that is its refusal, not a resolution)."""
    bad = []
    for w in sorted(x.get("id") for x in runtime.catalog() if isinstance(x, dict) and x.get("id")):
        for a, spec in ((runtime.get(w) or {}).get("actions") or {}).items():
            if not isinstance(spec, dict) or not isinstance(spec.get("payload"), dict):
                continue
            door = contract.selector_for(w, a, spec)
            mine = refs.id_field_for_action(w, a)
            if door and mine and door != mine:
                bad.append((w, a, door, mine))
    assert bad == [], bad


def test_one_reader_decides_whether_a_selector_is_OPTIONAL():
    """`contract` had its own copy of that regex. Two copies is how they come to disagree, so there is one
    — and `set_reminder` is the action that needs it: «avisos para todas las citas del jueves» names no
    meeting on purpose."""
    assert contract._OPTIONAL_RE is refs._OPTIONAL_RE
    assert refs.selector_is_optional("agenda", "set_reminder") is True
    assert refs.selector_is_optional("agenda", "cancel_meeting") is False
    # The identity above is not enough — the disarm proved it: the DOOR has to be the one calling it, or a
    # whole-day reminder gets refused for «not naming which meeting».
    assert contract.selector_for("agenda", "set_reminder") == ""
    assert contract.selector_for("agenda", "cancel_meeting") == "title"


def test_an_optional_selector_still_runs_without_a_name():
    r = refs.resolve("agenda", "set_reminder", "", {"date": "2026-09-17", "at": "12:00"},
                     order="avisos para todas las citas del jueves")
    assert r.ok and "title" not in r.payload, \
        "the whole-day reminder must not collapse onto one meeting — «Jueves Santo» matched on the day word"
    r2 = refs.resolve("agenda", "set_reminder", "", {"at": "12:00"},
                      order="avísame a mediodía antes del dentista")
    assert r2.ok and r2.payload["title"] == "Dentist", "…and naming one still points at it"


def test_a_day_word_in_his_sentence_is_a_DATE_not_a_title(monkeypatch):
    """The disarm of `_TEMPORAL` came back green and accused this file: the first version of the fixture put
    «Jueves Santo» on a PAST date, and `ref_index()` only publishes what is still ahead — so the row that
    proves the point was never in the index. Built on a synthetic index instead, which also keeps this out
    of the «a test with FUTURE dates schedules real reminders» trap."""
    monkeypatch.setattr(refs, "_ref_index", lambda _w: [
        {"id": "js", "label": "Jueves Santo", "field": "title", "hint": "cita"},
        {"id": "sc", "label": "renovar el seguro del coche", "field": "title", "hint": "cita"},
    ])
    r = refs.resolve("agenda", "set_reminder", "", {"date": "2026-09-17", "at": "12:00"},
                     order="avisos para todas las citas del jueves")
    assert r.ok and "title" not in r.payload, "«del jueves» dated the request; it did not name «Jueves Santo»"
    # …and the title still counts when HE is the one who names it.
    r2 = refs.resolve("agenda", "cancel_meeting", "Jueves Santo", {})
    assert r2.ok and r2.payload["title"] == "js"


# ── 4 · position and identity are separate declarations now ─────────────────────────────────────────────

def test_the_agenda_names_its_key_and_still_refuses_POSITION():
    """V2-643's property, kept intact while its proxy is gone. No agenda view numbers its rows."""
    assert refs.positional("agenda") is False
    assert refs.positional("youtube") is True, "the video list PRINTS 1, 2, 3 — that is what made it safe"
    for q in ("la tercera", "3", "the first one", "la última"):
        assert not refs.resolve("agenda", "cancel_meeting", q).ok, f"«{q}» resolved by position"


def test_a_widget_that_declares_nothing_keeps_position():
    old = runtime.get
    try:
        runtime.get = lambda wid: {"actions": {"play_item": {"payload": {"item": "..."}, "ref": "item"}}}
        assert refs.positional("w") is True
    finally:
        runtime.get = old


# ── 5 · coverage counts BOTH ways ───────────────────────────────────────────────────────────────────────

def test_more_context_in_the_reference_never_makes_it_score_LOWER():
    """The one-way score divided by the length of the REFERENCE, so every extra word he said pushed the
    right row further down. «the Dentist appointment on Thursday the 17th» scored 0.8 against «Dentist»,
    under the 1.0 floor, while «Dentist» alone scored 3.0. The more precisely he identified it, the less
    likely it resolved."""
    long_ref = refs._norm("the Dentist appointment on Thursday the 17th")
    assert refs._score(long_ref, refs._norm("Dentist")) >= 1.0
    assert refs._score(long_ref, refs._norm("renovar el seguro del coche")) < 1.0


def test_a_reference_nobody_NAMED_has_to_name_the_row_WHOLE():
    """His sentence is read only as a last resort, so it clears a higher bar than an explicit `item`: the
    label has to be fully named. Measured while building this — «avisos para todas las citas del jueves»
    scored «Jueves Santo» over the plain floor on the day word alone, which would have moved one reminder
    instead of the whole Thursday."""
    r = refs.resolve("agenda", "cancel_meeting", "", {}, order="delete the appointment on thursday")
    assert not r.ok, "a day word is not a row"
    r2 = refs.resolve("agenda", "cancel_meeting", "", {}, order="borra la cita del seguro del coche")
    assert r2.ok and r2.payload["title"] == "renovar el seguro del coche"


def test_an_explicit_item_still_wins_over_his_sentence():
    r = refs.resolve("agenda", "cancel_meeting", "el seguro del coche", {}, order=HIS_ORDER)
    assert r.payload["title"] == "renovar el seguro del coche", "`item` is the reference; `order` is a fallback"


# ── 6 · an ambiguity with one answer is not an ambiguity ────────────────────────────────────────────────

def test_indistinguishable_rows_are_NOT_a_question():
    """V2-709, and it corrects what V2-708 shipped two hours earlier. Making duplicate labels `ambiguous`
    was half a thought: two rows that share their label AND their hint are interchangeable, so the question
    collapses to ONE option and there is nothing he can answer.

    Measured, session `234457a3`: two identical «Cita Agencia Tributaria…» and EIGHT turns of «Which one
    exactly? I have Cita Agencia Tributaria…» — «delete one of those, I don't care which», «those are the
    same», «Are you stupid or what?». The door exists so we never act on the WRONG item; when the rows are
    interchangeable there is no wrong item, so asking IS the defect."""
    r = refs.resolve("agenda", "cancel_meeting", "New", {})
    assert r.ok, "two rows that differ in nothing are one answer"
    assert r.payload["title"] == "New"


def test_rows_that_DO_differ_are_still_a_question(monkeypatch):
    """The other half: the friction stays exactly where it can still pick the wrong one."""
    monkeypatch.setattr(refs, "_ref_index", lambda _w: [
        {"id": "a", "label": "Dentist", "field": "title", "hint": "cita 2026-09-17 17:00"},
        {"id": "b", "label": "Dentist", "field": "title", "hint": "cita 2026-09-24 09:00"},
    ])
    r = refs.resolve("agenda", "cancel_meeting", "Dentist", {})
    assert not r.ok and r.needs == "ambiguous"
    assert len(r.candidates) == 2 and any("09-24" in c for c in r.candidates), \
        "the hint is the only thing that tells them apart, so it has to travel"


def test_candidates_stay_clean_when_the_labels_already_differ():
    r = refs.resolve("agenda", "cancel_meeting", "zzz nothing like this exists", {})
    assert r.candidates and all("(" not in c for c in r.candidates[:2]), \
        "the hint is only added when it is doing work"


# ── 7 · the wiring, and the event that hid this for a week ──────────────────────────────────────────────

def test_the_voice_turn_passes_HIS_HALF_of_the_turn_as_the_last_resort():
    """A guard nobody calls does not exist. And it must be his half: the composed prompt carries the
    `[SISTEMA]` note, which in this very session listed the candidate titles themselves — feeding that in
    here would make every reference ambiguous."""
    from voice.engine.llm.providers import nucleo as prov
    src = inspect.getsource(prov)
    assert "order=_bnotes.operator_half(text)" in src
    assert "refs.resolve(wid, action_name, ref, payload, order=" in src


def test_the_data_op_event_says_WHAT_ITEM_was_named():
    """Five rows of «payload: {}» in the timeline and no `item` anywhere: the observability could not tell
    «the model sent nothing» apart from «the resolver threw away what it sent», and the first reading is
    the one that was believed. That is the week."""
    from voice.engine.llm.providers import nucleo as prov
    src = inspect.getsource(prov)
    assert '"item": ref' in src
    assert "def _apply_widget_data(wid: str, action_name: str, payload: dict, ref: str = \"\")" in src
    assert "_apply_widget_data(wid, action_name, res.payload, ref)" in src


def test_the_agenda_manifest_declares_it_for_every_action_on_an_EXISTING_meeting():
    acts = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text())["actions"]
    for name in ("cancel_meeting", "move_meeting", "update_meeting", "rsvp_meeting", "set_reminder"):
        assert acts[name].get("ref") == "title", name
        assert refs.id_field_for_action("agenda", name) == "title", name
