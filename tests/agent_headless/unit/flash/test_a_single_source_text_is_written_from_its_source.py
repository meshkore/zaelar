"""A text written from ONE known source reads that source first, through the search service (V2-831 T-26).

Demo F1, «write me a one page summary of the bitcoin whitepaper, in a document», went to a Brain Worker: plan,
search, several fetches, sections — 274-629 s. One look-up (`search.find`, 4.4 s on the whitepaper) and one written
answer do it. The composer used to write «from your own knowledge» only; it now gets the source's notes, bounded by
`SOURCE_TIMEOUT_S`, and without them writes as before.

Disarm: drop `_source_notes` from `compose` → red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace


def _patch(monkeypatch, answer="Section 4, Proof-of-Work: a hash beginning with zero bits."):
    seen = {}
    import search
    from nucleo.flash import second_pass
    monkeypatch.setattr(search, "find", lambda q, **k: SimpleNamespace(
        answer=answer, provider="gemini", pages=[SimpleNamespace(url="https://bitcoin.org/bitcoin.pdf")], sources=[]))

    async def collect(sys2, user, spec, max_tokens=0):
        seen["user"] = user
        return "## Proof of work\\nNodes vote with CPU power."
    monkeypatch.setattr(second_pass, "collect", collect)
    return seen


def test_the_text_is_written_from_its_looked_up_source(monkeypatch):
    seen = _patch(monkeypatch)
    from nucleo.flash import compose_rung
    body = asyncio.run(compose_rung.compose({"title": "Bitcoin whitepaper — one-page summary", "brief": "one page"},
                                            "write me a one page summary of the bitcoin whitepaper", None))
    assert body and "SOURCE NOTES" in seen["user"] and "zero bits" in seen["user"], seen.get("user", "")[:400]
    assert "bitcoin.org/bitcoin.pdf" in seen["user"]


def test_no_source_still_writes_from_what_the_model_knows(monkeypatch):
    seen = _patch(monkeypatch, answer="")
    from nucleo.flash import compose_rung
    body = asyncio.run(compose_rung.compose({"title": "A letter", "brief": "thank-you note"}, "write a thank-you note",
                                            None))
    assert body and "SOURCE NOTES" not in seen["user"]
