"""The JSON did not fit on the command line, and the bridge did not know how to read it from a file (V2-379).

Measured on `best-rated-rental-car__es` (2026-08-27, 2/5). The worker trace reads as follows:

    63,5 s  ⚠️ Contains brace with quote character (expansion obfuscation)   ← OUR gate blocks the JSON
    67,6 s  ✏️ writes 24316c-1/search.json                                   ← the worker improvises the workaround
    69,2 s  ⚠️ Exit code 1 invalid JSON payload                              ← and the bridge does not read files
    73,1 s  usage: worker_bridge act …                                       ← blindly
    77,5 s  usage: worker_bridge act …                                       ← again
    85,1 s  ✏️ writes 24316c-1/use_tool.json                                 ← and another one

Eight internal errors and ZERO browser results. The worker found the correct solution on its own
—writing the JSON to a file— and we told it no.

`act` is how the worker REQUESTS a search, so if it is closed there, the worker is left blind. And the convention ALREADY existed
in the other bridge: `widget_cli` accepts `@file` and `-` since V2-203. One bridge had it and the other did not.

The MECHANISM is shared (for the same reason as `bridge_usage.guided`): two payload readers diverge and
then one accepts `@file` and the other does not, which is exactly the state being fixed. Each bridge provides the MESSAGE,
because what to do with a missing file depends on who is asking.
"""
import json
import os

import pytest

from nucleo import bridge_usage as BU
from nucleo import worker_bridge as WB


# ── the shared reader ──────────────────────────────────────────────────────────────────────────────────────

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
    """`act` with an action and no payload is legitimate — not every action carries data."""
    assert BU.read_payload("") == ("", "argumento", "")


# ── the bridge actually uses it ────────────────────────────────────────────────────────────────────────────

def test_el_puente_LEE_el_fichero_y_no_dice_JSON_invalido(tmp_path, monkeypatch, capsys):
    """The wiring: the reader can be perfect and still not be connected, which is the state being fixed."""
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
    """V2-203 in this bridge: a message without an exit path is a message that stops the worker."""
    monkeypatch.setenv("ZAELAR_TASK_ID", "t1")
    assert WB._cmd_act("use_tool", "@no-existe.json") == 1
    err = capsys.readouterr().err
    assert "no puedo leer el payload de no-existe.json" in err
    assert os.getcwd() in err
    assert "DOS pasos" in err


def test_un_JSON_ROTO_dice_DE_DONDE_venia(tmp_path, monkeypatch, capsys):
    """“invalid JSON payload” by itself does not distinguish a malformed argument from a malformed file, and they require
    two different fixes."""
    f = tmp_path / "roto.json"
    f.write_text("{esto no es json", encoding="utf-8")
    monkeypatch.setenv("ZAELAR_TASK_ID", "t1")
    assert WB._cmd_act("use_tool", f"@{f}") == 1
    assert "fichero" in capsys.readouterr().err


# ── and the way out is SHOWN to it ─────────────────────────────────────────────────────────────────────────

def test_la_pista_de_act_nombra_el_rodeo_por_fichero():
    """A capability the worker does not know it has does not exist (V2-249). And the hint names the EXACT error that
    will be returned to it, which is what lets it match the error."""
    p = WB._hint_for("worker_bridge act")
    assert "brace with quote" in p
    assert "@busqueda.json" in p and "RELATIVA" in p


def test_las_pistas_de_los_otros_subcomandos_no_se_tocan():
    for cmd, aguja in (("ask", "pregunta ENTERA"), ("say", "entre comillas"), ("wait", "corr_id")):
        assert aguja in WB._hint_for(f"worker_bridge {cmd}")
