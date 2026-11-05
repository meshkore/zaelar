"""C15 — a contacts group made by conversation (V2-854): «make me a group with the school parents» → the agent asks
WHO → he names three people → the group exists with exactly them.

On the text channel he cannot point at three cards («este, este y este»), so the answer names them; the case is the
same: the first turn creates nothing and asks, the second fills the group. The group is read from the sandbox's
contacts store as a FILE: a label on each member today, or a group row with members once F1 lands — either shape
counts. Nothing is mirrored to WhatsApp (no `create_group` order) and nothing leaves the machine.

Opt-in like the whole battery (`ZAELAR_TEST_LIVE_BATTERY=1`); a sandbox of the case's own, never his engine.
"""
from __future__ import annotations

import time
import unicodedata

import pytest

from . import contacts_seed
from .script import sent_since
from .contacts_seed import directory_engine  # noqa: F401 — the case's own sandbox

ASK = {"es": "Créame un grupo con los padres del colegio", "en": "Make me a group with the school parents"}
WHO = {"es": ("Lucía Prats, Jordy Mas y Rakel Ibarz", ("lucia-active", "active-jordy", "fav-rakel")),
       "en": ("Katherine Hale, Jon Reyes and Megan Ford", ("fav-katherine", "active-jon", "megan-tel"))}
WORD = {"es": "padres", "en": "parents"}


def _fold(s) -> str:
    n = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def _members(workspace, word: str) -> set[str]:
    """Who is in a group whose name carries `word`: label holders, or the members of a group row (F1)."""
    db = contacts_seed.store_rows(workspace)
    out = {c["id"] for c in db.get("contacts") or [] if any(word in _fold(g) for g in c.get("groups") or [])}
    for g in db.get("groups") or []:                          # F1's collection, whatever it names its rows
        if isinstance(g, dict) and word in _fold(g.get("name") or g.get("label")):
            out |= {str(m) for m in g.get("members") or []}
    return out


@pytest.mark.parametrize("lang", ["es", "en"])
def test_c15_a_group_made_by_conversation(directory_engine, check, lang, rep):  # noqa: F811
    p, _rows = directory_engine(lang)
    t0 = time.time()
    first = p.say(ASK[lang])
    p.settle_quiet(first.since, quiet_s=8, timeout=60)
    check.that("the first turn asks and creates nothing", not _members(p.eng.workspace, WORD[lang]),
               sorted(_members(p.eng.workspace, WORD[lang])))
    said, ids = WHO[lang]
    second = p.say(said)
    p.wait_for(lambda: _members(p.eng.workspace, WORD[lang]) >= set(ids), timeout=120, every=3)
    p.settle_quiet(second.since, quiet_s=8, timeout=60)
    got = _members(p.eng.workspace, WORD[lang])
    check.that("the group holds exactly the three he named", got == set(ids), {"got": sorted(got), "want": sorted(ids)})
    pending = contacts_seed.store_rows(p.eng.workspace, "mensajeria").get("pending_group") or []
    check.that("nothing mirrored and nothing sent", not pending and not sent_since(p, t0),
               {"pending_group": pending[:2], "sent": sent_since(p, t0)[:2]})
    check.done(expected_red=check.expected)
