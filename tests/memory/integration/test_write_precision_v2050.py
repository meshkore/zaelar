"""V2-050 — WRITE PRECISION (continuation of V2-033): identity/long-term memory is not contaminated by garble.

Reproduces the failures found after booking the vehicle inspection (2026-07-17), where memory was built INCORRECTLY:
  [P0c·A] TYPED slot with malformed VALUE ('mi email es rjj.com' → 'rjj.com' without @) → NOT durable (it contaminated and
          competed with the valid email rjj@proars.com).
  [P0c·B] reified request misassigned to an IDENTITY slot ('quiere que entre en la web y reserve' →
          operator.treatment) → it is NOT that attribute → rejection. A stable attribute is never "quiere que…".
  [P0c·C] VAGUE reified request ('quiere que repitan algo', undefined object) → NOT durable; a CONCRETE task
          ('quiere que le reserve la cita') IS preserved.

Two levels: (1) the direct deterministic GATE `_precision_reject_atom` (without an LLM or DB, exact precision);
(2) the REAL write PATH with `mem_processor.process` mocked to inject the exact atom produced by the LLM
in production → verifies that a rejected atom does NOT reach long-term memory and a valid one DOES. Isolated DB (tmp_path).
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from nucleo import memory_agent
from nucleo import mem_processor


# ── (1) Direct deterministic GATE — the exact precision of each rule ────────────────────────────────────────
@pytest.mark.parametrize("atom, expect, label", [
    ({"slot": "operator.email", "value": "rjj.com", "text": "Su correo electrónico es rjj.com."},
     True, "A: email sin @"),
    ({"slot": "operator.email", "value": "rjj@proars.com", "text": "Su correo electrónico es rjj@proars.com."},
     False, "A-control: email válido"),
    ({"slot": "operator.phone", "value": "605", "text": "Su teléfono es 605."},
     True, "A: teléfono cortado"),
    ({"slot": "operator.phone", "value": "605802311", "text": "Su teléfono es 605802311."},
     False, "A-control: teléfono válido"),
    ({"slot": "operator.treatment", "text": "El operador quiere que entre en la web y reserve cita.", "kind": "pref"},
     True, "B: petición mis-slotteada a treatment"),
    ({"slot": "operator.treatment", "text": "Prefiere trato directo, sin rodeos.", "kind": "pref"},
     False, "B-control: treatment real"),
    ({"slot": None, "text": "El operador quiere que repitan algo.", "kind": "intent"},
     True, "C: petición vaga reificada"),
    ({"slot": None, "text": "El operador quiere que le reserve la cita de la ITV en Soria.", "kind": "intent"},
     False, "C-control: tarea concreta se conserva"),
    ({"slot": None, "text": "El operador quiere que su hijo estudie medicina.", "kind": "fact"},
     False, "C-control: deseo de vida (no asistente)"),
    ({"slot": "operator.name", "value": "Ricart Juncadella", "text": "El operador se llama Ricart Juncadella."},
     False, "control: nombre real"),
    ({"slot": None, "text": "El operador prefiere que le escriban al correo por la mañana.", "kind": "pref"},
     False, "A-control: preferencia que MENCIONA correo (no es un email)"),
])
def test_precision_gate(atom, expect, label):
    assert memory_agent._precision_reject_atom(atom, raw=atom.get("text", "")) is expect, label


def test_malformed_email_value(label="unidad _atom_value_invalid"):
    assert memory_agent._atom_value_invalid({"slot": "operator.email", "value": "rjj.com"}) is True
    assert memory_agent._atom_value_invalid({"slot": "operator.email", "value": "a@b.co"}) is False
    assert memory_agent._atom_value_invalid({"slot": "operator.phone", "value": "12"}) is True
    assert memory_agent._atom_value_invalid({"slot": None, "text": "cualquier cosa"}) is False


def test_double_namespaced_slot_canonicalizes():
    """The CORE double-namespaces ('operator.goal.current','operator.objetivo') → they must collapse to goal.current
    (state_field objetivo). REAL slots are untouched; an 'operator.<unknown>' is not invented. bot v1 #20/#28."""
    from memory import slots
    assert slots.canonical("operator.goal.current") == "goal.current"
    assert slots.state_field("operator.goal.current") == "objetivo"
    assert slots.canonical("operator.project.current") == "project.current"
    assert slots.canonical("operator.name") == "operator.name"          # real slot: unchanged
    assert slots.canonical("operator.car") == "operator.car"
    assert slots.canonical("operator.foo") == "operator.foo"            # unknown: not invented


def test_incoming_msg_regex_excludes_identity():
    """The incoming-message backstop must NOT confuse 'me llamo X' (IDENTITY) with 'me llamó X' (was called)."""
    fires = lambda t: bool(memory_agent._INCOMING_MSG_RE.search(t) and not memory_agent._EMPTY_MSG_RE.search(t))
    assert fires("Me escribió Carlos: la reunión se mueve.") is True
    assert fires("Me llamó Carlos ayer por teléfono.") is True
    assert fires("Me llamo Ramón y juego a pádel.") is False       # IDENTITY, without accent
    assert fires("No me dijo nada.") is False


# ── (2) REAL write PATH with the LLM atom mocked ─────────────────────────────────────────────────
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


def _durables() -> list[str]:
    rows = memdb.get_db().query(
        "SELECT text FROM memories WHERE valid=1 AND level IN ('mid', 'long') AND kind != 'concept'")
    return [r["text"] for r in rows]


def _run_with_atoms(monkeypatch, utterance, atoms):
    """Ingests one turn through the REAL path, with the LLM processor returning `atoms` (the exact production atoms)."""
    async def _fake_process(text, *, state=None):
        return atoms
    monkeypatch.setattr(mem_processor, "enabled", lambda: True)
    monkeypatch.setattr(mem_processor, "process", _fake_process)

    async def scenario():
        await memapi.start()
        res = await memory_agent.ingest_utterance(utterance, role="operator")
        await memqueue.get_queue().join()
        await memapi.stop()
        return res
    return asyncio.run(scenario())


def test_malformed_email_not_durable_e2e(fresh_db, monkeypatch):
    """The atom produced by the LLM in production for 'mi email es rjj.com' must NOT reach long-term memory."""
    _run_with_atoms(monkeypatch, "Y mi email es rjj.com.", [
        {"text": "Su correo electrónico es rjj.com.", "dest": "long", "slot": "operator.email",
         "kind": "fact", "value": "rjj.com", "change": "none"},
    ])
    assert not any("rjj.com" in t.lower() for t in _durables()), f"email garble quedó durable: {_durables()}"


def test_valid_email_is_durable_e2e(fresh_db, monkeypatch):
    """Control: a WELL-FORMED email IS stored (do not over-reject)."""
    _run_with_atoms(monkeypatch, "Mi correo es rjj@proars.com.", [
        {"text": "Su correo electrónico es rjj@proars.com.", "dest": "long", "slot": "operator.email",
         "kind": "fact", "value": "rjj@proars.com", "change": "none"},
    ])
    assert any("proars.com" in t.lower() for t in _durables()), f"el email bueno debe quedar: {_durables()}"


def test_namespaced_goal_slot_canonicalizes_e2e(fresh_db, monkeypatch):
    """The CORE sometimes namespaces 'operator.goal' (by analogy with operator.name). It must COLLAPSE to goal.current
    → sets the 'objetivo' state AND does not create a parallel lineage (bot v2 #25/#26). Alias in memory/slots.py."""
    _run_with_atoms(monkeypatch, "Mi gran meta es terminar una maratón.", [
        {"text": "Su objetivo vital actual es terminar una maratón.", "dest": "state", "slot": "operator.goal",
         "kind": "profile", "value": "terminar una maratón", "change": "none"},
    ])
    obj = (memapi.state().get("objetivo") or "").lower()
    assert "marat" in obj, f"el objetivo namespaced debe fijar el estado: {memapi.state()}"
    # exactly one current entry under the canonical goal.current slot (no parallel operator.goal lineage)
    from memory import slots as _sl
    rows = memdb.get_db().query("SELECT slot FROM memories WHERE valid=1 AND slot IS NOT NULL AND slot != ''")
    goal_slots = [r["slot"] for r in rows if _sl.canonical(r["slot"]) == "goal.current"]
    assert all(s == "goal.current" for s in goal_slots), f"linaje paralelo sin canonizar: {goal_slots}"


def test_same_entity_refinement_collapses_e2e(fresh_db, monkeypatch):
    """The same car in 3 phrasings ('Dacia Duster'/'Duster gris'/'Duster de Dacia') shares «duster» → refinement,
    not garble → the slot supersedes down to ≤2 (not 3 quarantined entries without a slot). bot v2 #21."""
    calls = iter([
        [{"text": "Conduce un Dacia Duster.", "dest": "long", "slot": "operator.car", "kind": "fact",
          "value": "Dacia Duster", "change": "none"}],
        [{"text": "Su coche es un Duster gris.", "dest": "long", "slot": "operator.car", "kind": "fact",
          "value": "Duster gris", "change": "none"}],
        [{"text": "Su coche es un Duster de Dacia.", "dest": "long", "slot": "operator.car", "kind": "fact",
          "value": "Duster de Dacia", "change": "none"}],
    ])

    async def _seq(text, *, state=None):
        return next(calls)
    monkeypatch.setattr(mem_processor, "enabled", lambda: True)
    monkeypatch.setattr(mem_processor, "process", _seq)

    async def scenario():
        await memapi.start()
        for u in ("Conduzco un Dacia Duster.", "Mi coche es un Duster gris.", "Tengo un Duster de Dacia."):
            await memory_agent.ingest_utterance(u, role="operator")
            await memqueue.get_queue().join()
        await memapi.stop()
    asyncio.run(scenario())
    dur = [t for t in _durables() if "duster" in t.lower()]
    assert len(dur) <= 2, f"el mismo coche dejó {len(dur)} píldoras (esperado ≤2): {dur}"


def test_name_garble_sharing_first_name_still_quarantined_e2e(fresh_db, monkeypatch):
    """CONTROL that refinement does NOT loosen the identity anti-garble check: 'Ana García' → 'Ana Pérez' shares
    only 'Ana' (<4) and the surname differs → it remains garble → does NOT overwrite the established name."""
    _run_with_atoms(monkeypatch, "Me llamo Ana García.", [
        {"text": "El operador se llama Ana García.", "dest": "state", "slot": "operator.name",
         "kind": "profile", "value": "Ana García", "change": "none"}])
    _run_with_atoms(monkeypatch, "Soy Ana Pérez.", [
        {"text": "El operador se llama Ana Pérez.", "dest": "state", "slot": "operator.name",
         "kind": "profile", "value": "Ana Pérez", "change": "none"}])
    assert memapi.state().get("operator_name") == "Ana García", \
        f"un garble de apellido NO debe sobrescribir el nombre: {memapi.state().get('operator_name')!r}"


def test_incoming_message_preserved_when_llm_hallucinates_e2e(fresh_db, monkeypatch):
    """An incoming message ('Me escribió Carlos... la reunión se mueve al viernes') must remain durable EVEN IF the
    CORE hallucinates a few-shot placeholder → the backstop stores the RAW TEXT (with carlos+viernes). bot v1 #24/#29."""
    _run_with_atoms(monkeypatch, "Me escribió Carlos por WhatsApp: la reunión del jueves se mueve al viernes.", [
        {"text": "X me pidió Y para el día Z.", "dest": "long", "slot": None, "kind": "event",
         "value": "Carlos", "change": "none"},   # átomo BASURA que produce el LLM (placeholder)
    ])
    dur = " ".join(_durables()).lower()
    assert "carlos" in dur and "viernes" in dur, f"el mensaje entrante crudo debe quedar durable: {_durables()}"


def test_own_task_not_treated_as_incoming_e2e(fresh_db, monkeypatch):
    """CONTROL: an empty negation ('no me dijo nada') does NOT trigger the incoming-message backstop."""
    res = _run_with_atoms(monkeypatch, "No me dijo nada.", [])
    assert not any("no me dijo nada" in t.lower() for t in _durables()), f"negación vacía no debe persistir: {_durables()}"


def test_state_patch_slotname_key_renamed_and_superseded_e2e(fresh_db, monkeypatch):
    """The CORE inserts 'goal.current' as a state KEY (the slot name, not the 'objetivo' field) → it must be
    renamed to 'objetivo' and a NEW goal must supersede the old one, with no stray key (bot v1 #20/#28)."""
    _run_with_atoms(monkeypatch, "Mi objetivo es lanzar en septiembre.", [
        {"text": "Su objetivo actual es lanzar en septiembre.", "dest": "state", "slot": "operator.goal.current",
         "kind": "profile", "value": "lanzar en septiembre",
         "state_patch": {"goal.current": "lanzar en septiembre"}, "change": "none"}])
    st = memapi.state()
    assert "septiembre" in (st.get("objetivo") or "").lower(), f"objetivo no fijado: {st}"
    assert "goal.current" not in st, f"clave stray de slot en el estado: {list(st)}"
    _run_with_atoms(monkeypatch, "Cambio: ahora mi objetivo es la demo para inversores.", [
        {"text": "Su objetivo actual es preparar la demo para inversores.", "dest": "state", "slot": "goal.current",
         "kind": "profile", "value": "preparar la demo para inversores",
         "state_patch": {"objetivo": "preparar la demo para inversores"}, "change": "update"}])
    st = memapi.state()
    assert "inversores" in (st.get("objetivo") or "").lower(), f"objetivo no superseded: {st}"
    assert "septiembre" not in " ".join(str(v) for v in st.values()).lower(), f"objetivo viejo persiste: {st}"


def test_request_not_slotted_to_identity_e2e(fresh_db, monkeypatch):
    """A reified request assigned to operator.treatment does NOT contaminate identity or state."""
    _run_with_atoms(monkeypatch, "Entra en la web y resérvame la cita directamente.", [
        {"text": "El operador quiere que entre en la web y reserve cita directamente.", "dest": "state",
         "slot": "operator.treatment", "kind": "pref", "value": "entrar en la web, reservar cita", "change": "none"},
    ])
    st = " ".join(str(v) for v in memapi.state().values()).lower()
    assert "reserve cita" not in st and "reservar cita" not in st, f"treatment contaminado: {memapi.state()}"
    assert not any("quiere que entre" in t.lower() for t in _durables()), f"petición quedó durable: {_durables()}"


# ── Forgetting: the DECISION tail is not part of the object (bot v2 #65, 2026-07-17) ──────────────────────────
def _forget_obj(t: str):
    fm = memory_agent._FORGET_RE.match(t)
    if not fm:
        return None
    o = fm.group(1).strip()
    return memory_agent._FORGET_HARD_RE.sub("", o).strip(" ,.")


@pytest.mark.parametrize("phrase, expected, label", [
    ("Olvida lo de las clases de cerámica de los jueves, al final no.",
     "clases de cerámica de los jueves", "al final no → coletilla podada"),
    ("Olvida lo del gimnasio, al final no voy.", "gimnasio", "al final no voy"),
    ("Olvida lo del regalo, mejor no.", "regalo", "mejor no"),
    ("Olvida mi contraseña vieja, que ya no la uso.", "contraseña vieja", "que ya no (ya funcionaba)"),
    # CONTROLS — the object must NOT lose legitimate content:
    ("Olvida lo del total de la factura.", "total de la factura", "control: 'total' es objeto, no coletilla"),
    ("Olvida la reunión del jueves.", "reunión del jueves", "control: sin coletilla"),
    ("Olvida lo de la cena, mejor dicho la comida.", "cena, mejor dicho la comida",
     "control: 'mejor dicho' ≠ 'mejor no' → no se poda"),
])
def test_forget_object_strips_decision_tail(phrase, expected, label):
    assert _forget_obj(phrase) == expected, f"{label}: {_forget_obj(phrase)!r}"


def test_forget_with_decision_tail_invalidates_target_e2e(fresh_db, monkeypatch):
    """bot v2 #65 end-to-end: the 'al final no' tail made the writer's AND match require 'final' →
    0 memories invalidated → the anchor remained in long-term memory. Verifies that forgetting DOES invalidate the
    target entry and that another entry with 'jueves' (rocódromo) SURVIVES (does not over-delete)."""
    async def scenario():
        await memapi.start()
        memapi.write_now("Quiere apuntarse a clases de cerámica los jueves.", level="long", kind="fact")
        memapi.write_now("Escala en el rocódromo los martes y jueves por la tarde.", level="long", kind="fact")
        res = await memory_agent.ingest_utterance(
            "Olvida lo de las clases de cerámica de los jueves, al final no.", role="operator")
        await memqueue.get_queue().join()
        await memapi.stop()
        return res
    res = asyncio.run(scenario())
    assert res.get("source") == "forget", f"no se detectó olvido: {res}"
    assert res.get("forgot", 0) >= 1, f"el olvido no invalidó la píldora objetivo (forgot={res.get('forgot')})"
    dur = " ".join(_durables()).lower()
    assert "cerámica" not in dur and "ceramica" not in dur, f"la píldora de cerámica sigue durable: {_durables()}"
    assert "rocódromo" in dur or "rocodromo" in dur, \
        f"CONTROL sobre-borrado: el rocódromo (otra píldora con 'jueves') no debe borrarse: {_durables()}"


def test_family_slot_projects_to_state_e2e(fresh_db, monkeypatch):
    """Finding 3 (live audit 2026-08-17): there was NO slot for family members — only loose
    `long/fact` entries (slot=None), reachable only through probabilistic semantic recall. Verifies that
    the new `operator.family` is reflected in the fixed STATE (state.familia), just like operator.car/hardware,
    through the SAME mechanical slot+value projection (memory_agent.py) — with no new projection code."""
    _run_with_atoms(monkeypatch, "Tengo dos hijos de 9 y 11 años.", [
        {"text": "Tiene dos hijos de 9 y 11 años.", "dest": "long", "slot": "operator.family",
         "kind": "fact", "value": "dos hijos de 9 y 11 años", "change": "none"},
    ])
    fam = (memapi.state().get("familia") or "").lower()
    assert "hijos" in fam and "9" in fam, f"el hecho de familia debe fijar el estado: {memapi.state()}"
