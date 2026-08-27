"""El JSON no cabía en la línea de comandos, y el puente no sabía leerlo de un fichero (V2-379).

Medido en `best-rated-rental-car__es` (2026-08-27, 2/5). El rastro del worker se lee de corrido:

    63,5 s  ⚠️ Contains brace with quote character (expansion obfuscation)   ← NUESTRA puerta bloquea el JSON
    67,6 s  ✏️ escribe 24316c-1/search.json                                  ← el worker inventa el rodeo
    69,2 s  ⚠️ Exit code 1 payload JSON inválido                             ← y el puente no lee ficheros
    73,1 s  usage: worker_bridge act …                                       ← a ciegas
    77,5 s  usage: worker_bridge act …                                       ← otra vez
    85,1 s  ✏️ escribe 24316c-1/use_tool.json                                ← y otra

Ocho errores internos y CERO resultados del navegador. El worker dio con la solución correcta él solo
—escribir el JSON a un fichero— y le dijimos que no.

`act` es por donde el worker PIDE una búsqueda, así que cerrado ahí se queda ciego. Y la convención YA existía
en el otro puente: `widget_cli` acepta `@fichero` y `-` desde V2-203. Un puente la tenía y el otro no.

El MECANISMO se comparte (misma razón que `bridge_usage.guided`): dos lectores de payload se separan y
entonces uno acepta `@fichero` y el otro no, que es exactamente el estado del que se sale. El MENSAJE lo pone
cada puente, porque qué hacer con un fichero que falta depende de quién pregunta.
"""
import json
import os

import pytest

from nucleo import bridge_usage as BU
from nucleo import worker_bridge as WB


# ── el lector compartido ───────────────────────────────────────────────────────────────────────────────────

def test_un_payload_en_LINEA_pasa_tal_cual():
    raw, src, err = BU.read_payload('{"tool":"web_search"}')
    assert raw == '{"tool":"web_search"}' and src == "argumento" and not err


def test_el_rodeo_por_FICHERO_que_el_worker_inventó_ya_funciona(tmp_path):
    f = tmp_path / "search.json"
    f.write_text('{"tool":"web_search","args":{"query":"alquiler coche Málaga"}}', encoding="utf-8")
    raw, src, err = BU.read_payload(f"@{f}")
    assert not err
    assert json.loads(raw)["args"]["query"] == "alquiler coche Málaga"
    assert str(f) in src


def test_un_fichero_que_NO_está_devuelve_el_error_sin_reventar():
    raw, src, err = BU.read_payload("@no-existe-jamas.json")
    assert raw == "" and err and "no-existe-jamas.json" in src


def test_la_entrada_estandar_tambien(monkeypatch):
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"a":1}'))
    raw, src, err = BU.read_payload("-")
    assert raw == '{"a":1}' and src == "stdin" and not err


def test_sin_payload_no_es_un_error():
    """`act` con acción y sin payload es legítimo — no todas las acciones llevan datos."""
    assert BU.read_payload("") == ("", "argumento", "")


# ── el puente lo usa de verdad ─────────────────────────────────────────────────────────────────────────────

def test_el_puente_LEE_el_fichero_y_no_dice_JSON_invalido(tmp_path, monkeypatch, capsys):
    """El cableado: el lector puede ser perfecto y no estar enchufado, que es el estado del que se sale."""
    f = tmp_path / "busqueda.json"
    f.write_text('{"tool":"web_search","args":{"query":"coches"}}', encoding="utf-8")
    monkeypatch.setenv("ZAELAR_TASK_ID", "t1")
    monkeypatch.setenv("ZAELAR_TASK_TOKEN", "tok")
    visto = {}
    monkeypatch.setattr(WB, "_post", lambda path, body: visto.update(body) or {"ok": True})
    assert WB._cmd_act("use_tool", f"@{f}") == 0
    assert visto["payload"]["args"]["query"] == "coches", "el JSON del fichero no llegó al servidor"
    assert visto["action"] == "use_tool"


def test_un_fichero_AUSENTE_dice_donde_mira_y_que_hacer(tmp_path, monkeypatch, capsys):
    """V2-203 en este puente: un mensaje sin salida es un mensaje que para al worker."""
    monkeypatch.setenv("ZAELAR_TASK_ID", "t1")
    assert WB._cmd_act("use_tool", "@no-existe.json") == 1
    err = capsys.readouterr().err
    assert "no puedo leer el payload de no-existe.json" in err
    assert os.getcwd() in err
    assert "DOS pasos" in err


def test_un_JSON_ROTO_dice_DE_DONDE_venia(tmp_path, monkeypatch, capsys):
    """«payload JSON inválido» a secas no distingue un argumento mal escrito de un fichero mal escrito, y son
    dos arreglos distintos."""
    f = tmp_path / "roto.json"
    f.write_text("{esto no es json", encoding="utf-8")
    monkeypatch.setenv("ZAELAR_TASK_ID", "t1")
    assert WB._cmd_act("use_tool", f"@{f}") == 1
    assert "fichero" in capsys.readouterr().err


# ── y se le ENSEÑA la salida ───────────────────────────────────────────────────────────────────────────────

def test_la_pista_de_act_nombra_el_rodeo_por_fichero():
    """Una capacidad que el worker no sabe que tiene no existe (V2-249). Y la pista nombra el error EXACTO que
    le van a devolver, que es con lo que puede casarlo."""
    p = WB._hint_for("worker_bridge act")
    assert "brace with quote" in p
    assert "@busqueda.json" in p and "RELATIVA" in p


def test_las_pistas_de_los_otros_subcomandos_no_se_tocan():
    for cmd, aguja in (("ask", "pregunta ENTERA"), ("say", "entre comillas"), ("wait", "corr_id")):
        assert aguja in WB._hint_for(f"worker_bridge {cmd}")
