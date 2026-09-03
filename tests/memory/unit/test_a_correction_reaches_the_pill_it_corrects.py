"""V2-565 — a spoken correction reaches the SLOTLESS pill it corrects.

Measured origin (2026-09-03, «reserva Soria»): STT transcribed «El Fogón» as «Elfo On», the heart stored two
long prefs with the wrong name, the operator corrected himself IN THE SAME conversation («he dicho el fogón»),
the agent acknowledged — and the false pills stayed `valid=1`, because every supersede path keys on `slot` and
additive facts are slotless by design. A worker later spent 15 minutes and $2.25 searching for a restaurant
that does not exist.

The mechanism: `api.correction_targets()` OFFERS the recently written slotless pills to the distiller
(«GUARDADO HACE POCO» block in `_render`), the model may answer with `change:"correction"` + `supersedes:[ids]`,
ingest intersects that answer with the SAME offer (whitelist — the model can only aim at what it was shown),
and the writer applies the supersede at the single chokepoint, slotless-and-valid targets only, reversibly.

Behaviour cases enter through `memory_agent.ingest_utterance` with the heart mocked at `mem_processor.process`
— the real seam (V2-199): what breaks easily here is the plumbing between the model's answer and the row.
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import queue as memqueue
from memory import writer as memwriter
from nucleo import memory_agent


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEM_PROCESSOR", "0")
    monkeypatch.setenv("MEMORY_RERANK", "off")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _atom_processor(monkeypatch, atom: dict):
    """Replaces the heart so the LLM-atom path runs with a known answer — the seam the mechanism hangs from."""
    from nucleo import mem_processor as mp

    async def _process(_t, state=None):
        return [dict(atom)]

    monkeypatch.setattr(mp, "process", _process)
    monkeypatch.setattr(mp, "enabled", lambda: True)


def _ingest(*utterances):
    async def scenario():
        await memapi.start()
        out = []
        for u in utterances:
            out.append(await memory_agent.ingest_utterance(u, role="operator"))
            await memqueue.get_queue().join()
        await memapi.stop()
        return out
    return asyncio.run(scenario())


def _row(mid: int) -> dict:
    return memdb.get_db().query("SELECT id, valid, superseded_by, text FROM memories WHERE id=?", (mid,))[0]


def _garbled_pill() -> int:
    """The state the defect leaves behind: a durable slotless pref carrying an STT mishearing."""
    return memwriter.insert_memory("Su restaurante favorito de Soria es Elfo On.", level="long", kind="pref")


def _correction_atom(target: int) -> dict:
    return {"text": "Su restaurante favorito de Soria es El Fogón del Salvador.", "dest": "long",
            "kind": "pref", "importance": 0.7, "ttl_days": None, "slot": None, "value": None,
            "change": "correction", "concepts": [], "state_patch": {}, "supersedes": [target]}


def test_a_correction_supersedes_the_offered_pill(fresh_db, monkeypatch):
    old = _garbled_pill()
    _atom_processor(monkeypatch, _correction_atom(old))
    _ingest("Que no, he dicho El Fogón del Salvador.")
    r = _row(old)
    assert r["valid"] == 0, "the garbled pill must stop being served"
    new = r["superseded_by"]
    assert new and _row(new)["valid"] == 1, "reversible: the old row points at its living successor"
    assert "Fogón" in _row(new)["text"]


def test_an_id_the_model_was_never_offered_dies_at_the_whitelist(fresh_db, monkeypatch):
    # A pill written OUTSIDE the conversation window was never in the «GUARDADO HACE POCO» offer, so a model
    # (or an injected turn) naming it gets no reach — the whitelist is the same function that built the offer.
    old = _garbled_pill()
    db = memdb.get_db()
    db.execute("UPDATE memories SET created = created - 86400 WHERE id=?", (old,))   # written "yesterday"
    _atom_processor(monkeypatch, _correction_atom(old))
    _ingest("Que no, he dicho El Fogón del Salvador.")
    assert _row(old)["valid"] == 1, "an unoffered id must be unreachable"


def test_without_the_correction_signal_the_ids_have_no_reach(fresh_db, monkeypatch):
    # `supersedes` rides ONLY on change:"correction" — an update naming ids is not a correction.
    old = _garbled_pill()
    atom = dict(_correction_atom(old), change="update")
    _atom_processor(monkeypatch, atom)
    _ingest("Ahora mi favorito es El Fogón del Salvador.")
    assert _row(old)["valid"] == 1


def test_a_slotted_pill_is_out_of_reach_at_the_writer(fresh_db):
    # The chokepoint guard, exercised directly at the chokepoint: identity/state stay untouchable by
    # construction even if an id sneaked through everything above.
    slotted = memwriter.insert_memory("Se llama Ricard.", level="long", kind="profile", slot="operator.name")
    new = memwriter.insert_memory("Su restaurante favorito de Soria es El Fogón del Salvador.",
                                  level="long", kind="pref", supersedes=[slotted])
    assert _row(slotted)["valid"] == 1, "a slotted fact has its own supersede; this path must refuse it"
    assert _row(new)["valid"] == 1


def test_the_survivor_of_a_dedup_still_inherits_the_correction(fresh_db):
    # The corrected pill may collapse into an existing row (exact dedup). Whichever row SURVIVES becomes the
    # successor — applied at the chokepoint precisely so every dedup exit keeps the promise.
    old = _garbled_pill()
    existing = memwriter.insert_memory("Su restaurante favorito de Soria es El Fogón del Salvador.",
                                       level="long", kind="pref")
    survivor = memwriter.insert_memory("Su restaurante favorito de Soria es El Fogón del Salvador.",
                                       level="long", kind="pref", supersedes=[old])
    assert survivor == existing, "precondition: the write deduped into the existing row"
    assert _row(old)["superseded_by"] == existing


def test_the_offer_reaches_the_rendered_prompt(fresh_db):
    # Asserted on `_render`'s OUTPUT, not on the helper: a helper nobody calls passes its own test (V2-199).
    from nucleo import mem_processor as mp
    assert "GUARDADO HACE POCO" not in mp._render("hola", None), "an empty memory must cost zero prompt tokens"
    mid = _garbled_pill()
    rendered = mp._render("Que no, he dicho El Fogón.", None)
    assert f"[{mid}]" in rendered and "Elfo On" in rendered and "GUARDADO HACE POCO" in rendered


def test_conv_rows_are_never_offered(fresh_db):
    # The conversation buffer repeats literal text every turn; offering it would waste the whole window.
    memwriter.insert_memory("Operador: hola · zaelar: hola", level="short", kind="conv")
    assert memapi.correction_targets() == []
