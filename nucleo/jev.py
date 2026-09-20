"""nucleo/jev.py — Jev (TypeSafe System One) Choice client, the single integration point.

The voice filler has ~1.1 s (ZAELAR_FILLER_MS) between the arm (model start) and the moment a cover
may sound. The regex classifier in `voice/engine/speech/filler_audio.py` answers instantly but only
knows shapes it was taught; Jev names the class with a calibrated verdict, so it can answer before
the deadline instead of after the release. This module is the ONLY place that talks to Jev — the
filler is its first caller, later ones reuse it.

MEASURED LATENCY (2026-09-20, V2-726 — this docstring previously claimed «70-500 ms», which no call
has ever taken): p50 **800 ms**, p95 910 ms, over 312 real calls in the operator's sessions plus a
live round against the API. The timeout is 2 s since F5: with the brief fired at turn start and read
2-4 s later, a slow call costs a daemon thread and nothing else — at 900 ms the engine was cancelling
5% of its canvas calls and 28% of its escalate-gate ones AFTER paying for them.

AND THE FACT THAT SHOULD SHAPE EVERY NEW CALLER: the cost is the ROUND TRIP, not the questions. The
`questions` field is a MAP — 1 question takes 800 ms, 10 take 817 ms, 100 take 1041 ms. Anything
that needs several verdicts in one turn must ask them in ONE call, not N. `choose_many_sync` /
`ask_many` (F1) and `select_many` (F4) are that call; a new caller uses one of them, never a loop
over the single-question door.

Protocol (verified against https://docs.typesafe.ai, 2026-09-20):
  POST https://api.typesafe.ai/v1/systemone, Bearer key, JSON {state, model: "jev-latest",
  questions: {request_type: {type: "choice", instructions, criteria}}}.
Answer: {answers: {request_type: {choice, probabilities, confidence}}}, no generated text.

Key resolution (names only, never values): TYPESAFE_API_KEY from the environment — which also covers
`zaelar.env`, since `server/common.py` loads that store into the environment at startup — else the
bare key in `.meshkore/credentials/jev.md` (gitignored, read here so it is never duplicated).

Non-blocking WHEN ASKED ASYNC: `ask_async()` fires a daemon thread at arm time and returns a
handle; `resolve_choice()` peeks at fire time without ever waiting. Jev is advisory — a slow, failed
or unsure call leaves the local verdict untouched, so no caller ever depends on the network.

⚠️ `choose_sync()` is NOT that, and it is not safe from a coroutine: `urllib.request.urlopen` blocks
the calling thread for up to the timeout, freezing the event loop STT, TTS and barge-in all share.
Two callers used to do exactly that from inside the voice provider's `async def _run_inner`
(`escalation_guard.judge_escalation` and `frontend.repair_action`); F2 replaced both with brief
readers, and `test_no_new_blocking_jev_call.py` is the ratchet that keeps the count at zero. The two
blocking functions remain for the probe/text channel, which has no event loop to freeze. Do NOT add
a `choose_sync` caller on the voice path: ask the question in the turn brief and `peek` the answer.

The request-type classifier (`classify_sync` / `request_async` / `resolve_kind`) is the first
caller, kept as a thin wrapper over the generic Choice primitive below.

Observability: every completed call emits one `brain` event (`jev <question-id>`) with the
utterance, the verdict, the confidence distribution and the milliseconds it took, so the timeline
shows when Jev was asked, how long it took and what it answered.
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
    return Path(__file__).resolve().parents[1]


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
    """2 s since V2-726 F5, up from 900 ms.

    900 against a measured p50 of 800 was the engine cancelling its own calls at the edge: 5% of the
    canvas verdicts and **28% of the escalate gate's** crossed it and were dropped AFTER being paid
    for. That timeout only made sense while a caller blocked on the answer; since F1 the brief is
    fired at t0 and read by `peek` 2-4 s later, so a slow call costs a daemon thread and nothing
    else — and the turn that would have thrown the verdict away now uses it."""
    try:
        return max(0.1, int(os.getenv("ZAELAR_JEV_TIMEOUT_MS", "2000")) / 1000.0)
    except Exception:
        return 2.0


# ── circuit breaker (V2-726 F5) ──────────────────────────────────────────────────────────────────
# A provider outage used to cost a thread and a full timeout on EVERY turn, for a verdict that was
# never going to arrive — and with the timeout now at 2 s that is 2 s of daemon thread per turn,
# forever, while the operator keeps talking. After `_BREAK_AFTER` consecutive failures the module
# stops dialling for `_BREAK_FOR_S`; the first call after that window is a probe, and one success
# closes it. Advisory all the way down: an open breaker reads exactly like a slow call — today's path.
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
    if _breaker_open():
        return False                      # the provider is down: no thread, no socket, today's path
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
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": f"Bearer {_read_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


# ── MANY questions, ONE trip (V2-726 F1) ────────────────────────────────────────────────────────────
# The API's `questions` field is a MAP, and measured 2026-09-20 the cost is the ROUND TRIP, not the
# questions: 1 question 800 ms, 4 heterogeneous 708-826 ms, 10 identical 817 ms, 100 candidates
# 1041 ms. Everything a turn needs to ask therefore belongs in ONE call — the engine was making two.
#
# Bounded on purpose. A malformed caller that enumerates a whole database would turn one cheap
# classifier into a slow expensive one, and the failure mode would be a silently truncated verdict
# set rather than an error. So both limits are checked HERE, where the only wire call lives.
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
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": f"Bearer {_read_key()}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        payload = _post_many(state, questions, _timeout_s() if timeout_s is None else timeout_s)
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


# ── SELECTION over parsed data (V2-726 F4) ──────────────────────────────────────────────────────
# The operator's case: «si le mandamos a Jev los datos parseados de los 100 resultados y la lista de
# criterios, nos puede decir cuáles son los que mejor encajan, en una sola request». Measured
# 2026-09-20 against 100 synthetic listings: ONE trip, 1041 ms, $0,0005, and it found all three rows
# that met every criterion (recall 3/3). The three false positives all came back under 0.33
# confidence while the three hits sat at 0.64-0.94, so the gate separates them cleanly.
#
# ⚠️ THE TRAP, and it cost a measurement to find: the candidate's identity must travel INSIDE its own
# question, not only in the shared `state`. Ten identical questions over a shared state answered
# `strong` to all ten — including a 125cc Vespa in a search for motocross bikes — at 0.82-0.89
# confidence. Confidently wrong, which is the worst failure this module has. `select_many` below
# therefore builds each question around its own candidate, and no caller can get that wrong.
FIT = {
    "strong": "meets every criterion",
    "partial": "meets some criteria but fails at least one",
    "no": "fails the core criteria",
}


def select_many(candidates, criteria: str, *, key=None, label=None,
                timeout_s: float | None = None, min_confidence: float = MIN_CONFIDENCE) -> list:
    """Score N candidates against `criteria` in ONE trip. Off the voice path by design.

    `candidates` is any sequence; `label(c)` renders one as text (default `str`) and `key(c)` names
    it in the result (default its index). Returns the ones that fit, best first:

        [{"key", "candidate", "fit", "confidence"}]

    Only `strong` verdicts at or above `min_confidence` are returned — «partial» is a shrug and an
    unsure «strong» is the false-positive band the measurement found. Returns [] when disabled, on
    any failure, or when nothing fits: the caller keeps whatever it would have done, as everywhere
    else in this module. Raises `JevBriefTooBig` past `MAX_QUESTIONS` rather than truncating, so a
    caller with a thousand rows pages them instead of silently scoring the first hundred.
    """
    return select_many_status(candidates, criteria, key=key, label=label, timeout_s=timeout_s,
                              min_confidence=min_confidence)[0]


#: What a selection round can END as. `[]` said all five of these at once, and the caller could not
#: tell «nothing fits» (a real answer, act on it) from «the service was not there» (no answer, ask).
#: V2-726 A6a gives them names; A1 generalises them to every bounded decision in the engine.
SELECTED, NO_MATCH, UNAVAILABLE, DISABLED, EMPTY = (
    "selected", "no_match", "unavailable", "disabled", "empty")


def select_many_status(candidates, criteria: str, *, key=None, label=None,
                       timeout_s: float | None = None,
                       min_confidence: float = MIN_CONFIDENCE) -> tuple[list, str]:
    """`select_many` plus the STATUS of the round: `(rows, status)`.

    The audit's finding 8, and it is the difference between two opposite behaviours: with nothing to
    offer, `task_recall` must SAY «nothing like it» when the chooser ran and rejected everything, and
    must ASK when the chooser never ran. Both looked like `[]`.
    """
    items = list(candidates or [])
    if not items or not (criteria or "").strip():
        return [], EMPTY
    if not enabled():
        return [], DISABLED
    _label = label or (lambda c: str(c))
    _key = key or (lambda c: items.index(c))
    questions = {}
    index = {}
    for n, cand in enumerate(items, 1):
        qid = f"cand_{n}"
        index[qid] = cand
        questions[qid] = {
            # The identity goes HERE, in this candidate's own question — see the trap above.
            "instructions": f"CANDIDATE {n}: «{_label(cand)}». Against the criteria in the state, "
                            f"how well does THIS candidate fit?",
            "criteria": dict(FIT),
        }
    verdicts = choose_many_sync(criteria, questions, timeout_s=timeout_s, question_id="select")
    if not verdicts:
        return [], UNAVAILABLE          # network, timeout, open breaker: the chooser never ran
    out = []
    for qid, cand in index.items():
        v = verdicts.get(qid) or {}
        if v.get("choice") == "strong" and v.get("confidence", 0.0) >= min_confidence:
            out.append({"key": _key(cand), "candidate": cand, "fit": "strong",
                        "confidence": v.get("confidence", 0.0)})
    out.sort(key=lambda r: -r["confidence"])
    return out, (SELECTED if out else NO_MATCH)


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


def classify_sync(text: str, *, last_reply: str = "", timeout_s: float | None = None) -> dict | None:
    """Blocking request-type verdict, for tests and manual probes. Thin wrapper over choose_sync."""
    ctx = ""
    if (last_reply or "").strip():
        ctx = f"[Our previous reply: {last_reply.strip()[:200]}]"
    verdict = choose_sync("request_type", text, instructions=_RT_INSTRUCTIONS,
                          criteria=REQUEST_TYPES, context=ctx, timeout_s=timeout_s,
                          question_id="request-type")
    if not verdict:
        return None
    return {"type": verdict["choice"], "kind": KIND_MAP.get(verdict["choice"], ""),
            "confidence": verdict["confidence"], "probs": verdict["probs"],
            "latency_ms": verdict["latency_ms"]}


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


def request_async(text: str, *, last_reply: str = "") -> dict | None:
    """Fire-and-forget request-type verdict for the hot path. Thin wrapper over ask_async."""
    text = (text or "").strip()
    if not text or not enabled():
        return None
    return ask_async(text, run=lambda: classify_sync(text, last_reply=last_reply),
                     name="jev-classify")


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


# ── THE BOUNDED-DECISION CONTRACT (V2-726 A1) ────────────────────────────────────────────────────
# «A cheap decision capability available throughout Colmena whenever a process can choose among
# available options» — the operator's own objective. Everything above is that capability with a
# door per caller shape; this is the ONE door, with outcomes that can be told apart.
#
# WHAT IT IS NOT, because the audit was specific about it: no second model client, no reasoner in
# front deciding whether to ask, no semantic router. Candidates come from the DOMAIN — manifests,
# indexed rows, the workflow registry, real agent cards — and the mechanism validates membership and
# authorised effects afterwards, exactly as `contract.guard` and `action_mode_now` already do.
#
# WHY THE STATUSES ARE THE POINT. `select_many` returned `[]` for «nothing fits», «no key»,
# «network down», «switched off» and «nothing to choose between». Two of those are ANSWERS the
# caller should act on and three are ABSENCES it should route around, and `task_recall` was quietly
# treating them alike — a shortlist nobody had looked at, presented as one the chooser had narrowed.

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
                     "call_id": call_id, "provenance": provenance or MODEL})


def decide(purpose: str, evidence: str, candidates: dict, *, abstain: bool = True,
           source: str = "", turn_id: str = "", task_id: str = "", state_rev: str = "",
           deadline_s: float | None = None, effect_class: str = "view",
           min_confidence: float = MIN_CONFIDENCE, background: bool = True) -> Decision:
    """Choose among DECLARED candidates, with an outcome the caller can act on.

    `candidates` is `{id: description}` — built by the domain, never by this module. `purpose` is
    one line of what is being decided; `evidence` is the state text the decision is made against.
    `abstain=True` adds a `none` option, which is how a decision says «none of these» rather than
    being forced to pick the least bad one.

    `effect_class` is carried for the record, NOT enforced here: nothing this function returns
    executes anything. The caller maps `chosen` onto a path that is already gated — that is rule 3
    of the initiative and it does not move for a nicer API.

    Bounded: `MAX_QUESTIONS` candidates, `MAX_STATE_CHARS` of evidence, and background callers share
    `_BG_LIMIT` slots so a worker sweeping a hundred rows cannot starve anything. `deadline_s`
    counts from entry INCLUDING the wait for a slot — a decision that arrives after its deadline is
    `expired`, not late.
    """
    t0 = time.monotonic()
    cands = {str(k): str(v) for k, v in (candidates or {}).items() if str(k).strip()}
    if not cands or not (purpose or "").strip():
        return _decision(EMPTY)
    if len(cands) > MAX_QUESTIONS:
        return _decision(TOO_BIG)
    state = f"{purpose.strip()}\n{(evidence or '').strip()}"[:MAX_STATE_CHARS + 1]
    if len(state) > MAX_STATE_CHARS:
        return _decision(TOO_BIG)
    if not enabled():
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
        verdicts = choose_many_sync(state, question, timeout_s=left, question_id="decide")
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
