"""Two players on screen and one word that fits both — whose order is it? (V2-740)

The operator, 2026-09-21, correcting the framing that called this a defect:

> «si tengo dos widgets que tienen las mismas tools con los mismos nombres, el motor va a dar un 50% de
>  ejecutar un play en un widget o en otro. Y cuando eso pase, el flashbrain tendrá que decir: tienes dos
>  tipos de reproductores abiertos y me tienes que especificar cuál quieres. Si por contexto sabe
>  identificarlo, perfecto. Porque si yo le digo cárgame un vídeo del Apolo 11 y luego le digo dale al
>  play, lo más lógico es que el usuario se esté refiriendo a todo eso […] probablemente el modelo de
>  evaluación de la decisión será capaz de decirnos a qué cree que se refiere el usuario y deberíamos
>  utilizarlo en ese punto del flujo.»

He is right that the widgets are not the problem: `youtube` and `musica` share NINE action names by
design, and sharing a vocabulary is what makes them both players. What was missing was the step after.

MEASURED, and it is why this test exists rather than a wider change: the brief has been asking this exact
question since V2-726 A4 — `screen_action`, keyed `<card>:<action>`, 68 options with both players open,
each labelled with its LIVE rail. Its only reader was `repair_action_from_brief`, whose own docstring says
it fires «ONLY on the invented-action path». So for a DECLARED action the verdict was paid for and thrown
away, and the model's coin flip stood.

These drive the REAL decision (`frontend.which_card`) with a handle of the REAL brief shape — a test that
builds the answer by hand proves the mapping and never the wiring.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import frontend as fe

BOTH = ["youtube", "musica"]


def _brief(choice: str, confidence: float = 0.95, *, open_ids=BOTH, ready: bool = True) -> dict:
    """A brief handle exactly as `jev.ask_many` hands one over: an Event, a result dict, and the stamp
    `turn_brief.stamp` writes on it. Nothing here re-implements `read` — it is the real one that runs."""
    ev = threading.Event()
    if ready:
        ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {"screen_action": {"choice": choice, "confidence": confidence}}}


# ── the common path pays nothing ────────────────────────────────────────────────────────────────────────
def test_one_card_that_can_do_it_is_not_a_question():
    assert fe.which_card("musica", "play", open_ids=["musica"], brief=None) == ("keep", None)


def test_an_action_only_one_of_them_declares_is_not_a_question():
    """`add_meeting` belongs to the agenda alone; having a player open changes nothing about it."""
    assert fe.which_card("agenda", "add_meeting", open_ids=["agenda", "youtube"],
                         brief=None) == ("keep", None)


def test_nothing_is_read_when_there_is_nothing_to_decide(monkeypatch):
    """The guard that keeps this free: with one candidate the brief is never touched, so the common
    path cannot pay a read — nor drag a verdict about another card into an unrelated order."""
    from nucleo.flash import turn_brief as tb
    leido = {"n": 0}
    real = tb.read
    monkeypatch.setattr(tb, "read", lambda *a, **k: (leido.__setitem__("n", leido["n"] + 1), real(*a, **k))[1])
    fe.which_card("musica", "play", open_ids=["musica"], brief=_brief("youtube:play"))
    assert leido["n"] == 0, "a call with nothing to decide must not read the brief at all"


# ── the verdict decides, and only about the card ────────────────────────────────────────────────────────
def test_the_brief_moves_the_order_to_the_card_it_names():
    """His Apollo-11 case: the video was loaded, so «dale al play» is about the video — and the brief
    knows because each candidate carries its card's live rail as its label."""
    assert fe.which_card("musica", "play", open_ids=BOTH,
                         brief=_brief("youtube:play")) == ("card", "youtube")


def test_a_verdict_that_agrees_with_the_model_changes_nothing():
    assert fe.which_card("youtube", "play", open_ids=BOTH,
                         brief=_brief("youtube:play")) == ("keep", None)


def test_a_verdict_about_ANOTHER_action_is_a_different_question():
    """It never repairs the verb. «Pausa» stays «pausa»; what it decides is whose. Two decisions behind
    one verdict would make the confident-and-wrong case twice as expensive."""
    kind, _ = fe.which_card("musica", "play", open_ids=BOTH, brief=_brief("youtube:next"))
    assert kind == "ask", "a verdict about `next` says nothing about who owns `play`"


def test_an_unsure_verdict_is_not_an_answer():
    kind, cands = fe.which_card("musica", "play", open_ids=BOTH, brief=_brief("youtube:play", 0.31))
    assert kind == "ask" and len(cands) == 2


def test_a_brief_still_in_flight_is_not_an_answer():
    kind, _ = fe.which_card("musica", "play", open_ids=BOTH,
                            brief=_brief("youtube:play", ready=False))
    assert kind == "ask", "nobody waits: a brief that has not landed is «I do not know», not a pause"


def test_no_brief_at_all_asks_rather_than_guessing():
    kind, cands = fe.which_card("musica", "play", open_ids=BOTH, brief=None)
    assert kind == "ask"
    assert any("youtube" in c for c in cands) and any("musica" in c for c in cands), cands


def test_a_verdict_naming_a_card_that_is_no_longer_open_is_stale(monkeypatch):
    """The brief enumerates what was open at fire time and the reader acts 2-4 s later. A card that has
    been closed in between cannot receive the order — `owner_still_open` is the join that says so."""
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["musica"]})
    kind, _ = fe.which_card("musica", "play", open_ids=BOTH, brief=_brief("youtube:play"))
    assert kind in ("ask", "keep"), kind
    assert kind != "card", "a verdict about a card that is gone must never move an order onto it"


# ── and the question it asks is the one the system already asks ─────────────────────────────────────────
def test_the_candidates_carry_each_cards_LIVE_rail_not_its_id():
    """«¿el vídeo o la música?» is useless with two of the same kind open. The label is the card's own
    face (`instances.card_face`), which is the only component that can say what it is showing."""
    from nucleo.flash import turn_brief as tb
    kind, cands = fe.which_card("musica", "play", open_ids=BOTH, brief=None)
    assert kind == "ask"
    assert cands == [tb._card_label("youtube"), tb._card_label("musica")], cands


def test_the_ask_is_consents_second_question_and_not_a_new_one():
    """V2-712's rule, unchanged: «¿hay DUDA sobre qué se va a tocar? → ASK_WHICH, con el recuento y los
    nombres». What is new is that the thing in doubt can be a CARD and not only a row inside one."""
    from nucleo import consent
    _, cands = fe.which_card("musica", "play", open_ids=BOTH, brief=None)
    v = consent.decide(candidates=cands)
    assert v["verdict"] == consent.ASK_WHICH, v
    assert v["candidates"] == cands and consent.asks(v)


# ── and the half that a mapping test cannot reach: is the decision WIRED, on BOTH channels? ─────────────
# The lesson this repo keeps paying for: an integration shipped in an initiative marked done and never made
# a call in its life, because every test built its verdict by hand. And the R3 class beside it — a rule that
# only ever existed on one side (`close_guards.is_short_close_order` lived inline in the voice rail for two
# months while the probe, which the use-case harness drives, answered differently).
import pathlib

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_VOICE = (_ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
_PROBE = (_ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")


def test_the_voice_rail_asks_WHOSE_order_before_dispatching_it():
    """Order matters, not just presence: deciding after the op ran would route the correction, not the
    order. The call has to sit above `_apply_widget_data`, in the same function."""
    call = _VOICE.index("card_decision(")
    dispatch = _VOICE.index("_apply_widget_data(_cd[\"card\"], action_name, res.payload, ref)")
    assert call < dispatch, "the card is decided BEFORE the op is dispatched, or it decides nothing"
    assert "_apply_widget_data(wid," not in _VOICE, (
        "the dispatch still takes the widget the MODEL named — the decision changes nothing")
    assert "ask_which_item" in _VOICE, "the ASK branch has to reach a phrase the operator hears"
    # …and it is the phrase consent's ASK_WHICH already owns: one question, one string. A second one
    # for the same verdict is a second thing to translate and a second thing to fall out of step.


def test_the_probe_takes_the_SAME_decision_and_does_not_copy_it():
    """Both channels call the one function. A copied condition costs a marker and leaves two places to
    edit — this repo's own ratchet vetoes a new mirror: «si dos canales necesitan la misma regla, extrae»."""
    from nucleo.flash import frontend
    src = (_ENGINE / "nucleo/flash/frontend.py").read_text(encoding="utf-8")
    for fn in ("card_decision", "which_card", "absent_widget_misroute"):
        assert f"def {fn}" in src and callable(getattr(frontend, fn)), fn
        assert f"def {fn}" not in _PROBE and f"def {fn}" not in _VOICE, (
            f"`{fn}` was COPIED into a channel instead of shared — «si dos canales necesitan la misma "
            f"regla, extrae primero»")
    assert "card_decision(" in _PROBE, "the text channel takes a different decision from the product"
    # …and the guard that WAS copied, in both, until this pass: the probe's own comment said so.
    assert "absent_widget_misroute(" in _PROBE and "absent_widget_misroute(" in _VOICE
    assert "looks_like_bare_ref" not in _PROBE, "the duplicated condition survived in the probe"


def test_no_third_blocking_caller_was_added_to_serve_the_briefless_channel():
    """The obvious repair for «the probe has no brief» is to ask synchronously, and node 3.61 freezes the
    blocking callers at two. The absence is deliberate and the comment says why: a channel with no brief
    ASKS, which is the behaviour asked for and cannot be wrong."""
    import ast

    src = (_ENGINE / "nucleo/flash/frontend.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "which_card")
    # A CALL, not a mention: the comment above it names `choose_sync` on purpose, to say why there is
    # none. A substring check would have read our own explanation as the defect it explains.
    calls = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")
             for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "choose_sync" not in calls, (
        "`which_card` must not open its own blocking call — put the question in the brief (node 3.61)")


def test_the_sentence_the_operator_HEARS_is_actually_produced():
    """A phrase that does not format is a phrase nobody hears: `ask_which_item` carries `{cands}`, and
    asking for `{cards}` raises KeyError inside the turn. Caught here because the source-level wiring
    assertions above could not see it — they prove the call, never that its argument fits."""
    from i18n import langs

    from nucleo.flash import frontend as fe
    for code in ("es", "en"):
        phrase = langs.spec(code).ask_which_item
        plan = fe.card_decision("musica", "play",
                                brief=_brief("", open_ids=BOTH), ask_phrase=phrase)
        assert plan["ask"], f"[{code}] the ASK branch produced no sentence"
        assert "{" not in plan["ask"], f"[{code}] an unfilled placeholder survived: {plan['ask']!r}"
        assert "youtube" in plan["ask"] and "musica" in plan["ask"], plan["ask"]
