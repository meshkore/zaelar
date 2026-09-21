"""An expectation is a CLAIM ABOUT THE PRODUCT, and it rots exactly like a comment does.

MEASURED, and the reason this file exists. `watch-a-video-not-listen-to-it` told its judge, in the text the
judge reads to grade the round:

    «the video widget has NO playlist actions … a request to queue several videos has no mechanism today
     and belongs in a finding, not here»

It was written on 2026-08-26. `8861c929` shipped `sort_list`/`filter_list`/`clear_list` (on top of
`add`/`next`/`previous`/`play_item`) on 2026-08-27 — the day after. For **26 days** the scoreboard carried
that case as ✅ with a 5 while instructing the judge to score a correct queue as OUT OF SCOPE. Nothing was
red. Nothing could go red: a judge cannot notice that the yardstick it was handed is the wrong length.

WHAT THIS GUARDS, narrowly and on purpose. Not «the prose is accurate» — that is not checkable. Only the one
shape that already cost us: an expectation that **denies** a capability while naming an action the widget's
own manifest **declares**. A deliberate absence stays legal and there are several (`dictate-a-reply-
honestly` runs with WhatsApp unlinked, `play-music-and-build-playlist` with Spotify deliberately not
connected) — those name a CONNECTOR or a state, never a declared action.

The fix when this goes red is never to soften the sentence: it is to decide whether the case should now
JUDGE that behaviour, because the product grew and the yardstick did not.
"""
from __future__ import annotations

import json
import pathlib
import re

WIDGETS = pathlib.Path("widgets")

#: Words that turn an expectation into a denial. Kept small and literal — a fuzzy list would flag the
#: ordinary prose of a hundred cases and this guard would be switched off within a week.
DENIAL = re.compile(
    r"(has no |have no |there (?:is|are) no |no mechanism|does not (?:exist|have)|do not exist"
    r"|n[oó] existe|no hay ning|no tiene )", re.I)

#: An action named the way these files name one: in backticks, or inside a slash-separated parenthetical.
NAMED = re.compile(r"`([a-z][a-z0-9_]{2,})`|\(([a-z][a-z0-9_/]{6,})\)")


def _declared() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for man in WIDGETS.glob("*/manifest.json"):
        if man.parent.name.startswith("_"):
            continue
        try:
            out[man.parent.name] = set(json.loads(man.read_text(encoding="utf-8")).get("actions") or {})
        except Exception:  # noqa: BLE001 — a malformed manifest is another test's business
            continue
    return out


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;])\s+", text or "") if s.strip()]


def test_no_case_expectation_denies_an_action_its_widget_declares():
    from tests.use_cases import cases_data

    declared = _declared()
    assert declared, "no widget manifests found — this guard would pass vacuously"
    all_actions = {a for acts in declared.values() for a in acts}

    offences: list[str] = []
    for case in cases_data.CASES:
        for sentence in _sentences(getattr(case, "expected", "") or ""):
            if not DENIAL.search(sentence):
                continue
            named: set[str] = set()
            for m in NAMED.finditer(sentence):
                named |= {p for p in (m.group(1) or m.group(2) or "").split("/") if p}
            hits = sorted(named & all_actions)
            if hits:
                owners = {a: sorted(w for w, acts in declared.items() if a in acts) for a in hits}
                offences.append(f"{case.id}: denies {hits} — declared by {owners}\n      «{sentence.strip()}»")

    assert not offences, (
        "a case expectation tells the judge a SHIPPED action does not exist, so a correct behaviour would "
        "be graded as out of scope:\n  " + "\n  ".join(offences)
        + "\n\nDecide whether the case should judge that behaviour now — do not just soften the wording.")


# ── the same rot, one level up: the catalog's own header ────────────────────────────────────────────────
# `CASES.md` opened with «NINE promoted» while twenty were. Nobody was lying: the number was true when it
# was typed and there is no way for a hand-written count to notice the eleventh. It is the smallest possible
# instance of the same failure as the expectation above — a claim about the product, written next to the
# product, with nothing tying it to the product — so it gets the same treatment rather than a better memory.
def test_the_catalog_header_counts_what_is_actually_promoted():
    import re

    from tests.use_cases import cases_data

    md = (pathlib.Path("tests/use_cases") / "CASES.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*Status: [^*]*?(\d+) promoted\.\*\*", md)
    assert m, "the catalog header no longer states how many cases are promoted — it is the first thing read"
    said = int(m.group(1))
    real = sum(1 for c in cases_data.CASES if getattr(c, "status", "") == "promoted")
    assert said == real, (
        f"CASES.md says {said} promoted and `cases_data.CASES` holds {real}. Update the header — a catalog "
        "that miscounts itself is read as a catalog that is not maintained.")
