"""A spent LEASE is not an empty ACCOUNT (V2-801).

THE FAILURE. A machine held a lease of 50 Energy — the small slice of the balance it may spend without asking —
with about 22 of it spent. A Brain Worker finished and billed its whole run in one charge (~155 Energy). The counter
crossed zero, `note_spend` blew the fuse on the spot, the agent stopped, the voice said «you're out of Energy» and
the screen said «your account has no Energy left — top up», while the balance was most of the plan and the battery
showed it. Sixty seconds later the retry loop asked for a lease for the first time, got one at once, and the agent
came back. Nothing had failed on the endpoint: no renewal had been ASKED for before stopping.

Two neighbours of the same class were open in the code: a 5xx from the lease endpoint fell through as `{}` and was
read as a VERDICT (lease zeroed, account-empty stop), and every stop was recorded with one reason, so the screen and
the voice could only ever say «your account is empty».

WHAT IS PINNED HERE:
  · running the lease out ASKS for another one (bounded backoff) before any stop; a grant means no stop at all;
  · a 5xx or a body without `ok` is a failed renewal, never a verdict; an answered `ok: false` stops at once;
  · the stop carries its CAUSE — `energy_denied` (the endpoint said no) or `lease_unrenewed` (no answer) — and only
    the first is told as an empty account (voice line and notice);
  · after a failed recovery the allowance is closed, also across a restart (the cause is persisted);
  · at boot a FRESH lease is asked for and no stop decision is taken while it is in flight;
  · the notice and the battery cannot contradict each other (`noticeKind`, run in Node);
  · DISARMS: each guard is mutated and its test is seen red.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from tests.waiting import until

from nucleo import runstate
from nucleo.energy import limits as account_limits, lease as energy_lease

ENGINE = Path(__file__).resolve().parents[4]


# ── harness ──────────────────────────────────────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _Endpoint:
    """A scripted lease endpoint: each POST takes the next item (a response, or an exception to raise)."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def client(self, *a, **kw):
        ep = self

        class _C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None, headers=None):
                ep.calls.append(json)
                item = ep.script.pop(0) if ep.script else _Resp(503, None)
                if isinstance(item, Exception):
                    raise item
                return item
        return _C()


GRANT = _Resp(200, {"ok": True, "lease_id": "L2", "energy": 50.0, "ttl_s": 1800, "balance": 971.6})


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    energy_lease._reset_for_tests()
    account_limits._exhausted.update(reason=None, at=0.0)
    persisted = {}
    monkeypatch.setattr(energy_lease, "_persist", lambda: persisted.update(dict(energy_lease._state)))
    monkeypatch.setattr(energy_lease, "_start_retry", lambda: None)
    monkeypatch.setattr(energy_lease, "_gauge_from_lease", lambda data: None)
    monkeypatch.setattr(energy_lease, "_RECOVER_DELAYS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://lease.example.test")
    from nucleo.energy import account as cloud_account
    monkeypatch.setattr(cloud_account, "my_user_id", lambda: "u-test")
    stops = []

    async def _stop(src=""):
        stops.append(src)
    monkeypatch.setattr(runstate, "stop", _stop)
    monkeypatch.setattr(runstate, "stopped", lambda: bool(stops))
    monkeypatch.setattr(runstate, "snapshot", lambda: {"src": stops[-1] if stops else ""})
    energy_lease._loaded = True
    yield {"stops": stops, "persisted": persisted}
    energy_lease._reset_for_tests()
    account_limits._exhausted.update(reason=None, at=0.0)


def _holding(granted=50.0, spent=22.0, cause=None):
    energy_lease._state.update({"lease_id": "L1", "granted": granted, "spent": spent,
                                "expires_at": time.time() + 1800, "at": time.time(), "cause": cause})


def _endpoint(monkeypatch, *script) -> _Endpoint:
    ep = _Endpoint(*script)
    monkeypatch.setattr(httpx, "AsyncClient", ep.client)
    return ep


def _run(coro):
    return asyncio.run(coro)


async def _spend_and_settle(energy: float):
    """`note_spend` as a worker's end-of-run charge does it, on a running loop, then let the recovery finish."""
    energy_lease.note_spend(energy)
    await until(lambda: not energy_lease._in_flight(), "the lease recovery to finish", timeout_s=5)
    await asyncio.sleep(0.2)


# ── the incident ─────────────────────────────────────────────────────────────────────────────────────────────

def test_one_charge_bigger_than_the_lease_renews_instead_of_stopping(_clean, monkeypatch):
    """The replay: 22 of 50 spent, then a 155.5 worker charge. The endpoint grants at once — nothing
    stops, no notice, no voice line."""
    _holding()
    ep = _endpoint(monkeypatch, GRANT)
    _run(_spend_and_settle(155.5))
    assert ep.calls and ep.calls[0]["reason"] == "exhausted", "no lease was asked for before deciding"
    assert not _clean["stops"], "the agent was stopped although the endpoint granted a lease"
    assert account_limits.exhausted() is None
    assert energy_lease.allowed() and energy_lease.stop_cause() is None


def test_a_5xx_is_a_failed_renewal_not_a_verdict(_clean, monkeypatch):
    """A redeploy answers 503 for a few seconds. That says nothing about the account: retry, and a grant on the
    next attempt means no stop — and the 503 alone never zeroes the lease nor records a denial."""
    _holding()
    ep = _endpoint(monkeypatch, _Resp(503, None), _Resp(502, ValueError("html")), GRANT)
    _run(_spend_and_settle(155.5))
    assert len(ep.calls) == 3
    assert not _clean["stops"] and account_limits.exhausted() is None

    energy_lease._reset_for_tests()
    energy_lease._loaded = True
    _holding(spent=10.0)
    _endpoint(monkeypatch, _Resp(503, None))
    _run(energy_lease._request("half_spent"))
    assert energy_lease._state["granted"] == 50.0, "a 5xx zeroed the lease as if the endpoint had said no"
    assert energy_lease.stop_cause() is None and not _clean["stops"]


def test_a_body_without_ok_is_not_an_answer(_clean, monkeypatch):
    _holding(spent=10.0)
    _endpoint(monkeypatch, _Resp(401, {"error": "unauthorized"}))
    _run(energy_lease._request("half_spent"))
    assert energy_lease._state["granted"] == 50.0 and energy_lease.stop_cause() is None


def test_an_unreachable_endpoint_stops_as_unrenewed_never_as_empty(_clean, monkeypatch):
    """Lease spent and the endpoint unreachable → paid work stops. Fail-closed — but said as what happened."""
    from i18n import langs
    _holding()
    boom = httpx.ConnectError("down")
    ep = _endpoint(monkeypatch, boom, boom, boom)
    _run(_spend_and_settle(155.5))
    assert len(ep.calls) == 3, "the recovery must try a bounded number of times before stopping"
    assert _clean["stops"] == [energy_lease.STOP_SRC], "an unreachable endpoint with the lease spent must stop"
    reason = account_limits.exhausted()["reason"]
    assert reason == energy_lease.CAUSE_UNRENEWED
    assert not account_limits.says_account_empty(reason)
    assert account_limits.spoken_line(reason) == langs.current_language().energy_unconfirmed
    assert _clean["persisted"].get("cause") == energy_lease.CAUSE_UNRENEWED, "the cause must survive a restart"


def test_an_answered_no_stops_at_once_as_denied(_clean, monkeypatch):
    """Any `ok: false` is a verdict, whatever its reason (a new reason must not slip through) — one request, stop."""
    from i18n import langs
    _holding()
    ep = _endpoint(monkeypatch, _Resp(200, {"ok": False, "error": "a_reason_added_next_year", "balance": 0}))
    _run(_spend_and_settle(155.5))
    assert len(ep.calls) == 1, "a verdict must not be retried as if it were an outage"
    assert _clean["stops"] == [energy_lease.STOP_SRC]
    reason = account_limits.exhausted()["reason"]
    assert reason == energy_lease.CAUSE_DENIED and account_limits.says_account_empty(reason)
    assert account_limits.spoken_line(reason) == langs.current_language().energy_exhausted


def test_a_grant_after_a_stop_clears_the_cause_and_resumes(_clean, monkeypatch):
    _holding(spent=60.0, cause=energy_lease.CAUSE_UNRENEWED)
    _clean["stops"].append(energy_lease.STOP_SRC)
    starts = []

    async def _start(src=""):
        starts.append(src)
    monkeypatch.setattr(runstate, "start", _start)
    _endpoint(monkeypatch, GRANT)

    async def go():
        await energy_lease.ensure(reason="retry_after_exhaustion", force=True)
        await asyncio.sleep(0.01)
    _run(go())
    assert energy_lease.stop_cause() is None and starts == [energy_lease.STOP_SRC]


# ── the gate during and after a recovery ─────────────────────────────────────────────────────────────────────

def test_the_gate_admits_a_lease_holder_while_it_recovers_and_closes_after_a_failure(_clean, monkeypatch):
    asked, blown = [], []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (asked.append(c.__name__), c.close()))
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda **kw: blown.append(kw))
    _holding(spent=60.0)                                   # spent, nothing failed yet
    assert energy_lease.check("llm") is True and asked == ["_renew_or_blow"] and not blown
    energy_lease._state["cause"] = energy_lease.CAUSE_UNRENEWED   # the recovery failed
    asked.clear()
    assert energy_lease.check("llm") is False and blown, "after a failed recovery the allowance must be closed"
    assert not asked


def test_a_restart_loop_does_not_reopen_the_allowance(_clean, monkeypatch):
    """The cause is persisted with the lease: a new process that boots on a failed recovery waits for its boot
    request quietly instead of spending another recovery window."""
    blown = []
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda **kw: blown.append(kw))
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    _holding(spent=177.0, cause=energy_lease.CAUSE_UNRENEWED)
    energy_lease._booting = True
    assert energy_lease.check("llm") is False and not blown


# ── boot ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_boot_asks_for_a_fresh_lease_before_any_stop_decision(_clean, monkeypatch):
    """The persisted lease is spent (177 of 50, as left by the previous process). Boot must ask the endpoint for a
    fresh lease — not adopt the stale one — and nothing may stop the agent while that request is pending."""
    _holding(spent=177.0)
    gate = asyncio.Event
    released = {}

    async def go():
        released["ev"] = gate()
        ep = _Endpoint(GRANT)
        real = ep.client

        def slow_client(*a, **kw):
            c = real()
            post = c.post

            async def held_post(url, json=None, headers=None):
                await released["ev"].wait()
                return await post(url, json=json, headers=headers)
            c.post = held_post
            return c
        monkeypatch.setattr(httpx, "AsyncClient", slow_client)
        task = energy_lease.start_at_boot()
        assert energy_lease._in_flight(), "the in-flight mark must be set before the task's first step"
        energy_lease._blow_fuse()                         # anything deciding to stop meanwhile…
        await asyncio.sleep(0.01)
        assert not _clean["stops"], "…must not: the boot answer is pending"
        released["ev"].set()
        await task
        assert ep.calls and ep.calls[0]["reason"] == "boot" and ep.calls[0]["spent"] == 177.0
    _run(go())
    assert energy_lease.allowed() and not _clean["stops"] and not energy_lease._in_flight()


def test_the_server_boots_through_the_fresh_lease_door():
    src = (ENGINE / "server" / "boot" / "surfaces.py").read_text(encoding="utf-8")
    assert "energy_lease.start_at_boot()" in src
    assert 'energy_lease.ensure(reason="boot")' not in src, "boot must not adopt the persisted lease"


# ── the notice and the battery ───────────────────────────────────────────────────────────────────────────────

_KIND_PROBE = """
import { noticeKind, ACCOUNT_EMPTY } from %s;
const cases = %s;
process.stdout.write(JSON.stringify({kinds: cases.map(noticeKind), set: [...ACCOUNT_EMPTY].sort()}));
"""

_CASES = [
    # the measured screen: a lease that could not be renewed, battery known and lit
    {"cloud": True, "known": True, "balance": 971.6, "exhausted": {"reason": "lease_unrenewed"}},
    # the endpoint said no and the battery agrees
    {"cloud": True, "known": True, "balance": 0, "exhausted": {"reason": "energy_denied"}},
    # the endpoint said no but the battery shows Energy: never «empty» next to a lit battery
    {"cloud": True, "known": True, "balance": 120, "exhausted": {"reason": "energy_denied"}},
    # the ledger said the balance is zero
    {"cloud": True, "known": True, "balance": 0, "exhausted": {"reason": "balance_depleted"}},
    # unknown balance, denial
    {"cloud": True, "known": False, "balance": None, "exhausted": {"reason": "energy_denied"}},
]


def _kinds(account_link: Path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to run the notice's pure decision")
    script = _KIND_PROBE % (json.dumps(account_link.as_uri()), json.dumps(_CASES))
    out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_notice_never_contradicts_the_battery():
    got = _kinds(ENGINE / "frontend" / "app" / "core" / "account-link.js")
    assert got["kinds"] == ["paused", "out", "paused", "out", "out"]
    assert got["set"] == sorted(account_limits.ACCOUNT_EMPTY), "the two lists of account-empty reasons drifted"


def test_the_paused_notice_has_its_words_and_no_top_up():
    src = (ENGINE / "frontend" / "app" / "components" / "EnergyNotice.js").read_text(encoding="utf-8")
    assert "energy.${kind()}.title" in src and 'kind() !== "out"' in src
    for lang in ("es", "en"):
        ui = json.loads((ENGINE / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
        voice = json.loads((ENGINE / "i18n" / "genesis" / lang / "voice.json").read_text(encoding="utf-8"))
        assert ui.get("energy.paused.title") and ui.get("energy.paused.body") and voice.get("energy_unconfirmed")


# ── DISARMS — each guard mutated, its test must go red ───────────────────────────────────────────────────────

def _expect_red(fn, *a):
    try:
        fn(*a)
    except (AssertionError, pytest.fail.Exception, Exception):
        return
    pytest.fail(f"{fn.__name__} stayed GREEN with its guard removed — the test does not measure the guard")


def test_disarm_stop_on_the_spot_reds_the_incident(_clean, monkeypatch):
    """Put back the old behaviour — blow the fuse the moment the lease counter crosses zero."""
    real = energy_lease._renew_or_blow

    async def old(reason="expired"):
        if reason == "exhausted":
            energy_lease._blow_fuse()
            return
        await real(reason)
    monkeypatch.setattr(energy_lease, "_renew_or_blow", old)
    assert energy_lease._renew_or_blow is old
    _expect_red(test_one_charge_bigger_than_the_lease_renews_instead_of_stopping, _clean, monkeypatch)


def test_disarm_5xx_as_verdict_reds_its_test(_clean, monkeypatch):
    """Put back the product's old reading — a 5xx becomes `{}`, and anything without `ok` falls through to the
    verdict branch — by recompiling `_request` from its own source with the guard removed."""
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(energy_lease._request))
    mutated = (src.replace('r.json() if r.status_code < 500 else None', 'r.json() if r.status_code < 500 else {}')
                  .replace('if not isinstance(data, dict) or "ok" not in data:', 'if False:'))
    assert mutated.count("if False:") == 1 and "else {}" in mutated, "the mutation did not land"
    ns = {}
    from nucleo.energy import lease_renewal      # `_request` lives there (refactor2710-10b); callers reach it via lease
    exec(compile(mutated, lease_renewal.__file__, "exec"), lease_renewal.__dict__, ns)
    monkeypatch.setattr(energy_lease, "_request", ns["_request"])
    _expect_red(test_a_5xx_is_a_failed_renewal_not_a_verdict, _clean, monkeypatch)


def test_disarm_one_reason_for_every_stop_reds_its_test(_clean, monkeypatch):
    """Record every stop as an empty account again."""
    real = account_limits.request_close
    monkeypatch.setattr(account_limits, "request_close", lambda reason: real(energy_lease.CAUSE_DENIED))
    _expect_red(test_an_unreachable_endpoint_stops_as_unrenewed_never_as_empty, _clean, monkeypatch)


def test_disarm_boot_adopting_the_stale_lease_reds_its_test(_clean, monkeypatch):
    """Boot without forcing, and without the synchronous in-flight mark."""
    def stale_boot():
        return asyncio.get_running_loop().create_task(energy_lease.ensure(reason="boot"))
    monkeypatch.setattr(energy_lease, "start_at_boot", stale_boot)
    _expect_red(test_boot_asks_for_a_fresh_lease_before_any_stop_decision, _clean, monkeypatch)


def test_disarm_the_battery_guard_reds_the_notice_test(tmp_path):
    """Remove the battery half of `noticeKind`: a denial next to a lit battery paints «empty» again."""
    src = (ENGINE / "frontend" / "app" / "core" / "account-link.js").read_text(encoding="utf-8")
    mutated = src.replace("ACCOUNT_EMPTY.has(reason) && !showsEnergy", "ACCOUNT_EMPTY.has(reason)")
    assert mutated != src, "the mutation did not land"
    f = tmp_path / "account-link.js"
    f.write_text(mutated, encoding="utf-8")
    got = _kinds(f)
    assert got["kinds"] != ["paused", "out", "paused", "out", "out"], "the battery guard is not what the test measures"
