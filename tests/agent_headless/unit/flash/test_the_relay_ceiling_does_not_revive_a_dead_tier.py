"""El techo del relevo por latencia levantaba el cooldown de un proveedor SIN CUOTA (V2-275).

Medido en `search-secondhand-monitor__es` (2026-08-24 00:56), leyendo la observabilidad de la ronda. En el
MISMO proceso, con 260 segundos de diferencia:

    +36,1 s  🔌 cerebro de cluster: «z.ai» (Z.AI GLM) sin cuota hasta el 25 Aug 01:39 → relevo a «aimlapi»
    +300,3 s 🔌 fin del relevo por latencia: vuelve «z.ai» (techo de 40 turnos en «aimlapi»)

`pick()` agota el techo de turnos de un relevo por LATENCIA y le devuelve el turno al titular «aunque siga
lento» — lo dice su propio comentario, así que la intención siempre fue esa. Lo que faltaba era poder
decirlo: `CooldownStore` guardaba un número y nada más, y `lift()` borraba el cooldown fuera cual fuera su
motivo. Así que el techo del relevo de latencia deshacía un castigo de 24 horas por falta de CUOTA y
mandaba el turno siguiente a un proveedor que sabíamos que iba a contestar 429.

Dos mecanismos del mismo módulo escribiendo un número y leyéndolo como si significara una sola cosa. Es la
forma de V2-252 por el otro lado: allí el cooldown caía sobre un proveedor SANO, aquí se le quitaba a uno
ROTO.

Y el techo NO tenía ni un test — por eso vivió. Éstos cubren las dos direcciones, porque «no levantes
nunca» arregla este caso y reintroduce el que el techo existe para evitar: quedarse indefinidamente en un
escalón más caro.
"""
import time

import pytest

from nucleo import provider_health as ph
from nucleo.flash import provider_chain as pc


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True                              # sin tocar la memoria real
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    pc._relay_turns.clear()
    for _var in ("Z_AI_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "AIMLAPI_KEY", "XAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(_var, raising=False)
    yield
    pc._relay_turns.clear()


def _two_tiers(monkeypatch):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": [
        {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"]},
        {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"]},
    ]} if k == "cluster" else {})
    monkeypatch.setenv("Z_AI_API_KEY", "z")
    monkeypatch.setenv("AIMLAPI_KEY", "a")


def _burn_the_relay_budget():
    """Deja al escalón de relevo con su presupuesto de turnos agotado, como tras una charla larga."""
    pc._relay_turns["aimlapi"] = pc._RELAY_TURN_BUDGET


# ── el defecto medido ──────────────────────────────────────────────────────────────────────────────────
def test_el_techo_NO_resucita_a_un_titular_sin_cuota(monkeypatch):
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)   # sin cuota semanal, como en la ronda
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "aimlapi", "le devolvió el turno al proveedor que no tiene cuota"
    assert pc._store.available("z.ai") is False, "el cooldown de SALUD se borró para resolver una latencia"


def test_y_no_se_queda_en_bucle_reintentando_el_techo(monkeypatch):
    """Sin reponer el contador, cada `pick` volvería a entrar en la rama y a emitir el mismo aviso."""
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)
    _burn_the_relay_budget()
    for _ in range(3):
        assert pc.pick()["name"] == "aimlapi"
    assert pc._relay_turns.get("aimlapi", 0) < pc._RELAY_TURN_BUDGET


# ── y la dirección contraria, que es lo que el techo existe para hacer ──────────────────────────────────
def test_pero_SI_lo_resucita_cuando_el_castigo_era_por_LENTITUD(monkeypatch):
    """Si esto se rompe, el arreglo de arriba deja al agente clavado en un escalón más caro para siempre."""
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + pc._SLOW_COOLDOWN_S, ph.REASON_LATENCY)
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "z.ai"
    assert pc._store.available("z.ai") is True


def test_un_titular_lento_Y_sin_cuota_esta_sin_cuota(monkeypatch):
    """El orden en que llegan los dos castigos no puede decidir cuál manda."""
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + pc._SLOW_COOLDOWN_S, ph.REASON_LATENCY)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "aimlapi"


def test_y_al_reves_un_castigo_de_salud_no_se_degrada_a_latencia(monkeypatch):
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)
    pc._store.set("z.ai", time.time() + pc._SLOW_COOLDOWN_S, ph.REASON_LATENCY)
    assert pc._store.why("z.ai") == ph.REASON_HEALTH
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "aimlapi"


# ── el motivo se guarda y sobrevive, y lo VIEJO se lee del lado seguro ──────────────────────────────────
def test_los_setters_reales_declaran_su_motivo(monkeypatch):
    """Sin esto el reason lo pone el default y el arreglo depende de que nadie olvide pasarlo."""
    _two_tiers(monkeypatch)
    reset = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
    pc.note_failure(f"429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at {reset} 00:00:00]",
                    {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert pc._store.why("z.ai") == ph.REASON_HEALTH

    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    tier = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"}
    for _ in range(pc._SLOW_STREAK):
        pc.note_slow({"cause": "pre_token", "ttft_ms": 9000}, role=pc.ROLE_CLUSTER, tier=tier)
    assert pc._store.why("z.ai") == ph.REASON_LATENCY, pc._store.why("z.ai")


def test_una_entrada_VIEJA_sin_motivo_se_lee_como_SALUD():
    """Lo que hay en disco AHORA es `{nombre: epoch}`. Leerla como latencia sería justo el defecto medido.

    Un cooldown que no se puede clasificar se trata como el lado del que no se puede levantar: martillear a
    un proveedor roto cuesta el turno, quedarse en el relevo cuesta unos céntimos.
    """
    st = ph.CooldownStore("t:legacy")
    st._loaded = True
    st._save = lambda: None
    saved = {"z.ai": time.time() + 3600}
    st._loaded = False
    st._cooldown, st._why = {}, {}
    import memory.api as memapi
    _real = memapi.kv_get
    memapi.kv_get = lambda k: saved if k == "t:legacy" else None
    try:
        assert st.why("z.ai") == ph.REASON_HEALTH
    finally:
        memapi.kv_get = _real
    st.lift("z.ai", only=ph.REASON_LATENCY)
    assert st.available("z.ai") is False
