"""The voice turn and the text probe import the same brain modules — or say why not (V2-778 F2-22, 2026-10-01).

ALERT 5 of the architecture doc: two channels that implement the same turn drift apart, and the bank of brain
cases runs on the PROBE, so a mechanism wired only into the voice turn is one the bank cannot see. Today's
difference is frozen below: every `nucleo.flash` module the voice turn imports (the provider plus what F1 moved out
of it, the tool executor and the post-stream chain) is imported by the text channel too, or is listed in
VOICE_ONLY with its reason. A NEW voice-only module fails here by name; wiring one into the probe means deleting
its line.
"""
from __future__ import annotations

import ast
import glob
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
VOICE = ["voice/engine/llm/providers/nucleo.py", "nucleo/flash/tool_executor.py", "nucleo/flash/tool_executor_widget.py",
         "nucleo/flash/tool_executor_calls.py", "nucleo/flash/tool_executor_widget_calls.py",
         "nucleo/flash/post_stream.py", "nucleo/flash/post_stream_words.py", "nucleo/flash/post_stream_lanes.py",
         "nucleo/flash/post_stream_settle.py"]

#: Voice-only on purpose, each with its reason (the «owed» lines this ratchet was born with were paid on 2026-10-02:
#: three wired into the probe, five explained). A new voice-only module either gets wired or gets its reason here.
VOICE_ONLY = {
    "accumulator": "the voice turn accumulates STT fragments before it speaks; the text channel gets whole lines",
    "canvas_visibility": ("the ONE door that flips a card's open flag on the live canvas; the probe REPORTS a `canvas:` action and opens nothing, and reads what is open through `_ctx_ids`"),
    "music_flow": ("the probe runs the SAME rail through `music_turn.execute`, which imports it — this ratchet reads direct imports only"),
    "surface_ack": ("the probe reaches it through `router_guards.show_ack` (a re-export); the voice turn imports it directly only for the `empty` flag of the canvas event, which the probe never emits"),
    "tool_selection": ("progressive selection is off by default (V2-726 A5), so both channels offer the full `_router.tools` catalog; the voice keeps the `need_capability` retry and the recent-families memory for when it is on — wire the probe the day it is"),
    "widget_read": ("the probe reaches the SAME seam through `second_pass.probe_light_routes` (`read_widget`) — this ratchet reads direct imports only"),
}


def _flash_imports(paths) -> set[str]:
    out: set[str] = set()
    for rel in paths:
        t = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        for n in ast.walk(t):
            if isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                if mod == "nucleo.flash" or (n.level == 1 and not mod and rel.startswith("nucleo/flash/")):
                    out |= {a.name for a in n.names}
                elif mod.startswith("nucleo.flash."):
                    out.add(mod.split(".")[2])
                elif n.level == 1 and mod and rel.startswith("nucleo/flash/"):
                    out.add(mod.split(".")[0])
            elif isinstance(n, ast.Import):
                out |= {a.name.split(".")[2] for a in n.names if a.name.startswith("nucleo.flash.")}
    return out


def _probe_files() -> list[str]:
    return sorted({"nucleo/flash/probe.py", *(str(Path(p).relative_to(ENGINE))
                                             for p in glob.glob(str(ENGINE / "nucleo/flash/probe_*.py")))}
                  # the text channel's own data-op executor (V2-778 F4-33), as the voice list holds its executors
                  | {"nucleo/flash/widget_data_turn.py"})


def test_no_new_brain_module_is_wired_into_the_voice_turn_only():
    voice_only = _flash_imports(VOICE) - _flash_imports(_probe_files()) - {"probe", "probe_after", "tool_executor", "tool_executor_widget",
                                                                          "post_stream_words", "post_stream_lanes",
                                                                          "post_stream_settle", "tool_executor_calls",
                                                                          "tool_executor_widget_calls",
                                                                          "post_stream"}
    new = sorted(voice_only - set(VOICE_ONLY))
    assert not new, ("these nucleo.flash modules are imported by the voice turn and not by the text probe — the "
                     f"bank of brain cases cannot see what they do. Wire them into the probe, or list them in "
                     f"VOICE_ONLY with the reason: {new}")


def test_a_listed_module_that_the_probe_now_imports_leaves_the_list():
    stale = sorted(m for m in VOICE_ONLY if m in _flash_imports(_probe_files()))
    assert not stale, f"the probe imports these now — delete their VOICE_ONLY line: {stale}"


def test_no_voice_only_module_is_left_owed():
    """V2-778 F2-22 (2026-10-02) paid the eight «owed» lines: three wired into the probe (`build_decision`, `hard_turn`,
    `task_recall`), five given the reason they really have. A new line carries its reason from day one."""
    owed = sorted(m for m, why in VOICE_ONLY.items() if why.strip() == "owed")
    assert not owed, f"write why these are voice-only, or wire them into the probe: {owed}"
