"""Cadena de proveedores del CEREBRO DE CLUSTER + relevo automático (2026-08-03).

Hermano de tests/agent_headless/unit/workers/test_provider_failover.py: mismo incidente-clase (un 429 de Z.AI sin
relevo), pero del lado del turno de cluster (`connectors/meshkore/brain.py` → `nucleo.flash.cluster.respond` →
`FastClient`), no del CLI de los brain workers. Antes de esto el tier se fijaba UNA VEZ al arrancar el server y el
heartbeat repetía la MISMA llamada rota en bucle — "cluster brain turn failed: 429" una y otra vez, sin relevo y
sin que el panel dijera nada.
"""
import time

import pytest

from nucleo.flash import provider_chain as pc

# Fecha SIEMPRE 2 días por delante de "ahora" — nunca un literal absoluto (uno se quedó atrás: "2026-08-04" pasó
# a estar en el pasado y un cooldown con reset ya vencido se considera disponible al instante, tumbando pick()).
RESET_DATE = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
REAL_429_EXHAUSTED = ("429 Too Many Requests — {\"error\":{\"message\":"
                      f"\"[1310][Weekly/Monthly Limit Exhausted. Your limit will reset at {RESET_DATE} 00:00:00]\"}}}}")
BARE_429 = "429 Too Many Requests"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True                              # sin tocar la memoria real
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    for _var in ("Z_AI_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "AIMLAPI_KEY", "XAI_API_KEY", "GROQ_API_KEY",
                 "MESHKORE_MISSION_MODEL", "ASSISTANT_LLM_MODEL", "LLM_MODEL", "MESHKORE_MISSION_MODEL_ZAI"):
        monkeypatch.delenv(_var, raising=False)
    yield


def _cfg(monkeypatch, providers=None):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": providers or []} if k == "cluster" else {})


# ── zero-config: la cadena por defecto usa las credenciales presentes, en el MISMO orden que antes ──────────
def test_default_chain_prefers_zai_then_aimlapi_then_xai_then_groq(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    monkeypatch.setenv("XAI_API_KEY", "k3")
    monkeypatch.setenv("GROQ_API_KEY", "k4")
    assert [t["name"] for t in pc.chain()] == ["z.ai", "aimlapi", "xai", "groq"]


def test_a_tier_without_credentials_is_not_offered(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert [t["name"] for t in pc.chain()] == ["z.ai"]


def test_explicit_llm_override_wins_over_zai(monkeypatch):
    """Un LLM_BASE_URL/LLM_API_KEY explícito seguía ganando a Z.AI antes de esto (el operador pinchó un endpoint a
    mano) — se preserva reordenando (aimlapi primero), no descartando Z.AI de la cadena."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("LLM_API_KEY", "k2")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.aimlapi.com/v1")
    assert [t["name"] for t in pc.chain()] == ["aimlapi", "z.ai"]


def test_operator_can_order_the_chain_by_hand(monkeypatch):
    _cfg(monkeypatch, providers=[
        {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"]},
        {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"]},
    ])
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("Z_AI_API_KEY", "z")
    assert [t["name"] for t in pc.chain()] == ["groq", "z.ai"]


# ── clasificar la avería: agotado ≠ rate-limit pasajero (misma regla que el hermano de workers) ─────────────
def test_a_passing_rate_limit_does_not_burn_a_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert pc.classify_failure(BARE_429) == "rate"
    assert pc.note_failure(BARE_429) is None            # se reintenta solo, no se releva
    assert pc.pick()["name"] == "z.ai"


def test_a_task_failure_is_not_a_provider_failure():
    assert pc.classify_failure("no encontré ningún parque acuático abierto hoy") == ""
    assert pc.note_failure("no encontré ningún parque acuático abierto hoy") is None


# ── el relevo ─────────────────────────────────────────────────────────────────────────────────────────────
def test_exhaustion_hands_over_and_respects_the_providers_own_reset_date(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    assert pc.pick()["name"] == "z.ai"

    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert nxt["name"] == "aimlapi"
    assert pc.pick()["name"] == "aimlapi"               # el siguiente turno ya arranca en el relevo (STICKY)
    assert pc._store._cooldown["z.ai"] == time.mktime(time.strptime(RESET_DATE, "%Y-%m-%d"))


def test_without_a_reset_date_it_retries_in_a_while(monkeypatch):
    """Una CUOTA que no dice cuándo vuelve: media hora y se reintenta.

    El ejemplo era «insufficient credit» y V2-243 lo convirtió en el OTRO caso —un saldo, que no vuelve solo—,
    así que aquí va un agotamiento de cuota de verdad. La intención del test no cambia; lo que tenía dos
    significados era el ejemplo."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure("quota exceeded", {"name": "z.ai", "base_url": "x"})
    assert time.time() < pc._store._cooldown["z.ai"] <= time.time() + pc._DEFAULT_COOLDOWN_S + 1


# ── V2-243: un SALDO agotado no es una cuota ────────────────────────────────────────────────────────────────
# Medido en producción el 2026-08-21: `Insufficient Balance` de DeepSeek (HTTP 402) dos veces, anunciado como
# «sin cuota hasta el 21 Aug 03:02 · SIN RELEVO disponible». A las 03:02 no iba a pasar nada — un saldo no se
# repone solo—, y con la cadena entera seca el arnés tuvo que parar de medir. Una cuota le dice al operador
# «espera»; un saldo le dice «recarga», y de eso depende lo que HAGA.

def test_un_saldo_agotado_se_reintenta_MUCHO_mas_tarde(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure("API Error 402 Insufficient Balance", {"name": "z.ai", "base_url": "x"})
    until = pc._store._cooldown["z.ai"]
    assert until > time.time() + pc._DEFAULT_COOLDOWN_S, \
        "reintentar cada media hora contra una cuenta vacía quema un turno por ronda"
    assert until <= time.time() + pc._DEPLETED_COOLDOWN_S + 1


def test_un_saldo_CON_fecha_de_reset_sigue_siendo_una_cuota(monkeypatch):
    """Sensibilidad, y no es teórico: un plan con forfait puede decir «insufficient credit … reset at …». Si
    anuncia cuándo vuelve, vuelve solo, y apagarlo seis horas de más es perder el escalón preferido."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure("insufficient credit, quota will reset at 2026-08-30", {"name": "z.ai", "base_url": "x"})
    assert pc._store._cooldown["z.ai"] == time.mktime(time.strptime("2026-08-30", "%Y-%m-%d")), \
        "con fecha anunciada manda la fecha: es el camino de la CUOTA, no el del saldo"


def test_el_aviso_DICE_recargar_y_no_una_hora_que_no_significa_nada(monkeypatch):
    """Lo que se escribe aquí es lo que el operador lee en el panel, y de ello depende lo que haga."""
    from voice import health_state
    dichos = []
    monkeypatch.setattr(health_state, "record", lambda *a, **k: dichos.append(a), raising=False)
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure("Insufficient Balance", {"name": "z.ai", "base_url": "x"})
    detalle = " ".join(str(x) for a in dichos for x in a)
    assert "SIN SALDO" in detalle and "recargar" in detalle
    assert "sin cuota hasta" not in detalle


def test_no_tier_left_returns_none(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    assert nxt is None
    assert pc.pick() is None


def test_clear_lets_the_operator_resume_after_topping_up(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    pc.clear("z.ai")
    assert pc.pick()["name"] == "z.ai"


def test_spec_for_carries_model_and_credential(monkeypatch):
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    tier = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "env": ["Z_AI_API_KEY"]}
    spec = pc.spec_for(tier)
    assert spec.model == "glm-5.2" and spec.base_url == "https://api.z.ai/api/anthropic" and spec.api_key == "zzz"


# ── y que el PANEL se entere ──────────────────────────────────────────────────────────────────────────────
def test_the_alerts_panel_surfaces_an_exhausted_cluster_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    from config import balances
    assert not [a for a in balances.cluster_providers() if a["state"] == "error"]

    pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    rows = balances.cluster_providers()
    bad = [r for r in rows if r["state"] == "error"]
    assert bad and bad[0]["key"] == "cluster:z.ai" and "cuota" in bad[0]["detail"]
    assert [r for r in rows if r["state"] == "ok" and "EN USO" in r["detail"]]


def test_no_tier_left_is_its_own_loud_alert(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    from config import balances
    assert any(r["key"] == "cluster:sin-relevo" for r in balances.cluster_providers())


# ── HARD failure on the VOICE role, not just a slow turn (2026-08-15 addendum) ──────────────────────────────
# `note_slow` already had a `role` param and was wired into the voice turn; `note_failure` was hardcoded to the
# cluster brain, so a real provider error (no balance, bad credential) on the FlashBrain's titular used to just
# repeat against the same broken tier every turn — nothing ever relayed it. Mirrors the cluster tests above,
# against `fast.providers` instead of `cluster.providers`.
def _cfg_fast(monkeypatch, providers=None):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": providers or []} if k == "fast" else {})


def test_voice_role_reads_the_fast_chain_not_cluster(monkeypatch):
    _cfg_fast(monkeypatch, providers=[
        {"name": "deepseek-directo", "base_url": "https://api.deepseek.com", "env": ["DEEPSEEK_API_KEY"]},
        {"name": "aimlapi-failover", "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"]},
    ])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    monkeypatch.setenv("AIMLAPI_KEY", "a")
    assert [t["name"] for t in pc.chain(pc.ROLE_VOICE)] == ["deepseek-directo", "aimlapi-failover"]
    assert pc.pick(pc.ROLE_VOICE)["name"] == "deepseek-directo"


def test_a_hard_failure_on_voice_relays_to_the_next_fast_tier(monkeypatch):
    _cfg_fast(monkeypatch, providers=[
        {"name": "deepseek-directo", "base_url": "https://api.deepseek.com", "env": ["DEEPSEEK_API_KEY"]},
        {"name": "aimlapi-failover", "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"]},
    ])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    monkeypatch.setenv("AIMLAPI_KEY", "a")
    assert pc.pick(pc.ROLE_VOICE)["name"] == "deepseek-directo"

    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "https://api.deepseek.com"},
                           role=pc.ROLE_VOICE)
    assert nxt["name"] == "aimlapi-failover"
    assert pc.pick(pc.ROLE_VOICE)["name"] == "aimlapi-failover"      # sticky: the next turn starts here


def test_note_failure_defaults_to_cluster_role_for_backward_compat(monkeypatch):
    """The original single caller (`connectors/meshkore/brain.py`) never passes `role` — it must keep hitting the
    cluster chain exactly as before."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert nxt["name"] == "aimlapi"


def test_a_voice_failure_does_not_burn_the_cluster_chain(monkeypatch):
    """The cooldown dict is shared by NAME (by design — same account, same outage), but a role mismatch on the
    HEALTH-STATE key/label must not happen: a voice failure records under "llm", never "cluster_brain"."""
    _cfg_fast(monkeypatch, providers=[
        {"name": "deepseek-directo", "base_url": "https://api.deepseek.com", "env": ["DEEPSEEK_API_KEY"]},
    ])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    from voice import health_state
    health_state.clear("cluster_brain")
    health_state.clear("llm")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "https://api.deepseek.com"},
                     role=pc.ROLE_VOICE)
    assert health_state.get("llm") is not None
    assert health_state.get("cluster_brain") is None


# ── V2-243: quedarse sin proveedor no es un tropiezo ─────────────────────────────────────────────────────────
# «Uf, se me ha ido un momento. ¿Me lo repites?» es la frase correcta ante un tropiezo: el siguiente intento
# puede ir bien. Con la cadena entera seca el siguiente intento falla igual, y el operador se queda
# repitiéndose a una máquina que no puede contestarle, sin enterarse de lo único que lo arregla — que es suyo y
# no del motor. Medido en producción el 2026-08-21: `Insufficient Balance` (DeepSeek, 402) dos veces, «SIN
# RELEVO disponible», y el canario del arnés MUDO en todos los turnos hasta que paró de medir.

def test_con_el_ultimo_escalon_seco_NO_queda_a_quien_preguntar(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert pc.pick() is not None
    pc.note_failure("Insufficient Balance", {"name": "z.ai", "base_url": "x"})
    assert pc.pick() is None, "sin este hecho, el turno no puede distinguir un tropiezo de una cadena seca"


def test_el_turno_de_VOZ_lo_pregunta_y_cambia_lo_que_dice():
    """GUARDA DE CABLEADO (V2-199): el hecho puede estar perfecto y el turno seguir diciendo «¿me lo repites?».
    Es lo que el operador OYE, así que es la parte que no puede quedarse sin probar."""
    import inspect
    import pathlib
    src = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    txt = src.read_text(encoding="utf-8")
    assert "_dry = _pchain1.pick(_pchain1.ROLE_VOICE) is None" in txt
    assert "sin proveedor de modelo" in txt
    assert 'send("Uf, se me ha ido un momento. ¿Me lo repites?" if not _dry else' in txt


# ── V2-244: callar un escalón es legítimo; callar QUE LO CALLAS, no ──────────────────────────────────────────
# El arnés lo aisló en dos líneas seguidas del log del 2026-08-21, con los proveedores reales:
#
#   02:39:41  memllm[i18n]: relevo a deepseek/deepseek-v4-pro @ aimlapi tras HTTP 402   ← i18n RELEVA y sigue
#   02:39:42  cerebro de voz: «titular» … sin cuota … · SIN RELEVO disponible           ← el cerebro NO
#
# La regla es del operador y NO se toca: en self-host la cadena de voz es solo el titular, porque quien se
# autohospeda paga sus APIs y no puede llevarse la sorpresa de que el agente se pase a un proveedor que él no
# eligió. Pero esa regla se escribió sobre el relevo por LATENCIA —todo el docstring habla de TTFT y de coste— y
# lo medido es otra cosa: el titular MUERTO deja el producto mudo con una clave viva sin usar. Esto no releva:
# hace que se pueda NOMBRAR, que es la diferencia entre «no puedo seguir» y «no puedo seguir, y esto lo arregla».

def _sin_lista_explicita(monkeypatch):
    """Self-host y SIN `fast.providers` — o sea, una instalación recién clonada.

    ⚠️ Sin este ayudante estos casos leen la config REAL de la máquina que corre la suite, y en la del operador
    `fast.providers` SÍ está puesta (titular directo + failover a AIMLAPI): el resultado sería vacío y el test
    verde por el motivo equivocado. Es la misma trampa que hizo leer como defecto de producto lo que era la
    config vacía de un sandbox (2026-08-21)."""
    from config import v2

    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False, raising=False)
    monkeypatch.setattr(v2, "get", lambda k: {}, raising=False)


def test_en_self_host_la_cadena_de_voz_es_SOLO_el_titular(monkeypatch):
    """La regla, tal cual, y sin ella el resto de este bloque no significa nada."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False, raising=False)
    monkeypatch.setenv("XAI_API_KEY", "k")
    assert all(t["name"] != "xai-fast" for t in pc._voice_chain())


def test_un_escalon_CALLADO_con_credencial_y_sano_se_puede_nombrar(monkeypatch):
    _sin_lista_explicita(monkeypatch)
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setenv("XAI_API_KEY", "k")
    assert "xai-fast" in pc.suppressed_relays()


def test_un_escalon_SIN_credencial_no_esta_callado_sino_que_NO_EXISTE(monkeypatch):
    """Nombrarlo mandaría al operador a activar algo para lo que no tiene cuenta."""
    _sin_lista_explicita(monkeypatch)
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    for var in ("XAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert pc.suppressed_relays() == []


def test_un_escalon_YA_EN_COOLDOWN_no_se_ofrece_como_salida(monkeypatch):
    """El caso REAL del 2026-08-21: `deepseek-directo` usa la MISMA cuenta que se quedó sin saldo. Ofrecerlo como
    remedio manda al operador a mirar un proveedor que también está caído."""
    _sin_lista_explicita(monkeypatch)
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_cooldown", {"deepseek-directo": time.time() + 3600})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    for var in ("XAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert pc.suppressed_relays() == []


def test_en_la_NUBE_no_hay_nada_callado(monkeypatch):
    """Allí la cadena sí trae relevos, así que un «escalón callado» sería una frase falsa."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: True, raising=False)
    monkeypatch.setenv("XAI_API_KEY", "k")
    assert pc.suppressed_relays() == []


def test_si_el_operador_YA_puso_su_lista_no_hay_nada_callado(monkeypatch):
    """Con `fast.providers` explícito manda él: decirle que le callamos algo sería mentira."""
    from config import v2

    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False, raising=False)
    monkeypatch.setattr(v2, "get", lambda k: {"providers": [{"name": "x"}]} if k == "fast" else {}, raising=False)
    monkeypatch.setenv("XAI_API_KEY", "k")
    assert pc.suppressed_relays() == []


def test_el_turno_de_voz_NOMBRA_lo_que_esta_callado():
    """GUARDA DE CABLEADO: es lo que el operador OYE. Sin esto, el hecho existe y no sale por ninguna boca."""
    import inspect
    import pathlib
    src = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    txt = src.read_text(encoding="utf-8")
    assert "_pchain2.suppressed_relays()" in txt
    assert "fast.providers" in txt
