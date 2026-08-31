"""The worker was told «HTTP Error 422», and the server DID say why.

Measured on 2026-08-28 during the 24/7 set's rounds: **five** attempts by the worker to save operational
findings died with «HTTP Error 422: Unprocessable Entity» and nothing else —

    Wallapop filtro que funciona: es.wallapop.com/search?category_id=100&max_sale_price=8000&order_b…
    Milanuncios bloqueado por anti-bot; Wallapop ok co…
    coches.net da error persistente («Ups! Algo no va bien») en cualquier…
    Facebook Marketplace requiere login en el navegador del operador…

— which is exactly the knowledge that keeps the next worker from repeating the work. The server responds
`descartado por el gate de precisión (<razón>)` in the BODY, while `urllib.error.HTTPError` only carries the
number: the worker retries or gives up blindly.

This does NOT loosen the gate. Loosening it is a decision about memory quality and first requires knowing WHAT
it is rejecting — which is what this makes possible.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from nucleo import mem_cli


def _falla(codigo: int, cuerpo: dict | None, monkeypatch):
    def _urlopen(*_a, **_k):
        raise urllib.error.HTTPError(
            "http://x/api/memory/remember", codigo, "Unprocessable Entity", {},
            io.BytesIO(json.dumps(cuerpo).encode()) if cuerpo is not None else io.BytesIO(b""))
    monkeypatch.setattr(mem_cli.urllib.request, "urlopen", _urlopen)


def test_el_MOTIVO_del_servidor_llega_al_worker(monkeypatch):
    _falla(422, {"detail": "descartado por el gate de precisión (pregunta reificada)"}, monkeypatch)
    with pytest.raises(RuntimeError) as e:
        mem_cli._post("/api/memory/remember", {"text": "x"})
    assert "422" in str(e.value) and "gate de precisión" in str(e.value)
    assert "pregunta reificada" in str(e.value), "sin la razón concreta no se puede corregir el hallazgo"


def test_sin_cuerpo_se_dice_al_menos_el_QUÉ(monkeypatch):
    """A server that does not explain cannot leave the worker worse off than before."""
    _falla(500, None, monkeypatch)
    with pytest.raises(RuntimeError) as e:
        mem_cli._post("/api/memory/remember", {"text": "x"})
    assert "500" in str(e.value)


def test_una_respuesta_BUENA_sigue_pasando(monkeypatch):
    """The sensitivity half: wrapping errors must not break the healthy path."""
    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true, "id": 7}'
    monkeypatch.setattr(mem_cli.urllib.request, "urlopen", lambda *_a, **_k: _R())
    assert mem_cli._post("/api/memory/remember", {"text": "x"}) == {"ok": True, "id": 7}


def test_NO_afloja_el_gate():
    """The decision about what enters memory does not change here. This only makes the rejection readable — and
    loosening the gate without knowing what it rejects would be exactly the mistake this repo has been paying for all night."""
    from pathlib import Path
    src = Path("server/memory_routes.py").read_text(encoding="utf-8")
    assert 'raise HTTPException(422, f"descartado por el gate de precisión' in src


def test_un_cuerpo_ILEGIBLE_no_empeora_el_error(monkeypatch):
    """Reading the body is an extra: if it fails, the worker must continue receiving the code and not a different
    exception on top of it. A failure to EXPLAIN a failure leaves the reader worse off than if it had not been
    attempted."""
    class _Rota(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("http://x", 422, "Unprocessable Entity", {}, None)
        def read(self, *_a, **_k):
            raise OSError("socket cerrado")
    def _urlopen(*_a, **_k):
        raise _Rota()
    monkeypatch.setattr(mem_cli.urllib.request, "urlopen", _urlopen)
    with pytest.raises(RuntimeError) as e:
        mem_cli._post("/api/memory/remember", {"text": "x"})
    assert "422" in str(e.value)
