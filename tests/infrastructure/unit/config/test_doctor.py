"""test_doctor.py — detector de capacidades (V2-040). Verifica: presencia de credenciales (redactada), match de
modelos de Ollama, recomendación de perfil por hardware, y el roundtrip build→write→report. Ejecutar:
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
    # el secreto NUNCA aparece en el informe
    assert "sk-secret-value" not in json.dumps(doctor.credentials())


def test_ollama_model_match_by_tag_and_base():
    models = ["qwen2.5:7b-instruct", "embeddinggemma:latest"]
    assert doctor._has_ollama_model(models, "qwen2.5:7b-instruct") is True
    assert doctor._has_ollama_model(models, "qwen2.5") is True          # nombre pelado casa el tag
    assert doctor._has_ollama_model(models, "embeddinggemma") is True   # tag :latest casa el pelado
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
    assert rec["profile"] == "cloud"           # un contenedor no tiene rutas de modelo local


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
    # report() sin refresh lee el de disco (reciente)
    got = doctor.report(refresh=False)
    assert got["ts"] == rep["ts"]


def test_report_refresh_rebuilds(tmp_path, monkeypatch):
    path = tmp_path / "system-report.json"
    monkeypatch.setattr(doctor, "REPORT_PATH", path)
    stale = {"schema": doctor.SCHEMA, "ts": 1, "hardware": {}, "ollama": {}, "tooling": {},
             "credentials": [], "current": {}, "recommend": {}}
    doctor.write(stale)
    fresh = doctor.report(refresh=True)
    assert fresh["ts"] > 1                       # re-analizar reconstruye
