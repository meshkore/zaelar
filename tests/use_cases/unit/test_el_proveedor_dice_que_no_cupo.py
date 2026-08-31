"""V2-382 — the provider SAYS it cut off, and the judge guessed it.

The judge's three branches parse `choices[0]` (or the Anthropic envelope) and **discarded the field that says how
the response ended**: `finish_reason="length"` for the OpenAI-compatible ones, `stop_reason="max_tokens"` for
Z.AI. Without that data, `_judge_with_retry` inferred “this was cut off” from WHERE parsing broke, and after
that inference it asked for “the same thing but shorter” **with the same ceiling**.

Measured in `things-to-do-nearby-weekend__es` (2026-08-27 11:00): 519 s of real conversation, the verdict
cut off halfway through a key (`"cambio`, char 6688 of 6750), three identical attempts against the same ceiling,
and the round left parked without a judgment. The response was not malformed: it DID NOT FIT, and the provider said so.
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
    """`length` is a cutoff; `stop` is a complete response. The branch must distinguish them, not assume them."""
    monkeypatch.setattr(VL.config, "DEEPSEEK_KEY", "k")
    monkeypatch.setattr(VL.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(_respuesta_openai("{}", motivo)))
    out: dict = {}
    VL.deepseek_direct_call([{"role": "user", "content": "x"}], out=out)
    assert out["finish_reason"] == motivo
    assert out["cortada"] is esperado


@pytest.mark.parametrize("motivo, esperado", [("max_tokens", True), ("end_turn", False)])
def test_la_pata_de_glm_habla_anthropic_y_el_campo_se_llama_distinto(monkeypatch, motivo, esperado):
    """Z.AI uses `stop_reason` instead of `finish_reason`, and `max_tokens` instead of `length`.

    That is why normalization belongs in the branch rather than in the caller: if each one reads its own field, the one
    that forgets one does not fail — it stays silent, which is exactly what used to happen.
    """
    monkeypatch.setattr(VL.config, "ZAI_KEY", "k")
    monkeypatch.setattr(VL.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(_respuesta_anthropic("hola", motivo)))
    out: dict = {}
    VL.glm_call([{"role": "user", "content": "x"}], out=out)
    assert out["cortada"] is esperado


def test_una_pata_que_NO_habla_no_hereda_la_palabra_de_la_anterior(monkeypatch):
    """GLM says “max_tokens” and crashes; a branch that answers but points to NOTHING follows → it cannot remain “cut off”.

    When this was first written, the dismantling (removing the clearing in `judge_call`) was applied and did NOT bite: the
    branch that answered pointed to its own reason and overwrote the previous one, so the clearing was supporting nothing and
    the guard measured nothing. What the clearing really protects is the branch that FORGETS to speak — none today, the
    next one added tomorrow—: without it, it reads “cut off” from a response it did not even inspect.
    """
    monkeypatch.setattr(VL.config, "JUDGE_PROVIDER", "zai")
    monkeypatch.setattr(VL.config, "ZAI_KEY", "k")
    monkeypatch.setattr(VL.config, "DEEPSEEK_KEY", "k")

    def _glm(msgs, **kw):
        VL._anota_corte(kw.get("out"), "max_tokens")
        return ""                      # EMPTY body → this branch crashes

    monkeypatch.setattr(VL, "glm_call", _glm)
    monkeypatch.setattr(VL, "deepseek_direct_call", lambda msgs, **kw: "{}")   # answers and points to NOTHING
    out: dict = {}
    VL.judge_call([{"role": "user", "content": "x"}], out=out)
    assert out["cortada"] is False, "la lectura tiene que ser del que contestó, no del que se cayó"


def _falso_juez(monkeypatch, guion: list[tuple[str, str]]) -> list[int]:
    """Chains `(body, finish_reason)` responses and returns the list of ceilings used to request each one."""
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


# A JSON that breaks VERY FAR from the end: the V2-373 heuristic would deem it NOT cut off, so if the
# ceiling increases it must be because the provider said so — not because the heuristic inferred it.
_CORTADO_PERO_NO_PARECE = '{"a": "' + "x" * 4000 + '", "b" }' + "y" * 4000


def test_si_el_proveedor_dice_que_no_cupo_el_reintento_pide_MAS_SITIO(monkeypatch):
    techos = _falso_juez(monkeypatch, [(_CORTADO_PERO_NO_PARECE, "length"), ('{"ok": 1}', "stop")])
    v = J._judge_with_retry([{"role": "user", "content": "x"}])
    assert v["ok"] == 1
    assert techos == [J.JUDGE_MAX_TOKENS, J.JUDGE_MAX_TOKENS_AMPLIADO], \
        "el segundo intento tiene que pedir el techo ampliado, no repetir el mismo"


def test_un_json_MAL_FORMADO_no_sube_el_techo(monkeypatch):
    """The branching must work in BOTH directions: more room does not fix an extra comma.

    If the ceiling also increased here, the guard above would pass without testing anything — it would measure that the
    ceiling always increases, not that it increases WHEN the response did not fit.
    """
    techos = _falso_juez(monkeypatch, [('{"a": 1,, }', "stop"), ('{"ok": 1}', "stop")])
    J._judge_with_retry([{"role": "user", "content": "x"}])
    assert techos == [J.JUDGE_MAX_TOKENS, J.JUDGE_MAX_TOKENS], \
        "una respuesta que CUPO y vino mal no gana nada con más sitio"


def test_el_error_final_dice_lo_que_dijo_el_proveedor(monkeypatch):
    """A tool failure that does not reveal its cause is repeated in full each time (V2-363)."""
    _falso_juez(monkeypatch, [(_CORTADO_PERO_NO_PARECE, "length")] * 3)
    with pytest.raises(RuntimeError) as ei:
        J._judge_with_retry([{"role": "user", "content": "x"}])
    assert "finish_reason='length'" in str(ei.value)
    assert f"techo {J.JUDGE_MAX_TOKENS_AMPLIADO}" in str(ei.value)
