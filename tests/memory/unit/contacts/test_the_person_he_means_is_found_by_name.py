"""V2-854 F0 · WHO a name means, on a directory shaped like his — the baseline writer a's resolver turns green.

Each case is said two ways — TYPED (capitals, accents) and VOICE-SHAPED (what the transcript hands over: lowercase,
no accents, a near spelling, a compound split in two) — in Spanish and in English, and asks `widgets/directory.resolve`
the one question every door asks. The RED ones on the base (`28cde8a25`) are strict xfails naming the phase that
fixes them: the ladder stops at the first rung that matches, so a BACKGROUND namesake hides the CIRCLE person a near
spelling would have found — and a one-word background row named exactly «raquel» wins outright over his favorite.
"""
from __future__ import annotations

import pytest

F2 = pytest.mark.xfail(strict=True, reason="V2-854 F2: one ranking — match strength x closeness, not a ladder that "
                                            "stops at the first rung")


def _ids(rows) -> list[str]:
    return [r["id"] for r in rows]


# ── a CIRCLE person with a near spelling among background namesakes resolves alone ───────────────────────────────

@F2
@pytest.mark.parametrize("said", ["Raquel", "raquel", "Raquél"], ids=["typed", "voice", "accent"])
def test_his_favorite_with_a_near_spelling_resolves_alone_among_nine_namesakes(directory_world, said):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == ["fav-rakel"]


@F2
@pytest.mark.parametrize("said", ["Catherine", "catherine"], ids=["typed", "voice"])
def test_a_c_for_a_k_finds_his_favorite_among_five_namesakes(directory_world, said):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == ["fav-katherine"]


@pytest.mark.parametrize("said", ["Elena", "elena"], ids=["typed", "voice"])
def test_a_silent_h_finds_his_favorite(directory_world, said):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == ["fav-helena"]


@pytest.mark.parametrize("said", ["Rakel", "rakel"], ids=["typed", "voice"])
def test_her_own_spelling_finds_her(directory_world, said):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == ["fav-rakel"]


# ── the person he talks to this week comes first, even spelt the other way ───────────────────────────────────────

@F2
@pytest.mark.parametrize("said,first", [("Jordi", "active-jordy"), ("jordi", "active-jordy"),
                                        ("John", "active-jon"), ("john", "active-jon")],
                         ids=["es-typed", "es-voice", "en-typed", "en-voice"])
def test_a_recent_conversation_with_a_near_spelling_comes_first(directory_world, said, first):
    _cd, d, _rows = directory_world
    hits = _ids(d.resolve(said))
    assert hits and hits[0] == first, hits


# ── a name in quotes is searched LITERALLY ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ['"Raquel"', "«Raquel»"], ids=["straight", "angled"])
def test_a_quoted_name_is_literal_and_never_a_near_spelling(directory_world, said):
    _cd, d, rows = directory_world
    hits = _ids(d.resolve(said))
    literal = {r["id"] for r in rows if r.get("kind") != "group" and "raquel" in r["name"].lower().replace(".", " ").split()}
    assert hits and set(hits) <= literal and "fav-rakel" not in hits, hits


@pytest.mark.parametrize("said", ['"Rakel"', "«Rakel»"], ids=["straight", "angled"])
def test_a_quoted_spelling_finds_exactly_that_spelling(directory_world, said):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == ["fav-rakel"]


# ── compound names, said split or joined ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ["Maricarmen", "mari carmen"], ids=["typed", "voice-split"])
def test_a_compound_first_name_said_split_finds_her(directory_world, said):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == ["mother-maricarmen"]


# ── a company and a person ───────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,who", [("Ferretería Ortiz", "company-ortiz"), ("ferreteria ortiz", "company-ortiz"),
                                      ("Marta Ortiz", "ortiz-1"), ("Thorne Plumbing", "company-thorne"),
                                      ("amy thorne", "thorne-1")],
                         ids=["es-company-typed", "es-company-voice", "es-person", "en-company", "en-person"])
def test_a_company_and_a_person_who_share_a_word_are_told_apart(directory_world, said, who):
    _cd, d, _rows = directory_world
    assert _ids(d.resolve(said)) == [who]


@pytest.mark.parametrize("said,both", [("Ortiz", {"company-ortiz", "ortiz-1"}), ("Thorne", {"company-thorne", "thorne-1"})],
                         ids=["es", "en"])
def test_the_shared_word_alone_is_a_question_that_names_the_company_too(directory_world, said, both):
    _cd, d, _rows = directory_world
    hits = set(_ids(d.resolve(said)))
    assert both <= hits and len(hits) > 1


# ── the card's read door answers from the same resolution ────────────────────────────────────────────────────────

@F2
@pytest.mark.parametrize("q,name", [("¿qué teléfono tiene Raquel?", "Rakel Ibarz"),
                                    ("what's Catherine's username?", "Katherine Hale")], ids=["es", "en"])
def test_a_question_about_her_is_answered_with_her_record(directory_world, q, name):
    from widgets.contactos.lookup import read_query
    answer = read_query(q)
    lines = answer.splitlines()
    assert len(lines) > 1 and name in lines[1], answer
