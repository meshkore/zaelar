"""nucleo/jev.py — Jev (TypeSafe System One) Choice client, the single integration point.

The voice filler has ~1.1 s (ZAELAR_FILLER_MS) between the arm (model start) and the moment a cover
may sound. The regex classifier in `voice/engine/speech/filler_audio.py` answers instantly but only
knows shapes it was taught; Jev answers in 70-500 ms with a calibrated verdict over request types,
so it can name the class before the deadline instead of after the release. This module is the ONLY
place that talks to Jev — the filler is its first caller, later ones reuse it.

Protocol (verified against https://docs.typesafe.ai, 2026-09-20):
  POST https://api.typesafe.ai/v1/systemone, Bearer key, JSON {state, model: "jev-latest",
  questions: {request_type: {type: "choice", instructions, criteria}}}.
Answer: {answers: {request_type: {choice, probabilities, confidence}}}, no generated text.

Key resolution (names only, never values): TYPESAFE_API_KEY from the environment — which also covers
`zaelar.env`, since `server/common.py` loads that store into the environment at startup — else the
bare key in `.meshkore/credentials/jev.md` (gitignored, read here so it is never duplicated).

Non-blocking by construction: `ask_async()` fires a daemon thread at arm time and returns a
handle; `resolve_choice()` peeks at fire time without ever waiting. Jev is advisory — a slow, failed
or unsure call leaves the local verdict untouched, so no caller ever depends on the network.
The request-type classifier (`classify_sync` / `request_async` / `resolve_kind`) is the first
caller, kept as a thin wrapper over the generic Choice primitive below.

Observability: every completed call emits one `brain` event (`jever request-type`) with the
utterance, the verdict, the confidence distribution and the milliseconds it took, so the timeline
shows when Jev was asked, how long it took and what it answered.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

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


def _engine_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_key() -> str:
    """TYPESAFE_API_KEY from the environment (covers zaelar.env), else the bare key file."""
    env = (os.getenv("TYPESAFE_API_KEY") or "").strip()
    if env:
        return env
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
                return line.strip()
    except Exception:
        pass
    return ""


def _timeout_s() -> float:
    try:
        return max(0.1, int(os.getenv("ZAELAR_JEV_TIMEOUT_MS", "900")) / 1000.0)
    except Exception:
        return 0.9


def enabled() -> bool:
    """False silences the whole module: no thread, no HTTP, callers keep their local verdict."""
    if (os.getenv("ZAELAR_JEV", "") or "").strip().lower() in ("0", "off", "no", "false"):
        return False
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
          pool: str = "") -> None:
    try:
        from voice.observer import emit
        emit(
            "brain", f"jev {question_id}",
            text=f"{text[:100]} -> {choice or 'none'} ({confidence:.2f}, {latency_ms} ms)"
            + (f" [error: {error[:80]}]" if error else ""),
            role="system",
            extra={"cat": "flash", "choice": choice, "confidence": round(confidence, 3),
                   "probabilities": probs, "latency_ms": latency_ms,
                   "pool": pool or KIND_MAP.get(choice, ""), "error": error[:80]},
        )
    except Exception:
        pass


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
        return None
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
