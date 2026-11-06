"""A transport order on a card's queue runs in the turn that asks it, and in no other (node 2.1628).

Use case build-a-video-playlist-from-links, 2026-11-06, ES (sandbox) and EN (local engine), both scored 2 after 4-5.
Three readers failed, one per turn, and each one is a CLASS, not the video card:

  1. The card door read the card's own output control as a write on his real app. «ponla seguida y dime qué está
     sonando» / «play it and let me know what's playing» → the brief answered `wants_words = tell` (0.98-1.00) because
     he also wants to be told, and `request_type = order` at 0.68 / 0.84 — an order, below the veto bar; `screen_action`
     was ABSENT (the card was closed) and `catalog_widget` named the music card, so no paid verdict could complete the
     model. The model called `youtube:play_item` (right) and `card._asks_without_ordering` dropped it as «a question»
     — the clause that keeps «show my messages» from marking a mail unread in his real app (2.908, kept). A control
     that starts or suspends what the card produces (`effects.OUTPUT_START`/`OUTPUT_STOP`, declared by
     `runtime.produce`/`suspend`) marks nothing in his app and the card itself undoes it, so a «tell me» never vetoes
     it; a sure `question` still does, and a real-app write under the same verdicts stays unwritten.
  2. The empty-turn completion fired the WEAKEST reader. «¿Eso va solo pasando al siguiente o se queda parado al
     terminar?» → `request_type = question` 0.80, `screen_action = youtube:next` 0.54, the model called nothing — and
     `direct_action.complete` ran `next`, which on an empty player starts the first video. The next turn's model read
     «youtube:next · done · now» and skipped nothing when he finally asked for it. A question read more surely than the
     action outranks it; a polite order measured action-first («¿Puedes enseñarme el catálogo?» 0.85 / 0.64, V2-757)
     still completes. No constant: two confidences the turn already paid for, compared.
  3. A queue step attests the item change, and the manifest did not say so. «Dale, pásame al siguiente» → end state
     `youtube:videoId` 0.77, `youtube:next` 0.60, and `spec.gate_completion` refused the completion because `next`
     declared no `done_when`. `load` and `play_result` declare «videoId changed»; `next` and `play_item` now do too.

Each part carries a variant the failing turn did not (the other language, another card, a reworded request), and each
is disarmed in place — the mechanism put back to its failing shape, the red asserted, the mechanism restored in a
`finally` — because a test that was never red proves nothing.
"""
from __future__ import annotations

import copy
import threading

import pytest

from nucleo.acts import card
from nucleo.circuit import spec as _spec
from nucleo.flash import direct_action as _da
from nucleo.turn import brief as _tb, verdicts


def _brief(answers: dict, *, open_ids=("youtube",)):
    """A brief handle in the REAL shape `jev.ask_many` returns: {key: (choice, confidence)}."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


# ── 1 · the card door: the card's own output control is not a write on his real app ────────────────────────

#: (card, output control, his words, request_type confidence) — the two measured turns and two variants (another
#: control, EN/ES). In every one `screen_action` was ABSENT (the card was closed, the brief enumerates open cards) and
#: `catalog_widget` named the wrong card, so no paid verdict could complete the model: the act's declared effect decides.
ORDER_AND_REPORT = [
    ("youtube", "play_item", "Vale, pues ponla seguida y dime qué está sonando ahora mismo.", 0.68),
    ("youtube", "play_item", "play it and let me know what's playing", 0.84),
    ("youtube", "next", "skip to the next one and tell me what comes after it", 0.72),
    ("youtube", "pause", "páralo un momento y dime cuánto le queda", 0.60),
]

#: (card, write on his real app, his words, request_type confidence) — the same verdicts keep these unwritten.
REAL_APP_WRITES = [
    ("mensajeria", "unread", "show my messages", 0.60),                      # show-my-messages EN, 2026-10-28 (2.908)
    ("mensajeria", "unread", "enséñame mis mensajes", 0.75),
    ("agenda", "add_meeting", "apunta al dentista el martes a las 10 y dime qué más tengo ese día", 0.70),
]


def _order_and_report(order_conf: float):
    return _brief({_tb.REQUEST_KEY: ("order", order_conf), _tb.WORDS_KEY: ("tell", 0.98)})


@pytest.mark.parametrize("wid,action,said,order_conf", ORDER_AND_REPORT)
def test_an_output_control_he_also_wants_reported_runs(wid, action, said, order_conf):
    from widgets import effects as _fx
    assert order_conf < verdicts.VETO, "the measured turns are orders BELOW the veto bar — that is the case"
    assert _fx.carries(wid, action, _fx.OUTPUT_START) or _fx.carries(wid, action, _fx.OUTPUT_STOP), "declared control"
    assert not card.question_keeps_unwritten(wid, action, said, _order_and_report(order_conf)), (
        f"{wid}:{action} is the card's own output control on an order he also wants reported; `tell` cannot veto it")


@pytest.mark.parametrize("wid,action,said,order_conf", REAL_APP_WRITES)
def test_a_write_on_his_real_app_under_the_same_verdicts_stays_unwritten(wid, action, said, order_conf):
    from widgets import effects as _fx
    assert _fx.carries(wid, action, _fx.DATA_WRITE) and not _fx.carries(wid, action, _fx.OUTPUT_START)
    assert card.question_keeps_unwritten(wid, action, said, _order_and_report(order_conf)), (
        f"{wid}:{action} marks his real app: a sure «tell me» with no sure order keeps it unwritten (2.908)")


def test_a_sure_question_keeps_both_kinds_unwritten_and_an_unsure_one_is_the_models_path():
    sure_q = _brief({_tb.REQUEST_KEY: ("question", 0.93), _tb.WORDS_KEY: ("tell", 0.98)})
    assert card.question_keeps_unwritten("youtube", "next", "¿va solo al siguiente?", sure_q)
    assert card.question_keeps_unwritten("mensajeria", "unread", "what's new in my inbox", sure_q)
    unsure_q = _brief({_tb.REQUEST_KEY: ("question", 0.64)})
    assert not card.question_keeps_unwritten("youtube", "pause", "¿puedes parar el vídeo?", unsure_q), (
        "a question below the veto bar is the model's own path (CRIT-K2)")


def test_disarm_a_control_read_as_a_real_app_write_is_vetoed_again():
    """With the effects reader denying that the control starts or suspends the card's output, the clause reads it as a
    write on his real app and the measured ES turn is vetoed again. Restored in `finally`."""
    from widgets import effects as _fx
    kept = _fx.carries

    def no_output(wid, action, effect):
        return False if effect in (_fx.OUTPUT_START, _fx.OUTPUT_STOP) else kept(wid, action, effect)
    _fx.carries = no_output
    try:
        assert not _fx.carries("youtube", "play_item", _fx.OUTPUT_START), "the disarm did not land"
        wid, action, said, conf = ORDER_AND_REPORT[0]
        with pytest.raises(AssertionError):
            test_an_output_control_he_also_wants_reported_runs(wid, action, said, conf)
    finally:
        _fx.carries = kept
    wid, action, said, conf = ORDER_AND_REPORT[0]
    test_an_output_control_he_also_wants_reported_runs(wid, action, said, conf)


# ── 2 · the empty turn: a question read more surely than the action completes nothing ───────────────────────

class _Spent:
    def __init__(self):
        self.applied: list[tuple] = []
        self.presented: list[str] = []

    def present(self, wid, **kw):
        self.presented.append(wid)

    def apply(self, wid, action, payload):
        self.applied.append((wid, action, dict(payload or {})))

    def emit(self, *a, **kw):
        pass


def _complete(brief, words):
    s = _Spent()
    fired = _da.complete(brief, operator_text=words, emit=s.emit, present=s.present, apply_widget_data=s.apply)
    return fired, s


@pytest.fixture
def on_screen(monkeypatch):
    """The video card is the one open card and the one his last turn acted on: the rung's `undecided` reader (a control
    two open cards share) and `subject_card` read that state from memory, and a neighbour test may leave another card there."""
    from memory import api as _memapi
    from nucleo import canvas_focus as _cf
    from nucleo.acts import named_target as _nt
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": ["youtube"]})
    monkeypatch.setattr(_cf, "last_turn_card", lambda _ids: "youtube")
    _nt._PARKED.clear()          # a «which card?» a neighbour test parked would answer his sentence (a `volume_down` did)
    yield
    _nt._PARKED.clear()


#: (his words, question confidence, screen action, its confidence)
GENUINE_QUESTIONS = [
    ("Jaja clásico, Rickroll de aperitivo. ¿Eso va solo pasando al siguiente o se queda parado al terminar?",
     0.80, "youtube:next", 0.54),                                          # the measured ES turn
    ("does it move on to the next one by itself or stop at the end?", 0.86, "youtube:next", 0.61),
    ("¿la lista se repite cuando acaba el último?", 0.78, "youtube:restart", 0.52),
]


@pytest.mark.parametrize("said,q_conf,action,a_conf", GENUINE_QUESTIONS)
def test_a_question_read_more_surely_than_the_action_completes_nothing(on_screen, said, q_conf, action, a_conf):
    assert a_conf >= verdicts.LICENCE, "the action verdict is at the licence bar — the completion WOULD have fired"
    fired, s = _complete(_brief({_tb.TARGET_KEY: (action, a_conf), _tb.REQUEST_KEY: ("question", q_conf)}), said)
    assert fired == "" and s.applied == [], f"a turn that only asks about the queue moved it: {s.applied}"


def test_a_polite_order_measured_action_first_still_completes(on_screen):
    """V2-757's case keeps its path: the action is the stronger reader."""
    fired, s = _complete(_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97), _tb.REQUEST_KEY: ("question", 0.64)}),
                         "¿Puedes parar el vídeo?")
    assert fired == "pause" and s.applied == [("youtube", "pause", {})]
    fired, s = _complete(_brief({_tb.TARGET_KEY: ("youtube:next", 0.75), _tb.REQUEST_KEY: ("question", 0.60)}),
                         "¿Me pones el siguiente?")
    assert fired == "next" and s.applied == [("youtube", "next", {})]


def test_disarm_a_completion_that_never_compares_the_readers_skips_on_a_question(on_screen):
    kept = _da.a_question_outranks_the_action
    _da.a_question_outranks_the_action = lambda *a, **k: False
    try:
        assert _da.a_question_outranks_the_action(None, None) is False, "the disarm did not land"
        said, q_conf, action, a_conf = GENUINE_QUESTIONS[0]
        fired, s = _complete(_brief({_tb.TARGET_KEY: (action, a_conf), _tb.REQUEST_KEY: ("question", q_conf)}), said)
        assert fired == "next" and s.applied == [("youtube", "next", {})], "disarmed, the question must skip again"
    finally:
        _da.a_question_outranks_the_action = kept
    said, q_conf, action, a_conf = GENUINE_QUESTIONS[0]
    assert _complete(_brief({_tb.TARGET_KEY: (action, a_conf), _tb.REQUEST_KEY: ("question", q_conf)}), said)[0] == ""


# ── 3 · the queue steps declare the item change they attest ──────────────────────────────────────────────────

def _end_brief(action: str, a_conf: float, end: str, e_conf: float):
    return _brief({_tb.TARGET_KEY: (action, a_conf), _spec.END_KEY: (end, e_conf)})


@pytest.mark.parametrize("action", ["next", "play_item"])
def test_a_queue_step_attests_the_item_change_so_the_completion_may_fire(action):
    """The measured ES turn: «Dale, pásame al siguiente, quiero ver ya el de PSY» → end state `youtube:videoId` 0.77,
    `youtube:next` 0.60 — both under the veto bar, so the end state governs, and the step must attest it."""
    tpl = _spec.template_of("youtube", action)
    assert tpl is not None and _spec.target_of(tpl) == "youtube:videoId", f"{action} must declare the item change"
    assert _spec.gate_completion(_end_brief(f"youtube:{action}", 0.60, "youtube:videoId", 0.77), "youtube", action) == ""


def test_a_step_that_attests_nothing_is_still_refused_under_a_sure_end_state():
    why = _spec.gate_completion(_end_brief("youtube:volume_up", 0.60, "youtube:videoId", 0.77), "youtube", "volume_up")
    assert "attests nothing" in why


def test_disarm_a_queue_step_with_no_declared_end_state_is_refused_again():
    kept = _spec._manifest

    def stripped(wid: str) -> dict:
        man = copy.deepcopy(kept(wid))
        for a in ("next", "play_item"):
            (man.get("actions") or {}).get(a, {}).pop("done_when", None)
        return man
    _spec._manifest = stripped
    try:
        assert _spec.template_of("youtube", "next") is None, "the disarm did not land"
        why = _spec.gate_completion(_end_brief("youtube:next", 0.60, "youtube:videoId", 0.77), "youtube", "next")
        assert "attests nothing" in why, "disarmed, the gate must refuse the skip again"
    finally:
        _spec._manifest = kept
    assert _spec.gate_completion(_end_brief("youtube:next", 0.60, "youtube:videoId", 0.77), "youtube", "next") == ""
