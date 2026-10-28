"""nucleo/jev — Jev (TypeSafe System One) Choice client: the ONLY place that talks to Jev.

The cost is the ROUND TRIP, not the questions (2026-09-20: p50 800 ms; 1 question 800 ms, 10 take 817 ms, 100 take
1 041 ms): a turn asks every question it needs in ONE call — the turn's brief (`nucleo/turn/brief.py` → `ask_many`),
`select_many` (`nucleo/jev/select.py`) or the bounded decision (`nucleo/jev/decision.py`) — never a loop over the
single-question door. The timeout is 2 s (F5): the brief is read 2-4 s after it is fired.

Protocol (https://docs.typesafe.ai, 2026-09-20): POST /v1/systemone, Bearer key, JSON {state, model: "jev-latest",
questions: {<key>: {type: "choice", instructions, criteria}}} → {answers: {<key>: {choice, probabilities, confidence}}}.
Key resolution (names only): TYPESAFE_API_KEY from the environment, else `.meshkore/credentials/jev.md` (gitignored).

Jev is advisory: a slow, failed or unsure call leaves the caller's own fallback untouched. ⚠️ `choose_sync()` blocks
its thread for up to the timeout — never call it from the voice path's event loop (`test_no_new_blocking_jev_call` keeps
that count at zero): ask the question in the turn brief and `peek`/`read` it. Every completed call emits one `brain`
event (`jev <question-id>`) with the verdict, its distribution and its milliseconds; every READ emits `jev read`.
"""
from __future__ import annotations

import itertools
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

_PROC_TAG = f"{int(time.time()) % 100000:05d}"

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

# The request types Jev chooses between. Small on purpose: one Choice question, each option a shape
# the filler pools already know how to cover (see KIND_MAP). Greeting stays in the list so a phatic
# turn is never misread as a question — the smalltalk lane owns the reply, the filler only the cover.
REQUEST_TYPES: dict[str, str] = {
    "question": "The user asks for information, an explanation, or an answer",
    "order": "The user wants something DONE: an action, a change on screen, a booking, a message sent",
    "comment": "The user shares information or chats, without asking for anything or ordering anything",
    "greeting": "Phatic contact only: hello, goodbye, thanks, small talk with no request inside",
    "answer": "The user answers a question WE just asked: a short reply that asks nothing itself",
    "complaint": "The user talks about US or the conversation: corrections, complaints, presence checks",
}

# Jev verdict -> filler pool. Reuses the four pools `langs.pick_filler()` already ships, so no new
# catalog of phrases: question keeps the thinking pool, order the motion pool, answer the receipt
# pool, and everything phatic or meta the explanation-opener pool.
KIND_MAP: dict[str, str] = {
    "question": "neutral",
    "order": "action",
    "answer": "ack",
    "greeting": "social",
    "comment": "social",
    "complaint": "social",
}

MIN_CONFIDENCE = 0.5  # below this the verdict is a shrug: keep the regex class, log the doubt

_CALL_SEQ = itertools.count(1)


def new_call_id() -> str:
    """A short id for ONE round trip, so the ASK and every READ of it can be joined.

    V2-726's audit could only attribute two events in a real session to the same turn by their
    timestamps — «temporal, not a durable join», which is not evidence. Monotonic per process and
    prefixed with the process start, because two engines write into the same timeline."""
    return f"{_PROC_TAG}-{next(_CALL_SEQ)}"


def _engine_root() -> Path:
    return Path(__file__).resolve().parents[2]      # nucleo/jev/__init__.py → the engine root


_KEY_CACHE: dict = {"env": None, "value": ""}


def _read_key() -> str:
    """TYPESAFE_API_KEY from the environment (covers zaelar.env), else the bare key file.

    The FILE read is cached (V2-726 F5). `enabled()` calls this on every single Jev touch and
    `_post_*` calls it again to build the header, so on a machine where the key lives in
    `credentials/jev.md` rather than the environment — which is this one — every verdict was
    opening and parsing a file twice, on the voice turn's thread. The cache is keyed on the env var
    so exporting it still takes effect immediately, and a key ROTATED in the file is picked up by
    the restart that any credential change already needs.
    """
    env = (os.getenv("TYPESAFE_API_KEY") or "").strip()
    if env:
        return env
    if _KEY_CACHE["env"] == "" and _KEY_CACHE["value"]:
        return _KEY_CACHE["value"]
    try:
        for line in (_engine_root() / ".meshkore" / "credentials" / "jev.md").read_text(
            encoding="utf-8"
        ).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line and not line.startswith("apikey_"):
                _, _, line = line.partition("=")
            if line.strip():
                _KEY_CACHE["env"], _KEY_CACHE["value"] = "", line.strip()
                return _KEY_CACHE["value"]
    except Exception:
        pass
    return ""


def _timeout_s() -> float:
    """3.5 s since the demo pass of 2026-09-28 (full24 A2): with the brief fired at t0 and read by `peek` 2-4 s later,
    a 2 s wall threw away answers that would have landed in time — both hedged calls ran out at 2010 ms, every read
    after it saw «absent», and «put that away» was answered «tucked away» with nothing tucked. 2 s since V2-726 F5,
    up from 900 ms.

    900 against a measured p50 of 800 was the engine cancelling its own calls at the edge: 5% of the
    canvas verdicts and **28% of the escalate gate's** crossed it and were dropped AFTER being paid
    for. That timeout only made sense while a caller blocked on the answer; since F1 the brief is
    fired at t0 and read by `peek` 2-4 s later, so a slow call costs a daemon thread and nothing
    else — and the turn that would have thrown the verdict away now uses it."""
    try:
        return max(0.1, int(os.getenv("ZAELAR_JEV_TIMEOUT_MS", "3500")) / 1000.0)
    except Exception:
        return 3.5


# ── circuit breaker (V2-726 F5): after `_BREAK_AFTER` failures in a row, no dialling for `_BREAK_FOR_S`; the first call
# after it is a probe and one success closes it. An open breaker reads exactly like a slow call — today's path.
_BREAK_AFTER = 3
_BREAK_FOR_S = 60.0
_breaker: dict = {"fails": 0, "open_until": 0.0}


def _breaker_open(now: float | None = None) -> bool:
    return (time.monotonic() if now is None else now) < _breaker["open_until"]


def _note_failure() -> None:
    _breaker["fails"] += 1
    if _breaker["fails"] >= _BREAK_AFTER:
        _breaker["open_until"] = time.monotonic() + _BREAK_FOR_S


def _note_success() -> None:
    _breaker["fails"] = 0
    _breaker["open_until"] = 0.0


def reset_breaker() -> None:
    """Tests and the `/debug` surface: forget the outage."""
    _note_success()


def enabled() -> bool:
    """False silences the whole module: no thread, no HTTP, callers keep their local verdict."""
    if (os.getenv("ZAELAR_JEV", "") or "").strip().lower() in ("0", "off", "no", "false"):
        return False
    if _breaker_open() or not __import__("nucleo.energy.lease", fromlist=["check"]).check("decision"):
        return False                      # provider down, or no energy lease: no thread, no socket, today's path
    return bool(_read_key())


_RT_INSTRUCTIONS = "What kind of turn is the user's message"


def _post_question(answer_key: str, state: str, instructions: str, criteria: dict,
                   timeout_s: float) -> dict:
    """One blocking Jev call for an arbitrary Choice question. `_post` below is its
    request-type specialization — the seam the committed filler test fakes."""
    body = json.dumps(
        {
            "state": state,
            "model": MODEL,
            "questions": {
                answer_key: {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
        }
    ).encode("utf-8")
    payload = _trip(body, timeout_s)
    _meter(1)
    return payload


def _trip(body: bytes, timeout_s: float) -> dict:
    """One Jev trip; `llm_egress.route_url` decides where (the provider directly, or mediated egress)."""
    from nucleo.energy import egress as llm_egress
    return llm_egress.post_json(*llm_egress.route_url(ENDPOINT, _read_key()), body, timeout_s)


def _meter(questions: int) -> None:
    """Report the round trip to Energy. Jev is a PAID provider — roughly 1.4 trips per voice
    turn. Reported after the answer, like every other call site: a trip that never came back is
    not a billed trip. Never raises: metering must not be able to break a verdict."""
    try:
        from nucleo.energy import meter as energy_meter
        energy_meter.report_decision_usage(provider="typesafe", questions=questions)
    except Exception:
        pass


def _post(state: str, timeout_s: float) -> dict:
    """One blocking request-type call — the exact seam the committed filler test fakes.
    Thin specialization of `_post_question`; signature frozen at two positional args."""
    return _post_question("request_type", state, _RT_INSTRUCTIONS, REQUEST_TYPES, timeout_s)


def _parse(payload: dict, *, answer_key: str = "request_type",
           allowed: dict | None = None) -> tuple[str, float, dict]:
    allowed = REQUEST_TYPES if allowed is None else allowed
    ans = (payload.get("answers") or {}).get(answer_key) or {}
    choice = str(ans.get("choice") or "")
    try:
        confidence = float(ans.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    probs = ans.get("probabilities") or {}
    if choice not in allowed:
        choice = ""
    return choice, confidence, dict(probs)


def _emit(text: str, *, choice: str, confidence: float, probs: dict,
          latency_ms: int, error: str = "", question_id: str = "request-type",
          pool: str = "", per_question: dict | None = None, call_id: str = "") -> None:
    try:
        from voice.observer import emit
        extra = {"cat": "flash", "choice": choice, "confidence": round(confidence, 3),
                 "probabilities": probs, "latency_ms": latency_ms,
                 "pool": pool or KIND_MAP.get(choice, ""), "error": error[:80]}
        if per_question:
            extra["per_question"] = per_question
        if call_id:
            extra["call_id"] = call_id
        emit(
            "brain", f"jev {question_id}",
            text=f"{text[:100]} -> {choice or 'none'} ({confidence:.2f}, {latency_ms} ms)"
            + (f" [error: {error[:80]}]" if error else ""),
            role="system",
            extra=extra,
        )
    except Exception:
        pass


# ── MANY questions, ONE trip (V2-726 F1). Bounded HERE, where the only wire call lives: a caller that enumerates a
# whole database gets an error (`JevBriefTooBig`), never a silently truncated verdict set.
MAX_QUESTIONS = 120           # 100 candidates measured fine; the margin is for the turn's own keys
MAX_STATE_CHARS = 60_000      # ~15k tokens of state; past this the caller is asking the wrong way


class JevBriefTooBig(ValueError):
    """Raised by `choose_many_sync` when a caller exceeds the bounds above — never on the wire."""


def _post_many(state: str, questions: dict, timeout_s: float) -> dict:
    """One blocking call carrying N Choice questions. The multi-question sibling of `_post_question`,
    kept separate so the single-question seam the committed filler test fakes stays frozen."""
    body = json.dumps(
        {"state": state, "model": MODEL,
         "questions": {k: {"type": "choice", "instructions": q["instructions"],
                           "criteria": q["criteria"]} for k, q in questions.items()}}
    ).encode("utf-8")
    payload = _trip(body, timeout_s)
    # ONE trip, whatever the number of questions — that is what is billed and the reason this
    # function exists (`nucleo/jev.py` module note: «the cost is the ROUND TRIP, not the questions»).
    _meter(len(questions or {}))
    return payload


def _hedge_after_s() -> float:
    """When to send a second, identical brief if the first has not answered (0 = never).

    Demo pass 2026-09-28 (full18): the provider's p50 was 317 ms and p90 450 ms, and 6 briefs in 78 hit the 2 s
    wall — each one a turn read with no verdict at all (C5b «tidy up the screen» and E4 «leave that inworld one
    as unread» both went wrong that way). Passes 16-17 had none. A tail that rare and that long is what a hedged
    request is for: one more trip for the few slow ones, the first answer wins."""
    try:
        return max(0.0, int(os.getenv("ZAELAR_JEV_HEDGE_MS", "900")) / 1000.0)
    except Exception:
        return 0.9


_HEDGE_POOL = None


def _post_many_hedged(state: str, questions: dict, timeout_s: float) -> dict:
    """`_post_many`, with a second identical call if the first is still out after `_hedge_after_s()`. Whichever
    answers first is returned; the deadline stays `timeout_s` from the first send. Both failing raises the first
    call's error, exactly as a single call would."""
    global _HEDGE_POOL
    hedge = _hedge_after_s()
    if hedge <= 0 or hedge >= timeout_s:
        return _post_many(state, questions, timeout_s)
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
    if _HEDGE_POOL is None:
        _HEDGE_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="jev-hedge")
    t0 = time.monotonic()
    calls = [_HEDGE_POOL.submit(_post_many, state, questions, timeout_s)]
    done, _ = wait(calls, timeout=hedge)
    if not done:
        calls.append(_HEDGE_POOL.submit(_post_many, state, questions, max(0.1, timeout_s - hedge)))
    first_error = None
    pending = set(calls)
    while pending:
        left = timeout_s - (time.monotonic() - t0)
        if left <= 0:
            break
        done, pending = wait(pending, timeout=left, return_when=FIRST_COMPLETED)
        for f in done:
            if f.exception() is None:
                return f.result()
            first_error = first_error or f.exception()
    raise first_error or TimeoutError("The read operation timed out")


def choose_many_sync(state: str, questions: dict, *, timeout_s: float | None = None,
                     question_id: str = "brief") -> dict | None:
    """Blocking verdicts for N enumerated questions in ONE trip.

    `questions` is `{key: {"instructions": str, "criteria": {option: description}}}`. Returns
    `{key: {"choice", "confidence", "probs"}}` plus `"_latency_ms"`, or None when disabled or on
    any failure — the caller then keeps whatever it had, exactly as with a single question.

    The confidence gate lives with the caller (`read`), never here: an unsure verdict is returned
    so the caller can log the doubt instead of silently inheriting a shrug.
    """
    state = (state or "").strip()
    if not state or not questions or not enabled():
        return None
    if len(questions) > MAX_QUESTIONS:
        raise JevBriefTooBig(f"{len(questions)} questions > MAX_QUESTIONS ({MAX_QUESTIONS})")
    if len(state) > MAX_STATE_CHARS:
        raise JevBriefTooBig(f"state is {len(state)} chars > MAX_STATE_CHARS ({MAX_STATE_CHARS})")
    call_id = new_call_id()
    t0 = time.monotonic()
    try:
        payload = _post_many_hedged(state, questions, _timeout_s() if timeout_s is None else timeout_s)
    except Exception as e:  # noqa: BLE001 — no caller may ever break on a classifier
        _emit(state, choice="", confidence=0.0, probs={},
              latency_ms=int((time.monotonic() - t0) * 1000),
              error=f"{type(e).__name__}: {e}", question_id=question_id, call_id=call_id)
        _note_failure()
        return None
    _note_success()
    latency_ms = int((time.monotonic() - t0) * 1000)
    out: dict = {"_latency_ms": latency_ms, "_call_id": call_id, "_ready_at": time.time()}
    for key, q in questions.items():
        choice, confidence, probs = _parse(payload, answer_key=key, allowed=q["criteria"])
        out[key] = {"choice": choice, "confidence": confidence, "probs": probs}
    # ONE event for the whole brief: N events for one trip would read like N trips in the timeline,
    # which is exactly the fact this design exists to change.
    #
    # ⚠️ The `confidence` field used to be `max()` over the questions, and V2-726's audit found that
    # it cannot answer the only question the event exists for: whether an individual consumer's
    # verdict crossed ITS threshold. One sure canvas verb hid three unsure ones behind a 0.99. The
    # maximum stays in the headline number (the event schema has one), but every question's own
    # confidence now travels in `extra.per_question`, which is what a report reads.
    _emit(state, choice=",".join(f"{k}={out[k]['choice'] or '-'}" for k in questions),
          confidence=max((out[k]["confidence"] for k in questions), default=0.0),
          probs={k: out[k]["probs"] for k in questions}, latency_ms=latency_ms,
          question_id=f"{question_id} ({len(questions)}q)",
          per_question={k: {"choice": out[k]["choice"],
                            "confidence": round(out[k]["confidence"], 3)} for k in questions},
          call_id=out["_call_id"])
    return out


def ask_many(state: str, questions: dict, *, name: str = "jev-brief",
             question_id: str = "brief") -> dict | None:
    """Fire-and-forget multi-question brief for the hot path. Same handle shape `peek` reads."""
    if not (state or "").strip() or not questions or not enabled():
        return None
    return ask_async(state, name=name,
                     run=lambda: choose_many_sync(state, questions, question_id=question_id))


def read(handle: dict | None, key: str, fallback, *, min_confidence: float = MIN_CONFIDENCE):
    """One verdict out of a brief: the choice when it is READY and SURE, else `fallback`.

    Never waits — a brief still in flight, failed, disabled, or missing this key reads as the
    fallback, which is today's path. Returns `(choice, info)`; `info["used"]` says which it was,
    so the observability trail can attribute a misfire to the reader rather than to the model.

    AND IT SAYS SO OUT LOUD (V2-726 A6a). `info["used"]` existed and every consumer in the engine
    threw it away, so the timeline recorded that Jev was ASKED and never whether the answer was
    used — the one fact needed to say whether any of this is worth its round trip. One bounded
    event per (call_id, key), with WHY: used · unsure · absent · in_flight · off.
    """
    verdict = peek(handle)
    if not verdict or key not in verdict:
        why = "in_flight" if (handle and not _is_ready(handle)) else ("absent" if handle else "off")
        _emit_read(handle, key, used=False, why=why, confidence=0.0, choice="")
        return fallback, None
    ans = verdict[key] or {}
    if not ans.get("choice"):
        _emit_read(handle, key, used=False, why="no_choice", confidence=0.0, choice="")
        return fallback, ans
    if ans.get("confidence", 0.0) < min_confidence:
        _emit_read(handle, key, used=False, why="unsure",
                   confidence=ans.get("confidence", 0.0), choice=ans["choice"])
        return fallback, {**ans, "used": False}
    _emit_read(handle, key, used=True, why="used",
               confidence=ans.get("confidence", 0.0), choice=ans["choice"])
    return ans["choice"], {**ans, "used": True}


def _is_ready(handle) -> bool:
    try:
        return bool(handle["event"].is_set())
    except Exception:  # noqa: BLE001
        return False


_READ_SEEN: set = set()          # (call_id, key) — one event per verdict per reader, never a loop
_READ_SEEN_MAX = 512


def _emit_read(handle, key: str, *, used: bool, why: str, confidence: float, choice: str) -> None:
    """One bounded event per verdict READ. Bounded twice: deduped on (call_id, key), and the set of
    seen pairs is capped — a reader in a loop must not be able to fill the operator's timeline."""
    try:
        call_id = (handle or {}).get("_call_id") or ""
        if not call_id:
            v = peek(handle) or {}
            call_id = v.get("_call_id") or ""
        turn_id = (handle or {}).get("turn_id") or ""
        seen_key = (call_id, key)
        if call_id:
            if seen_key in _READ_SEEN:
                return
            if len(_READ_SEEN) >= _READ_SEEN_MAX:
                _READ_SEEN.clear()
            _READ_SEEN.add(seen_key)
        from voice.observer import emit
        emit("brain", f"jev read {key}",
             text=f"{choice or '-'} -> {'USED' if used else why} ({confidence:.2f})",
             role="system",
             extra={"cat": "flash", "call_id": call_id, "turn_id": turn_id, "question": key,
                    "used": bool(used), "why": why, "confidence": round(confidence, 3),
                    "choice": choice})
    except Exception:  # noqa: BLE001 — observability may never break a turn
        pass


def reset_read_events() -> None:
    """Tests: forget which verdicts have already been reported."""
    _READ_SEEN.clear()


def choose_sync(answer_key: str, text: str, *, instructions: str, criteria: dict,
                allowed: dict | None = None, context: str = "",
                timeout_s: float | None = None,
                question_id: str = "") -> dict | None:
    """Blocking Choice verdict for an arbitrary per-call enumerated question.

    Returns {"choice", "confidence", "probs", "latency_ms"}, or None when disabled or on any
    failure. The confidence gate lives with the CALLER (resolve_choice): an unsure verdict is
    returned, not hidden, so the caller can log the doubt and keep its local verdict."""
    text = (text or "").strip()
    if not text or not enabled():
        return None
    state = text
    if (context or "").strip():
        state += f"\n{context.strip()[:200]}"
    t0 = time.monotonic()
    try:
        # The request-type question keeps going through `_post` with exactly two positional
        # args — that is the seam the committed filler test fakes. Any other Choice question
        # goes through the generic wire call, which newer tests fake instead.
        timeout = _timeout_s() if timeout_s is None else timeout_s
        if answer_key == "request_type":
            payload = _post(state, timeout)
        else:
            payload = _post_question(answer_key, state, instructions, criteria, timeout)
        choice, confidence, probs = _parse(
            payload, answer_key=answer_key, allowed=criteria if allowed is None else allowed)
    except Exception as e:  # noqa: BLE001 — no caller may ever break on a classifier
        _emit(text, choice="", confidence=0.0, probs={},
              latency_ms=int((time.monotonic() - t0) * 1000), error=f"{type(e).__name__}: {e}",
              question_id=question_id or answer_key)
        _note_failure()
        return None
    _note_success()
    latency_ms = int((time.monotonic() - t0) * 1000)
    _emit(text, choice=choice, confidence=confidence, probs=probs, latency_ms=latency_ms,
          question_id=question_id or answer_key)
    return {"choice": choice, "confidence": confidence, "probs": probs,
            "latency_ms": latency_ms}


def ask_async(text: str, *, run, name: str = "jev") -> dict | None:
    """Fire-and-forget Choice verdict for the hot path. `run` is a zero-arg callable returning a
    verdict dict or None (typically a `choose_sync` partial); the handle shape is the same one
    `peek` reads. None when there is nothing to wait for — the caller keeps its local verdict."""
    text = (text or "").strip()
    if not text or not enabled():
        return None
    handle: dict = {"event": threading.Event(), "result": None}

    def _run() -> None:
        try:
            handle["result"] = run()
        except Exception:
            handle["result"] = None
        handle["event"].set()

    threading.Thread(target=_run, name=name, daemon=True).start()
    return handle


def resolve_choice(handle: dict | None, fallback, *, min_confidence: float = MIN_CONFIDENCE):
    """Fire-time decision over a generic Choice handle: Jev's choice when it is ready AND sure,
    else the fallback. Same gate shape as `resolve_kind`, over {"choice", ...} verdicts."""
    verdict = peek(handle)
    if not verdict or not verdict.get("choice"):
        return fallback, verdict
    if verdict.get("confidence", 0.0) < min_confidence:
        return fallback, {**verdict, "used": False}
    return verdict["choice"], {**verdict, "used": True}


def peek(handle: dict | None) -> dict | None:
    """Non-blocking read: the verdict dict, or None when still flying, failed, or never asked."""
    if not handle or not handle["event"].is_set():
        return None
    return handle["result"]


def resolve_kind(handle: dict | None, fallback: str) -> tuple[str, dict | None]:
    """Fire-time decision: Jev's pool when it is ready AND sure, else the regex fallback.

    The confidence gate is the load-bearing guard: an unsure verdict must not move the cover —
    a wrong pool is exactly the incoherence this module exists to remove."""
    verdict = peek(handle)
    if not verdict or not verdict.get("type") or not verdict.get("kind"):
        return fallback, verdict
    if verdict.get("confidence", 0.0) < MIN_CONFIDENCE:
        return fallback, {**verdict, "used": False}
    return verdict["kind"], {**verdict, "used": True}


# ── refactor2710-07: the selection and the bounded decision live beside the client; their names stay here ──────
from nucleo.jev.select import (  # noqa: E402,F401
    DISABLED, EMPTY, FIT, NO_MATCH, SELECTED, UNAVAILABLE, select_many, select_many_status)
from nucleo.jev.decision import ABSTAINED, DECISION_STATUSES, EXPIRED, TOO_BIG, Decision, decide  # noqa: E402,F401
