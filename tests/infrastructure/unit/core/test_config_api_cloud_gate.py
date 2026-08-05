"""server/config_api.py — cloud profile locks provider/model selection (INI-019 addenda "Cambio B",
2026-08-05). Self-host (ZAELAR_USER_ID unset) must be COMPLETELY unaffected — this only restricts
hosted cloud accounts, never the OSS product."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.config_api import router


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
    r = _client().post("/api/config/v2", json={"section": "fast", "patch": {"provider": "aimlapi"}})
    assert r.status_code == 200
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
