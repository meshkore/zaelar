#
# test_memory_agent.py — the MEMORIA ★ agent of SlowBrain (V2-006, T81). Verifies that compose_context returns
# ONLY what is relevant (state + recall, not the entire store), remember() writes to memory through the queue (the sole
# writer) and applies a state_patch, and that the LLM router is skipped without credentials (pure heuristic).
# Run: .venv/bin/pytest tests/memory/integration/test_memory_agent.py
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
    # without a fast-model credential → the LLM router is NOT triggered (pure heuristic, no network)
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    # memory LLM processor OFF by default in tests → ingest_utterance uses the DETERMINISTIC heuristic
    # (without depending on Ollama). Tests that want to exercise the LLM enable it and mock `process`.
    monkeypatch.setenv("MEM_PROCESSOR", "0")
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_compose_context_includes_state_and_recall(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "location": "Barcelona"})
    memapi.write_now("el operador quiere comprar una moto de segunda mano en Wallapop", kind="fact", level="long")
    ctx = asyncio.run(memory_agent.compose_context("¿qué quería comprar el operador?", budget=1000))
    assert "Ricart" in ctx                          # state always
    assert "moto" in ctx.lower()                     # relevant recall
    assert "LO QUE SABES DEL OPERADOR" in ctx        # v2 dossier (V2-056): header of the memories block


def test_the_agenda_follows_the_memorys_clock_not_the_wall(tmp_path, monkeypatch, fresh_db):
    """A timeline replay thinks it is March; `date.today()` answers with the REAL current day.

    Measured on 2026-08-21: with the clock at 2026-03-10 and an appointment six simulated days ahead,
    `_agenda_lines()` returned NOTHING — every future date was read as past. The worker dossier plans
    blindly, which is precisely the failure this function exists for (2026-07-19 P1-2 audit), and fails EMPTY: a
    replay looks like an operator with no agenda, not a broken filter. Same rule as the distiller's anchor.
    """
    import datetime

    from memory import clock
    from widgets import store as wstore

    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))       # never the operator's real widgets
    wstore.save("agenda", {"events": [{"date": "2026-03-16", "time": "09:00", "title": "Revisión"}]})
    with clock.travel(int(datetime.datetime(2026, 3, 10, 9, 0).timestamp())):
        lineas = memory_agent._agenda_lines()
    assert lineas and "2026-03-16" in lineas[0]


def test_the_agenda_still_drops_what_is_already_past(tmp_path, monkeypatch, fresh_db):
    """The other direction: continue dropping what is past. A filter that lets everything through is not a fix."""
    import datetime

    from memory import clock
    from widgets import store as wstore

    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    wstore.save("agenda", {"events": [{"date": "2026-03-01", "title": "Ya pasó"},
                                      {"date": "2026-03-16", "title": "Aún no"}]})
    with clock.travel(int(datetime.datetime(2026, 3, 10, 9, 0).timestamp())):
        lineas = memory_agent._agenda_lines()
    texto = " ".join(lineas)
    assert "Aún no" in texto and "Ya pasó" not in texto


def test_every_surface_inherits_the_rule_because_it_lives_at_the_source(fresh_db):
    """The bottleneck: `memory.query()` applies the rule, so a NEW surface inherits it.

    The list of surfaces was shown to be incomplete THREE times in one day (passive block 2026-07-14, worker
    dossier, and active recall 2026-08-21), and a FOURTH —`/api/memory/recall`, the `mem_cli` bridge— appeared
    precisely while looking for a way to stop needing the list. `query()` already receives the request the rule needs.
    """
    memapi.write_now("Vive en el centro de Madrid.", level="long", kind="profile",
                     importance=0.95, weight=1.0, pinned=True, slot="operator.location")
    memapi.write_now("Weather in Soria now: 14.5C.", level="mid", kind="note",
                     importance=0.3, weight=0.5, slot="meteo-soria:weather:soria")
    textos = " ".join(m["text"] for m in memapi.query("necesito un fontanero urgente")["memories"])
    assert "Soria" not in textos and "Madrid" in textos
    # and it remains CONDITIONAL: naming the city brings it back
    assert "Soria" in " ".join(m["text"] for m in memapi.query("qué tiempo hace en Soria")["memories"])


def test_memorys_own_synthesis_is_not_a_background_dump(fresh_db):
    """`insight:<concept>` contains a colon and is NOT a background dump: REM writes it by summarizing the operator's
    own pills. Excluding it would break the entire REM cycle — that is what made the first attempt fail."""
    memapi.write_now("Le gusta la música española clásica.", level="long", kind="fact",
                     importance=0.8, weight=0.9, slot="insight:musica")
    textos = " ".join(m["text"] for m in memapi.query("qué música le gusta")["memories"])
    assert "música española" in textos
    assert memapi.background_slot_off_topic("insight:musica", "cualquier otra cosa") is False
    assert memapi.background_slot_off_topic("secret:wallet:seed", "cualquier otra cosa") is True  # NOT the vault


def test_background_widget_pill_does_not_decide_an_unrelated_errand(fresh_db):
    """A background widget dump must NOT be presented to the worker as “what you know about the operator”.

    Case measured on 2026-08-21 in `best-plumber-same-day`: `widgets/meteo-soria` (which SHIPS in the repo) writes
    a `weather:soria` pill every hour; in the worker dossier it appeared ABOVE `operator.location` =
    "Vive en el centro de Madrid", and the worker made three searches for "fontanero Soria". The passive block had
    already excluded namespaced slots since the 2026-07-14 audit; the dossier had not.
    """
    memapi.set_state({"operator_name": "Ricart", "location": "el centro de Madrid"})
    memapi.write_now("Vive en el centro de Madrid.", level="long", kind="profile",
                     importance=0.95, weight=1.0, pinned=True, slot="operator.location")
    memapi.write_now("Weather in Soria now: 14.5C, parcialmente nublado.",
                     level="mid", kind="note", importance=0.6, weight=0.8, slot="weather:soria")
    ctx = asyncio.run(memory_agent.compose_context(
        "Encuentra un fontanero que pueda venir hoy mismo, urgente", budget=2000))
    assert "Soria" not in ctx                        # the task does not mention Soria → the background note does NOT enter
    assert "Madrid" in ctx                           # and the operator's fact is STILL there


def test_background_pill_still_reachable_when_the_task_names_it(fresh_db):
    """The exclusion is CONDITIONAL: the 2026-07-14 promise is that they remain retrievable for an EXPLICIT
    question. A `weather:soria` must enter when the worker's task mentions Soria."""
    memapi.write_now("Weather in Soria now: 14.5C, parcialmente nublado.",
                     level="mid", kind="note", importance=0.6, weight=0.8, slot="weather:soria")
    ctx = asyncio.run(memory_agent.compose_context("Dime qué tiempo hace en Soria ahora", budget=2000))
    assert "Soria" in ctx


def test_operator_dot_slots_are_never_treated_as_background(fresh_db):
    """Operator slots use `.` rather than `:` — the filter cannot touch them even when the task does not name them."""
    assert memory_agent._background_slot_off_topic("operator.location", "cualquier cosa") is False
    assert memory_agent._background_slot_off_topic("", "cualquier cosa") is False
    assert memory_agent._background_slot_off_topic("weather:soria", "busca un fontanero") is True


def test_compose_context_empty_db_is_safe(fresh_db):
    ctx = asyncio.run(memory_agent.compose_context("cualquier cosa", budget=500))
    assert isinstance(ctx, str)                      # never raises; string (possibly empty or state only)


def test_remember_writes_to_memory(fresh_db):
    async def run():
        await memapi.start()
        try:
            await memory_agent.remember({"text": "conclusión: el mejor modelo es el X", "kind": "result"})
            # give the sole consumer time to drain the queue
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
    """Dim M — a REVERSAL/cessation ('I no longer drink coffee', 'I no longer work there') is a memorable state
    change that the LLM tends to discard; the backstop rescues it. It does not trigger on 'no longer' alone or on
    chatter."""
    R = memory_agent._REVERSAL_RE
    assert R.search("ya no bebo café, lo he dejado")
    assert R.search("ya no me gusta madrugar")
    assert not R.search("ya no")                                # no content → does not trigger
    assert not R.search("hoy hace sol")


def test_forget_regex_accepts_enclitic_pronouns():
    """Dim N — the FORGET hook must trigger on the NATURAL phrasing of enclitics ('delete X for me', 'delete it',
    'forget what I said about Y', 'delete it for me'), not only on 'forget/delete it' (bug caught by bot BATCH_159)."""
    R = memory_agent._FORGET_RE
    assert R.search("bórrame el número de la seguridad social")
    assert R.search("olvídame lo de la reunión")
    assert R.search("bórramelo del todo el número")
    assert R.search("olvida lo del regalo")                      # the classic still triggers
    assert R.search("bórrate mi contraseña vieja")
    assert not R.search("hoy hace un día estupendo")            # chatter → does not trigger
    # 'bórralo' alone (anaphoric, with no explicit object) does NOT trigger forget-by-name: there is nothing to forget
    assert not R.search("bórralo")


def test_observation_backstop_regex():
    """Dim I — explicit SELF-AWARENESS ('I have noticed that…', 'I have realized that…') must be rescued even if
    the LLM discards it as 'chatter'. The backstop triggers on the observation marker, not on normal chatter."""
    R = memory_agent._OBSERVATION_RE
    assert R.search("me he dado cuenta de que cuando ceno tarde duermo mal")
    assert R.search("he notado que rindo más por las mañanas")
    assert R.search("he observado que el café me pone nervioso")
    assert not R.search("hoy hace un día estupendo")            # chatter → does not trigger


def test_concept_vocab_covers_dietary_restrictions():
    """T183/T178 (prerequisite) — dietary RESTRICTIONS must be tagged with the concept 'food' so they can be
    organized and (in the future) applied cross-topic. Previously 'celiac/gluten' returned [] (no concept)."""
    from memory.concepts import derive_concepts as d
    assert "comida" in d("soy celíaco no puedo tomar gluten")
    assert "comida" in d("soy intolerante a la lactosa")
    assert "comida" in d("me recomiendas un restaurante para cenar")   # the SAME concept as the restriction
    assert d("tengo una hipoteca") == ["finanzas"]                     # no regression


def test_assistant_query_discard_regex():
    """Dim E — an unambiguous QUESTION to the assistant (the weather for X, a recommendation) is NOT a fact → it is
    intercepted and discarded; but a question that CONTAINS a fact ('did you know I moved?') is NOT intercepted (the
    CORE processes it)."""
    R = memory_agent._ASSISTANT_QUERY_RE
    assert R.search("¿qué tiempo va a hacer mañana en Cuenca?")
    assert R.search("¿me recomiendas algún restaurante japonés?")
    assert not R.search("¿sabes que me mudé a Madrid?")          # contains a fact → not intercepted
    assert not R.search("¿tú crees que debería comprarme un coche eléctrico?")  # deliberation (edge case) → not intercepted


def test_is_ambiguous_heuristic():
    assert memory_agent._is_ambiguous("hola", {"memories": []}) is True        # no results
    assert memory_agent._is_ambiguous("a b", {"memories": [{"score": 0.9}]}) is True   # very short query
    assert memory_agent._is_ambiguous(
        "una pregunta bien formada y larga", {"memories": [{"score": 0.9}]}) is False


# ── V2-013: the core classifies and does not lose the profile ────────────────────────────────────────────

def test_classify_extracts_profile_name_and_location():
    plan = memory_agent.classify("Me llamo Ramón y vivo en Barcelona.")
    assert plan["state_patch"].get("operator_name") == "Ramón"
    assert "Barcelona" in plan["state_patch"].get("location", "")
    assert plan["level"] == "long"
    assert plan["pinned"] is True
    assert plan["kind"] == "profile"


def test_classify_extracts_hardware_and_car():
    plan = memory_agent.classify("Tengo un MacBook Pro y conduzco un Tesla Model 3.")
    # one rule wins per turn; check that at least one part of the profile is captured.
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
    # 2026-07-20 contract (H2 audit): raw input WITHOUT a strong signal is no longer durable — short + TTL (visible for a
    # few days due to recency; unequivocally durable items are rescued by the patterns or the LLM on return).
    plan = memory_agent.classify("La reunión con el equipo terminó a las cinco.")
    assert plan["level"] == "short"
    assert plan["kind"] == "fact"
    assert plan.get("ttl_days") == 3.0
    assert plan["state_patch"] == {}


def test_ingest_utterance_populates_state(fresh_db):
    # MEM_PROCESSOR=0 (fixture) → DETERMINISTIC heuristic path (fail-open), without Ollama.
    async def run():
        await memapi.start()
        try:
            res = await memory_agent.ingest_utterance("Me llamo Ramón y vivo en Barcelona.")
            # give the sole consumer time (async write).
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
    # obvious trivia/command → cheap discard, without the LLM (MEM_PROCESSOR=0 in the fixture as well).
    for t in ("gracias", "hola", "cierra el widget"):
        res = asyncio.run(memory_agent.ingest_utterance(t))
        assert res["source"] == "discard", t
        assert res["atoms"] == 0


def test_ingest_utterance_respects_llm_discard(fresh_db, monkeypatch):
    """If the LLM RUNS and returns [] (nothing memorable), it is DISCARDED — it is not re-inflated with the heuristic."""
    monkeypatch.setenv("MEM_PROCESSOR", "1")

    async def fake_process(text, *, state=None):
        return []                                   # it ran and there is nothing to save

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", fake_process)
    # sentence the heuristic WOULD save (mid/fact) — the LLM's verdict takes precedence.
    res = asyncio.run(memory_agent.ingest_utterance("La reunión con el equipo terminó a las cinco."))
    assert res["source"] == "discard-llm"
    assert res["atoms"] == 0


def test_ingest_utterance_retries_once_before_heuristic(fresh_db, monkeypatch):
    """V2-103 (2026-08-16): a transient CORE hiccup must not degrade straight to the heuristic — a single
    retry (off the hot path) protects against the blip that produced raw fragments in a real session. If the
    retry DOES respond, its pills are used, not the heuristic."""
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
    assert res["source"] == "llm"                    # the retry won; it did NOT fall back to the heuristic


def test_ingest_utterance_falls_back_after_retry_also_fails(fresh_db, monkeypatch):
    monkeypatch.setenv("MEM_PROCESSOR", "1")
    calls = {"n": 0}

    async def always_fails(text, *, state=None):
        calls["n"] += 1
        raise RuntimeError("caído de verdad")

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", always_fails)
    res = asyncio.run(memory_agent.ingest_utterance("Vamos a ver, aquí hay un problema grave."))
    assert calls["n"] == 2                            # tried + retried; both failed
    assert res["source"] in ("heuristic", "heuristic-demoted", "discard")   # falls back to the heuristic, as before


def test_ingest_utterance_no_retry_when_processor_disabled(fresh_db, monkeypatch):
    # MEM_PROCESSOR=0 (the fixture default): it is called ONCE (process() internally decides it is
    # off), but `enabled()` being False skips the retry — retrying something switched off makes no sense.
    calls = {"n": 0}

    async def counting_process(text, *, state=None):
        calls["n"] += 1
        return None

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", counting_process)
    asyncio.run(memory_agent.ingest_utterance("cualquier frase"))
    assert calls["n"] == 1    # ONE call, no retry (`enabled()` is False)


def test_ingest_utterance_uses_llm_atoms_when_processor_on(fresh_db, monkeypatch):
    """With the LLM processor ON (mocked), ingest_utterance writes the PILLS it returns, not the heuristic."""
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
    assert st.get("operator_name") == "Ramón"                 # dest=state atom set the state
    out = memapi.query("pádel", reinforce_used=False)
    assert any("pádel" in m["text"].lower() for m in out["memories"])   # dest=long atom became searchable


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
    assert "MacBook Pro M4" in joined            # custom field is now visible in the prompt
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
