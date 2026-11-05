"""The worker briefs AS A WORKER READS THEM — rendered by the real builders, never a module's source (refactor2710-08).

A rule that lives in a brief is tested here on the text the worker receives: a string split across two literals, or a
block a builder forgot to append, is invisible to a source read and visible here. Since V2-851 F3 a worker reads its
prompt AND the catalogue families it can ask for (`python -m nucleo.cli.bridge catalog <family>`): a lesson that
moved to a family is still read by the worker that needs it, so `rendered()` is both.
"""
from __future__ import annotations


def prompts_only(goal: str = "busca un piso de alquiler en Madrid y dime los tres mejores") -> str:
    """The web brief and the generic (trusted) brief for one goal, joined — what travels in the first request."""
    from nucleo.workers import prompts
    return prompts._web_prompt(goal, "") + "\n\n" + prompts._build_prompt(goal, "", True)


def rendered(goal: str = "busca un piso de alquiler en Madrid y dime los tres mejores") -> str:
    """Everything a worker can read for one goal: both briefs and every catalogue family."""
    from nucleo.workers.prompts import catalog
    return prompts_only(goal) + "\n\n" + "\n\n".join(catalog.full(f) for f in catalog.FAMILIES)


def families() -> str:
    """Every catalogue family's full set, as `python -m nucleo.cli.bridge catalog <family>` prints it."""
    from nucleo.workers.prompts import catalog
    return "\n\n".join(catalog.full(f) for f in catalog.FAMILIES)


def web(goal: str, context: str = "", brief: dict | None = None, **kw) -> str:
    """What a WEB worker can read for this goal: its prompt and every family."""
    from nucleo.workers import prompts
    return prompts._web_prompt(goal, context, brief, **kw) + "\n\n" + families()


def generic(goal: str, context: str = "", brief: dict | None = None) -> str:
    """What a trusted GENERIC worker can read for this goal: its prompt and every family."""
    from nucleo.workers import prompts
    return prompts._build_prompt(goal, context, True, brief) + "\n\n" + families()


def research(brief: dict) -> str:
    """What a research worker reads of its brief: the block, and the results sheet's contract (family `results`)."""
    from nucleo.workers import brief as _brief
    from nucleo.workers.prompts import catalog
    return _brief.to_prompt_block(brief) + "\n\n" + catalog.full("results")


def untrusted_header() -> str:
    from nucleo.workers.prompts import catalog
    return catalog.words("header_untrusted")
