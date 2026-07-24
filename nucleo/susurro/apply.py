"""Aplicadores de correcciones del Susurro (V2-053 F1) — MECÁNICOS, con ANTES/DESPUÉS registrado.

Regla del operador (GO §4): toda corrección aplicada deja en el timeline un evento con el snapshot previo y el
resultante de lo que tocó. En F1 nada muta estado/memoria: `repair_say` empuja una nota [SISTEMA] (el canal que
ya drena el turno siguiente) y `finding` va a la cola durable que consume el bucle de desarrollo.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import deque

FINDINGS_PATH = os.path.join(".meshkore", "logs", "susurro", "findings.jsonl")

# Dedup DURO por-request, más allá de sesiones vivas: si un worker_action ya se intentó (viva o YA TERMINADA,
# ok o fallida) hace poco, no se re-escala — evita el bucle infinito de un request condenado a fallar siempre
# igual (p.ej. generator_fail) que, sin esto, se relanzaba en cada nuevo disparo de fricción posterior.
_RECENT_REQUESTS: deque = deque(maxlen=20)   # [(request, ts), …]
_REQUEST_COOLDOWN_S = 300

# Mismo dedup para repair_say: el auditor LLM puede repetir el MISMO diagnóstico (a veces equivocado) en
# fricciones sucesivas no relacionadas — sin esto, la MISMA frase de reparación se re-inyecta en cada turno
# siguiente e secuestra respuestas a preguntas que no tienen nada que ver (bug real 2026-07-22: "Ya veo el
# mensaje de Rakel Karó…" colándose en respuestas sobre la ITV/el ojo, turno tras turno).
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


def apply_corrections(corrections: list[dict], *, reason: str, trace: str = "",
                      findings_path: str | None = None) -> list[dict]:
    """Aplica F1 (repair_say + finding). Devuelve un registro por corrección con before/after + estado."""
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
            # F2 (V2-061): RE-RUTEO — el auditor concluyó que el cerebro rápido dejó sin ejecutar una acción
            # real/consecuente → dispara el worker correcto por la MISMA vía que el FlashBrain (escalate), con el
            # contexto de memoria+conversación que dispatch adjunta. Dedup DURO contra sesiones vivas (no relanzar
            # lo que ya está en marcha). Nunca toca BRAIN RULES — solo lanza una tarea (invariante de Susurro).
            req = str(c.get("request") or "").strip()
            child = ""
            ok = False
            dup = ""
            if req:
                now = time.time()
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
                    except Exception:
                        ok = False
            rec = {"type": "worker_action", "ok": ok, "before": None, "after": req,
                   "child": child, "dedup": bool(dup)}
            _emit(("🚀 worker_action → escalada" if ok else
                   ("🧵 worker_action (ya hay un worker vivo, no duplica)" if dup else
                    "⚠️ worker_action no lanzada")),
                  text=req, extra={"before": None, "after": req, "child": child,
                                   "dup_of": dup, "ok": ok, "reason": reason})
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
