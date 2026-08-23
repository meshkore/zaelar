"""The local reranker's first load is a 1.1 GB DOWNLOAD — and no recall may wait for it (2026-08-23).

The trap this closes was live on the operator's own machine: `config/v2.py` ships `rerank_provider: "local"`,
both wizard profiles write the same, `fastembed` is installed (it is in requirements.txt) — and the model was
not in any cache. `TextCrossEncoder(...)` downloads synchronously with no timeout of its own, so the first LONG
recall of the first real turn would have blocked on a gigabyte of network, inside a voice turn, while
`rerank.status()` cheerfully reported `available: True`.

Three separate failures, and the tests below own one each:

  1. **Waiting.** The download may happen; a caller may not wait for it. Budget exceeded → `rank()` returns
     None and the recall goes out unranked, exactly as with no provider at all.
  2. **Forgetting.** A load that fails for good used to be retried from scratch on EVERY call.
  3. **Lying.** `available` answered "is fastembed importable", which is not the question anyone asking it has.

The distinction that carries the design: a TIMEOUT must not be sticky (it fixes itself when the bytes land) and
a hard failure must be. Both directions are asserted — a sticky timeout would leave the reranker permanently off
after one slow morning, which is the same silent quality loss with the opposite cause."""
from __future__ import annotations

import threading
import time

import pytest

from memory import rerank, rerank_local


@pytest.fixture(autouse=True)
def _clean_state():
    rerank_local.reset()
    yield
    rerank_local.reset()


class _FakeEncoder:
    def rerank(self, query, texts):
        # el ÚLTIMO texto es el "mejor" → una permutación inequívoca, invertida respecto al orden de entrada
        return [float(i) for i in range(len(texts))]


def _install_loader(monkeypatch, factory):
    """Replace the class `_load_into` imports, counting how many times a load is actually attempted."""
    import fastembed.rerank.cross_encoder as ce
    calls: list[str] = []

    def _ctor(model_name=None, **kw):
        calls.append(model_name)
        return factory(model_name)

    monkeypatch.setattr(ce, "TextCrossEncoder", _ctor)
    return calls


def test_una_descarga_lenta_no_bloquea_el_recall(monkeypatch):
    """El presupuesto se respeta y el recall sale SIN reordenar, no colgado."""
    arrancada = threading.Event()

    def _lentisimo(_model):
        arrancada.set()
        time.sleep(30)          # el hilo es daemon: la suite no lo espera
        return _FakeEncoder()

    _install_loader(monkeypatch, _lentisimo)
    monkeypatch.setenv("MEMORY_RERANK_LOAD_BUDGET_S", "0.3")

    t0 = time.monotonic()
    out = rerank_local.rank("¿dónde vivo?", ["vivo en soria", "tengo un perro"])
    dt = time.monotonic() - t0

    assert out is None, "sin modelo listo se devuelve None (fail-open), nunca un orden inventado"
    assert dt < 5.0, f"el recall esperó {dt:.1f}s a una descarga: el presupuesto no se está aplicando"
    assert arrancada.is_set(), "la carga TIENE que haber arrancado — se rinde el que espera, no la descarga"
    assert rerank_local.loading() is True
    assert rerank_local.gave_up() is None, "un timeout NO es una rendición: se arregla solo cuando lleguen los bytes"
    assert rerank_local.ready() is False


def test_cuando_la_descarga_termina_el_reranker_se_engancha_solo(monkeypatch):
    """La otra mitad: rendirse una vez no puede significar renunciar para siempre."""
    puerta = threading.Event()

    def _bloqueado(_model):
        puerta.wait(10)
        return _FakeEncoder()

    calls = _install_loader(monkeypatch, _bloqueado)
    monkeypatch.setenv("MEMORY_RERANK_LOAD_BUDGET_S", "0.2")

    assert rerank_local.rank("q", ["a", "b"]) is None      # primer intento: aún cargando
    puerta.set()                                            # "termina la descarga"
    deadline = time.monotonic() + 5
    while rerank_local.loading() and time.monotonic() < deadline:
        time.sleep(0.02)

    out = rerank_local.rank("q", ["a", "b"])
    assert out is not None, "con el modelo ya cargado, la siguiente llamada TIENE que reordenar"
    assert [i for i, _ in out] == [1, 0]
    assert rerank_local.ready() is True
    assert len(calls) == 1, "no se relanza la descarga por cada llamada; se reaprovecha el hilo en vuelo"


def test_un_fallo_duro_se_recuerda_y_no_se_reintenta_en_cada_llamada(monkeypatch):
    """Antes, una máquina que no puede servir este modelo pagaba el fallo en CADA recall."""
    def _revienta(_model):
        raise RuntimeError("modelo inexistente")

    calls = _install_loader(monkeypatch, _revienta)
    monkeypatch.setenv("MEMORY_RERANK_LOAD_BUDGET_S", "5")

    for _ in range(4):
        assert rerank_local.rank("q", ["a", "b"]) is None

    assert len(calls) == 1, f"se reintentó la carga {len(calls)} veces: la rendición no se recuerda"
    assert "modelo inexistente" in (rerank_local.gave_up() or ""), "y el motivo tiene que quedar legible"


def test_status_distingue_listo_de_meramente_instalado(monkeypatch):
    """`available` decía True con fastembed importable y CERO modelo en disco — la mentira que empezó todo."""
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "local"})

    st = rerank.status()
    assert st["available"] is True, "fastembed está instalado: el proveedor está cableado"
    assert st["ready"] is False, "pero NADA se ha reordenado todavía — y eso tiene que verse"
    assert st["loading"] is False
    assert st["gave_up"] is None


def test_tras_una_rendicion_dura_el_proveedor_deja_de_declararse_disponible(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "local"})
    _install_loader(monkeypatch, lambda _m: (_ for _ in ()).throw(RuntimeError("sin disco")))
    monkeypatch.setenv("MEMORY_RERANK_LOAD_BUDGET_S", "5")

    rerank_local.rank("q", ["a", "b"])
    st = rerank.status()
    assert st["available"] is False, "un modelo escrito como imposible no puede seguir contando como disponible"
    assert st["ready"] is False
    assert "sin disco" in (st["gave_up"] or "")


def test_off_no_carga_nada(monkeypatch):
    """El proveedor apagado no puede tocar el cargador ni de refilón."""
    calls = _install_loader(monkeypatch, lambda _m: _FakeEncoder())
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "off"})
    rerank.rerank("q", [{"text": "a", "score": 1.0}, {"text": "b", "score": 0.5}])
    assert calls == []
