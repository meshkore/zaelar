#
# Permisos por-CLUSTER (V2-076) + su traducción al catálogo. Run: .venv/bin/pytest connectors/meshkore/test_perms.py -q
#
# Base de la Parte A/C: un cluster nuevo DENIEGA todo (seguridad máxima); el operador eleva al conectar; el perfil se
# traduce al subconjunto del catálogo del FlashBrain y al contexto de escalada ACOTADO. Permiso cero → sin tools →
# el turno de cluster se queda como hoy (cero regresión).
#
from pathlib import Path

import pytest

from connectors.meshkore import perms, store


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CONFIG_FILE", Path(tmp_path) / "meshkore.json")
    yield


# ── store: perfil por-cluster ───────────────────────────────────────────────────────────────────────────────────
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
    store.save_cluster("meshcore", "c_1", "tok", "zaelar")     # re-guardar creds no debe borrar los permisos
    assert store.get_perms("meshcore")["code"] is True


# ── perms: traducción al catálogo + contexto de escalada ────────────────────────────────────────────────────────
def test_no_perms_no_tools_zero_regression():
    p = store.DEFAULT_PERMS
    assert perms.gated_tool_names(p) == set()
    assert perms.any_capability(p) is False           # → el turno de cluster se queda como hoy


def test_code_perm_offers_escalate():
    assert perms.gated_tool_names({"code": True}) == {"escalate_to_slowbrain"}
    assert perms.any_capability({"code": True}) is True


def test_workers_perm_offers_escalate_and_search():
    names = perms.gated_tool_names({"workers": True})
    assert "escalate_to_slowbrain" in names and "web_search" in names


def test_escalate_context_never_trusted():
    ctx = perms.escalate_context("meshcore", {"code": True, "repo": "meshkore/algo", "execute": True})
    assert ctx["trusted"] is False                    # una escalada de cluster JAMÁS hereda la confianza del operador
    assert ctx["src"] == "cluster" and ctx["cluster"] == "meshcore"
    assert ctx["dev"] is True and ctx["repo"] == "meshkore/algo" and ctx["execute"] is True
