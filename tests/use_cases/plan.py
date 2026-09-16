"""The PLAN of a use case: the ordered list of what is going to happen, declared before it happens.

The operator's ask, 2026-09-16: «cada test puede tener una lista con todo lo que se va a hacer y luego
una pantalla de control». That only works if the list exists BEFORE the run — a plan reconstructed from
the events that already happened is a log, and a log is exactly the thousand-line scroll this replaces.

So one module owns the plan, and two very different readers import it:

  · `tests/use_cases/catalog.py` renders it into the case's `execution_path`, which is what the
    Observatory paints as an unticked checklist while the case is still just a catalog entry;
  · `tests/use_cases/e2e/agent/bus.py` emits `step.started` / `step.finished` against these exact
    `id`s while the round runs, which is what ticks them.

They agree because there is one list, not two. Stdlib only, and no import of the runner: the catalog is
built by a web request on the dashboard thread and must not drag in the driver, the judge or httpx.

`TURNS` is the one step that is not a single action — it holds the conversation, and the bus reports it
as `turno N/M` as it advances, so the control panel can count TURNS as the unit of progress for this
family (a use case is 10-20 turns, not one test).
"""
from __future__ import annotations

#: id, label, and whether the step is conditional on the scenario declaring it.
STEPS: tuple[dict[str, object], ...] = (
    {"id": "engine", "label": "motor desechable en pie", "optional": False},
    {"id": "seed", "label": "siembra en memoria (sesión aparte)", "optional": True},
    {"id": "turns", "label": "conversación con el agente", "optional": False, "repeats": True},
    {"id": "verify", "label": "verificación del mecanismo real", "optional": False},
    {"id": "judge", "label": "juez: resultado, mecanismo, naturalidad", "optional": False},
    {"id": "verdict", "label": "veredicto al marcador", "optional": False},
)

STEP_IDS: tuple[str, ...] = tuple(str(step["id"]) for step in STEPS)


def labels() -> list[str]:
    """The plan as the Observatory's `execution_path` — human labels, in order."""
    return [f"{step['label']}{' (si el caso lo declara)' if step.get('optional') else ''}"
            for step in STEPS]


def label_of(step_id: str) -> str:
    for step in STEPS:
        if step["id"] == step_id:
            return str(step["label"])
    return step_id
