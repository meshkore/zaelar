"""Un relevo automático se relanza «UNA vez» — y el contador vivía en el sitio que no cuenta.

MEDIDO en el motor del OPERADOR, no en un plató (`memory/_data/zaelar.db`, 2026-08-17): SEIS workers para una
sola búsqueda de coches.

    12:48:48  spawned id=1                       12:57:03  spawned id=3
    12:56:35  done    id=1  error  ($2.0897, 138155 tok, «context window limit»)
    12:56:43  spawned id=2   ← 8 s después       12:57:07  spawned id=4   ← con el 3 aún vivo
    12:57:00  done    id=2  error  ← 17 s        13:08:03  spawned id=5
                                                 13:08:26  spawned id=6

Dos clases de worker: los que trabajan (7m47s, 10m53s) y CUATRO cadáveres de ~17 s que nacen 3-8 s después de que
muera el anterior y mueren con el MISMO error. El primero se dejó dos dólares.

`_finish` tiene dos relevos automáticos —contexto agotado (compactar y continuar) y proveedor sin cuota— y los dos
se protegen con un booleano del RECORD (`context_retried`, `provider_retried`). Pero cada relevo crea un
`SessionRecord` NUEVO en `run_listener`, así que el booleano nace en False otra vez: el «UNA vez» del comentario
no acota la CADENA, solo el registro. `depth` tampoco contaba — viajaba en el contexto SIN incrementar.

Es la misma forma que el id de hoja que se reiniciaba con el proceso: un contador de instancia leído como si
fuera global. La diferencia es que aquí el error no es reintentable —una ventana de contexto llena no se
descongestiona por volver a intentarlo— así que el bucle gasta dinero real hasta que alguien lo mira.

Lo que se fija: que la generación VIAJE, que el tope corte, y que al cortar se diga la VERDAD. Esto último no es
adorno: sin la frase honesta, el resumen capado sigue llevando el error crudo y `operator_safe_summary` lo
traduce a «me he quedado sin espacio de contexto… LA RETOMO con lo que llevaba» — una promesa de reintento que ya
no va a ocurrir, con el operador esperando a nadie.
"""
import asyncio
import inspect

import pytest

from nucleo.workers.base import WorkerSpec
from nucleo.workers.session import SessionRecord, WorkerSession, _RELAY_CAP_DEFAULT


class _Backend:
    """`_finish` no habla con el backend: solo necesita existir para construir la sesión."""


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
    """Captura lo que se re-escala, sin publicar nada en el bus real."""
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


# ── 1) la generación tiene que VIAJAR ────────────────────────────────────────────────────────────────────────

def test_the_relay_carries_its_generation_forward(relevos):
    rec = _rec(gen=0, context_full={"tokens": 138155})
    asyncio.run(_sesion(rec)._finish())
    assert len(relevos) == 1, "el primer contexto agotado sí se retoma"
    assert relevos[0]["context"].get("relay_gen") == 1, \
        "sin generación en el contexto, el worker nuevo vuelve a empezar en cero y la cadena no acaba nunca"


def test_the_dispatcher_reads_it_back_at_the_only_door(relevos):
    """El otro filo del cable. `run_listener` es la ÚNICA puerta por la que pasan todas las escaladas; si no lo
    lee ahí, el campo viaja y se tira a la basura al construir el record."""
    from nucleo import dispatch
    src = inspect.getsource(dispatch.run_listener)
    assert 'relay_gen=int(ctx.get("relay_gen", 0) or 0)' in src


# ── 2) el tope corta ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_cap_is_a_small_number():
    """Pinned on purpose. La primera versión de este fichero usaba `_RELAY_CAP_DEFAULT` como entrada Y como
    referencia, así que subir el tope subía también el caso: con el tope en 999 los siete tests seguían VERDES.
    Un test que se mide contra la constante que vigila no vigila nada."""
    assert 1 <= _RELAY_CAP_DEFAULT <= 3, f"un tope de {_RELAY_CAP_DEFAULT} relanzamientos no es un tope"


def test_at_the_cap_the_chain_stops(relevos):
    rec = _rec(gen=_RELAY_CAP_DEFAULT, context_full={"tokens": 138155})
    asyncio.run(_sesion(rec)._finish())
    assert not relevos, f"en la generación {_RELAY_CAP_DEFAULT} la cadena tiene que parar, no relanzar"


def test_the_provider_relay_is_bounded_by_the_same_counter(relevos):
    """Las dos causas comparten tope a propósito: lo que se acota es la CADENA de relanzamientos de un encargo,
    no cada remedio por su lado. Un encargo que alterna las dos causas se relanzaría igual sin parar."""
    rec = _rec(gen=5, provider_down={"provider": "x", "next": "y", "text": "quota"})
    asyncio.run(_sesion(rec)._finish())
    assert not relevos


def test_under_the_cap_the_provider_relay_still_happens(relevos):
    rec = _rec(gen=0, provider_down={"provider": "x", "next": "y", "text": "quota"})
    asyncio.run(_sesion(rec)._finish())
    assert len(relevos) == 1 and relevos[0]["context"].get("relay_gen") == 1


# ── 3) y al cortar se dice la VERDAD ─────────────────────────────────────────────────────────────────────────

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
    """Un «no he podido» sin número no distingue «lo intenté una vez» de «me gasté dos dólares intentándolo»."""
    rec = _rec(gen=5, context_full={"tokens": 1})
    asyncio.run(_sesion(rec)._finish())
    assert "6 veces" in rec.result_summary, rec.result_summary
