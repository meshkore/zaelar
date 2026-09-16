"""V2-711 T0.7 · The file of highest consequence keeps the evidence of why it is the way it is.

## What was lost

`87874bd7` (2026-08-31) was a legitimate functional fix (V2-509, «the gate reads the ORDER, not the words»)
and it also carried that day's comment-translation batch. `nucleo/danger.py` came out of it with a
one-line docstring — the bare sentence «Documentation translated to English.» — and **93** comments
replaced by the literal «# translated implementation note». Same damage in `nucleo/agent_api.py` (9) and
`nucleo/cron_api.py`
(7): 109 across three files, out of 777 the batch walked.

That is the worst possible place for it. This repo's method IS that each pattern carries beside it the
incident that measured it — the docstring that was destroyed explained the gate, its siblinghood with the
browser's own gate, and why blind stems are forbidden — and every one of those notes is what stops the next
agent from re-widening a pattern that was deliberately narrowed. Re-grafted by hand in V2-711 T0.7, onto the
code as it stands today, because the same commit changed the code too: this was never a `git checkout`.

That **three** files out of 777 ended this way is luck, not design. This is the design.

## The trap this test had to avoid

⚠️ A scan for a literal goes red on the prose that EXPLAINS the literal — the V2-615 lesson, paid there by a
CSS guard that tripped on its own explanatory comment. `danger.py`'s new module docstring names the marker in
a sentence describing what was lost, and that sentence is documentation, not damage. So the two are
distinguished by SHAPE: damage is a comment line that is ONLY the marker, or a docstring that is ONLY the
placeholder. A paragraph mentioning it is neither.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

_MARKER = "translated implementation note"
_DOC_PLACEHOLDER = "Documentation translated to English."

_SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git", "vendor", "tests"}

#: Modules whose comments ARE the mechanism: each carries the incident that shaped it, and a reader who
#: loses them re-widens a pattern that was deliberately narrowed. A module joins this list when its rules
#: are load-bearing enough that «why is it like this» cannot be answered from the code alone.
_CRITICAL = (
    "nucleo/danger.py",          # the classifier the three decision points read
    "widgets/contract.py",       # the V2-705 refusal that stopped 147 DELETEs
    "nucleo/errands/party.py",   # the highest-consequence mouth in the engine
    "widgets/rows.py",           # the generic data door, where the friction is the RADIUS
    "widgets/server_api.py",     # the single funnel every caller passes through
    "nucleo/worker_policy.py",   # what a Brain Worker may do
)


def _py_files():
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        if any(part in _SKIP_DIRS for part in rel.split("/")):
            continue
        yield rel, p


def _damaged_lines(text: str) -> list[str]:
    """Lines that ARE the placeholder, never a paragraph that mentions it (see the trap, above)."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line in (f"# {_MARKER}", f"#{_MARKER}"):
            out.append(line)
        elif line in (f'"""{_DOC_PLACEHOLDER}"""', f"'''{_DOC_PLACEHOLDER}'''"):
            out.append(line)
    return out


def test_no_module_carries_a_placeholder_where_its_reasoning_was():
    hits = []
    for rel, p in _py_files():
        try:
            n = len(_damaged_lines(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
        if n:
            hits.append(f"{rel}: {n}")
    assert not hits, (
        "a comment was replaced by a placeholder and the incident it recorded is gone. Recover it from the "
        "commit BEFORE the translation batch (`git log --diff-filter=M -- <file>`) and graft it onto the "
        "code as it stands — never a bare checkout, the code moved too:\n  " + "\n  ".join(hits))


def _preamble(text: str) -> str:
    """What the module says about ITSELF before any code — a docstring, or the leading comment block some of
    these files use instead (`server_api.py` is written that way and it reads perfectly well). The test is
    about the REASONING surviving, not about which of the two shapes carries it."""
    doc = ast.get_docstring(ast.parse(text))
    if doc:
        return doc
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("#"):
            lines.append(s.lstrip("#").strip())
        elif s:
            break
    return "\n".join(lines)


@pytest.mark.parametrize("rel", _CRITICAL)
def test_a_critical_module_says_what_it_is_for(rel):
    p = ENGINE / rel
    assert p.exists(), f"{rel} is listed as critical and is not on disk: if it moved, update this list"
    doc = _preamble(p.read_text(encoding="utf-8"))
    assert doc, f"{rel} lost the preamble that says what it is for"
    assert _DOC_PLACEHOLDER not in doc.splitlines()[0], f"{rel}'s preamble is the placeholder, not the reason"
    assert len(doc) >= 200, (
        f"{rel}'s preamble is {len(doc)} chars. This module's rules are load-bearing: what it is FOR, and "
        f"which incident shaped it, has to survive the next agent who reads only this file.")


def test_the_gates_docstring_still_names_its_sibling_and_its_three_readers():
    """The two facts the destroyed docstring carried that nothing else in the repo states: this gate is the
    SIBLING of the browser's per-click one, and three decision points read this module for three different
    questions. Losing either is how the four vocabularies drifted apart in the first place."""
    doc = ast.get_docstring(ast.parse((ENGINE / "nucleo/danger.py").read_text(encoding="utf-8"))) or ""
    assert "navegador" in doc, "the browser gate is its sibling and the docstring has to say so"
    for reader in ("is_dangerous", "moves_money", "ends_a_commitment"):
        assert reader in doc, f"the docstring no longer says what {reader} is for"
