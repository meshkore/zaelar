"""ENERGY LEASE (ADR-0005) — the ceiling by which the machine watches itself.

What is being tested is not that subtraction subtracts. It is what the design exists to guarantee: that
without a link to the cloud this machine does NOT spend without a ceiling, and that the fuse does not
take control away from the operator.
"""
import time

import pytest

from nucleo import energy_lease


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    energy_lease._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    yield
    energy_lease._reset_for_tests()


def _con_arriendo(monkeypatch, granted=100.0, ttl=1800.0):
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._state.update({"lease_id": "L1", "granted": granted, "spent": 0.0,
                                "expires_at": time.time() + ttl, "at": time.time()})


def test_self_host_no_tiene_arriendo_ni_lo_necesita(monkeypatch):
    """Without a cloud account: always allowed, zero state, zero network. Anyone who self-hosts pays for
    their own APIs, and nobody leases them energy."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: False)
    assert energy_lease.allowed() is True
    energy_lease.note_spend(999999)
    assert energy_lease.allowed() is True
    assert energy_lease.snapshot() == {"leased": False}


def test_sin_arriendo_una_cuenta_de_nube_NO_puede_gastar(monkeypatch):
    """Fail-closed. The absence of a lease is the CLOSED state, not “go ahead until someone says
    otherwise”—which is the `guarded-until-configured` behavior that cost nine days of open cloud spend."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    assert energy_lease.allowed() is False


def test_gastar_por_debajo_del_techo_no_toca_la_red(monkeypatch):
    """The whole point of the design: in steady state, spending is a subtraction. If this called the
    cloud, the latency that the lease exists to avoid would be back."""
    _con_arriendo(monkeypatch)
    llamadas = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (llamadas.append(1), c.close()))
    energy_lease.note_spend(10.0)
    assert energy_lease.remaining() == pytest.approx(90.0)
    assert energy_lease.allowed() is True
    assert not llamadas


def test_a_la_mitad_se_pide_renovacion_ANTES_de_quedarse_sin_nada(monkeypatch):
    _con_arriendo(monkeypatch)
    pedidas = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (pedidas.append(1), c.close()))
    energy_lease.note_spend(50.0)
    assert pedidas, "no se pidió renovación al 50%: llegaría tarde"
    assert energy_lease.allowed() is True, "el arriendo actual sigue sirviendo mientras se renueva"


def test_agotarse_PARA_de_verdad(monkeypatch):
    """Without this, “reactive” just means waiting for the cloud to answer. The fuse is what limits the damage."""
    _con_arriendo(monkeypatch)
    parado = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda: parado.append(1))
    energy_lease.note_spend(100.0)
    assert energy_lease.allowed() is False
    assert parado


def test_un_arriendo_caducado_no_sirve_aunque_le_quede_saldo(monkeypatch):
    """Expiry is the other half of the ceiling: a machine that has slept for months cannot wake up and
    spend against an authorization from another era."""
    _con_arriendo(monkeypatch, ttl=-1)
    assert energy_lease.expired() is True
    assert energy_lease.allowed() is False


def test_pasarse_no_deja_el_restante_en_negativo(monkeypatch):
    """Going over is NORMAL—an in-flight operation can cross the limit—and is accounted for by the
    issuer's margin. What matters is that nothing new starts after that point."""
    _con_arriendo(monkeypatch, granted=10.0)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda: None)
    energy_lease.note_spend(25.0)
    assert energy_lease.remaining() == 0.0
    assert energy_lease.allowed() is False


def test_contar_jamas_tumba_el_turno_que_lo_disparo(monkeypatch):
    _con_arriendo(monkeypatch)

    def revienta():
        raise RuntimeError("kv caído")

    monkeypatch.setattr(energy_lease, "_persist", revienta)
    energy_lease.note_spend(1.0)          # must not raise


def test_al_renovar_se_reanuda_SOLO_lo_que_paramos_nosotros(monkeypatch):
    """Deliberate asymmetry, inherited from V2-092: if the OPERATOR stopped it, leave it alone. Turning
    on something a person switched off by hand is one of the things that most undermines trust."""
    from nucleo import runstate

    arrancados = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (arrancados.append(1), c.close()))
    monkeypatch.setattr(runstate, "stopped", lambda: True)

    monkeypatch.setattr(runstate, "snapshot", lambda: {"src": "operator"})
    energy_lease._maybe_resume()
    assert not arrancados, "se reanudó una parada del OPERADOR"

    monkeypatch.setattr(runstate, "snapshot", lambda: {"src": energy_lease.STOP_SRC})
    energy_lease._maybe_resume()
    assert arrancados, "no se reanudó lo que paramos nosotros por energía"


def test_arrancando_no_es_agotado(monkeypatch):
    """When starting up, the lease is requested as a task; an operation that arrives first must NOT stop
    the agent so it can restart a second later. That flicker protects against nothing."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._renewing = True                      # request in flight, no lease yet
    parado = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (parado.append(1), c.close()))
    energy_lease._blow_fuse()
    assert not parado


def test_pero_agotado_de_verdad_SI_para(monkeypatch):
    """El guard anterior no puede convertirse en una puerta abierta: con arriendo concedido y gastado,
    el fusible salta igual."""
    from nucleo import runstate
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._renewing = True                      # even while renewing…
    energy_lease._state.update({"granted": 10.0, "spent": 10.0})   # …but it DID have and spend a lease
    parado = []
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (parado.append(1), c.close()))
    energy_lease._blow_fuse()
    assert parado


def test_el_fusible_arranca_un_reintento_o_seria_una_trampa(monkeypatch):
    """Without this, the fuse is effectively irreversible: renewal is triggered by SPENDING, and stopped
    machines do not spend—so replenishing the balance would never wake the machine. This was found in deployment.
    """
    from nucleo import runstate
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._state.update({"granted": 10.0, "spent": 10.0})
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    arrancado = []
    monkeypatch.setattr(energy_lease, "_start_retry", lambda: arrancado.append(1))
    energy_lease._blow_fuse()
    assert arrancado, "el fusible saltó sin dejar forma de volver"


# ── EXPIRED IS NOT EXHAUSTED ──────────────────────────────────────────────────────────────────────
# The three below come from a REAL production failure (2026-08-14): the machine spent the night powered
# on without spending, its lease ran out at 17:28, and by morning the agent sat stopped with 1,987
# Energy in the account. No alert, no reason on screen: the operator only saw that it would not start.
# The cause was treating "my clock ran out" the same as "I ran out of energy".

def test_expiry_asks_for_another_lease_instead_of_stopping(monkeypatch):
    """With leased balance still unspent, running out by CLOCK must renew. Stopping here shuts down the
    agent of someone whose account is full, and the retry loop takes a minute to even try."""
    _con_arriendo(monkeypatch, granted=100.0, ttl=-1)
    stopped, renewed = [], []
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda: stopped.append(1))
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (renewed.append(c.__name__), c.close()))
    energy_lease.note_spend(1.0)
    assert renewed == ["_renew_or_blow"], "an expired lease with balance must be RENEWED, not stopped"
    assert not stopped


def test_but_if_the_renewal_never_lands_it_DOES_stop(monkeypatch):
    """The other half: renewing is the attempt, not the guarantee. If the cloud refuses or stays silent the
    lease is still expired and the fuse has to blow — precisely the case the fuse exists to cover."""
    _con_arriendo(monkeypatch, granted=100.0, ttl=-1)
    stopped = []
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda: stopped.append(1))

    async def fails(**kw):
        return False   # like a timeout against the cloud: nothing was renewed

    monkeypatch.setattr(energy_lease, "ensure", fails)
    import asyncio
    asyncio.run(energy_lease._renew_or_blow())
    assert stopped, "no renewal and an expired lease must stop: fail-closed"


def test_renewal_happens_BEFORE_expiry_not_after(monkeypatch):
    """`_EXPIRY_MARGIN_S` sat declared and unused: the intent written, the wire never run. A machine that
    spends little never reached the 50% mark and watched its lease expire with energy to spare."""
    _con_arriendo(monkeypatch, granted=100.0, ttl=energy_lease._EXPIRY_MARGIN_S / 2)
    assert energy_lease._near_expiry() is True
    assert energy_lease.expired() is False, "still usable — which is why it must renew NOW, not at expiry"
    asked = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (asked.append(1), c.close()))
    energy_lease.note_spend(1.0)   # far below 50%: only the clock can trigger this
    assert asked, "a lease that was still usable was allowed to expire"


# Captured at IMPORT time, before the autouse fixture swaps `_persist` for a no-op — this is the only
# way to get a handle on the real function from inside a test.
_REAL_PERSIST = energy_lease._persist


def test_the_lease_really_persists_to_sys_kv(monkeypatch):
    """The durable counter is what stops a restart LOOP from being uncapped spend: without it every boot
    puts `spent` back to zero and asks for a fresh lease.

    It was broken in production for a day by a bare `import memory` — that facade is a docstring and
    re-exports nothing, so `memory.kv_get` raised AttributeError, the `except` downgraded it to a debug
    line, and persistence quietly stopped happening. The evidence was in the cloud, not in any test:
    seven consecutive leases, every one `reported_spent = 0`.

    `_persist` swallows everything on purpose (saving must never break a turn), so asserting "it did not
    raise" proves nothing at all. The only assertion worth making is that the write LANDED.
    """
    from memory import api as memapi
    written = {}
    monkeypatch.setattr(memapi, "kv_set", lambda k, v: written.update({k: v}))
    energy_lease._state.update({"lease_id": "L1", "granted": 100.0, "spent": 3.0})
    _REAL_PERSIST()
    assert energy_lease._KV_KEY in written, "the lease never reached sys_kv: a restart would forget it"
    assert written[energy_lease._KV_KEY]["spent"] == 3.0
