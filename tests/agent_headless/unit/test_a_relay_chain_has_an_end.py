"""An automatic relay is relaunched «ONCE» — and the counter lived where it does not count.

MEASURED in the OPERATOR engine, not on a set (`memory/_data/zaelar.db`, 2026-08-17): SIX workers for a
single car search.

    12:48:48  spawned id=1                       12:57:03  spawned id=3
    12:56:35  done    id=1  error  ($2.0897, 138155 tok, «context window limit»)
    12:56:43  spawned id=2   ← 8 s después       12:57:07  spawned id=4   ← con el 3 aún vivo
    12:57:00  done    id=2  error  ← 17 s        13:08:03  spawned id=5
                                                 13:08:26  spawned id=6

Two kinds of worker: the ones that work (7m47s, 10m53s) and FOUR ~17-second corpses that are born 3–8 s after the
previous one dies and die with the SAME error. The first one cost two dollars.

`_finish` has two automatic relays — exhausted context (compact and continue) and provider out of quota — and both
are protected by a boolean on the RECORD (`context_retried`, `provider_retried`). But each relay creates a NEW
`SessionRecord` in `run_listener`, so the boolean is born False again: the «ONCE» in the comment does not bound the
CHAIN, only the record. `depth` did not count either — it traveled in the context WITHOUT being incremented.

It is the same pattern as the leaf ID that reset with the process: an instance counter read as though it were
global. The difference is that here the error is not retryable — a full context window does not clear by trying
again — so the loop spends real money until someone notices.

What is fixed: that the generation TRAVELS, that the cap cuts things off, and that the TRUTH is told when cutting
things off. The latter is not decoration: without the honest phrase, the capped summary still carries the raw error
and `operator_safe_summary` translates it to «I have run out of context space… I’LL RESUME IT with what I had» — a
retry promise that will no longer happen, leaving the operator waiting for no one.
"""
import asyncio
import inspect

import pytest

from nucleo.workers.base import WorkerSpec
from nucleo.workers.session import SessionRecord, WorkerSession, _RELAY_CAP_DEFAULT


class _Backend:
    """`_finish` does not talk to the backend: it only needs to exist to construct the session."""


def _sesion(rec: SessionRecord) -> WorkerSession:
    return WorkerSession(_Backend(), WorkerSpec(kind=rec.kind, task_id=rec.task_id), rec)


def _rec(gen: int = 0, **kw) -> SessionRecord:
    rec = SessionRecord(task_id="t", goal="busca coches de segunda mano diésel por menos de 12.000", kind="web")
    rec.relay_gen = gen
    for k, v in kw.items():
        setattr(rec, k, v)
    return rec


@pytest.fixture
def relevos(monkeypatch):
    """Capture what is re-escalated without publishing anything on the real bus."""
    vistos = []

    def _fake(request, context=None, **_kw):
        vistos.append({"request": request, "context": dict(context or {})})

    import nucleo.flash.escalate as _esc
    monkeypatch.setattr(_esc, "escalate_to_slowbrain", _fake)

    async def _no_deliver(_rec):
        return None
    import nucleo.workers.session as _s
    monkeypatch.setattr(_s, "_deliver", _no_deliver)
    return vistos


# ── 1) the generation has to TRAVEL ──────────────────────────────────────────────────────────────────────────

def test_the_relay_carries_its_generation_forward(relevos):
    rec = _rec(gen=0, context_full={"tokens": 138155})
    asyncio.run(_sesion(rec)._finish())
    assert len(relevos) == 1, "el primer contexto agotado sí se retoma"
    assert relevos[0]["context"].get("relay_gen") == 1, \
        "sin generación en el contexto, el worker nuevo vuelve a empezar en cero y la cadena no acaba nunca"


def test_the_dispatcher_reads_it_back_at_the_only_door(relevos):
    """The other end of the cable. `run_listener` is the ONLY door through which all escalations pass; if it does not
    read it there, the field travels and is thrown away when building the record."""
    from nucleo import dispatch
    src = inspect.getsource(dispatch.run_listener)
    assert 'relay_gen=int(ctx.get("relay_gen", 0) or 0)' in src


# ── 2) the cap cuts things off ───────────────────────────────────────────────────────────────────────────────

def test_the_cap_is_a_small_number():
    """Pinned on purpose. The first version of this file used `_RELAY_CAP_DEFAULT` as both input AND
    reference, so raising the cap also raised the case: with the cap at 999 all seven tests stayed GREEN.
    A test measured against the constant it watches guards nothing."""
    assert 1 <= _RELAY_CAP_DEFAULT <= 3, f"un tope de {_RELAY_CAP_DEFAULT} relanzamientos no es un tope"


def test_at_the_cap_the_chain_stops(relevos):
    rec = _rec(gen=_RELAY_CAP_DEFAULT, context_full={"tokens": 138155})
    asyncio.run(_sesion(rec)._finish())
    assert not relevos, f"en la generación {_RELAY_CAP_DEFAULT} la cadena tiene que parar, no relanzar"


def test_the_provider_relay_is_bounded_by_the_same_counter(relevos):
    """The two causes deliberately share a cap: what is bounded is the CHAIN of relaunches for a task,
    not each remedy separately. A task alternating between the two causes would otherwise relaunch forever."""
    rec = _rec(gen=5, provider_down={"provider": "x", "next": "y", "text": "quota"})
    asyncio.run(_sesion(rec)._finish())
    assert not relevos


def test_under_the_cap_the_provider_relay_still_happens(relevos):
    rec = _rec(gen=0, provider_down={"provider": "x", "next": "y", "text": "quota"})
    asyncio.run(_sesion(rec)._finish())
    assert len(relevos) == 1 and relevos[0]["context"].get("relay_gen") == 1


# ── 3) and when cutting off, the TRUTH is told ───────────────────────────────────────────────────────────────

def test_a_capped_chain_never_promises_a_retake(relevos):
    rec = _rec(gen=5, context_full={"tokens": 138155})
    rec.result_summary = "API Error: The model has reached its context window limit."
    asyncio.run(_sesion(rec)._finish())

    from nucleo.workers.session import operator_safe_summary
    dicho = operator_safe_summary(rec.result_summary)
    assert "retomo" not in dicho.lower(), f"le promete una retoma que no va a pasar: {dicho!r}"
    assert not rec.ok
    assert "partes" in dicho.lower(), "tiene que decirle QUÉ hacer, no solo que falló"


def test_the_capped_chain_says_how_many_times_it_tried(relevos):
    """A «I could not do it» without a number does not distinguish «I tried once» from «I spent two dollars trying»."""
    rec = _rec(gen=5, context_full={"tokens": 1})
    asyncio.run(_sesion(rec)._finish())
    assert "6 veces" in rec.result_summary, rec.result_summary
