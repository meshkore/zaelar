"""test_credentials.py — escritor del credential store (V2-040). Verifica: persistencia + chmod 600, quoting de
valores con espacios, vista redactada (solo presencia, NUNCA el valor), borrado con valor vacío, y rechazo de
nombres inválidos. Ejecutar: .venv/bin/pytest config/test_credentials.py
"""
import os

import pytest

import config.credentials as cred


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(cred, "STORE", Path(tmp_path) / "zaelar.env")
    for k in ("AIMLAPI_KEY", "FOO_TOKEN", "PLAIN_VAL", "DEEPGRAM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return cred


def test_set_persists_chmod_600_and_hot_env(store):
    res = store.set_key("AIMLAPI_KEY", "sk-secret-123")
    assert res["ok"] and res["set"] is True
    assert store.STORE.exists()
    assert oct(store.STORE.stat().st_mode & 0o777) == "0o600"     # solo el dueño
    assert os.getenv("AIMLAPI_KEY") == "sk-secret-123"            # aplicado en caliente


def test_status_redacts_value(store):
    store.set_key("AIMLAPI_KEY", "sk-supersecret")
    st = store.status(["AIMLAPI_KEY", "DEEPGRAM_API_KEY"])
    assert st["AIMLAPI_KEY"] == {"set": True, "secret": True}
    assert st["DEEPGRAM_API_KEY"]["set"] is False
    assert "sk-supersecret" not in str(st)                        # el valor NUNCA sale


def test_value_with_spaces_is_quoted(store):
    store.set_key("FOO_TOKEN", "abc def")
    assert 'FOO_TOKEN="abc def"' in store.STORE.read_text()
    assert store.get("FOO_TOKEN") == "abc def"                    # y se lee sin comillas


def test_empty_value_deletes(store):
    store.set_key("AIMLAPI_KEY", "x")
    assert store.status(["AIMLAPI_KEY"])["AIMLAPI_KEY"]["set"] is True
    store.set_key("AIMLAPI_KEY", "")
    assert store.status(["AIMLAPI_KEY"])["AIMLAPI_KEY"]["set"] is False
    assert os.getenv("AIMLAPI_KEY") in (None, "")


def test_invalid_key_rejected(store):
    assert store.set_key("bad name!", "x")["ok"] is False
    assert store.set_key("", "x")["ok"] is False


def test_preserves_other_lines_and_comments(store):
    store.STORE.write_text("# my creds\nEXISTING_KEY=keepme\n")
    store.set_key("NEW_KEY", "added")
    txt = store.STORE.read_text()
    assert "# my creds" in txt and "EXISTING_KEY=keepme" in txt and "NEW_KEY=added" in txt


def test_is_secret_classification():
    assert cred.is_secret("OPENAI_API_KEY") and cred.is_secret("TG_API_HASH")
    assert cred.is_secret("MESHKORE_API_TOKEN") and cred.is_secret("LIVEKIT_API_SECRET")
    assert not cred.is_secret("ZAELAR_LANGUAGE") and not cred.is_secret("PORT")
