"""V2-289 — al worker se le mandaba mirar una captura que su modelo no puede leer.

Medido en `search-buy-guitar__es` (2026-08-24 11:23), con el relevo puesto por cuota agotada
(«z.ai → relevo a deepseek»). Los eventos del bus, literales:

    task 💬 worker | La captura no se pudo leer (formato no soportado). Sigo por DOM
    task 💬 worker | La visión no carga la PNG (formato no soportado), así que trabajo con el snapshot DOM

Dos veces en la misma corrida. **La PNG estaba perfecta** —`PNG image data, 1280 x 800, 8-bit/color RGB` en
disco— así que no era una captura rota: el que no lee imágenes es DeepSeek V4. Y se lo pedíamos por DOS sitios a
la vez: el paso 1 del método del prompt («la visión es tu camino PRINCIPAL») y la respuesta de CADA acción del
puente («MÍRALA con Read …»). Coste por acción: un `Read` de 300-530 KB para redescubrir lo mismo, más la
narración del fallo al operador, que no tiene qué hacer con ella.

Es la familia de V2-284 vista por el otro lado: allí se ordenaba contar algo que el turno no sostenía, aquí se
ordena mirar algo que el modelo no puede ver. Una instrucción imposible no se desobedece — se choca con ella.

⚠️ **Y la dirección del fail-open es la mitad del arreglo.** Ausente = SÍ ve, que es la conducta de siempre. Un
«no ve» equivocado deja CIEGO a un worker que veía, y un worker ciego es el fallo más difícil de atribuir que
tiene este módulo (`workers/workdir.py` lo dice sobre `read_dirs`); un «sí ve» equivocado cuesta un `Read`
fallido y se sigue por el DOM, que es exactamente lo que ya pasaba. Por eso solo se declara donde está MEDIDO.
"""
import os

import pytest

from nucleo import nav_cli
from nucleo.dispatch_prompts import _web_prompt
from nucleo.workers import providers


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ZAELAR_NAV_VISION", raising=False)
    yield


# ── el escalón DECLARA la capacidad ───────────────────────────────────────────────────────────────────────
def test_the_measured_rung_declares_it_cannot_see():
    """El escalón de DeepSeek es el que se midió chocando; el veredicto vive con él, no en una lista aparte."""
    ds = next(t for t in providers.KNOWN if t["name"] == "deepseek")
    assert ds.get("vision") is False


def test_a_rung_that_says_nothing_keeps_the_vision_path():
    """Un escalón nuevo NO hereda un veredicto que nadie ha comprobado — y el silencio cae del lado seguro."""
    assert providers.vision_env({"name": "nuevo"}) == {}
    assert providers.vision_env(None) == {}
    assert providers.vision_env({"vision": True}) == {}


def test_only_an_explicit_no_turns_it_off():
    assert providers.vision_env({"vision": False}) == {"ZAELAR_NAV_VISION": "0"}


# ── el PUENTE deja de ofrecer la captura ──────────────────────────────────────────────────────────────────
_RES = {"ok": True, "url": "https://es.wallapop.com", "title": "Wallapop", "shot": "/tmp/shot-t1.png",
        "viewport": {"width": 1280, "height": 800}, "elements": "[2] caja de búsqueda\n[29] Precio"}


def test_the_bridge_offers_the_capture_when_the_model_can_see(capsys):
    nav_cli._print_state(_RES)
    out = capsys.readouterr().out
    assert "MÍRALA con Read" in out and _RES["shot"] in out


def test_the_bridge_does_not_send_a_blind_model_to_read_a_png(capsys, monkeypatch):
    monkeypatch.setenv("ZAELAR_NAV_VISION", "0")
    nav_cli._print_state(_RES)
    out = capsys.readouterr().out
    assert "MÍRALA con Read" not in out
    assert _RES["shot"] not in out, "la ruta del PNG sigue delante: la va a abrir igual"
    assert "click_at" in out, "no basta con callar la captura: hay que decir que esos comandos tampoco valen"


def test_the_blind_bridge_still_says_there_is_no_view(capsys, monkeypatch):
    """Callarlo se leería como que la captura FALLÓ, que es otra cosa y tiene su propio aviso (V2-205)."""
    monkeypatch.setenv("ZAELAR_NAV_VISION", "0")
    nav_cli._print_state(_RES)
    out = capsys.readouterr().out
    assert "VISTA:" in out and "no lee imágenes" in out
    assert "no llegó a escribirse" not in out


def test_the_elements_survive_either_way(capsys, monkeypatch):
    """El camino de texto es el que QUEDA cuando no hay visión: perderlo aquí dejaría al worker sin ninguno."""
    for blind in (False, True):
        if blind:
            monkeypatch.setenv("ZAELAR_NAV_VISION", "0")
        nav_cli._print_state(_RES)
        assert "[29] Precio" in capsys.readouterr().out


# ── y el PROMPT deja de ordenárselo ───────────────────────────────────────────────────────────────────────
def test_the_method_stops_calling_vision_the_main_path():
    con = _web_prompt("busca una guitarra", "")
    sin = _web_prompt("busca una guitarra", "", vision=False)
    assert "abre el PNG con Read" in con
    assert "abre el PNG con Read" not in sin
    assert "NO LEE IMÁGENES" in sin


def _paso_uno(prompt: str) -> str:
    """La línea del PASO 1, no el prompt entero. Assertar sobre el prompt completo daba VERDE con la orden
    borrada: `click <ref>`/`type <ref>` también salen en la lista de comandos de más arriba, así que la
    comprobación la satisfacía otro bloque. Lo cazó el desarme, no la lectura."""
    return next(l for l in prompt.splitlines() if l.startswith("1) MIRA"))


def test_the_blind_method_names_the_path_that_is_left():
    """Quitar la orden imposible sin poner la posible deja al worker sin paso 1."""
    paso = _paso_uno(_web_prompt("busca una guitarra", "", vision=False))
    assert "click <ref>" in paso and "type <ref>" in paso, paso


def test_the_rest_of_the_method_is_untouched():
    """Partir un bloque en dos es como se pierde una regla por el camino (la lección de V2-185)."""
    con = _web_prompt("busca una guitarra", "")
    sin = _web_prompt("busca una guitarra", "", vision=False)
    for paso in ("2) DESBLOQUEA", "3) RECONOCE", "MÉTODO — como lo haría"):
        assert paso in con and paso in sin, paso


def test_vision_is_the_default():
    """Sin decir nada, el prompt es el de siempre — un cambio que apaga la visión por descuido es MUDO."""
    assert _web_prompt("x", "") == _web_prompt("x", "", vision=True)
