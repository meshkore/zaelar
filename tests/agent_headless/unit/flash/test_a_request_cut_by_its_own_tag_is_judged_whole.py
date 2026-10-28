"""A request his own barge-in cut before it was answered is judged WHOLE by the next turn's verdict, and an answer
composed from the state is the turn's reply — never followed by the mute apology (V2-820 T-06, 2026-10-27).

Measured on a live session. He asked, at length, for his mail from sixteen months back to be read until his
writing style was captured, and closed with «¿Te parece bien?». That tag barged in: T59 was cancelled before its first
word, its sentence stayed in the dialog window (`dialog.push_user`), and T60 was the tag alone. The model answered the
whole (it escalated the errand); the turn brief, fired on the admitted sentence, judged only the tag — question · tell ·
handle_inline, sure — and CRIT-K34 annulled the commission as `answered`. Measured against the live brief the same
day: the tag alone reads question 0.94-0.96; the request + the tag reads ORDER 0.60-0.82 (es) / 0.78-0.82 (en).
The verdict was right about what it was shown; it was shown half.

Then the composed answer went out, but `spoken_text` had been read before the commission pass: the model had only
called the tool, the annulled commission no longer counted as handled, and the mute backstop appended «Perdona, se me
ha ido. ¿Me lo dices otra vez?» to an answer that had just said something.
"""
import asyncio
import types

import pytest

from nucleo.input import stt as acc
from nucleo.flash import escalation_guard as eg
from nucleo.turn import brief as tb

CUT_ES = ("¿Por qué no miras algo más antiguo, de hace dieciséis meses hacia atrás, y a partir de veinte palabras "
          "ve cogiendo mensajes hasta que des por bueno que tenemos mi estilo de escritura capturado?")
TAG_ES = "¿Te parece bien?"
CUT_EN = ("Why don't you look further back, sixteen months and more, and from twenty words up keep collecting "
          "messages until you think my writing style is captured.")
TAG_EN = "Does that sound good?"


def _brain():
    return types.SimpleNamespace(_acc=acc.Accumulator(), _window=[])


@pytest.mark.parametrize("cut,tag", [(CUT_ES, TAG_ES), (CUT_EN, TAG_EN)], ids=["es", "en"])
def test_the_turn_after_a_cut_request_is_judged_with_it(cut, tag):
    brain = _brain()
    acc.unanswered_by(brain, cut)
    assert acc.whole_turn(brain, tag) == f"{cut} {tag}", "the verdict reads what the model answers"
    assert acc.whole_turn(brain, "Pon música.") == "Pon música.", "consumed by the first turn that reads it"


def test_a_sentence_handed_back_longer_is_not_doubled():
    brain = _brain()
    acc.unanswered_by(brain, "So open me a video")
    assert acc.whole_turn(brain, "So open me a video of the Madonna concert") == \
        "So open me a video of the Madonna concert"


def test_a_cut_too_old_to_be_the_same_sentence_is_not_glued_on():
    brain = _brain()
    acc.unanswered_by(brain, CUT_ES)
    assert acc.whole_turn(brain, TAG_ES, now=brain._cut_unanswered[1] + acc.MAX_GAP_S + 1) == TAG_ES


def test_a_turn_with_nothing_cut_is_judged_as_said():
    assert acc.whole_turn(_brain(), TAG_ES) == TAG_ES


def test_two_cuts_in_a_row_are_both_owed_and_the_system_notes_never_are():
    """The cancel branch holds the COMPOSED turn (his words, then the notes): what is owed is what the verdict judged."""
    brain = _brain()
    acc.unanswered_by(brain, CUT_ES)
    assert acc.whole_turn(brain, "y solo del correo") == f"{CUT_ES} y solo del correo"
    acc.unanswered_by(brain, "y solo del correo\n\n[SISTEMA] La tarea de fondo terminó.")
    assert acc.whole_turn(brain, TAG_ES) == f"{CUT_ES} y solo del correo {TAG_ES}"


def test_the_voice_admission_fires_the_brief_on_the_whole(monkeypatch):
    from voice.engine.llm.providers import turn_admit
    from voice.engine.llm.providers import nucleo as _p
    fired = []
    monkeypatch.setattr(tb, "ask_for_turn", lambda text, **k: fired.append(text) or {"judged": text})
    monkeypatch.setattr(_p._show_target, "_running_goals", lambda: [])
    brain = _brain()
    brain._seeded = True
    attention = types.SimpleNamespace(typed_line=lambda t: False, clamp_input=lambda t, n: (t, False))
    acc.unanswered_by(brain, CUT_ES)
    out = asyncio.run(turn_admit.admit_the_turn(attention=attention, brain=brain, emit=lambda *a, **k: None,
                                                first_turn=False, text=TAG_ES))
    assert fired == [f"{CUT_ES} {TAG_ES}"], "the brief judges the cut request with its tag"
    assert out["operator_text"] == TAG_ES, "his words this turn stay his words: only the verdict's input grows"


@pytest.mark.parametrize("cut,tail", [(CUT_ES, "Vale."), (CUT_EN, "OK.")], ids=["es", "en"])
def test_the_fragment_guard_reads_the_words_the_verdict_read(cut, tail):
    """«Vale.» alone could not have commissioned anything; after his cut request, it did not have to."""
    req = {"v": "read his sent mail and capture his style", "more": []}
    assert not eg.drop_if_fragment(req, operator_text=tail, brief={"judged": f"{cut} {tail}"})
    assert req["v"], "the commission came from the cut words and stands"
    req = {"v": "x", "more": []}
    assert eg.drop_if_fragment(req, operator_text=tail, brief={"judged": tail}), "a bare «vale» is still a fragment"


# ── the composed answer is the reply ─────────────────────────────────────────────────────────────────────────────
ANSWER_ES = "Sí, me parece bien. Dime solo si tiro de WhatsApp, de correo o de los dos, y arranco."
ANSWER_EN = "Sounds good. Just tell me whether to read WhatsApp, mail or both, and I'll start."


def _hold(monkeypatch, *, verdicts, answer, tag):
    from nucleo.flash import router as _router
    from nucleo.flash import post_stream as pst, post_stream_acts as psw, second_pass as sp, card_commission as cc

    monkeypatch.setattr(tb, "read", lambda h, key, fallback, **k: (verdicts.get(key, fallback), None))

    async def _noop(*a, **k):
        return None

    async def _collect(*a, **k):
        return answer

    monkeypatch.setattr(pst._resume_turn, "before_fragment_guard", _noop)
    monkeypatch.setattr(pst._direct_action, "take_rung", lambda *a, **k: False)
    monkeypatch.setattr(cc, "before_worker", _noop)
    monkeypatch.setattr(sp, "collect", _collect)
    spoken, sent = [], []
    box = lambda v=None: {"v": v}
    kw = dict(_apply_widget_data=lambda *a, **k: None, _brief={"judged": tag}, _data_ops_hechas=[], _has_workers=False,
              _prompt_mod=None, _repeat_repair=box(), _router=_router,
              _show_guard_target=lambda *a, **k: None, _tag_emit=lambda *a, **k: None, _tool_fired=set(),
              _turn_op_tasks=[], acted={"widget": False}, brain=types.SimpleNamespace(_window=[], _last_action=None,
              _last_spoken="", _last_reply=""), canvas_h=None, clarify={"msg": ""}, cron_seen=box(),
              data_done={"v": None, "ops": []}, emit=lambda *a, **k: None,
              escalate_req={"v": "Analizar el estilo de escritura del operador", "more": []}, images_req=box(),
              listing_req=box(), music_req=box(), operator_text=tag, read_req=box(), recall_req=box(),
              reopen_req=box(), reveal_req=box(), search_req=box(), send=sent.append, speak=_noop, spec=None,
              speech=types.SimpleNamespace(sanitize=lambda t, **k: t), spoken=spoken, text=tag,
              worker_acted={"v": None})
    return asyncio.run(psw.complete_the_acts(**kw)), sent


@pytest.mark.parametrize("answer,tag", [(ANSWER_ES, TAG_ES), (ANSWER_EN, TAG_EN)], ids=["es", "en"])
def test_an_answer_composed_from_the_state_is_the_turn_s_reply(monkeypatch, answer, tag):
    out, sent = _hold(monkeypatch, verdicts={"request_type": "question", "wants_words": "tell",
                                             "escalate_or_inline": "handle_inline"}, answer=answer, tag=tag)
    assert sent == [answer], "the composed answer was said"
    assert out["spoken_text"] == answer, \
        "what was said is the reply — an empty one sends the turn to the mute backstop («Perdona, se me ha ido»)"
