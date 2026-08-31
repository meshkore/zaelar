"""z.ai has TWO wallets, and the panel must tell them apart (V2-517).

Measured live 2026-08-31: the worker row said "z.ai · sin cuota hasta el 01 Sep 01:39" — a flat red that the
operator read as "z.ai dead" — while the OTHER purse (pay-per-use credits, paas/v4) served a real
completion. The coding-plan quota and the credits balance are separate wallets (V2-462 routes them by
URL segment); when the plan tier is in cooldown, the panel measures the second wallet with a 1-token
completion (no public balance endpoint exists — every candidate 404s) and adds a row saying whether
work can still go well.
"""
from __future__ import annotations

from config import balances


def test_the_verdict_reads_the_wire_not_hopes():
    ok = balances._zai_credits_verdict(200, '{"choices": [...]}')
    assert ok["state"] == "ok" and "MEDIDO" in ok["detail"]
    dry = balances._zai_credits_verdict(429, '{"error":{"code":"1113","message":"Insufficient balance"}}')
    assert dry["state"] == "error" and "1113" in dry["detail"]
    bad = balances._zai_credits_verdict(401, "unauthorized")
    assert bad["state"] == "error"
    fog = balances._zai_credits_verdict(500, "boom")
    assert fog["state"] == "unknown"


def test_a_downed_plan_row_brings_the_second_wallet_row(monkeypatch):
    from nucleo.workers import providers as prov
    monkeypatch.setattr(prov, "status", lambda: [
        {"name": "z.ai", "plan": "coding plan", "state": "error",
         "detail": "sin cuota hasta el 01 Sep 01:39", "serving": False, "active": False},
        {"name": "deepseek", "plan": "api directa", "state": "ok", "detail": "disponible",
         "serving": True, "active": True},
    ])
    monkeypatch.setattr(balances, "balance",
                        lambda svc, refresh=False: {"state": "ok", "detail": "con saldo · MEDIDO"}
                        if svc == "z.ai-creditos" else {"state": "unknown"})
    rows = balances.worker_providers()
    wallet = [r for r in rows if r["key"] == "worker:z.ai-creditos"]
    assert len(wallet) == 1
    assert wallet[0]["state"] == "ok" and "MEDIDO" in wallet[0]["detail"]
    # the good news must survive the alerts() warn/error filter: it rides ON the plan's red row
    plan = next(r for r in rows if r["key"] == "worker:z.ai")
    assert "CON saldo" in plan["detail"]


def test_a_healthy_plan_needs_no_second_row(monkeypatch):
    from nucleo.workers import providers as prov
    monkeypatch.setattr(prov, "status", lambda: [
        {"name": "z.ai", "plan": "coding plan", "state": "ok", "detail": "disponible",
         "serving": True, "active": True},
    ])
    called = {"n": 0}
    monkeypatch.setattr(balances, "balance",
                        lambda svc, refresh=False: called.__setitem__("n", called["n"] + 1) or {"state": "ok"})
    rows = balances.worker_providers()
    assert not [r for r in rows if r["key"] == "worker:z.ai-creditos"]
    assert called["n"] == 0                       # the paid probe never fires when the plan is healthy


def test_no_key_stays_silent(monkeypatch):
    from nucleo.workers import providers as prov
    monkeypatch.setattr(prov, "status", lambda: [
        {"name": "z.ai", "plan": "coding plan", "state": "error", "detail": "sin cuota",
         "serving": False, "active": False},
    ])
    monkeypatch.setattr(balances, "balance", lambda svc, refresh=False: {"state": "no_key"})
    rows = balances.worker_providers()
    assert not [r for r in rows if r["key"] == "worker:z.ai-creditos"]
