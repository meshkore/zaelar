"""V2-382 — el proveedor DICE que cortó, y el juez lo adivinaba.

Las tres patas del juez parsean `choices[0]` (o el sobre de Anthropic) y **tiraban el campo que dice cómo
terminó la respuesta**: `finish_reason="length"` en las compatibles con OpenAI, `stop_reason="max_tokens"` en
la de Z.AI. Sin ese dato, `_judge_with_retry` deducía «esto se cortó» de DÓNDE reventó el parseo, y al deducirlo
pedía «lo mismo más breve» **con el mismo techo**.

Medido en `things-to-do-nearby-weekend__es` (2026-08-27 11:00): 519 s de conversación real, el veredicto
cortado a mitad de una clave (`"cambio`, char 6688 de 6750), tres intentos idénticos contra el mismo techo y la
ronda aparcada sin juzgar. La respuesta no venía mal formada: NO CABÍA, y el proveedor lo decía.
"""
from __future__ import annotations

import json
import io
import pytest

from tests.voice.e2e.agent import llm as VL
from tests.use_cases.e2e.agent import judge as J


def _respuesta_openai(texto: str, finish: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": texto}, "finish_reason": finish}]}).encode()


def _respuesta_anthropic(texto: str, stop: str) -> bytes:
    return json.dumps({"content": [{"type": "text", "text": texto}], "stop_reason": stop}).encode()


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.mark.parametrize("motivo, esperado", [("length", True), ("stop", False)])
def test_la_pata_directa_de_deepseek_apunta_lo_que_dijo_el_proveedor(monkeypatch, motivo, esperado):
    """`length` es un corte; `stop` es una respuesta entera. La pata tiene que distinguirlos, no suponerlos."""
    monkeypatch.setattr(VL.config, "DEEPSEEK_KEY", "k")
    monkeypatch.setattr(VL.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(_respuesta_openai("{}", motivo)))
    out: dict = {}
    VL.deepseek_direct_call([{"role": "user", "content": "x"}], out=out)
    assert out["finish_reason"] == motivo
    assert out["cortada"] is esperado


@pytest.mark.parametrize("motivo, esperado", [("max_tokens", True), ("end_turn", False)])
def test_la_pata_de_glm_habla_anthropic_y_el_campo_se_llama_distinto(monkeypatch, motivo, esperado):
    """Z.AI no dice `finish_reason` sino `stop_reason`, y no dice `length` sino `max_tokens`.

    Es el motivo de normalizar en la pata y no en quien llama: si cada uno lee su propio campo, el que se
    olvide de uno no falla — se queda callado, que es exactamente lo que pasaba.
    """
    monkeypatch.setattr(VL.config, "ZAI_KEY", "k")
    monkeypatch.setattr(VL.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(_respuesta_anthropic("hola", motivo)))
    out: dict = {}
    VL.glm_call([{"role": "user", "content": "x"}], out=out)
    assert out["cortada"] is esperado


def test_una_pata_que_NO_habla_no_hereda_la_palabra_de_la_anterior(monkeypatch):
    """GLM dice «max_tokens» y se cae; contesta una pata que NO apunta nada → no puede quedar «cortada».

    Al escribir esto la primera vez el desarme (quitar el borrado de `judge_call`) se aplicó y NO mordió: la
    pata que contestaba apuntaba su propio motivo y pisaba el anterior, así que el borrado no sostenía nada y
    el guarda no medía nada. Lo que el borrado protege de verdad es la pata que se OLVIDA de hablar —hoy
    ninguna, mañana la siguiente que se añada—: sin él lee «cortada» de una respuesta que ni miró.
    """
    monkeypatch.setattr(VL.config, "JUDGE_PROVIDER", "zai")
    monkeypatch.setattr(VL.config, "ZAI_KEY", "k")
    monkeypatch.setattr(VL.config, "DEEPSEEK_KEY", "k")

    def _glm(msgs, **kw):
        VL._anota_corte(kw.get("out"), "max_tokens")
        return ""                      # cuerpo VACÍO → esta pata se cae

    monkeypatch.setattr(VL, "glm_call", _glm)
    monkeypatch.setattr(VL, "deepseek_direct_call", lambda msgs, **kw: "{}")   # contesta y NO apunta nada
    out: dict = {}
    VL.judge_call([{"role": "user", "content": "x"}], out=out)
    assert out["cortada"] is False, "la lectura tiene que ser del que contestó, no del que se cayó"


def _falso_juez(monkeypatch, guion: list[tuple[str, str]]) -> list[int]:
    """Encadena respuestas `(cuerpo, finish_reason)` y devuelve la lista de techos con que se pidió cada una."""
    techos: list[int] = []
    pasos = iter(guion)

    def _call(msgs, max_tokens=2000, out=None):
        techos.append(max_tokens)
        cuerpo, finish = next(pasos)
        if out is not None:
            out["finish_reason"] = finish
            out["cortada"] = finish in ("length", "max_tokens")
        return cuerpo, "juez-de-mentira"

    monkeypatch.setattr(J.llm, "judge_call", _call)
    return techos


# Un JSON que revienta MUY LEJOS del final: la heurística de V2-373 lo daría por NO cortado, así que si el
# techo sube tiene que ser porque el proveedor lo dijo — no porque la heurística lo dedujera.
_CORTADO_PERO_NO_PARECE = '{"a": "' + "x" * 4000 + '", "b" }' + "y" * 4000


def test_si_el_proveedor_dice_que_no_cupo_el_reintento_pide_MAS_SITIO(monkeypatch):
    techos = _falso_juez(monkeypatch, [(_CORTADO_PERO_NO_PARECE, "length"), ('{"ok": 1}', "stop")])
    v = J._judge_with_retry([{"role": "user", "content": "x"}])
    assert v["ok"] == 1
    assert techos == [J.JUDGE_MAX_TOKENS, J.JUDGE_MAX_TOKENS_AMPLIADO], \
        "el segundo intento tiene que pedir el techo ampliado, no repetir el mismo"


def test_un_json_MAL_FORMADO_no_sube_el_techo(monkeypatch):
    """La bifurcación tiene que ir en los DOS sentidos: más sitio no arregla una coma de más.

    Si subiera el techo también aquí, el guarda de arriba pasaría sin probar nada — mediría que el techo sube
    siempre, no que sube CUANDO no cupo.
    """
    techos = _falso_juez(monkeypatch, [('{"a": 1,, }', "stop"), ('{"ok": 1}', "stop")])
    J._judge_with_retry([{"role": "user", "content": "x"}])
    assert techos == [J.JUDGE_MAX_TOKENS, J.JUDGE_MAX_TOKENS], \
        "una respuesta que CUPO y vino mal no gana nada con más sitio"


def test_el_error_final_dice_lo_que_dijo_el_proveedor(monkeypatch):
    """Un fallo del instrumento que no deja ver su causa se repite entero cada vez (V2-363)."""
    _falso_juez(monkeypatch, [(_CORTADO_PERO_NO_PARECE, "length")] * 3)
    with pytest.raises(RuntimeError) as ei:
        J._judge_with_retry([{"role": "user", "content": "x"}])
    assert "finish_reason='length'" in str(ei.value)
    assert f"techo {J.JUDGE_MAX_TOKENS_AMPLIADO}" in str(ei.value)
