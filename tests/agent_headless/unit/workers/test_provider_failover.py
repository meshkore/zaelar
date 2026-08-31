"""Brain Worker provider chain + automatic failover when a quota is exhausted.

Incident 2026-08-02: the Z.AI plan exhausted its WEEKLY quota midway through a search («[1310] Weekly/Monthly
Limit Exhausted. Your limit will reset at 2026-08-04»). Three failures at once: the worker died without failover, the
operator received the error text where the report was expected, and the alerts panel—which exists precisely to
warn about this—said nothing because the worker provider was not in any service map.

Operator rule: Claude Code is ALWAYS the driver; what fails over underneath is the
Anthropic-compatible endpoint, using SUBSCRIPTION plans (flat-rate), not pay-per-token.
"""
import time

import pytest

from nucleo.workers import providers as prov

# Reset date ALWAYS two days ahead of "now" (2026-08-09: a fixed date fell into the past once—
# "2026-08-04" became the PAST, and a cooldown with an expired reset date is considered available immediately,
# breaking relayed()/pick() in a cascade). Never hardcode an absolute date in a cooldown test.
RESET_DATE = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
REAL_429 = ("API Error: Request rejected (429) · [1310][Weekly/Monthly Limit Exhausted. "
            f"Your limit will reset at {RESET_DATE} 00:00:00]")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = prov.CooldownStore(prov._KV)
    fresh._loaded = True                                # without touching real state
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(prov, "_store", fresh)
    monkeypatch.setattr(prov, "_is_container", lambda: False)
    # The chain checks `os.environ` to determine which tier EXISTS. In the full suite, something loads the real
    # credential store before this file → a real `Z_AI_API_KEY` appeared and two tests failed solely due to ORDER
    # (they passed in isolation). Each test sets the credential environment, never the machine.
    for _var in {e for t in prov.KNOWN for e in t.get("env", ())}:
        monkeypatch.delenv(_var, raising=False)
    yield


def _cfg(monkeypatch, **over):
    import config.v2 as v2
    base = {"base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2"}
    base.update(over)
    monkeypatch.setattr(v2, "get", lambda k: base if k == "code_agent" else {})


# ── the chain only offers tiers that genuinely exist ─────────────────────────────────────────────────
def test_a_tier_without_credentials_is_not_offered(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    names = [t["name"] for t in prov.chain()]
    assert names[0] == "z.ai"                    # the configured one comes first
    assert "moonshot" not in names               # without a key it is not a tier, but a mirage
    assert names[-1] == "licencia-claude"        # the local licence, always last


def test_a_second_subscription_joins_the_chain(monkeypatch):
    """Two cheap subscriptions cover one another's weekly gap—without changing code, just by setting the key."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k2")
    # V2-497: primary + ONE failover (+ the local licence, which is not an API provider but the
    # lifeline for anyone self-hosting). Moonshot was removed: neither measured nor credentialed.
    assert [t["name"] for t in prov.chain()] == ["z.ai", "deepseek", "licencia-claude"]


def test_cloud_never_offers_the_browser_licence(monkeypatch):
    """There is no browser login in a container: offering the licence there would promise nonexistent failover."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setattr(prov, "_is_container", lambda: True)
    assert "licencia-claude" not in [t["name"] for t in prov.chain()]


def test_operator_can_order_the_chain_by_hand(monkeypatch):
    _cfg(monkeypatch, providers=[{"name": "deepseek", "base_url": "https://api.deepseek.com/anthropic",
                                  "env": ["DEEPSEEK_API_KEY"]},
                                 {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic",
                                  "env": ["Z_AI_API_KEY"]}])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k2")
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert [t["name"] for t in prov.chain()] == ["deepseek", "z.ai"]


# ── classify the failure: exhausted ≠ transient rate limit ───────────────────────────────────────────────
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


# ── failover ──────────────────────────────────────────────────────────────────────────────────────────────
def test_exhaustion_hands_over_and_respects_the_providers_own_reset_date(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert prov.pick()["name"] == "z.ai"

    nxt = prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert nxt["name"] == "licencia-claude"
    assert prov.pick()["name"] == "licencia-claude"          # the next spawn already starts on the failover
    # the cooldown comes from the DATE supplied by the provider, not an invented timeout
    assert prov._store._cooldown["z.ai"] == time.mktime(time.strptime(RESET_DATE, "%Y-%m-%d"))


def test_without_a_reset_date_it_retries_in_a_while(monkeypatch):
    """A QUOTA that does not say when it returns: wait half an hour and retry.

    The example was «insufficient credit», and V2-243 turned it into the OTHER case—a balance that does not return
    on its own—so this uses a genuine quota exhaustion. The test's intent is unchanged; it was the example that had
    two meanings."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure("quota exceeded", {"name": "z.ai", "base_url": "x"})
    assert time.time() < prov._store._cooldown["z.ai"] <= time.time() + prov._DEFAULT_COOLDOWN_S + 1


# ── V2-243: an exhausted BALANCE is not a quota ────────────────────────────────────────────────────────────
# Measured in production on 2026-08-21: DeepSeek `Insufficient Balance` (HTTP 402) twice, announced as
# «no quota until 21 Aug 03:02 · NO FAILOVER available». At 03:02 nothing would have changed—a balance does not
# replenish itself—and with the entire chain dry, the harness had to stop measuring. A quota tells the operator
# «wait»; a balance says «top up», and what it DOES depends on that distinction.

def test_un_saldo_agotado_se_reintenta_MUCHO_mas_tarde(monkeypatch):
    """Rewritten on 2026-08-27, NOT reverted. What it protected remains: an exhausted balance is penalized MORE than
    than an ordinary failure, because retrying frequently against an empty account burns one turn per round. What
    changes is the ceiling, and one measurement changes it: with six hours, the 402 at 18:55 kept the primary out
    past midnight; the operator topped up at 19:40 and the engine had no way to know, so it kept sending everything
    to the failover—and when that failover fell, the brain went SILENT with the healthy primary beside it. A top-up
    is invisible from here: the only way to detect it is to try again. Now the penalty remains greater than that for
    an undated quota, but fits within a probationary period.
    """
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure("API Error 402 Insufficient Balance", {"name": "z.ai", "base_url": "x"})
    until = prov._store._cooldown["z.ai"]
    assert until > time.time(), "un saldo agotado tiene que castigar algo"
    assert until <= time.time() + prov._DEPLETED_COOLDOWN_S + 1
    assert prov._DEPLETED_COOLDOWN_S <= 30 * 60, \
        "el castigo por saldo volvió a ser tan largo que una recarga no se nota"


def test_un_saldo_CON_fecha_de_reset_sigue_siendo_una_cuota(monkeypatch):
    """Sensitivity, and this is not theoretical: a flat-rate plan may say «insufficient credit … reset at …». If
    it announces when it returns, it returns on its own, and disabling it six hours too long loses the preferred tier."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    # The date is calculated, not written: with the literal "2026-08-30", this case worked until 23:33
    # on the 29th, after which the announced date was in the past, so the quarantine floor took over
    # and the case started measuring the opposite of what it says. A test with an embedded date
    # contains a time bomb.
    _manana = time.strftime("%Y-%m-%d", time.localtime(time.time() + 3 * 86400))
    prov.note_failure(f"insufficient credit, quota will reset at {_manana}",
                      {"name": "z.ai", "base_url": "x"})
    assert prov._store._cooldown["z.ai"] == time.mktime(time.strptime(_manana, "%Y-%m-%d")), \
        "con fecha anunciada manda la fecha: es el camino de la CUOTA, no el del saldo"


def test_el_aviso_DICE_recargar_y_no_una_hora_que_no_significa_nada(monkeypatch):
    """What is written here is what the operator reads in the panel, and what they do depends on it."""
    from voice import health_state
    dichos = []
    monkeypatch.setattr(health_state, "record", lambda *a, **k: dichos.append(a), raising=False)
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure("Insufficient Balance", {"name": "z.ai", "base_url": "x"})
    detalle = " ".join(str(x) for a in dichos for x in a)
    assert "SIN SALDO" in detalle and "recargar" in detalle
    assert "sin cuota hasta" not in detalle


def test_the_local_licence_is_never_put_in_cooldown(monkeypatch):
    """It has no API quota to exhaust; removing it from the chain would leave us without a last resort."""
    _cfg(monkeypatch, base_url="")
    assert prov.pick()["name"] == "licencia-claude"
    assert prov.note_failure(REAL_429) is None
    assert prov.pick()["name"] == "licencia-claude"


def test_env_for_worker_points_at_the_healthy_tier(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ddd")
    assert prov.env_for_worker()["ANTHROPIC_AUTH_TOKEN"] == "zzz"
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    env = prov.env_for_worker()
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "ddd"


def test_falling_back_to_the_licence_means_no_redirect(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert prov.env_for_worker() == {}          # sin ANTHROPIC_BASE_URL el CLI usa la licencia logueada


def test_clear_lets_the_operator_resume_after_topping_up(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "x"})
    prov.clear("z.ai")
    assert prov.pick()["name"] == "z.ai"


# ── and make sure the PANEL knows (what was missing) ───────────────────────────────────────────────────────
def test_the_alerts_panel_surfaces_an_exhausted_worker_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    from config import balances
    assert not [a for a in balances.worker_providers() if a["state"] == "error"]

    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "x"})
    rows = balances.worker_providers()
    bad = [r for r in rows if r["state"] == "error"]
    assert bad and bad[0]["key"] == "worker:z.ai" and "cuota" in bad[0]["detail"]
    # «PRÓXIMO», not «EN USO» (2026-08-10): this assertion said «EN USO», precisely the inaccurate meaning
    # that made the panel lie—it marked a tier as working when it was only the candidate. What still matters
    # is checked here: after failover, we see WHO takes command.
    assert [r for r in rows if r["state"] == "ok" and "PRÓXIMO" in r["detail"]]


def test_no_tier_left_is_its_own_loud_alert(monkeypatch):
    """Without any failover, the operator must see it BEFORE requesting a task that cannot run."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setattr(prov, "_is_container", lambda: True)      # cloud: sin licencia local
    prov.note_failure(REAL_429, {"name": "z.ai", "base_url": "x"})
    from config import balances
    assert any(r["key"] == "worker:sin-relevo" for r in balances.worker_providers())


# ── the MODEL travels with the tier (otherwise failover does not fail over) ───────────────────────────────
def test_the_model_belongs_to_its_tier_not_to_the_global_config(monkeypatch):
    """First real failover (2026-08-02): the endpoint changed but it kept requesting `glm-5.2`, and the CLI died with
    «There's an issue with the selected model (glm-5.2)». `code_agent.model` exists only in ITS provider."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k2")
    by_name = {t["name"]: t for t in prov.chain()}
    assert by_name["z.ai"]["model"] == "glm-5.3"          # el de la tabla
    assert by_name["deepseek"]["model"] == "deepseek-v4-flash"   # el suplente lleva EL SUYO, de la tabla
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
    """Regression: tightening the model-per-tier behavior broke the usual PER-INVOCATION model
    (`code_agent.model_code`), which must continue to take precedence until failover occurs."""
    from nucleo import dispatch
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {})              # sin proveedor externo configurado
    monkeypatch.setattr(v2, "code_agent_model", lambda k: "modelo-de-tarea")
    assert prov.relayed() is False
    assert dispatch._model_for("code") == "modelo-de-tarea"


# ── BLIND ≠ DOWN: the provider's TOOLS are exhausted without the model failing (2026-08-10) ─────────────────
# Finding from a real e2e test (reported by another session while running a sailboat search): a provider's plan
# is exhausted in TWO different ways that until now were treated as one thing.
#
#   · el MODELO se agota (`[1308] Usage limit reached for 5 hour`) → la llamada falla → relevo. Ya funcionaba.
#   · las TOOLS INTEGRADAS del proveedor se agotan (`[1310] … for web_search_prime`) → **la llamada al modelo no
#     fails**. The worker keeps reasoning but is BLIND: it cannot search or read a page. The error arrives inside
#     a `tool_result`, which was discarded as internal noise → no alert, failover, or trace. The worker appeared
#     sano y entregaba conclusiones sin material.
#
# It is this system's most costly failure mode: a DECEPTIVE state. These tests lock in the distinction.
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
    # The culprit is the tier on which THAT session was running, not the chain's current first tier: after
    # failover they differ, and naming the wrong one sends the operator to inspect the provider that works.
    detail = prov.note_tool_blindness(TOOL_429, tool="web_search_prime", provider="z.ai")
    assert "z.ai" in detail
    assert "2026-08-30" in detail, "la fecha de reset la da el propio proveedor: es lo que dice cuándo vuelve a ver"
    assert "no puede buscar" in detail.lower() or "NO puede buscar" in detail
    rec = health_state.get("worker_tools")
    assert rec and rec["kind"] == "credit"


def test_going_blind_does_NOT_put_the_model_in_cooldown(monkeypatch):
    """Its tools are exhausted, its model is not. Penalizing the model would shut down a provider that works for
    everything else—and that policy is the operator's decision, not a side effect of instrumentation."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    prov._store._cooldown.clear()
    prov.note_tool_blindness(TOOL_429, tool="web_search_prime", provider="z.ai")
    assert prov._store._cooldown == {}, "la ceguera no releva de escalón"
    assert (prov.pick() or {}).get("name") == "z.ai", "el proveedor sigue sirviendo el modelo"


def test_the_panel_gets_its_own_row_for_blindness(monkeypatch):
    """Its own row, not the «provider without quota» row: it is a different problem with a different solution. Without
    it, the panel said «all ok» while the worker delivered conclusions without being able to look at anything."""
    from voice import health_state
    import config.balances as balances

    health_state.clear("worker_tools")
    assert not [r for r in balances.worker_providers() if r["key"] == "worker:tools"]
    prov.note_tool_blindness(TOOL_429, tool="web_search_prime", provider="z.ai")
    rows = [r for r in balances.worker_providers() if r["key"] == "worker:tools"]
    assert rows and rows[0]["state"] == "error"
    assert "z.ai" in rows[0]["detail"]
    health_state.clear("worker_tools")


# ── AN EXHAUSTED WINDOW IS NOT A RATE LIMIT (2026-08-10) ─────────────────────────────────────────────────────
# Finding from a real e2e test: the 429 `[1308] Usage limit reached for 5 hour … reset at 23:15:37` fell into `rate`, and
# `rate` does NOT set a cooldown or fail over. Measured consequence: the cooldown that was set came from another
# path and expired at 16:11—SEVEN HOURS before the reset announced by the provider itself. From then on, each new
# worker chose that tier, hit a 429, and burned its retry, one after another, until 23:15.
#
# Two linked causes, and both are necessary: classification (it is not transient) and READING THE TIME
# (`_RESET_RE` captured only the DATE, so a time on the same day resolved to the past midnight → an epoch in
# the past → the cooldown was born expired and fell back to the half-hour floor).
# The reset time is CALCULATED (now + 3 h) instead of being fixed. It was fixed at «23:15:37», which made
# que `test_the_window_limit_actually_relays_and_waits` —que comprueba que el cooldown llega a la hora anunciada y
# not the half-hour floor—depended on when the suite was run: green in the morning, red from
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
    """At 23:50, a «reset at 00:30» is tomorrow, not 23 hours ago."""
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


# ── «IN USE» ≠ «THE ONE THAT WOULD BE CHOSEN» ───────────────────────────────────────────────────────────────
def test_the_panel_does_not_claim_a_provider_is_working_when_it_is_not(monkeypatch):
    """The row said «IN USE · available» for a tier serving nobody: after failover, the failover tier is working,
    and the one that would be chosen becomes the first again when its cooldown expires. These are two different
    questions, and the panel must distinguish them."""
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


# ── V2-309: «session limit» is an exhausted WINDOW, and its time comes in whatever form the provider uses ────
#
# Measured on 2026-08-25 04:36: the worker died instantly with «You've hit your session limit · resets 6:10am
# (Europe/Madrid)», `classify_failure` devolvió "" (no es fallo de proveedor) → sin cooldown y sin relevo, así
# que CADA worker nuevo iba al mismo escalón muerto y moría igual. La ronda acabó con la hoja vacía y zaelar
# diciendo la verdad («se cortó por el límite de sesión») contra un estado que decía EN CURSO.

@pytest.mark.parametrize("text", [
    "You've hit your session limit · resets 6:10am (Europe/Madrid)",
    "You have reached your session limit, resets at 06:10",
    "Session limit exceeded — will reset at 2026-08-25 06:10",
])
def test_a_session_limit_is_an_exhausted_window(text):
    assert prov.classify_failure(text) == "exhausted", \
        "sin clasificarlo no hay cooldown ni relevo: cada worker nuevo muere contra el mismo escalón"


def test_a_sentence_that_merely_mentions_a_session_limit_is_not_a_failure():
    """Sensitivity: the pattern requires the verb indicating it was reached or its reset—a sentence that mentions
    the limit («session limit is configurable in settings») must not bring down a healthy tier."""
    assert prov.classify_failure("session limit is configurable in settings") == ""


def test_the_reset_hour_is_read_even_written_as_6_10am():
    """Without reading the time, the cooldown fell to the default floor (30 min) and another worker died against the
    same limit before it was replenished. `6:10am` is how the CLI writes it: one digit with the suffix attached."""
    import time as _t
    got = prov._reset_epoch("You've hit your session limit · resets 6:10am (Europe/Madrid)")
    assert got, "la hora no se leyó"
    assert _t.localtime(got).tm_hour == 6 and _t.localtime(got).tm_min == 10
    assert got > _t.time(), "un cooldown que nace vencido no protege de nada"


def test_the_iso_and_24h_forms_still_work():
    """The form that already worked is untouched while broadening the pattern."""
    import time as _t
    iso = prov._reset_epoch("limit will reset at 2026-08-25 06:10")
    assert _t.localtime(iso).tm_hour == 6
    h24 = prov._reset_epoch("Usage limit reached, resets 23:45")
    assert _t.localtime(h24).tm_hour == 23 and _t.localtime(h24).tm_min == 45
