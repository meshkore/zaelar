"""A US persona that answers «Madrid centro» is not measuring the product — it is measuring the harness.

Measured 2026-08-27, before any of this existed: of the 60 US scenarios, **19 carried Spanish reality inside**
— a San Francisco persona giving «Madrid centro» as its neighbourhood, «menos de 100.000 km» under an opening
written in miles, budgets in € under a $ figure — and **all 60** read their instructions in Spanish inside an
English brief, with a final line telling them to write in English. Neither was sloppiness: the follow-up
answers live in a profile keyed by the bare case id, shared by both locales, and the scaffolding was written
once, in Spanish, for everybody.

What is shared and what is not: the QUESTION zaelar asks does not change with the market, so the profile is
still one. The ANSWER is where the country lives, and that is `_US_ANSWERS`.

The third test is a RATCHET, not a pass: 25 US cases still fall back to the shared Spanish answers. They are
tiers 3-7 and none of them is in the measured set, so this is honest debt rather than a hidden failure — and
it can only go DOWN. Adding a case to that list is the one edit this test exists to make expensive.
"""
from __future__ import annotations

import re

from tests.use_cases import cases_data as CD
from tests.use_cases.e2e.agent import derived as D
from tests.use_cases.e2e.agent import scenarios as S

_SPANISH_REALITY = re.compile(
    r"Madrid|Barcelona|Bilbao|Sevilla|Zaragoza|España|españ|€|\beuros?\b|\bkm\b|Wallapop|Idealista|Chamberí",
    re.IGNORECASE)
_SPANISH_SCAFFOLD = re.compile(r"No reveles|Te despides|Datos que das|si te pregunta por")


def _us_scenarios():
    return [x for x in S.all_scenarios() if x.locale == "us"]


def test_no_us_persona_lives_in_spain():
    offenders = sorted(x.id for x in _us_scenarios() if _SPANISH_REALITY.search(x.persona_brief or ""))
    assert not offenders, (
        "these US scenarios answer with Spanish reality — currency, distance or a Spanish city:\n  "
        + "\n  ".join(offenders))


def test_and_reads_its_instructions_in_its_own_language():
    """A brief that instructs in one language and closes with «write in English» is the exact mixed prompt
    that already produced language drift here (2026-08-18, the whole first sandboxed batch)."""
    offenders = sorted(x.id for x in _us_scenarios() if _SPANISH_SCAFFOLD.search(x.persona_brief or ""))
    assert not offenders, "these US briefs still carry Spanish scaffolding:\n  " + "\n  ".join(offenders)


#: US cases whose follow-up answers are still the shared Spanish ones. Tiers 3-7, none of them measured yet.
#: This list may only SHRINK — write the case's answers into `_US_ANSWERS` and delete its line here.
_SHARED_ANSWERS_DEBT = {
    "archive-newsletters", "book-barber-slot", "buy-known-product", "cancel-trial-before-it-charges",
    "clean-and-reply-inbox", "compare-flights-sf-austin", "confirm-restaurant-together",
    "coordinate-dinner-with-alex", "file-expense-report", "grocery-restock-reactive",
    "gym-membership-no-silent-renew", "house-search-los-angeles", "negotiate-lower-phone-bill", "pay-known-bill",
    "plan-joint-trip-with-friend", "rebook-delayed-flight-now", "reorder-prescription", "resolve-meetup-conflict",
    "search-buy-book", "smog-check-before-deadline", "split-airbnb-with-jordan", "track-package-reschedule",
    "track-price-drop-buy", "weekend-trip-austin",
}


def test_the_debt_of_shared_answers_only_goes_down():
    pending = {c.id for c in CD.CASES if getattr(c, "locale", "") == "us"
               and (p := D.PROFILES.get(c.id)) and p.clarifications and not p.clarifications_us}
    new = sorted(pending - _SHARED_ANSWERS_DEBT)
    assert not new, (
        f"US cases newly falling back to the shared Spanish answers: {new}. Write them into `_US_ANSWERS` — "
        "this list is a ratchet and does not grow.")
    # And conversely: whoever pays down debt has to remove it from the list, or the ratchet stops tightening.
    stale = sorted(_SHARED_ANSWERS_DEBT - pending)
    assert not stale, f"these were fixed and are still declared as debt: {stale}"
