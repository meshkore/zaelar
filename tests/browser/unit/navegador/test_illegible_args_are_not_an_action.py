"""Unos argumentos ilegibles no son una acción SIN argumentos (V2-253).

Sale del barrido que adoptó el cluster el 2026-08-21, con la regla que propuso memoria-dev: **un techo solo es
peligroso si el lector acepta PREFIJOS**. El arnés barrió sus cuatro topes y los declaró seguros (exigen JSON
entero y caen a un default). Al barrer los del motor con el mismo criterio, todos los lectores resultaron seguros
—`attention._parse_directed` y `segmenter._parse_judge` exigen el objeto entero y fallan a un valor conservador—
menos uno: el que conduce el NAVEGADOR.

`_next_action` devolvía **el NOMBRE de la acción con `{}`** cuando el JSON de sus argumentos no parseaba. O sea
que el bucle ejecutaba `click` sin ref, `type` sin texto o `navigate` sin url: una acción plausible con lo que el
modelo dijo BORRADO. Es la familia de V2-171 —«una tool call truncada se descarta en silencio»— y aquí es peor,
porque no se descarta: **se actúa**.

Y se distingue quién lo rompió, que es la mitad útil: el TOPE es nuestro y se arregla subiéndolo; unos argumentos
inválidos son del modelo y se arreglan reintentando. «No emitió acción» tapaba las dos.
"""
import asyncio
import json

import pytest

from widgets.navegador import agent


class _Fn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class _TC:
    def __init__(self, name, arguments):
        self.function = _Fn(name, arguments)


class _Choice:
    def __init__(self, tool_calls, finish_reason=None):
        self.message = type("M", (), {"tool_calls": tool_calls})()
        self.finish_reason = finish_reason


class _Resp:
    def __init__(self, tool_calls, finish_reason=None):
        self.choices = [_Choice(tool_calls, finish_reason)]
        self.usage = None


def _decidir(monkeypatch, resp):
    class _Cli:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return resp

    monkeypatch.setattr(agent, "_c", lambda: _Cli(), raising=False)
    monkeypatch.setattr(agent, "_meter", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(agent, "_model", lambda: "m", raising=False)
    monkeypatch.setattr(agent, "_model_strong", lambda: "", raising=False)
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        agent._next_action([{"role": "system", "content": "x"}], [], strong=False))


# ── el caso ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_un_JSON_a_medias_NO_se_ejecuta_como_accion_vacia(monkeypatch):
    accion, args = _decidir(monkeypatch, _Resp([_TC("click", '{"ref": 2')], finish_reason="length"))
    assert accion is None, "devolvía «click» con los argumentos borrados y el bucle lo ejecutaba"
    assert "no la ejecuto" in args["_error"]


def test_dice_que_lo_CORTAMOS_NOSOTROS_cuando_fue_el_tope(monkeypatch):
    _, args = _decidir(monkeypatch, _Resp([_TC("type", '{"text": "monitor 27 pul')], finish_reason="length"))
    assert "tope de tokens" in args["_error"], "el tope es NUESTRO y se arregla subiéndolo"
    assert "type" in args["_error"]


def test_y_que_fue_el_MODELO_cuando_no_lo_fue(monkeypatch):
    """La otra mitad: unos argumentos inválidos con el turno entero entregado son del modelo, y se arreglan
    reintentando. Confundirlas manda a mirar al sitio equivocado."""
    _, args = _decidir(monkeypatch, _Resp([_TC("click", "no soy json")], finish_reason="stop"))
    assert "ilegibles" in args["_error"] and "tope" not in args["_error"]


def test_sin_ninguna_accion_tambien_se_dice_si_fue_el_tope(monkeypatch):
    accion, args = _decidir(monkeypatch, _Resp([], finish_reason="length"))
    assert accion is None and "tope de tokens" in args["_error"]


# ── la otra dirección: el camino bueno no cambia ─────────────────────────────────────────────────────────────

def test_una_accion_BIEN_formada_pasa_igual(monkeypatch):
    accion, args = _decidir(monkeypatch, _Resp([_TC("click", json.dumps({"ref": 7}))], finish_reason="stop"))
    assert accion == "click" and args == {"ref": 7}


def test_unos_argumentos_VACIOS_de_verdad_siguen_valiendo(monkeypatch):
    """`snapshot` o `back` no llevan argumentos: `{}` legítimo no puede confundirse con `{}` de un fallo."""
    accion, args = _decidir(monkeypatch, _Resp([_TC("snapshot", "{}")], finish_reason="stop"))
    assert accion == "snapshot" and args == {}


def test_el_BUCLE_apunta_el_motivo_y_no_una_frase_generica():
    """GUARDA DE CABLEADO (V2-199): el motivo puede estar perfecto y el bucle seguir escribiendo «no emitió
    acción» en los pasos, que es justo lo que manda a mirar al modelo cuando el tope es nuestro."""
    import inspect
    src = inspect.getsource(agent)
    assert 'steps.append(args.get("_error") or "(el modelo no emitió acción)")' in src


@pytest.mark.parametrize("lector,fuente", [
    ("_parse_directed", "voice.attention"),
    ("_parse_judge", "nucleo.flash.segmenter"),
])
def test_los_OTROS_lectores_del_motor_exigen_el_objeto_entero(lector, fuente):
    """El barrido, clavado: si alguno se relaja y empieza a aceptar un prefijo, su techo se vuelve peligroso sin
    que nada falle. Los dos parsean JSON y caen a un valor conservador (None / «incomplete»)."""
    import importlib
    import inspect
    src = inspect.getsource(getattr(importlib.import_module(fuente), lector))
    assert "json.loads" in src
    assert "except" in src


# ── y se cuenta por el canal que YA existe (V2-255) ──────────────────────────────────────────────────────────
# `tool_dropped` nació en V2-171 para exactamente este suceso en el FlashBrain, y el arnés ya lo lee (su nodo
# 10.6). El navegador tenía el mismo suceso y lo contaba solo en su lista de pasos: para cualquier instrumento
# de fuera, no ocurría. Estrenar un kind nuevo habría obligado a cambiar a quien ya lo consume.

def test_una_accion_descartada_SALE_por_tool_dropped(monkeypatch):
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append((a, k)), raising=False)
    _decidir(monkeypatch, _Resp([_TC("click", '{"ref": 2')], finish_reason="length"))
    assert vistos and vistos[0][0][0] == "tool_dropped"
    extra = vistos[0][1]["extra"]
    assert extra["tool"] == "click" and extra["where"] == "navegador"
    assert extra["finish_reason"] == "length", "el instrumento tiene que poder separar nuestro tope del modelo"


def test_una_accion_BUENA_no_emite_nada(monkeypatch):
    """Sensibilidad: si esto se disparara siempre, el contador de acciones descartadas dejaría de significar nada."""
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append(a), raising=False)
    _decidir(monkeypatch, _Resp([_TC("click", '{"ref": 2}')], finish_reason="stop"))
    assert not vistos


def test_es_la_MISMA_forma_de_evento_que_la_del_FlashBrain():
    """GUARDA DE FUENTE: quien ya consume `tool_dropped` no puede tener que cambiar para verlo también aquí."""
    import inspect

    from nucleo.flash import fast_client
    for src in (inspect.getsource(fast_client), inspect.getsource(agent)):
        assert '"tool_dropped", "⚠️ acción descartada"' in src
        assert '"tool":' in src and '"reason":' in src
