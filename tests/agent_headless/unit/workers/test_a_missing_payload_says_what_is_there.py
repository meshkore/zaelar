"""«No such file or directory: progreso.json» is true and completely useless.

It leaves the worker unable to tell whether it wrote the file **somewhere else**, wrote it **under a different
name**, or **never managed to write it**. The three outcomes call for different actions, and from that message
they look identical, so the model chooses blindly. Measured in `best-plumber-same-day__es` (2026-08-28, brain
deepseek-v4-flash+glm-5.3): the step died there and the run took eight minutes without delivering what the
operator had explicitly requested three times.

It is the rule of «if you have the answer, print it»: the bridge is STOPPED in that directory and knows
perfectly well what is inside. The time a preflight held a 402 while saying «check the log» cost eight hours
and forty-six retries.

And the mechanism is SHARED: `widget_cli` already listed the `.json` files present and `worker_bridge` did
not, meaning the two bridges answered the same question differently. That divergence is exactly what led to
V2-379 (one bridge accepted `@fichero` and the other did not). Each bridge produces the message; only one is
being inspected.
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
    """«You did not write it» and «you wrote it somewhere else» lead to opposite actions."""
    monkeypatch.chdir(tmp_path)
    assert "VACÍO" in BU.what_is_here()
    assert "no llegó a escribirse" in BU.what_is_here()


def test_sin_ningun_json_se_enseña_lo_que_haya(tmp_path, monkeypatch):
    """Having files but none of them `.json` is the signature of «you wrote it with another extension»."""
    (tmp_path / "salida.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    dicho = BU.what_is_here()
    assert "ningún .json" in dicho and "salida.txt" in dicho


def test_esta_acotado(tmp_path, monkeypatch):
    """It goes to a bridge's stderr; it is not a file explorer."""
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
    """The failure was not that the listing was missing; it was having it in one bridge and not the other."""
    from pathlib import Path
    for f in ("nucleo/worker_bridge.py", "nucleo/widget_cli.py"):
        src = Path(f).read_text(encoding="utf-8")
        assert "what_is_here()" in src, f"{f} no comparte el mecanismo"
