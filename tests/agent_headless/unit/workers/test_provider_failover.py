"""Cadena de proveedores del Brain Worker + relevo automático por cuota agotada.

Incidente 2026-08-02: el plan de Z.AI agotó su cuota SEMANAL en mitad de una búsqueda («[1310] Weekly/Monthly
Limit Exhausted. Your limit will reset at 2026-08-04»). Tres fallos a la vez: el worker murió sin relevo, al
operador se le entregó el texto del error donde esperaba su informe, y el panel de alertas —que existe justo para
avisar de esto— no dijo nada porque el proveedor de los workers no estaba en ningún mapa de servicios.

Regla del operador: quien conduce es SIEMPRE Claude Code; lo que se releva por debajo es el endpoint
Anthropic-compatible, y con planes de SUSCRIPCIÓN (forfait), no pago por token.
"""
import time

import pytest

from nucleo.workers import providers as prov

# Fecha de reset SIEMPRE 2 días por delante de "ahora" (2026-08-09: una fecha fija ya se quedó atrás una vez —
# "2026-08-04" pasó a estar en el PASADO, y un cooldown con fecha de reset ya vencida se considera disponible al
# instante, tumbando relayed()/pick() en cascada). Nunca hardcodear una fecha absoluta en un test de cooldown.
RESET_DATE = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
REAL_429 = ("API Error: Request rejected (429) · [1310][Weekly/Monthly Limit Exhausted. "
            f"Your limit will reset at {RESET_DATE} 00:00:00]")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(prov, "_cooldown", {})
    monkeypatch.setattr(prov, "_loaded", True)          # sin tocar la memoria real
    monkeypatch.setattr(prov, "_save", lambda: None)
    monkeypatch.setattr(prov, "_is_container", lambda: False)
    # La cadena mira `os.environ` para saber qué escalón EXISTE. En la batería completa alguien carga el
    # credential store real antes que este fichero → aparecía una `Z_AI_API_KEY` de verdad y dos tests fallaban
    # solo por el ORDEN (pasaban sueltos). El entorno de credenciales lo fija cada test, nunca la máquina.
    for _var in {e for t in prov.KNOWN for e in t.get("env", ())}:
        monkeypatch.delenv(_var, raising=False)
    yield


def _cfg(monkeypatch, **over):
    import config.v2 as v2
    base = {"base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2"}
    base.update(over)
    monkeypatch.setattr(v2, "get", lambda k: base if k == "code_agent" else {})


# ── la cadena solo ofrece escalones que existen de verdad ─────────────────────────────────────────────────
def test_a_tier_without_credentials_is_not_offered(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    names = [t["name"] for t in prov.chain()]
    assert names[0] == "z.ai"                    # el configurado va primero
    assert "moonshot" not in names               # sin key no es un escalón, es un espejismo
    assert names[-1] == "licencia-claude"        # la licencia local, siempre la última


def test_a_second_subscription_joins_the_chain(monkeypatch):
    """Dos suscripciones baratas cubren el hueco semanal de una — sin tocar código, solo poniendo la key."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("MOONSHOT_API_KEY", "k2")
    assert [t["name"] for t in prov.chain()] == ["z.ai", "moonshot", "licencia-claude"]


def test_cloud_never_offers_the_browser_licence(monkeypatch):
    """En un contenedor no hay login de navegador: ofrecer la licencia ahí sería prometer un relevo inexistente."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setattr(prov, "_is_container", lambda: True)
    assert "licencia-claude" not in [t["name"] for t in prov.chain()]


def test_operator_can_order_the_chain_by_hand(monkeypatch):
    _cfg(monkeypatch, providers=[{"name": "moonshot", "base_url": "https://api.moonshot.ai/anthropic",
                                  "env": ["MOONSHOT_API_KEY"]},
                                 {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic",
                                  "env": ["Z_AI_API_KEY"]}])
    monkeypatch.setenv("MOONSHOT_API_KEY", "k2")
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert [t["name"] for t in prov.chain()] == ["moonshot", "z.ai"]


# ── clasificar la avería: agotado ≠ rate-limit pasajero ───────────────────────────────────────────────────
def test_the_real_incident_is_read_as_exhausted():
    assert prov.classify_failure(REAL_429) == "exhausted"


def test_a_passing_rate_limit_does_not_burn_a_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert prov.classify_failure("429 Too Many Requests") == "rate"
    assert prov.note_failure("429 Too Many Requests") is None     # se reintenta solo, no se releva
    assert prov.pick()["name"] == "z.ai"


def test_a_task_failure_is_not_a_provider_failure():
    assert prov.classify_failure("no encontré ningún parque acuático abierto hoy") == ""
    assert prov.note_failure("no encontré ningún parque acuático abierto hoy") is None


# ── el relevo ────────────────────────────────────────────────────────────────────────────────────────────
def test_exhaustion_hands_over_and_respects_the_providers_own_reset_date(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert prov.pick()["name"] == "z.ai"

    nxt = prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert nxt["name"] == "licencia-claude"
    assert prov.pick()["name"] == "licencia-claude"          # el siguiente spawn ya arranca en el relevo
    # el cooldown sale de la FECHA que da el proveedor, no de un timeout inventado
    assert prov._cooldown["z.ai"] == time.mktime(time.strptime(RESET_DATE, "%Y-%m-%d"))


def test_without_a_reset_date_it_retries_in_a_while(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure("insufficient credit", {"name": "z.ai", "base_url": "x"})
    assert time.time() < prov._cooldown["z.ai"] <= time.time() + prov._DEFAULT_COOLDOWN_S + 1


def test_the_local_licence_is_never_put_in_cooldown(monkeypatch):
    """No tiene cuota de API que agotar; sacarla de la cadena nos dejaría sin último recurso."""
    _cfg(monkeypatch, base_url="")
    assert prov.pick()["name"] == "licencia-claude"
    assert prov.note_failure(REAL_429) is None
    assert prov.pick()["name"] == "licencia-claude"


def test_env_for_worker_points_at_the_healthy_tier(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    monkeypatch.setenv("MOONSHOT_API_KEY", "mmm")
    assert prov.env_for_worker()["ANTHROPIC_AUTH_TOKEN"] == "zzz"
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    env = prov.env_for_worker()
    assert env["ANTHROPIC_BASE_URL"] == "https://api.moonshot.ai/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "mmm"


def test_falling_back_to_the_licence_means_no_redirect(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert prov.env_for_worker() == {}          # sin ANTHROPIC_BASE_URL el CLI usa la licencia logueada


def test_clear_lets_the_operator_resume_after_topping_up(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "x"})
    prov.clear("z.ai")
    assert prov.pick()["name"] == "z.ai"


# ── y que el PANEL se entere (lo que faltaba) ─────────────────────────────────────────────────────────────
def test_the_alerts_panel_surfaces_an_exhausted_worker_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    from config import balances
    assert not [a for a in balances.worker_providers() if a["state"] == "error"]

    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "x"})
    rows = balances.worker_providers()
    bad = [r for r in rows if r["state"] == "error"]
    assert bad and bad[0]["key"] == "worker:z.ai" and "cuota" in bad[0]["detail"]
    assert [r for r in rows if r["state"] == "ok" and "EN USO" in r["detail"]]


def test_no_tier_left_is_its_own_loud_alert(monkeypatch):
    """Sin ningún relevo el operador tiene que verlo ANTES de pedir una tarea que no va a poder correr."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setattr(prov, "_is_container", lambda: True)      # cloud: sin licencia local
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "x"})
    from config import balances
    assert any(r["key"] == "worker:sin-relevo" for r in balances.worker_providers())


# ── el MODELO viaja con el escalón (si no, el relevo no releva) ───────────────────────────────────────────
def test_the_model_belongs_to_its_tier_not_to_the_global_config(monkeypatch):
    """Primer relevo real (2026-08-02): cambió el endpoint pero siguió pidiendo `glm-5.2`, y el CLI murió con
    «There's an issue with the selected model (glm-5.2)». `code_agent.model` solo existe en SU proveedor."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("MOONSHOT_API_KEY", "k2")
    by_name = {t["name"]: t for t in prov.chain()}
    assert by_name["z.ai"]["model"] == "glm-5.2"          # el configurado sí lo lleva
    assert by_name["moonshot"]["model"] == ""             # otro proveedor → su propio default
    assert by_name["licencia-claude"]["model"] == ""      # la licencia → el default del CLI


def test_dispatch_asks_the_active_tier_for_the_model(monkeypatch):
    from nucleo import dispatch
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert dispatch._model_for("generic") == "glm-5.2"
    assert prov.relayed() is False
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert prov.relayed() is True
    assert dispatch._model_for("generic") == ""          # relevado a la licencia: sin --model


def test_without_a_relay_the_per_invocation_model_still_rules(monkeypatch):
    """Regresión: al endurecer el modelo-por-escalón se rompió el modelo POR INVOCACIÓN de siempre
    (`code_agent.model_code`), que debe seguir mandando mientras no haya habido relevo."""
    from nucleo import dispatch
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {})              # sin proveedor externo configurado
    monkeypatch.setattr(v2, "code_agent_model", lambda k: "modelo-de-tarea")
    assert prov.relayed() is False
    assert dispatch._model_for("code") == "modelo-de-tarea"
