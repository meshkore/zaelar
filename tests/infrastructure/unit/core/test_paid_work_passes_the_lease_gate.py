"""Paid work asks the energy lease BEFORE it starts (V2-785).

THE FAILURE. `energy_lease.allowed()` — «may this machine start something that costs money?» — existed from
the day the lease was written, and no paid path asked it: every paid call started first and was subtracted
afterwards. So an engine with nothing to lease, that nobody had opened, could still spend an LLM call and two
web searches at start-up and go negative. On top of that, a denied boot lease never stopped anything: the denial ran inside the very
request `_blow_fuse` exempts as «still asking».

WHAT IS PINNED HERE:
  · the gate's own semantics (self-host always admits; no lease refuses and blows the fuse; a request in flight
    refuses quietly; an expired lease with energy left admits once and asks for a renewal; a DENIAL stops);
  · each door refuses with no lease — model egress, the hot model client (before its relay loop, so no healthy
    tier is marked), paid search keys, opening a worker, the decision model, the boot search probe;
  · the voice turn says the out-of-energy line instead of «the brain is down»;
  · the out-of-energy STATE is recorded once and cleared by a lease;
  · STRUCTURE: every product file that meters paid spend also passes a door (a grep, like `test_energy_coverage`);
  · DISARM: with the gate removed (`check` always True), the door tests go red — they measure the gate, not
    a missing key.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from nucleo import account_limits, energy_lease

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    energy_lease._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    monkeypatch.setattr(energy_lease, "_start_retry", lambda: None)
    account_limits._exhausted.update(reason=None, at=0.0)
    yield
    energy_lease._reset_for_tests()
    account_limits._exhausted.update(reason=None, at=0.0)
    account_limits.clear_closer()


@pytest.fixture
def no_lease(monkeypatch):
    """A cloud machine holding no lease at all (the 2026-10-22 account). The fuse is recorded, not fired."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    blown = []
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda **kw: blown.append(kw))
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    return blown


def _disarmed(monkeypatch):
    monkeypatch.setattr(energy_lease, "check", lambda kind="": True)


# ── the gate itself ─────────────────────────────────────────────────────────────────────────────────────────

def test_self_host_always_admits(monkeypatch):
    monkeypatch.setattr(energy_lease, "enabled", lambda: False)
    assert energy_lease.check("llm") is True
    energy_lease.admit("search")                       # does not raise


def test_no_lease_refuses_and_blows_the_fuse(no_lease):
    assert energy_lease.check("llm") is False
    assert no_lease, "a refusal must reach the operator as the out-of-energy state, not only as a failed call"
    with pytest.raises(energy_lease.OutOfEnergy) as ei:
        energy_lease.admit("llm")
    assert energy_lease.is_refusal(ei.value) and energy_lease.is_refusal(str(ei.value))


def test_a_request_in_flight_refuses_quietly(no_lease):
    energy_lease._renewing = True                      # boot: asked, not answered yet
    assert energy_lease.check("llm") is False
    assert not no_lease, "stopping the agent for an answer seconds away is the flicker the lease refuses to cause"


def test_an_expired_lease_with_energy_left_admits_and_renews(monkeypatch):
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._state.update(granted=50.0, spent=10.0, expires_at=1.0)   # expired long ago
    asked = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (asked.append(c.__name__), c.close()))
    assert energy_lease.check("llm") is True
    assert asked == ["_renew_or_blow"]


def test_a_denied_boot_lease_stops_even_while_the_request_is_in_flight(monkeypatch):
    """The bug under the incident: the denial runs INSIDE the request, with `_renewing` still True."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._renewing = True
    stops, closes = [], []
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (stops.append(1), c.close()))
    monkeypatch.setattr(account_limits, "request_close", lambda r: closes.append(r))
    energy_lease._blow_fuse(verdict=True)
    assert stops and closes == [energy_lease.CAUSE_DENIED]   # the cloud SAID no: the account-empty reason


# ── the doors ───────────────────────────────────────────────────────────────────────────────────────────────

def _route_refuses():
    from nucleo import llm_egress
    with pytest.raises(energy_lease.OutOfEnergy):
        llm_egress.route("https://api.deepseek.com", "k")
    assert llm_egress.route("http://localhost:11434/v1", "ollama")[0].startswith("http://localhost")


def test_the_model_egress_refuses_without_a_lease(no_lease):
    _route_refuses()


def _stream_refuses_before_any_client(monkeypatch):
    from nucleo.llm import fast_client, provider_failure
    from nucleo.llm.model_spec import ModelSpec
    built, marked = [], []
    monkeypatch.setattr(fast_client.FastClient, "_client_for", lambda self, spec: built.append(1) or (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(provider_failure, "handle", lambda *a, **k: marked.append(1) or {})
    spec = ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="k")

    async def go():
        async for _ in fast_client.FastClient().stream([{"role": "user", "content": "hi"}], spec=spec):
            pass
    with pytest.raises(energy_lease.OutOfEnergy):
        asyncio.run(go())
    assert not built and not marked, "a refusal must never reach the relay loop that marks a healthy tier"


def test_the_hot_model_client_refuses_before_its_relay_loop(no_lease, monkeypatch):
    _stream_refuses_before_any_client(monkeypatch)


def _search_refuses(monkeypatch):
    monkeypatch.setenv("Z_AI_API_KEY", "placeholder")
    from search import health, web
    from search.providers import keys
    assert keys.key("zai") == "", "no lease → no key: the paid index is never asked"
    assert keys.present("ddg") is True, "a free index is not the lease's business"
    assert health.probe("zai")["state"] == "unfunded"
    called = []
    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS,
                        # as the real module does: no key → no request (`search/providers/zai.py::search`)
                        "zai": lambda q, k: ({"results": [{"url": "u"}], "answer": "", "_": called.append("zai")}
                                             if keys.key("zai") else {"results": [], "answer": ""}),
                        "ddg": lambda q, k: {"query": q, "answer": "", "results": [{"title": "t", "url": "u", "snippet": ""}], "source": "ddg"}})
    monkeypatch.setattr(web, "provider", lambda mode="answer": "zai")
    web._recent.clear()
    r = web.search("lease gate probe query", mode="results")
    assert "zai" not in called and r.get("source") == "ddg"


def test_paid_search_gets_no_key_without_a_lease_and_degrades_to_free(no_lease, monkeypatch):
    _search_refuses(monkeypatch)


def test_no_worker_opens_without_a_lease(no_lease, monkeypatch):
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    assert runstate.blocks_new_work(who="test") is True


def test_the_decision_model_stays_silent_without_a_lease(no_lease, monkeypatch):
    from nucleo import jev
    monkeypatch.setenv("TYPESAFE_API_KEY", "placeholder")
    jev.reset_breaker()
    assert jev.enabled() is False


def test_the_boot_search_probe_never_pays_in_a_leased_deployment(monkeypatch):
    """Task 5 of V2-785: the two searches of the 2026-10-22 account were THIS probe (`search.api.prime_cache`,
    45 s after boot), one paid request per keyed index, on every machine start."""
    from search import api, health
    from search.providers import PROVIDERS, keys
    monkeypatch.setattr(keys, "leased", lambda: True)
    asked = []
    monkeypatch.setattr(health, "probe_all", lambda names=None, parallel=True: asked.extend(names or []) or [])
    api.prime_cache()
    assert asked and not [n for n in asked if PROVIDERS[n].paid]
    assert {r["provider"] for r in api.cached_rows() if r["state"] == "unprobed"} == {n for n, p in PROVIDERS.items() if p.paid}


def test_a_refusal_never_marks_a_provider(no_lease):
    from nucleo.llm import provider_failure
    from nucleo.llm import provider_chain as pc
    assert provider_failure.handle("no energy lease for llm", role=pc.ROLE_VOICE) == {"relay": None, "dry": False}


def test_the_voice_turn_says_out_of_energy_not_brain_down():
    from i18n import langs
    from voice.engine.llm.providers import turn_failure
    said, alerts = [], []
    account_limits.note_exhausted(energy_lease.CAUSE_DENIED)
    ok = turn_failure._refused_for_energy(energy_lease.OutOfEnergy("no energy lease for llm"), "",
                                          lambda *a, **k: alerts.append(a), said.append)
    assert ok and said == [langs.current_language().energy_exhausted]
    # V2-801 — with no recorded reason, or a lease that could not be renewed, the voice never says «empty».
    for reason in (None, energy_lease.CAUSE_UNRENEWED):
        account_limits._exhausted.update(reason=reason, at=0.0)
        said.clear()
        turn_failure._refused_for_energy(energy_lease.OutOfEnergy("no energy lease for llm"), "",
                                         lambda *a, **k: None, said.append)
        assert said == [langs.current_language().energy_unconfirmed]
    assert not turn_failure._refused_for_energy(RuntimeError("HTTP 503"), "HTTP 503", lambda *a, **k: None, said.append)


# ── the out-of-energy state ─────────────────────────────────────────────────────────────────────────────────

def test_the_state_is_recorded_once_and_a_lease_or_a_top_up_clears_it(monkeypatch):
    published = []
    monkeypatch.setattr(account_limits, "_publish", lambda: published.append(account_limits._exhausted["reason"]))
    account_limits.request_close("lease_unrenewed")
    account_limits.request_close("lease_unrenewed")
    assert account_limits.exhausted()["reason"] == "lease_unrenewed" and published == ["lease_unrenewed"]
    account_limits.clear_exhausted()
    assert account_limits.exhausted() is None and published[-1] is None
    account_limits.on_balance(0)
    assert account_limits.exhausted()["reason"] == "balance_depleted"
    account_limits.on_balance(40)
    assert account_limits.exhausted() is None


def test_the_account_url_has_one_home(monkeypatch):
    from nucleo import cloud_account
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    assert cloud_account.account_url() == ""
    monkeypatch.setenv("ZAELAR_USER_ID", "u1")
    monkeypatch.delenv("ZAELAR_ACCOUNT_URL", raising=False)
    assert cloud_account.account_url() == "https://zaelar.com/account"
    monkeypatch.setenv("ZAELAR_ACCOUNT_URL", "https://example.test/acct")
    assert cloud_account.account_url() == "https://example.test/acct"


# ── structure: every file that meters paid spend passes a door ────────────────────────────────────────────────

_METERS = ("report_llm_usage(", "meter_openai_response(", "report_search_usage(", "report_worker_usage(",
           "report_decision_usage(")
_DOORS = ("energy_lease", "llm_egress.route(", "_keys.key(", "blocks_new_work")
_EXEMPT = {
    "nucleo/energy_meter.py": "IS the meter.",
    "nucleo/workers/session_finish.py": "reads a worker's usage AFTER it ran; the worker was opened through "
                                 "`runstate.blocks_new_work`, which asks the lease.",
    "widgets/generator.py": "meters a widget generation's worker; generations are opened through dispatch / "
                            "`blocks_new_work` (widgets/server_api.py), which ask the lease.",
}


def test_paid_work_passes_the_lease_gate():
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    gaps = []
    for rel in files:
        if rel.startswith(("tests/", "scripts/")) or rel in _EXEMPT:
            continue
        src = (ENGINE / rel).read_text(encoding="utf-8", errors="ignore")
        if any(m in src for m in _METERS) and not any(d in src for d in _DOORS):
            gaps.append(rel)
    assert not gaps, ("these files meter paid spend and pass no lease door — on a cloud machine with no lease "
                      f"they spend anyway: {gaps}. Gate them (energy_lease.check/admit) or exempt with a reason.")


def test_every_exemption_still_exists():
    assert [r for r in _EXEMPT if not (ENGINE / r).exists()] == []


# ── DISARM: remove the gate and the door tests must fail ─────────────────────────────────────────────────────

@pytest.mark.parametrize("door", ["route", "stream", "search"])
def test_disarm_with_the_gate_removed_the_doors_spend(no_lease, monkeypatch, door):
    _disarmed(monkeypatch)
    with pytest.raises((Exception, pytest.fail.Exception)):      # any way of NOT passing
        if door == "route":
            _route_refuses()
        elif door == "stream":
            _stream_refuses_before_any_client(monkeypatch)
        else:
            _search_refuses(monkeypatch)
