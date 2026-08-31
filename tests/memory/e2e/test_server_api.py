"""Tests for memory/server_api.py — upload → episodic memory → search (V2-003 · T54)."""
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory import db as memdb
from memory import embeddings as mememb
from memory import retriever as memret
from server.memory_routes import router


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    memdb.reset_db()


def test_upload_lands_in_episodic_and_is_searchable(client):
    files = {"file": ("informe.txt", io.BytesIO("precios de Wallapop en Barcelona".encode()), "text/plain")}
    r = client.post("/api/files/upload", files=files, data={"source": "paste"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "informe.txt" and body["episode_id"]
    # the file summary is retrievable through memory.query (retriever)
    res = memret.search("Wallapop", limit=5, expand=False)
    assert res, "el resumen del archivo subido debe ser buscable"


def test_upload_then_list(client):
    client.post("/api/files/upload",
                files={"file": ("doc.txt", io.BytesIO(b"hola"), "text/plain")})
    r = client.get("/api/files")
    assert r.status_code == 200
    names = {f["name"] for f in r.json()["files"]}
    assert "doc.txt" in names


def test_upload_too_large_rejected(client):
    big = io.BytesIO(b"x" * (51 * 1024 * 1024))
    r = client.post("/api/files/upload", files={"file": ("big.bin", big, "application/octet-stream")})
    assert r.status_code == 413


def test_memory_map_endpoint(client):
    from memory import api as memapi
    memapi.write_now("recuerdo corto", kind="event", level="short")
    memapi.write_now("hecho largo", kind="fact", level="long")
    r = client.get("/api/memory/map")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"
    body = r.json()
    assert set(body) >= {"state", "layers", "edges", "counts"}
    assert body["counts"]["short"] >= 1 and body["counts"]["long"] >= 1
    # The map must reflect the operator's REAL language, not a fixed one. This assert used to say "es" when the
    # product had Spanish as its default; with the default set to English (V2-089), it failed even though nothing
    # was broken. What is tested here is that the endpoint does not invent the language, checked against the source.
    from voice.engine.core import langs
    assert body["state"]["language"] == langs.current_code(), (
        f"el mapa dice {body['state']['language']!r} y el idioma del operador es {langs.current_code()!r}")
