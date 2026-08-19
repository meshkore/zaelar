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
    # NORMA DEL OPERADOR (2026-08-19, Hard rule de CLAUDE.md): DeepSeek V4 DIRECTO de su proveedor es la opción
    # principal; AIMLAPI es el primer fallback y OpenAI/Anthropic el último. El default deja de ir por el broker.
    assert fast["provider"] == "deepseek"
    # Y V4 **PRO**, no Flash, por el endpoint directo: el banco a 3 rondas del nodo 2.13 (42 turnos por brazo,
    # 2026-08-15) midió justo lo que el comentario del default exigía para promoverlo — «córrelo a 3 rondas y si
    # aguanta, cámbialo». Pro aguantó (41/42, igual que el broker) y Flash directo NO (38/42, falló
    # `mostrar widget` 3 de 3: eso no es varianza, es un defecto). Lo que cuesta: el turno de voz pasa de ~0,5 a
    # ~1 Energy, y esa era la decisión de TARIFA que faltaba, no otra medición.
    # Histórico del titular: un modelo Anthropic vía broker (V2-034, 2026-07-12) → deepseek-v4-flash vía broker (2026-08-14) →
    # esto. Los dos anteriores siguen siendo opciones válidas del broker.
    assert fast["model"] == "deepseek-v4-pro"
    assert fast["base_url"] == "https://api.deepseek.com", "el titular va DIRECTO, no por el broker"
    # La cadena de relevo sigue VACÍA por defecto y la norma no lo cambia: vacía = titular + cadena AUTOMÁTICA
    # (en la nube, directo → broker; en SELF-HOST, solo el titular, porque quien se autohospeda paga sus APIs y
    # no puede llevarse la sorpresa de un proveedor que él no eligió).
    assert fast["providers"] == []
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
