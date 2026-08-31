"""Susurro correction appliers (V2-053 F1) — MECHANICAL, with BEFORE/AFTER recorded.

Operator rule (GO §4): every applied correction leaves an event in the timeline with the previous snapshot and the
result of what it touched. In F1 nothing mutates state/memory: `repair_say` pushes a [SYSTEM] note (the channel that
already drains into the next turn), and `finding` goes to the durable queue consumed by the development loop.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import deque

FINDINGS_PATH = os.path.join(".meshkore", "logs", "susurro", "findings.jsonl")

# HARD per-request deduplication, beyond live sessions: if a worker_action was attempted recently (live or ALREADY FINISHED,
# successful or failed), do not re-escalate it — this prevents the infinite loop of a request doomed to always fail
# (e.g. generator_fail), which without this would be relaunched on every subsequent friction trigger.
_RECENT_REQUESTS: deque = deque(maxlen=20)   # [(request, ts), …]
_REQUEST_COOLDOWN_S = 300

# LOOP GUARD (2026-07-26 audit, 07/25 incident: Susurro F2 ↔ the execute-real-action widget spawned
# chained code-workers, load 5.86, and overwhelmed voice/chat). The dedup above is only TEXT similarity — an auditor
# LLM that writes "in one sentence" each time can vary enough to evade it turn after turn, while the
# semantic pattern (mirror widget for an already-escalated action, re-flagged as a risk on every subsequent refresh)
# repeats forever. This breaker is the DETERMINISTIC last-resort brake, independent of whether the
# dedup above succeeds: a HARD CAP on how many worker_action calls Susurro can trigger in a short window,
# no matter what. If reached, the circuit OPENS (dev+security first: stop spending resources, notify the operator
# ONCE) and NO new worker_action runs until the window rolls over.
_BREAKER_WINDOW_S = 600          # 10 min
_BREAKER_MAX = 3                 # máx. worker_action lanzados en la ventana
_worker_action_ts: deque = deque(maxlen=_BREAKER_MAX * 4)   # timestamps de escaladas OK
_breaker_notified_at = 0.0
_BREAKER_RENOTIFY_S = 1800       # no reavisar al operador más de una vez cada 30 min mientras siga abierto


def _breaker_tripped(now: float) -> bool:
    while _worker_action_ts and now - _worker_action_ts[0] > _BREAKER_WINDOW_S:
        _worker_action_ts.popleft()
    return len(_worker_action_ts) >= _BREAKER_MAX


def _breaker_record(now: float) -> None:
    _worker_action_ts.append(now)


def breaker_reset() -> None:
    """For tests: clear the breaker state AND the in-memory request deduplication."""
    global _breaker_notified_at
    _worker_action_ts.clear()
    _RECENT_REQUESTS.clear()
    _breaker_notified_at = 0.0

# Same deduplication for repair_say: the LLM auditor may repeat the SAME diagnosis (sometimes incorrectly) in
# successive unrelated frictions — without this, the SAME repair phrase is re-injected on every following turn
# and hijacks responses to completely unrelated questions (real bug 2026-07-22: "I see the message from Rakel
# Karó…" slipping into responses about the vehicle inspection/the eye, turn after turn).
_RECENT_REPAIRS: deque = deque(maxlen=20)    # [(text, ts), …]


def _emit(label: str, text: str = "", extra: dict | None = None):
    try:
        from voice.observer import emit
        emit("susurro", label, text=text, role="system", extra=extra or {})
    except Exception:
        pass


def _finding_key(f: dict) -> str:
    base = f"{f.get('area', '')}|{f.get('title', '')}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]


def _known_finding_keys(path: str) -> set[str]:
    keys: set[str] = set()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    keys.add(json.loads(line).get("key", ""))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return keys


_STOP = {"de", "la", "el", "los", "las", "un", "una", "en", "y", "a", "que", "del", "al", "por", "con", "para",
         "lo", "se", "su", "sus", "es", "the", "and", "for", "with", "to", "of", "in", "on", "it", "is"}


def _grounded(request: str, window: str) -> bool:
    """Does the proposed action concern something that is IN THE WINDOW, or was it invented?

    Second defense from the 2026-08-13 incident (the first is not auditing without a conversation, in `window.py`). Even with
    a window, an auditor can go off on its own and propose an action in the real world that nobody asked for; here it did so
    by copying the EXAMPLE case from its own system prompt. `worker_action` is the ONLY correction that ACTS,
    so it is the only one requiring anchoring: at least two content words from the request must appear in
    the audited window. This is not semantic understanding and does not claim to be — it is a cheap belt against text
    coming from outside the conversation. Fail-OPEN if there is no window to compare against (nothing that worked is
    broken), fail-CLOSED when there is a window and the request does not appear in it."""
    win = (window or "").lower()
    if not win:
        return True
    words = {w for w in re.findall(r"[a-záéíóúñü]{4,}", (request or "").lower()) if w not in _STOP}
    if not words:
        return True
    hits = sum(1 for w in words if w in win)
    return hits >= 2


def apply_corrections(corrections: list[dict], *, reason: str, trace: str = "",
                      findings_path: str | None = None, window: str = "") -> list[dict]:
    """Apply F1 (repair_say + finding) + F2 (worker_action). Return one record per correction with
    before/after + status. `window` = the audited document, to require ANCHORING for the only correction that ACTS."""
    findings_path = findings_path or FINDINGS_PATH
    applied: list[dict] = []
    known = None
    for c in corrections:
        t = c.get("type")
        if t == "repair_say":
            text = str(c.get("text") or "")
            now = time.time()
            try:
                from nucleo.flash.dialog import similar
                dup = any(similar(text, r, thr=0.6) for r, ts in _RECENT_REPAIRS if now - ts < _REQUEST_COOLDOWN_S)
            except Exception:
                dup = False
            ok = False
            if not dup:
                note = f"[SISTEMA] (susurro) Repara con naturalidad en tu PRÓXIMA respuesta: {text}"
                ok = True
                try:
                    from voice import brain_notes
                    brain_notes.push(note)
                    _RECENT_REPAIRS.append((text, now))
                except Exception:
                    ok = False
            rec = {"type": "repair_say", "ok": ok, "before": None, "after": text, "dedup": dup}
            _emit(("🩹 repair_say → brain_notes" if not dup else "🩹 repair_say (repetido, no re-inyectado)"),
                  text=text, extra={"before": None, "after": text, "ok": ok, "reason": reason, "dedup": dup})
            applied.append(rec)
        elif t == "worker_action":
            # F2 (V2-061): RE-ROUTING — the auditor concluded that the fast brain failed to execute a
            # real/consequential action → trigger the correct worker through the SAME path as FlashBrain (escalate),
            # with the memory+conversation context attached by dispatch. HARD deduplication against live sessions (do
            # not relaunch what is already in progress). Never touches BRAIN RULES — only launches a task (Susurro invariant).
            req = str(c.get("request") or "").strip()
            child = ""
            ok = False
            dup = ""
            breaker = False
            ungrounded = False
            now = time.time()
            if req and not _grounded(req, window):
                # The action does not concern anything in the window → it comes from outside the conversation. It is
                # DEGRADED to a finding (recorded for the dev loop) instead of being executed.
                ungrounded = True
            elif req and _breaker_tripped(now):
                breaker = True
                global _breaker_notified_at
                if now - _breaker_notified_at > _BREAKER_RENOTIFY_S:
                    _breaker_notified_at = now
                    try:
                        from voice import brain_notes
                        brain_notes.push(
                            "[SISTEMA] (susurro) demasiadas auto-reparaciones seguidas — me detengo un rato "
                            "para no saturar el sistema. Si sigue sin ir, dímelo directamente.")
                    except Exception:
                        pass
            elif req:
                try:
                    from nucleo.flash.dialog import similar
                except Exception:
                    similar = None
                if similar and any(similar(req, r, thr=0.6) for r, ts in _RECENT_REQUESTS
                                    if now - ts < _REQUEST_COOLDOWN_S):
                    dup = "cooldown"
                if not dup and similar:
                    try:
                        from nucleo import dispatch as _disp
                        for s in _disp.active_sessions():
                            g = str(s.get("goal") or "")
                            if g and similar(req, g, thr=0.6):
                                dup = str(s.get("id") or "")
                                break
                    except Exception:
                        dup = ""
                if not dup:
                    try:
                        from nucleo.flash import escalate
                        child = str(escalate.escalate_to_slowbrain(
                            req, context={"src": "susurro", "reason": reason, "trace": trace}) or "")
                        ok = bool(child)
                        if ok:
                            _RECENT_REQUESTS.append((req, now))
                            _breaker_record(now)
                    except Exception:
                        ok = False
            rec = {"type": "worker_action", "ok": ok, "before": None, "after": req,
                   "child": child, "dedup": bool(dup), "breaker": breaker, "ungrounded": ungrounded}
            _emit(("🚫 worker_action DESCARTADA (no aparece en la ventana — probable invención)" if ungrounded else
                   "🛑 worker_action (circuito ABIERTO, no escala — anti-bucle)" if breaker else
                   "🚀 worker_action → escalada" if ok else
                   ("🧵 worker_action (ya hay un worker vivo, no duplica)" if dup else
                    "⚠️ worker_action no lanzada")),
                  text=req, extra={"before": None, "after": req, "child": child,
                                   "dup_of": dup, "ok": ok, "reason": reason, "breaker": breaker})
            applied.append(rec)
        elif t == "finding":
            if known is None:
                known = _known_finding_keys(findings_path)
            key = _finding_key(c)
            fresh = key not in known
            if fresh:
                row = dict(c, key=key, ts=time.time(), reason=reason, trace=trace)
                try:
                    os.makedirs(os.path.dirname(findings_path), exist_ok=True)
                    with open(findings_path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    known.add(key)
                except Exception:
                    fresh = False
                try:
                    import bus
                    bus.emit_sync("susurro.finding", row)
                except Exception:
                    pass
            rec = {"type": "finding", "ok": True, "dedup": not fresh,
                   "before": None, "after": c.get("title", "")}
            _emit(("📌 finding → cola dev-loop" if fresh else "📌 finding (duplicado, no re-encolado)"),
                  text=f"[{c.get('severity', 'P2')}·{c.get('area', '')}] {c.get('title', '')}",
                  extra={"finding": c, "fresh": fresh, "reason": reason})
            applied.append(rec)
    return applied
