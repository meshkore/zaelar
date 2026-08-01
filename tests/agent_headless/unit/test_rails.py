"""Tests de nucleo/rails.py (V2-042) — RAILS: registro de runs vivos + proyección al estado + guía situacional."""
import time

import pytest

from nucleo import rails


@pytest.fixture(autouse=True)
def _iso(monkeypatch):
    """Aísla el registro RAM y captura la proyección (sin tocar la memoria real)."""
    projected = {}

    def _fake_set_state(fields):
        projected.update(fields or {})
        return projected

    from memory import api as mapi
    monkeypatch.setattr(mapi, "set_state", _fake_set_state)
    rails._RUNS.clear()
    yield projected
    rails._RUNS.clear()


def test_upsert_and_get():
    a = rails.upsert("music.search", "vuela conmigo", status="searching", bump=True)
    assert a["kind"] == "music.search" and a["status"] == "searching" and a["attempts"] == 1
    assert rails.get("music.search")["label"] == "vuela conmigo"


def test_singleton_new_label_replaces_and_resets_attempts():
    rails.upsert("music.search", "cancion A", bump=True)
    rails.upsert("music.search", "cancion A", bump=True)
    assert rails.get("music.search")["attempts"] == 2
    rails.upsert("music.search", "cancion B", bump=True)     # OTRO objetivo → sustituye, intentos de cero
    a = rails.get("music.search")
    assert a["label"] == "cancion B" and a["attempts"] == 1


def test_fail_keeps_isolated_sin_resolver():
    rails.upsert("music.search", "vuela conmigo", status="searching", bump=True)
    rails.fail("music.search", "la web no la identificó")
    a = rails.get("music.search")
    assert a["status"] == "sin_resolver" and "identificó" in a["detail"]
    assert any(x["kind"] == "music.search" for x in rails.live())   # sigue vivo (aislado), no borrado


def test_resolve_removes():
    rails.upsert("music.search", "x")
    rails.resolve("music.search")
    assert rails.get("music.search") is None


def test_ttl_expires():
    rails.upsert("music.search", "x", status="searching")
    rails._RUNS["music.search"]["updated"] = time.time() - 11 * 60   # > TTL searching (10 min)
    assert not rails.live()


def test_projection_shape(_iso):
    rails.upsert("music.playing", "Come Fly With Me — Frank Sinatra", status="playing", detail="vía spotify")
    payload = _iso.get("rails")
    assert payload and payload[0]["kind"] == "music.playing" and payload[0]["status"] == "playing"
    assert "label" in payload[0] and "attempts" in payload[0]


def test_prompt_lines_only_when_live_and_matching_status():
    # rail en reposo → sin guía (cero coste de prompt)
    assert rails.prompt_lines() == []
    # buscando (aún no fallida) → la guía de music.search aplica solo a sin_resolver
    rails.upsert("music.search", "vuela conmigo", status="searching")
    assert rails.prompt_lines() == []
    rails.fail("music.search")
    lines = rails.prompt_lines()
    assert lines and "SIN RESOLVER" in lines[0] and "play_music" in lines[0]
    # resuelta → desaparece la guía
    rails.resolve("music.search")
    assert rails.prompt_lines() == []


def test_compose_state_renders_rails(_iso, monkeypatch):
    """La memoria pinta la línea 'Rails en curso' con estado legible (sin_resolver → SIN RESOLVER)."""
    import memory.api as mapi
    st = {"rails": [{"kind": "music.search", "label": "vuela conmigo", "status": "sin_resolver",
                     "detail": "la web no la identificó", "attempts": 2}]}
    monkeypatch.setattr(mapi._state, "read", lambda: st)
    monkeypatch.setattr(mapi, "critical_facts", lambda limit=6: [])
    monkeypatch.setattr(mapi, "salient_long", lambda limit=5, max_chars=440: [])
    monkeypatch.setattr(mapi, "recent_short", lambda limit=20: [])
    block, _op, stats = mapi.compose_state(mission_fallback="m")
    assert "Rails en curso" in block and "SIN RESOLVER" in block and "vuela conmigo" in block
    assert "(2 intentos)" in block
