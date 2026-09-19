"""nucleo/jev.py — Jev (TypeSafe System One) request-type classifier, the single integration point.

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

Non-blocking by construction: `request_async()` fires a daemon thread at arm time and returns a
handle; `resolve_kind()` peeks at fire time without ever waiting. Jev is advisory — a slow, failed
or unsure call leaves the regex verdict untouched, so the filler never depends on the network.

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


def _post(state: str, timeout_s: float) -> dict:
    """One blocking Jev call. Separated so tests can fake the wire without touching threads."""
    body = json.dumps(
        {
            "state": state,
            "model": MODEL,
            "questions": {
                "request_type": {
                    "type": "choice",
                    "instructions": "What kind of turn is the user's message",
                    "criteria": REQUEST_TYPES,
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


def _parse(payload: dict) -> tuple[str, float, dict]:
    ans = (payload.get("answers") or {}).get("request_type") or {}
    choice = str(ans.get("choice") or "")
    try:
        confidence = float(ans.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    probs = ans.get("probabilities") or {}
    if choice not in REQUEST_TYPES:
        choice = ""
    return choice, confidence, dict(probs)


def _emit(text: str, *, choice: str, confidence: float, probs: dict,
          latency_ms: int, error: str = "") -> None:
    try:
        from voice.observer import emit
        emit(
            "brain", "jev request-type",
            text=f"{text[:100]} -> {choice or 'none'} ({confidence:.2f}, {latency_ms} ms)"
            + (f" [error: {error[:80]}]" if error else ""),
            role="system",
            extra={"cat": "flash", "choice": choice, "confidence": round(confidence, 3),
                   "probabilities": probs, "latency_ms": latency_ms,
                   "pool": KIND_MAP.get(choice, ""), "error": error[:80]},
        )
    except Exception:
        pass


def classify_sync(text: str, *, last_reply: str = "", timeout_s: float | None = None) -> dict | None:
    """Blocking verdict, for tests and manual probes. None when disabled or on any failure."""
    text = (text or "").strip()
    if not text or not enabled():
        return None
    state = text
    if (last_reply or "").strip():
        state += f"\n[Our previous reply: {last_reply.strip()[:200]}]"
    t0 = time.monotonic()
    try:
        choice, confidence, probs = _parse(_post(state, _timeout_s() if timeout_s is None else timeout_s))
    except Exception as e:  # noqa: BLE001 — the voice path must never break on a classifier
        _emit(text, choice="", confidence=0.0, probs={},
              latency_ms=int((time.monotonic() - t0) * 1000), error=f"{type(e).__name__}: {e}")
        return None
    latency_ms = int((time.monotonic() - t0) * 1000)
    _emit(text, choice=choice, confidence=confidence, probs=probs, latency_ms=latency_ms)
    return {"type": choice, "kind": KIND_MAP.get(choice, ""),
            "confidence": confidence, "probs": probs, "latency_ms": latency_ms}


def request_async(text: str, *, last_reply: str = "") -> dict | None:
    """Fire-and-forget verdict for the hot path. Returns a handle, or None when there is nothing
    to wait for (disabled, no key, empty text) — the caller keeps its local verdict either way."""
    text = (text or "").strip()
    if not text or not enabled():
        return None
    handle: dict = {"event": threading.Event(), "result": None}

    def _run() -> None:
        handle["result"] = classify_sync(text, last_reply=last_reply)
        handle["event"].set()

    threading.Thread(target=_run, name="jev-classify", daemon=True).start()
    return handle


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
