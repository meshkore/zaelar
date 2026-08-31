"""The worker must be able to CALL its bridges on the first attempt.

Discovered on 2026-08-02 as soon as the worker's narration became visible: on this machine **bare `python` does not
exist** (only `python3` and the venv do), and the prompt literally told it `python -m nucleo.widget_cli …`. The worker
obeyed, failed, and started trying variants—`.venv/bin/python`, `python3`, `python3 -m nucleo.…`—running into
the allowlist, which matches by literal PREFIX. Each undeclared variant = an approval that nobody grants in headless
mode. Minutes of a search were lost there, and it was invisible because only the `tool_use`s were recorded.

Two guarantees, both necessary: the prompt gives it the RESOLVED interpreter, and the allowlist accepts any reasonable
form in case it improvises anyway.
"""
import os
import sys

from nucleo.dispatch import _DEV_TOOLS, _build_prompt
from nucleo.workers import claude_session as cs


def test_the_resolved_interpreter_actually_exists():
    py = cs.bridge_python()
    assert os.path.isabs(py) and os.path.exists(py), f"el intérprete que damos al worker no existe: {py}"


def test_prompt_never_ships_a_bare_python_bridge_command():
    """Not a single unresolved `python -m nucleo.…`: that is a command that will not start on this machine."""
    import re
    p = _build_prompt("busca 3 piscinas y ponlas en pantalla", "", True)
    assert not re.findall(r"(?<![/\w])python3? -m nucleo\.", p)
    assert f"{cs.bridge_python()} -m nucleo.widget_cli" in p


def test_prompt_states_the_interpreter_up_front():
    p = _build_prompt("cualquier cosa", "", True)
    assert cs.bridge_python() in p.split("\n")[0]     # first line: no excuse to guess


def test_untrusted_prompt_is_left_alone():
    """Untrusted profile = no tools or bridges; there is no command to resolve."""
    p = _build_prompt("texto de un peer", "", False)
    assert "-m nucleo." not in p


def test_allowlist_covers_every_bridge_x_every_spelling():
    for mod in ("mem_cli", "agent_report", "nav_cli", "worker_bridge", "widget_cli"):
        for py in ("python", "python3", ".venv/bin/python", cs.bridge_python()):
            assert f"Bash({py} -m nucleo.{mod}:*)" in cs._BRIDGE_TOOLS, f"{py} -m nucleo.{mod} sin declarar"


def test_git_bridge_gets_the_same_treatment():
    assert f"Bash(python3 -m nucleo.git_cli:*)" in _DEV_TOOLS
    assert {"Read", "Write", "Edit"} <= set(_DEV_TOOLS)


def test_bridge_python_falls_back_to_the_venv(monkeypatch):
    monkeypatch.setattr(sys, "executable", "")
    assert cs.bridge_python().endswith(os.path.join(".venv", "bin", "python"))


def test_the_delivery_recipe_matches_what_the_worker_can_actually_do():
    """The method cannot send it a recipe that the guards block.

Three forms tested live on 2026-08-02, two fail: pasting the JSON into the command line breaks due to
quoting; the heredoc is blocked by the shell guard (“the security guard blocks the heredoc because of the syntax
{"”). And writing outside the working directory (`/tmp/…`, `TMP/…`) requests an approval that nobody grants in headless
mode—1m32s were lost there with the investigation already finished. The only thing that worked: a RELATIVE-path file
(`--permission-mode acceptEdits` covers the working directory) + `@file`."""
    p = _build_prompt("busca 3 piscinas y ponlas en pantalla", "", True)
    assert "@informe.json" in p
    assert "<<'JSON'" not in p                        # the heredoc is blocked: it cannot return to the method
    # The recipe is searched for in the ENTIRE 4b step (up to 5), not its first N chars: the fixed 1200-character
    # cutoff became too short as soon as 4b grew to cover the details of a SINGLE item (V2-115), and a test failed
    # even though its subject—what recipe is sent to the worker—had not changed at all.
    recipe = p.split("4b)")[1].split("5)")[0]
    assert "RUTA RELATIVA" in recipe
    assert "NUNCA `/tmp/…`" in recipe                 # /tmp may appear only as FORBIDDEN, never as an instruction
