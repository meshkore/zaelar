"""The pill GRAMMAR, and the one door a RESULT is written through.

A pill's `kind` says what KIND of knowledge it is, and one of them is not like the others: `result` claims that
something was DONE. The only party that knows that is the circuit that ran the errand and judged its end state
(`verdict == "met"`). The operator's words never are — «captúrame el estilo hasta darlo por capturado» is a
REQUEST, and stored as a result it later answered «¿has terminado?» with «Sí, está terminado» for an errand that
had failed (V2-825 F1).

So the grammar is enforced where a pill is born, not at the reader:
  - the distiller's kinds are `profile · pref · fact · event · intent · request` (`request` = something he ASKED
    the assistant to do, done or not). A `result` the model returns is written as a `request` — the distiller cannot know an order was carried out (`distilled_kind`).
  - `result(...)` is the door for the circuit's verdict. It writes only on `met`; anything else is refused.
"""
from __future__ import annotations

#: Written only by `result()`, on the circuit's `met` verdict.
RESULT = "result"


def distilled_kind(raw: object) -> str:
    """The kind a distilled pill is stored as. A `result` from the distiller is a request by construction; an
    unknown kind stays as the model wrote it (readers treat it as a fact), an empty one is a fact."""
    kind = (str(raw or "") or "fact").strip().lower() or "fact"
    return "request" if kind == RESULT else kind


async def result(text: str, *, task_id: str, verdict: str, level: str = "mid",
                 importance: float = 0.5, meta: dict | None = None) -> bool:
    """Write the OUTCOME of an errand as a `result` pill — only when the circuit's verdict is `met`.

    Returns True when the pill was queued. Any other verdict writes nothing: a failed or interrupted errand's
    outcome is a fact of the task store, read from there, never from memory."""
    text = (text or "").strip()
    v = str(verdict or "").strip().lower()
    why = "" if text and v == "met" else ("empty text" if not text else f"verdict is {v or 'missing'}, not met")
    _observe(task_id, v, why)
    if why:
        return False
    from nucleo.memory_agent.external import remember
    stamp = {**(meta or {}), "source": f"worker:{task_id}", "verdict": "met"}
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
