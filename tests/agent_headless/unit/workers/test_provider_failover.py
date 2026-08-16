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
    fresh = prov.CooldownStore(prov._KV)
    fresh._loaded = True                                # sin tocar la memoria real
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(prov, "_store", fresh)
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
    assert prov._store._cooldown["z.ai"] == time.mktime(time.strptime(RESET_DATE, "%Y-%m-%d"))


def test_without_a_reset_date_it_retries_in_a_while(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure("insufficient credit", {"name": "z.ai", "base_url": "x"})
    assert time.time() < prov._store._cooldown["z.ai"] <= time.time() + prov._DEFAULT_COOLDOWN_S + 1


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
    # «PRÓXIMO», no «EN USO» (2026-08-10): esta aserción decía «EN USO» y era precisamente el significado
    # impreciso que hacía mentir al panel — marcaba como trabajando a un escalón que solo era el candidato. Lo que
    # importa aquí sigue comprobándose: tras el relevo se ve QUIÉN toma el mando.
    assert [r for r in rows if r["state"] == "ok" and "PRÓXIMO" in r["detail"]]


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


# ── CIEGO ≠ CAÍDO: las TOOLS del proveedor se agotan sin que falle el modelo (2026-08-10) ─────────────────────
# Hallazgo de una prueba e2e real (informada por otra sesión mientras corría una búsqueda de veleros): el plan de
# un proveedor se agota por DOS vías distintas que hasta hoy se trataban como una sola cosa.
#
#   · el MODELO se agota (`[1308] Usage limit reached for 5 hour`) → la llamada falla → relevo. Ya funcionaba.
#   · las TOOLS INTEGRADAS del proveedor se agotan (`[1310] … for web_search_prime`) → **la llamada al modelo no
#     falla**. El worker sigue razonando pero CIEGO: no puede buscar ni leer una página. El error llega dentro de
#     un `tool_result`, que se descartaba como ruido interno → ni alerta, ni relevo, ni rastro. El worker parecía
#     sano y entregaba conclusiones sin material.
#
# Es el modo de fallo más caro de este sistema: un estado que ENGAÑA. Estos tests fijan la distinción.
TOOL_429 = ('API Error: 429 {"error":{"code":"1310","message":"Weekly/Monthly Limit Exhausted for '
            'web_search_prime. Your limit will reset at 2026-08-30"}}')
MODEL_429 = ('API Error: 429 {"error":{"code":"1308","message":"Usage limit reached for 5 hour, '
             'please try again later"}}')


def test_a_tool_quota_and_a_model_quota_are_not_the_same_thing():
    assert prov.classify_tool_failure(TOOL_429) == "blind"
    assert prov.classify_tool_failure(MODEL_429) == "", (
        "un 429 del MODELO no es ceguera: es el caso que ya releva `note_failure`, y confundirlos daría una "
        "alerta equivocada y un cooldown injusto")
    assert prov.classify_tool_failure("File not found: /tmp/x") == ""
    assert prov.classify_tool_failure("") == ""


def test_going_blind_raises_an_alert_and_names_the_right_provider(monkeypatch):
    from voice import health_state

    health_state.clear("worker_tools")
    # El culpable es el escalón con el que corría ESA sesión, no el primero de la cadena ahora mismo: tras un
    # relevo son distintos, y nombrar al equivocado manda al operador a mirar el proveedor que sí funciona.
    detail = prov.note_tool_blindness(TOOL_429, tool="web_search_prime", provider="z.ai")
    assert "z.ai" in detail
    assert "2026-08-30" in detail, "la fecha de reset la da el propio proveedor: es lo que dice cuándo vuelve a ver"
    assert "no puede buscar" in detail.lower() or "NO puede buscar" in detail
    rec = health_state.get("worker_tools")
    assert rec and rec["kind"] == "credit"


def test_going_blind_does_NOT_put_the_model_in_cooldown(monkeypatch):
    """Sus tools están agotadas, su modelo no. Castigar al modelo apagaría un proveedor que funciona para todo lo
    demás — y esa política es decisión del operador, no un efecto colateral de instrumentar."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov._store._cooldown.clear()
    prov.note_tool_blindness(TOOL_429, tool="web_search_prime", provider="z.ai")
    assert prov._store._cooldown == {}, "la ceguera no releva de escalón"
    assert (prov.pick() or {}).get("name") == "z.ai", "el proveedor sigue sirviendo el modelo"


def test_the_panel_gets_its_own_row_for_blindness(monkeypatch):
    """Fila propia, no la de «proveedor sin cuota»: es otro problema con otra solución. Sin ella el panel decía
    «todo ok» mientras el worker entregaba conclusiones sin haber podido mirar nada."""
    from voice import health_state
    import config.balances as balances

    health_state.clear("worker_tools")
    assert not [r for r in balances.worker_providers() if r["key"] == "worker:tools"]
    prov.note_tool_blindness(TOOL_429, tool="web_search_prime", provider="z.ai")
    rows = [r for r in balances.worker_providers() if r["key"] == "worker:tools"]
    assert rows and rows[0]["state"] == "error"
    assert "z.ai" in rows[0]["detail"]
    health_state.clear("worker_tools")


# ── UNA VENTANA AGOTADA NO ES UN RATE-LIMIT (2026-08-10) ──────────────────────────────────────────────────────
# Hallazgo de un e2e real: el 429 `[1308] Usage limit reached for 5 hour … reset at 23:15:37` caía en `rate`, y
# `rate` NO pone cooldown ni releva. Consecuencia medida: el cooldown que sí se puso venía de otro camino y expiró
# a las 16:11 — SIETE HORAS antes del reset que el propio proveedor anuncia. A partir de ahí, cada worker nuevo
# elegía ese escalón, se comía un 429 y quemaba su reintento, uno detrás de otro, hasta las 23:15.
#
# Dos causas encadenadas, y las dos hacen falta: la clasificación (no es pasajero) y la LECTURA DE LA HORA
# (`_RESET_RE` solo capturaba la FECHA, así que una hora del mismo día se resolvía a medianoche pasada → epoch en
# el pasado → el cooldown nacía vencido y caía al suelo de media hora).
# La hora de reset se CALCULA (ahora + 3 h) en vez de estar clavada. Estuvo clavada a las «23:15:37», y eso hacía
# que `test_the_window_limit_actually_relays_and_waits` —que comprueba que el cooldown llega a la hora anunciada y
# no al suelo de media hora— dependiera de la hora a la que corres la suite: verde por la mañana, rojo a partir de
# las 22:15 todas las noches. El test habla del MECANISMO, no del reloj de quien lo lanza.
_RESET_AT = time.strftime("%H:%M:%S", time.localtime(time.time() + 3 * 3600))
WINDOW_429 = ('API Error: 429 {"error":{"code":"1308","message":"Usage limit reached for 5 hour. '
              f'Your limit will reset at {_RESET_AT}"}}')


def test_a_window_limit_that_announces_its_reset_is_exhausted_not_rate():
    assert prov.classify_failure(WINDOW_429) == "exhausted", (
        "esperar a una hora concreta no se arregla reintentando en dos segundos: hay que relevar")
    assert prov.classify_failure("HTTP 429 Too Many Requests") == "rate", (
        "un 429 pelado SÍ es pasajero — no se puede castigar un escalón por una ráfaga")
    assert prov.classify_failure("connection reset by peer") == ""


def test_a_bare_time_resets_today_not_at_midnight_past():
    import time

    e = prov._reset_epoch(WINDOW_429)
    assert e > time.time(), "un reset anunciado para hoy NO puede resolverse a un instante ya pasado"
    assert time.strftime("%H:%M", time.localtime(e)) == _RESET_AT[:5]


def test_a_bare_time_already_gone_rolls_to_tomorrow(monkeypatch):
    """A las 23:50 un «reset at 00:30» es de mañana, no de hace 23 horas."""
    import time as _t

    e = prov._reset_epoch("your limit will reset at 00:30")
    assert e > _t.time()
    assert _t.strftime("%H:%M", _t.localtime(e)) == "00:30"


def test_the_window_limit_actually_relays_and_waits(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov._store._cooldown.clear()
    nxt = prov.note_failure(WINDOW_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert nxt and nxt["name"] != "z.ai", "hay que relevar, no reintentar contra el mismo"
    import time
    assert prov._store._cooldown["z.ai"] > time.time() + 3600, (
        "el cooldown tiene que llegar a la hora anunciada, no a los 5-30 minutos del suelo: si no, todos los "
        "workers de las próximas horas vuelven a elegirlo y queman su reintento")
    prov._store._cooldown.clear()


# ── «EN USO» ≠ «EL QUE SE ELEGIRÍA» ──────────────────────────────────────────────────────────────────────────
def test_the_panel_does_not_claim_a_provider_is_working_when_it_is_not(monkeypatch):
    """La fila decía «EN USO · disponible» de un escalón que no estaba sirviendo a nadie: tras un relevo, el que
    trabaja es el de relevo, y el que se elegiría vuelve a ser el primero en cuanto expira su cooldown. Son dos
    preguntas distintas y el panel tiene que distinguirlas."""
    import config.balances as balances

    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov._store._cooldown.clear()
    monkeypatch.setattr(prov, "_serving", lambda: set())          # nadie trabajando
    rows = {r["key"]: r for r in balances.worker_providers()}
    assert "EN USO" not in rows["worker:z.ai"]["detail"], "sin sesiones vivas, nadie está «EN USO»"
    assert "PRÓXIMO" in rows["worker:z.ai"]["detail"], "…pero sí es el que se elegiría, y eso también se dice"

    monkeypatch.setattr(prov, "_serving", lambda: {"licencia-claude"})
    rows = {r["key"]: r for r in balances.worker_providers()}
    assert "EN USO" in rows["worker:licencia-claude"]["detail"], "el que trabaja de verdad es el que va marcado"
    assert "EN USO" not in rows["worker:z.ai"]["detail"]
