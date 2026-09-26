"""Node 3.73 — the rung between «answer it» and «spend five minutes on it», and the three guards
that were overruling the verdict the engine already pays for (V2-741).

MEASURED, live session 092569ab (2026-09-21, engine 3.33+3e44994b — the CURRENT build, not a stale
one). The operator asked for a catalogue of Apollo 11 videos. Four things then happened in order,
and every one of them is a test below:

  146.8s  the turn brief answered `screen_action = youtube:search` at **0.97** — the right card, the
          right action, and the cheap one.
  149.3s  the model called `play_video(query="Apollo 11 documentales")`, which was also right, and
          `video_license` ate it as context-bleed: its conjugated-verb table has no «preparar» and no
          «podrías».
  193.2s  with no tool fired, the reply was a promise with nothing behind it; the friction auditor
          diagnosed «data-op fantasma» and its repair was a GENERIC `claude_code` worker.
  387.8s  that worker reached its first `youtube:search` — **195 seconds** after it started.

Two more from the same six minutes, same shape: a «Sí.» to our own offer was annulled as «un
fragmento, no un encargo» while the brief had answered `request_type=answer` at 1.00; and a
commission for ten restaurants was annulled as `handled_inline / worker-running` because an
UNRELATED worker was alive — nobody ever searched for a restaurant.

The class, in one line: **the engine asks Jev the right questions and then lets a regex or a second
model overrule the answer.**

Static and unit, deliberately. Proving any of this against a live turn needs a model, a network and
an operator talking — the condition nobody can reproduce on demand, which is exactly why the defects
survived six months of guards. What CAN be pinned is that each decision READS the verdict, and that
is the whole of what changed.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import threading

import pytest

from nucleo.flash import canvas_license as _lic
from nucleo.flash import direct_action as _da
from nucleo.flash import escalation_guard as _eg
from nucleo.flash import turn_brief as _tb

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_PROVIDER = _ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"

#: His actual sentence, from the transcript. Kept verbatim: a paraphrase would be a test of a test.
HIS_WORDS = "Muy bien. ¿Me podrías preparar un catálogo de vídeos sobre el Apollo once?"


def _brief(choice: str, *, key=None, confidence: float = 0.97, open_ids=("youtube",)):
    """A brief handle in the REAL shape `jev.ask_many` returns — an Event, a result dict, the stamp.

    Built rather than mocked, because the thing under test is `turn_brief.read`'s own path through
    it: a hand-rolled double with a convenient shape would pass with the reader disconnected.
    """
    k = key or _tb.TARGET_KEY
    ev = threading.Event()
    ev.set()                    # `jev.peek` returns None on an unset event: an unset one tests nothing
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": choice, "confidence": confidence}}}


# ── the rung itself ──────────────────────────────────────────────────────────────────────────────

def test_the_payload_key_comes_from_the_manifest_and_not_from_a_list_of_ours():
    """`youtube:search` declares `query` (required) and `n` («opcional»). Exactly one is fillable.

    The rule has to be read from the widget or it is a table that rots the first time a manifest
    changes — the failure `cases_data` was caught with 26 days late (V2-739).
    """
    assert _da.fillable_key("youtube", "search") == "query"


def test_an_action_whose_keys_are_ALL_optional_is_not_fillable_from_a_sentence():
    """`youtube:load` takes url / videoId / query / title, every one of them «(opcional)».

    Zero required keys is not «fill the first one»: the action wants an empty payload or the model's
    own arguments, and guessing which of four to stuff a sentence into is the invention this refuses.
    """
    from widgets import runtime
    payload = ((runtime.get("youtube") or {}).get("actions") or {}).get("load", {}).get("payload") or {}
    assert len(payload) > 1, "the premise moved: youtube:load no longer has several optional keys"
    assert _da.fillable_key("youtube", "load") == ""


def test_TWO_required_keys_is_a_question_to_ASK_and_never_a_call_to_make():
    """The other side of «exactly one». An action that needs a second datum we do not have is
    V2-712's ASK_FACT, not a guess — and guessing there is how an errand acquires a wrong argument
    nobody typed."""
    import types
    fake = {"two": {"payload": {"a": "first thing", "b": "second thing"}}}
    real = _da.__dict__.get("_base_of")
    import nucleo.flash.frontend as fe
    saved = fe.declared_actions
    fe.declared_actions = lambda wid: fake if wid == "youtube" else saved(wid)
    try:
        assert _da.fillable_key("youtube", "two") == ""
    finally:
        fe.declared_actions = saved
    assert real is _da.__dict__.get("_base_of")   # the shim touched nothing else


def test_an_action_that_names_an_EXISTING_row_is_never_filled_with_a_sentence():
    """A selector asks «which of the rows you can see»; a sentence is not one of them.

    Same trap `turn_brief._possible_now` documents one layer over, and the same resolver
    (`refs.id_field_for_action`) is what tells them apart — asked once, not re-derived here.
    """
    from widgets import refs
    for action in ("play_item", "play_result", "remove"):
        field = refs.id_field_for_action("youtube", action)
        if field:
            assert _da.fillable_key("youtube", action) != field, (
                f"youtube:{action} would be filled with a sentence on the key that names a row")


def test_the_rung_takes_the_action_the_VERDICT_names():
    got = _da.resolve("Prepara un catálogo de vídeos del Apollo 11",
                      brief=_brief("youtube:search"), operator_text=HIS_WORDS)
    assert got.get("widget") == "youtube" and got.get("action") == "search", got
    assert got["payload"]["query"] == HIS_WORDS, "the payload must carry HIS words, not ours"


def test_the_MODELS_own_arguments_win_over_the_operators_sentence():
    """When a guard swallowed a real tool call, its arguments are the best source there is: the model
    had just read the whole turn and produced «Apollo 11 documentales», not a 12-word sentence."""
    got = _da.resolve("cualquier cosa", brief=_brief("youtube:search"),
                      swallowed={"query": "Apollo 11 documentales"}, operator_text=HIS_WORDS)
    assert got["payload"] == {"query": "Apollo 11 documentales"}
    assert got["source"] == "swallowed-tool"


def test_a_LONG_errand_is_not_a_query_and_the_rung_declines_it():
    """The bound is the honest part. A rambling errand IS worker work; pretending a paragraph is a
    search query would make this rung worse than the worker it replaces."""
    long = " ".join(["palabra"] * (_da.MAX_QUERY_WORDS + 1))
    assert _da.resolve(long, brief=_brief("youtube:search"), operator_text=long) == {}


def test_a_verdict_about_a_CLOSED_card_is_no_verdict():
    """The brief enumerates the screen at fire time and is read 2-4 s later (`owner_still_open`)."""
    handle = _brief("musica:search", open_ids=("youtube",))     # the verdict names a card not in the set
    assert _da.from_brief(handle) == ("", "")


def test_NO_BRIEF_asks_nothing_and_therefore_emits_nothing():
    """A read-attribution event per call is how V2-726 A6a says whether a verdict was used. With no
    brief there is no verdict to attribute, and emitting anyway put a `jev read screen_action → off`
    line on every video turn of a channel that fires no brief — noise in the one place that has to
    stay readable. Caught by the flow test that counts a turn's events by kind, not by this file."""
    seen: list = []
    import voice.observer as _obs
    saved = _obs.emit
    _obs.emit = lambda *a, **k: seen.append(a)
    try:
        assert _da.from_brief(None) == ("", "")
        assert _da.endorses(None, "youtube") is False
        assert _lic.video_license("qué bien", "", brief=None) is False
    finally:
        _obs.emit = saved
    assert not seen, f"a turn with no brief emitted {seen}"


def test_no_verdict_means_no_rung_and_therefore_todays_path():
    assert _da.resolve("lo que sea", brief=None, operator_text="hola") == {}
    assert _da.resolve("lo que sea", brief=_brief("none"), operator_text="hola") == {}


def test_an_unsure_verdict_does_not_spend_the_rung():
    """Under `jev.MIN_CONFIDENCE` the reader returns the caller's fallback, which here is «nothing»."""
    from nucleo import jev
    handle = _brief("youtube:search", confidence=max(0.0, jev.MIN_CONFIDENCE - 0.2))
    assert _da.resolve("x", brief=handle, operator_text=HIS_WORDS) == {}


def test_taking_the_rung_CLEARS_the_commission_and_fires_the_action():
    """The point is not that it decides — it is that the worker no longer happens."""
    seen: dict = {}
    req = {"v": "Prepara un catálogo de vídeos del Apollo 11", "more": ["otra"]}
    ok = _da.take_rung(
        req, brief=_brief("youtube:search"), operator_text=HIS_WORDS,
        emit=lambda *a, **k: seen.setdefault("emitted", (a, k)),
        present=lambda *a, **k: seen.setdefault("shown", a[0]),
        apply_widget_data=lambda w, a, p: seen.setdefault("fired", (w, a, p)))
    assert ok is True
    assert seen["fired"][:2] == ("youtube", "search")
    assert seen["shown"] == "youtube"
    assert req["v"] is None and req["more"] == [], "the commission must not ALSO go to a worker"


def test_the_rung_never_raises_into_the_turn():
    """Fail-soft is the contract of everything in this circuit: a classifier may not break a turn."""
    req = {"v": "algo", "more": []}
    def boom(*_a, **_k):
        raise RuntimeError("the rails are down")
    assert _da.take_rung(req, brief=_brief("youtube:search"), operator_text=HIS_WORDS,
                         emit=boom, present=boom, apply_widget_data=boom) is False
    assert req["v"] == "algo", "a failed rung must leave the commission where it was"


# ── E2 · the verdict overrules the grammar, never the other way round ────────────────────────────

def test_HIS_ACTUAL_SENTENCE_is_refused_by_the_verb_table():
    """The measurement this whole batch rests on. If this ever goes green on its own, the table was
    quietly extended and the test below stops proving anything — so it is asserted, not assumed."""
    assert _lic.video_license(HIS_WORDS, "") is False, (
        "the grammar table now accepts this sentence; the override test below is no longer a test")


def test_the_same_sentence_is_LICENSED_once_the_verdict_is_handed_over():
    assert _lic.video_license(HIS_WORDS, "", brief=_brief("youtube:search")) is True


def test_the_override_only_ever_GRANTS():
    """It may add a permitted call and may never remove one: with no verdict, the grammar decides
    exactly as it did before, in both directions."""
    assert _lic.video_license("ponme el vídeo del Apolo 11", "", brief=None) is True
    assert _lic.video_license("ponme el vídeo del Apolo 11", "", brief=_brief("none")) is True
    assert _lic.video_license("qué bien, gracias", "", brief=None) is False


def test_a_verdict_about_ANOTHER_card_does_not_license_the_player():
    """`musica:search` is not a licence to load a video: the override is bound to the card."""
    assert _lic.video_license(HIS_WORDS, "", brief=_brief("musica:search",
                                                          open_ids=("musica",))) is False


# ── E3 · a running worker is not evidence that THIS was handled ─────────────────────────────────

RESTAURANTS = "Busca y elabora una lista de diez restaurantes cerca de la Torre del Oro en Sevilla"


def test_an_UNRELATED_worker_no_longer_annuls_a_commission(monkeypatch):
    """The ten restaurants, exactly as they died: `handle_inline`, nothing acted, an Apollo worker
    alive. The old spelling annulled on `anything_running` alone."""
    monkeypatch.setattr(_eg, "covered_by_live_work", lambda *a, **k: False)
    v = _eg.annulment_verdict("handle_inline", reply="", acted=False,
                              anything_running=True, commission=RESTAURANTS)
    assert v["annul"] is False and v["disposition"] == _eg.UNRESOLVED


def test_a_worker_running_THIS_VERY_commission_still_annuls_it(monkeypatch):
    """The other half — without it this would just be «never annul», which re-opens the duplicate
    workers V2-507's dedup exists to stop."""
    monkeypatch.setattr(_eg, "covered_by_live_work", lambda *a, **k: True)
    v = _eg.annulment_verdict("handle_inline", reply="", acted=False,
                              anything_running=True, commission=RESTAURANTS)
    assert v["annul"] is True and v["why"] == "covered-by-live-work"


def test_nothing_running_is_answered_without_asking_the_dedup(monkeypatch):
    def never(*_a, **_k):
        raise AssertionError("the dedup was scanned with no live errand to scan against")
    monkeypatch.setattr("nucleo.dispatch.dedup_scan", never)
    assert _eg.covered_by_live_work(RESTAURANTS, anything_running=False) is False


def test_the_coverage_question_is_asked_of_the_DEDUP_and_not_re_derived():
    """V2-252's rule: a second copy of a similarity yardstick drifts, and then two gates disagree
    about whether two sentences are the same errand."""
    src = inspect.getsource(_eg.covered_by_live_work)
    assert "dedup_scan(" in src, "the coverage check no longer goes through the dispatch dedup"
    assert '"web"' in src, (
        "the dedup is asked with a kind that unlocks the target-widget shortcut: two different "
        "errands about the same card would read as one")


# ── E4 · a «Sí» to our own offer is an answer, not a fragment ───────────────────────────────────

def test_a_bare_YES_is_still_a_fragment_with_no_brief_to_read():
    assert _eg.is_a_fragment("Sí.") is True


def test_a_bare_YES_survives_when_the_verdict_says_it_ANSWERS_US():
    handle = _brief("answer", key=_tb.REQUEST_KEY, confidence=1.0)
    assert _eg.is_a_fragment("Sí.", brief=handle,
                             last_reply="¿Quieres que me ocupe del correo de AliExpress?") is False


def test_BOTH_halves_are_required():
    """The verdict says it is an answer; `answered_an_offer` says there was a question. A «sí» is an
    answer only where there was a question — the pairing `offer_of_media` already documents."""
    handle = _brief("answer", key=_tb.REQUEST_KEY, confidence=1.0)
    assert _eg.is_a_fragment("Sí.", brief=handle, last_reply="Vale, lo dejo.") is True
    order = _brief("order", key=_tb.REQUEST_KEY, confidence=1.0)
    assert _eg.is_a_fragment("Sí.", brief=order, last_reply="¿Lo hago?") is True


def test_a_real_errand_is_never_called_a_fragment():
    assert _eg.is_a_fragment(RESTAURANTS) is False


def test_dropping_a_fragment_says_so_and_leaves_a_real_one_alone():
    said: list = []
    req = {"v": "inventado", "more": ["x"]}
    assert _eg.drop_if_fragment(req, operator_text="Sí.", emit=lambda *a, **k: said.append(a)) is True
    assert req["v"] is None and req["more"] == [] and said, "an annulment that is silent is the defect"
    keep = {"v": RESTAURANTS, "more": []}
    assert _eg.drop_if_fragment(keep, operator_text=RESTAURANTS, emit=lambda *a, **k: None) is False
    assert keep["v"] == RESTAURANTS


# ── WIRING · the provider must actually reach all of this ───────────────────────────────────────

def _provider_src() -> str:
    return _PROVIDER.read_text(encoding="utf-8")


def test_the_provider_tries_the_rung_BEFORE_the_escalate_gate():
    """Order is the whole point: after the gate, the commission has already been settled and the
    worker is on its way. A rung that runs late is a rung that never runs."""
    code = "\n".join(l.split("#", 1)[0] for l in _provider_src().splitlines())
    rung = code.index("_direct_action.take_rung(")
    gate = code.index("_eguard.settle_commission(")
    assert rung < gate, "the declared-action rung is tried AFTER the commission has been settled"


def _if_guarding(call_name: str) -> ast.If:
    """The `if` statement whose body actually reaches `call_name`, read from the AST.

    Read structurally rather than by slicing text, because a text slice cannot tell a live guard
    from a dead one — `if False and take_rung(...)` keeps every word a substring check looks for,
    and a disarm proved exactly that while this file was being written.
    """
    tree = ast.parse(_provider_src())
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call)
                    and getattr(inner.func, "attr", "") == call_name):
                return node
    raise AssertionError(f"the provider never calls {call_name}")


def test_the_rung_only_fires_where_the_alternative_costs_minutes():
    """Its precondition is not decoration: firing it over a turn that already produced a result
    would re-run an action the operator has already seen happen."""
    guard = _if_guarding("take_rung")
    test_src = ast.dump(guard.test)
    assert "Constant(value=False)" not in test_src, (
        "the rung is behind a constant-false guard: it is wired and unreachable")
    src = _provider_src()
    window = src[src.index("# V2-741 · THE THIRD RUNG"):src.index("_direct_action.take_rung(")]
    for needed in ('escalate_req["v"] is not None', 'not acted["widget"]', 'not data_done["v"]'):
        assert needed in window, f"the rung lost its precondition: {needed}"


def test_the_provider_hands_the_brief_to_the_video_license():
    """Without this argument the override is unreachable and every test above is theatre."""
    src = _provider_src()
    call = src[src.index("_video_turn.voice_execute("):][:300]
    assert "brief=_brief" in call, "the video branch no longer receives the turn's brief"


def test_the_fragment_guard_receives_the_brief_too():
    src = _provider_src()
    call = src[src.index("_eguard.drop_if_fragment("):][:300]
    assert "brief=_brief" in call and "last_reply=" in call


def test_the_settlement_is_told_WHICH_commission_it_is_settling():
    src = _provider_src()
    call = src[src.index("_eguard.settle_commission("):][:400]
    assert "commission=" in call or "escalate_req" in call
    assert "commission=" in inspect.getsource(_eg.settle_commission), (
        "the settlement no longer passes the commission down, so coverage is back to «any worker»")


def test_no_new_blocking_jev_call_was_added_by_any_of_this():
    """The V2-726 F2 invariant, checked where this batch could have broken it: `choose_sync` freezes
    the thread on urlopen and the voice path runs on the loop STT, TTS and barge-in share."""
    for mod in (_da, _lic, _eg):
        tree = ast.parse(pathlib.Path(inspect.getfile(mod)).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in ("choose_sync", "classify_sync") and mod is not _eg:
                pytest.fail(f"{mod.__name__} added a blocking Jev call at line {node.lineno}")


# ── E5 · the memory diagnostic names the cause it actually found ────────────────────────────────

def test_the_degraded_recall_line_compares_the_signatures_instead_of_printing_both():
    """Live it printed «(cloud:text-embedding-3-small:768) does not match the indexed one
    (cloud:text-embedding-3-small:768)» — the same string twice — while the real cause was an
    embedder with no credits. A diagnostic that accuses the wrong file spends the reader's trust."""
    src = inspect.getsource(pathlib.Path(_ENGINE / "memory" / "retriever.py").read_text) if False else \
        (_ENGINE / "memory" / "retriever.py").read_text(encoding="utf-8")
    block = src[src.index("def _warn_wrong_space") if "def _warn_wrong_space" in src else 0:]
    block = block[:block.index("espacio vectorial descuadrado") + 200]
    assert "active == stored" in block, (
        "the two embedding signatures are still printed side by side instead of compared")
    assert "EMBEDDER" in block, "the embedder-down cause is not named"



def test_a_commission_naming_a_CLOSED_card_of_ours_is_read_before_the_worker(monkeypatch):
    """V2-773 final pass (C1): the two rungs above only see a card the brief names through `screen_action`,
    which exists only for OPEN cards; with the agenda closed the catalogue verdict named it (0.79) and the
    commission still went to a worker. The third branch asks the card-or-worker pass (`card_commission`) and
    turns a read into the turn's own `read_req`, which the read path below then serves."""
    src = _provider_src()
    window = src[src.index("# V2-741 · THE THIRD RUNG"):src.index("_eguard.settle_commission(")]
    assert "_cardc.before_worker(escalate_req, read_req" in window
    # …and every `if` on the way to that call is LIVE: `if False and await …` keeps every word above.
    tree = ast.parse(src)
    guards = [n for n in ast.walk(tree) if isinstance(n, ast.If)
              and any(isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "before_worker" for c in ast.walk(n))]
    assert guards and all("Constant(value=False)" not in ast.dump(g.test) for g in guards), "a dead guard reaches the rung"
    assert src.index("_cardc.before_worker(") < src.index('if read_req["v"] is not None and escalate_req["v"] is None'), (
        "the read path must run AFTER the rung fills read_req")
    import asyncio
    from nucleo import danger
    from nucleo.flash import act_repair, build_decision, card_commission, widget_read
    monkeypatch.setattr(build_decision, "named_card", lambda brief: "agenda")
    monkeypatch.setattr(widget_read, "can_answer", lambda wid: wid == "agenda")
    monkeypatch.setattr(danger, "is_dangerous", lambda text: "delete everything" in text)
    answer = {"kind": "read", "widget_id": "agenda", "question": "free between 12:00 and 18:00 on 2026-09-27?"}

    async def pass_(operator_text, commission, wid, spec=None):
        return answer
    monkeypatch.setattr(act_repair, "call_or_read_for_commission", pass_)
    seen, applied = [], []
    kw = dict(brief={"x": 1}, operator_text="Find me a free 45-minute slot tomorrow afternoon", spec=None,
              emit=lambda *a, **k: seen.append(a), present=lambda *a, **k: True,
              apply_widget_data=lambda w, a, p: applied.append((w, a, p)))
    esc, rd = {"v": "find a slot", "more": ["x"]}, {"v": None}
    assert asyncio.run(card_commission.before_worker(esc, rd, **kw)) == "read"
    assert rd["v"] == {"widget_id": "agenda", "question": answer["question"]} and esc["v"] is None and esc["more"] == []
    answer = {"kind": "call", "widget_id": "agenda", "action": "add_meeting", "payload": {"title": "x"}}
    esc, rd = {"v": "put it in", "more": []}, {"v": None}
    assert asyncio.run(card_commission.before_worker(esc, rd, **kw)) == "call"
    assert applied == [("agenda", "add_meeting", {"title": "x"})] and esc["v"] is None
    answer = None
    esc = {"v": "book a table", "more": []}
    assert asyncio.run(card_commission.before_worker(esc, {"v": None}, **kw)) == "" and esc["v"] == "book a table", (
        "nothing called → the worker keeps the errand")
    answer = {"kind": "read", "widget_id": "agenda", "question": "?"}
    esc = {"v": "delete everything", "more": []}
    assert asyncio.run(card_commission.before_worker(esc, {"v": None}, **dict(kw, operator_text="delete everything"))) == ""
    assert esc["v"] == "delete everything", "an irreversible order never takes this shortcut"


def test_a_read_the_verdict_says_to_SHOW_brings_the_card(monkeypatch):
    """V2-773 final pass (C2): «Show me that time in my calendar» was answered by a read, in words, with the
    agenda closed — the verdict had said canvas=show (0.74). The card he asked to see comes up."""
    src = _provider_src()
    i = src.index('if read_req["v"] is not None and escalate_req["v"] is None')
    assert "_cardc.present_if_show(read_req" in src[i:i + 1200]
    from nucleo.flash import card_commission, turn_brief, widget_read
    monkeypatch.setattr(widget_read, "resolve", lambda arg, text="": "agenda" if "agenda" in (arg + text) else None)
    verb = ["show"]
    monkeypatch.setattr(turn_brief, "read", lambda brief, key, fb, **k: (verb[0], {"used": True}))
    shown = []
    kw = dict(brief={"x": 1}, operator_text="Show me that time in my calendar", emit=lambda *a, **k: None,
              present=lambda wid, **k: shown.append((wid, k.get("reason"))) or True)
    assert card_commission.present_if_show({"v": {"widget_id": "agenda"}}, is_open=lambda w: False, **kw)
    assert shown == [("agenda", "turn-order")]
    assert not card_commission.present_if_show({"v": {"widget_id": "agenda"}}, is_open=lambda w: True, **kw), "open: nothing to do"
    verb[0] = "neither"
    assert not card_commission.present_if_show({"v": {"widget_id": "agenda"}}, is_open=lambda w: False, **kw), (
        "a question with no show in it stays a read")
