"""V2-500 — el reparto de modelos vive en UN sitio, y las superficies de nube son copias que no pueden derivar.

Norma del operador (2026-08-30): *«la configuración debe estar en un archivo por defecto, público y en el
repositorio… quiero que ese archivo sea único y no quiero que estos datos estén en mil sitios a la vez»*.

Estaban en SEIS: `config/v2.py::_DEFAULTS`, `nucleo/flash/provider_chain.py`,
`nucleo/workers/providers.py`, `voice/engine/core/config.py`, `engine/fly.accounts.toml` y
`cloud/provisioner/src/machineConfig.js`. Los cuatro primeros ya LEEN la tabla, así que no pueden derivar por
construcción. Los dos últimos no son Python —son un TOML de Fly y un módulo JS de otro repo— así que la única
forma de que no se separen es comprobarlo, y ésa es la razón de este fichero.

Y derivaban de verdad: el 2026-08-30, con la norma «DeepSeek directo titular, AIMLAPI solo failover» dicha
varias veces, la nube tenía **AIMLAPI de titular de voz** y la memoria iba por el broker en los dos lados.
Nadie comparaba nada, así que la norma vivía únicamente en el `config/v2.json` del operador — gitignorado, y
por tanto invisible para cualquier instalación nueva.

El fichero de la nube puede no estar (es otro repo, privado): entonces se SALTA, nunca se inventa un verde.
"""
import json
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
TABLA = ENGINE / "config" / "models.default.json"
FLY = ENGINE / "fly.accounts.toml"
CLOUD = ENGINE.parent / "cloud" / "provisioner" / "src" / "machineConfig.js"


def _titular(servicio: str, campo: str) -> str:
    t = json.loads(TABLA.read_text(encoding="utf-8"))["services"][servicio]["titular"]
    return str(t.get(campo) or "")


#: Lo que las dos superficies de nube tienen que decir, sacado de la tabla.
def _esperado() -> dict[str, str]:
    return {
        "FAST_PROVIDER": _titular("voice_brain", "provider"),
        "FAST_BASE_URL": _titular("voice_brain", "base_url"),
        "FAST_MODEL": _titular("voice_brain", "model"),
        "CODE_AGENT_BASE_URL": _titular("brain_worker", "base_url"),
        "CODE_AGENT_MODEL": _titular("brain_worker", "model"),
        "MEM_PROCESSOR_URL": _titular("memory_writer", "base_url"),
        "MEM_PROCESSOR_MODEL": _titular("memory_writer", "model"),
        "ZAELAR_STT": _titular("stt", "provider"),
        "ZAELAR_TTS": _titular("tts", "provider"),
        # The vector space is the piece that costs MOST when local and cloud differ: it does not fail, it simply
        # finds something else. That is why all three surfaces name it identically, even though the engine
        # carries its own default.
        "ZAELAR_EMBED_BACKEND": _titular("embeddings", "provider"),
        "ZAELAR_EMBED_MODEL": _titular("embeddings", "model"),
        "ZAELAR_EMBED_BASE_URL": _titular("embeddings", "base_url"),
        "MEMORY_RERANK": _titular("reranker", "provider"),
    }


def _leidos(texto: str) -> dict[str, str]:
    """Vale para el TOML (`X = "v"`) y para el JS (`X: 'v'`) — la forma cambia, el par no."""
    out = {}
    for k in _esperado():
        m = re.search(rf"\b{k}\s*[:=]\s*['\"]([^'\"]*)['\"]", texto)
        if m:
            out[k] = m.group(1)
    return out


@pytest.mark.parametrize("fichero", [FLY, CLOUD], ids=["fly.accounts.toml", "cloud/machineConfig.js"])
def test_la_superficie_de_nube_dice_lo_MISMO_que_la_tabla(fichero):
    if not fichero.exists():
        pytest.skip(f"{fichero.name} no está aquí (repo privado): no se puede comprobar, y no se inventa")
    leidos, esperado = _leidos(fichero.read_text(encoding="utf-8")), _esperado()
    difiere = {k: (v, esperado[k]) for k, v in leidos.items() if v != esperado[k]}
    assert not difiere, (
        f"{fichero.name} se ha separado de la tabla: {difiere} (leído, esperado). No lo edites ahí — la tabla "
        f"es `config/models.default.json` y esto es una copia suya.")


@pytest.mark.parametrize("fichero", [FLY, CLOUD], ids=["fly.accounts.toml", "cloud/machineConfig.js"])
def test_la_superficie_NOMBRA_lo_que_tiene_que_nombrar(fichero):
    """Sensibilidad: si el regex dejara de casar, lo de arriba pasaría con un diccionario vacío — la forma
    exacta de un test que se cree verde porque no midió nada."""
    if not fichero.exists():
        pytest.skip("repo privado")
    faltan = set(_esperado()) - set(_leidos(fichero.read_text(encoding="utf-8")))
    assert not faltan, f"{fichero.name} no declara {sorted(faltan)}: la máquina saldría con otro reparto"


# ── la norma que gobierna la tabla ───────────────────────────────────────────────────────────────────────

def test_UN_SOLO_failover_por_servicio():
    """Norma del operador: titular y suplente, y si el suplente cae esa parte deja de funcionar. Una cadena de
    cuatro no se puede razonar, ni configurar, ni depurar — y no llega a estar seca nunca, así que el turno no
    puede decirle al operador «no queda nadie, esto lo arreglas tú»."""
    servicios = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for nombre, s in servicios.items():
        assert "titular" in s, f"«{nombre}» no declara titular"
        f = s.get("failover")
        assert f is None or isinstance(f, dict), (
            f"«{nombre}» declara más de un failover, o algo que no es uno: {type(f).__name__}")


def test_NADA_de_la_tabla_depende_de_un_servidor_LOCAL():
    """Todo tiene que poder correr en la nube. Ollama es un servidor local: dentro de un contenedor no existe,
    así que un default que lo nombre convierte la nube en una instalación degradada en silencio."""
    # Solo los CAMPOS que deciden a quién se llama. La prosa de `why` nombra Ollama justo para explicar por
    # qué está fuera, y un guarda que leyera el fichero entero se dispararía con su propia documentación.
    servicios = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for nombre, s in servicios.items():
        for cual in ("titular", "failover"):
            fila = s.get(cual) or {}
            aguja = f"{fila.get('provider','')} {fila.get('base_url','')} {fila.get('model','')}".lower()
            for prohibido in ("ollama", "localhost", "127.0.0.1", "11434"):
                assert prohibido not in aguja, (
                    f"«{prohibido}» en {nombre}.{cual}: eso no arranca dentro de un contenedor")


def test_ZAI_solo_aparece_en_el_BRAIN_WORKER():
    """V2-496, aplicado a la tabla: es donde ahora se decidiría volver a colarlo."""
    servicios = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for nombre, s in servicios.items():
        for cual in ("titular", "failover"):
            fila = s.get(cual) or {}
            if "z.ai" in str(fila.get("base_url") or ""):
                assert nombre == "brain_worker", f"Z.AI asomando en «{nombre}.{cual}»"


def test_lo_RETIRADO_no_ha_vuelto():
    """Cada entrada de `retired` dice por qué se quitó. Sin esto, el siguiente lo añade creyendo que falta —
    que es exactamente cómo volvió Z.AI a la cadena de voz."""
    tabla = json.loads(TABLA.read_text(encoding="utf-8"))
    retirados = {k for k in tabla.get("retired", {}) if k != "_"}
    assert {"xai", "groq", "ollama"} <= retirados, "falta declarar por qué se quitó algo que sí se quitó"
    for nombre, s in tabla["services"].items():
        for cual in ("titular", "failover"):
            url = str((s.get(cual) or {}).get("base_url") or "").lower()
            for muerto, host in (("xai", "api.x.ai"), ("groq", "api.groq.com")):
                assert host not in url, (
                    f"«{muerto}» ha vuelto en {nombre}.{cual}; su motivo sigue escrito en `retired`")


def test_every_credential_in_the_table_CAN_be_resolved_by_the_engine(monkeypatch):
    """A row can declare a `key_env` the engine cannot resolve for THAT endpoint — and then nothing fails: the
    request goes out unauthenticated, eats a 401 and degrades in silence (exactly what `nucleo/provider_keys`
    documents, since it was born from four lists drifting apart). What is checked here is the only thing that
    closes the hole: that for every `base_url` in the table the resolver returns the credential that same row
    NAMES.

    Variables are marked with sentinels instead of reading real values: the test needs no key at all and its
    output is safe in a log.
    """
    from nucleo import provider_keys

    for env_name in {e for _n, e in provider_keys._ENDPOINTS}:
        monkeypatch.setenv(env_name, f"SENTINEL::{env_name}")

    table = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for service, svc in table.items():
        for which in ("titular", "failover"):
            rung = svc.get(which)
            if not rung or not rung.get("base_url") or not rung.get("key_env"):
                continue
            resolved = provider_keys.key_for_endpoint(rung["base_url"])
            assert resolved == f"SENTINEL::{rung['key_env']}", (
                f"{service}.{which}: the table says {rung['base_url']} is paid for with {rung['key_env']}, but "
                f"the engine resolves something else ({resolved or 'NOTHING'}). Add the endpoint to "
                f"nucleo/provider_keys.")
