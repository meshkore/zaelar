"""The REM SYNTHESIS prompt is composed without blowing up (regression 2026-08-09).

The real bug this prevents: `_REM_SYSTEM` ends with a literal JSON example —`[{"concept": str, "insight":
str|null}]`— and was interpolated with `str.format(lang=…)`, which treats those braces as placeholders → `KeyError:
'"concept"'` on EVERY call. `memory/rem.py::synthesize` catches any exception from the hook and returns 0, so
the deep-sleep INSIGHTS phase had been writing NOTHING for weeks, silently failing open: the
symptom was "memory does not consolidate", not a visible error.

The test does NOT call any model: it exercises prompt composition and the hook's fail-open contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from nucleo import memllm  # noqa: E402


def test_prompt_rem_se_compone_sin_reventar():
    """Composition MUST NOT raise, and the language must actually be substituted."""
    system = memllm._REM_SYSTEM.replace("{lang}", "castellano")
    assert "castellano" in system
    assert "{lang}" not in system
    # the contract's JSON example remains intact (it anchors the model's output format)
    assert '"concept"' in system and '"insight"' in system


def test_format_sobre_el_prompt_esta_prohibido():
    """Explicit safeguard: if someone puts `.format()` back here, this catches it instead of production.

    `str.format` on this prompt ALWAYS raises while the contract contains literal braces—which is
    correct and will not be removed. That is why interpolation must use `.replace`.
    """
    import pytest
    with pytest.raises(KeyError):
        memllm._REM_SYSTEM.format(lang="castellano")


def test_synthesize_no_llama_al_modelo_sin_grupos():
    """Cheap contract: with no groups, there is neither a call nor an exception."""
    assert memllm.synthesize_concept_groups([]) == []


def test_synthesize_compone_el_prompt_de_verdad(monkeypatch):
    """The REAL path to the network boundary: if composition blew up, `chat_sync` would not be
    invoked and the failure would again be hidden behind the caller's fail-open behavior."""
    visto = {}

    def _fake_chat_sync(task, system, user, **kw):
        visto["task"], visto["system"], visto["user"] = task, system, user
        return '[{"concept": "salud", "insight": "Cuida su salud con rutina de gimnasio."}]'

    monkeypatch.setattr(memllm, "chat_sync", _fake_chat_sync)
    out = memllm.synthesize_concept_groups(
        [{"concept": "salud", "pills": ["Va al gimnasio los lunes.", "Dejó el café en enero."]}]
    )
    assert visto["task"] == "rem"
    assert "{lang}" not in visto["system"]          # the language arrived substituted
    assert "gimnasio" in visto["user"]              # the pills reached the model
    assert out == [{"concept": "salud", "insight": "Cuida su salud con rutina de gimnasio."}]
