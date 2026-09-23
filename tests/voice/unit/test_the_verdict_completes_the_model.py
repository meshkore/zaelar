"""V2-754 — the verdict COMPLETES the model; it never overrules it.

MEASURED, live session 3afe34a8 (2026-09-23, engine 3.33+dc36b4fc — the build V2-753 had just
shipped). The video card was open with a catalogue of Apollo 11 results and a video playing. Four
orders to get back to that catalogue, and what the two readers said about each:

    turn  he said                                          brief `screen_action`   the model called
    T2    «Vuelve al dashboard. Quiero seguir viendo       show_tab  0.96  ✓       play_item(item="volver al
           el catálogo.»                                                             inicio / catálogo") ✗
    T3    «Sí, el catálogo de vídeos del Apolo once.»      show_tab  0.88  ✓       — nothing —           ✗
    T4    «Venga, vuelve al inicio del widget de vídeo.»   restart   0.99  ✗       show_tab(tab="home")  ✓
    T5    «Muéstrame el inicio del widget de vídeo.»       restart   0.81  ✗       show_tab(tab="inicio") ✓

T2 ended in «¿a cuál te refieres?» (the engine asked WHICH ITEM when the doubt was WHICH ACTION); T3
in «te dejo otra vez el catálogo» over nothing; T4 in `unknown_tab` (the widget refused `home`); T5
finally worked, and he powered off. **Each reader was right exactly where the other was wrong**, and
nothing in the engine crossed them: the verdict was read only by scattered guards, the model's call
was the de-facto router, and a valid `show_tab` was refused over vocabulary.

THE ONE RULE this pins, in the only direction that evidence allows:

  · a VALID, resolvable call from the model runs, whatever the verdict says — on T4 a «verdict
    routes» design would have RESTARTED the video he was trying to leave, at 0.99;
  · where the model left the turn EMPTY (T3) or its call could not resolve (T2), the verdict's action
    on the still-open card fills the gap — with a payload it can fill honestly, through the same
    `action_mode_now` gate every model call goes through;
  · the empty-turn half fires only on a turn the brief read as an ORDER or an ANSWER — a comment that
    names an action («¿el siguiente es de la NASA?» → `next`) must not move the player;
  · when both are valid and disagree, the model runs and the disagreement is LOGGED — the measurement
    that will one day say whom to believe.

And the two payload shapes the rung could not fill before, both of which were the incident: an action
with NO payload (`pause`), and ONE required key that is a declared CHOICE, filled by an alias the
operator actually said («dashboard» → `inicio`, declared in the manifest, resolved by `widgets.enums`).

Deterministic on purpose: the live half is the table above and the Jev battery in the initiative.
What this pins is the RULE, its bounds, and its WIRING.

Run: .venv/bin/pytest tests/voice/unit/test_the_verdict_completes_the_model.py
"""
from __future__ import annotations

import pathlib
import threading

import pytest

from nucleo.flash import direct_action as _da
from nucleo.flash import turn_brief as _tb
from widgets import enums as _enums

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_PROVIDER = _ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"

#: His sentences, verbatim from the transcript. A paraphrase would be a test of a test.
T2 = "Vale, bueno, este no me gusta. Vuelve a la al dashboard. Quiero seguir viendo el catálogo."
T3 = "Sí, el el catálogo de vídeos del Apol once."
T4 = "Venga, vuelve al inicio del widget de vídeo."


def _brief(answers: dict, *, open_ids=("youtube",)):
    """A brief handle in the REAL shape `jev.ask_many` returns — the builder nodes 2.68 and 2.72 use."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def on_screen(monkeypatch):
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


class _Spent:
    """What the arbiter spent: the card it presented and the action it applied."""
    def __init__(self):
        self.presented: list[str] = []
        self.applied: list[tuple] = []
        self.events: list[tuple] = []

    def present(self, wid, **kw):
        self.presented.append(wid)

    def apply(self, wid, action, payload):
        self.applied.append((wid, action, dict(payload or {})))

    def emit(self, kind, label, **kw):
        self.events.append((label, kw.get("extra") or {}))


def _complete(brief, words, **kw):
    s = _Spent()
    fired = _da.complete(brief, operator_text=words, emit=s.emit, present=s.present,
                         apply_widget_data=s.apply, **kw)
    return fired, s


# ── 1 · THE TWO TURNS THE MODEL LEFT EMPTY OR UNRESOLVABLE ────────────────────────────────────────

def test_T3_an_empty_turn_is_completed_by_the_verdict(on_screen):
    """«Sí, el catálogo…» → the model said it would and called nothing. The brief had `show_tab`."""
    fired, s = _complete(_brief({_tb.TARGET_KEY: ("youtube:show_tab", 0.88),
                                 _tb.REQUEST_KEY: ("answer", 0.7)}), T3)
    assert fired == "show_tab"
    assert s.applied == [("youtube", "show_tab", {"tab": "inicio"})], "the face he named, by its alias"
    assert s.presented == ["youtube"]


def test_T2_an_unresolvable_call_is_completed_by_the_verdicts_OTHER_action(on_screen):
    """The model called `play_item` on a row that does not exist. The doubt was the ACTION, and the
    verdict had named it. `instead_of` is the model's own action, so an identical verdict is no help."""
    b = _brief({_tb.TARGET_KEY: ("youtube:show_tab", 0.96), _tb.REQUEST_KEY: ("order", 0.8)})
    fired, s = _complete(b, T2, widget_id="youtube", instead_of="play_item", require_order=False)
    assert fired == "show_tab" and s.applied[0][2] == {"tab": "inicio"}
    assert _complete(b, T2, widget_id="youtube", instead_of="show_tab", require_order=False)[0] == "", (
        "a verdict that names the SAME action the model already failed with cannot rescue it")


# ── 2 · THE BOUNDS — what it must NOT do ──────────────────────────────────────────────────────────

def test_T4_a_VALID_model_call_is_not_overruled_by_a_confident_wrong_verdict(on_screen):
    """`completes` only REPORTS the disagreement; the caller runs the model's call. At 0.99 the verdict
    said `restart` — «vuelve al inicio» — and the model's `show_tab` was the right one."""
    b = _brief({_tb.TARGET_KEY: ("youtube:restart", 0.99)})
    assert _da.completes(b, "youtube", model_action="show_tab") == "restart", "the disagreement is named"
    assert _da.completes(b, "youtube", model_action="restart") == "", "agreement is not a disagreement"
    assert _da.completes(b, "musica", model_action="pause") == "", "another card is nobody's business"


@pytest.mark.parametrize("kind,why", [
    ("comment", "a comment that names an action must not move the player"),
    ("greeting", "phatic contact"),
])
def test_a_CONFIDENT_remark_never_completes_an_empty_turn(on_screen, kind, why):
    # V2-756 — `complaint` left this list. It was here on the reading that «pero veo que es incapaz de
    # pararlo» is about US, but V2-750 (node 2.70) had already ruled the other way: a complaint about
    # what was just done IS an order to do it properly, and a complaint with nothing to redo answers
    # `none` on the screen question anyway («Vale, hasta aquí bien, aunque te ha costado bastante» →
    # none 0.92, measured). The case that pays for it is one row down.
    fired, s = _complete(_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97),
                                 _tb.REQUEST_KEY: (kind, 0.9)}), "Pero veo que es incapaz de pararlo.")
    assert fired == "" and s.applied == [], why


def test_a_question_that_is_really_an_ORDER_completes_the_turn(on_screen):
    """V2-757 — `question` left this list too, twelve hours later and for the same reason `complaint`
    did. «¿Puedes enseñarme el catálogo?» measured `show_tab` 0.85 with `question` 0.64: in Spanish a
    polite order is shaped like a question, and every GENUINE question answers `none` on the screen
    side anyway (0.78-0.94, measured), so the entry could only ever be wrong. Node 2.76."""
    fired, s = _complete(_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97),
                                 _tb.REQUEST_KEY: ("question", 0.64)}), "¿Puedes parar el vídeo?")
    assert fired == "pause" and s.applied == [("youtube", "pause", {})]


def test_a_COMPLAINT_about_what_we_just_failed_to_do_IS_an_order(on_screen):
    """V2-756, live session 74be8e9a: «He dicho que pares el vídeo. Que no me has oído.» — complaint,
    and the only thing he wants is the pause he already asked for."""
    fired, _s = _complete(_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97),
                                  _tb.REQUEST_KEY: ("complaint", 0.9)}),
                          "He dicho que pares el vídeo. Que no me has oído.")
    assert fired == "pause"


def test_without_a_request_verdict_at_all_the_empty_turn_is_left_alone(on_screen):
    """No `request_type` answer: the gate still fails CLOSED, exactly as V2-754 promised."""
    fired, _s = _complete(_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97)}), "páralo")
    assert fired == ""


def test_an_UNSURE_request_type_is_not_a_veto(on_screen):
    """V2-756 — this used to read the same as «absent» and fail closed, which let an unsure reader
    veto a near-certain one: «Para el vídeo» measured `screen_action = youtube:pause` 0.95 with
    `request_type` torn (answer 0.49 / comment 0.39), nothing fired, and he had to say «He dicho que
    pares el vídeo. Que no me has oído.». An answer below the bar has NO opinion; an answer that never
    came still fails closed (the test above)."""
    fired, _s = _complete(_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97),
                                  _tb.REQUEST_KEY: ("comment", 0.3)}), "Para el vídeo")
    assert fired == "pause"


def test_an_unsure_or_absent_screen_verdict_completes_nothing(on_screen):
    assert _complete(_brief({_tb.TARGET_KEY: ("youtube:show_tab", 0.4),
                             _tb.REQUEST_KEY: ("order", 0.9)}), T3)[0] == ""
    assert _complete(_brief({_tb.REQUEST_KEY: ("order", 0.9)}), T3)[0] == ""
    assert _complete(None, T3)[0] == ""


def test_a_verdict_about_a_card_that_CLOSED_is_no_verdict(monkeypatch):
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: False)
    assert _complete(_brief({_tb.TARGET_KEY: ("youtube:show_tab", 0.96),
                             _tb.REQUEST_KEY: ("order", 0.9)}), T3)[0] == ""


def test_it_never_raises_into_the_turn(on_screen):
    b = _brief({_tb.TARGET_KEY: ("youtube:show_tab", 0.96), _tb.REQUEST_KEY: ("order", 0.9)})

    def boom(*a, **k):
        raise RuntimeError("widget down")
    assert _da.complete(b, operator_text=T3, emit=lambda *a, **k: None,
                        present=lambda *a, **k: None, apply_widget_data=boom) == ""


# ── 3 · THE TWO PAYLOAD SHAPES THE RUNG COULD NOT FILL ────────────────────────────────────────────

def test_an_action_with_NO_payload_fires_bare_and_one_with_optional_keys_does_not():
    """`pause` declares nothing: nothing to invent. `load` declares four optional keys: which of the
    four to stuff a sentence into is the invention V2-741 refuses (its own test pins that)."""
    assert _da.no_payload("youtube", "pause") is True
    assert _da.no_payload("youtube", "load") is False
    assert _da.no_payload("youtube", "show_tab") is False
    assert _da.no_payload("youtube", "no_such_action") is False


def test_a_choice_key_is_filled_by_an_ALIAS_he_said_and_never_by_the_sentence():
    assert _da.enum_fill("youtube", "show_tab", T2) == {"tab": "inicio"}
    assert _da.enum_fill("youtube", "show_tab", "ponme el tercero") == {}, "no face named → nothing"
    assert _da.enum_fill("youtube", "show_tab", "del reproductor a la cola") == {}, "two faces → a question"
    assert _da.fillable_key("youtube", "show_tab") == "", "V2-742's guard is intact: a sentence is not a value"


def test_resolve_routes_both_shapes_through_the_rung(on_screen):
    r = _da.resolve("", brief=_brief({_tb.TARGET_KEY: ("youtube:pause", 0.97)}), operator_text="páralo")
    assert (r["action"], r["payload"], r["source"]) == ("pause", {}, "no-payload")
    r = _da.resolve("", brief=_brief({_tb.TARGET_KEY: ("youtube:show_tab", 0.96)}), operator_text=T2)
    assert (r["action"], r["payload"], r["source"]) == ("show_tab", {"tab": "inicio"}, "enum-alias")
    assert _da.resolve("", brief=_brief({_tb.TARGET_KEY: ("youtube:load", 0.9)}), operator_text="ponme algo") == {}


# ── 4 · THE DECLARATION IS ONE TEXT, READ BY BOTH ─────────────────────────────────────────────────

def test_the_faces_aliases_live_in_the_manifest_and_the_parser_reads_them():
    from widgets import runtime
    spec = runtime.get("youtube")["actions"]["show_tab"]["payload"]["tab"]
    table = _enums.parse(spec)
    from widgets.youtube import data as ydata
    assert sorted(table) == sorted(ydata._TABS), "the enum's values ARE the card's faces — nothing may drift"
    assert "home" in table["inicio"] and "dashboard" in table["inicio"], "the two words from the incident"
    assert _enums.resolve(spec, "home") == "inicio"
    assert _enums.resolve(spec, "lateral") == "", "unknown stays unknown — never the nearest value"


def test_the_parser_does_not_mistake_a_free_text_hint_for_an_enumeration():
    assert _enums.parse("texto a buscar (vacío = quitar filtro)") == {}
    assert _enums.parse("qué buscar, en lenguaje natural") == {}
    assert list(_enums.parse("'title' o 'added'")) == ["title", "added"], "the older house spelling"


# ── 5 · THE WIRING — a rule in a module nobody calls is V2-750's catalog_widget ───────────────────

def test_the_provider_completes_an_UNRESOLVED_call_before_asking_which_item():
    body = _PROVIDER.read_text(encoding="utf-8")
    i = body.index("if not res.ok:")
    seg = body[i:i + 1200]
    assert "_direct_action.complete(" in seg and 'instead_of=action_name' in seg
    assert seg.index("_direct_action.complete(") < seg.index("ask_which_item"), "the verdict goes BEFORE the question"


def test_the_provider_completes_an_EMPTY_turn_and_logs_a_disagreement():
    body = _PROVIDER.read_text(encoding="utf-8")
    i = body.index("_no_tool = (")
    assert "_direct_action.complete(" in body[i:i + 900], "the empty-turn site"
    # V2-756 — anchored on ORDER, not on a byte distance: the repair of a key the model left empty
    # (`fill_missing`) now sits between the two, and a window measured in characters made a correct
    # wiring look broken.
    j = body.index('_apply_widget_data(_cd["card"], action_name, res.payload, ref)')
    k = body.index("_direct_action.completes(")
    assert k < j, "the disagreement is logged where the model's call runs"
    assert body.index("_direct_action.fill_missing(", k, j) > k, (
        "and the empty key is repaired before the call is applied, not after (V2-756)")
