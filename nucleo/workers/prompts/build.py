"""The generic worker's brief (`_build_prompt`): the request, its context and the blocks it needs.

V2-851 F3 — composed in the session's language (`voice` pack, `worker_brief.*`) as a STABLE PREFIX (the shell's rules,
the header, the playbook, the catalogue's headlines) followed by what changes per task (language, today, his rules,
memory, the recent conversation, the request, the research brief), so a provider that caches by prefix reuses it.
What used to be written out whole for every task — the long method, the network's step 0, the trusted sites,
widgets, messaging, scheduling, `decide` — is a family of the catalogue, read on request (`prompts/catalog.py`).
"""
from __future__ import annotations

from nucleo.workers import brief as research
from nucleo.workers.prompts import catalog, playbook as _playbook
from nucleo.workers.prompts.context import _recent_conversation_block, _today_block
from nucleo.workers.prompts.drawer import _with_interpreter
from nucleo.workers.prompts.surfaces import worker_language_block


def _build_prompt(request: str, context: str, trusted: bool, brief: dict | None = None, *,
                  playbook: str = _playbook.ERRAND) -> str:
    if not trusted:
        parts = [catalog.words("header_untrusted"), worker_language_block()]
        if context:
            parts.append(f"{catalog.words('context_head')}\n{context}")
        parts.append(f"{catalog.words('request_head')}\n{request}")
        return "\n\n".join(p for p in parts if p)
    stable = [catalog.words("header"), _playbook.block(playbook, _playbook.done_when(playbook)), catalog.headlines()]
    variable = [worker_language_block(), _today_block(), catalog.said_block()]
    variable.append(catalog.known_lines(request))   # what is KNOWN about this errand: per task, so not on request
    if context:
        variable.append(f"{catalog.words('context_head')}\n{context}")
    recent = _recent_conversation_block()
    if recent:
        variable.append(f"{catalog.words('recent_head')}\n{recent}")
    variable.append(f"{catalog.words('request_head')}\n{request}")
    # The research BRIEF goes after the literal request: it says HOW to do it well, read knowing what is asked.
    if brief:
        variable.append(research.to_prompt_block(brief) or "")
    # A surface's presentation budgets ride with the `results` family, on request (the headlines name every surface,
    # so hooking them on the text here would attach them to every worker).
    return _with_interpreter("\n\n".join(p for p in stable + variable if p))
