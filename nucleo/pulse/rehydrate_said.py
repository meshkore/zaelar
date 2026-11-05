"""The restart's decisions, said one event per task (V2-851 F1; split out of `rehydrate.py` by concern).

`rehydrate.at_boot` decides what a restart does with each task it finds cut (resume it, bury it, keep it waiting for
his answer); this says it to the observability viewer, one `task` event per decision, each label LITERAL at its
`emit` so the frozen-event test (`test_a_pulse_or_energy_event_survives_a_move.py`) can read them.
"""
from __future__ import annotations


def said(plan: dict) -> None:
    # Mind the field names: `observer.emit` does `ev.update(extra)`, so a `kind` inside `extra` OVERWRITES the event's
    # kind and takes its family with it (seen live: these events were classified `code`/`web` instead of `task`, so
    # the viewer's «Brain Workers» chip did not show them). The kind of work travels as `work`. And `cat` is NOT
    # passed: `observer._CAT` seals the family from the kind, its closed inventory — passing it by hand allowed a
    # retired family («main») to be made up.
    try:
        from voice.observer import emit
        def _x(ent):
            return {"id": ent["id"], "work": ent["kind"], "age_s": ent["age_s"], "reason": ent.get("why", "")}
        for ent in plan["resume"]:     # each label LITERAL at its emit: the viewer's frozen-event test reads them
            emit("task", "🔁 lo reanudo — se cortó al reiniciar", role="system", text=ent["goal"][:160], extra=_x(ent))
        for ent in plan["buried"]:
            emit("task", "✂️ se cortó al reiniciar y no la reanudo", role="system", text=ent["goal"][:160], extra=_x(ent))
        for ent in plan["waiting"]:
            emit("task", "⏸ waits for his answer — kept through the restart", role="system", text=ent["goal"][:160],
                 extra=_x(ent))
    except Exception:
        pass
