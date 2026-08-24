"""Lo que la ÚLTIMA barrida del navegador deja en la hoja tiene que llegar a la conversación.

Medido por el arnés el 2026-08-24 en tres casos (guitarra 49 s, hotel 42 s, vuelos 113 s): las filas entraban en
la hoja DECENAS DE SEGUNDOS antes del último turno y el agente seguía diciendo «todavía no tengo nada».

La causa es estructural y no es un olvido puntual. `results.intake.push` es la puerta ÚNICA de las filas
(V2-257) pero NO lleva nota: la nota la empuja el llamante. De los tres llamantes, dos la empujan
(`act_api._hand_over`, `owner.py`) y el tercero —`dispatch._finalize_web`, que hace su propia extracción final
cuando el worker termina o muere— escribía las filas y no decía nada.

La otra mitad, y por eso el test la fija igual de fuerte: NO puede contarlo dos veces. Si la extracción de esa
pestaña ya salió por la nota de `_hand_over`, la barrida final es casi la misma página otra vez, y una segunda
nota se lee como «ha encontrado más» cuando ha encontrado lo mismo.
"""
from __future__ import annotations

import pytest

from nucleo.workers import findings
from widgets.navegador import act_api


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    empujadas = []
    monkeypatch.setattr("voice.brain_notes.push", lambda t: empujadas.append(t), raising=False)
    monkeypatch.setattr(act_api, "_HANDED", {})
    monkeypatch.setattr(findings, "_HANDED", {})
    yield empujadas


FILAS = [{"title": "Fender Stratocaster", "price": "450 €", "url": "https://x/1"},
         {"title": "Gibson Les Paul", "price": "900 €", "url": "https://x/2"}]


def test_la_barrida_final_lo_cuenta(_limpio):
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra de segunda mano") is True
    assert len(_limpio) == 1
    nota = _limpio[0]
    assert "Fender Stratocaster" in nota and "450 €" in nota, "la nota no nombra lo que encontró"
    assert "guitarra" in nota, "la nota no dice de qué encargo habla"


def test_no_lo_cuenta_DOS_veces_si_ya_salio_por_la_otra_puerta(_limpio):
    """`act_api._HANDED` marca las pestañas cuya extracción ya salió como nota. La condición es sobre la
    PESTAÑA y no sobre estas filas a propósito: la barrida final es casi la misma página otra vez."""
    act_api._HANDED["nav1"] = "una-firma-cualquiera"
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra") is False
    assert _limpio == []


def test_una_pestana_DISTINTA_no_queda_callada_por_la_de_al_lado(_limpio):
    """El defecto simétrico: mirar el diccionario entero en vez de ESTA pestaña dejaría mudo un encargo porque
    otro, en paralelo, ya habló."""
    act_api._HANDED["otra"] = "firma"
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra") is True


def test_sin_filas_no_se_dice_nada(_limpio):
    """Una nota que dice «he terminado y no traigo nada» ya la da el cierre del worker. Aquí, callarse."""
    assert findings.hand_sheet_finding("nav1", [], "una guitarra") is False
    assert findings.hand_sheet_finding("nav1", [{"nada": "util"}], "una guitarra") is False
    assert _limpio == []


def test_dice_cuantas_MAS_hay_sin_soltarlas_todas(_limpio):
    """La nota entra en el prompt del turno: van tres y se dice cuántas quedan. Perder en silencio la
    información de que había más es la doctrina de `observability/evidence.py`."""
    muchas = FILAS + [{"title": f"Guitarra {i}", "price": "100 €"} for i in range(5)]
    findings.hand_sheet_finding("nav1", muchas, "una guitarra")
    assert "y 4 más" in _limpio[0], _limpio[0]


def test_si_no_puede_saber_si_ya_se_contó_lo_cuenta(monkeypatch, _limpio):
    """Fail-soft con criterio: no poder mirar el marcador no puede significar callarse. Una nota repetida es
    ruido; una nota que falta es el operador esperando delante de una hoja llena."""
    import builtins
    real = builtins.__import__

    def _boom(name, *a, **k):
        if name == "widgets.navegador.act_api":
            raise RuntimeError("no disponible")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _boom)
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra") is True


# ── el CABLEADO: que `_finalize_web` la llame ────────────────────────────────────────────────────────────────

def test_finalize_web_llama_a_la_nota_justo_donde_escribe_las_filas():
    """Guarda de cableado por AST. La función puede estar perfecta y no servir de nada si el único camino que
    la necesitaba no la llama — que es literalmente el defecto que arregla."""
    import ast
    src = ast.parse(open("nucleo/dispatch.py", encoding="utf8").read())
    fn = next(n for n in ast.walk(src)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_finalize_web")
    llamadas = [getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(fn) if isinstance(c, ast.Call)]
    assert "push" in llamadas, "…¿ya no entrega a la hoja?"
    assert "hand_sheet_finding" in llamadas, \
        "`_finalize_web` escribe las filas en la hoja y no se lo cuenta a nadie: el operador las tiene delante " \
        "y el agente sigue diciendo que no hay nada"
