"""The THREE families of test, and the one axis above them: the language.

Until now the Observatory listed nine suites side by side, ordered by nothing in particular, and the
operator had to know that `browser` is a pile of deterministic pytest while `use_cases` is an LLM
negotiating with the product. Two different questions were being asked in the same list:

  · **integrity** — «does the code still do what it did yesterday?» Deterministic pytest. It is about
    CODE, not about a user, and it has no language: `test_opens_in_wal` is the same test in Madrid and
    in Los Angeles.
  · **use_cases** — «can a person actually get this done?» An intelligent agent drives a real
    conversation against a real engine, a watchdog watches for drift, the mechanism is verified against
    system state and a judge scores it. Every one of these is INDEXED BY LANGUAGE, because the task is
    not the same task: in Spain the second-hand bike is on Wallapop, in the US it is somewhere else.
  · **memory** — «does it remember, age, correct and forget correctly?» Neither of the above: a corpus
    plus a clock (ingest → consolidate → REM → recall, 180 simulated days). It is composite like a use
    case but its shape is a corpus, not a conversation, so it keeps its own family.

The language selector is the PRIMARY index, not a filter: picking `es` or `us` selects a different SET
of cases, not a subset of one set. There is deliberately no "todos los idiomas" option — mixing them is
what the two locales' scoreboards did before, and it made «7/24 verdes» a number about nothing.

Honesty rule for a locale with nothing in it: say `0 casos · no existe todavía`, never hide the family
and never borrow the other locale's cases to fill the gap. A family that is not localized at all
(`integrity`) is shown under every locale unchanged, because it genuinely is the same thing.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The locales the suite indexes by. `id` is what every runner, port table and scoreboard already
#: writes (`--locale es`, `<case>__us`, ports 43921/43922) — this table names them, it does not rename
#: them.
LOCALES: tuple[dict[str, str], ...] = (
    {"id": "es", "label": "Español · España", "short": "ES", "flag": "🇪🇸"},
    {"id": "us", "label": "English · United States", "short": "US", "flag": "🇺🇸"},
)

LOCALE_IDS: tuple[str, ...] = tuple(locale["id"] for locale in LOCALES)
DEFAULT_LOCALE = "es"


@dataclass(frozen=True)
class Family:
    id: str
    label: str
    question: str          # the question this family answers, in the operator's words
    kind: str              # deterministic | dynamic | corpus
    localized: bool        # does the language selector change WHICH cases exist here?
    members: tuple[str, ...]   # suite ids that live under this family


FAMILIES: tuple[Family, ...] = (
    Family(
        id="integrity",
        label="Integridad del código",
        question="¿el código sigue haciendo lo que hacía ayer?",
        kind="deterministic",
        localized=False,
        members=("agent-headless", "browser", "memory", "voice", "infrastructure",
                 "connectors", "cluster"),
    ),
    Family(
        id="use_cases",
        label="Casos de uso",
        question="¿una persona consigue de verdad hacer esto?",
        kind="dynamic",
        localized=True,
        members=("use_cases", "journey"),
    ),
    Family(
        id="memory",
        label="Memoria",
        question="¿recuerda, envejece, corrige y olvida bien?",
        kind="corpus",
        localized=True,
        members=("memory",),
    ),
)

FAMILY_IDS: tuple[str, ...] = tuple(family.id for family in FAMILIES)

#: A suite id can appear in two families (`memory` is both deterministic pytest and a live corpus).
#: This maps a suite to the family that owns its DETERMINISTIC half, which is the one the pytest
#: event stream must be filed under.
_DETERMINISTIC_OWNER = {suite: "integrity" for suite in FAMILIES[0].members}


def family(family_id: str) -> Family:
    for entry in FAMILIES:
        if entry.id == family_id:
            return entry
    raise KeyError(family_id)


def family_of_pytest(suite_id: str) -> str:
    """Which family a deterministic pytest node belongs to. Always `integrity` when the suite is
    registered there — a memory UNIT test is code integrity, not a memory corpus."""
    return _DETERMINISTIC_OWNER.get(suite_id, "integrity")


def locale_of(case: dict) -> str:
    """The locale a case belongs to, or "" when it is not localized.

    Read in this order, because three conventions already exist in the tree and all three are load
    bearing somewhere:
      1. an explicit `locale` field (the catalog adapters emit it);
      2. `raw.locale` (what `use_cases/catalog.py` carried before this existed);
      3. the `__es` / `__us` suffix the derived scenarios and the scoreboard use in their ids.
    """
    explicit = str(case.get("locale") or "")
    if explicit in LOCALE_IDS:
        return explicit
    raw = case.get("raw") or {}
    if isinstance(raw, dict):
        nested = str(raw.get("locale") or "")
        if nested in LOCALE_IDS:
            return nested
    case_id = str(case.get("id") or "")
    for locale in LOCALE_IDS:
        if case_id.endswith(f"__{locale}") or f"::{locale}::" in case_id:
            return locale
    return ""


def belongs_to(case: dict, locale: str) -> bool:
    """A case is shown under `locale` when it declares that locale, or when it declares none at all.

    The second half is the rule that keeps a non-localized case visible instead of orphaned: a pytest
    node, a memory corpus written before the axis existed, a journey step. The day one of those grows
    a locale, it starts filtering — nothing else has to change.
    """
    own = locale_of(case)
    return own == "" or own == locale


def rows(counts: dict[str, dict[str, int]] | None = None) -> list[dict]:
    """The family table for the UI. `counts[family_id][locale]` fills in the per-locale case count so a
    family with nothing in a locale can say so instead of looking broken."""
    counts = counts or {}
    return [
        {
            "id": entry.id, "label": entry.label, "question": entry.question, "kind": entry.kind,
            "localized": entry.localized, "members": list(entry.members),
            "counts": counts.get(entry.id, {}),
        }
        for entry in FAMILIES
    ]
