"""nucleo/workers/handoff.py — lo que se le CUENTA al operador y al worker siguiente cuando algo falla (V2-276).

Extraído de `session.py` el 2026-08-24 para pagar el trinquete de arquitectura, que llevaba rojo desde la
noche anterior por mis propios commits. Los dos son constructores de TEXTO PUROS sobre un `SessionRecord`
—cero I/O, cero estado del pool, cero contacto con el proceso del worker— y esa es toda la razón de que la
frontera sea limpia: `session.py` gobierna el ciclo de vida de una sesión viva, y estas dos funciones solo
redactan.

Son hermanas a propósito y por eso viajan juntas: las dos existen porque el mismo incidente (2026-08-18)
enseñó que un texto interno entregado tal cual miente en las dos direcciones — hacia el OPERADOR, que oyó
«API Error: The model has reached its context window limit.» donde esperaba una guitarra, y hacia el worker
SIGUIENTE, al que ese mismo texto le habría dicho que el error de su predecesor era un hallazgo.

Se re-exportan desde `session` porque los tests y `providers.py` los nombran desde allí: es una mudanza, no
un cambio de interfaz.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # pragma: no cover — solo para el anotador
    from nucleo.workers.session import SessionRecord


def operator_safe_summary(summary: str) -> str:
    """LAST GATE before a worker's summary is spoken and written to the chat wall (incident 2026-08-18).

    A raw provider error is NEVER a report. The operator asked for a guitar and got
    «API Error: The model has reached its context window limit.» — read aloud, in English, as if it were the answer.
    The 2026-08-10 quota incident closed this for its own error class by classifying it upstream; this closes it for
    the class as a WHOLE, so the next unforeseen provider message does not reach the operator either.

    It lives here, at the delivery point, ON PURPOSE: the specific paths (`provider_down`, `context_full`) each
    already replace the text with something readable, but they only cover the failures we anticipated. This one
    covers the rest, and it is a translation, never a silence — the operator always learns the task did not finish;
    what disappears is the internal wording. The full text stays in the log and in the record."""
    t = (summary or "").strip()
    if not t:
        return ""
    try:
        from nucleo.workers import providers as _prov
        if _prov.is_context_overflow(t):
            return ("Me he quedado sin espacio de contexto a mitad de esa tarea. La retomo con lo que llevaba; "
                    "si vuelve a pasar, pídemela por partes.")
        if _prov.classify_failure(t):
            return ("El proveedor que mueve mis procesos de fondo me ha dado un problema con esa tarea. "
                    "Lo tienes en el panel de estado.")
    except Exception:
        pass
    # A bare «API Error…» with no classification is still not a report: it is the CLI talking to us, not to them.
    if t.lower().startswith("api error"):
        return "Esa tarea no ha podido completarse por un fallo del proveedor. Lo tienes en el panel de estado."
    return t


def context_handoff(rec: "SessionRecord") -> str:
    """The brief a fresh worker inherits when the previous one ran out of context (incident 2026-08-18).

    Built ONLY from what we already hold in the record — plan, steps taken, last narrated note, breadth reported.
    No LLM call: compacting must not depend on a model being reachable at the exact moment one just failed, and this
    runs on the failure path.

    What it deliberately does NOT carry is the dead worker's `result_summary`: on this path that field holds the raw
    provider error, and pasting it in would tell the new worker its predecessor's error message was a finding."""
    parts = [f"RETOMA esta tarea, que se quedó a medias porque el worker anterior agotó su contexto: {rec.goal}"]
    if rec.plan:
        done = max(0, min(int(rec.done or 0), len(rec.plan)))
        parts.append("Su plan era: " + " · ".join(str(p) for p in rec.plan[:8])
                     + f" (llevaba {done} de {len(rec.plan)} pasos).")
    if rec.note:
        parts.append(f"Lo último que dijo: {str(rec.note)[:300]}")
    if rec.steps:
        seen: list[str] = []
        for s in rec.steps[-8:]:
            bit = " ".join(x for x in (str(s.get("action") or ""), str(s.get("target") or "")) if x).strip()
            if bit and bit not in seen:
                seen.append(bit)
        if seen:
            parts.append("Ya había mirado: " + " · ".join(seen)[:600] + ".")
    if int(rec.considered or -1) > 0:
        parts.append(f"Había revisado {rec.considered} candidatos y se quedaba con {max(0, int(rec.kept or 0))}.")
    parts.append("NO repitas lo ya mirado: sigue desde ahí y ENTREGA en cuanto tengas algo presentable, "
                 "aunque sea parcial. Ve al grano — el contexto es limitado.")
    return "\n".join(parts)
