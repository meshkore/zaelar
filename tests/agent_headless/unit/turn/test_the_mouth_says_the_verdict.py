"""The mouth says the verdict (refactor2710-03): for each verdict of an act, the line — and only the lines it owes.

`nucleo/turn/reply.py` composes an acting turn's last words from what its acts ENDED in. One i18n key per verdict
(`reply_<verdict>`), in every language the engine ships. The rules: `met` names its object unless the words already
named it; `unmet`, `cannot` and `asked` are always said (unless the act's own door already said them); `started`,
`skipped` and the rest add nothing. Each line leaves one event carrying its verdict.

The disarm feeds a WRONG verdict to the same act and sees the line change: a test that stays green over it would be
checking the template, not the verdict.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.turn import reply as R

VALUES = ("started", "met", "unmet", "unverifiable", "undeclared", "cannot", "asked", "skipped")


@pytest.fixture(params=["en", "es"])
def lang(request, monkeypatch):
    from i18n import langs
    spec = langs.LANGUAGES[request.param]
    monkeypatch.setattr(langs, "current_language", lambda: spec)
    return spec


def _send():
    said = []

    class _Speech:
        @staticmethod
        def sanitize(t, drop_metadata=False):
            return t

    return said, said.append, _Speech


def test_every_verdict_has_its_key_in_every_language(lang):
    for v in VALUES:
        assert hasattr(lang, f"reply_{v}"), f"{lang.code}: no reply_{v}"
    for v in ("started", "met", "unmet", "unverifiable", "undeclared", "cannot", "asked"):
        assert getattr(lang, f"reply_{v}"), f"{lang.code}: reply_{v} is empty"


def test_each_verdict_says_its_line(lang):
    obj, why = "«Dune: Part Two»", "Nothing is at full screen right now."
    assert obj in R.line(R.Outcome("met", object=obj))
    assert obj in R.line(R.Outcome("undeclared", object=obj))
    assert obj in R.line(R.Outcome("unverifiable", object=obj))
    assert why in R.line(R.Outcome("unmet", reason=why))
    assert why in R.line(R.Outcome("cannot", reason=why))
    assert "Which one?" in R.line(R.Outcome("asked", reason="Which one?"))
    assert R.line(R.Outcome("skipped")) == ""
    assert R.line(R.Outcome("met")) == "", "a met with no object has nothing to name: «Done.» alone is never the line"
    assert R.line(R.Outcome("unmet")) == lang.op_failed, "an unmet with no speakable reason says the base line"


def test_only_what_the_verdict_owes_is_said(lang):
    title = "Dune: Part Two | Official Trailer"
    met = R.Outcome("met", "youtube", "load", object=f"«{title}»")
    assert R.owed([met], "") and R.owed([met], "I'll put it on."), "the words did not name what loaded"
    assert not R.owed([met], f"Putting on {title} now."), "the words already named it"
    assert not R.owed([R.Outcome("started", "youtube", "load")], "On it."), "a promise is a START: nothing added"
    assert not R.owed([R.Outcome("unmet", "agenda", "add", reason="x", told=True)], "Done."), \
        "a refusal its own door already said is not said twice"
    assert R.owed([R.Outcome("cannot", "canvas", "unfullscreen", reason="Nothing there.")], "Done.")
    assert len(R.owed([met, met], "")) == 1, "one line, once"


def test_a_data_op_result_becomes_its_verdict():
    assert R.of_op("youtube", "load", {"ok": True, "title": "X"}).verdict == "met"
    assert R.of_op("youtube", "load", {"ok": True, "title": "X"}).object == "«X»"
    assert R.of_op("youtube", "load", {"ok": False, "message": "no"}).verdict == "unmet"
    assert R.of_op("youtube", "load", {}).verdict == "started", "silence is not success"
    q = R.of_op("youtube", "queue_search", {"ok": True, "title": "A", "queued": ["A", "B", "C"]})
    assert all(f"«{t}»" in q.object for t in "ABC")


def test_each_line_leaves_its_verdict_event(lang, monkeypatch):
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: seen.append((a, k)))
    said, send, speech = _send()
    out = R.speak([R.Outcome("cannot", "canvas", "unfullscreen", reason="Nothing there.")], "Done.", send, speech)
    assert out.startswith("Done. ") and out.endswith("Nothing there.") and len(said) == 1
    (args, kw), = seen
    assert kw["extra"]["verdict"] == "cannot" and kw["extra"]["key"] == "reply_cannot"


def test_a_declared_verdict_is_said_once_after_the_acts(lang):
    said, send, speech = _send()
    R.note(R.Outcome("asked", "tasks", "reopen", reason="Which one?"))
    assert asyncio.run(R.after_acts((), "", send, speech)).endswith("Which one?")
    assert asyncio.run(R.after_acts((), "", send, speech)) == "", "a declared verdict is taken once"


def test_disarm_a_wrong_verdict_changes_the_line(lang):
    """Feed the same act a wrong verdict: the line must change, or this file checks templates, not verdicts."""
    right = R.line(R.Outcome("met", object="«X»"))
    for wrong in ("unmet", "cannot", "asked", "started", "skipped"):
        assert R.line(R.Outcome(wrong, object="«X»", reason="no")) != right, wrong


def test_the_lines_are_keyed_on_the_one_vocabulary(lang):
    """Every verdict of `nucleo.circuit.verdict` has its line key; a name no verdict has says nothing."""
    from nucleo.circuit import verdict as V
    assert set(V.ALL) == set(VALUES)
    assert R.line(R.Outcome(V.MET, object="«X»")) == R.line(R.Outcome("met", object="«X»"))
    assert R.line(R.Outcome("gave_up", reason="x")) == R.line(R.Outcome("unmet", reason="x")), "a stored name reads as one"
    assert R.line(R.Outcome("done", object="«X»")) == ""
