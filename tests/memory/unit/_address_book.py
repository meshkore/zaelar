"""Shared rig for the V2-854 F3 tests: an isolated memory DB and an isolated contacts store, synthetic people only."""
from __future__ import annotations

import pytest

from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture
def book(tmp_path, monkeypatch):
    """A fresh memory and a fresh address book; returns the contacts card's data module (its door)."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "widgets"))
    from widgets.contactos import data as card
    yield card
    memdb.reset_db()
    mememb.reset()


def add(card, **fields) -> str:
    """One record through the card's own door; its id."""
    out = card.apply_action("add_contact", fields)
    assert out.get("ok"), out
    return out["result"]["contact"]["id"]


def contact_pills() -> list[dict]:
    return [dict(r) for r in memdb.get_db().query(
        "SELECT id, kind, text, slot, meta FROM memories WHERE valid=1 AND kind='contact' ORDER BY id")]
