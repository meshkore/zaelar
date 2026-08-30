"""ONE yardstick for «are these two texts the same errand?» — F4 of the 2026-08-23 architecture audit.

The audit's finding H3, measured live on 2026-08-21: TWO similarity judges lived in this tree and CONTRADICTED
each other about the same pair of texts. `dispatch.find_duplicate` (Jaccard >= 0.60) said «different errands»
and spawned three workers; `navegador/tasks._similar` (>= 2 shared stems OR Jaccard >= 0.40) said «same browsing
session» and handed all three ONE tab — 46, 27 and 7 interleaved actions, `click [29]` landing on a page another
worker had just changed. The real texts' Jaccard (0.333-0.375) sat exactly in the gap between the two bars.

The fix is not picking a winner between the two thresholds — each is defensible for its own question. It is that
the PRIMITIVE lives once (`nucleo/matching.py`) and both judges import it, and that the dispatcher's question
(«same errand across REFORMULATIONS?») gets the metric that actually answers it: containment, not Jaccard.
Measured populations (harness, full sweep): same errand reformulated 0.571-0.893, different errands 0.062-0.227
— disjoint under containment, inseparable under Jaccard.
"""
import inspect

from nucleo import dispatch, matching
from nucleo.workers.session import SessionRecord

# Real goals from the operator's own engine (memory/_data/zaelar.db, 2026-08-17): the car search that spawned
# SIX workers. The long form is what escalate.requested carried; the short form is the kind of reformulation
# the brain emits on re-escalation.
LONG = ("Busca coches de segunda mano en España que cumplan: que no sean muy viejos (idealmente a partir de "
        "2018-2019 en adelante), motor diésel, y precio máximo de 12.000 euros")
SHORT = "busca coches diésel de segunda mano por menos de 12.000 euros"
OTHER = "búscame un piso de alquiler en Madrid en idealista por menos de 900 euros"


# ── the primitive ────────────────────────────────────────────────────────────────────────────────────────────

def test_containment_separates_where_jaccard_cannot():
    """The whole reason the metric changed: a longer rewording looks *different by being longer* under Jaccard
    (it divides by the union), while containment asks the actual question — is the short one inside the long
    one? Both numbers below are printed into the assertion so a future recalibration sees what moved."""
    a, b = matching.content_words(LONG), matching.content_words(SHORT)
    j, c = matching.jaccard(a, b), matching.containment(a, b)
    assert j < 0.60, f"jaccard {j:.3f} — if this now clears the old bar, the fixture stopped reproducing the bug"
    assert c >= matching.SAME_ERRAND, f"containment {c:.3f} must clear SAME_ERRAND for a real reformulation"


def test_different_errands_stay_apart():
    a, c = matching.content_words(LONG), matching.content_words(OTHER)
    assert matching.containment(a, c) < matching.SAME_ERRAND


def test_the_threshold_sits_in_the_measured_gap():
    """0.227 is the worst different-errand pair measured; 0.571 the weakest same-errand pair. A threshold
    outside that gap is not a tuning choice — it is one of the two failure modes coming back."""
    assert 0.227 < matching.SAME_ERRAND < 0.571


def test_empty_sets_never_match():
    assert matching.containment(set(), {"algo"}) == 0.0
    assert matching.jaccard(set(), set()) == 0.0


# ── the dispatcher's judge, end to end ───────────────────────────────────────────────────────────────────────

def _live(tid: str, goal: str):
    rec = SessionRecord(task_id=tid, goal=goal.strip()[:200], kind="web")   # [:200] exactly as run_listener does
    rec.status = "running"
    dispatch._SESSIONS[tid] = rec
    return rec


def test_a_reformulated_errand_now_finds_its_live_twin(monkeypatch):
    """The Thursday class of bug (hotel Sevilla, J=0.679 real vs truncated): a short re-escalation of a live
    long errand must dedup. Under Jaccard 0.60 this exact pair did NOT match and both workers ran."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    _live("live", LONG)
    assert dispatch.find_duplicate(SHORT, "web") == "live"


def test_a_genuinely_different_errand_still_spawns(monkeypatch):
    """The counterweight, without which «fixing dedup» is indistinguishable from loosening it: over-merging
    swallows a new task into an old session (the V2-123 flow-fusion class), worse than a duplicate worker."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    _live("live", LONG)
    assert dispatch.find_duplicate(OTHER, "web") is None


def test_truncation_of_the_stored_goal_is_harmless_now():
    """The 200-char truncation bug dissolves under containment BY CONSTRUCTION: the truncated side is the min
    the ratio divides by. Proven with a stored goal cut mid-sentence."""
    full = LONG + " y que tenga menos de 100.000 kilómetros y cambio manual y aire acondicionado"
    stored = matching.content_words(full[:200])
    incoming = matching.content_words(full)
    assert matching.containment(incoming, stored) > 0.9, "truncating the stored goal must barely move containment"


# ── the wiring — one yardstick, two judges, zero private copies ──────────────────────────────────────────────

def test_both_judges_import_the_shared_primitive():
    """The class guard. Two copies of a decision drift apart silently, and the alarm arrives as three workers
    driving one tab. If either judge grows its own set-arithmetic again, this goes red."""
    # V2-507 moved the loop into `nucleo/dedup.py::scan` (the verdict now travels with the evidence it
    # decided on) and left `find_duplicate` a wrapper. The guard has to follow the RULE, not the name:
    # pointed at the wrapper it would keep passing while the arithmetic drifted a module away — a guard that
    # guards nothing, which is worse than no guard because it reads like coverage.
    from nucleo import dedup as _dedup
    src_dispatch = inspect.getsource(_dedup.scan)
    assert "matching.containment" in src_dispatch
    assert "len(req_w | o)" not in src_dispatch, "dedup.scan grew a private union-division again"
    assert "dedup_scan(" in inspect.getsource(dispatch.find_duplicate), (
        "find_duplicate must keep delegating: a second copy of the rule is how the two judges drifted apart")

    from widgets.navegador import tasks
    src_similar = inspect.getsource(tasks._similar)
    assert "matching.jaccard" in src_similar
    assert "/ union" not in src_similar, "_similar grew a private union-division again"


def test_the_tokenizer_is_the_shared_one():
    assert dispatch._content_words("guitarra zurdo, clásica") == matching.content_words("(guitarra) zurdo clasica")
