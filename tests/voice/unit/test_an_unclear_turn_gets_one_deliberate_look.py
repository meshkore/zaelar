"""A turn the fast model could not read says so as a CALL, and gets one deliberate look (V2-833 F7).

The class: the voice model runs with reasoning off (a reasoning model cannot keep a spoken conversation fluid), so a
garbled transcript — «…y lo pon pa tipos como tú de Shakira» — was answered «say it again?», and no repair could
catch it, because every repair fires on a PROMISE. Now the model calls `not_understood` instead; the engine says a
«let me think» line from the language table, asks the same model once with reasoning on, and speaks what it says —
or, when that pass fails, times out or stays silent, the honest «I did not understand: other words, or one more
detail». Variants here: Spanish and English, an act (music) and a non-act (a question back), a hung pass.
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


class _Client:
    """A fake model: records what it was given, optionally calls a tool and/or answers, optionally hangs."""

    def __init__(self, *, call=None, text="", hang=False):
        self.call, self.text, self.hang, self.seen = call, text, hang, {}

    def __call__(self):
        return self

    async def complete(self, messages, *, spec=None, tools=None, on_tool_call=None, max_tokens=None):
        self.seen = {"messages": messages, "tools": [t["function"]["name"] for t in tools or []],
                     "max_tokens": max_tokens}
        if self.hang:
            await asyncio.sleep(30)
        if self.call:
            on_tool_call(*self.call)
        return self.text


def _run(code, client, monkeypatch, window=()):
    monkeypatch.setattr(U, "_lang", lambda: _Lang(code))
    sent, calls, events, buf = [], [], [], [""]
    catalog = [{"type": "function", "function": {"name": n}} for n in
               ("play_music", "web_search", "not_understood", "need_capability")]

    def take(final):
        out, buf[0] = buf[0], ""
        return out

    acted = asyncio.run(U.answer(
        messages=[{"role": "system", "content": "S"}, {"role": "user", "content": "lo pon pa tipos como tú"}],
        spec=None, catalog=catalog, on_tool_call=lambda n, a: calls.append((n, a)), send=sent.append, take=take,
        buf_reset=lambda: buf.__setitem__(0, ""), buf_add=lambda d: buf.__setitem__(0, buf[0] + d),
        emit=lambda *a, **k: events.append((a, k)), speech=type("S", (), {"sanitize": staticmethod(
            lambda t, drop_metadata=False: t)}), window=list(window), client_factory=client))
    return acted, sent, calls, events


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_clear_second_read_acts_after_a_thinking_line(code, monkeypatch):
    lang = _Lang(code)
    client = _Client(call=("play_music", {"query": "Shakira"}), text="")
    acted, sent, calls, _ = _run(code, client, monkeypatch)
    assert acted and calls == [("play_music", {"query": "Shakira"})]
    assert sent and sent[0].strip() in lang.pondering_lines, "the thinking line is said first, from the table"
    assert not any(s in lang.not_understood_lines for s in sent), "a pass that acted never says it did not understand"
    assert "not_understood" not in client.seen["tools"] and "need_capability" not in client.seen["tools"]
    assert lang.unclear_pass_note in client.seen["messages"][-1]["content"], "the note rides under his words"
    assert client.seen["messages"][-1]["content"].startswith("lo pon pa tipos como tú")


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_second_read_that_still_cannot_tell_says_so_in_its_own_words(code, monkeypatch):
    acted, sent, calls, _ = _run(code, _Client(text="¿Qué canción de Shakira quieres?"), monkeypatch)
    assert not acted and not calls
    assert sent[-1] == "¿Qué canción de Shakira quieres?"


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_hung_or_silent_pass_ends_in_the_honest_line(code, monkeypatch):
    lang = _Lang(code)
    monkeypatch.setenv("ZAELAR_UNCLEAR_PASS_S", "1")
    for client in (_Client(hang=True), _Client(text="")):
        acted, sent, calls, events = _run(code, client, monkeypatch)
        assert not acted and sent[-1] in lang.not_understood_lines
        assert events[-1][1]["extra"]["why"] in ("wall", "nothing")


def test_the_thinking_line_rotates(monkeypatch):
    lang = _Lang("es")
    first = lang.pondering_lines[0]
    _, sent, _, _ = _run("es", _Client(text="x"), monkeypatch, window=[{"role": "assistant", "content": first}])
    assert sent[0].strip() != first and sent[0].strip() in lang.pondering_lines


def test_the_lines_and_the_note_exist_in_both_languages():
    for code in ("es", "en"):
        s = _Lang(code)
        assert len(s.pondering_lines) >= 3 and len(s.not_understood_lines) >= 2 and s.unclear_pass_note
        assert not set(s.pondering_lines) & set(s.fillers), "thinking lines are not the lead-in fillers"


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


def test_the_turn_runs_the_deliberate_look_before_the_post_stream_chain():
    src = (ROOT / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    m = re.search(r"getattr\(self, \"_not_understood\", False\).*?_unclear\.answer\(.*?\)\s*\n\s*_ps = await "
                  r"_post_stream\.run\(", src, re.S)
    assert m, "the turn must answer a `not_understood` call before the post-stream chain spends its calls"
    assert "on_tool_call=_on_tool_call" in m.group(0), "the pass's calls go through the turn's own gate"


def test_the_language_rule_asks_for_the_call_not_for_a_repeat():
    from nucleo.turn.prompt.builder import _lang_lock
    lock = _lang_lock()
    assert "not_understood" in lock


def test_the_thinking_line_is_never_glued_to_words_already_said(monkeypatch):
    """Measured on the EN bench: «No te he entendido nada, lo siento.Déjame pensar…» — the first pass spoke AND called."""
    monkeypatch.setattr(U, "_lang", lambda: _Lang("es"))
    sent = []
    asyncio.run(U.answer(messages=[{"role": "user", "content": "x"}], spec=None, catalog=[], on_tool_call=lambda *a: None,
                         send=sent.append, take=lambda f: "", buf_reset=lambda: None, buf_add=lambda d: None,
                         emit=lambda *a, **k: None, speech=None, window=[], client_factory=_Client(text=""),
                         said_before="Lo siento."))
    assert sent[0].startswith(" ")


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
    h = FP.Hold(late, sent.append)
    h.say("No te he ")
    assert sent == [] and h.unclear is None, "inside the deadline the first words wait for the verdict"
    late["result"] = {"_call_id": "t", U.KEY: {"choice": U.GARBLED, "confidence": 0.85, "probs": {}}}
    late["event"].set()
    h.say("pillado.")
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert sent == [] and h.unread == U.GARBLED
    gone = _handle(ready=False)
    h2 = FP.Hold(gone, sent.append)
    h2.t0 -= 5.0                                  # past the lead-in filler's deadline: nothing is held
    h2.say("Hola")
    assert sent == ["Hola"] and h2.unclear == ""


def test_noise_goes_straight_to_the_honest_line(monkeypatch):
    lang = _Lang("en")
    client = _Client(call=("play_music", {}))
    monkeypatch.setattr(U, "_lang", lambda: lang)
    sent = []
    acted = asyncio.run(U.answer(messages=[{"role": "user", "content": "brr"}], spec=None, catalog=[],
                                 on_tool_call=lambda *a: None, send=sent.append, take=lambda f: "",
                                 buf_reset=lambda: None, buf_add=lambda d: None, emit=lambda *a, **k: None,
                                 speech=None, window=[], client_factory=client, readable=U.NOISE))
    assert not acted and client.seen == {} and sent and sent[0] in lang.not_understood_lines


def test_the_turn_answers_the_held_verdict_through_the_same_door():
    src = (ROOT / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    m = re.search(r'_unread = getattr\(locals\(\)\.get\("_hold"\), "unread", ""\)\s*\n\s*if \(_unread or '
                  r'getattr\(self, "_not_understood", False\)\).*?_unclear\.answer\(.*?readable=_unread', src, re.S)
    assert m, "the held verdict must reach unclear_turn.answer"


def test_the_pass_reads_his_words_not_the_notices_appended_to_them(monkeypatch):
    """F8 bench: a pending system notice riding his line made the deliberate pass rewrite an appointment."""
    monkeypatch.setattr(U, "_lang", lambda: _Lang("es"))
    client = _Client(text="x")
    asyncio.run(U.answer(messages=[{"role": "system", "content": "S"}, {"role": "user", "content":
                         "lo pon pa tipos como tú\n\n[SISTEMA] Avisos pendientes — add_meeting sin duration_min"}],
                         spec=None, catalog=[], on_tool_call=lambda *a: None, send=lambda t: None, take=lambda f: "",
                         buf_reset=lambda: None, buf_add=lambda d: None, emit=lambda *a, **k: None,
                         speech=type("S", (), {"sanitize": staticmethod(lambda t, drop_metadata=False: t)}),
                         window=[], client_factory=client, heard="lo pon pa tipos como tú"))
    last = client.seen["messages"][-1]["content"]
    assert last.startswith("lo pon pa tipos como tú") and "Avisos pendientes" not in last
    assert client.seen["messages"][0]["content"] == "S", "the system prompt and the conversation are kept"


def test_a_pass_that_acted_in_silence_leaves_the_receipt_to_the_lane(monkeypatch):
    """F8 bench: «Déjame pensar…» then silence while the song started — the music lane says «Suena «X»» only when the
    turn said nothing, and the cover counted as said."""
    monkeypatch.setattr(U, "_lang", lambda: _Lang("es"))
    spoken, sent = [], []

    def send(t):
        sent.append(t)
        spoken.append(t)
    asyncio.run(U.answer(messages=[{"role": "user", "content": "x"}], spec=None, catalog=[],
                         on_tool_call=lambda *a: None, send=send, take=lambda f: "", buf_reset=lambda: None,
                         buf_add=lambda d: None, emit=lambda *a, **k: None, speech=None, window=[],
                         client_factory=_Client(call=("play_music", {"query": "Shakira"}), text=""), spoken=spoken))
    assert sent and sent[0].strip() in _Lang("es").pondering_lines, "the cover is still SAID"
    assert spoken == [], "…but it is not the turn's words"


def test_a_pass_that_acted_never_speaks_the_words_it_wrote_before_the_act(monkeypatch):
    """F8 bench: «Déjame pensar… No te he entendido, ¿me lo repites?» while the song it had called started."""
    monkeypatch.setattr(U, "_lang", lambda: _Lang("es"))
    acted, sent, calls, events = _run("es", _Client(call=("play_music", {"query": "Shakira"}),
                                                    text="No te he entendido, ¿me lo repites?"), monkeypatch)
    assert acted and calls and all("repites" not in t for t in sent)
