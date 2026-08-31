"""We asked it to write a file and did not give it the tool to do so.

The payload from the bridges is passed via `@fichero` since V2-379, and the prompt spells it out:
*«escríbelo con Write a un fichero de tu directorio y pásalo con `@fichero.json`»*. But `Write` was not in
the allowlist passed to the CLI, so the CLI requested approval that in headless **nobody is going to grant**.

Measured on 2026-08-28 in `find-best-hotel-city__us` (24/7 set), with the entire chain visible for the first time
thanks to the fixes from that same night:

    ⚠️ Claude requested permissions to write to …/zaelar-workers/6b9810-1/informe.json,
       but you haven't granted it yet.
    ⚠️ Exit code 2 · no puedo leer el payload de informe.json: [Errno 2] No such file or directory

Nine blind turns and a score of 1/5 in that round. An instruction that the system makes impossible to follow is not
an instruction: it is a trap for the model AND for whoever reads the transcript.
"""
from __future__ import annotations

from nucleo.workers import claude_session as CS


def test_el_worker_PUEDE_escribir():
    assert "Write" in CS._DEFAULT_TOOLS


def test_y_solo_Write():
    """Neither `Edit` nor `NotebookEdit`: a worker gets a fresh disposable directory, and writing its own JSON is
    the smallest operation there is. MODIFYING files that already exist is another matter, and nobody has asked for it."""
    assert "Edit" not in CS._DEFAULT_TOOLS and "NotebookEdit" not in CS._DEFAULT_TOOLS
    assert set(CS._DEFAULT_TOOLS) == {"Read", "Write"}


def test_el_prompt_y_la_allowlist_dicen_lo_MISMO():
    """The important half: the defect was not that a tool was missing, but that **the one the prompt requests** was missing.
    If the prompt shows another way tomorrow, this needs to be checked again."""
    from nucleo import dispatch_prompts as DP
    reglas = DP._drawer_rules("/x/.venv/bin/python")
    assert "Write" in reglas, "el prompt dejó de pedir Write y esta allowlist se quedó sin motivo"


def test_con_deny_tools_sigue_SIN_NADA():
    """Untrusted input (§v3·P): the upper gate is not touched — an untrusted worker does not gain a tool
    because the one next to it needs it."""
    import inspect
    src = inspect.getsource(CS)
    i = src.index("if spec.deny_tools:")
    assert "tools: list[str] = []" in src[i:i + 160]
