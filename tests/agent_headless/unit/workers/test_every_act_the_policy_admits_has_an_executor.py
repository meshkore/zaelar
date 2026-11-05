"""Every act the worker policy admits has an executor (V2-851 F2, §15c).

F0 found `push_channel` dead: CONFIRM in `worker_policy`, no branch in `_exec_allow`, so after his yes the act fell to
«acción ALLOW no ejecutable» — a question to him that ran nothing. It was deleted; this keeps the class closed: every
name in `_KNOWN_ACTS` (but `ask_user`, which parks before executing) is a branch of `worker_api_exec._exec_allow`.
Read off the source (AST), so no executor runs.
"""
from __future__ import annotations

import ast
import inspect

from nucleo.cli import worker_api_exec
from nucleo.cli.worker_policy import _KNOWN_ACTS


def _executed() -> set[str]:
    tree = ast.parse(inspect.getsource(worker_api_exec._exec_allow))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "action":
            for c in node.comparators:
                for k in ([c] if isinstance(c, ast.Constant) else list(getattr(c, "elts", []))):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        out.add(k.value)
    return out


def test_every_known_act_but_the_question_has_a_branch():
    missing = [a for a in _KNOWN_ACTS if a != "ask_user" and a not in _executed()]
    assert not missing, f"admitted by the policy with nothing to run them: {missing}"


def test_the_dead_door_is_gone():
    assert "push_channel" not in _KNOWN_ACTS
