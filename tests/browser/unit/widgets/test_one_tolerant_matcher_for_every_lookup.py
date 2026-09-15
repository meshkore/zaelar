"""V2-705 · ONE tolerant, intelligent matcher shared by contacts, calendar and messages.

The operator, 2026-09-15, verbatim: «las búsquedas de contactos y de datos internos deben funcionar con
algún poco de tolerancia… una C por una K, una letra que falta, una H… tiene que funcionar para cualquiera,
tanto para buscar contactos como para buscar una entrada en un calendario… localizar mensajes de ciertas
personas. Que sea flexible, preciso, pero inteligente.»

`widgets/textmatch.py` is that one primitive. These cases pin its tolerance and its refusals, and that the
three surfaces (the contacts door `directory.resolve`, the send door `outbound`, the agenda cancel matcher
`sweep`) all go through it — so a C for a K works the same whether you name a person, a meeting or a sender.
"""
from __future__ import annotations

import pytest

from widgets import textmatch as tm


# ── fold: the one comparison form ───────────────────────────────────────────────────────────────────────

def test_fold_strips_accents_case_and_punctuation():
    assert tm.fold("Crùz, José-Mª ") == "cruz jose ma"
    assert tm.fold("@Cryptonite_Fund!") == "cryptonite fund"
    assert tm.fold("") == "" and tm.fold(None) == ""


# ── spans: decoration peeled, most specific first ───────────────────────────────────────────────────────

def test_spans_peel_decoration_but_keep_the_whole_first():
    s = tm.spans("Kryptonite (Telegram @cryptonitefund)")
    assert s[0] == "Kryptonite (Telegram @cryptonitefund)" and "Kryptonite" in s


def test_spans_take_the_head_before_a_clause():
    assert "the dentist appointment" in tm.spans("the dentist appointment, the one on the 16th")


def test_a_span_of_only_filler_names_nothing():
    assert tm.spans("the meeting") == [] or all(tm.fold(x) != "the meeting" for x in tm.spans("the meeting"))


# ── score: tolerant by construction ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q,c,lo", [
    ("Kryptonite", "Cryptonite", 0.85),          # C for K
    ("Criptonait", "Cryptonite", 0.75),          # several letters off
    ("dentits", "Dentist", 0.8),                 # a transposition
    ("renovar seguro coche", "Renovar el seguro del coche", 0.9),   # dropped stopwords
    ("dentist", "Dentist appointment", 0.9),     # a slice
])
def test_a_real_reference_scores_over_the_floor(q, c, lo):
    assert tm.score(q, c) >= lo, (q, c, tm.score(q, c))


@pytest.mark.parametrize("q,c", [
    ("weather", "Cryptonite"),
    ("Napoleon", "Cryptonite"),
    ("the fund", "David Vera Construcción"),
])
def test_an_unrelated_reference_stays_below_the_floor(q, c):
    assert tm.score(q, c) < 0.72, (q, c, tm.score(q, c))


# ── rank and pick_one: shortlist vs commit ──────────────────────────────────────────────────────────────

def test_rank_returns_a_shortlist_best_first_and_nothing_below_the_floor():
    people = [{"n": "Cryptonite"}, {"n": "CryptoKnight"}, {"n": "David Vera"}]
    r = tm.rank("Kryptonite", people, key=lambda c: c["n"])
    assert r and r[0][1]["n"] == "Cryptonite"
    assert all(c["n"] != "David Vera" for _s, c in r), "an unrelated name is not in the shortlist"


def test_pick_one_commits_to_a_clear_winner_and_refuses_a_near_tie():
    people = [{"n": "Cryptonite"}, {"n": "CryptoKnight"}, {"n": "David Vera"}]
    assert tm.pick_one("Kryptonite", people, key=lambda c: c["n"])["n"] == "Cryptonite"
    # «Crypto» sits between the two crypto names — a tie the caller must ASK about, never a silent pick.
    assert tm.pick_one("Crypto", people, key=lambda c: c["n"]) is None


def test_an_exact_fold_wins_even_against_a_tie():
    people = [{"n": "Ana"}, {"n": "Ana Garcia"}]
    assert tm.pick_one("ana", people, key=lambda c: c["n"])["n"] == "Ana"


def test_no_match_is_a_real_answer():
    assert tm.rank("Napoleon", [{"n": "Cryptonite"}], key=lambda c: c["n"]) == []
    assert tm.pick_one("Napoleon", [{"n": "Cryptonite"}], key=lambda c: c["n"]) is None


# ── the three surfaces go through it ─────────────────────────────────────────────────────────────────────

def test_the_contacts_door_uses_the_shared_matcher():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/directory.py").read_text(encoding="utf-8")
    assert "textmatch" in src and "difflib" not in src.split("def resolve")[1][:1200], (
        "resolve must resolve through textmatch, not its own difflib block")


def test_the_agenda_cancel_matcher_uses_the_shared_matcher():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/agenda/sweep.py").read_text(encoding="utf-8")
    assert "textmatch" in src[src.index("def _matches("):src.index("def cancel_meeting(")]


def test_the_send_door_uses_the_shared_matcher():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/mensajeria/outbound.py").read_text(encoding="utf-8")
    assert "textmatch.spans" in src


def test_textmatch_is_stdlib_only():
    """It is imported by `widgets/*/data.py`, which is stdlib-only by contract."""
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/textmatch.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in {"__future__"}, node.module
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name in {"difflib", "re", "unicodedata"}, a.name
