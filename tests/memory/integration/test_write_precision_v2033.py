"""V2-033 — CORE write precision: long-term memory does not get polluted.

Verifies the 3 measured failures (2026-07-12 report) through the REAL write path (`memory_agent.ingest_utterance`
→ the same path used by voice), with the LLM processor DISABLED (`MEM_PROCESSOR=0`) so the test is DETERMINISTIC
and GPU-free: this isolates the deterministic GATES (where the fix lives—the small model does not obey prompts).
The same gates also apply to LLM output in production.

Isolated DB (tmp_path)—NEVER touches the real profile.

  [P0a] requests/questions/ack → DISCARD (not durable), WITHOUT losing wrapped assertions ("remind me that…").
  [P0b] a proper name that CONTRADICTS the established identity does not overwrite `state` (STT garble).
  [P1]  an EPHEMERAL preference ("don't show me") does not become globally durable.
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from nucleo import memory_agent


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEM_PROCESSOR", "0")      # deterministic heuristic, no Ollama/GPU
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


def _run(*utterances) -> list[dict]:
    """Ingests each turn through the REAL path (start→ingest→join→stop, a single loop). Returns the result dicts."""
    async def scenario():
        await memapi.start()
        out = []
        for u in utterances:
            out.append(await memory_agent.ingest_utterance(u, role="operator"))
            await memqueue.get_queue().join()
        await memapi.stop()
        return out
    return asyncio.run(scenario())


def _durables() -> list[str]:
    # Excludes CONCEPT NODES (kind='concept', T126): they are graph infrastructure (categories such as "salud"),
    # not fact pills. Here we measure which FACTS entered long-term memory.
    rows = memdb.get_db().query(
        "SELECT text FROM memories WHERE valid=1 AND level IN ('mid','long') AND kind != 'concept'")
    return [r["text"] for r in rows]


def _contains(sub: str) -> bool:
    return any(sub.lower() in t.lower() for t in _durables())


def _state_blob() -> str:
    return " ".join(str(v) for v in memapi.state().values()).lower()


# ── [P0a] requests / questions / ack → NOT durable ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "¿puedes mirar eso por mí?",
    "sí, búscame algo con más detalle",
    "mira eso",
    "¿qué tiempo hace mañana?",
    "oye, ¿me recomiendas algo?",
    "vale, gracias",
    "ajá",
    "no me muestres nada ahora",
])
def test_noise_is_not_persisted(fresh_db, text):
    res = _run(text)[0]
    assert res["source"] in ("discard", "skip"), f"{text!r} debería descartarse, no {res}"
    assert _durables() == [], f"{text!r} dejó basura durable: {_durables()}"


# ── control: ASSERTIONS with data → durable (do not over-discard) ──────────────────────────────────────────
def test_assertion_with_data_is_kept(fresh_db):
    res = _run("soy alérgico al marisco")[0]
    assert res["source"] != "discard", f"una afirmación con dato no debe descartarse: {res}"
    assert _contains("marisco"), f"el alérgeno debe quedar durable: {_durables()}"


def test_concrete_task_is_kept(fresh_db):
    """A CONCRETE TASK with data is remembered ('what did I ask you to do?')—it is not confused with vague noise."""
    _run("búscame vuelos a Tokio para agosto")
    assert _contains("tokio"), f"la tarea concreta debe recordarse: {_durables()}"


def test_wrapped_assertion_survives(fresh_db):
    """The assertion WRAPPED in a request ('remind me that…') is NOT lost (brief warning)."""
    _run("recuérdame que soy alérgico a la penicilina")
    assert _contains("penicilina"), f"el hecho envuelto debe quedar: {_durables()}"


# ── [P1] EPHEMERAL preference does not become globally durable ──────────────────────────────────────────────
def test_ephemeral_pref_not_durable(fresh_db):
    res = _run("no me muestres nada ahora")[0]
    assert res.get("reason") == "ephemeral_directive", res
    assert "mostr" not in _state_blob() and "muestr" not in _state_blob(), f"state contaminado: {memapi.state()}"
    assert _durables() == []


def test_durable_pref_is_kept(fresh_db):
    """Control: a preference MARKED as durable ('I prefer…') IS saved."""
    res = _run("prefiero que me hables directo, sin rodeos")[0]
    assert res["source"] != "discard", f"una preferencia durable no debe descartarse: {res}"


# ── [P0b] established identity is NOT overwritten by a conflicting name (garble) ───────────────────────────
def test_established_identity_not_overwritten_by_conflict(fresh_db):
    _run("me llamo Ricard", "me llamo Alex Teigano")
    assert memapi.state().get("operator_name") == "Ricard", \
        f"identity was corrupted by the garble: {memapi.state().get('operator_name')!r}"
    # the garble remains in QUARANTINE (trust=untrusted): it does NOT surface in the brain's recall/prompt
    out = memapi.query("¿cómo me llamo?", reinforce_used=False)
    assert not any("teigano" in m["text"].lower() for m in out["memories"]), \
        f"el nombre garbleado NO debe aflorar en recall: {[m['text'] for m in out['memories']]}"


def test_first_name_on_empty_profile_is_set(fresh_db):
    """Control: in an EMPTY profile, the first name IS set (there is no conflict)."""
    _run("me llamo Ricard")
    assert memapi.state().get("operator_name") == "Ricard"


# ── integrated brief objective: the 3 turns, long-term = ONLY the allergen ──────────────────────────────────
def test_brief_three_turns_only_allergen(fresh_db):
    _run("¿puedes mirar eso por mí?",      # request → nothing
         "soy alérgico al marisco",         # assertion → durable
         "no me muestres nada ahora")       # ephemeral pref → nothing global
    dur = _durables()
    assert any("marisco" in t.lower() for t in dur), f"falta el alérgeno: {dur}"
    assert all("marisco" in t.lower() for t in dur), f"hay basura además del alérgeno: {dur}"
    assert "mostr" not in _state_blob() and "muestr" not in _state_blob(), f"state con pref 'sin mostrar': {memapi.state()}"


# ── [P0b·2026-08-21] a `change` SELF-SIGNED BY THE MODEL is not enough to overwrite an identity ─────────────
#
# The incident, on the operator's machine and not in a lab: Deepgram mangled «Calatayud» (`cal a`,
# `Kalatayut`, `valch`), zaelar did not understand and asked, and the operator clarified the name—«which is called
# Calatayut,, city of Calatayut», within a ROUTES request. The distiller wrote `operator.location` =
# «Lives in Calatayud.» with importance 0.95 and invalidated the previous value. `state.location` remained Calatayud.
#
# What makes this case deserving of its own guard is that the door EXISTED: P0b was literally built for the
# «typical STT garble». Reproduced with the real values, it ends with `is_correction=False` and lets it through
# with `True`—and no deterministic detector set `True` (all three return `False` for that phrase, correctly),
# but the distiller itself, declaring `change=update`. The anti-garble guard was disabled by a signal signed by
# the very party causing it.
def _atom_processor(monkeypatch, atom: dict):
    """Replaces the CORE to exercise the LLM ATOM path (the MEM_PROCESSOR=0 heuristic does not touch it)."""
    from nucleo import mem_processor as mp

    async def _process(_t, state=None):
        return [dict(atom)]

    monkeypatch.setattr(mp, "process", _process)
    monkeypatch.setattr(mp, "enabled", lambda: True)


_CALATAYUD_ATOM = {
    "text": "Vive en Calatayud.", "level": "long", "kind": "profile", "importance": 0.95, "pinned": True,
    "dest": "state", "slot": "operator.location", "state_patch": {"location": "Calatayud"},
    "value": "Calatayud", "change": "update",       # ← the self-declaration, as received
}


def test_a_self_declared_update_cannot_overwrite_identity_when_the_turn_is_not_about_the_operator(
        fresh_db, monkeypatch):
    """The REAL turn that corrupted the profile. The sentence names a place; it says nothing about the operator."""
    _run("me he mudado a Soria")
    assert memapi.state().get("location") == "Soria", "el montaje falla: la identidad de partida no quedó puesta"

    _atom_processor(monkeypatch, _CALATAYUD_ATOM)
    _run("que se llama Calatayut,, ciudad de Calatayut.")

    assert memapi.state().get("location") == "Soria", \
        f"un `change` autodeclarado pisó la identidad: {memapi.state().get('location')!r}"


def test_and_the_garbled_value_is_QUARANTINED_not_just_kept_out_of_state(fresh_db, monkeypatch):
    """Saving `state` is not enough: the pill remains in the DB and the brain would read it anyway. We verify what
    P0b promises—quarantine (`meta.trust='untrusted'`), NOT deletion: outside the passive block shown every turn,
    while still reachable through an explicit question.

    We assert this through SQL and `salient_long` (direct reading) deliberately, without going through the
    retriever: `_cfg()` in `memory/rerank.py` gives `config/v2.json` priority over `MEMORY_RERANK`, and that file
    is GITIGNORED—in the operator's machine, the local reranker starts DOWNLOADING from HuggingFace and this test
    would silently cease to be deterministic. Same family as the absolute floor against a live corpus."""
    _run("me he mudado a Soria")
    _atom_processor(monkeypatch, _CALATAYUD_ATOM)
    _run("que se llama Calatayut,, ciudad de Calatayut.")

    rows = memdb.get_db().query(
        "SELECT text, slot, json_extract(meta,'$.trust') AS trust FROM memories "
        "WHERE valid=1 AND lower(text) LIKE '%calatayud%'")
    assert rows, "la píldora desapareció: P0b degrada y aparta, no borra"
    assert all((r["trust"] or "") == "untrusted" for r in rows), \
        f"el valor garbleado quedó como hecho de confianza: {[dict(r) for r in rows]}"
    assert all(not (r["slot"] or "") for r in rows), \
        f"el garble conservó el slot de identidad: {[dict(r) for r in rows]}"

    pasivo = " ".join(m["text"].lower() for m in memapi.salient_long())
    assert "calatayud" not in pasivo, f"el garble se pinta en «lo que sabes del operador»: {pasivo!r}"


def test_a_REAL_move_still_goes_through_on_the_self_declared_signal(fresh_db, monkeypatch):
    """The control ensuring the fix is not a lock. A move stated in the first person STILL passes through
    `change`, exactly what the anti-injection guard protects for other languages: here the sentence is Catalan,
    so the deterministic (Spanish) expressions do NOT see it and the only support is the self-declaration. If
    this case turned red, the fix would have broken multilingual moves."""
    _run("me he mudado a Soria")
    _atom_processor(monkeypatch, dict(
        _CALATAYUD_ATOM, text="Viu a Girona.", state_patch={"location": "Girona"}, value="Girona"))
    _run("ara visc a Girona")

    assert memapi.state().get("location") == "Girona", \
        f"una mudanza legítima quedó bloqueada por el arreglo: {memapi.state().get('location')!r}"


@pytest.mark.parametrize("frase, habla_del_operador, por_que", [
    ("que se llama Calatayut,, ciudad de Calatayut.", False, "EL turno del incidente"),
    ("ciudad de Valls, la de Tarragona",              False, "aclarar un tercero"),
    ("es Valls, con uve",                             False, "deletrear un nombre"),
    ("me he mudado a Girona",                         True,  "es"),
    ("m'acabo de traslladar a València, saps?",       True,  "ca con clítico ELIDIDO"),
    ("m'he mudat a Girona",                           True,  "ca, la misma categoría"),
    ("acabo de mudarme a Girona",                     True,  "es con enclítico"),
    ("je viens de déménager à Lyon",                  True,  "fr"),
    ("mi sono trasferito a Roma",                     True,  "it"),
    ("I live in Berlin now",                          True,  "en"),
    ("a mi casa en Soria",                            True,  "el que SÍ era legítimo (id=95 del operador)"),
])
def test_the_discriminator_separates_talking_about_oneself_from_naming_a_place(frase, habla_del_operador, por_que):
    """The discriminator table, explicitly. It is an ENUMERATION and should be read as such: it is not intended
    to be a grammar, and its gap was found by an existing contract—`m'acabo de traslladar` (Catalan, a clitic
    elided with an apostrophe) fell outside because a `\\b` before `m'` does not match. That is why elided forms
    are searched separately: this is a Romance-language CATEGORY, not an isolated case. Anything not covered by
    the list leaves an observability trace (`_report_self_declared_change_ignored`) instead of being lost silently."""
    assert memory_agent._talks_about_the_operator(frase) is habla_del_operador, por_que
