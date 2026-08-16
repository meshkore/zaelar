#
# test_memory_agent.py — el agente de MEMORIA ★ del SlowBrain (V2-006, T81). Verifica: compose_context da
# SOLO lo relevante (estado + recall, no todo el store), remember() escribe a memoria por la cola (único
# escritor) y aplica un state_patch, y que el router LLM se salta sin credencial (heurística pura).
# Ejecutar: .venv/bin/pytest tests/memory/integration/test_memory_agent.py
#
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import memory_agent


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    # sin credencial de modelo rápido → el router LLM NO se dispara (heurística pura, sin red)
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    # procesador LLM de memoria OFF por defecto en tests → ingest_utterance usa la heurística DETERMINISTA
    # (sin depender de Ollama). Los tests que quieren ejercitar el LLM lo activan y mockean `process`.
    monkeypatch.setenv("MEM_PROCESSOR", "0")
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_compose_context_includes_state_and_recall(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "location": "Barcelona"})
    memapi.write_now("el operador quiere comprar una moto de segunda mano en Wallapop", kind="fact", level="long")
    ctx = asyncio.run(memory_agent.compose_context("¿qué quería comprar el operador?", budget=1000))
    assert "Ricart" in ctx                          # estado siempre
    assert "moto" in ctx.lower()                     # recall relevante
    assert "LO QUE SABES DEL OPERADOR" in ctx        # dossier v2 (V2-056): cabecera del bloque de recuerdos


def test_compose_context_empty_db_is_safe(fresh_db):
    ctx = asyncio.run(memory_agent.compose_context("cualquier cosa", budget=500))
    assert isinstance(ctx, str)                      # nunca lanza; string (posiblemente vacío o solo estado)


def test_remember_writes_to_memory(fresh_db):
    async def run():
        await memapi.start()
        try:
            await memory_agent.remember({"text": "conclusión: el mejor modelo es el X", "kind": "result"})
            # da tiempo a que el consumidor único drene la cola
            for _ in range(50):
                out = memapi.query("mejor modelo", reinforce_used=False)
                if any("mejor modelo" in m["text"] for m in out["memories"]):
                    return True
                await asyncio.sleep(0.02)
            return False
        finally:
            await memapi.stop()
    assert asyncio.run(run()) is True


def test_remember_applies_state_patch(fresh_db):
    asyncio.run(memory_agent.remember({"state_patch": {"treatment": "tutéame"}}))
    assert memapi.state().get("treatment") == "tutéame"


def test_reversal_backstop_regex():
    """Dim M — una REVERSIÓN/cese ('ya no bebo café', 'ya no trabajo allí') es un cambio de estado memorable que el
    LLM tiende a descartar; el backstop lo rescata. No dispara con 'ya no' a secas ni con charla."""
    R = memory_agent._REVERSAL_RE
    assert R.search("ya no bebo café, lo he dejado")
    assert R.search("ya no me gusta madrugar")
    assert not R.search("ya no")                                # sin contenido → no dispara
    assert not R.search("hoy hace sol")


def test_forget_regex_accepts_enclitic_pronouns():
    """Dim N — el hook de OLVIDO debe disparar con el fraseo NATURAL de enclíticos ('bórrame X', 'bórralo',
    'olvídame lo de Y', 'bórramelo'), no solo con 'olvida/bórrate' (bug cazado por el bot BATCH_159)."""
    R = memory_agent._FORGET_RE
    assert R.search("bórrame el número de la seguridad social")
    assert R.search("olvídame lo de la reunión")
    assert R.search("bórramelo del todo el número")
    assert R.search("olvida lo del regalo")                      # el clásico sigue disparando
    assert R.search("bórrate mi contraseña vieja")
    assert not R.search("hoy hace un día estupendo")            # charla → no dispara
    # 'bórralo' a secas (anafórico, sin objeto explícito) NO dispara el olvido-por-nombre: no hay QUÉ olvidar
    assert not R.search("bórralo")


def test_observation_backstop_regex():
    """Dim I — un AUTOCONOCIMIENTO explícito ('he notado que…', 'me he dado cuenta de que…') debe rescatarse aunque
    el LLM lo descarte por 'charla'. El backstop dispara con la marca de observación; no con charla normal."""
    R = memory_agent._OBSERVATION_RE
    assert R.search("me he dado cuenta de que cuando ceno tarde duermo mal")
    assert R.search("he notado que rindo más por las mañanas")
    assert R.search("he observado que el café me pone nervioso")
    assert not R.search("hoy hace un día estupendo")            # charla → no dispara


def test_concept_vocab_covers_dietary_restrictions():
    """T183/T178 (prerequisito) — las RESTRICCIONES alimentarias deben etiquetarse con el concepto 'comida' para
    organizarse y (a futuro) aplicarse cross-topic. Antes 'celíaco/gluten' daba [] (sin concepto)."""
    from memory.concepts import derive_concepts as d
    assert "comida" in d("soy celíaco no puedo tomar gluten")
    assert "comida" in d("soy intolerante a la lactosa")
    assert "comida" in d("me recomiendas un restaurante para cenar")   # el MISMO concepto que la restricción
    assert d("tengo una hipoteca") == ["finanzas"]                     # sin regresión


def test_assistant_query_discard_regex():
    """Dim E — una PREGUNTA inequívoca al asistente (el tiempo de X, una recomendación) NO es un hecho → se ataja
    y descarta; pero una pregunta que TRAE un dato ('¿sabes que me mudé?') NO se ataja (la procesa el CORAZÓN)."""
    R = memory_agent._ASSISTANT_QUERY_RE
    assert R.search("¿qué tiempo va a hacer mañana en Cuenca?")
    assert R.search("¿me recomiendas algún restaurante japonés?")
    assert not R.search("¿sabes que me mudé a Madrid?")          # trae un hecho → no se ataja
    assert not R.search("¿tú crees que debería comprarme un coche eléctrico?")  # deliberación (borde) → no se ataja


def test_is_ambiguous_heuristic():
    assert memory_agent._is_ambiguous("hola", {"memories": []}) is True        # sin resultados
    assert memory_agent._is_ambiguous("a b", {"memories": [{"score": 0.9}]}) is True   # query cortísima
    assert memory_agent._is_ambiguous(
        "una pregunta bien formada y larga", {"memories": [{"score": 0.9}]}) is False


# ── V2-013: el corazón clasifica y no pierde el perfil ──────────────────────────────────────────────────

def test_classify_extracts_profile_name_and_location():
    plan = memory_agent.classify("Me llamo Ramón y vivo en Barcelona.")
    assert plan["state_patch"].get("operator_name") == "Ramón"
    assert "Barcelona" in plan["state_patch"].get("location", "")
    assert plan["level"] == "long"
    assert plan["pinned"] is True
    assert plan["kind"] == "profile"


def test_classify_extracts_hardware_and_car():
    plan = memory_agent.classify("Tengo un MacBook Pro y conduzco un Tesla Model 3.")
    # una regla gana por turno; comprobamos que al menos una parte del perfil se pilla.
    p = plan["state_patch"]
    assert "hardware" in p or "car" in p
    assert plan["level"] == "long"


def test_classify_treatment_preference():
    plan = memory_agent.classify("Tutéame, por favor.")
    assert "tut" in (plan["state_patch"].get("treatment") or "").lower()
    assert plan["kind"] == "profile"


def test_classify_desire_goes_long_not_pinned():
    plan = memory_agent.classify("Quiero comprarme una moto de segunda mano.")
    assert plan["state_patch"] == {}
    assert plan["level"] == "long"
    assert plan["pinned"] is False
    assert plan["kind"] == "pref"


def test_classify_trivia_and_commands_are_skipped():
    for t in ("hola", "gracias", "vale", "cierra el widget"):
        plan = memory_agent.classify(t)
        assert plan["level"] is None, f"debería saltarse: {t!r}"
        assert plan["state_patch"] == {}


def test_classify_default_is_short_ttl():
    # Contrato 2026-07-20 (auditoría H2): el crudo SIN señal fuerte ya no es durable — short + TTL (visible unos
    # días por recencia; lo durable inequívoco lo rescatan las redes o el LLM al volver).
    plan = memory_agent.classify("La reunión con el equipo terminó a las cinco.")
    assert plan["level"] == "short"
    assert plan["kind"] == "fact"
    assert plan.get("ttl_days") == 3.0
    assert plan["state_patch"] == {}


def test_ingest_utterance_populates_state(fresh_db):
    # MEM_PROCESSOR=0 (fixture) → ruta heurística DETERMINISTA (fail-open), sin Ollama.
    async def run():
        await memapi.start()
        try:
            res = await memory_agent.ingest_utterance("Me llamo Ramón y vivo en Barcelona.")
            # da tiempo al consumidor único (write async).
            for _ in range(50):
                st = memapi.state()
                if st.get("operator_name") == "Ramón":
                    return res, st
                await asyncio.sleep(0.02)
            return res, memapi.state()
        finally:
            await memapi.stop()
    res, st = asyncio.run(run())
    assert res["source"] == "heuristic"
    assert res["plan"]["state_patch"].get("operator_name") == "Ramón"
    assert st.get("operator_name") == "Ramón"
    assert "Barcelona" in (st.get("location") or "")


def test_ingest_utterance_discards_trivia(fresh_db):
    # trivia/comando obvio → descarte barato, sin LLM (MEM_PROCESSOR=0 en el fixture igualmente).
    for t in ("gracias", "hola", "cierra el widget"):
        res = asyncio.run(memory_agent.ingest_utterance(t))
        assert res["source"] == "discard", t
        assert res["atoms"] == 0


def test_ingest_utterance_respects_llm_discard(fresh_db, monkeypatch):
    """Si el LLM CORRE y devuelve [] (nada memorable), se DESCARTA — no se re-infla con la heurística."""
    monkeypatch.setenv("MEM_PROCESSOR", "1")

    async def fake_process(text, *, state=None):
        return []                                   # corrió y no hay nada que guardar

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", fake_process)
    # frase que la heurística SÍ guardaría (mid/fact) — el veredicto del LLM manda.
    res = asyncio.run(memory_agent.ingest_utterance("La reunión con el equipo terminó a las cinco."))
    assert res["source"] == "discard-llm"
    assert res["atoms"] == 0


def test_ingest_utterance_retries_once_before_heuristic(fresh_db, monkeypatch):
    """V2-103 (2026-08-16): un hipo transitorio del CORAZÓN no debe degradar directo a la heurística — un solo
    reintento (off-hot-path) protege contra el blip que produjo fragmentos crudos en una sesión real. Si el
    reintento SÍ responde, se usan sus píldoras, no la heurística."""
    monkeypatch.setenv("MEM_PROCESSOR", "1")
    calls = {"n": 0}

    async def flaky_process(text, *, state=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("blip transitorio de red")
        return [{"text": "El operador se llama Ramón.", "dest": "state", "kind": "profile",
                 "importance": 0.95, "ttl_days": None, "slot": "operator.name",
                 "state_patch": {"operator_name": "Ramón"}}]

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", flaky_process)
    res = asyncio.run(memory_agent.ingest_utterance("me llamo Ramón"))
    assert calls["n"] == 2
    assert res["source"] == "llm"                    # el reintento ganó, NO cayó a la heurística


def test_ingest_utterance_falls_back_after_retry_also_fails(fresh_db, monkeypatch):
    monkeypatch.setenv("MEM_PROCESSOR", "1")
    calls = {"n": 0}

    async def always_fails(text, *, state=None):
        calls["n"] += 1
        raise RuntimeError("caído de verdad")

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", always_fails)
    res = asyncio.run(memory_agent.ingest_utterance("Vamos a ver, aquí hay un problema grave."))
    assert calls["n"] == 2                            # intentó + reintentó, los dos fallaron
    assert res["source"] in ("heuristic", "heuristic-demoted", "discard")   # cae a la heurística, como antes


def test_ingest_utterance_no_retry_when_processor_disabled(fresh_db, monkeypatch):
    # MEM_PROCESSOR=0 (el default del fixture): se llama UNA vez (process() decide internamente que está
    # apagado) pero `enabled()` en False descarta el reintento — no tiene sentido reintentar algo apagado.
    calls = {"n": 0}

    async def counting_process(text, *, state=None):
        calls["n"] += 1
        return None

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", counting_process)
    asyncio.run(memory_agent.ingest_utterance("cualquier frase"))
    assert calls["n"] == 1    # UNA llamada, sin reintento (`enabled()` es False)


def test_ingest_utterance_uses_llm_atoms_when_processor_on(fresh_db, monkeypatch):
    """Con el procesador LLM ON (mockeado), ingest_utterance escribe las PÍLDORAS que devuelve, no la heurística."""
    monkeypatch.setenv("MEM_PROCESSOR", "1")

    async def fake_process(text, *, state=None):
        return [
            {"text": "El operador se llama Ramón.", "dest": "state", "kind": "profile",
             "importance": 0.95, "ttl_days": None, "slot": "operator.name",
             "state_patch": {"operator_name": "Ramón"}},
            {"text": "Le gusta el pádel los martes.", "dest": "long", "kind": "pref",
             "importance": 0.7, "ttl_days": None, "slot": None, "state_patch": {}},
        ]

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", fake_process)

    async def run():
        await memapi.start()
        try:
            res = await memory_agent.ingest_utterance("bla bla me llamo Ramón y juego a pádel los martes")
            for _ in range(50):
                st = memapi.state()
                if st.get("operator_name") == "Ramón":
                    return res, st
                await asyncio.sleep(0.02)
            return res, memapi.state()
        finally:
            await memapi.stop()

    res, st = asyncio.run(run())
    assert res["source"] == "llm"
    assert res["atoms"] == 2
    assert st.get("operator_name") == "Ramón"                 # átomo dest=state fijó el estado
    out = memapi.query("pádel", reinforce_used=False)
    assert any("pádel" in m["text"].lower() for m in out["memories"])   # átomo dest=long quedó buscable


def test_state_lines_includes_custom_fields():
    lines = memory_agent._state_lines({
        "operator_name": "Ramón",
        "location": "Barcelona",
        "hardware": "MacBook Pro M4",
        "car": "Tesla Model 3",
    })
    joined = "\n".join(lines)
    assert "Ramón" in joined
    assert "Barcelona" in joined
    assert "MacBook Pro M4" in joined            # campo custom ahora es visible en el prompt
    assert "Tesla Model 3" in joined


def test_remember_auto_classifies_when_caller_gives_only_text(fresh_db):
    async def run():
        await memapi.start()
        try:
            await memory_agent.remember({"text": "Me llamo Ramón."})
            for _ in range(50):
                st = memapi.state()
                if st.get("operator_name") == "Ramón":
                    return st
                await asyncio.sleep(0.02)
            return memapi.state()
        finally:
            await memapi.stop()
    st = asyncio.run(run())
    assert st.get("operator_name") == "Ramón"
