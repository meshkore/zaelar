"""nucleo/turn/declined_build.py — a «no» to BUILDING is not a «no» to the errand (docs-single-recipe-not-a-list EN).

Measured 2026-10-14 (sandbox 20261014-120418-en). «Give me the carbonara recipe» was escalated as «…and display it
in the documento widget»; the build gate read that as «build a new card» and asked «Shall I?». He answered «just the
recipe is fine, no need to build anything. lmk when it's ready», and the model re-escalated the SAME recipe, this
time with no card to build. The answer closed the build — and the re-escalation was dropped with it as «the errand
the answer resolved», so nothing ever wrote the recipe, the sheet stayed empty, and the turn said «Done.».

When the answer is NO and the parked errand was a widget build, a request of the same turn that is the same errand
WITHOUT a build is what he still wants: it starts. A «yes» is unchanged (the confirmed errand is relaunched by the
gate itself), and so is a «no» to anything that is not a build.
"""
from __future__ import annotations


def still_wanted(request: str, resolved: str) -> bool:
    """True when `request` is `resolved` asked again without the widget build he just declined."""
    from nucleo.request import kind as errand_kind
    return bool(errand_kind.code_change(resolved or "")) and not errand_kind.code_change(request or "")
