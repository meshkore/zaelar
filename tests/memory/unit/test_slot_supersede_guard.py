"""P0d — a third party's fact must not SUPERSEDE the operator's own identity pill (2026-08-19).

The bug, reproduced end to end before writing a line of the fix: with the operator's birthday established,
"El cumpleaños de Marta es el 3 de mayo." arrived as `dest="long"` with `slot="operator.birthday"`, the writer
applied "the most recent MANDA", the operator's row went `valid=0`, and `query("¿cuándo es mi cumpleaños?")`
answered with Marta's date. The operator's own birthday, silently gone from recall.

Why no existing gate caught it. `_plausibility_demote` (P0b) protects the `state` and does that well — verified in
the same run: `operator_name` stayed Ricart and `birthday` stayed 12 February. But the destructive operation is
the SLOT supersede, and P0b cannot see it: it returns early on `dest != "state"` and then requires the slot to
have a `state_field`. A third-party fact fails BOTH conditions. Five identity slots therefore had no contradiction
protection at all — `birthday`, `phone`, `email`, `address`, `diet` — because the guard is keyed on having a state
field, which is an unrelated property.

Why a deterministic backstop rather than a prompt fix: the prompt ALREADY forbids it ("slot: SOLO para ATRIBUTOS
SINGULARES del operador"; "personas del entorno → slot=null SIEMPRE") and the model does it anyway. Measured with
real API calls: 0/5 with an empty profile, 3/5 with an identity established — it misfires precisely when there is
something to destroy. Samples are small so no rate is claimed; a reproducible loss does not need one.

The disposal is what separates this from P0b: a garbled name is junk and gets QUARANTINED, whereas "Marta's
birthday" is perfectly good information about someone else. So the pill is KEPT as a plain durable fact and only
its `slot` is dropped. Quarantining would fix the overwrite by discarding the fact — the same data loss in a
different hat. Verified against the real pipeline afterwards: both facts coexist, and with the memory language
coherent "cuándo es mi cumpleaños" ranks the operator's pill first while "el cumpleaños de Marta" ranks Marta's
first — the ranking needed no change.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter
from nucleo import memory_agent as MA


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
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


def _establish(slot: str, text: str, value: str) -> int:
    """Write the pill that the guard has to protect, the way `_write_atom` does — with `meta.value`."""
    return memwriter.insert_memory(text, level="long", kind="profile", slot=slot,
                                   meta={"source": "voice", "path": "llm", "value": value})


def _atom(slot: str, value: str, text: str, dest: str = "long") -> dict:
    return {"text": text, "dest": dest, "kind": "fact", "slot": slot, "value": value, "state_patch": {}}


# ── the bug ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_third_partys_value_does_not_supersede_the_operators_identity(fresh_db):
    _establish("operator.birthday", "Su cumpleaños es el 12 de febrero.", "12 de febrero")
    out = MA._slot_supersede_guard(_atom("operator.birthday", "3 de mayo",
                                        "El cumpleaños de Marta es el 3 de mayo."), is_correction=False)
    assert out["slot"] is None, "con slot puesto el writer invalidaría la píldora del operador"
    assert out["text"] == "El cumpleaños de Marta es el 3 de mayo.", "el hecho NO se descarta, solo pierde el slot"
    assert not out.get("_quarantine"), (
        "cuarentenar arreglaría el pisotón tirando el dato — es la misma pérdida con otro sombrero"
    )


def test_the_five_slots_with_no_state_field_are_the_ones_this_covers(fresh_db):
    """These are exactly the slots P0b can never reach, so they are the regression surface that matters."""
    from memory import slots as S
    for slot in ("operator.birthday", "operator.phone", "operator.email", "operator.address", "operator.diet"):
        assert S.SLOTS[slot].state_field is None, f"{slot} ganó un state_field: P0b ya lo cubre, revisa este gate"
        assert slot in S.identity_slots() and slot in S.garble_guard_slots()
        _establish(slot, f"valor establecido de {slot}", "establecido-uno")
        out = MA._slot_supersede_guard(_atom(slot, "otro-valor-distinto", "hecho de un tercero"),
                                       is_correction=False)
        assert out["slot"] is None, f"{slot} sigue sin protección de supersede"


# ── what must still work ─────────────────────────────────────────────────────────────────────────────────────
def test_an_explicit_correction_still_supersedes(fresh_db):
    """The operator saying "no, mi cumpleaños es el 3 de mayo" MUST overwrite. A guard that blocks corrections
    freezes the first thing it ever heard, which is a worse failure than the one it prevents."""
    _establish("operator.birthday", "Su cumpleaños es el 12 de febrero.", "12 de febrero")
    out = MA._slot_supersede_guard(_atom("operator.birthday", "3 de mayo", "Su cumpleaños es el 3 de mayo."),
                                   is_correction=True)
    assert out["slot"] == "operator.birthday"


def test_the_first_value_of_a_slot_passes(fresh_db):
    out = MA._slot_supersede_guard(_atom("operator.birthday", "12 de febrero", "Su cumpleaños es el 12 de febrero."),
                                   is_correction=False)
    assert out["slot"] == "operator.birthday"


def test_the_same_value_again_passes(fresh_db):
    """Repeating a fact is reinforcement, not a conflict — it has to keep reaching the slot's dedup."""
    _establish("operator.email", "Su correo es rj@proars.com.", "rj@proars.com")
    out = MA._slot_supersede_guard(_atom("operator.email", "RJ@Proars.com", "Su correo es RJ@Proars.com."),
                                   is_correction=False)
    assert out["slot"] == "operator.email"


def test_a_refinement_of_the_same_entity_passes(fresh_db):
    """Same rule P0b already uses (V2-050): sharing a distinctive token means facets of one thing, not a conflict.
    Reused deliberately instead of inventing a second notion of "contradiction" that would drift from it."""
    _establish("operator.address", "Vive en Calle Mallorca 200.", "Calle Mallorca 200")
    out = MA._slot_supersede_guard(_atom("operator.address", "Calle Mallorca 200, 3º 2ª",
                                        "Vive en Calle Mallorca 200, 3º 2ª."), is_correction=False)
    assert out["slot"] == "operator.address"


def test_a_slot_that_evolves_by_rephrasing_is_untouched(fresh_db):
    """`garble_guard=False` slots (treatment, job, family) change by being restated — that is their contract, and
    quarantining/derailing them is the 2026-07-19 incident where operator.treatment ended with 0 valid rows."""
    from memory import slots as S
    assert S.SLOTS["operator.treatment"].garble_guard is False
    _establish("operator.treatment", "Prefiere trato directo.", "directo")
    out = MA._slot_supersede_guard(_atom("operator.treatment", "cercano", "Prefiere trato cercano."),
                                   is_correction=False)
    assert out["slot"] == "operator.treatment"


def test_no_declared_value_leaves_behaviour_unchanged(fresh_db):
    """Fail-open on the question itself. Without a `value` there is nothing to compare, and comparing SENTENCES
    instead would misfire: "Su cumpleaños es el 12 de febrero" and "El cumpleaños de Marta es el 3 de mayo" share
    the token "cumpleaños", which the refinement test reads as the same entity."""
    _establish("operator.birthday", "Su cumpleaños es el 12 de febrero.", "12 de febrero")
    atom = _atom("operator.birthday", "", "El cumpleaños de Marta es el 3 de mayo.")
    assert MA._slot_supersede_guard(atom, is_correction=False)["slot"] == "operator.birthday"


def test_an_established_pill_from_before_P0d_declines_to_act(fresh_db):
    """Rows written before P0d carry no `meta.value`. The guard must decline rather than guess — and it must not
    fall back to text comparison, for the reason in the test above."""
    memwriter.insert_memory("Su cumpleaños es el 12 de febrero.", level="long", kind="profile",
                            slot="operator.birthday", meta={"source": "voice", "path": "llm"})
    out = MA._slot_supersede_guard(_atom("operator.birthday", "3 de mayo",
                                        "El cumpleaños de Marta es el 3 de mayo."), is_correction=False)
    assert out["slot"] == "operator.birthday"


def test_a_slot_less_atom_is_never_touched(fresh_db):
    out = MA._slot_supersede_guard({"text": "algo", "dest": "long", "slot": None, "value": "x"},
                                   is_correction=False)
    assert out["slot"] is None and out["text"] == "algo"


# ── visibility and persistence ───────────────────────────────────────────────────────────────────────────────
def test_the_guard_is_VISIBLE_when_it_fires(fresh_db, monkeypatch):
    """A protection that fires in silence is indistinguishable from the bug it prevents — the rule this module has
    already paid for three times (the REM KeyError, the two-day-dead distiller, the latched embedding backend)."""
    seen = []
    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit", lambda *a, **k: seen.append((a, k)))
    _establish("operator.birthday", "Su cumpleaños es el 12 de febrero.", "12 de febrero")
    MA._slot_supersede_guard(_atom("operator.birthday", "3 de mayo", "El cumpleaños de Marta es el 3 de mayo."),
                             is_correction=False)
    assert seen, "el gate saltó sin dejar rastro"
    assert any("operator.birthday" in json.dumps(k, default=str) for _, k in seen)


def test_write_atom_persists_the_canonical_value(fresh_db):
    """`meta.value` is what makes the guard possible at all: the distiller computed it, used it to build
    `state_patch`, and it was then discarded — so for the five slots with no `state_field` nothing on the row
    recorded WHAT the slot holds, only a sentence containing it."""
    written = {}

    async def _fake_remember(payload):
        written.update(payload)

    import nucleo.memory_agent as _MA
    orig, _MA.remember = _MA.remember, _fake_remember
    try:
        asyncio.run(_MA._write_atom(
            _atom("operator.birthday", "12 de febrero", "Su cumpleaños es el 12 de febrero."),
            raw="mi cumpleaños es el 12 de febrero"))
    finally:
        _MA.remember = orig
    assert written["meta"]["value"] == "12 de febrero"


def test_no_value_is_persisted_for_a_slot_less_pill(fresh_db):
    """`meta.value` only means something as the value OF A SLOT; stamping it on a free pill would invite a future
    reader to treat a loose fact as a canonical singular value."""
    written = {}

    async def _fake_remember(payload):
        written.update(payload)

    import nucleo.memory_agent as _MA
    orig, _MA.remember = _MA.remember, _fake_remember
    try:
        asyncio.run(_MA._write_atom({"text": "Le gusta el buceo.", "dest": "long", "kind": "pref",
                                     "slot": None, "value": "buceo", "state_patch": {}},
                                    raw="me gusta el buceo"))
    finally:
        _MA.remember = orig
    assert "value" not in written["meta"]
