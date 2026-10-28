"""The errand's narration, the results sheet's title and its notes are text the ENGINE writes for the screen,
so they come out in the instance's language — never in Castilian on an English instance.

Measured on an English instance (operator screenshot, 2026-10-21): a sheet titled «Resultados», the note
«Buscando a fondo…», task rows «buscando «…» en la memoria…» and «ejecutando un paso…». Every one of them was
a literal in the engine. They now come from the `ui` pack (`task.phase.*`, `widgets.results.*`): Spanish on a
Spanish instance, and English on any language with no pack of its own yet (the manifest is the floor).
"""
from __future__ import annotations

import pytest


def _lines() -> dict:
    from nucleo.request.kind import default_label
    from nucleo.workers import progress as P
    from nucleo.workers.tool_steps import _tool_phase
    from widgets.results import data as sheet
    return {
        "recall": P.phrase({"where": "memoria", "action": "recall", "target": "dinner"}),
        "step": _tool_phase("Bash", {"command": "ls -la"}),
        "alive": P.still_alive(P.phrase({"where": "navegador", "action": "scroll"}), 95),
        "found": P.found(3),
        "label": default_label("generic"),
        "queued": P.say("queued", "queued"),
        "title": sheet.default_title(),
        "deep": sheet.note_text("note_searching_deep", "Searching in depth…"),
        "none": sheet.note_text("note_none", "No results."),
    }


SPANISH = {
    "recall": "buscando «dinner» en la memoria",
    "step": "ejecutando un paso…",
    "alive": "recorriendo la página — lleva 1 min",
    "found": "3 resultados en la página",
    "label": "Pensando…",
    "queued": "en cola",
    "title": "Resultados",
    "deep": "Buscando a fondo…",
    "none": "Sin resultados.",
}
ENGLISH = {
    "recall": "searching memory for «dinner»",
    "step": "running a step…",
    "alive": "scrolling through the page — 1 min so far",
    "found": "3 results on the page",
    "label": "Thinking…",
    "queued": "queued",
    "title": "Results",
    "deep": "Searching in depth…",
    "none": "No results.",
}


@pytest.mark.parametrize("code, want", [("es", SPANISH), ("en", ENGLISH), ("sw", ENGLISH)])
def test_the_narration_is_said_in_the_instance_language(monkeypatch, code, want):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    from i18n import runtime as _rt
    if code not in _rt.PRESET:     # a language whose bundle has not been generated yet: English is the floor
        monkeypatch.setattr(_rt, "strings", lambda c: (_rt._preset(c) or {}) if c in _rt.PRESET else {})
    _rt.invalidate()
    try:
        assert _lines() == want
    finally:
        _rt.invalidate()
