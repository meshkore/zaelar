"""Every `agent_report` command our own instructions name parses — and the measured mis-glued call does too
(node 2.677).

search-buy-boat-multicountry ES (2026-10-14, sandbox 093838-es): the status demand (`nucleo/loop.REPORT_DEMAND`)
names `phase "<…>"` and `progress "<nota>" --done <pasos hechos>` in one sentence; the worker ran
`agent_report phase "Buscando Lagoon 440 …" --done 1` and got exit code 2, so the report it was told to give never
arrived. The test reads the instructions from the source (every string literal under `nucleo/`, adjacent literals
joined), so a new instruction that names a flag the CLI does not take fails here, not in a worker's sandbox.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from nucleo import agent_report

ENGINE = Path(__file__).resolve().parents[4]
_CMD = re.compile(r"agent_report\s+(phase|note|plan|progress|goal|considered)\b(.*?)(?=agent_report|\n|`|$)")


def _literals(path: Path) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{x}" for v in node.values))
    return out


def _instructions() -> list[tuple[str, list[str]]]:
    found = []
    for path in sorted((ENGINE / "nucleo").rglob("*.py")):
        for text in _literals(path):
            for m in _CMD.finditer(text):
                flags = re.findall(r"--[a-z]+", m.group(2))
                found.append((m.group(1), flags))
    return found


def test_the_instructions_are_found():
    subs = {s for s, _ in _instructions()}
    assert {"phase", "progress", "plan"} <= subs
    assert any("--done" in f for _, f in _instructions())


@pytest.mark.parametrize("sub, flags", sorted({(s, tuple(f)) for s, f in _instructions()}))
def test_each_named_command_parses(sub, flags):
    argv = [sub, "2" if sub == "considered" else "texto"]
    for f in flags:
        argv += [f, "2"]
    agent_report.parser().parse_args(argv)


def test_the_measured_call_parses_and_reports_both(monkeypatch):
    sent = []
    monkeypatch.setattr(agent_report, "_post", lambda body: sent.append(body) or 0)
    rc = agent_report.main(["phase", "Buscando Lagoon 440 en portales náuticos", "--done", "1"])
    assert rc == 0
    assert sent == [{"phase": "Buscando Lagoon 440 en portales náuticos"},
                    {"progress": "Buscando Lagoon 440 en portales náuticos", "done": 1}]


@pytest.mark.parametrize("raw, n", [("3", 3), ("3/5", 3), ("1,2,3", 3), ("paso 2", 2), ("1 2", 2)])
def test_a_step_count_as_a_worker_writes_it(raw, n):
    assert agent_report.parser().parse_args(["progress", "x", "--done", raw]).done == n


def test_a_count_with_no_number_is_a_usage_error():
    with pytest.raises(SystemExit):
        agent_report.parser().parse_args(["progress", "x", "--done", "todos"])
