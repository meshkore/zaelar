"""tests/memory/e2e/bot/distiller_tape.py — the distiller tape (V2-114 F1).

What is tested, and why each case exists:

- Recording does NOT change behavior: the recorded run must remain valid, or recording the fixture would
  contaminate the measurement that produces it.
- All THREE `process()` return values are preserved (`None` / `[]` / `[atoms]`): they are distinct caller
  branches (`None` falls back to the heuristic, `[]` is a legitimate discard), and a tape that confused them
  would reproduce a write path that never occurred.
- The RETRY is reproduced. `memory_agent` retries once after a `None` (V2-103), so one phrase can generate two
  calls. This is precisely why the tape is SEQUENTIAL rather than a text→pills dict: this test fails with the
  dictionary implementation.
- A missing text falls back to the heuristic (or raises in `strict`), and is COUNTED — silent partial coverage
  would produce a number that looks good but is not comparable.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import mem_processor
from tests.memory.e2e.bot import distiller_tape as tape


def test_record_delegates_and_preserves_all_three_return_shapes(tmp_path, monkeypatch):
    """Recording must be transparent: the same values returned as by the original, and all three types written
    to the fixture exactly as they are (including `None`, which is NOT the same as `[]`)."""
    guion = {"con datos": [{"text": "Vive en Girona."}], "trivial": [], "caido": None}

    async def _fake(text, *, state=None):
        return guion[text]

    monkeypatch.setattr(mem_processor, "process", _fake)
    fixture = tmp_path / "t.jsonl"

    async def _run():
        out = []
        with tape.record(fixture):
            for k in ("con datos", "trivial", "caido"):
                out.append(await mem_processor.process(k))
        return out

    devuelto = asyncio.run(_run())
    assert devuelto == [[{"text": "Vive en Girona."}], [], None], \
        "grabar no puede alterar lo que el llamador recibe"

    t = tape._Tape(fixture)
    assert t.load() == 3
    assert [e["atoms"] for e in t.entries] == [[{"text": "Vive en Girona."}], [], None], \
        "los tres tipos deben sobrevivir al viaje por JSONL sin colapsar entre sí"


def test_replay_needs_no_network_and_reproduces_the_recorded_decisions(tmp_path, monkeypatch):
    llamadas = {"n": 0}

    async def _fake(text, *, state=None):
        llamadas["n"] += 1
        return [{"text": f"destilado de {text}"}]

    monkeypatch.setattr(mem_processor, "process", _fake)
    fixture = tmp_path / "t.jsonl"

    async def _grabar():
        with tape.record(fixture):
            for k in ("uno", "dos"):
                await mem_processor.process(k)

    asyncio.run(_grabar())
    assert llamadas["n"] == 2

    async def _replicar():
        with tape.replay(fixture) as t:
            a = await mem_processor.process("uno")
            b = await mem_processor.process("dos")
            return a, b, t.stats()

    a, b, st = asyncio.run(_replicar())
    assert llamadas["n"] == 2, "replicar NO puede volver a llamar al destilador real (cero red es el punto)"
    assert a == [{"text": "destilado de uno"}] and b == [{"text": "destilado de dos"}]
    assert st["hits"] == 2 and st["misses"] == 0 and st["coverage"] == 1.0


def test_sequential_tape_reproduces_the_retry_after_a_none(tmp_path, monkeypatch):
    """The case that requires the tape to be sequential: the SAME phrase produces two calls because the
    caller retries after a `None`. A tape indexed by text would return `None` both times and the retry would
    never recover."""
    secuencia = [None, [{"text": "Se llama Nala."}]]

    async def _fake(text, *, state=None):
        return secuencia.pop(0)

    monkeypatch.setattr(mem_processor, "process", _fake)
    fixture = tmp_path / "t.jsonl"

    async def _grabar():
        with tape.record(fixture):
            primero = await mem_processor.process("mi perra se llama Nala")
            segundo = await mem_processor.process("mi perra se llama Nala")   # the V2-103 retry
            return primero, segundo

    assert asyncio.run(_grabar()) == (None, [{"text": "Se llama Nala."}])

    async def _replicar():
        with tape.replay(fixture):
            return (await mem_processor.process("mi perra se llama Nala"),
                    await mem_processor.process("mi perra se llama Nala"))

    assert asyncio.run(_replicar()) == (None, [{"text": "Se llama Nala."}]), \
        "la cinta debe devolver None y LUEGO las píldoras, igual que al grabar"


def test_replay_forces_enabled_so_the_retry_path_stays_reachable(tmp_path):
    """`memory_agent` retries only if `mem_processor.enabled()`. During replay there is no key or endpoint, so
    without forcing it, the recorded retry would be unreachable and the write path would diverge."""
    fixture = tmp_path / "t.jsonl"
    fixture.write_text('{"i":0,"text":"x","atoms":null}\n', encoding="utf-8")

    antes = mem_processor.enabled

    async def _run():
        with tape.replay(fixture):
            return mem_processor.enabled()

    assert asyncio.run(_run()) is True
    # It is also restored on EXIT: a forced `enabled()` that remained stuck on the process would make the rest
    # of the suite (and a subsequent real run in the same process) believe the CORE is alive when it is not.
    assert mem_processor.enabled is antes, "replay() debe devolver enabled() a su implementación original"


def test_a_missing_phrase_is_counted_and_degrades_instead_of_lying(tmp_path):
    fixture = tmp_path / "t.jsonl"
    fixture.write_text('{"i":0,"text":"conocida","atoms":[{"text":"ok"}]}\n', encoding="utf-8")

    async def _run():
        with tape.replay(fixture) as t:
            fuera = await mem_processor.process("frase que no estaba en el corpus")
            return fuera, t.stats()

    fuera, st = asyncio.run(_run())
    assert fuera is None, "sin entrada en la cinta se degrada a la heurística, no se inventan píldoras"
    assert st["misses"] == 1 and st["coverage"] < 1.0, "una cobertura parcial tiene que ser VISIBLE"


def test_strict_mode_refuses_to_measure_with_an_incomplete_fixture(tmp_path):
    fixture = tmp_path / "t.jsonl"
    fixture.write_text('{"i":0,"text":"conocida","atoms":[]}\n', encoding="utf-8")

    async def _run():
        with tape.replay(fixture, strict=True):
            await mem_processor.process("ausente")

    with pytest.raises(AssertionError, match="incomplete fixture coverage"):
        asyncio.run(_run())


def test_out_of_order_lookup_finds_the_phrase_and_flags_it(tmp_path):
    """Replaying a SUBRANGE shifts the positions. The tape must still find the phrase, but COUNT it — so that
    an out-of-order run is not presented as an exact replay."""
    fixture = tmp_path / "t.jsonl"
    fixture.write_text('{"i":0,"text":"a","atoms":[]}\n'
                       '{"i":1,"text":"b","atoms":[{"text":"B"}]}\n', encoding="utf-8")

    async def _run():
        with tape.replay(fixture) as t:
            got = await mem_processor.process("b")      # skips "a"
            return got, t.stats()

    got, st = asyncio.run(_run())
    assert got == [{"text": "B"}]
    assert st["out_of_order"] == 1 and st["misses"] == 0
