"""V2-750 — the grammar proposes, the verdict decides: «vamos a hacer una cosa» is not an order to build.

MEASURED, live session b41925f6 (2026-09-22). The YouTube card was already on his screen — he had
opened it with his own hand one second earlier — when he said:

    «Entonces, vamos a hacer una cosa, ábreme el widget de vídeo, preséntame un catálogo de vídeos
     sobre el Apolo once.»

`router_guards.looks_like_create_widget` answered True. The `show_widget` tool was redirected to the
WIDGET GENERATOR, a Brain Worker opened, and two minutes later his catalogue had a brand-new
duplicate video player in it called **`entonces-vamos-cosa`** — a card named after the preamble of an
order. The regex match, verbatim: `hacer una cosa, abreme el widget`. `_CREATE_WIDGET_RE` permits 45
characters of anything between a create verb and the word «widget» and never asks whether the verb
GOVERNS it.

The turn's own verdict had already answered: `catalog_widget = youtube` at **1.00** — asked, paid
for, and read by nobody — and on the next turn `screen_action = youtube:search` at 0.91, read and
overruled. Third time this month with that exact shape (V2-741 a grammar licence, V2-748 the
irreversibles gate), which is why the repair is a rule about AUTHORITY and not another pattern.

## AND WHY A BIGGER TABLE WAS NEVER THE ANSWER

Measured over the five-language corpus (node 2.68, live): the regex is not Spanish-biased, it is
**Latin-script only**, and it is wrong in both directions — «チェスのウィジェットを作って» (make me a
chess widget) returns False, so in Chinese, Japanese and Hindi the generator is UNREACHABLE by
voice. Writing CJK and Devanagari verb tables would be the same mistake in three more scripts.

    regex today   es 8/9 · en 9/9 · zh 6/9 · ja 6/9 · hi 6/9      (35/45)
    build_decision   9/9 ·    9/9 ·    9/9 ·    9/9 ·    9/9      (45/45)

Deterministic here on purpose: the live half is node 2.68. What this file pins is the RULE and its
WIRING — that the decision composes the two verdicts, that each clause fails towards «do not build»,
and that the provider's guard actually asks it instead of asking the regex.

Run: .venv/bin/pytest tests/voice/unit/test_a_verb_table_is_not_a_router.py
"""
from __future__ import annotations

import ast
import pathlib
import threading

import pytest

from nucleo.flash import build_decision as _bd
from nucleo.flash import router_guards as _rg
from nucleo.flash import turn_brief as _tb

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_PROVIDER = _ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"

#: His sentence, verbatim from the transcript. A paraphrase would be a test of a test.
HIS_WORDS = ("Entonces, vamos a hacer una cosa, ábreme el widget de vídeo, "
             "preséntame un catálogo de vídeos sobre el Apolo once.")


def _brief(answers: dict, *, open_ids=()):
    """A brief handle in the REAL shape `jev.ask_many` returns — Event set, result dict, stamp.

    Built rather than mocked, because what is under test is `turn_brief.read`'s own path through it:
    a double with a convenient shape would pass with the reader disconnected.
    """
    ev = threading.Event()
    ev.set()                    # `jev.peek` returns None on an unset event: an unset one tests nothing
    result = {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": result}


# ── the sentence he actually said ────────────────────────────────────────────────────────────────

def test_the_grammar_still_reads_his_sentence_as_a_create():
    """The defect is NOT repaired in the regex, and that is the point: it is left exactly as it was,
    proposing, so a repair that quietly deleted a pattern would not read as a pass here."""
    assert _rg.looks_like_create_widget(HIS_WORDS) is True
    assert _rg.looks_like_create_widget("ábreme el widget de vídeo") is False, (
        "without the filler it never fired — the trigger is «hacer» three clauses away")


def test_the_verdict_refuses_the_generator_over_a_card_we_already_have():
    brief = _brief({_tb.CATALOG_KEY: ("youtube", 0.98), _bd.BUILD_KEY: ("use_existing", 0.78)})
    build, why = _bd.decide(HIS_WORDS, brief=brief)
    assert build is False, "the generator was reached over a card that already exists"
    assert "youtube" in why, "the refusal has to SAY which card it recognised"


def test_the_card_may_be_named_by_either_twin(monkeypatch):
    """`turn_brief.build` asks `screen_action` when something is open and `catalog_widget` when
    nothing is, and must not be made to ask both. `screen_action` names its owner in the key, so the
    veto reads whichever one the turn actually carries."""
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    brief = _brief({_tb.TARGET_KEY: ("youtube:search", 0.91), _bd.BUILD_KEY: ("use_existing", 0.7)},
                   open_ids=("youtube",))
    assert _bd.named_card(brief) == "youtube"
    assert _bd.decide(HIS_WORDS, brief=brief)[0] is False


# ── and a genuine create still reaches the generator ─────────────────────────────────────────────

def test_a_real_create_is_untouched_when_the_grammar_sees_it():
    brief = _brief({_tb.CATALOG_KEY: ("none", 0.97), _bd.BUILD_KEY: ("build_new", 0.81)})
    assert _bd.decide("créame un widget de ajedrez", brief=brief)[0] is True


def test_a_create_the_grammar_CANNOT_read_now_reaches_the_generator():
    """The other direction, and the one no table of ours can fix: «make me a chess widget» in
    Japanese. The regex is blind; the verdict is not."""
    ja = "チェスのウィジェットを作って"
    assert _rg.looks_like_create_widget(ja) is False, "if this ever fires, the table grew — read the header"
    brief = _brief({_tb.CATALOG_KEY: ("none", 0.97), _bd.BUILD_KEY: ("build_new", 0.78)})
    build, why = _bd.decide(ja, brief=brief)
    assert build is True and _bd.BUILD_KEY in why


def test_the_veto_does_not_fire_over_a_verdict_that_says_BUILD():
    """A named card refuses a create only while `build_or_use` disagrees with it. Dropping that
    condition makes the veto swallow «abre la agenda y luego créame un widget de calorías» — an order
    that names a card AND asks for a new one — which the grammar gets right on its own."""
    brief = _brief({_tb.CATALOG_KEY: ("youtube", 0.9), _bd.BUILD_KEY: ("build_new", 0.8)})
    assert _bd.decide("créame un widget nuevo", brief=brief, proposed=True)[0] is True


def test_an_unsure_build_verdict_cannot_start_a_generator():
    """The gate is `turn_brief.read`'s, not a raw dictionary lookup. Reading the choice past the gate
    would let a 0.20 shrug spend two minutes writing a widget."""
    brief = _brief({_tb.CATALOG_KEY: ("none", 0.9), _bd.BUILD_KEY: ("build_new", 0.20)})
    assert _bd.decide("algo que la gramática no ve", brief=brief, proposed=False)[0] is False


def test_building_demands_a_POSITIVE_verdict_and_no_card_named():
    """Two independent signals must agree. Either one alone leaves today's path, because a widget is
    two minutes and a new folder in his catalogue: that deserves a yes, not the absence of a no."""
    only_build = _brief({_tb.CATALOG_KEY: ("youtube", 0.9), _bd.BUILD_KEY: ("build_new", 0.8)})
    assert _bd.decide("algo", brief=only_build, proposed=False)[0] is False
    only_none = _brief({_tb.CATALOG_KEY: ("none", 0.9), _bd.BUILD_KEY: ("use_existing", 0.8)})
    assert _bd.decide("algo", brief=only_none, proposed=False)[0] is False


# ── every absence is today's path, bit for bit ───────────────────────────────────────────────────

@pytest.mark.parametrize("brief,label", [
    (None, "no brief at all"),
    ({"event": threading.Event(), "turn_id": "t", "open_ids": [], "result": None}, "still in flight"),
    (_brief({}), "answered nothing"),
    (_brief({_tb.CATALOG_KEY: ("youtube", 0.31), _bd.BUILD_KEY: ("use_existing", 0.2)}), "under the gate"),
])
def test_an_absent_or_unsure_verdict_leaves_the_grammar_in_charge(brief, label):
    assert _bd.decide(HIS_WORDS, brief=brief, proposed=True)[0] is True, label
    assert _bd.decide("hola qué tal", brief=brief, proposed=False)[0] is False, label


def test_a_broken_brief_never_breaks_a_turn():
    """A classifier may not raise. Anything unreadable answers «no opinion»."""
    class _Boom(dict):
        def __getitem__(self, k):
            raise RuntimeError("boom")
    assert _bd.decide(HIS_WORDS, brief=_Boom(), proposed=True)[0] is True
    assert _bd.named_card(_Boom()) == ""


# ── the WIRING: the provider's guard asks the decision, not the regex ────────────────────────────

def _create_guard_test() -> str:
    """The source of the `if`/`elif` that redirects `show_widget` to the generator.

    Read from the AST and not by matching text near the emit: the explanation of a fix survives the
    deletion of the fix, so a marker-based guard goes green on a file whose code is gone.
    """
    tree = ast.parse(_PROVIDER.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
        if "show_widget→CREATE" in body:
            hits.append((len(body), ast.unparse(node.test)))
    if not hits:
        raise AssertionError("the show_widget→CREATE guard is no longer an `if` in providers/nucleo.py")
    # The marker sits inside several nested `if`s; the guard is the INNERMOST one, i.e. the smallest
    # body that still carries it. Taking the first match found `if name == 'show_widget'`, three
    # levels out — a condition that has nothing to do with this decision and would never go red.
    return min(hits)[1]


def test_the_guard_reads_the_decision_and_not_the_bare_grammar():
    cond = _create_guard_test()
    assert "_build_decision" in cond or "_bd" in cond, (
        "the generator is still gated on the regex alone — that is the measured defect")


def test_the_grammar_is_handed_IN_so_the_two_never_disagree():
    """`decide` asks the regex itself when nobody hands it one. The provider hands its own, so the
    sentence is classified once per turn and one answer cannot drift from the other."""
    src = _PROVIDER.read_text(encoding="utf-8")
    i = src.index("show_widget→CREATE")
    window = src[max(0, i - 700):i]
    assert "proposed=" in window and "looks_like_create_widget" in window


def test_the_question_is_asked_on_every_turn():
    """A verdict nobody asks for is a verdict nobody can read — which is how `catalog_widget` came to
    answer 1.00 into a void. It rides the brief that already flies, so it costs no round trip."""
    import inspect
    src = inspect.getsource(_tb.build)
    assert "BUILD_KEY" in src, "build_or_use is not in the turn brief"
    assert "if " not in src.split("BUILD_KEY")[0].split("qs: dict")[-1], (
        "the question is conditional — it has to ride every brief")


def test_the_card_is_certain_even_when_the_action_is_not(monkeypatch):
    """V2-773 final pass (C3): «Schedule it as Catch up with Ethan» over the open agenda read
    `agenda:update_meeting` 0.51 · `agenda:add_meeting` 0.27 · none 0.18 — unsure as an ACTION, 0.82 as a
    CARD — and the claim «booked» with no call escaped the repair whose only gate is this name."""
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: _o == "agenda")
    brief = _brief({_tb.TARGET_KEY: ("agenda:update_meeting", 0.48)}, open_ids=("agenda",))
    brief["result"][_tb.TARGET_KEY]["probs"] = {"agenda:update_meeting": 0.51, "agenda:add_meeting": 0.27,
                                                "none": 0.18, "agenda:add_task": 0.04}
    assert _bd.named_card(brief) == "agenda"
    brief["result"][_tb.TARGET_KEY]["probs"] = {"agenda:update_meeting": 0.30, "youtube:play": 0.30, "none": 0.40}
    assert _bd.named_card(brief) == "", "mass split across cards names nobody"
    brief["result"][_tb.TARGET_KEY]["probs"] = {"youtube:play": 0.9, "none": 0.1}
    assert _bd.named_card(brief) == "", "a card no longer open is no card"


def test_an_order_names_a_card_through_either_twin(monkeypatch):
    """V2-773 (K1, E1 of the demo): «Message Ethan on Telegram» with no card open read catalogue=messaging 1.0,
    the model promised «I'll send Ethan a Telegram now» and called nothing — and `names_an_order`, reading
    `screen_action` alone, said no card was named, so no repair ever looked at the promise."""
    from nucleo.flash import direct_action as _da
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    closed = _brief({_tb.CATALOG_KEY: ("mensajeria", 0.99), _tb.REQUEST_KEY: ("order", 0.96)})
    assert _da.names_an_order(closed), "the catalogue names the card while it is closed"
    remark = _brief({_tb.CATALOG_KEY: ("mensajeria", 0.99), _tb.REQUEST_KEY: ("comment", 0.9)})
    assert not _da.names_an_order(remark), "a remark about a card is not an order on it"
    nobody = _brief({_tb.CATALOG_KEY: ("none", 0.97), _tb.REQUEST_KEY: ("order", 0.96)})
    assert not _da.names_an_order(nobody)
    open_ = _brief({_tb.TARGET_KEY: ("youtube:search", 0.91), _tb.REQUEST_KEY: ("order", 0.9)}, open_ids=("youtube",))
    assert _da.names_an_order(open_), "…and screen_action still names it while open"


def test_a_stop_aimed_at_a_card_never_kills_the_errands(monkeypatch):
    """V2-773 (demo kickoff + video): «Stop it and close the video widget» with the verdict at `youtube:close`
    0.97 and canvas=close 1.0 — the stop-worker backstop read «stop it» as «stop the background work» and
    CANCELLED the two errands launched a minute earlier."""
    from nucleo.flash import direct_action as _da
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    video = _brief({_tb.TARGET_KEY: ("youtube:close", 0.97), _tb.CANVAS_KEY: ("close", 1.0)}, open_ids=("youtube",))
    assert _da.aims_at_a_card(video)
    canvas_only = _brief({_tb.CANVAS_KEY: ("close", 0.9)})
    assert _da.aims_at_a_card(canvas_only)
    work = _brief({_tb.CANVAS_KEY: ("neither", 0.95), _tb.REQUEST_KEY: ("order", 0.9)})
    assert not _da.aims_at_a_card(work), "«stop the search» names no card: the backstop keeps its job"
    src = (_ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_router.looks_like_stop_work(text) and not _direct_action.aims_at_a_card(_brief)" in src


def test_the_verdict_alone_can_send_an_unkept_order_to_a_worker():
    """V2-773 (demo kickoff, A1): «find me three 27-inch 4K monitors under 400 dollars» — the verdict said
    escalate, the model answered «On it — I'll show you the options as soon as I have them» and called
    nothing, and no errand was born: the backstop only knew the verb tables."""
    from nucleo.flash import direct_action as _da
    assert _da.verdict_escalates(_brief({_tb.ESCALATE_KEY: ("escalate", 1.0), _tb.REQUEST_KEY: ("order", 0.99)}))
    assert not _da.verdict_escalates(_brief({_tb.ESCALATE_KEY: ("handle_inline", 0.9), _tb.REQUEST_KEY: ("order", 0.99)}))
    assert not _da.verdict_escalates(_brief({_tb.ESCALATE_KEY: ("escalate", 1.0), _tb.REQUEST_KEY: ("comment", 0.9)})), (
        "a remark is not an order, whatever it would take to act on it")
    assert not _da.verdict_escalates(_brief({_tb.ESCALATE_KEY: ("escalate", 0.3), _tb.REQUEST_KEY: ("order", 0.99)})), "unsure"
    # V2-773 (demo R1, 2026-09-27): «When does my Tesla insurance renew?» → «March 12, 2027» — the verdict said
    # escalate (0.84) and a Brain Worker went to the web over a fact the turn had just said. A QUESTION the reply
    # answered without a promise is not an errand; an ORDER keeps the verdict whatever the reply sounds like.
    q = _brief({_tb.ESCALATE_KEY: ("escalate", 0.84), _tb.REQUEST_KEY: ("question", 0.6)})
    assert _da.verdict_escalates(q), "unanswered, the question may well be work («what's the cheapest flight?»)"
    assert not _da.verdict_escalates(q, answered=True), "THE BUG: an answered question spawned a worker"
    o = _brief({_tb.ESCALATE_KEY: ("escalate", 1.0), _tb.REQUEST_KEY: ("order", 0.99)})
    assert _da.verdict_escalates(o, answered=True), "an order is work even when the reply sounds finished"
    src = (_ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert src.count("_direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))") == 2, (
        "both backstop gates pass whether the reply answered")


def test_a_repair_that_may_write_needs_a_sure_action_verdict(monkeypatch):
    """V2-773 (demo v3, C2): «Find me a free 45-minute slot» read `agenda:add_meeting` at 0.54, the reply was
    an ANSWER, and the promise repair booked «Call with Ethan» — a write nobody ordered."""
    from nucleo.flash import direct_action as _da
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    unsure = _brief({_tb.TARGET_KEY: ("agenda:add_meeting", 0.54), _tb.REQUEST_KEY: ("order", 0.84)}, open_ids=("agenda",))
    assert _da.names_an_order(unsure), "it names the card — the mute question still reads it"
    assert not _da.names_an_order(unsure, sure=0.8), "…but a WRITE on it needs a sure action"
    sure = _brief({_tb.TARGET_KEY: ("agenda:add_meeting", 0.93), _tb.REQUEST_KEY: ("order", 0.84)}, open_ids=("agenda",))
    assert _da.names_an_order(sure, sure=0.8)
    src = (_ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_direct_action.names_an_order(_brief, sure=0.8)" in src, "the promise repair's gate must carry the floor"


def test_a_show_that_names_a_card_we_have_beats_the_worker_and_an_undone_order_over_a_card_escalates():
    """V2-773 (demo S1 / F1, 2026-09-27). S1: «Show me the monitors» over the finished errand's CLOSED sheet — the
    escalate verdict fired before the show branch and a second worker searched the monitors again. F1: «Write me
    a one-page summary … in a document» — the catalogue named `documento` (0.86), nothing was called, the
    escalation verdict was unsure (0.15), and «on its way» was on its way nowhere."""
    from nucleo.flash import direct_action as _da
    assert _da.order_over_a_card_left_undone(_brief({_tb.REQUEST_KEY: ("order", 0.59), _tb.CATALOG_KEY: ("documento", 0.86)}))
    assert not _da.order_over_a_card_left_undone(_brief({_tb.REQUEST_KEY: ("question", 0.9), _tb.CATALOG_KEY: ("agenda", 0.9)})), "a question is not work owed"
    assert not _da.order_over_a_card_left_undone(_brief({_tb.REQUEST_KEY: ("order", 0.9), _tb.CATALOG_KEY: ("none", 0.8)})), "no card named: the other gates decide"
    assert not _da.order_over_a_card_left_undone(_brief({_tb.REQUEST_KEY: ("order", 0.3), _tb.CATALOG_KEY: ("documento", 0.9)})), "unsure"
    src = (_ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    i_show = src.index('_pw = _identify(_op_text) if _router.looks_like_show_strict(_op_text) else ""')
    i_esc = src.index("🧭 escalada por backstop (prometió crear/gestionar sin escalar)", i_show)
    assert src.index("🪟 show por backstop de promesa", i_show) < i_esc, "a named card is shown BEFORE the worker gate"
    assert "or _direct_action.order_over_a_card_left_undone(_brief)):" in src[i_show:i_esc]
