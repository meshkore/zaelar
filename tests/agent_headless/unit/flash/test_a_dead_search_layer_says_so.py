"""An empty search and an IMPOSSIBLE search are not the same, and the turn must be able to distinguish them (V2-176).

Measured in `cheapest-monitor` (2026-08-20 10:26), ten turns:

    TESTER  Find me a good monitor for work that isn't terribly expensive.
    ZAELAR  I'll get on it and bring you a couple of well-priced options.
    ...
    TESTER  Can you give me a specific model with a price and store now, even if it's just a first option?
    ZAELAR  I don't have a specific model yet; the search is reviewing the catalog and hasn't returned any
            candidates yet. Do you want me to stop it or continue?
    TESTER  Keep going, please.
    ZAELAR  Done, I'll let you know right away.

Twenty search events, zero candidates, and the watchdog firing `stuck/nudge` as it went. The search chain was
DOWN (quota exhausted plus a CAPTCHA), so the RESULT was unreachable—and the only thing that was, reporting it,
wasn't either: `websearch.search()` returns `results: []` with `source: "none"` when the entire chain fails, which
is indistinguishable from “I searched properly and found nothing.” The only trace of the collapse was a
`logger.warning`.

Same remedy as on the LLM side (`provider_chain.note_failure` + `health_state.record`): the layer records its
own health and the turn reads it. And it states the REASON, not a generic one: “the quota has run out” and “I'm
being asked for a captcha” lead the operator to different decisions, and neither of them is to wait.
"""
from __future__ import annotations

import pytest

from nucleo import websearch


@pytest.fixture(autouse=True)
def _clean():
    websearch.note_success()
    yield
    websearch.note_success()


# ── the layer remembers its own collapse ─────────────────────────────────────────────────────────────────────
def test_a_healthy_layer_says_nothing():
    assert websearch.recent_failure() == {}


def test_a_collapsed_chain_is_remembered():
    websearch.note_failure("google: Weekly Limit Exhausted · ddg: sin resultados")
    assert websearch.recent_failure()


def test_and_a_backend_answering_clears_it():
    """Without this, an isolated failure would leave the agent saying “I can't search” for the rest of the session."""
    websearch.note_failure("google: timeout")
    websearch.note_success()
    assert websearch.recent_failure() == {}


def test_it_forgets_on_its_own_after_a_while():
    """A fact must expire: the quota renews and the CAPTCHA goes away, and nobody calls `note_success` if
    nobody searches again."""
    websearch.note_failure("google: unusual traffic")
    at = websearch.recent_failure()["at"]
    assert websearch.recent_failure(now=at + websearch._FAILURE_MEMORY_S + 1) == {}


@pytest.mark.parametrize("detail,kind", [
    ("google: Weekly Limit Exhausted", "quota"),
    ("brave: 429 too many requests", "quota"),
    ("google: unusual traffic detected", "captcha"),
    ("google: /sorry/index?continue=", "captcha"),
    ("tavily: 401 unauthorized", "credential"),
    ("perplexity: invalid api key", "credential"),
    ("ddg: connection timed out", "network"),
    ("google: algo raro pasó", "error"),
])
def test_the_reason_is_classified_because_the_reasons_lead_somewhere_different(detail, kind):
    websearch.note_failure(detail)
    assert websearch.recent_failure()["kind"] == kind


def test_the_operator_semaphore_is_lit(monkeypatch):
    """“Visible state, not silent”: a failed search layer shown in green is indistinguishable from an agent
    that does not want to search, and the operator debugs the wrong thing."""
    seen: list[tuple] = []
    from voice import health_state
    monkeypatch.setattr(health_state, "record", lambda *a, **kw: seen.append(a))
    websearch.note_failure("google: Weekly Limit Exhausted")
    assert seen and seen[0][0] == "search"


# ── and it reaches the TURN, which was what was missing ────────────────────────────────────────────────────────
def _state() -> str:
    from nucleo.flash import prompt
    return prompt.live_state()


def test_the_turn_is_told_that_it_cannot_look(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_failure("google: Weekly Limit Exhausted")
    st = _state()
    assert "BÚSQUEDAS WEB NO ESTÁN FUNCIONANDO" in st


def test_it_says_WHICH_reason(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_failure("google: unusual traffic detected")
    assert "anti-robot" in _state()
    websearch.note_success()
    websearch.note_failure("google: Weekly Limit Exhausted")
    assert "cuota" in _state()


def test_and_it_forbids_the_exact_sentence_the_run_kept_saying(monkeypatch):
    """The measured harm was not keeping the fact quiet: it was promising “I'll let you know as soon as I have it”
    about something that was never going to arrive. The instruction must target THAT sentence, not merely inform."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_failure("google: Weekly Limit Exhausted")
    st = _state()
    assert "en cuanto lo tenga" in st, "no se nombra la promesa que hay que dejar de hacer"
    assert "navegador" in st, "se prohíbe esperar sin ofrecer nada a cambio"


def test_a_healthy_layer_puts_NOTHING_in_the_turn(monkeypatch):
    """The other half: without this, “report when the search is down” and “always report” pass the same test—and
    an agent that says it cannot search when it can is worse than the original defect."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_success()
    assert "BÚSQUEDAS WEB NO ESTÁN FUNCIONANDO" not in _state()


def test_the_chain_records_its_own_collapse(monkeypatch):
    """The safeguard that matters: that `search()` CALLS `note_failure`. A record that nobody writes is a dead fix
    —this batch has already produced several."""
    monkeypatch.setattr(websearch, "_order", lambda: ["ddg"])
    monkeypatch.setitem(websearch._BACKENDS, "ddg",
                        lambda q, k: (_ for _ in ()).throw(RuntimeError("Weekly Limit Exhausted")))
    res = websearch.search("monitor para trabajar")
    assert res["source"] == "none" and not res["results"]
    f = websearch.recent_failure()
    assert f and f["kind"] == "quota"
    assert "ddg" in f["detail"], "el registro no dice qué backend cayó"


def test_and_a_backend_that_answers_leaves_the_layer_healthy(monkeypatch):
    monkeypatch.setattr(websearch, "_order", lambda: ["ddg"])
    monkeypatch.setitem(websearch._BACKENDS, "ddg",
                        lambda q, k: {"query": q, "answer": "", "results": [{"title": "t", "snippet": "s",
                                                                            "url": "https://x.test"}],
                                      "source": "ddg", "ai": False})
    websearch.note_failure("google: timeout")
    websearch.search("monitor")
    assert websearch.recent_failure() == {}
