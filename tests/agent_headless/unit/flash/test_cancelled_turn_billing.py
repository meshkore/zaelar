"""A CANCELLED turn still costs money — check it still gets metered (2026-08-14).

Session b70a45d0 cancelled **38 of 54 turns** (barge-in / the operator carrying on talking). Every one of those had
already sent its prompt to the provider and got tokens back, so every one is a real invoice line. The provider
charges for a request it served whether or not we bothered to read the end of the stream.

The trap is specific and easy to get wrong: **`usage` arrives in the LAST chunk of the stream**. A cancelled turn
never reaches it. So the naive shape

    async for chunk in stream: ...
    report(usage.prompt_tokens)        # ← never runs when cancelled

bills nothing for a turn that cost real money, and — worse — fails silently, which is how the four Energy holes of
2026-08-13 all worked. Nothing errors; the number just comes out low and nobody compares it with anything.

`fast_client.stream()` already gets this right (the reporting lives in a `finally`, and a char-based estimate is
seeded BEFORE the request so the fallback has something real to say). This file pins that, because it is a property
nobody would notice losing: a refactor that moves the reporting out of the `finally`, or drops the estimate seed,
breaks billing with every test still green.

Both branches are covered here — cancelled mid-stream (estimate) and a clean finish (provider truth) — because
"it reports something" is not the claim. The claim is that it reports the RIGHT source in each case.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import fast_client as fc


class _Delta:
    def __init__(self, content=None):
        self.content = content
        self.tool_calls = None


class _Choice:
    def __init__(self, content=None):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content=None, usage=None):
        self.choices = [_Choice(content)]
        self.usage = usage


class _Usage:
    def __init__(self, p, c):
        self.prompt_tokens = p
        self.completion_tokens = c
        self.total_tokens = p + c


class _Stream:
    """Stands in for the provider's SSE stream. `tail` is what happens after the text chunks: a final usage chunk
    (clean finish) or a hang the consumer cancels out of (barge-in)."""

    def __init__(self, chunks, hang=False):
        self._chunks = chunks
        self._hang = hang

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            yield c
        if self._hang:
            await asyncio.sleep(30)      # the consumer cancels here, exactly like a barge-in


@pytest.fixture
def spy(monkeypatch):
    """Captures what reaches Energy, and pins the provider so no request can leave the machine."""
    calls: list[dict] = []
    import nucleo.energy_meter as em
    monkeypatch.setattr(em, "report_llm_usage", lambda **kw: calls.append(kw))
    return calls


def _spec():
    return fc.ModelSpec(model="deepseek/deepseek-v4-flash", base_url="https://api.aimlapi.com/v1",
                        api_key="test", provider="aimlapi")


def _wire(monkeypatch, stream):
    class _Completions:
        async def create(self, **kw):
            return stream

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(fc.FastClient, "_client_for", lambda self, spec: _Client())


LONG = [{"role": "system", "content": "x" * 8000}, {"role": "user", "content": "vacía la agenda"}]


def test_un_turno_CANCELADO_a_media_respuesta_igual_se_contabiliza(monkeypatch, spy):
    """The 38 turns of the real session. No `usage` chunk ever arrives, so the estimate has to carry it."""
    _wire(monkeypatch, _Stream([_Chunk("Vale, "), _Chunk("ahora mismo")], hang=True))

    async def run():
        cli = fc.FastClient()
        m: dict = {}
        agen = cli.stream(LONG, spec=_spec(), metrics=m).__aiter__()
        assert await agen.__anext__() == "Vale, "        # the provider answered: real tokens are already spent
        await agen.aclose()                              # barge-in: the consumer walks away
        return m

    metrics = asyncio.run(run())

    assert spy, ("a cancelled turn reported NOTHING to Energy. The provider charged for it. Check the reporting is "
                 "still inside the `finally` of fast_client.stream().")
    got = spy[-1]
    assert (got.get("prompt_tokens") or 0) > 0, f"billed with no input tokens: {got}"
    # The estimate is what makes this possible, and it is seeded BEFORE the request precisely so a cancellation
    # still has a number. If this is None the fallback has nothing to fall back to.
    assert metrics.get("prompt_tokens_est"), "prompt_tokens_est not seeded before the request"
    assert metrics.get("usage_source") == "estimate"


def test_un_turno_COMPLETO_usa_los_tokens_REALES_del_proveedor(monkeypatch, spy):
    """The other branch: when the last chunk does arrive, provider truth must win over our estimate — otherwise the
    test above would be satisfied by a meter that always guesses."""
    _wire(monkeypatch, _Stream([_Chunk("Hecho."), _Chunk(None, usage=_Usage(9363, 42))]))

    async def run():
        cli = fc.FastClient()
        m: dict = {}
        async for _ in cli.stream(LONG, spec=_spec(), metrics=m):
            pass
        return m

    metrics = asyncio.run(run())

    assert metrics.get("usage_source") == "provider"
    assert metrics.get("prompt_tokens") == 9363
    assert spy[-1].get("prompt_tokens") == 9363, (
        f"provider usage arrived and the estimate was billed instead: {spy[-1]}")


def test_el_estimado_de_un_turno_cancelado_es_del_ORDEN_correcto(monkeypatch, spy):
    """A fallback that bills a token when the real cost was ten thousand is not billing, it is rounding to zero.

    The voice prompt is 9-10k tokens and the input dominates 14:1 in this brain, so the input estimate is what
    matters. Checked as an ORDER of magnitude, not a fixed number: it is a char-based estimate and pinning it
    exactly would just make the test brittle about the tokenizer.
    """
    _wire(monkeypatch, _Stream([_Chunk("Vale")], hang=True))

    async def run():
        cli = fc.FastClient()
        m: dict = {}
        agen = cli.stream(LONG, spec=_spec(), metrics=m).__aiter__()
        await agen.__anext__()
        await agen.aclose()
        return m

    asyncio.run(run())
    billed = spy[-1].get("prompt_tokens") or 0
    # ~8k chars of system prompt → order of thousands of tokens. A wrong-by-10x estimate fails here.
    assert 1000 <= billed <= 20000, f"input estimate out of order for an 8k-char prompt: {billed}"


def test_la_densidad_del_estimado_no_vuelve_al_valor_INGLES():
    """The constant is money, so it gets a guard.

    Measured over 114 real turns that carried both the provider's `usage` and their character counts, our input runs
    at **3.36 chars/token** — Spanish with accents plus the tools JSON. The 4.0 that used to be here is the English
    rule of thumb, and it under-billed every cancelled turn by 16%. Under-billing is the wrong direction on purpose
    (2026-08-13: «perder dinero por sub-cobrar es peor que sobre-cobrar un poco»), so the divisor must stay at or
    below the measured density.
    """
    assert fc._CHARS_PER_TOKEN <= 3.36, (
        f"_CHARS_PER_TOKEN={fc._CHARS_PER_TOKEN} over-estimates chars per token, which UNDER-bills every cancelled "
        f"turn. Measured density on real Spanish input is 3.36.")
    assert fc._CHARS_PER_TOKEN >= 2.5, (
        f"_CHARS_PER_TOKEN={fc._CHARS_PER_TOKEN} is far below the measured 3.36 — that over-bills a lot, and a "
        f"cost meter nobody trusts gets switched off.")
    # And the shape of the function itself: 30.019 chars was a real turn the provider billed at 8.870 tokens.
    est = fc.est_tokens(12684 + 17335)
    assert abs(est - 8870) / 8870 < 0.12, f"estimate {est} vs the provider's real 8870 for that same turn"
