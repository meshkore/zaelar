"""The use-case tester's window into the Observatory — the tier that used to run BLIND.

Measured 2026-09-16, and it is the reason this file exists: of the six runners under `tests/`, five
emit the platform event protocol (`memory/e2e/bot`, `memory/e2e/timeline`, `journey`, `voice/e2e/agent`,
the pytest plugin) and the ONE the operator cares most about — the dynamic use-case tester — emitted
nothing at all. It printed to a terminal and wrote a report when it was over. So the Observatory showed
its 166 cases as a static catalog («Catálogo — sin runner todavía») and, when a round was actually
running, the only thing on screen was `process.output`: the tester's own stdout, line by line, which is
precisely the thousand-line scroll the operator asked to be rid of.

What a watcher needs is not the stdout. It is:

  · **the plan before it happens** — `tests/use_cases/plan.py`, ticked as it advances, so «what is it
    doing right now» is a position in a list and not a guess from the last printed line;
  · **the turns as turns** — a use case is 10-20 turns of negotiation, and the unit of progress for
    this family is the TURN, not the case. «57 / 1000 acciones» is only meaningful if a turn counts.
  · **the verdict with its two halves separate** — judge score and mechanism, because a mechanism
    defect never shows green however good the average (the scoreboard's own rule).

## Fail-soft, always

Every entry point here is wrapped: a dashboard that is not listening, a run directory that vanished, a
value that will not serialize — none of them may take down a round that has already been paid for in
real model calls and real minutes. The same rule `recorder.py` holds for the video holds here: the
telemetry is a MIRROR of the round, never part of it.

## Off by default

With no `ZAELAR_TEST_RUN_DIR` in the environment there is no writer and every call is a no-op, so the
runner keeps working exactly as before when launched straight from a terminal
(`python -m tests.use_cases.e2e.agent.run --scenario X --sandbox`). The variable is set by
`tests/platform/cli.py` when the round is launched through `python -m tests run use_cases`.
"""
from __future__ import annotations

import os
from typing import Any

from tests.use_cases import plan as planmod

_SUITE = "use_cases"
_writer = None
_resolved = False


def _out():
    """The EventWriter, or None. Resolved once — a round makes hundreds of calls through here."""
    global _writer, _resolved
    if _resolved:
        return _writer
    _resolved = True
    run_dir = os.getenv("ZAELAR_TEST_RUN_DIR")
    if not run_dir:
        return None
    try:
        from tests.platform.events import EventWriter
        _writer = EventWriter(run_dir, run_id=os.getenv("ZAELAR_TEST_RUN_ID"))
    except Exception:  # noqa: BLE001 — see module docstring: telemetry never kills a round
        _writer = None
    return _writer


def enabled() -> bool:
    return _out() is not None


def _emit(event_type: str, **fields: Any) -> None:
    writer = _out()
    if writer is None:
        return
    try:
        writer.emit(event_type, suite=_SUITE, **fields)
    except Exception:  # noqa: BLE001
        pass


def case_id(scenario) -> str:
    """The stable catalog id of a scenario — the SAME string `tests/use_cases/catalog.py` publishes,
    so a row the Observatory painted from the catalog is the row that lights up when it runs.

    A derived scenario carries its locale in its id (`book-hotel-night-known__us`); a hand-written one
    does not (`hotel-under-15-days`). Only the scenario's OWN locale suffix is stripped — not any `__`
    in the id — so a case that happens to contain a double underscore keeps it.
    """
    raw = str(getattr(scenario, "id", ""))
    locale = str(getattr(scenario, "locale", "") or "")
    if locale and raw.endswith(f"__{locale}"):
        raw = raw[: -len(locale) - 2]
    return f"use_cases::{locale}::{raw}"


def batch_discovered(scenarios: list) -> None:
    """Announce the whole batch BEFORE the first turn, so the control panel has a denominator.

    Without this the panel can only count what has already finished, which is how a progress bar ends
    up reading «7473 / 1» — a number the UI had to invent because nobody declared the total.
    """
    total = len(scenarios)
    for index, scenario in enumerate(scenarios, start=1):
        _emit("test.discovered", test_id=case_id(scenario), label=getattr(scenario, "title", "") or
              getattr(scenario, "id", ""), index=index, total=total,
              locale=str(getattr(scenario, "locale", "") or ""),
              tier=int(getattr(scenario, "tier", 0) or 0),
              # The turn BUDGET, so the control panel can build an action total before a single turn has
              # happened. Without it «57 / 1000 acciones» can only ever be «57 / 57».
              turns=int(getattr(scenario, "turns", 0) or 0),
              plan=[{"id": step["id"], "label": step["label"]} for step in planmod.STEPS])
    _emit("collection.finished", total=total)


def case_started(scenario, *, sandboxed: bool, session: str = "") -> None:
    _emit("test.started", test_id=case_id(scenario),
          label=getattr(scenario, "title", "") or getattr(scenario, "id", ""),
          locale=str(getattr(scenario, "locale", "") or ""),
          tier=int(getattr(scenario, "tier", 0) or 0),
          sandboxed=bool(sandboxed), session=session,
          turns=int(getattr(scenario, "turns", 0) or 0),
          plan=[{"id": step["id"], "label": step["label"]} for step in planmod.STEPS])


def step_started(scenario, step_id: str, *, detail: str = "") -> None:
    _emit("step.started", test_id=case_id(scenario), step=step_id,
          label=planmod.label_of(step_id), detail=detail)


def step_finished(scenario, step_id: str, *, status: str = "passed", detail: str = "") -> None:
    """`status` is one of passed | failed | skipped. A step the scenario never declared (no memory
    seed, say) is `skipped` — it has to be VISIBLE as not-run, not silently absent, or the checklist
    stops being a checklist."""
    _emit("step.finished", test_id=case_id(scenario), step=step_id,
          label=planmod.label_of(step_id), status=status, detail=detail)


def turn(scenario, *, index: int, who: str, text: str, budget: int = 0) -> None:
    """One conversational turn. `who` is 'tester' or 'zaelar'.

    The tester's line is an `interaction.input` and the agent's an `interaction.output`, which is the
    protocol the Observatory already renders for memory and journey — a use case does not need its own
    event type to show a conversation.
    """
    payload = {"test_id": case_id(scenario), "turn": int(index), "who": who,
               "label": f"turno {index}" + (f"/{budget}" if budget else "")}
    if who == "tester":
        _emit("interaction.input", input={"text": text}, **payload)
    else:
        _emit("interaction.output", output={"text": text}, **payload)


def watchdog(scenario, verdict: dict) -> None:
    """The watchdog's opinion is an OPINION, not a fact (`test_el_watchdog_es_opinion_no_hecho.py`),
    so it rides as its own event and never as a step status."""
    _emit("watchdog.verdict", test_id=case_id(scenario),
          health=str(verdict.get("health", "")), action=str(verdict.get("action", "")),
          reason=str(verdict.get("reason", ""))[:400])


def case_finished(scenario, *, status: str, state: str = "", overall: Any = None,
                  scores: dict | None = None, turns: int = 0, verdict: str = "",
                  duration_ms: float = 0.0) -> None:
    """`status` is the platform's pass/fail for the run; `state` is the scoreboard's richer verdict
    (PASS · FAIL · INFRA · CAPPED), which deliberately does not collapse into it: an INFRA round says
    nothing about the use case and must never be painted as a product failure."""
    _emit("test.finished", test_id=case_id(scenario),
          label=getattr(scenario, "title", "") or getattr(scenario, "id", ""),
          status=status, state=state, overall=overall, scores=dict(scores or {}),
          turns=int(turns), verdict=str(verdict)[:600], duration_ms=round(float(duration_ms), 2),
          locale=str(getattr(scenario, "locale", "") or ""))
