"""Provider chain for the CLUSTER BRAIN + automatic failover (2026-08-03).

Sibling of tests/agent_headless/unit/workers/test_provider_failover.py: same class of incident (a Z.AI 429 without
failover), but on the cluster turn side (`connectors/meshkore/brain.py` → `nucleo.flash.cluster.respond` →
`FastClient`), not the brain workers' CLI. Before this, the tier was fixed ONCE when the server started and the
heartbeat repeated the SAME broken call in a loop — "cluster brain turn failed: 429" over and over, with no failover
and without the panel saying anything.
"""
import time

import pytest

from nucleo.flash import provider_chain as pc

# ALWAYS 2 days ahead of "now" — never an absolute literal (one fell behind: "2026-08-04" became
# past and a cooldown with an already-expired reset is considered available immediately, breaking pick()).
RESET_DATE = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
REAL_429_EXHAUSTED = ("429 Too Many Requests — {\"error\":{\"message\":"
                      f"\"[1310][Weekly/Monthly Limit Exhausted. Your limit will reset at {RESET_DATE} 00:00:00]\"}}}}")
BARE_429 = "429 Too Many Requests"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True                              # without touching real memory
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    # `DEEPSEEK_API_KEY` entered this list on 2026-08-30 and this is not cosmetic: when the chain's primary moved
    # to DeepSeek (V2-497), an ENVIRONMENT key —the operator's or another suite's— bought a tier that these cases
    # assume is absent. They passed alone and failed in the full map, which is what a test that measures its
    # environment looks like.
    for _var in ("Z_AI_API_KEY", "DEEPSEEK_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "AIMLAPI_KEY",
                 "XAI_API_KEY", "GROQ_API_KEY", "MOONSHOT_API_KEY",
                 "MESHKORE_MISSION_MODEL", "ASSISTANT_LLM_MODEL", "LLM_MODEL", "MESHKORE_MISSION_MODEL_ZAI"):
        monkeypatch.delenv(_var, raising=False)
    yield


def _cfg(monkeypatch, providers=None):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": providers or []} if k == "cluster" else {})


# ── zero-config: the default chain uses the credentials present, in the SAME order as before ──────────
def test_la_cadena_de_voz_NO_OFRECE_ZAI_por_norma(monkeypatch):
    """OPERATOR RULE (2026-08-30): «the Z.AI provider is only for the Brain Worker, to be used
    inside Claude Code; it is not a failover for anything else and must not be used in any other part
    of the agent».

    This chain is used by the VOICE brain, the brief composer, and the cluster brain — none of them is a
    worker. Until 2026-08-30 it carried BOTH Z.AI wallets (plan via `api/anthropic` and credits via
    `paas/v4`, V2-462) and they were consumed automatically by failover: that is how the balance of a wallet
    the operator had not authorized for this was reduced.

    The key is SET deliberately: what is being fixed is that the absence is a DECISION, not a missing
    credential."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k2")
    monkeypatch.setenv("AIMLAPI_KEY", "k3")
    # ONE SINGLE FAILOVER (operator rule, 2026-08-30): primary + backup, and that's it.
    assert [t["name"] for t in pc.chain()] == ["deepseek-directo", "aimlapi-failover"]
    assert not any("z.ai" in (t.get("base_url") or "") for t in pc.chain())


def test_a_tier_without_credentials_is_not_offered(monkeypatch):
    """Without a credential there is no tier, only a mirage. And with Z.AI set and NO other credential, the voice
    chain stays EMPTY — the rule above viewed from the other side: that key no longer buys a tier here."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert [t["name"] for t in pc.chain()] == []


def test_explicit_llm_override_sigue_mandando(monkeypatch):
    """An explicit `LLM_BASE_URL`/`LLM_API_KEY` —the operator plugging in an endpoint by hand— still goes
    first. What changes from before is whom it moves ahead of: no longer Z.AI, which is absent."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("LLM_API_KEY", "k2")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.aimlapi.com/v1")
    assert [t["name"] for t in pc.chain()][0] == "endpoint-del-operador"


def test_operator_can_order_the_chain_by_hand(monkeypatch):
    _cfg(monkeypatch, providers=[
        {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"]},
        {"name": "xai", "base_url": "https://api.x.ai/v1", "env": ["XAI_API_KEY"]},
    ])
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("XAI_API_KEY", "z")
    assert [t["name"] for t in pc.chain()] == ["groq", "xai"]


# ── classify the failure: exhausted ≠ transient rate limit (same rule as the worker sibling) ─────────────
def test_a_passing_rate_limit_does_not_burn_a_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert pc.classify_failure(BARE_429) == "rate"
    assert pc.note_failure(BARE_429) is None            # retry it on its own; do not fail over
    assert pc.pick()["name"] == "deepseek-directo"


def test_a_task_failure_is_not_a_provider_failure():
    assert pc.classify_failure("no encontré ningún parque acuático abierto hoy") == ""
    assert pc.note_failure("no encontré ningún parque acuático abierto hoy") is None


# ── failover ─────────────────────────────────────────────────────────────────────────────────────────────
def test_exhaustion_hands_over_and_respects_the_providers_own_reset_date(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    assert pc.pick()["name"] == "deepseek-directo"

    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "https://api.deepseek.com"})
    assert nxt["name"] == "aimlapi-failover"
    assert pc.pick()["name"] == "aimlapi-failover"          # el siguiente turno ya arranca en el relevo (STICKY)
    assert pc._store._cooldown["deepseek-directo"] == time.mktime(time.strptime(RESET_DATE, "%Y-%m-%d"))


def test_without_a_reset_date_it_retries_in_a_while(monkeypatch):
    """A QUOTA that does not say when it returns: retry after half an hour.

    The example was «insufficient credit» and V2-243 turned it into the OTHER case —a balance, which does not
    return on its own—, so this uses a genuine quota exhaustion. The test's intent does not change; the example
    was what had two meanings."""
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pc.note_failure("quota exceeded", {"name": "deepseek-directo", "base_url": "x"})
    assert time.time() < pc._store._cooldown["deepseek-directo"] <= time.time() + pc._DEFAULT_COOLDOWN_S + 1


# ── V2-243: an exhausted BALANCE is not a quota ────────────────────────────────────────────────────────────────
# Measured in production on 2026-08-21: DeepSeek's `Insufficient Balance` (HTTP 402) twice, announced as
# «no quota until 21 Aug 03:02 · NO FAILOVER available». At 03:02 nothing would happen — a balance does not
# replenish itself—, and with the entire chain dry the harness had to stop measuring. A quota tells the operator
# «wait»; a balance tells them «top up», and what it DOES depends on that distinction.

def test_un_saldo_agotado_se_reintenta_MUCHO_mas_tarde(monkeypatch):
    """Rewritten on 2026-08-27, NOT reverted. What it protected remains: an exhausted balance is penalized MORE than
    an ordinary failure, because retrying frequently against an empty account burns one turn per round. What
    changes is the ceiling, and one measurement changed it: with six hours, the 402 at 18:55 kept the primary out
    past midnight; the operator topped up at 19:40 and the engine had no way to know, so it kept sending everything
    to the failover — and when that failover went down, the brain went SILENT with a healthy primary beside it.
    A top-up is invisible from here: the only way to see it is to try again. The penalty is still greater than
    that for an undated quota, but fits within a probationary period.
    """
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pc.note_failure("API Error 402 Insufficient Balance", {"name": "deepseek-directo", "base_url": "x"})
    until = pc._store._cooldown["deepseek-directo"]
    assert until > time.time(), "un saldo agotado tiene que castigar algo"
    assert until <= time.time() + pc._DEPLETED_COOLDOWN_S + 1
    assert pc._DEPLETED_COOLDOWN_S <= 30 * 60, \
        "the balance penalty became so long again that a top-up is not noticed"


def test_un_saldo_CON_fecha_de_reset_sigue_siendo_una_cuota(monkeypatch):
    """Sensitivity, and not theoretical: a flat-rate plan may say «insufficient credit … reset at …». If
    it announces when it returns, it returns on its own, and disabling it six hours too long loses the preferred tier."""
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    # The date is calculated, not written: with the literal "2026-08-30" this case worked until 23:33
    # on the 29th, after which the announced date was in the past, so the quarantine floor took over and the case
    # started measuring the opposite of what it says. A test with a date inside it contains a time bomb.
    _manana = time.strftime("%Y-%m-%d", time.localtime(time.time() + 3 * 86400))
    pc.note_failure(f"insufficient credit, quota will reset at {_manana}",
                    {"name": "deepseek-directo", "base_url": "x"})
    assert pc._store._cooldown["deepseek-directo"] == time.mktime(time.strptime(_manana, "%Y-%m-%d")), \
        "con fecha anunciada manda la fecha: es el camino de la CUOTA, no el del saldo"


def test_el_aviso_DICE_recargar_y_no_una_hora_que_no_significa_nada(monkeypatch):
    """What is written here is what the operator reads in the panel, and what they do depends on it."""
    from voice import health_state
    dichos = []
    monkeypatch.setattr(health_state, "record", lambda *a, **k: dichos.append(a), raising=False)
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pc.note_failure("Insufficient Balance", {"name": "deepseek-directo", "base_url": "x"})
    detalle = " ".join(str(x) for a in dichos for x in a)
    assert "SIN SALDO" in detalle and "recargar" in detalle
    assert "sin cuota hasta" not in detalle


def test_no_tier_left_returns_none(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    # One credential = one offered tier; once it is dried up, there is nobody left to ask.
    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "https://api.deepseek.com"})
    assert nxt is None
    assert pc.pick() is None


def test_clear_lets_the_operator_resume_after_topping_up(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "x"})
    pc.clear("deepseek-directo")
    assert pc.pick()["name"] == "deepseek-directo"


def test_spec_for_carries_model_and_credential(monkeypatch):
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    tier = {"name": "xai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "env": ["Z_AI_API_KEY"]}
    spec = pc.spec_for(tier)
    assert spec.model == "glm-5.2" and spec.base_url == "https://api.z.ai/api/anthropic" and spec.api_key == "zzz"


# ── and make sure the PANEL knows ───────────────────────────────────────────────────────────────────────────
def test_the_alerts_panel_surfaces_an_exhausted_cluster_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    from config import balances
    assert not [a for a in balances.cluster_providers() if a["state"] == "error"]

    pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "https://api.deepseek.com"})
    rows = balances.cluster_providers()
    bad = [r for r in rows if r["state"] == "error"]
    assert bad and bad[0]["key"] == "cluster:deepseek-directo" and "cuota" in bad[0]["detail"]
    assert [r for r in rows if r["state"] == "ok" and "EN USO" in r["detail"]]


def test_no_tier_left_is_its_own_loud_alert(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "x"})
    pc.note_failure("1113 Insufficient balance or no resource package",
                    {"name": "groq", "base_url": "https://api.groq.com/openai/v1"})
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
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "deepseek-directo", "base_url": "https://api.deepseek.com"})
    assert nxt["name"] == "aimlapi-failover"


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


# ── V2-243: running out of providers is not a stumble ─────────────────────────────────────────────────────────
# «Oops, I lost it for a moment. Could you repeat that?» is the right phrase for a stumble: the next attempt
# may succeed. With the entire chain dry, the next attempt fails the same way, and the operator keeps repeating
# themselves to a machine that cannot answer, unaware of the only thing that fixes it — something they own,
# not the engine. Measured in production on 2026-08-21: `Insufficient Balance` (DeepSeek, 402) twice, «NO
# FAILOVER available», and the harness canary SILENT on every turn until measurement stopped.

def test_con_el_ultimo_escalon_seco_NO_queda_a_quien_preguntar(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    assert pc.pick() is not None
    # The COMPLETE tier, as returned by `pick()` — including the real URL and `env`: V2-458 matching uses
    # the host + RESOLVED credential, and without that the sibling remains standing and the case measures something else.
    #
    # With ONE SINGLE failover (2026-08-30 rule), drying the chain takes two blows, not four — and that is half
    # the reason for the rule: a five-tier chain never became dry, so the turn could not tell the operator
    # «nobody is left; you fix this by topping up».
    pc.note_failure("Insufficient Balance", {"name": "deepseek-directo",
                                             "base_url": "https://api.deepseek.com", "env": ["DEEPSEEK_API_KEY"]})
    pc.note_failure("Insufficient Balance", {"name": "aimlapi-failover",
                                             "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"]})
    assert pc.pick() is None, "sin este hecho, el turno no puede distinguir un tropiezo de una cadena seca"


def test_el_turno_de_VOZ_lo_pregunta_y_cambia_lo_que_dice():
    """WIRING GUARD (V2-199): the fact may be perfect while the turn keeps saying «could you repeat that?».
    This is what the operator HEARS, so it is the part that cannot go untested."""
    import inspect
    import pathlib
    src = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    txt = src.read_text(encoding="utf-8")
    # V2-252: the shared module resolves «is anyone left?» and this turn READS the verdict.
    assert '_dry = bool(_v.get("dry"))' in txt
    assert "sin proveedor de modelo" in txt
    # Repointed 2026-08-31 (ratchet extraction): the wiring is unchanged — «¿me lo repites?» stays the
    # NOT-dry line, and the dry branch swaps it for the chain's own sentence (dry_chain_line).
    assert '_line = "Uf, se me ha ido un momento. ¿Me lo repites?"' in txt
    assert "if _dry:" in txt and "_pchain2.dry_chain_line" in txt
    from nucleo.flash import provider_failure as _pf
    assert "pc.pick(role) is None" in inspect.getsource(_pf.handle)


# ── V2-244: silencing a tier is legitimate; hiding THAT YOU SILENCE IT is not ──────────────────────────────────────────
# The harness isolated it in two consecutive lines of the 2026-08-21 log, with the real providers:
#
#   02:39:41  memllm[i18n]: failover to deepseek/deepseek-v4-pro @ aimlapi after HTTP 402   ← i18n FAILS OVER and continues
#   02:39:42  voice brain: «primary» … no quota … · NO FAILOVER available                  ← the brain does NOT
#
# The rule belongs to the operator and is NOT touched: in self-host, the voice chain is only the primary, because whoever
# self-hosting means paying for its APIs, and the operator cannot be surprised by the agent switching to a provider
# they did not choose. But that rule was written for LATENCY failover —the entire docstring discusses TTFT and cost— and
# what was measured is something else: the DEAD primary leaves the product mute while a live key goes unused. This does not
# fail over; it makes it possible to NAME the issue, which is the difference between “I cannot continue” and “I cannot
# continue, and this is what fixes it.”

def _sin_lista_explicita(monkeypatch):
    """Self-host and WITHOUT `fast.providers` — that is, a freshly cloned installation.

    ⚠️ Without this helper these cases read the REAL config of the machine running the suite, and on the operator's
    machine `fast.providers` IS set (direct primary + AIMLAPI failover): the result would be empty and the test
    green for the wrong reason. It is the same trap that made an empty sandbox config look like a product default
    (2026-08-21)."""
    from config import v2

    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False, raising=False)
    monkeypatch.setattr(v2, "get", lambda k: {}, raising=False)


def test_en_self_host_la_cadena_de_voz_es_SOLO_el_titular(monkeypatch):
    """The rule exactly as written; without it, the rest of this block means nothing."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert all(t["name"] != "xai-fast" for t in pc._voice_chain())


def test_un_escalon_CALLADO_con_credencial_y_sano_se_puede_nombrar(monkeypatch):
    _sin_lista_explicita(monkeypatch)
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert "deepseek-directo" in pc.suppressed_relays()


def test_un_escalon_SIN_credencial_no_esta_callado_sino_que_NO_EXISTE(monkeypatch):
    """Naming it would send the operator to activate something for which they have no account."""
    _sin_lista_explicita(monkeypatch)
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    for var in ("XAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert pc.suppressed_relays() == []


def test_un_escalon_YA_EN_COOLDOWN_no_se_ofrece_como_salida(monkeypatch):
    """The REAL case from 2026-08-21: `deepseek-directo` uses the SAME account that ran out of balance. Offering it
    as a remedy sends the operator to check a provider that is also down."""
    _sin_lista_explicita(monkeypatch)
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_cooldown", {"deepseek-directo": time.time() + 3600})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    for var in ("XAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert pc.suppressed_relays() == []


def test_en_la_NUBE_no_hay_nada_callado(monkeypatch):
    """There the chain does include failovers, so a «silent tier» would be a false statement."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: True, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert pc.suppressed_relays() == []


def test_si_el_operador_YA_puso_su_lista_no_hay_nada_callado(monkeypatch):
    """With explicit `fast.providers`, the operator is in charge: telling them we silenced something would be a lie."""
    from config import v2

    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False, raising=False)
    monkeypatch.setattr(v2, "get", lambda k: {"providers": [{"name": "x"}]} if k == "fast" else {}, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert pc.suppressed_relays() == []


def test_el_turno_de_voz_NOMBRA_lo_que_esta_callado():
    """WIRING GUARD: this is what the operator HEARS. Without it, the fact exists but comes out of no mouth.

    Repointed on 2026-08-31 (architecture ratchet): MESSAGE COMPOSITION was extracted to
    `provider_chain.dry_chain_line` — the guard still covers both halves, each where it now lives:
    the voice turn CALLS (suppressed_relays + dry_chain_line in nucleo.py), and the phrase NAMES the key that
    activates it (`fast.providers`, now checked as FUNCTION BEHAVIOR rather than as text in a file)."""
    import inspect
    import pathlib
    src = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    txt = src.read_text(encoding="utf-8")
    assert "_pchain2.suppressed_relays()" in txt
    assert "_pchain2.dry_chain_line" in txt
    line = pc.dry_chain_line(["deepseek-directo"])
    assert "fast.providers" in line and "deepseek-directo" in line
    assert "fast.providers" not in pc.dry_chain_line([])   # sin callados no se receta una clave que no aplica


# ── V2-246: a tier that ALWAYS stalls was never penalized ──────────────────────────────────────────
# `note_slow` lives on the RESPONSE path, so it only sees turns that finished; and `note_failure` is skipped
# when the turn stalls, because a stall is usually transient. Between the two, a tier that always stalls
# never entered cooldown and the next turn returned to the SAME place. Forever.
#
# Measured by the harness on 2026-08-21 against AIMLAPI with the operator's key, with the real chain already seeded
# in its sandbox: `deepseek/deepseek-v4-flash` —the failover tier's model— TIMED OUT at 75 s, while
# `deepseek/deepseek-v4-pro` responded in 18.3 s. The failover existed, was entered, and went silent too.

_UNO = {"name": "xai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm", "env": ["Z_AI_API_KEY"]}
_DOS = {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "model": "", "env": ["AIMLAPI_KEY"]}


def _dos_escalones(monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(_UNO), dict(_DOS)])
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k")


def test_UN_atasco_suelto_no_releva(monkeypatch):
    """Failing over for a network hiccup would be switching providers because of noise."""
    _dos_escalones(monkeypatch)
    assert pc.note_stall(role=pc.ROLE_VOICE) is None
    assert pc.pick(pc.ROLE_VOICE)["name"] == "xai"


def test_DOS_atascos_seguidos_SI_relevan(monkeypatch):
    _dos_escalones(monkeypatch)
    pc.note_stall(role=pc.ROLE_VOICE)
    nxt = pc.note_stall(role=pc.ROLE_VOICE)
    assert nxt and nxt["name"] == "aimlapi", "the stalled tier remained selected forever"
    assert pc._store._cooldown.get("xai", 0) > time.time()


def test_un_turno_BUENO_rompe_la_racha(monkeypatch):
    """It deliberately shares a streak with `note_slow`: two stalls with a healthy turn in between are not a streak."""
    _dos_escalones(monkeypatch)
    pc.note_stall(role=pc.ROLE_VOICE)
    pc.note_slow({"cause": "ok"}, role=pc.ROLE_VOICE)
    assert pc.note_stall(role=pc.ROLE_VOICE) is None


def test_el_ULTIMO_escalon_atascado_no_se_castiga(monkeypatch):
    """Penalizing it would leave us without a provider, which is worse than a slow one."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(_UNO)])
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pc.note_stall(role=pc.ROLE_VOICE)
    assert pc.note_stall(role=pc.ROLE_VOICE) is None
    assert pc._store._cooldown.get("xai", 0) == 0


def test_el_turno_de_voz_LO_LLAMA_cuando_se_atasca():
    """WIRING GUARD (V2-199): the predicate may be perfect and the turn may still fail to call it — which is
    exactly what happened, because the stall branch deliberately skipped the ENTIRE provider circuit."""
    import inspect
    import pathlib
    src = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    txt = src.read_text(encoding="utf-8")
    # V2-252: the turn passes the FACT (`stalled=`) and the shared module decides `note_stall` vs `note_failure`.
    # Both halves are checked: without the first the stall does not arrive; without the second it is not penalized.
    assert "stalled=bool(stalled)" in txt
    from nucleo.flash import provider_failure as _pf
    assert "pc.note_stall(role=role, tier=culpable)" in inspect.getsource(_pf.handle)
