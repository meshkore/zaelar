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


def test_an_object_already_named_is_not_news(lang):
    """V2-834 T08/T12, use case `watch-a-video-not-listen-to-it` (2026-11-02): «Vale, bajo el volumen un par de pasos.
    Hecho: «Dune…»», then «Ya lo paro. Hecho: «Dune…». He pausado «Dune…»». The object OUR previous reply named is
    not news beside the model's own words; a card's own sentence speaks for its object; with no words of the model's,
    the line still names it. Read from the previous reply, never a global: another conversation named nothing here."""
    dune = "«Dune: Parte Tres | Tráiler Final»"
    prior = f"Hecho: {dune}."
    vol = R.Outcome("met", "youtube", "volume_down", object=dune)
    assert not R.owed([vol], "Vale, bajo el volumen un par de pasos.", prior), "named last reply, and he has words"
    assert R.owed([vol], "Vale, bajo el volumen un par de pasos."), "no previous reply named it: it is said"
    assert R.owed([vol], "", prior), "no words at all: the line is the turn's only answer"
    paused = R.Outcome("met", "youtube", "pause", object=dune, said=f"He pausado {dune}.")
    got = [t for _o, t in R.owed([R.Outcome("met", "youtube", "pause", object=dune), paused], "Ya lo paro.", prior)]
    assert got == [f"He pausado {dune}."], got
    assert R.owed([R.Outcome("met", "youtube", "load", object="«Otra cosa»")], "Te pongo otra.", prior)


def test_a_refusal_its_door_kept_internal_is_said_by_the_mouth(monkeypatch):
    """V2-834 T24 — agenda-appointment-lifecycle (ES): «ponla a las cinco» ran `set_reminder`, refused with an `error`
    only («motivo interno, no se habla»), marked `told`, and «Ya está movida» stood. Unless another op on that card
    landed (the model's own corrected call), the refusal is the mouth's to say."""
    internal = {"ok": False, "error": "el aviso caería después de la cita"}
    o = R.of_op("agenda", "set_reminder", internal)
    assert o.verdict == "unmet" and not o.told
    assert [t for _o, t in R.owed([o], "Ya está movida a las cinco.")], "a claim over an unspoken refusal stood"
    met = R.Outcome("met", "agenda", "move_meeting", object="«Revisión del coche»")
    assert all(x.action != "set_reminder" for x, _t in R.owed([o, met], "Movida."))
    spoken = R.of_op("agenda", "add", {"ok": False, "message": "Falta la hora."})
    assert not spoken.told and len([t for _o, t in R.owed([spoken], "Hecho.")]) == 1, \
        "V2-851 F2: a refusal is this mouth's ONE line — no door said it before"


def test_prior_is_the_previous_reply_on_both_channels():
    """S1 audit H17 asked whether, on the typed channel, `prior` (read from the window in `post_stream_settle`) could be
    THIS turn's reply. It cannot, by construction, and this pins it: both channels run the same `_run_inner`
    (`voice/typed_turn.py` borrows it whole and never writes the window), and there the post-stream chain — the settle
    that reads `prior` — runs BEFORE `close_the_turn`, the one place this turn's reply enters the window."""
    import inspect
    from pathlib import Path
    from voice.engine.llm.providers import nucleo as provider
    src = inspect.getsource(provider.NucleoLLMStream._run_inner)
    assert src.index("_post_stream.run(") < src.index("close_the_turn("), "the settle must read the window before the reply joins it"
    typed = (Path(provider.__file__).resolve().parents[3] / "typed_turn.py").read_text(encoding="utf-8")
    assert "_window" not in typed and '"_run_inner"' in typed
    # …and the searched reply's source (T11) is written in that same `close_the_turn`, so the typed channel — the one
    # the use cases drive — exercises it too (S1 audit H4 read it as voice-only).
    from voice.engine.llm.providers import turn_after
    assert "source_last_reply" in inspect.getsource(turn_after.close_the_turn)
