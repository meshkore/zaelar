"""A turn the fast model could not read is answered with ONE line that asks him — never a second look (V2-833 F7/F8,
V2-851 F5).

The class: the voice model runs with reasoning off, so a garbled transcript — «…y lo pon pa tipos como tú de Shakira» —
cannot be read. «Unreadable» is a STATE of the turn: the brief's `readable` verdict holds the reflex pass's words (an
act proves it read him and keeps them), and the model's own `not_understood` call is the second reader. Either way the
turn says one `not_understood_lines` line from the table. The deliberate pass that re-ran the model with reasoning on
went in V2-851 F5 with every model re-run after the main stream: Flash asks until it is clear.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from nucleo.flash import unclear_turn as U

ROOT = Path(__file__).resolve().parents[3]


class _Lang:
    def __init__(self, code: str):
        from i18n import langs
        self._s = langs.spec(code)

    def __getattr__(self, k):
        return getattr(self._s, k)


def test_the_call_is_offered_every_turn_and_its_door_marks_the_turn():
    from nucleo.flash import router
    from nucleo.acts.tools import CATALOG
    from nucleo.flash import tool_selection
    assert router.family_of("not_understood") == "core"   # `core` is never trimmed
    kept, _ = tool_selection.select(router.tools({}), turn_text="lo pon pa tipos como tú")
    assert "not_understood" in [t["function"]["name"] for t in kept], "offered every turn, whatever it names"

    class C:
        self = type("T", (), {})()
        operator_text, text = "x", "x"
        emit = staticmethod(lambda *a, **k: None)
    CATALOG["not_understood"]({}, C)
    assert C.self._not_understood is True


def test_the_language_rule_asks_for_the_call_not_for_a_repeat():
    from nucleo.turn.prompt.builder import _lang_lock
    lock = _lang_lock()
    assert "not_understood" in lock


# ── V2-833 F8 · «unreadable» is a STATE of the turn, decided by the brief's verdict ─────────────────────────────────────

import threading

from nucleo.flash import follow_up_pass as FP


def _handle(choice=None, conf=0.0, ready=True):
    ev = threading.Event()
    if ready:
        ev.set()
    res = {"_call_id": "t", U.KEY: {"choice": choice, "confidence": conf, "probs": {}}} if choice else {"_call_id": "t"}
    return {"event": ev, "result": res if ready else None}


def test_the_brief_asks_whether_the_sentence_can_be_read():
    from nucleo.turn import brief
    assert U.KEY in brief.keys()
    q = brief.build("lo pon pa tipos como tú", open_ids=[], last_reply="¿Qué te pongo?")[U.KEY]
    assert set(q["criteria"]) == {U.CLEAR, U.GARBLED, U.NOISE}
    assert "¿Qué te pongo?" in q["instructions"], "our previous reply rides along, as in request_type"


@pytest.mark.parametrize("choice, conf, want", [(U.GARBLED, 0.82, U.GARBLED), (U.NOISE, 0.95, U.NOISE),
                                                (U.GARBLED, 0.40, ""), (U.CLEAR, 0.99, "")])
def test_only_a_sure_unreadable_verdict_counts(choice, conf, want):
    assert U.verdict(_handle(choice, conf)) == want
    assert U.verdict(None) == "" and U.verdict(_handle(ready=False)) == ""


def _hold(brief, calls, pieces=("No te he pillado, ", "¿me lo repites?")):
    sent, events = [], []
    h = FP.Hold(brief, sent.append)
    for p in pieces:
        h.say(p)
    asyncio.run(h.release(calls, (), lambda *a, **k: events.append((a, k))))
    return h, sent, events


def test_an_unreadable_turn_whose_reflex_pass_acted_keeps_its_words():
    h, sent, _ = _hold(_handle(U.GARBLED, 0.85), [{"name": "play_music", "args": {"query": "Shakira"}}],
                       ("Te pongo ", "a Shakira."))
    assert "".join(sent) == "Te pongo a Shakira." and not h.unread, "an act is the proof it read the sentence"


@pytest.mark.parametrize("calls", [[], [{"name": "not_understood", "args": {}}]])
def test_an_unreadable_turn_that_did_not_act_says_nothing_of_its_own(calls):
    h, sent, events = _hold(_handle(U.GARBLED, 0.85), calls)
    assert sent == [] and h.unread == U.GARBLED
    assert any("unreadable" in a[1] for a, _k in events)


def test_a_clear_verdict_holds_nothing():
    h, sent, _ = _hold(_handle(U.CLEAR, 0.99), [])
    assert "".join(sent) == "No te he pillado, ¿me lo repites?" and not h.unread


def test_a_brief_in_flight_at_the_first_word_waits_at_most_the_filler_deadline(monkeypatch):
    late = _handle(ready=False)
    sent = []
    h = FP.Hold(late, sent.append, wait_s=1.1)
    h.say("No te he ")
    assert sent == [] and h.unclear is None, "inside the deadline the first words wait for the verdict"
    late["result"] = {"_call_id": "t", U.KEY: {"choice": U.GARBLED, "confidence": 0.85, "probs": {}}}
    late["event"].set()
    h.say("pillado.")
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert sent == [] and h.unread == U.GARBLED
    gone = _handle(ready=False)
    h2 = FP.Hold(gone, sent.append, wait_s=1.1)
    h2.t0 -= 5.0                                  # past the lead-in filler's deadline: nothing is held
    h2.say("Hola")
    assert sent == ["Hola"] and h2.unclear == ""
    h3 = FP.Hold(_handle(ready=False), sent.append)   # a channel that hands no deadline in: nothing waits
    h3.say("Hey")
    assert sent == ["Hola", "Hey"] and h3.unclear == ""


def test_a_reply_that_ends_before_the_brief_lands_waits_for_it_up_to_the_deadline():
    """A check per chunk is not a wait: a short reply has no later chunk to check on, so the release itself waits."""
    import time as _t
    late = _handle(ready=False)
    sent = []
    h = FP.Hold(late, sent.append, wait_s=2.0)
    h.say("No te he pillado.")
    assert sent == [] and h.unclear is None

    def _land():
        _t.sleep(0.15)
        late["result"] = {"_call_id": "t", U.KEY: {"choice": U.GARBLED, "confidence": 0.85, "probs": {}}}
        late["event"].set()
    threading.Thread(target=_land, daemon=True).start()
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert sent == [] and h.unread == U.GARBLED, "the verdict landed inside the deadline: the words were held"
    never = _handle(ready=False)
    h2 = FP.Hold(never, sent.append, wait_s=0.2)
    h2.say("Hola.")
    t0 = _t.monotonic()
    asyncio.run(h2.release([], (), lambda *a, **k: None))
    assert sent == ["Hola."] and not h2.unread and _t.monotonic() - t0 < 1.5, "past the deadline the words are said"


@pytest.mark.parametrize("name", sorted(U.READS - {""}))
def test_a_reflex_pass_that_only_read_has_not_shown_it_read_him(name):
    """Memory recall, a card read, the model's own mark: none is an act on his sentence — the words still go unsaid."""
    h, sent, _ = _hold(_handle(U.GARBLED, 0.85), [{"name": name, "args": {}}])
    assert sent == [] and h.unread == U.GARBLED


def test_the_hold_never_reaches_into_the_motor_for_its_deadline():
    src = (ROOT / "nucleo" / "flash" / "follow_up_pass.py").read_text(encoding="utf-8")
    assert "voice.engine" not in src, "the channel hands the deadline in (dependency direction, modularity §2)"




# ── V2-851 F5 · the turn asks; nothing runs the model again ─────────────────────────────────────────────────────────

from voice.engine.llm.providers import turn_unclear as TU


def _say(hold=None, marked=False, errored=False, spoken=(), code="es", monkeypatch=None, window=()):
    if monkeypatch is not None:
        monkeypatch.setattr(U, "_lang", lambda: _Lang(code))
    sent, events = [], []
    said = TU.say_unread(hold=hold, marked=marked, errored=errored, window=list(window), send=sent.append,
                         emit=lambda *a, **k: events.append((a, k)), spoken=list(spoken))
    return said, sent, events


@pytest.mark.parametrize("code", ["es", "en"])
@pytest.mark.parametrize("readable", [U.GARBLED, U.NOISE])
def test_a_held_unreadable_turn_says_one_table_line(code, readable, monkeypatch):
    said, sent, events = _say(hold=type("H", (), {"unread": readable})(), code=code, monkeypatch=monkeypatch)
    assert said and len(sent) == 1 and sent[0].strip() in _Lang(code).not_understood_lines
    assert any("no second look" in a[1] for a, _k in events)


def test_the_models_own_mark_says_the_line_only_when_it_said_nothing(monkeypatch):
    said, sent, _ = _say(marked=True, monkeypatch=monkeypatch)
    assert said and sent[0].strip() in _Lang("es").not_understood_lines
    said, sent, _ = _say(marked=True, spoken=("¿Cómo dices?",), monkeypatch=monkeypatch)
    assert not said and sent == [], "the model's own words already ask him"


def test_an_errored_or_clear_turn_says_nothing_here(monkeypatch):
    assert _say(hold=type("H", (), {"unread": U.GARBLED})(), errored=True, monkeypatch=monkeypatch)[1] == []
    assert _say(hold=type("H", (), {"unread": ""})(), monkeypatch=monkeypatch)[1] == []


def test_the_line_rotates_and_is_never_glued(monkeypatch):
    lang = _Lang("es")
    first = lang.not_understood_lines[0]
    _, sent, _ = _say(marked=True, window=[{"role": "assistant", "content": first}], monkeypatch=monkeypatch)
    assert sent[0].strip() != first
    _, sent, _ = _say(hold=type("H", (), {"unread": U.GARBLED})(), spoken=("Vale.",), monkeypatch=monkeypatch)
    assert sent[0].startswith(" ")


def test_the_lines_exist_in_both_languages():
    for code in ("es", "en"):
        assert len(_Lang(code).not_understood_lines) >= 2


def test_nothing_on_this_path_runs_a_model():
    """The disarm of V2-851 F5: the deliberate pass called `client.complete` from here; any model client on this path is
    a re-run after the main stream."""
    for rel in ("voice/engine/llm/providers/turn_unclear.py", "nucleo/flash/unclear_turn.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "FastClient" not in src and ".complete(" not in src and ".stream(" not in src, rel
    src = (ROOT / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    assert re.search(r"_turn_unclear\.say_unread\(.*?\)\s*\n\s*_ps = await _post_stream\.run\(", src, re.S), \
        "the turn answers an unreadable sentence before the post-stream chain"
    assert "wait_s=_turn_unclear.hold_deadline_s(" in src, "the channel hands the Hold its deadline"
