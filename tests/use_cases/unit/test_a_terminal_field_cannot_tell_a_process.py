"""Un campo TERMINAL no puede contar un PROCESO — y un cero no dice por qué es cero (V2-512).

Nace de dos errores del 2026-08-30 cometidos con horas de diferencia y la misma forma, los dos ya camino de
otro agente cuando se cazaron:

1. El informe publicaba `navegador_task.url`, que es el ÚLTIMO url. Con eso escribí que el agente «se quedó en
   la portada de Amazon sin buscar». Había pasado por `amazon.com/s?k=27+inch+4k+monitor` —la página de
   resultados correcta— dos pasos antes, y por Best Buy después: 19 páginas en total.
2. `search_health` decía `degraded: false` mientras `bhphotovideo.com/c/search` devolvía 403 con página
   anti-robot (verificado con `curl`). Así que «no encontró nada» y «no le dejaron entrar» llegaban al juez
   como el mismo hecho.

Lo que se fija aquí no es el detector: es que el RECORRIDO viaje entero y que un muro se diga como muro.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, paginas):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms REAL, payload TEXT)")
    for i, (titulo, url) in enumerate(paginas):
        payload = json.dumps({"kind": "navegador", "label": "🧭 página", "text": f"{titulo} · {url}"})
        con.execute("INSERT INTO events (ts_ms, payload) VALUES (?,?)", (1000.0 + i, payload))
    con.commit()
    con.close()
    return str(p)


def test_el_recorrido_viaja_ENTERO_no_solo_donde_acabo(tmp_path):
    db = _db(tmp_path, [
        ("Amazon.com. Spend less. Smile more.", "https://www.amazon.com/"),
        ("Amazon.com : 27 inch 4k monitor", "https://www.amazon.com/s?k=27+inch+4k+monitor"),
        ("Best Buy | Official Online Store", "https://www.bestbuy.com/"),
    ])
    j = verify.page_journey(db)
    assert j["n_pages"] == 3
    urls = [p["url"] for p in j["pages"]]
    assert "https://www.amazon.com/s?k=27+inch+4k+monitor" in urls, (
        "la página de resultados no viaja — con solo la última, «buscó» y «no buscó» se leen igual")
    assert urls[-1].startswith("https://www.bestbuy.com"), "el orden importa: es un recorrido, no un conjunto"


@pytest.mark.parametrize("titulo", ["Page Not Found", "Access Denied", "Robot Check", "403 Forbidden",
                                   "Are you a human?", "Too Many Requests 429"])
def test_un_muro_se_dice_como_MURO(tmp_path, titulo):
    """El título lo dice en cuatro palabras; el cuerpo de un muro son 5 KB de HTML que no dicen nada.

    NO se fija CUÁL de los patrones casa: «403 Forbidden» casa con dos y cuál gana es el orden de una tupla,
    un detalle de implementación. Lo que tiene que cumplirse es la propiedad — que el motivo publicado esté
    de verdad en el título, para que quien lea el informe pueda comprobarlo sin abrir el código.
    """
    db = _db(tmp_path, [("Amazon.com : monitores", "https://www.amazon.com/s?k=x"), (titulo, "https://x.test/y")])
    j = verify.page_journey(db)
    assert j["n_walls"] == 1
    assert j["walls"][0]["why"] in titulo.lower(), "el motivo publicado no está en el título que lo provocó"
    assert j["walls"][0]["url"] == "https://x.test/y"


def test_una_pagina_SANA_no_es_un_muro(tmp_path):
    """El contrapeso, sin el cual esto es «marcar todo como bloqueado»: una ronda que fue bien no puede salir
    con puertas cerradas, o el juez aprende a ignorar el aviso."""
    db = _db(tmp_path, [("Amazon.com : 27 inch 4k monitor", "https://www.amazon.com/s?k=x"),
                        ("Best Buy | Official Online Store", "https://www.bestbuy.com/")])
    j = verify.page_journey(db)
    assert j["n_walls"] == 0 and j["walls"] == []


def test_la_misma_pagina_repetida_seguida_no_es_un_paso_nuevo(tmp_path):
    db = _db(tmp_path, [("Amazon", "https://a.test/"), ("Amazon", "https://a.test/"), ("Otra", "https://b.test/")])
    assert verify.page_journey(db)["n_pages"] == 2


def test_sin_base_no_INVENTA_un_recorrido(tmp_path):
    """`read: False` es la respuesta honesta. Un recorrido vacío que no se distingue de «no lo pude leer» es
    cómo una ausencia se lee como un hecho."""
    j = verify.page_journey(str(tmp_path / "no-existe.db"))
    assert j["read"] is False and j["n_pages"] == 0


def test_el_juez_recibe_el_MURO_y_la_orden_de_no_puntuarlo(tmp_path):
    from tests.use_cases.e2e.agent.judge import mechanism_facts

    txt = mechanism_facts({"page_journey": {"read": True, "n_pages": 4, "n_walls": 1,
                                            "pages": [{"title": "x", "url": "u"}],
                                            "walls": [{"title": "Access Denied", "url": "u", "why": "access denied"}]}})
    assert "CERRÓ" in txt and "Access Denied" in txt
    assert "NO es del producto" in txt, "sin esto, el juez puntúa un 403 como que el worker buscó mal"
    assert "RECORRIDO" in txt, "y tiene que saber que la última página no resume lo que hizo"
