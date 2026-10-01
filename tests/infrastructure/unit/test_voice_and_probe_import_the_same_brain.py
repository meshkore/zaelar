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

#: Voice-only on purpose, or owed. «owed» means it was voice-only when this ratchet was born and nobody has yet
#: written why — the next person to touch it either wires it into the probe or writes the reason here.
VOICE_ONLY = {
    "accumulator": "the voice turn accumulates STT fragments before it speaks; the text channel gets whole lines",
    "build_decision": "owed",
    "canvas_visibility": "owed",
    "data_ops": "owed",
    "hard_turn": "owed",
    "music_flow": "owed",
    "surface_ack": "owed",
    "task_recall": "owed",
    "tool_selection": "owed",
    "widget_read": "owed",
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
                                             for p in glob.glob(str(ENGINE / "nucleo/flash/probe_*.py")))})


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
