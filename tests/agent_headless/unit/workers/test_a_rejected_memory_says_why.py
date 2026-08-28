"""Al worker le decían «HTTP Error 422» y el servidor SÍ decía por qué.

Medido el 2026-08-28 sobre las rondas del plató 24/7: **cinco** intentos del worker de guardar hallazgos
operativos murieron con «HTTP Error 422: Unprocessable Entity» y nada más —

    Wallapop filtro que funciona: es.wallapop.com/search?category_id=100&max_sale_price=8000&order_b…
    Milanuncios bloqueado por anti-bot; Wallapop ok co…
    coches.net da error persistente («Ups! Algo no va bien») en cualquier…
    Facebook Marketplace requiere login en el navegador del operador…

— que es exactamente el conocimiento que evita que el siguiente worker repita el trabajo. El servidor
responde `descartado por el gate de precisión (<razón>)` en el CUERPO, y `urllib.error.HTTPError` solo trae el
número: el worker reintenta o se rinde a ciegas.

Esto NO afloja el gate. Aflojarlo es una decisión sobre la calidad de la memoria y necesita saber primero QUÉ
está rechazando — que es lo que esto hace posible.
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
    """Un servidor que no explica no puede dejar al worker peor que antes."""
    _falla(500, None, monkeypatch)
    with pytest.raises(RuntimeError) as e:
        mem_cli._post("/api/memory/remember", {"text": "x"})
    assert "500" in str(e.value)


def test_una_respuesta_BUENA_sigue_pasando(monkeypatch):
    """La mitad de sensibilidad: envolver los errores no puede romper el camino sano."""
    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true, "id": 7}'
    monkeypatch.setattr(mem_cli.urllib.request, "urlopen", lambda *_a, **_k: _R())
    assert mem_cli._post("/api/memory/remember", {"text": "x"}) == {"ok": True, "id": 7}


def test_NO_afloja_el_gate():
    """La decisión de qué entra en memoria no cambia aquí. Esto solo hace legible el rechazo — y aflojar el
    gate sin saber qué rechaza sería exactamente el error que este repo lleva toda la noche pagando."""
    from pathlib import Path
    src = Path("server/memory_routes.py").read_text(encoding="utf-8")
    assert 'raise HTTPException(422, f"descartado por el gate de precisión' in src


def test_un_cuerpo_ILEGIBLE_no_empeora_el_error(monkeypatch):
    """Leer el cuerpo es un extra: si falla, el worker tiene que seguir recibiendo el código y no una
    excepción distinta encima. Un fallo al EXPLICAR un fallo deja al que lee peor que si no se hubiera
    intentado."""
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
