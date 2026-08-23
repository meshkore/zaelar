"""V2-033 — PRECISIÓN de escritura del CORAZÓN: el largo plazo no se ensucia.

Verifica los 3 fallos medidos (informe 2026-07-12) por el CAMINO REAL de escritura (`memory_agent.ingest_utterance`
→ misma ruta que la voz), con el procesador LLM DESACTIVADO (`MEM_PROCESSOR=0`) para que la prueba sea DETERMINISTA
y sin GPU: así aísla los GATES deterministas (que es donde vive el arreglo — el modelo pequeño no obedece por prompt).
Los mismos gates se aplican también a la salida del LLM en producción.

BD aislada (tmp_path) — NUNCA toca el perfil real.

  [P0a] peticiones/preguntas/ack → DESCARTE (no durable), SIN perder afirmaciones envueltas ("recuérdame que…").
  [P0b] un nombre propio que CONTRADICE la identidad establecida no sobrescribe el `state` (garble del STT).
  [P1]  una preferencia EFÍMERA ("no me muestres") no se hace durable global.
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
    monkeypatch.setenv("MEM_PROCESSOR", "0")      # heurística determinista, sin Ollama/GPU
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
    """Ingesta cada turno por la ruta REAL (start→ingest→join→stop, un solo loop). Devuelve los res-dict."""
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
    # Excluye los NODOS-CONCEPTO (kind='concept', T126): son infraestructura del grafo (categorías como "salud"),
    # no píldoras de hechos. Aquí medimos qué HECHOS entraron al largo plazo.
    rows = memdb.get_db().query(
        "SELECT text FROM memories WHERE valid=1 AND level IN ('mid','long') AND kind != 'concept'")
    return [r["text"] for r in rows]


def _contains(sub: str) -> bool:
    return any(sub.lower() in t.lower() for t in _durables())


def _state_blob() -> str:
    return " ".join(str(v) for v in memapi.state().values()).lower()


# ── [P0a] peticiones / preguntas / ack → NO durable ──────────────────────────────────────────────────────────
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


# ── control: AFIRMACIONES con dato → SÍ durable (no sobre-descartar) ──────────────────────────────────────────
def test_assertion_with_data_is_kept(fresh_db):
    res = _run("soy alérgico al marisco")[0]
    assert res["source"] != "discard", f"una afirmación con dato no debe descartarse: {res}"
    assert _contains("marisco"), f"el alérgeno debe quedar durable: {_durables()}"


def test_concrete_task_is_kept(fresh_db):
    """Una TAREA CONCRETA con dato sí se recuerda ('¿qué te pedí?') — no se confunde con ruido vago."""
    _run("búscame vuelos a Tokio para agosto")
    assert _contains("tokio"), f"la tarea concreta debe recordarse: {_durables()}"


def test_wrapped_assertion_survives(fresh_db):
    """La afirmación ENVUELTA en petición ('recuérdame que…') NO se pierde (aviso del brief)."""
    _run("recuérdame que soy alérgico a la penicilina")
    assert _contains("penicilina"), f"el hecho envuelto debe quedar: {_durables()}"


# ── [P1] preferencia EFÍMERA no se hace durable global ───────────────────────────────────────────────────────
def test_ephemeral_pref_not_durable(fresh_db):
    res = _run("no me muestres nada ahora")[0]
    assert res.get("reason") == "ephemeral_directive", res
    assert "mostr" not in _state_blob() and "muestr" not in _state_blob(), f"state contaminado: {memapi.state()}"
    assert _durables() == []


def test_durable_pref_is_kept(fresh_db):
    """Control: una preferencia CON marca de durabilidad ('prefiero…') SÍ se guarda."""
    res = _run("prefiero que me hables directo, sin rodeos")[0]
    assert res["source"] != "discard", f"una preferencia durable no debe descartarse: {res}"


# ── [P0b] identidad establecida NO se sobrescribe por un nombre en conflicto (garble) ────────────────────────
def test_established_identity_not_overwritten_by_conflict(fresh_db):
    _run("me llamo Ricard", "me llamo Alex Teigano")
    assert memapi.state().get("operator_name") == "Ricard", \
        f"la identidad se corrompió con el garble: {memapi.state().get('operator_name')!r}"
    # el garble queda en CUARENTENA (trust=untrusted): NO aflora en el recall/prompt del cerebro
    out = memapi.query("¿cómo me llamo?", reinforce_used=False)
    assert not any("teigano" in m["text"].lower() for m in out["memories"]), \
        f"el nombre garbleado NO debe aflorar en recall: {[m['text'] for m in out['memories']]}"


def test_first_name_on_empty_profile_is_set(fresh_db):
    """Control: en un perfil VACÍO, el primer nombre SÍ se fija (no hay conflicto)."""
    _run("me llamo Ricard")
    assert memapi.state().get("operator_name") == "Ricard"


# ── objetivo integrado del brief: los 3 turnos, largo = SOLO el alérgeno ─────────────────────────────────────
def test_brief_three_turns_only_allergen(fresh_db):
    _run("¿puedes mirar eso por mí?",      # petición → nada
         "soy alérgico al marisco",         # afirmación → durable
         "no me muestres nada ahora")       # pref efímera → nada global
    dur = _durables()
    assert any("marisco" in t.lower() for t in dur), f"falta el alérgeno: {dur}"
    assert all("marisco" in t.lower() for t in dur), f"hay basura además del alérgeno: {dur}"
    assert "mostr" not in _state_blob() and "muestr" not in _state_blob(), f"state con pref 'sin mostrar': {memapi.state()}"


# ── [P0b·2026-08-21] el `change` que el MODELO SE FIRMA SOLO no basta para pisar una identidad ────────────────
#
# El incidente, en la máquina del operador y no en un laboratorio: Deepgram destrozó «Calatayud» (`cal a`,
# `Kalatayut`, `valch`), zaelar no entendía y preguntaba, y el operador aclaró el nombre — «que se llama
# Calatayut,, ciudad de Calatayut», dentro de un encargo de RUTAS. El destilador escribió `operator.location` =
# «Vive en Calatayud.» con importancia 0,95 e invalidó la anterior. `state.location` se quedó en Calatayud.
#
# Lo que hace este caso digno de un guarda propio es que la puerta EXISTÍA: P0b se construyó, literalmente, para
# el «típico garble del STT». Reproducida con los valores reales, cierra con `is_correction=False` y deja pasar
# con `True` — y a `True` no lo puso ninguno de los detectores deterministas (los tres dan `False` sobre esa
# frase, y aciertan), sino el propio destilador declarando `change=update`. La guarda anti-garble la apagaba una
# señal que firma quien la provoca.
def _atom_processor(monkeypatch, atom: dict):
    """Suplanta al CORAZÓN para ejercitar la ruta del ÁTOMO LLM (la heurística de MEM_PROCESSOR=0 no la toca)."""
    from nucleo import mem_processor as mp

    async def _process(_t, state=None):
        return [dict(atom)]

    monkeypatch.setattr(mp, "process", _process)
    monkeypatch.setattr(mp, "enabled", lambda: True)


_CALATAYUD_ATOM = {
    "text": "Vive en Calatayud.", "level": "long", "kind": "profile", "importance": 0.95, "pinned": True,
    "dest": "state", "slot": "operator.location", "state_patch": {"location": "Calatayud"},
    "value": "Calatayud", "change": "update",       # ← la autodeclaración, tal como vino
}


def test_a_self_declared_update_cannot_overwrite_identity_when_the_turn_is_not_about_the_operator(
        fresh_db, monkeypatch):
    """El turno REAL que corrompió el perfil. La frase nombra un sitio, no dice nada del operador."""
    _run("me he mudado a Soria")
    assert memapi.state().get("location") == "Soria", "el montaje falla: la identidad de partida no quedó puesta"

    _atom_processor(monkeypatch, _CALATAYUD_ATOM)
    _run("que se llama Calatayut,, ciudad de Calatayut.")

    assert memapi.state().get("location") == "Soria", \
        f"un `change` autodeclarado pisó la identidad: {memapi.state().get('location')!r}"


def test_and_the_garbled_value_is_QUARANTINED_not_just_kept_out_of_state(fresh_db, monkeypatch):
    """No basta con salvar el `state`: la píldora sigue en la BD y el cerebro la leería igual. Se comprueba lo
    que P0b promete — cuarentena (`meta.trust='untrusted'`), NO borrado: fuera del bloque pasivo que se pinta
    cada turno, y todavía alcanzable por una pregunta explícita.

    Se afirma por SQL y por `salient_long` (lectura directa) a propósito, sin pasar por el retriever: `_cfg()` de
    `memory/rerank.py` da prioridad a `config/v2.json` sobre `MEMORY_RERANK`, y ese fichero está GITIGNOREADO —
    en la máquina del operador el reranker local se pone a DESCARGAR de HuggingFace y este test dejaría de ser
    determinista sin decirlo. Misma familia que el suelo absoluto contra un corpus vivo."""
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
    """El control que impide que el arreglo sea un candado. Una mudanza dicha en primera persona SIGUE pasando
    por `change`, que es exactamente lo que el comentario anti-inyección protege para los demás idiomas: aquí la
    frase es catalana, así que las expresiones deterministas (castellanas) NO la ven y el único apoyo es la
    autodeclaración. Si este caso se pusiera rojo, el arreglo habría roto las mudanzas multilingües."""
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
    """La tabla del discriminador, explícita. Es una ENUMERACIÓN y conviene que se lea como tal: no pretende ser
    una gramática, y su hueco lo encontró un contrato que ya existía — `m'acabo de traslladar` (catalán, clítico
    elidido con apóstrofo) caía fuera porque un `\\b` delante de `m'` no casa. Por eso los elididos se buscan
    aparte: es una CATEGORÍA románica, no un caso suelto. Lo que la lista no cubra deja rastro en observabilidad
    (`_report_self_declared_change_ignored`) en vez de perderse en silencio."""
    assert memory_agent._talks_about_the_operator(frase) is habla_del_operador, por_que
