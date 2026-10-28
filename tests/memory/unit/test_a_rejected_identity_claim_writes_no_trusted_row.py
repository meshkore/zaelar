"""V2-802 T-02 · An identity claim a gate rejects is rejected — it never becomes a trusted row.

The class: three gates can refuse an operator-identity pill (the «is this turn about him?» question, P0b's
plausibility demote, P0d's slot-supersede guard), and only one of them disposed of what it refused. The other two
stripped the SLOT and let the pill fall through to `_write_atom`, which wrote it as a pinned `long` profile row with
`slot=NULL` and full trust. Measured: ambient TV audio («Bruno Velasco.») was refused for the slot and still stored
as «the operator is called Bruno Velasco», recallable for good.

One disposal now (`gates._quarantine_identity`): `meta.trust=untrusted`, no slot, no state, not pinned —
recoverable by an explicit query, never surfacing in recall or the prompt. A TYPED turn is exempt from the
«about him?» question: nobody types by accident, and a pasted signature never speaks in the first person.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from memory import writer as memwriter
from nucleo import memory_agent
from nucleo.memory_agent import gates


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEMORY_RERANK", "off")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _distiller_says(monkeypatch, atom: dict):
    from nucleo.memory_agent.processor import distill, distill_config

    async def _process(_t, state=None):
        return [dict(atom)]

    monkeypatch.setattr(distill, "process", _process)
    monkeypatch.setattr(distill_config, "enabled", lambda: True)


def _ingest(text: str, channel: str = "voice") -> None:
    async def scenario():
        await memapi.start()
        await memory_agent.ingest_utterance(text, role="operator", channel=channel)
        await memqueue.get_queue().join()
        await memapi.stop()
    asyncio.run(scenario())


def _rows(sub: str) -> list[dict]:
    return [dict(r) for r in memdb.get_db().query(
        "SELECT text, slot, pinned, json_extract(meta,'$.trust') AS trust, json_extract(meta,'$.source') AS source "
        "FROM memories WHERE valid=1 AND kind != 'concept' AND lower(text) LIKE ?", (f"%{sub.lower()}%",))]


_NAME_FROM_THE_TV = {"text": "El operador se llama Bruno Velasco.", "dest": "state", "kind": "profile",
                     "importance": 0.95, "ttl_days": None, "slot": "operator.name", "value": "Bruno Velasco",
                     "change": "none", "state_patch": {"operator_name": "Bruno Velasco"}}


def test_an_ambient_name_on_an_empty_profile_writes_no_trusted_row(fresh_db, monkeypatch):
    """The incident with nothing established to contradict: no later guard had anything to compare, so the
    stranger's name went straight into `state` as HIS."""
    _distiller_says(monkeypatch, _NAME_FROM_THE_TV)
    _ingest("Bruno Velasco.")
    assert not memapi.state().get("operator_name"), f"a TV name became his: {memapi.state()!r}"
    rows = _rows("velasco")
    assert rows, "the pill vanished: a rejected claim is quarantined (recoverable), not deleted"
    bad = [r for r in rows if (r["trust"] or "") != "untrusted" or r["slot"] or r["pinned"]]
    assert not bad, f"a rejected identity claim was written as a trusted row: {bad}"
    pasivo = " ".join(m["text"].lower() for m in memapi.salient_long())
    assert "velasco" not in pasivo, f"it surfaces in «what you know about the operator»: {pasivo!r}"


def test_an_ambient_name_against_an_established_slot_pill_writes_no_trusted_row(fresh_db, monkeypatch):
    """The supersede-guard path of the incident: the slot pill exists (with its value), `state` does not carry the
    name, so P0b had nothing to compare and P0d stripped the slot — and the row was written pinned and trusted."""
    memwriter.insert_memory("El operador se llama Pablo.", level="long", kind="profile", slot="operator.name",
                            meta={"source": "voice", "path": "llm", "value": "Pablo"})
    _distiller_says(monkeypatch, _NAME_FROM_THE_TV)
    _ingest("Bruno Velasco.")
    bad = [r for r in _rows("velasco") if (r["trust"] or "") != "untrusted" or r["pinned"]]
    assert not bad, f"a rejected identity claim was written as a trusted row: {bad}"


def test_the_supersede_guard_quarantines_a_contradicting_claim_the_distiller_put_in_state(fresh_db):
    """Even when the turn IS about him: `dest=state` is the distiller declaring it HIS identity, so a value that
    contradicts the established one is P0b's case — quarantine. A third party's misslotted fact (`dest=long`) is
    still kept as a plain durable fact (covered in `test_slot_supersede_guard`)."""
    memwriter.insert_memory("Su correo es ana@uno.es.", level="long", kind="profile", slot="operator.email",
                            meta={"source": "voice", "path": "llm", "value": "ana@uno.es"})
    out = gates._slot_supersede_guard({"text": "Su correo es pepe@dos.es.", "dest": "state", "kind": "profile",
                                       "slot": "operator.email", "value": "pepe@dos.es", "state_patch": {}},
                                      is_correction=False)
    assert out.get("_quarantine") and out["dest"] == "long" and not out.get("slot") and not out.get("pinned"), out


def test_a_typed_signature_is_not_refused_for_lacking_the_first_person(fresh_db, monkeypatch):
    """The control: a pasted email signs «Ana Ruiz» with no «I». Written by him, it is not ambient audio."""
    _distiller_says(monkeypatch, dict(_NAME_FROM_THE_TV, text="El operador se llama Ana Ruiz.", value="Ana Ruiz",
                                      state_patch={"operator_name": "Ana Ruiz"}))
    _ingest("Un saludo,\nAna Ruiz\nana@ejemplo.com", channel="typed")
    assert memapi.state().get("operator_name") == "Ana Ruiz", memapi.state()
    assert {r["source"] for r in _rows("ana ruiz")} == {"typed"}, _rows("ana ruiz")
