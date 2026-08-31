"""Unreadable arguments are not an argument-less action (V2-253).

It comes from the sweep adopted by the cluster on 2026-08-21, using the rule proposed by memoria-dev: **a limit is only
dangerous if the parser accepts PREFIXES**. The harness swept its four limits and declared them safe (they require
complete JSON and fall back to a default). Sweeping the engine's limits with the same criterion, all parsers proved safe
—`attention._parse_directed` and `segmenter._parse_judge` require the complete object and fall back to a conservative value—
except one: the one that drives the BROWSER.

`_next_action` returned **the action NAME with `{}`** when its arguments' JSON could not be parsed. In other words,
the loop executed `click` without a ref, `type` without text, or `navigate` without a URL: a plausible action based on
what the model said DELETED. It is part of the V2-171 family —“a truncated tool call is silently discarded”— and here it is worse,
because it is not discarded: **the action is taken**.

And it distinguishes who broke it, which is the useful half: the LIMIT is ours and is fixed by raising it; invalid arguments
come from the model and are fixed by retrying. “No action emitted” hid both cases.
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


# ── the case ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_un_JSON_a_medias_NO_se_ejecuta_como_accion_vacia(monkeypatch):
    accion, args = _decidir(monkeypatch, _Resp([_TC("click", '{"ref": 2')], finish_reason="length"))
    assert accion is None, "devolvía «click» con los argumentos borrados y el bucle lo ejecutaba"
    assert "no la ejecuto" in args["_error"]


def test_dice_que_lo_CORTAMOS_NOSOTROS_cuando_fue_el_tope(monkeypatch):
    _, args = _decidir(monkeypatch, _Resp([_TC("type", '{"text": "monitor 27 pul')], finish_reason="length"))
    assert "tope de tokens" in args["_error"], "el tope es NUESTRO y se arregla subiéndolo"
    assert "type" in args["_error"]


def test_y_que_fue_el_MODELO_cuando_no_lo_fue(monkeypatch):
    """The other half: invalid arguments with the entire turn delivered come from the model and are fixed by
    retrying. Confusing them sends investigation to the wrong place."""
    _, args = _decidir(monkeypatch, _Resp([_TC("click", "no soy json")], finish_reason="stop"))
    assert "ilegibles" in args["_error"] and "tope" not in args["_error"]


def test_sin_ninguna_accion_tambien_se_dice_si_fue_el_tope(monkeypatch):
    accion, args = _decidir(monkeypatch, _Resp([], finish_reason="length"))
    assert accion is None and "tope de tokens" in args["_error"]


# ── the other direction: the successful path remains unchanged ─────────────────────────────────────────────

def test_una_accion_BIEN_formada_pasa_igual(monkeypatch):
    accion, args = _decidir(monkeypatch, _Resp([_TC("click", json.dumps({"ref": 7}))], finish_reason="stop"))
    assert accion == "click" and args == {"ref": 7}


def test_unos_argumentos_VACIOS_de_verdad_siguen_valiendo(monkeypatch):
    """`snapshot` and `back` take no arguments: legitimate `{}` must not be confused with `{}` from a failure."""
    accion, args = _decidir(monkeypatch, _Resp([_TC("snapshot", "{}")], finish_reason="stop"))
    assert accion == "snapshot" and args == {}


def test_el_BUCLE_apunta_el_motivo_y_no_una_frase_generica():
    """WIRING GUARD (V2-199): the reason may be perfect while the loop keeps writing “no action emitted” in the
    steps, which is exactly what directs investigation to the model when the limit is ours."""
    import inspect
    src = inspect.getsource(agent)
    assert 'steps.append(args.get("_error") or "(el modelo no emitió acción)")' in src


@pytest.mark.parametrize("lector,fuente", [
    ("_parse_directed", "voice.attention"),
    ("_parse_judge", "nucleo.flash.segmenter"),
])
def test_los_OTROS_lectores_del_motor_exigen_el_objeto_entero(lector, fuente):
    """The sweep, nailed down: if either parser relaxes and starts accepting a prefix, its limit becomes dangerous
    without anything failing. Both parse JSON and fall back to a conservative value (None / “incomplete”)."""
    import importlib
    import inspect
    src = inspect.getsource(getattr(importlib.import_module(fuente), lector))
    assert "json.loads" in src
    assert "except" in src


# ── and it is counted through the channel that ALREADY exists (V2-255) ─────────────────────────────────────
# `tool_dropped` originated in V2-171 for exactly this event in FlashBrain, and the harness already reads it (its node
# 10.6). The browser had the same event and counted it only in its steps list: to any external instrument, it did not
# occur. Introducing a new kind would have forced changes in the existing consumer.

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
    """Sensitivity: if this fired every time, the discarded-actions counter would cease to mean anything."""
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append(a), raising=False)
    _decidir(monkeypatch, _Resp([_TC("click", '{"ref": 2}')], finish_reason="stop"))
    assert not vistos


def test_es_la_MISMA_forma_de_evento_que_la_del_FlashBrain():
    """SOURCE GUARD: a consumer that already consumes `tool_dropped` must not have to change to see it here too."""
    import inspect

    from nucleo.flash import fast_client
    for src in (inspect.getsource(fast_client), inspect.getsource(agent)):
        assert '"tool_dropped", "⚠️ acción descartada"' in src
        assert '"tool":' in src and '"reason":' in src
