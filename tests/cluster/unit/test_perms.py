#
# Per-cluster permissions (V2-076) + their translation to the catalog. Run: .venv/bin/pytest tests/cluster/unit/test_perms.py -q
#
# Basis of Parts A/C: a new cluster DENIES everything (maximum security); the operator escalates when connecting; the profile is
# translated to the subset of the FlashBrain catalog and to the BOUNDED escalation context. Zero permissions → no tools →
# the cluster turn remains as it is today (zero regression).
#
from pathlib import Path

import pytest

from connectors.meshkore import perms, store


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CONFIG_FILE", Path(tmp_path) / "meshkore.json")
    yield


# ── store: per-cluster profile ──────────────────────────────────────────────────────────────────────────────────
def test_default_perms_deny_all(cfg):
    p = store.get_perms("nuevo")
    assert p == {"workers": False, "code": False, "repo": None, "execute": False, "deploy": False}


def test_set_perms_merges_and_persists(cfg):
    store.set_perms("meshcore", {"code": True, "repo": "meshkore/algo"})
    p = store.get_perms("meshcore")
    assert p["code"] is True and p["repo"] == "meshkore/algo" and p["workers"] is False


def test_set_perms_ignores_unknown_keys(cfg):
    store.set_perms("meshcore", {"code": True, "run_rm_rf": True})
    assert "run_rm_rf" not in store.get_perms("meshcore")


def test_save_cluster_preserves_perms(cfg):
    store.set_perms("meshcore", {"code": True})
    store.save_cluster("meshcore", "c_1", "tok", "zaelar")     # saving credentials again must not delete permissions
    assert store.get_perms("meshcore")["code"] is True


# ── perms: translation to the catalog + escalation context ─────────────────────────────────────────────────────
def test_no_perms_no_tools_zero_regression():
    p = store.DEFAULT_PERMS
    assert perms.gated_tool_names(p) == set()
    assert perms.any_capability(p) is False           # → the cluster turn remains as it is today


def test_code_perm_offers_escalate():
    assert perms.gated_tool_names({"code": True}) == {"escalate_to_slowbrain"}
    assert perms.any_capability({"code": True}) is True


def test_workers_perm_offers_escalate_and_search():
    names = perms.gated_tool_names({"workers": True})
    assert "escalate_to_slowbrain" in names and "web_search" in names


def test_escalate_context_never_trusted():
    ctx = perms.escalate_context("meshcore", {"code": True, "repo": "meshkore/algo", "execute": True})
    assert ctx["trusted"] is False                    # a cluster escalation NEVER inherits the operator's trust
    assert ctx["src"] == "cluster" and ctx["cluster"] == "meshcore"
    assert ctx["dev"] is True and ctx["repo"] == "meshkore/algo" and ctx["execute"] is True


# ── objective ownership guard (audit 2026-07-26, P0 finding) ───────────────────────────────────────────────────
def test_gate_dev_by_objective_blocks_without_objective():
    ctx = perms.escalate_context("meshcore", {"code": True, "repo": "meshkore/algo"})
    gated = perms.gate_dev_by_objective(ctx, "")
    assert gated["dev"] is False and gated["repo"] == "meshkore/algo"    # rest of context unchanged
    assert perms.gate_dev_by_objective(ctx, None)["dev"] is False
    assert perms.gate_dev_by_objective(ctx, "   ")["dev"] is False       # whitespace only = no objective


def test_gate_dev_by_objective_allows_with_objective():
    ctx = perms.escalate_context("meshcore", {"code": True, "repo": "meshkore/algo"})
    gated = perms.gate_dev_by_objective(ctx, "portar el algoritmo de trading a Python")
    assert gated["dev"] is True and gated is ctx                        # no objective to degrade → same dict


def test_gate_dev_by_objective_noop_without_dev_permission():
    ctx = perms.escalate_context("meshcore", {"workers": True})         # workers without code → dev is already False
    assert perms.gate_dev_by_objective(ctx, "") is ctx                  # nothing to degrade
