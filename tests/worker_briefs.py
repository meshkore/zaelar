"""The worker briefs AS A WORKER READS THEM — rendered by the real builders, never a module's source (refactor2710-08).

A rule that lives in a brief is tested here on the text the worker receives: a string split across two literals, or a
block a builder forgot to append, is invisible to a source read and visible here.
"""
from __future__ import annotations


def rendered(goal: str = "busca un piso de alquiler en Madrid y dime los tres mejores") -> str:
    """The web brief and the generic (trusted) brief for one goal, joined."""
    from nucleo.workers import prompts
    return prompts._web_prompt(goal, "") + "\n\n" + prompts._build_prompt(goal, "", True)
