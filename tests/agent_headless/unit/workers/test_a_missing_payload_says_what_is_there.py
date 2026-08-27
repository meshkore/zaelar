"""«No such file or directory: progreso.json» es verdad y no sirve para nada.

Deja al worker sin saber si escribió el fichero **en otro sitio**, si lo escribió **con otro nombre**, o si
**no llegó a escribirlo**. Las tres salidas piden acciones distintas y desde ese mensaje se ven iguales, así
que el modelo elige a ciegas. Medido en `best-plumber-same-day__es` (2026-08-28, cerebro
deepseek-v4-flash+glm-5.3): el paso murió ahí y la ronda se fue en ocho minutos sin entregar lo que el
operador había pedido explícitamente tres veces.

Es la norma de «si tienes la respuesta, imprímela»: el puente está PARADO en ese directorio y sabe
perfectamente lo que hay dentro. La vez que un preflight sostuvo un 402 diciendo «mira el log» costó ocho
horas y cuarenta y seis reintentos.

Y el mecanismo se COMPARTE: `widget_cli` ya listaba los `.json` presentes y `worker_bridge` no, o sea que los
dos puentes contestaban distinto a la misma pregunta. Esa divergencia es exactamente de la que salió V2-379
(un puente aceptaba `@fichero` y el otro no). El mensaje lo pone cada puente; lo que se mira es uno solo.
"""
from __future__ import annotations

import os

from nucleo import bridge_usage as BU


def test_dice_los_json_que_SI_hay(tmp_path, monkeypatch):
    (tmp_path / "busqueda.json").write_text("{}", encoding="utf-8")
    (tmp_path / "use_tool.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    dicho = BU.what_is_here()
    assert "busqueda.json" in dicho and "use_tool.json" in dicho
    assert "notas.txt" not in dicho, "habiendo json, el ruido no ayuda"


def test_un_directorio_VACIO_es_una_respuesta_distinta(tmp_path, monkeypatch):
    """«No lo escribiste» y «lo escribiste en otro sitio» llevan a acciones opuestas."""
    monkeypatch.chdir(tmp_path)
    assert "VACÍO" in BU.what_is_here()
    assert "no llegó a escribirse" in BU.what_is_here()


def test_sin_ningun_json_se_enseña_lo_que_haya(tmp_path, monkeypatch):
    """Que haya ficheros pero ninguno `.json` es la firma de «lo escribió con otra extensión»."""
    (tmp_path / "salida.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    dicho = BU.what_is_here()
    assert "ningún .json" in dicho and "salida.txt" in dicho


def test_esta_acotado(tmp_path, monkeypatch):
    """Va a stderr de un puente, no es un explorador de ficheros."""
    for i in range(30):
        (tmp_path / f"f{i:02d}.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    dicho = BU.what_is_here()
    assert dicho.count(".json") <= 9 and "más" in dicho


def test_un_directorio_ILEGIBLE_no_convierte_un_error_claro_en_una_excepcion(monkeypatch):
    def _boom(*_a, **_k):
        raise OSError("nope")
    monkeypatch.setattr(os, "listdir", _boom)
    assert BU.what_is_here() == ""


def test_los_DOS_puentes_miran_el_mismo_sitio():
    """El fallo no fue que faltara el listado: fue tenerlo en un puente y no en el otro."""
    from pathlib import Path
    for f in ("nucleo/worker_bridge.py", "nucleo/widget_cli.py"):
        src = Path(f).read_text(encoding="utf-8")
        assert "what_is_here()" in src, f"{f} no comparte el mecanismo"
