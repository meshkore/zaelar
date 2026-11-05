"""V2-854 F0 · the contacts test set stands on a SYNTHETIC directory with the shape of the real one.

The cases of this folder are only as good as the directory they run on: a fixture of six tidy people proves the
resolver on six tidy people. So the fixture is held to the proportions measured on a real ~2 900-entry directory
(`directory_fixture` docstring) — and to carrying nothing that could reach anybody.
"""
from __future__ import annotations

import collections
import re

from . import directory_fixture as fx


def _people(rows):
    return [r for r in rows if r.get("kind") != "group"]


def _first(r) -> str:
    return fx._fold(r["name"]).split(" ")[0]


def test_it_is_deterministic():
    assert fx.build(now=1.8e9) == fx.build(now=1.8e9)


def test_people_and_groups_in_the_measured_proportion():
    rows = fx.build()
    groups = [r for r in rows if r.get("kind") == "group"]
    assert 250 <= len(rows) <= 500, "a few hundred rows: big enough for namesakes, small enough for a unit test"
    assert 0.03 <= len(groups) / len(rows) <= 0.09
    assert all(g.get("platform") == "whatsapp" and g["channels"][0]["chatId"].endswith("@g.us") for g in groups)
    assert sum(1 for r in rows if r.get("kind") == "company") >= 1


def test_how_people_are_reached_follows_the_real_mix():
    ppl = _people(fx.build())
    has_tel = [bool(r["phone"]) for r in ppl]
    has_mail = [bool(r["email"]) for r in ppl]
    has_ch = [bool(r["channels"]) for r in ppl]
    phone_only = sum(t and not m for t, m in zip(has_tel, has_mail)) / len(ppl)
    mail_only = sum(m and not t for t, m in zip(has_tel, has_mail)) / len(ppl)
    unclassified = [r for r, t, m, c in zip(ppl, has_tel, has_mail, has_ch) if not (t or m or c)]
    assert 0.45 <= phone_only <= 0.70 and 0.25 <= mail_only <= 0.45, (phone_only, mail_only)
    assert unclassified, "the people with no phone, no e-mail and no channel are part of the shape"
    lids = [ch for r in ppl for ch in r["channels"] if ch["platform"] == "whatsapp"]
    assert lids and all(ch["chatId"].endswith("@lid") for ch in lids), "his WhatsApp chats are linked ids, not phones"
    assert any(ch["platform"] == "telegram" for r in ppl for ch in r["channels"])


def test_names_are_as_untidy_as_real_ones():
    ppl = _people(fx.build())
    words = collections.Counter(min(len(r["name"].split()), 4) for r in ppl)
    assert words[1] / len(ppl) >= 0.15 and words[4] / len(ppl) >= 0.10, words
    assert sum(r["name"] == r["name"].lower() for r in ppl) / len(ppl) >= 0.10
    assert any("." in r["name"] and " " not in r["name"] for r in ppl), "an e-mail-only person named like the address"
    first = collections.Counter(_first(r) for r in ppl)
    shared = sum(n for n in first.values() if n >= 2) / len(ppl)
    assert shared >= 0.40, f"most people share their first word with someone ({shared:.0%})"


def test_where_confusion_lives_is_in_it():
    rows = fx.build()
    by_id = {r["id"]: r for r in rows}
    raquels = [r for r in _people(rows) if "raquel" in fx._fold(r["name"]).replace(".", " ").split()]
    assert len(raquels) >= 9 and not by_id["fav-rakel"]["name"].lower().startswith("raquel")
    assert by_id["fav-rakel"]["favorite"] and by_id["fav-helena"]["favorite"] and by_id["fav-katherine"]["favorite"]
    assert by_id["rakel-mail"]["email"] and not by_id["rakel-mail"]["phone"], "one person split across two records"
    tels = collections.Counter(r["phone"] for r in _people(rows) if r["phone"])
    mails = collections.Counter(r["email"] for r in _people(rows) if r["email"])
    assert any(n > 1 for n in tels.values()) and any(n > 1 for n in mails.values()), "records sharing a phone/e-mail"


def test_nothing_in_it_can_reach_anybody():
    for r in fx.build():
        if r["phone"]:
            assert re.fullmatch(r"\+44 7700 900\d{3}", r["phone"]), r["phone"]
        if r["email"]:
            assert re.fullmatch(r"[^@\s]+@example\.(com|net|org)", r["email"]), r["email"]
        for ch in r["channels"]:
            assert re.fullmatch(r"(9000000000\d{5}@lid|1203630000000\d{5}@g\.us|khale_fx)", ch["chatId"]), ch
