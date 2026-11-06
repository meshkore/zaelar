"""
LATENCY FAILOVER for the VOICE brain (V2-094, 2026-08-14).

`provider_chain` had existed since 2026-08-03 but only served the CLUSTER brain, and only failed over for a BROKEN
provider (429 / quota / credential). The failure the operator actually experiences is different: the SLOW provider.
Measured in session b70a45d0 — p50 TTFT of 8,370 ms and a maximum of 25,703 ms with the CONSTANT prompt (±9%) and
120 tok/s generation, meaning all the time before the first token — and translated as “it looks like you have gone
dumb”.

What is fixed here is the POLICY, which is where the risk of spending money unintentionally lies:

  · the trigger reads the verdict from `turn_perf` (it does not measure again): `pre_token` and `proveedor` count;
    `frio`, `trabajo`, `prompt`, `reparto`, and `ok` do not, and ANY of them breaks the streak;
  · CONSECUTIVE slow turns are required (an isolated spike does not change provider);
  · the cooldown is SHORT and there is a TURN CEILING: latency failover activates precisely on difficult turns, which
    are the ones that spend the most tokens;
  · **there is no default failover in self-host**: self-hosting users pay for their APIs and must not be surprised
    by the agent switching on its own to a provider they did not choose.
"""
from __future__ import annotations

import pytest

from nucleo.llm import provider_chain as pc


T1 = {"name": "titular", "base_url": "https://t/v1", "api_key": "k1", "model": "m-titular", "plan": "titular"}
T2 = {"name": "relevo", "base_url": "https://r/v1", "api_key": "k2", "model": "m-relevo", "plan": "relevo"}
T3 = {"name": "ultimo", "base_url": "https://u/v1", "api_key": "k3", "model": "m-ultimo", "plan": "último"}


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    """Reset in-process state to zero with no persistence: the cooldown is stored in `sys_kv`, and a test must not
    leave the operator with a penalized provider."""
    pc._store._cooldown.clear()
    pc._slow_streak.clear()
    pc._relay_turns.clear()
    pc._store._loaded = True                            # do not read the real sys_kv
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(T1), dict(T2), dict(T3)])
    yield
    pc._store._cooldown.clear()
    pc._slow_streak.clear()
    pc._relay_turns.clear()


def _v(cause, ttft=9000, total=10000):
    return {"cause": cause, "ttft_ms": ttft, "total_ms": total, "ttft_frac": ttft / total}


# ── the trigger ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_un_solo_turno_lento_no_releva():
    """An isolated spike is noise. Failing over for one would continuously change the model—and the price."""
    assert pc.note_slow(_v("pre_token")) is None
    assert pc.pick()["name"] == "titular"


def test_dos_turnos_lentos_seguidos_relevan():
    assert pc.note_slow(_v("pre_token")) is None
    nxt = pc.note_slow(_v("pre_token"))
    assert nxt and nxt["name"] == "relevo"
    assert pc.pick()["name"] == "relevo", "el relevo tiene que ser STICKY, no solo devuelto una vez"


def test_generar_despacio_tambien_cuenta():
    """`proveedor` = writes slowly. It also leaves the operator waiting, so it also fails over."""
    pc.note_slow(_v("proveedor", ttft=500, total=9000))
    assert pc.note_slow(_v("proveedor", ttft=500, total=9000))["name"] == "relevo"


@pytest.mark.parametrize("cause", ["frio", "trabajo", "prompt", "reparto", "ok"])
def test_las_causas_que_no_son_del_proveedor_no_relevan(cause):
    """Changing provider for a cold start makes it WORSE (the new one also pays the handshake). For a large prompt,
    it fixes nothing: the prompt is what fixes that. For a legitimate second pass, it penalizes the worker."""
    for _ in range(5):
        assert pc.note_slow(_v(cause)) is None
    assert pc.pick()["name"] == "titular"


def test_un_turno_sano_ROMPE_la_racha():
    """CONSECUTIVE slow turns are required. Without this, two bad turns separated by an afternoon of good turns would
    eventually fail over—and the operator would find themselves on another provider for no current reason."""
    pc.note_slow(_v("pre_token"))
    pc.note_slow(_v("ok", ttft=200, total=800))
    assert pc.note_slow(_v("pre_token")) is None, "la racha no se reinició"
    assert pc.pick()["name"] == "titular"


def test_el_ultimo_escalon_no_se_castiga(monkeypatch):
    """If we are already on the last one, penalizing it would leave us without a provider: a slow turn is better than none."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(T3)])
    for _ in range(4):
        assert pc.note_slow(_v("pre_token")) is None
    assert pc.pick()["name"] == "ultimo"


# ── the spending ceiling ──────────────────────────────────────────────────────────────────────────────────────────
def test_el_relevo_tiene_TECHO_DE_TURNOS_y_devuelve_el_turno_al_titular():
    """THE cost protection. Latency failover activates on DIFFICULT turns, which are the ones that spend the most tokens;
    in the cloud, moving to a large tier can cost 14× the input. Once the ceiling is reached, it returns to the
    primary even if it remains slow: we prefer a slow turn to a surprise bill."""
    pc.note_slow(_v("pre_token"))
    pc.note_slow(_v("pre_token"))
    assert pc.pick()["name"] == "relevo"
    for _ in range(pc._RELAY_TURN_BUDGET + 2):
        pc.pick()
    assert pc.pick()["name"] == "titular", "el relevo se quedó indefinidamente en el escalón caro"


def test_el_cooldown_de_latencia_es_corto():
    """Slowness is temporary. The quota cooldown is half an hour because the quota takes time to replenish; staying
    half an hour on a more expensive tier because of two bad turns is extremely costly."""
    assert pc._SLOW_COOLDOWN_S <= 10 * 60
    assert pc._SLOW_COOLDOWN_S < pc._DEFAULT_COOLDOWN_S


def test_el_relevo_es_VISIBLE(monkeypatch):
    """Changing provider behind the operator's back is the kind of state that misleads—and in the cloud it also
    changes what each turn costs."""
    eventos = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: eventos.append((a, k)))
    pc.note_slow(_v("pre_token"))
    pc.note_slow(_v("pre_token"))
    assert eventos, "el relevo no dejó rastro en el timeline"
    texto = " ".join(str(a) for a, _ in eventos)
    assert "LATENCIA" in texto and "relevo" in texto.lower()


# ── the default chains ──────────────────────────────────────────────────────────────────────────────────────────
def test_el_cooldown_es_compartido_pero_la_cadena_no(monkeypatch):
    """If a provider runs out of quota, it has run out for everyone (one truth per provider). What changes per consumer
    is the ORDER of the chain, not its health."""
    monkeypatch.undo()
    assert pc.ROLE_VOICE != pc.ROLE_CLUSTER
    assert pc._config_key(pc.ROLE_VOICE) == "fast"
    assert pc._config_key(pc.ROLE_CLUSTER) == "cluster"
