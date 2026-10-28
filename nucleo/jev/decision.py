"""The BOUNDED-DECISION contract (V2-726 A1): one door, `decide`, with outcomes that can be told apart. Moved out of
`nucleo/jev.py` (refactor2710-07); calls the client through the package, so a patch on `nucleo.jev` governs it."""
from __future__ import annotations

import threading
import time

from nucleo import jev as _j
from nucleo.jev.select import DISABLED, EMPTY, NO_MATCH, SELECTED, UNAVAILABLE

# Candidates come from the DOMAIN (manifests, indexed rows, the workflow registry, real agent cards) and the mechanism
# validates membership and effects afterwards — no second model client, no router in front. The statuses are the point:
# `selected`/`no_match`/`abstained` are ANSWERS to act on; the rest are ABSENCES to route around.
#: Every way a bounded decision can end. `selected`/`no_match`/`abstained` are answers; the rest are
#: absences. A caller that cannot tell them apart will eventually claim one for the other.
ABSTAINED, EXPIRED, TOO_BIG = "abstained", "expired", "too_big"
DECISION_STATUSES = (SELECTED, NO_MATCH, ABSTAINED, UNAVAILABLE, DISABLED, EMPTY, EXPIRED, TOO_BIG)

#: Concurrency for BACKGROUND callers (workers, memory, recall). The voice brief does not take it:
#: it is one call per turn on a deadline, and making it queue behind a worker's hundred-candidate
#: sweep would be the one way this module could make a turn slower.
_BG_LIMIT = 4
_bg_sem = threading.BoundedSemaphore(_BG_LIMIT)


class Decision(dict):
    """The result of ONE bounded decision. A dict so it crosses the worker bridge as JSON unchanged.

        {status, chosen: [id, …], confidence: {id: float}, latency_ms, call_id, provenance}

    `chosen` is empty for every status but `selected`. `status` is never inferred from that
    emptiness — that conflation is the defect this type exists to remove.
    """

    @property
    def ok(self) -> bool:
        return self["status"] == SELECTED


def _decision(status: str, *, chosen=None, confidence=None, latency_ms: int = 0,
              call_id: str = "", provenance: str = "") -> Decision:
    return Decision({"status": status, "chosen": list(chosen or []),
                     "confidence": dict(confidence or {}), "latency_ms": latency_ms,
                     "call_id": call_id, "provenance": provenance or _j.MODEL})


def decide(purpose: str, evidence: str, candidates: dict, *, abstain: bool = True,
           source: str = "", turn_id: str = "", task_id: str = "", state_rev: str = "",
           deadline_s: float | None = None, effect_class: str = "view",
           min_confidence: float = _j.MIN_CONFIDENCE, background: bool = True) -> Decision:
    """Choose among DECLARED candidates, with an outcome the caller can act on.

    `candidates` is `{id: description}` — built by the domain, never by this module. `purpose` is
    one line of what is being decided; `evidence` is the state text the decision is made against.
    `abstain=True` adds a `none` option, which is how a decision says «none of these» rather than
    being forced to pick the least bad one.

    `effect_class` is carried for the record, NOT enforced here: nothing this function returns
    executes anything. The caller maps `chosen` onto a path that is already gated — that is rule 3
    of the initiative and it does not move for a nicer API.

    Bounded: `_j.MAX_QUESTIONS` candidates, `_j.MAX_STATE_CHARS` of evidence, and background callers share
    `_BG_LIMIT` slots so a worker sweeping a hundred rows cannot starve anything. `deadline_s`
    counts from entry INCLUDING the wait for a slot — a decision that arrives after its deadline is
    `expired`, not late.
    """
    t0 = time.monotonic()
    cands = {str(k): str(v) for k, v in (candidates or {}).items() if str(k).strip()}
    if not cands or not (purpose or "").strip():
        return _decision(EMPTY)
    if len(cands) > _j.MAX_QUESTIONS:
        return _decision(TOO_BIG)
    state = f"{purpose.strip()}\n{(evidence or '').strip()}"[:_j.MAX_STATE_CHARS + 1]
    if len(state) > _j.MAX_STATE_CHARS:
        return _decision(TOO_BIG)
    if not _j.enabled():
        return _decision(DISABLED)

    criteria = dict(cands)
    if abstain:
        criteria["none"] = "none of these fits what is being decided"
    question = {"decision": {"instructions": _decide_instructions(purpose, source, state_rev),
                             "criteria": criteria}}

    acquired = False
    if background:
        wait = 1.0 if deadline_s is None else max(0.0, deadline_s - (time.monotonic() - t0))
        acquired = _bg_sem.acquire(timeout=wait)
        if not acquired:
            return _decision(EXPIRED, latency_ms=int((time.monotonic() - t0) * 1000))
    try:
        if deadline_s is not None and (time.monotonic() - t0) >= deadline_s:
            return _decision(EXPIRED, latency_ms=int((time.monotonic() - t0) * 1000))
        left = None if deadline_s is None else max(0.1, deadline_s - (time.monotonic() - t0))
        verdicts = _j.choose_many_sync(state, question, timeout_s=left, question_id="decide")
    finally:
        if acquired:
            _bg_sem.release()

    latency_ms = int((time.monotonic() - t0) * 1000)
    if not verdicts:
        return _decision(UNAVAILABLE, latency_ms=latency_ms)
    call_id = verdicts.get("_call_id", "")
    v = verdicts.get("decision") or {}
    choice, conf = str(v.get("choice") or ""), float(v.get("confidence") or 0.0)
    if not choice or choice not in criteria:
        return _decision(NO_MATCH, latency_ms=latency_ms, call_id=call_id)
    if choice == "none":
        return _decision(ABSTAINED, latency_ms=latency_ms, call_id=call_id,
                         confidence={"none": conf})
    if conf < min_confidence:
        return _decision(ABSTAINED, latency_ms=latency_ms, call_id=call_id,
                         confidence={choice: conf})
    return _decision(SELECTED, chosen=[choice], confidence={choice: conf},
                     latency_ms=latency_ms, call_id=call_id)


def _decide_instructions(purpose: str, source: str, state_rev: str) -> str:
    """The question's own instructions. The candidate ids are the options; the purpose is what the
    decision is FOR. `source`/`state_rev` ride along so a verdict in the timeline can be traced to
    who asked and against which revision of the state — the audit could do neither."""
    bits = [purpose.strip()]
    if source:
        bits.append(f"[asked by {source}]")
    if state_rev:
        bits.append(f"[state rev {state_rev}]")
    return " ".join(bits)
