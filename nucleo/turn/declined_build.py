"""nucleo/turn/declined_build.py — a «no» to BUILDING is not a «no» to the errand (docs-single-recipe-not-a-list EN).

Measured 2026-10-14 (sandbox 20261014-120418-en). «Give me the carbonara recipe» was escalated as «…and display it
in the documento widget»; the build gate read that as «build a new card» and asked «Shall I?». He answered «just the
recipe is fine, no need to build anything. lmk when it's ready», and the model re-escalated the SAME recipe, this
time with no card to build. The answer closed the build — and the re-escalation was dropped with it as «the errand
the answer resolved», so nothing ever wrote the recipe, the sheet stayed empty, and the turn said «Done.».

When the answer is NO and the parked errand was a card build, a request of the same turn that is the same errand
WITHOUT a build is what he still wants: it starts. Both halves are read from state, never from words (V2-851 F4): the
parked errand was a build because the card gate parked it (`asked`), and this turn's request is not one because the
turn's brief says its kind is not card code.
"""
from __future__ import annotations

_ASKED: list[str] = []          # the requests the card gate parked (most recent last, bounded)


def _flat(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def asked(request: str) -> None:
    """The card gate parked `request` (`dispatch.confirm.remember_code_change`)."""
    _ASKED.append(_flat(request))
    del _ASKED[:-16]


def _this_turn_builds() -> bool:
    try:
        from nucleo.request import kind as _kind
        from nucleo.turn import brief as _tb
        return bool(_kind.code_change(_kind.verdict(_tb.of_this_turn())))
    except Exception as e:  # noqa: BLE001 — unreadable: not a build
        from loguru import logger
        logger.debug(f"declined_build: the turn's kind unread — {e!r}")
        return False


def still_wanted(request: str, resolved: str) -> bool:
    """True when `request` is `resolved` asked again without the card build he just declined."""
    return _flat(resolved) in _ASKED and not _this_turn_builds()
