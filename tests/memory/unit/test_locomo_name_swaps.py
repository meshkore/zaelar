"""LoCoMo's «adversarial» category asks about the WRONG PERSON — and keeps the right person's answer (2026-08-19).

Found by re-measuring the temporal anchor and getting a result that looked like a regression: every category that
measures memory went UP while cat 5 fell 31.9% -> 14.9%. Chasing the 9 lost questions to the source dialogue showed
why, and it is not our bug:

    cat 4  "What activity did Caroline used to do with her dad?"   gold: Horseback riding   ev: D13:7
    cat 5  "What activity did Melanie  used to do with her dad?"   gold: Horseback riding   ev: D13:7

Caroline is the one who said it (`session_13`). The cat-5 twin swaps the name and keeps the gold AND the evidence
pointer, so the only way to score on it is to ignore who is being asked about. **8 of the 9 questions we "lost"
were twins of exactly this shape**: the run before had a vague pill («She attended a transgender poetry
reading…») that let the answerer attach it to whoever the question named; resolving the pronoun to «Caroline» made
the answerer correctly refuse a question about Melanie — and that scores as WRONG.

Measured across the whole set: **427 of 446 cat-5 questions (96%)**, and 100% in 7 of the 10 conversations. Cat 5
is ~22% of LoCoMo's 1,986 questions, so a fifth of any published overall figure — ours or a competitor's — rewards
mis-attribution. This is the guard that stops the finding from decaying back into "our adversarial score dropped".
"""
from __future__ import annotations

import json
import pathlib

import pytest

from tests.memory.benchmarks.locomo import adapter as A

_DATA = pathlib.Path("/private/tmp/claude-501/locomo10.json")


# ── the logic, on a fixture: deterministic, no dataset, no network ─────────────────────────────────────────────
def _conv(qa: list[dict]) -> dict:
    return {"qa": qa}


def test_a_cat5_sharing_gold_AND_evidence_with_a_cat4_is_a_twin():
    conv = _conv([
        {"category": 4, "question": "What activity did Caroline do with her dad?",
         "answer": "Horseback riding", "evidence": ["D13:7"]},
        {"category": 5, "question": "What activity did Melanie did with her dad?",
         "adversarial_answer": "Horseback riding", "evidence": ["D13:7"]},
    ])
    assert A.name_swap_twins(conv) == {"What activity did Melanie did with her dad?"}


def test_a_cat5_with_its_OWN_answer_is_not_a_twin():
    """A genuinely adversarial question — one whose gold is not borrowed from a single-hop question — is a real
    test and must keep counting. Excluding all of cat 5 by category would have thrown these away too."""
    conv = _conv([
        {"category": 4, "question": "Where does Caroline live?", "answer": "Madrid", "evidence": ["D2:1"]},
        {"category": 5, "question": "What car does Caroline drive?",
         "adversarial_answer": "Not mentioned in the conversation", "evidence": ["D9:4"]},
    ])
    assert A.name_swap_twins(conv) == set()


def test_matching_needs_the_EVIDENCE_too_not_just_the_gold():
    """Short golds repeat across a conversation («yes», «her family», a year). Matching on the answer alone would
    pair questions that have nothing to do with each other and quietly delete real coverage."""
    conv = _conv([
        {"category": 4, "question": "Did Caroline enjoy the race?", "answer": "yes", "evidence": ["D3:1"]},
        {"category": 5, "question": "Did Melanie enjoy the concert?", "adversarial_answer": "yes",
         "evidence": ["D8:2"]},
    ])
    assert A.name_swap_twins(conv) == set()


def test_a_cat4_without_evidence_never_seeds_a_match():
    conv = _conv([
        {"category": 4, "question": "Who is Caroline?", "answer": "a friend", "evidence": []},
        {"category": 5, "question": "Who is Melanie?", "adversarial_answer": "a friend", "evidence": []},
    ])
    assert A.name_swap_twins(conv) == set()


def test_an_empty_conversation_is_handled():
    assert A.name_swap_twins({}) == set()
    assert A.name_swap_twins({"qa": []}) == set()


# ── the CLAIM, against the real dataset when it is on this machine ─────────────────────────────────────────────
@pytest.mark.skipif(not _DATA.exists(), reason="LoCoMo-10 no está en esta máquina (no se commitea: 2,8 MB)")
def test_the_96_percent_claim_holds_against_the_real_dataset():
    """The number this whole finding rests on. It is asserted rather than remembered so that a future reader does
    not have to take my word for it — and so that a change to the matcher that quietly stops matching announces
    itself here instead of in a benchmark result nobody can explain."""
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    total5 = sum(1 for c in data for q in (c.get("qa") or []) if q.get("category") == 5)
    twins = sum(len(A.name_swap_twins(c)) for c in data)
    assert total5 == 446, f"el dataset cambió: {total5} preguntas cat-5"
    assert twins >= 420, f"solo {twins}/{total5} gemelas — ¿el matcher dejó de casar?"
    assert twins / total5 > 0.9
