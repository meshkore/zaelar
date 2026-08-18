"""tests/memory/e2e/bot/distiller_tape.py — la cinta del destilador (V2-114 F1).

Lo que se prueba, y por qué cada caso existe:

- Grabar NO cambia el comportamiento: la corrida grabada tiene que seguir siendo válida, o grabar el fixture
  contaminaría la medición que lo produce.
- Los TRES retornos de `process()` se conservan (`None` / `[]` / `[átomos]`): son ramas distintas del llamador
  (`None` cae a la heurística, `[]` es un descarte legítimo), y una cinta que los confunda replicaría un
  camino de escritura que nunca ocurrió.
- El REINTENTO se reproduce. `memory_agent` reintenta una vez tras un `None` (V2-103), así que una frase puede
  generar dos llamadas. Es exactamente el motivo de que la cinta sea SECUENCIAL y no un dict texto→píldoras:
  este test falla con la implementación de diccionario.
- Un texto ausente degrada a la heurística (o lanza en `strict`), y queda CONTADO — una cobertura parcial
  silenciosa daría un número que parece bueno y no es comparable.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import mem_processor
from tests.memory.e2e.bot import distiller_tape as tape


def test_record_delegates_and_preserves_all_three_return_shapes(tmp_path, monkeypatch):
    """Grabar tiene que ser transparente: mismos valores devueltos que el original, y los tres tipos escritos
    al fixture tal cual (incluido `None`, que NO es lo mismo que `[]`)."""
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
    """El caso que obliga a que la cinta sea secuencial: la MISMA frase produce dos llamadas porque el
    llamador reintenta tras un `None`. Una cinta indexada por texto devolvería el `None` las dos veces y
    el reintento nunca se recuperaría."""
    secuencia = [None, [{"text": "Se llama Nala."}]]

    async def _fake(text, *, state=None):
        return secuencia.pop(0)

    monkeypatch.setattr(mem_processor, "process", _fake)
    fixture = tmp_path / "t.jsonl"

    async def _grabar():
        with tape.record(fixture):
            primero = await mem_processor.process("mi perra se llama Nala")
            segundo = await mem_processor.process("mi perra se llama Nala")   # el reintento de V2-103
            return primero, segundo

    assert asyncio.run(_grabar()) == (None, [{"text": "Se llama Nala."}])

    async def _replicar():
        with tape.replay(fixture):
            return (await mem_processor.process("mi perra se llama Nala"),
                    await mem_processor.process("mi perra se llama Nala"))

    assert asyncio.run(_replicar()) == (None, [{"text": "Se llama Nala."}]), \
        "la cinta debe devolver None y LUEGO las píldoras, igual que al grabar"


def test_replay_forces_enabled_so_the_retry_path_stays_reachable(tmp_path):
    """`memory_agent` solo reintenta si `mem_processor.enabled()`. Al replicar no hay clave ni endpoint, así
    que sin forzarlo el reintento grabado sería inalcanzable y el camino de escritura divergiría."""
    fixture = tmp_path / "t.jsonl"
    fixture.write_text('{"i":0,"text":"x","atoms":null}\n', encoding="utf-8")

    antes = mem_processor.enabled

    async def _run():
        with tape.replay(fixture):
            return mem_processor.enabled()

    assert asyncio.run(_run()) is True
    # Y se restaura al SALIR: un `enabled()` forzado que se quedara pegado al proceso haría creer al resto de
    # la suite (y a una corrida real posterior en el mismo proceso) que el CORAZÓN está vivo sin estarlo.
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
    """Replicar un SUBRANGO desplaza las posiciones. La cinta debe encontrar la frase igualmente, pero
    contarlo — para que una corrida desordenada no se presente como una réplica exacta."""
    fixture = tmp_path / "t.jsonl"
    fixture.write_text('{"i":0,"text":"a","atoms":[]}\n'
                       '{"i":1,"text":"b","atoms":[{"text":"B"}]}\n', encoding="utf-8")

    async def _run():
        with tape.replay(fixture) as t:
            got = await mem_processor.process("b")      # se salta "a"
            return got, t.stats()

    got, st = asyncio.run(_run())
    assert got == [{"text": "B"}]
    assert st["out_of_order"] == 1 and st["misses"] == 0
