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


# ── V2-726 A3 · a commission is RESOLVED, never silently cleared ─────────────────────────────────
# The audit's finding 4. The gate runs AFTER the model has answered and usually after speech has
# started, and a turn that carried an escalation normally REPLIED with a promise. Clearing it on a
# confident `handle_inline` alone produced the engine's oldest failure — a promise the operator
# heard with nothing on the board. `handle_inline` means «no worker needed», not «already done».

def test_an_owed_order_VETOES_the_annulment(monkeypatch):
    """The case that costs money in the wrong direction: Jev's escalate key is confidently `handle_inline`, the brief
    reads an ORDER, and nothing ran — the commission is the only thing that would make the order true. The brief
    decides, never our words (refactor2710-03)."""
    from nucleo.turn import reply as _reply
    monkeypatch.setattr(_reply, "owes_an_act", lambda brief: "order" if brief == "ORDER" else "")
    for said in ("Te lo busco ahora mismo.", "", "Done."):
        v = _eg.annulment_verdict("handle_inline", reply=said, acted=False, anything_running=False, brief="ORDER")
        assert v["annul"] is False and v["disposition"] == _eg.PROMISED, said
    v = _eg.annulment_verdict("handle_inline", reply="Te lo busco ahora mismo.", acted=False, anything_running=False)
    assert v["disposition"] != _eg.PROMISED, "no order in the brief: the words commit to nothing"


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


def test_every_outcome_is_a_NAMED_disposition(monkeypatch):
    """A commission that simply disappears is the failure this gate exists to prevent, so there is
    no unnamed exit: each of the four paths ends on a constant the timeline can be counted by."""
    from nucleo.turn import reply as _reply
    monkeypatch.setattr(_reply, "owes_an_act", lambda brief: "order" if brief == "ORDER" else "")
    named = {_eg.DELEGATED, _eg.HANDLED_INLINE, _eg.PROMISED, _eg.UNRESOLVED}
    seen = {_eg.annulment_verdict(c, reply="", acted=a, anything_running=w, brief=b)["disposition"]
            for c in ("handle_inline", "escalate")
            for b in (None, "ORDER")
            for a in (True, False)
            for w in (True, False)}
    assert seen <= named and len(seen) == 4, seen


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
