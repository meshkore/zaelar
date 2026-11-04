"""V2-849 step 5 · what the brain reads of the directory comes closest first, and the background is counted, not listed.

Every turn carries the people his sentence names (`people_named`, the «people» block); with the card open, a digest of
the directory; and voice references resolve through `ref_index`. Over a real directory of 2,706 contacts all three read
store order: «Pablo» put four arbitrary rows of fifteen in the prompt, and the digest listed the first fifteen
alphabetically-ish rows of a mostly forgotten address book.

  · `people_named`: a word he gave a person (an alias) names them; a full name names its row in any level; a first
    name brings only the CLOSEST level that has it, and says how many more exist — a count, never an instruction;
  · `prompt_digest`: counts per level, lists his circle and the people he talks to, and says the background is saved
    and found by name;
  · `ref_index`: every visible contact stays nameable (V2-026 — `refs.py` resolves a contactId only there), closest
    first.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    directory._WINDOW.clear()
    from widgets.contactos import data as d
    db = d.load_db()
    recent = [{"platform": "whatsapp", "chatId": "3460001@s.whatsapp.net", "handle": "", "volume": 4,
               "last_seen": time.time() - 2 * 86400}]
    rows = [{"name": "Psm Pablo Buso"}, {"name": "Pablo Elastic"}, {"name": "Pablo Hernandez"},
            {"name": "Pablo Sabin", "channels": recent},
            {"name": "Raquel Salvador Esteban", "aliases": ["mi tontita"]}]
    for i, r in enumerate(rows):
        db["contacts"].append({"id": f"c{i}", "kind": "person", "aliases": [], "relation": "", "channels": [], **r})
    d.store.save(d.WIDGET_ID, db)
    return d


def _names(rows) -> list[str]:
    return [r["name"] for r in rows]


def test_a_first_name_brings_the_closest_level_and_counts_the_rest(ct):
    rows = ct.people_named("pregunta a pablo si ha probado zaelar")
    assert _names(rows) == ["Pablo Sabin"] and rows[-1]["more"] == 2   # «Psm Pablo Buso» is not a first-name match


def test_his_word_for_a_person_names_her(ct):
    assert _names(ct.people_named("dile a mi tontita que voy a casa")) == ["Raquel Salvador Esteban"]


def test_a_full_name_reaches_the_background(ct):
    assert _names(ct.people_named("send Pablo Hernandez the invoice")) == ["Pablo Hernandez"]


def test_the_people_block_carries_the_count_not_an_order(ct):
    from nucleo.turn.prompt import builder
    block = builder._people_block("pregunta a pablo si ha probado zaelar")
    assert "Pablo Sabin" in block and "2 más con ese nombre" in block
    assert "Pablo Elastic" not in block and "pregunta" not in block.split("──")[-1].lower()


def test_the_digest_counts_every_level_and_lists_only_the_closest(ct):
    d = ct.prompt_digest()
    assert "5 entradas" in d and "1 de su círculo" in d and "1 con trato reciente" in d and "3 de fondo" in d
    assert "Pablo Sabin" in d and "Raquel Salvador Esteban" in d
    assert "Pablo Elastic" not in d and "se encuentran por su nombre" in d


def test_every_contact_stays_nameable_closest_first(ct):
    labels = [r["label"] for r in ct.ref_index()]
    assert labels[:2] == ["Raquel Salvador Esteban", "Pablo Sabin"]
    assert {"Psm Pablo Buso", "Pablo Elastic", "Pablo Hernandez"} <= set(labels)
