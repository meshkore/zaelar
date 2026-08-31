"""test_doctor.py — capability detector (V2-040). Verifies: presence of credentials (redacted), Ollama model
matching, hardware-based profile recommendation, and the build→write→report round trip. Run:
.venv/bin/pytest tests/infrastructure/unit/config/test_doctor.py
"""
import json

import config.doctor as doctor


def test_credentials_only_report_presence(monkeypatch):
    for spec in doctor.CREDENTIALS:
        for e in spec["env"]:
            monkeypatch.delenv(e, raising=False)
    monkeypatch.setenv("AIMLAPI_KEY", "sk-secret-value")
    creds = {c["key"]: c for c in doctor.credentials()}
    assert creds["aimlapi"]["set"] is True
    assert creds["deepgram"]["set"] is False
    # the secret NEVER appears in the report
    assert "sk-secret-value" not in json.dumps(doctor.credentials())


def test_ollama_model_match_by_tag_and_base():
    models = ["qwen2.5:7b-instruct", "embeddinggemma:latest"]
    assert doctor._has_ollama_model(models, "qwen2.5:7b-instruct") is True
    assert doctor._has_ollama_model(models, "qwen2.5") is True          # bare name matches the tag
    assert doctor._has_ollama_model(models, "embeddinggemma") is True   # :latest tag matches the bare name
    assert doctor._has_ollama_model(models, "llama3") is False


def test_recommend_local_when_accel_and_ollama():
    rec = doctor.recommend({"metal": True, "cuda": False, "container": False},
                           {"reachable": True}, {})
    assert rec["profile"] == "local"


def test_recommend_cloud_without_accel():
    rec = doctor.recommend({"metal": False, "cuda": False, "container": False},
                           {"reachable": False}, {})
    assert rec["profile"] == "cloud"


def test_recommend_cloud_in_container():
    rec = doctor.recommend({"metal": True, "cuda": True, "container": True},
                           {"reachable": True}, {})
    assert rec["profile"] == "cloud"           # a container has no local model paths


def test_build_has_all_sections():
    rep = doctor.build()
    for k in ("schema", "hardware", "ollama", "tooling", "credentials", "current", "recommend"):
        assert k in rep
    assert rep["schema"] == doctor.SCHEMA
    assert isinstance(rep["tooling"]["deps"], dict)


def test_write_and_report_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "system-report.json"
    monkeypatch.setattr(doctor, "REPORT_PATH", path)
    rep = doctor.build()
    doctor.write(rep)
    assert path.exists()
    # report() without refresh reads the one from disk (recent)
    got = doctor.report(refresh=False)
    assert got["ts"] == rep["ts"]


def test_report_refresh_rebuilds(tmp_path, monkeypatch):
    path = tmp_path / "system-report.json"
    monkeypatch.setattr(doctor, "REPORT_PATH", path)
    stale = {"schema": doctor.SCHEMA, "ts": 1, "hardware": {}, "ollama": {}, "tooling": {},
             "credentials": [], "current": {}, "recommend": {}}
    doctor.write(stale)
    fresh = doctor.report(refresh=True)
    assert fresh["ts"] > 1                       # re-analysis rebuilds it
