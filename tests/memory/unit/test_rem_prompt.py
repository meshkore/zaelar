"""El prompt de la SÍNTESIS REM se compone sin reventar (regresión 2026-08-09).

Bug real que esto evita: `_REM_SYSTEM` termina con un ejemplo de JSON literal —`[{"concept": str, "insight":
str|null}]`— y se interpolaba con `str.format(lang=…)`, que trata esas llaves como marcadores → `KeyError:
'"concept"'` en CADA llamada. `memory/rem.py::synthesize` captura cualquier excepción del hook y devuelve 0, así
que la fase de INSIGHTS del sueño profundo llevaba semanas sin escribir NADA, fallando abierta en silencio: el
síntoma era "la memoria no consolida", no un error visible.

La prueba NO llama a ningún modelo: ejercita la composición del prompt y el contrato de fail-open del hook.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from nucleo import memllm  # noqa: E402


def test_prompt_rem_se_compone_sin_reventar():
    """La composición NO puede lanzar, y el idioma tiene que quedar sustituido de verdad."""
    system = memllm._REM_SYSTEM.replace("{lang}", "castellano")
    assert "castellano" in system
    assert "{lang}" not in system
    # el ejemplo de JSON del contrato sigue intacto (es lo que ancla el formato de salida del modelo)
    assert '"concept"' in system and '"insight"' in system


def test_format_sobre_el_prompt_esta_prohibido():
    """Guarda explícita: si alguien vuelve a meter `.format()` aquí, esto lo caza en vez de la producción.

    `str.format` sobre este prompt SIEMPRE lanza mientras el contrato lleve llaves literales — que es lo
    correcto y no se va a quitar. Por eso la interpolación tiene que ser `.replace`.
    """
    import pytest
    with pytest.raises(KeyError):
        memllm._REM_SYSTEM.format(lang="castellano")


def test_synthesize_no_llama_al_modelo_sin_grupos():
    """Contrato barato: sin grupos no hay llamada ni excepción."""
    assert memllm.synthesize_concept_groups([]) == []


def test_synthesize_compone_el_prompt_de_verdad(monkeypatch):
    """El camino REAL hasta el borde de la red: si la composición reventara, `chat_sync` no llegaría a
    invocarse y el fallo volvería a esconderse tras el fail-open del llamador."""
    visto = {}

    def _fake_chat_sync(task, system, user, **kw):
        visto["task"], visto["system"], visto["user"] = task, system, user
        return '[{"concept": "salud", "insight": "Cuida su salud con rutina de gimnasio."}]'

    monkeypatch.setattr(memllm, "chat_sync", _fake_chat_sync)
    out = memllm.synthesize_concept_groups(
        [{"concept": "salud", "pills": ["Va al gimnasio los lunes.", "Dejó el café en enero."]}]
    )
    assert visto["task"] == "rem"
    assert "{lang}" not in visto["system"]          # el idioma llegó sustituido
    assert "gimnasio" in visto["user"]              # las píldoras llegaron al modelo
    assert out == [{"concept": "salud", "insight": "Cuida su salud con rutina de gimnasio."}]
