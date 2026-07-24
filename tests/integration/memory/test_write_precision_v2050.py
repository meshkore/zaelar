"""V2-050 — PRECISIÓN de escritura (continuación de V2-033): la identidad/largo plazo no se ensucia con garble.

Reproduce los fallos encontrados tras la reserva de la ITV (2026-07-17), donde la memoria se construía MAL:
  [P0c·A] slot TIPADO con VALOR malformado ('mi email es rjj.com' → 'rjj.com' sin @) → NO durable (ensuciaba y
          competía con el email bueno rjj@proars.com).
  [P0c·B] petición reificada mis-asignada a un slot de IDENTIDAD ('quiere que entre en la web y reserve' →
          operator.treatment) → NO es ese atributo → rechazo. Un atributo estable jamás es "quiere que…".
  [P0c·C] petición VAGA reificada ('quiere que repitan algo', objeto indefinido) → NO durable; una tarea CONCRETA
          ('quiere que le reserve la cita') SÍ se conserva.

Dos niveles: (1) el GATE determinista `_precision_reject_atom` directo (sin LLM ni BD, precisión exacta);
(2) la RUTA REAL de escritura con `mem_processor.process` mockeado para inyectar el átomo exacto que el LLM produjo
en producción → verifica que un átomo rechazado NO llega al largo plazo y uno válido SÍ. BD aislada (tmp_path).
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from nucleo import memory_agent
from nucleo import mem_processor


# ── (1) GATE determinista directo — la precisión exacta de cada regla ────────────────────────────────────────
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
    """El CORAZÓN doble-namespacea ('operator.goal.current','operator.objetivo') → deben colapsar a goal.current
    (state_field objetivo). Los slots REALES no se tocan; un 'operator.<desconocido>' no se inventa. bot v1 #20/#28."""
    from memory import slots
    assert slots.canonical("operator.goal.current") == "goal.current"
    assert slots.state_field("operator.goal.current") == "objetivo"
    assert slots.canonical("operator.project.current") == "project.current"
    assert slots.canonical("operator.name") == "operator.name"          # slot real: intacto
    assert slots.canonical("operator.car") == "operator.car"
    assert slots.canonical("operator.foo") == "operator.foo"            # desconocido: no se inventa


def test_incoming_msg_regex_excludes_identity():
    """El backstop de mensaje entrante NO debe confundir 'me llamo X' (IDENTIDAD) con 'me llamó X' (me llamó)."""
    fires = lambda t: bool(memory_agent._INCOMING_MSG_RE.search(t) and not memory_agent._EMPTY_MSG_RE.search(t))
    assert fires("Me escribió Carlos: la reunión se mueve.") is True
    assert fires("Me llamó Carlos ayer por teléfono.") is True
    assert fires("Me llamo Ramón y juego a pádel.") is False       # IDENTIDAD, sin acento
    assert fires("No me dijo nada.") is False


# ── (2) RUTA REAL de escritura con el átomo del LLM mockeado ─────────────────────────────────────────────────
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
    """Ingesta un turno por la ruta REAL, con el procesador LLM devolviendo `atoms` (átomos exactos de producción)."""
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
    """El átomo que el LLM produjo en producción para 'mi email es rjj.com' NO debe llegar al largo plazo."""
    _run_with_atoms(monkeypatch, "Y mi email es rjj.com.", [
        {"text": "Su correo electrónico es rjj.com.", "dest": "long", "slot": "operator.email",
         "kind": "fact", "value": "rjj.com", "change": "none"},
    ])
    assert not any("rjj.com" in t.lower() for t in _durables()), f"email garble quedó durable: {_durables()}"


def test_valid_email_is_durable_e2e(fresh_db, monkeypatch):
    """Control: un email BIEN formado SÍ se guarda (no sobre-rechazar)."""
    _run_with_atoms(monkeypatch, "Mi correo es rjj@proars.com.", [
        {"text": "Su correo electrónico es rjj@proars.com.", "dest": "long", "slot": "operator.email",
         "kind": "fact", "value": "rjj@proars.com", "change": "none"},
    ])
    assert any("proars.com" in t.lower() for t in _durables()), f"el email bueno debe quedar: {_durables()}"


def test_namespaced_goal_slot_canonicalizes_e2e(fresh_db, monkeypatch):
    """El CORAZÓN a veces namespacea 'operator.goal' (por analogía con operator.name). Debe COLAPSAR a goal.current
    → fija el estado 'objetivo' Y no crea un linaje paralelo (bot v2 #25/#26). Alias en memory/slots.py."""
    _run_with_atoms(monkeypatch, "Mi gran meta es terminar una maratón.", [
        {"text": "Su objetivo vital actual es terminar una maratón.", "dest": "state", "slot": "operator.goal",
         "kind": "profile", "value": "terminar una maratón", "change": "none"},
    ])
    obj = (memapi.state().get("objetivo") or "").lower()
    assert "marat" in obj, f"el objetivo namespaced debe fijar el estado: {memapi.state()}"
    # una sola vigente bajo el slot canónico goal.current (no linaje paralelo operator.goal)
    from memory import slots as _sl
    rows = memdb.get_db().query("SELECT slot FROM memories WHERE valid=1 AND slot IS NOT NULL AND slot != ''")
    goal_slots = [r["slot"] for r in rows if _sl.canonical(r["slot"]) == "goal.current"]
    assert all(s == "goal.current" for s in goal_slots), f"linaje paralelo sin canonizar: {goal_slots}"


def test_same_entity_refinement_collapses_e2e(fresh_db, monkeypatch):
    """El mismo coche en 3 fraseos ('Dacia Duster'/'Duster gris'/'Duster de Dacia') comparte «duster» → refinamiento,
    no garble → el slot superseda a ≤2 (no 3 cuarentenados sin slot). bot v2 #21."""
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
    """CONTROL de que el refinamiento NO afloja el anti-garble de identidad: 'Ana García' → 'Ana Pérez' comparte
    solo 'Ana' (<4) y el apellido difiere → sigue siendo garble → NO sobrescribe el nombre establecido."""
    _run_with_atoms(monkeypatch, "Me llamo Ana García.", [
        {"text": "El operador se llama Ana García.", "dest": "state", "slot": "operator.name",
         "kind": "profile", "value": "Ana García", "change": "none"}])
    _run_with_atoms(monkeypatch, "Soy Ana Pérez.", [
        {"text": "El operador se llama Ana Pérez.", "dest": "state", "slot": "operator.name",
         "kind": "profile", "value": "Ana Pérez", "change": "none"}])
    assert memapi.state().get("operator_name") == "Ana García", \
        f"un garble de apellido NO debe sobrescribir el nombre: {memapi.state().get('operator_name')!r}"


def test_incoming_message_preserved_when_llm_hallucinates_e2e(fresh_db, monkeypatch):
    """Un mensaje entrante ('Me escribió Carlos... la reunión se mueve al viernes') debe quedar durable AUNQUE el
    CORAZÓN alucine un placeholder de fewshot → el backstop guarda el TEXTO CRUDO (con carlos+viernes). bot v1 #24/#29."""
    _run_with_atoms(monkeypatch, "Me escribió Carlos por WhatsApp: la reunión del jueves se mueve al viernes.", [
        {"text": "X me pidió Y para el día Z.", "dest": "long", "slot": None, "kind": "event",
         "value": "Carlos", "change": "none"},   # átomo BASURA que produce el LLM (placeholder)
    ])
    dur = " ".join(_durables()).lower()
    assert "carlos" in dur and "viernes" in dur, f"el mensaje entrante crudo debe quedar durable: {_durables()}"


def test_own_task_not_treated_as_incoming_e2e(fresh_db, monkeypatch):
    """CONTROL: una negación vacía ('no me dijo nada') NO dispara el backstop de mensaje entrante."""
    res = _run_with_atoms(monkeypatch, "No me dijo nada.", [])
    assert not any("no me dijo nada" in t.lower() for t in _durables()), f"negación vacía no debe persistir: {_durables()}"


def test_state_patch_slotname_key_renamed_and_superseded_e2e(fresh_db, monkeypatch):
    """El CORAZÓN mete 'goal.current' como CLAVE del estado (nombre del slot, no el campo 'objetivo') → debe
    renombrarse a 'objetivo' y un objetivo NUEVO debe superseder al viejo, sin clave stray (bot v1 #20/#28)."""
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
    """Una orden reificada a operator.treatment NO ensucia la identidad ni el estado."""
    _run_with_atoms(monkeypatch, "Entra en la web y resérvame la cita directamente.", [
        {"text": "El operador quiere que entre en la web y reserve cita directamente.", "dest": "state",
         "slot": "operator.treatment", "kind": "pref", "value": "entrar en la web, reservar cita", "change": "none"},
    ])
    st = " ".join(str(v) for v in memapi.state().values()).lower()
    assert "reserve cita" not in st and "reservar cita" not in st, f"treatment contaminado: {memapi.state()}"
    assert not any("quiere que entre" in t.lower() for t in _durables()), f"petición quedó durable: {_durables()}"


# ── Olvido: la coletilla de DECISIÓN no es parte del objeto (bot v2 #65, 2026-07-17) ──────────────────────────
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
    # CONTROLES — el objeto NO debe perder contenido legítimo:
    ("Olvida lo del total de la factura.", "total de la factura", "control: 'total' es objeto, no coletilla"),
    ("Olvida la reunión del jueves.", "reunión del jueves", "control: sin coletilla"),
    ("Olvida lo de la cena, mejor dicho la comida.", "cena, mejor dicho la comida",
     "control: 'mejor dicho' ≠ 'mejor no' → no se poda"),
])
def test_forget_object_strips_decision_tail(phrase, expected, label):
    assert _forget_obj(phrase) == expected, f"{label}: {_forget_obj(phrase)!r}"


def test_forget_with_decision_tail_invalidates_target_e2e(fresh_db, monkeypatch):
    """bot v2 #65 end-to-end: la coletilla 'al final no' hacía que el AND-match del writer exigiera 'final' →
    0 recuerdos invalidados → el ancla seguía en el largo plazo. Verifica que el olvido SÍ invalida la píldora
    objetivo y que otra píldora con 'jueves' (rocódromo) SOBREVIVE (no sobre-borra)."""
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
