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
