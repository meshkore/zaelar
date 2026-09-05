"""V2-588 — «ordena los widgets» is voice-reachable: a built capability the model could not name.

Measured in session 0e3a42d6 (2026-09-05): asked to arrange the widgets («Dale al botón del front end»),
the model claimed TWICE «no hay un botón en el front-end para eso» — false: the ⤢ button (WidgetRail),
`Desktop.arrange()` (V2-464), `POST /api/canvas/arrange` and the SSE handler all existed. The worker it
escalated to confirmed there was no bridge action and improvised by re-opening cards, then confabulated
«el canvas queda ordenado». An undeclared capability is one the model NARRATES (V2-540's law): everything
downstream was built and nothing faced the model. Three doors now share one rail: the `arrange_canvas`
tool, the action map's `arrange`, and the REST endpoint — all emit the same ("widget", "arrange") event.
"""
from __future__ import annotations

from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]


def test_the_tool_exists_and_needs_no_arguments():
    from nucleo.flash import router
    t = next((x for x in router.tools() if x["function"]["name"] == "arrange_canvas"), None)
    assert t is not None, "arrange_canvas dropped from the catalog — the capability is unnameable again"
    assert not t["function"]["parameters"].get("required"), "a whole-canvas op takes no arguments"


def test_asking_to_arrange_retains_the_tool_through_the_trim():
    """The V2-586/V2-548 lesson applied at birth: a tool whose family cannot name it gets trimmed exactly
    on the turns that ask for it."""
    from nucleo.flash import router, tool_selection as ts
    full = router.tools()
    for phrase in ("ordena los widgets de la pantalla", "recoloca los widgets", "arrange the widgets"):
        kept, report = ts.select(full, turn_text=phrase)
        assert "arrange_canvas" in {t["function"]["name"] for t in kept}, (phrase, report)


def test_the_action_map_knows_arrange_and_emits_on_the_shared_rail():
    from nucleo.actionmap import executor
    assert executor.validate({"do": "arrange"}) == ""
    fired = []
    ok = executor.execute({"do": "arrange"}, lambda kind, label, **kw: fired.append((kind, label)),
                          phrase="ordena los widgets")
    assert ok is True
    assert ("widget", "arrange") in fired, "the map must use the SAME emit as the REST endpoint"


def test_both_seed_packs_carry_arrange_phrases_and_the_pack_version_moved():
    """A pack fixed later reaches nobody unless the version moves (V2-545's re-import rule)."""
    import json
    for lang in ("es", "en"):
        d = json.loads((ENGINE / f"nucleo/actionmap/seeds/{lang}.json").read_text(encoding="utf-8"))
        assert d["version"] >= 4, f"{lang} pack version did not move — existing installs never re-import"
        arr = [e for e in d["entries"] if (e.get("action") or {}).get("do") == "arrange"]
        assert arr, f"{lang} pack has no arrange phrases"


def test_both_channels_wire_the_tool():
    """The parallel-implementation trap, pinned as everywhere else: voice AND probe must handle it."""
    voice = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert 'name == "arrange_canvas"' in voice, "the voice channel dropped the handler"
    assert '"arrange_canvas" in names' in probe, "the probe channel dropped the mirror"
    assert '"canvas:arrange"' in probe, "the probe no longer reports/executes the canvas action"
