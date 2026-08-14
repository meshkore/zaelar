#
# test_v2.py — esquema de config v2 «Colmena» (V2-001, T38). Verifica: defaults, persistencia atómica,
# fallback a env, y la INVARIANTE de privacidad (la vista pública nunca revela una API key).
# Ejecutar: .venv/bin/pytest tests/infrastructure/unit/config/test_v2.py
#
import importlib

import pytest


@pytest.fixture()
def v2(tmp_path, monkeypatch):
    # aísla el fichero de store por test
    import config.v2 as v2mod
    monkeypatch.setattr(v2mod, "_PATH", tmp_path / "v2.json")
    # limpia cualquier env de fallback que ensucie el test
    for env in ("FAST_MODEL", "FAST_PROVIDER", "FAST_API_KEY", "FAST_BASE_URL",
                "CODE_AGENT_PROVIDER", "CODE_AGENT_MODEL", "CODE_AGENT_API_KEY", "BRAIN"):
        monkeypatch.delenv(env, raising=False)
    return v2mod


def test_defaults(v2):
    fast = v2.get("fast")
    assert fast["provider"] == "aimlapi"
    # 2026-08-14: el default pasa a `deepseek/deepseek-v4-flash`, y con esto el DEFAULT y lo que el operador corre
    # de verdad dejan de contar historias distintas (su `config/v2.json` llevaba tiempo en DeepSeek). Lo respalda el
    # mismo banco del nodo 2.13 que eligió a Haiku en su día: sobre los 14 casos con el prompt real, DeepSeek enruta
    # **14/14** y Haiku **11/14** (falla mostrar-widget, data-op y alias). Haiku sigue en el catálogo y en el mismo
    # broker. Histórico: V2-034 (2026-07-12) lo puso en Haiku frente a grok-4-fast-non-reasoning.
    assert fast["model"] == "deepseek/deepseek-v4-flash"
    # El endpoint DIRECTO (api.deepseek.com) NO es el default a propósito: es 4× más rápido al primer token pero dio
    # 12/14 en una pasada suelta, y la regla es que si el nodo 2.13 baja, no se despliega. Vive como primer escalón
    # de relevo por latencia (`provider_chain._voice_chain`). Ver V2-097 §1.
    assert fast["base_url"] == "", "el titular va por el broker; el endpoint directo es RELEVO, no titular"
    assert v2.active_brain() == "nucleo"        # tras el entierro de Hermes (V2-009): cerebro propio por defecto
    assert v2.get("flags")["memory_enabled"] is True


def test_set_persists_and_reads_back(v2):
    v2.set("fast", {"model": "qwen2.5:14b", "provider": "ollama"})
    assert v2.get("fast")["model"] == "qwen2.5:14b"
    assert v2.get("fast")["provider"] == "ollama"
    # y persiste en disco
    assert v2._PATH.exists()


def test_set_ignores_unknown_keys(v2):
    v2.set("fast", {"model": "m", "bogus": "x"})
    assert "bogus" not in v2.get("fast")


def test_set_unknown_section_raises(v2):
    with pytest.raises(KeyError):
        v2.set("nope", {"a": 1})


def test_env_fallback_only_when_store_silent(v2, monkeypatch):
    monkeypatch.setenv("FAST_MODEL", "from-env")
    assert v2.get("fast")["model"] == "from-env"          # store vacío → cae a env
    v2.set("fast", {"model": "from-store"})
    assert v2.get("fast")["model"] == "from-store"        # store MANDA sobre env


def test_public_view_redacts_api_key(v2):
    v2.set("fast", {"api_key": "sk-supersecret"})
    pub = v2.public("fast")
    assert "api_key" not in pub                            # nunca en claro
    assert pub["api_key_set"] is True
    # y sin key configurada → _set False
    assert v2.public("code_agent")["api_key_set"] is False


def test_public_all_never_leaks_a_secret(v2):
    v2.set("fast", {"api_key": "sk-abc"})
    v2.set("code_agent", {"api_key": "sk-def"})
    blob = repr(v2.public_all())
    assert "sk-abc" not in blob and "sk-def" not in blob


def test_specs_for_by_invocation(v2):
    v2.set("fast", {"model": "grok", "provider": "aimlapi"})
    spec = v2.fast_model_spec()
    assert spec["model"] == "grok" and spec["provider"] == "aimlapi"
    assert "api_key" in spec                               # uso interno SÍ ve el secreto
