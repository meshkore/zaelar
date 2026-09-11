"""server/config_api.py — cloud profile locks provider/model selection (INI-019 addenda "Change B",
2026-08-05). Self-host (ZAELAR_USER_ID unset) must be COMPLETELY unaffected — this only restricts
hosted cloud accounts, never the OSS product.

⚠️ **This file wrote to the OPERATOR'S OWN `config/v2.json` until 2026-09-11.** It isolated nothing, and
`test_set_v2_allowed_for_self_host` posts a REAL save: every run of this node made AIMLAPI — the broker,
which the model table forbids as the titular of anything — the provider of his voice brain, over a `model`
and a `base_url` that stayed DeepSeek's. Found on his live engine, and only because the V2-673 guard started
refusing the incoherent result; before that it landed silently and the label was the only thing that moved.
That is the class this repo has paid for twice already («un test unitario nunca toca artefactos vivos»,
«mi suite reseteó su motor VIVO»). `_client` isolates the store now, and the payload is a COHERENT provider
change so this node tests the cloud gate instead of tripping over the mismatch validator.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.config_api import router


@pytest.fixture(autouse=True)
def _isolated_v2_store(tmp_path, monkeypatch):
    """No test in this file may touch the real routing store."""
    from config import v2
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_config_reports_cloud_profile_false_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    r = _client().get("/api/config")
    assert r.status_code == 200
    assert r.json()["cloud_profile"] is False


def test_get_config_reports_cloud_profile_true_for_cloud_account(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    r = _client().get("/api/config")
    assert r.status_code == 200
    assert r.json()["cloud_profile"] is True


def test_set_v2_allowed_for_self_host(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    # A COHERENT change (provider + its model + its endpoint): this node is about the cloud gate, and a
    # payload that the mismatch validator has to refuse would test the wrong thing.
    r = _client().post("/api/config/v2", json={"section": "fast", "patch": {
        "provider": "aimlapi", "model": "deepseek/deepseek-v4-pro",
        "base_url": "https://api.aimlapi.com/v1"}})
    assert r.status_code == 200, r.json()
    assert r.json()["ok"] is True


def test_set_v2_blocked_for_cloud_account_on_provider_sections(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    for section in ("fast", "code_agent", "memory", "triage", "susurro"):
        r = _client().post("/api/config/v2", json={"section": section, "patch": {"provider": "x"}})
        assert r.status_code == 403, f"section={section} should be locked in the cloud profile"
        assert r.json()["ok"] is False


def test_set_v2_flags_section_stays_open_for_cloud_account(monkeypatch):
    """`flags` isn't a provider/model choice — it must NOT be swept up by the cloud gate."""
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    r = _client().post("/api/config/v2", json={"section": "flags", "patch": {}})
    assert r.status_code == 200
