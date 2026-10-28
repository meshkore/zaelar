"""The pill GRAMMAR, and the one door a RESULT is written through.

A pill's `kind` says what KIND of knowledge it is, and `result` is not like the others: it claims an errand
delivered. Only the circuit that ran the errand and judged its end state knows that; the operator's words never do —
«captúrame el estilo hasta darlo por capturado» is a REQUEST, and stored as a result it answered «¿has terminado?»
with «Sí, está terminado» for an errand that had failed (V2-825 F1).

So the grammar is enforced where a pill is born, not at the reader:
  - the distiller's kinds are `profile · pref · fact · event · intent · request` (`request` = something he ASKED
    the assistant to do). A `result` the model returns is stored as a `request` (`distilled_kind`).
  - `result(...)` is the door for the circuit's verdict: it writes when the worker DELIVERED
    (the verdicts that declare `delivered`), stamping the verdict so a reader tells «checked» from «delivered, unverified»; a
    failed or parked errand writes nothing.
"""
from __future__ import annotations

RESULT = "result"


def distilled_kind(raw: object) -> str:
    """The kind a distilled pill is stored as. A `result` from the distiller is a request by construction; an
    unknown kind stays as the model wrote it (readers treat it as a fact), an empty one is a fact."""
    kind = (str(raw or "") or "fact").strip().lower() or "fact"
    return "request" if kind == RESULT else kind


async def result(text: str, *, task_id: str, verdict: str, level: str = "mid",
                 importance: float = 0.5, meta: dict | None = None) -> bool:
    """Write an errand's OUTCOME as a `result` pill (`meta.verdict` = the verdict) when the worker delivered; True
    when queued. Any other verdict writes nothing: that outcome is a fact of the task store, never of memory."""
    text = (text or "").strip()
    from nucleo.circuit import verdict as _verdict   # each verdict declares whether the worker DELIVERED
    v = getattr(_v := _verdict.of(str(verdict or "").strip().lower()), "name", str(verdict or "").strip().lower())
    why = ("" if text and _v is not None and _v.delivered
           else "empty text" if not text else f"verdict is {v or 'missing'}, nothing delivered")
    _observe(task_id, v, why)
    if why:
        return False
    from nucleo.memory_agent.external import remember
    stamp = {**(meta or {}), "source": f"worker:{task_id}", "verdict": v}
    await remember({"text": text, "kind": RESULT, "level": level, "importance": importance, "meta": stamp})
    return True


def _observe(task_id: str, verdict: str, why: str) -> None:
    """The door's decision is an event: accepted, or refused and why."""
    try:
        from voice.observer import emit
        emit("memory", "resultado rechazado" if why else "resultado aceptado", role="system", text=why,
             extra={"layer": "write", "kind": RESULT, "task_id": task_id, "verdict": verdict,
                    "accepted": not why, "reason": why})
    except Exception as e:  # noqa: BLE001 — observability NEVER breaks the memory
        from loguru import logger
        logger.debug(f"memory_agent.writer: result-door event not emitted: {e}")
