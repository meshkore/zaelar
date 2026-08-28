"""`payload JSON inválido` es la anomalía nº 1 de TODO el tablero, y no decía nada.

Contadas el 2026-08-28 sobre las 44 filas del marcador: **18 apariciones** de
`worker/task «↩ zaelar ⚠️ error»: Exit code N payload JSON inválido`, más del **doble** que la siguiente
firma. El mensaje era literalmente eso: ni qué tenía de inválido, ni qué se había leído. Un worker no puede
arreglar lo que no sabe que escribió mal, así que reintenta igual — el rastro de esas rondas son tres y
cuatro intentos idénticos seguidos.

Dos cosas distintas, y las dos hacían falta:

  · **Tolerar la valla de markdown.** A un modelo al que le pides «escribe un JSON» le sale ```json … ``` sin
    pensarlo, porque es como escribe JSON en todas partes. No es ambiguo —una valla tiene una sola lectura—,
    así que rechazarlo no protege de nada: solo gasta una vuelta entera.
  · **Decir QUÉ falló.** El parser da línea, columna y motivo, y lo tirábamos.

Lo que NO se tolera: comillas simples, comas de más ni ningún otro «casi JSON». Eso sí es ambiguo, y un parser
indulgente acabaría ejecutando lo que el worker no dijo — que es peor que rechazarlo.
"""
from __future__ import annotations

from nucleo import bridge_usage as BU

_VALLA = "```json\n{\"accion\": \"buscar\", \"q\": \"hoteles\"}\n```"


def test_un_json_normal_pasa_igual():
    d, err = BU.parse_payload('{"a": 1}')
    assert d == {"a": 1} and err == ""


def test_la_valla_de_markdown_se_tolera():
    d, err = BU.parse_payload(_VALLA)
    assert d == {"accion": "buscar", "q": "hoteles"} and err == ""


def test_tambien_la_valla_sin_idioma():
    d, err = BU.parse_payload("```\n{\"a\": 1}\n```")
    assert d == {"a": 1} and err == ""


def test_un_json_ROTO_dice_linea_columna_y_motivo():
    """«Inválido» a secas es lo que hace que el worker reintente lo mismo tres veces."""
    _, err = BU.parse_payload('{"a": 1,}')
    assert "line 1" in err and "column" in err
    assert "empieza por" in err and '{"a": 1,}' in err


def test_el_casi_json_NO_se_arregla_solo():
    """La mitad de sensibilidad, y la que importa: un parser indulgente ejecuta lo que el worker no dijo."""
    for casi in ("{'a': 1}", '{"a": 1,}', "{a: 1}"):
        d, err = BU.parse_payload(casi)
        assert d == {} and err, casi


def test_una_lista_no_es_un_payload():
    """`act` espera un objeto. Devolver `{}` en silencio mandaría una acción vacía como si fuera buena."""
    d, err = BU.parse_payload("[1, 2]")
    assert d == {} and "no un objeto" in err and "list" in err


def test_vacio_es_un_payload_vacio_y_no_un_error():
    """`act` sin payload es legítimo — no todo comando lleva argumentos."""
    assert BU.parse_payload("") == ({}, "")
    assert BU.parse_payload("   ") == ({}, "")


def test_el_puente_lo_USA_y_enseña_el_motivo():
    """La fontanería: sin esto la clasificación existe y el worker sigue leyendo «inválido» a secas."""
    from pathlib import Path
    src = Path("nucleo/worker_bridge.py").read_text(encoding="utf-8")
    assert "_bu.parse_payload(_raw)" in src
    assert 'payload JSON inválido ({_src}): {_perr}' in src


# ── V2-469 · un texto plano para web_search ES la query ──────────────────────────────────────────────────
def test_una_query_pelada_para_web_search_es_la_query():
    """Medido en `cheapest-monitor__us` (00:14): el worker llamó `act web_search` con el payload siendo la
    query pelada («LG 27US500-W 27 inch 4K monitor price») — lo natural, la familia de V2-341 — y perdió
    el turno con «payload JSON inválido». Para una acción cuyo payload es exactamente {"query": …}, un
    texto plano no tiene otra lectura. Vive en `bare_query_payload`, que decide UNA vez para el CLI."""
    d = BU.bare_query_payload("web_search", "LG 27US500-W 27 inch 4K monitor price")
    assert d == {"query": "LG 27US500-W 27 inch 4K monitor price"}


def test_otra_accion_con_texto_plano_sigue_siendo_error():
    """Convertir texto plano para una acción con estructura inventaría el payload — eso sí es ambiguo."""
    assert BU.bare_query_payload("push_channel", "mándale esto a Marc") is None


def test_un_json_roto_no_se_convierte_en_query():
    """Un texto que EMPIEZA como JSON y no parsea es un JSON mal escrito, no una query: convertirlo
    ejecutaría una búsqueda con las llaves dentro."""
    assert BU.bare_query_payload("web_search", '{"query": "hoteles"') is None


def test_el_cli_cablea_la_conversion():
    """Guarda de cableado: los tres de arriba pasan enteros con la llamada del CLI borrada."""
    from pathlib import Path
    src = Path("nucleo/worker_bridge.py").read_text(encoding="utf-8")
    assert "bare_query_payload" in src
