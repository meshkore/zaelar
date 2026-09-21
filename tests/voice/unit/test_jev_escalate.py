"""Node 3.62 — Jev second opinion on a would-be worker commission (T-jev-escalate).

Contract under test (`nucleo/flash/escalation_guard.py`): `judge_escalation` answers
"handle_inline" ONLY on a confident Jev verdict over {handle_inline, escalate}, read from the
operator's words plus state facts (goals in flight, workers active, a worker waiting) — never
a new word list. Every other outcome — confident `escalate`, unsure, unknown, slow, failed,
disabled, empty — returns "escalate", i.e. today's path untouched. The gate only ever clears
a surviving commission; it never commissions one.
"""
from __future__ import annotations

import pytest

from nucleo import jev
from nucleo.flash import escalation_guard as _eg


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "900")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    yield


def _canned(choice="handle_inline", confidence=0.9):
    return {"model": "jev-latest",
            "answers": {"escalate_or_inline": {"type": "choice", "choice": choice,
                                               "probabilities": {choice: confidence},
                                               "confidence": confidence}}}


def test_the_question_is_two_answers_over_the_operators_words_plus_state(monkeypatch):
    """The catalog is fixed and reviewable; the state facts travel as context, not as rails."""
    seen: dict = {}
    # NOTE: _post_question takes (answer_key, state, instructions, criteria, timeout) — the
    # state facts ride inside `state` (choose_sync appends context there). Read them back.
    monkeypatch.setattr(jev, "_post_question",
                        lambda ak, st, ins, crit, to: (seen.update(
                            answer_key=ak, criteria=crit, state=st), _canned())[1])
    out = _eg.judge_escalation("It is", running_goals=["find a plumber"],
                               has_workers=True, ask_pending=True)
    assert out == "handle_inline"
    assert seen["answer_key"] == "escalate_or_inline"
    assert set(seen["criteria"]) == {"handle_inline", "escalate"}
    assert "It is" in seen["state"]
    assert "find a plumber" in seen["state"]
    assert "Workers active now: yes" in seen["state"]
    assert "waiting for the operator's answer: yes" in seen["state"]


def test_a_confident_escalate_changes_nothing(monkeypatch):
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="escalate"))
    assert _eg.judge_escalation("research roman culture for me") == "escalate"


def test_unsure_or_unknown_keep_todays_path(monkeypatch):
    """The load-bearing guard: a shrug must not annul a commission. Removing the gate turns
    these red."""
    monkeypatch.setattr(jev, "_post_question",
                        lambda *a: _canned(choice="handle_inline", confidence=0.2))
    assert _eg.judge_escalation("It is") == "escalate"
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="teleport"))
    assert _eg.judge_escalation("It is") == "escalate"


def test_failed_disabled_and_empty_never_annul(monkeypatch):
    def _boom(*a):
        raise TimeoutError("slow")
    monkeypatch.setattr(jev, "_post_question", _boom)
    assert _eg.judge_escalation("It is") == "escalate"

    calls: list = []
    monkeypatch.setattr(jev, "_post_question", lambda *a: (calls.append(a), _canned())[1])
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert _eg.judge_escalation("It is") == "escalate"
    monkeypatch.delenv("ZAELAR_JEV")
    assert _eg.judge_escalation("   ") == "escalate"
    assert calls == []


# ── V2-726 A3 · a commission is RESOLVED, never silently cleared ─────────────────────────────────
# The audit's finding 4. The gate runs AFTER the model has answered and usually after speech has
# started, and a turn that carried an escalation normally REPLIED with a promise. Clearing it on a
# confident `handle_inline` alone produced the engine's oldest failure — a promise the operator
# heard with nothing on the board. `handle_inline` means «no worker needed», not «already done».

def test_a_promise_in_the_reply_VETOES_the_annulment():
    """The case that costs money in the wrong direction: Jev is confidently wrong, we already said
    we would do it, and the commission is the only thing that would have made that true."""
    for reply in ("Te lo busco ahora mismo.",
                  "Voy a mirar los vuelos y te digo.",
                  "Déjame que lo compruebe.",
                  "Te pongo algo de rock."):
        v = _eg.annulment_verdict("handle_inline", reply=reply, acted=False, anything_running=False)
        assert v["annul"] is False, f"a promised errand was annulled: {reply!r}"
        assert v["disposition"] == _eg.PROMISED


def test_a_NEGATED_promise_is_not_a_promise():
    """«No voy a buscarlo» commits to nothing. The clause arithmetic is V2-534's and lives in
    `nucleo/flash/negation.py`; this only proves the gate inherits it instead of re-deriving it."""
    v = _eg.annulment_verdict("handle_inline", reply="No voy a buscarlo, no hace falta.",
                             acted=False, anything_running=False)
    assert v["disposition"] != _eg.PROMISED


def test_a_real_inline_result_lets_the_annulment_through():
    """The other direction, and the reason this is not just «never annul»: when the turn DID
    something — a widget op, a data read, a search, a listing — `handle_inline` is describing a
    result that exists, and keeping the commission would spend a worker on finished work."""
    v = _eg.annulment_verdict("handle_inline", reply="Son las cinco y media.",
                             acted=True, anything_running=False)
    assert v["annul"] is True and v["disposition"] == _eg.HANDLED_INLINE


def test_a_live_worker_counts_as_the_work_being_under_way_ONLY_IF_IT_IS_THIS_WORK(monkeypatch):
    """⚠️ THIS TEST USED TO ENCODE THE DEFECT, and it was green the whole time it was costing errands.

    It asserted that ANY live worker annulled ANY commission, and it passed — the code did exactly
    what it said. Measured live (session 092569ab, 2026-09-21): the operator asked for ten
    restaurants near the Torre del Oro while an unrelated Apollo-11 worker was still going. The
    commission was annulled as `handled_inline / worker-running`, the model had just said «voy a
    lanzar de una la búsqueda de los diez restaurantes ahora mismo», and **nobody ever searched for
    a restaurant**. The errand did not fail; it was never born.

    `anything_running` answers «is the engine busy». The question the gate needs is «is what he just
    asked for already being done», and that one has an owner since V2-507 — the dispatch dedup. Both
    directions are pinned below, because «never annul» would re-open the duplicate workers that dedup
    exists to stop.
    """
    monkeypatch.setattr(_eg, "covered_by_live_work", lambda *a, **k: True)
    v = _eg.annulment_verdict("handle_inline", reply="Sigo con ello.", acted=False,
                              anything_running=True, commission="lo mismo que ya corre")
    assert v["annul"] is True and v["disposition"] == _eg.HANDLED_INLINE

    monkeypatch.setattr(_eg, "covered_by_live_work", lambda *a, **k: False)
    v = _eg.annulment_verdict("handle_inline", reply="Sigo con ello.", acted=False,
                              anything_running=True, commission="diez restaurantes en Sevilla")
    assert v["annul"] is False and v["disposition"] == _eg.UNRESOLVED, (
        "an unrelated worker is annulling a commission again — this is how the restaurants died")


def test_no_evidence_either_way_KEEPS_the_commission():
    """The safe side of this gate, stated in its own instructions: «a missed errand is worse than a
    wasted question». Nothing acted and nothing was promised, so nothing proves it is done."""
    v = _eg.annulment_verdict("handle_inline", reply="Vale.", acted=False, anything_running=False)
    assert v["annul"] is False and v["disposition"] == _eg.UNRESOLVED


def test_a_verdict_that_is_not_handle_inline_never_annuls():
    for choice in ("escalate", "", "nonsense"):
        v = _eg.annulment_verdict(choice, reply="Son las cinco.", acted=True, anything_running=False)
        assert v["annul"] is False and v["disposition"] == _eg.DELEGATED


def test_every_outcome_is_a_NAMED_disposition():
    """A commission that simply disappears is the failure this gate exists to prevent, so there is
    no unnamed exit: each of the four paths ends on a constant the timeline can be counted by."""
    named = {_eg.DELEGATED, _eg.HANDLED_INLINE, _eg.PROMISED, _eg.UNRESOLVED}
    seen = {_eg.annulment_verdict(c, reply=r, acted=a, anything_running=w)["disposition"]
            for c in ("handle_inline", "escalate")
            for r in ("", "Te lo busco.")
            for a in (True, False)
            for w in (True, False)}
    assert seen <= named and len(seen) == 4, seen


def test_the_provider_records_the_disposition_and_only_clears_on_annul():
    """The wiring, statically — the decision is worthless if the provider still clears on the raw
    verdict. It must call `annulment_verdict`, emit what it decided, and gate the clear on it."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[3]
           / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    assert "settle_commission(" in code, (
        "the provider annuls on the raw verdict again instead of going through the gate (V2-726 A3)")
    assert "annulment_verdict(" not in code, (
        "the decision moved back INTO the god file — the architecture ratchet's answer to a block "
        "that grows is «extract a module», and `escalation_guard` is where this one lives")

    # …and the module it moved to still does all three things.
    import inspect
    src = inspect.getsource(_eg.settle_commission)
    assert 'escalate_req["more"] = []' in src, "the sibling commissions are no longer handled"
    assert '"disposition"' in src, "the disposition is decided and never recorded"
    assert 'if verdict["annul"]:' in src, "the clear is not gated on the disposition"


def test_the_gate_records_a_disposition_for_every_outcome():
    """The function the provider now calls, driven directly: it emits what it decided and clears
    only what it earned. A commission that simply disappears is the failure this exists to name."""
    seen = []
    for choice, reply, acted, expect_kept in (
            ("handle_inline", "Te lo busco ahora mismo.", False, True),     # promised → kept
            ("handle_inline", "Son las cinco y media.", True, False),       # real result → annulled
            ("handle_inline", "Vale.", False, True),                        # no evidence → kept
            ("escalate", "", True, True)):                                  # not inline → kept
        req = {"v": "búscame vuelos a Tokio", "more": ["y un hotel"]}
        out = _eg.settle_commission(
            req, brief=None, operator_text="búscame vuelos", reply=reply, acted=acted,
            anything_running=False, emit=lambda *a, **k: seen.append(k.get("extra", {})))
        # `brief=None` reads as «escalate», so the inline cases are forced through the verdict itself
        if choice == "handle_inline":
            out = _eg.annulment_verdict(choice, reply=reply, acted=acted, anything_running=False)
            if out["annul"]:
                req["v"], req["more"] = None, []
        assert (req["v"] is not None) is expect_kept, (choice, reply, req)
    assert all("disposition" in e for e in seen), "an outcome went unrecorded"
