"""V2-500 — the model allocation lives in ONE place: `config/models.default.json`.

Operator rule (2026-08-30): the configuration lives in one default file, public and in the repository, and
nowhere else. Every engine module that needs the allocation READS that table, so it cannot diverge by
construction.

A deployment repo checked out alongside the engine may declare the same keys in its own config files (TOML or
JS). Those cannot import the table, so the only way to keep them from diverging is to check them — which is
what this file does. When no such repo is present the checks are SKIPPED; a green result is never invented.
"""
import json
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
TABLA = ENGINE / "config" / "models.default.json"
# Optional deployment configs from a repo checked out alongside (skipped when absent).
DEPLOY_TOML = ENGINE.parent / "cloud" / "infra" / "fly" / "fly.accounts.toml"
DEPLOY_JS = ENGINE.parent / "cloud" / "provisioner" / "src" / "machineConfig.js"


def _titular(servicio: str, campo: str) -> str:
    t = json.loads(TABLA.read_text(encoding="utf-8"))["services"][servicio]["titular"]
    return str(t.get(campo) or "")


#: What a deployment config must say, taken from the table.
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
        # The vector space is the piece that costs MOST when two installs differ: it does not fail, it simply
        # finds something else. That is why every surface names it identically, even though the engine
        # carries its own default.
        "ZAELAR_EMBED_BACKEND": _titular("embeddings", "provider"),
        "ZAELAR_EMBED_MODEL": _titular("embeddings", "model"),
        "ZAELAR_EMBED_BASE_URL": _titular("embeddings", "base_url"),
        "MEMORY_RERANK": _titular("reranker", "provider"),
    }


def _leidos(texto: str) -> dict[str, str]:
    """Works for TOML (`X = "v"`) and JS (`X: 'v'`) — the form changes, the pair does not."""
    out = {}
    for k in _esperado():
        m = re.search(rf"\b{k}\s*[:=]\s*['\"]([^'\"]*)['\"]", texto)
        if m:
            out[k] = m.group(1)
    return out


@pytest.mark.parametrize("fichero", [DEPLOY_TOML, DEPLOY_JS], ids=["deployment-toml", "deployment-js"])
def test_a_deployment_config_says_the_SAME_as_the_table(fichero):
    if not fichero.exists():
        pytest.skip(f"{fichero.name} is not present (no deployment repo alongside): nothing to check, nothing invented")
    leidos, esperado = _leidos(fichero.read_text(encoding="utf-8")), _esperado()
    difiere = {k: (v, esperado[k]) for k, v in leidos.items() if v != esperado[k]}
    assert not difiere, (
        f"{fichero.name} se ha separado de la tabla: {difiere} (leído, esperado). No lo edites ahí — la tabla "
        f"es `config/models.default.json` y esto es una copia suya.")


@pytest.mark.parametrize("fichero", [DEPLOY_TOML, DEPLOY_JS], ids=["deployment-toml", "deployment-js"])
def test_la_superficie_NOMBRA_lo_que_tiene_que_nombrar(fichero):
    """Sensitivity: if the regex stopped matching, the above would pass with an empty dictionary — the exact
    form of a test that thinks it is green because it measured nothing."""
    if not fichero.exists():
        pytest.skip("no deployment repo alongside")
    faltan = set(_esperado()) - set(_leidos(fichero.read_text(encoding="utf-8")))
    assert not faltan, f"{fichero.name} no declara {sorted(faltan)}: la máquina saldría con otro reparto"


# ── the rule governing the table ──────────────────────────────────────────────────────────────────────────

def test_UN_SOLO_failover_por_servicio():
    """Operator rule: primary and backup, and if the backup goes down that part stops working. A chain of
    four cannot be reasoned about, configured, or debugged — and it never gets exhausted, so the turn cannot
    tell the operator “there is nobody left; you fix this.”"""
    servicios = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for nombre, s in servicios.items():
        assert "titular" in s, f"«{nombre}» no declara titular"
        f = s.get("failover")
        assert f is None or isinstance(f, dict), (
            f"«{nombre}» declara más de un failover, o algo que no es uno: {type(f).__name__}")


def test_NADA_de_la_tabla_depende_de_un_servidor_LOCAL():
    """Everything must be able to run in the cloud. Ollama is a local server: it does not exist inside a container,
    so a default that names it turns the cloud into a silently degraded installation."""
    # Only the FIELDS that decide whom to call. The `why` prose names Ollama specifically to explain why
    # it is excluded, and a guard that read the entire file would trigger on its own documentation.
    servicios = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for nombre, s in servicios.items():
        for cual in ("titular", "failover"):
            fila = s.get(cual) or {}
            aguja = f"{fila.get('provider','')} {fila.get('base_url','')} {fila.get('model','')}".lower()
            for prohibido in ("ollama", "localhost", "127.0.0.1", "11434"):
                assert prohibido not in aguja, (
                    f"«{prohibido}» en {nombre}.{cual}: eso no arranca dentro de un contenedor")


def test_ZAI_solo_aparece_en_el_BRAIN_WORKER():
    """V2-496, applied to the table: this is where someone might now decide to slip it back in."""
    servicios = json.loads(TABLA.read_text(encoding="utf-8"))["services"]
    for nombre, s in servicios.items():
        for cual in ("titular", "failover"):
            fila = s.get(cual) or {}
            if "z.ai" in str(fila.get("base_url") or ""):
                assert nombre == "brain_worker", f"Z.AI asomando en «{nombre}.{cual}»"


def test_lo_RETIRADO_no_ha_vuelto():
    """Each `retired` entry says why it was removed. Without this, the next person adds it thinking it is missing —
    which is exactly how Z.AI returned to the voice chain."""
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
    request goes out unauthenticated, eats a 401 and degrades in silence (exactly what `nucleo/energy/keys`
    documents, since it was born from four lists drifting apart). What is checked here is the only thing that
    closes the hole: that for every `base_url` in the table the resolver returns the credential that same row
    NAMES.

    Variables are marked with sentinels instead of reading real values: the test needs no key at all and its
    output is safe in a log.
    """
    from nucleo.energy import keys as provider_keys

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
                f"nucleo/energy/keys.")


#: How a retired provider SHOWS UP in a rung, since the `retired` section names the provider and a rung names a
#: URL and a model. Written out rather than derived, because a guard that guesses its own needles is a guard
#: that quietly stops matching.
_RETIRED_MARKERS = {
    "xai": ("x.ai", "grok"),
    "groq": ("groq.com", "llama-3"),
    "ollama": ("11434", "localhost", "127.0.0.1"),
    "cartesia": ("cartesia",),
}


def _live_chains() -> "list[tuple[str, list[dict]]]":
    """Every ladder the engine actually builds — asked as FUNCTIONS, never grepped out of the source.

    A source-text guard on this would have gone green on a rename and red on a refactor that changed nothing,
    which is the failure mode that already cost a round here. What matters is what the builders RETURN.
    """
    out = []
    from nucleo.llm import provider_chain as pc
    from nucleo.workers import providers as wp
    out.append(("voice latency relays", list(pc._VOICE_RELAYS())))
    out.append(("voice catalogue", list(pc._known_chain())))
    out.append(("brain worker catalogue", [dict(k) for k in wp.KNOWN]))
    return out


@pytest.mark.parametrize("who", sorted(_RETIRED_MARKERS))
def test_no_ladder_names_a_provider_the_table_RETIRED(who):
    """V2-500 retired xAI and Groq by measurement (`403 used all available credits`, `404 model_not_found`) —
    and removed them from ONE ladder, when there are TWO. The latency-relay ladder went on naming both,
    including `llama-3.3-70b-versatile`, for eleven days.

    It broke nothing: in self-host that ladder resolves empty, and none of the three engines ever used it. It
    did something slower and worse — it was the place where the allocation still said something else, so the
    same settled decision got re-opened every time somebody read it. The operator has had to say «we agreed
    the memory runs on DeepSeek direct» more times than any measurement should need.

    So the rule is not «the catalogue is right», it is: **a retired provider may not appear in ANY ladder.**
    """
    retired = json.loads(TABLA.read_text(encoding="utf-8"))["retired"]
    assert who in retired, f"'{who}' is no longer in the table's `retired` section — update this guard with it"

    offenders = []
    for label, chain in _live_chains():
        for rung in chain:
            haystack = " ".join(str(rung.get(f) or "") for f in ("base_url", "model", "name", "provider")).lower()
            hit = next((m for m in _RETIRED_MARKERS[who] if m in haystack), None)
            if hit:
                offenders.append(f"{label}: {rung.get('name')} ({hit})")
    assert not offenders, (
        f"'{who}' was retired — {retired[who]} — and is still named by: {', '.join(offenders)}. "
        f"The table is the allocation; a ladder that contradicts it re-opens a closed decision.")
