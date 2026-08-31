#
# test_turn_boundaries.py — ONE SENTENCE = ONE TURN, and a turn that dies leaves a trace.
#
# Anchored to a REAL session: `.meshkore/logs/sessions/9748acc2-….jsonl` (2026-08-10, 13:20:50). The operator dictated
# «Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a Ibiza el día diecisiete de agosto… para un coche de cinco
# metros… y cuatro personas, entre ellas dos niños de nueve y once años.» and STT delivered it in EIGHT FINAL
# transcriptions. Consequences, all visible in that log:
#   · T3/T4/T5 opened a turn with HALF a sentence; T5 even spoke («¿De Denia a dónde, Ricart?»), asking about the
#     destination the operator was saying at that moment.
#   · T6 carried the COMPLETE request and received no response: 13 ms later «Muéstrame los resultados» arrived and
#     LiveKit cancelled it while building the prompt. Not a single line in the log explained it, and the criteria were
#     lost → the next turn talked about «los resultados» without knowing what they were and opened a blank surface,
#     saying «Aquí lo tienes».
# The three mechanisms that close it are fixed here so they cannot come loose again.
#
import os

import pytest

# VERBATIM fragments from the session (events i=59/62/69/83…104), in the order they arrived.
FRAGMENTS = [
    "Fenomenal. ¿Me vas a buscar un ferry para ir",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a Ibiza el día diecisiete de agosto, si es lunes, si no, "
    "pues el día dieciocho de agosto. Quiero que sea el más rápido posible, para un coche de cinco metros, metro "
    "ochenta de alto, y cuatro personas, entre ellas dos niños de nueve y once años.",
]
NEXT_SENTENCE = "Muéstrame los resultados."


# ── 1. The fragment signal is STRUCTURAL (no verb tables or language-specific logic) ─────────────────────────────

def test_each_real_fragment_is_a_prefix_of_the_next():
    from voice.engine.llm.providers.nucleo import _extends
    for prev, cur in zip(FRAGMENTS, FRAGMENTS[1:]):
        assert _extends(prev, cur), f"{prev!r} debería detectarse como fragmento de {cur[:40]!r}"


def test_a_new_sentence_is_not_a_fragment():
    """«Muéstrame los resultados» is another sentence, not the continuation: the guard must NOT swallow it."""
    from voice.engine.llm.providers.nucleo import _extends
    assert not _extends(FRAGMENTS[-1], NEXT_SENTENCE)
    assert not _extends(NEXT_SENTENCE, FRAGMENTS[0])


def test_identical_text_is_not_an_extension():
    """Repeating the same sentence is NOT a superseded fragment—for otherwise a turn would discard itself."""
    from voice.engine.llm.providers.nucleo import _extends
    assert not _extends("pon música", "pon música")
    assert not _extends("", "cualquier cosa")     # without a previous sentence there is nothing to supersede


def test_extension_ignores_spacing_and_case():
    """STT reformats spacing/capitalization between partial deliveries; that must not break detection."""
    from voice.engine.llm.providers.nucleo import _extends
    assert _extends("Busca un   hotel", "busca un hotel en Ibiza")


def test_the_signal_is_language_agnostic():
    """GENERIC mechanism: the same criterion when dictating in English or writing a program."""
    from voice.engine.llm.providers.nucleo import _extends
    assert _extends("write a function that", "write a function that returns the sum")
    assert _extends("お腹が", "お腹がすいた")


# ── 2. A superseded turn neither speaks nor acts ─────────────────────────────────────────────────────────────────

class _FakeBrain:
    def __init__(self, utterance_text):
        self._utterance = {"text": utterance_text, "at": 0.0}
        self._window = []


class _FakeStream:
    """Minimal probe: reuses the stream's REAL methods on a fake brain."""

    def __init__(self, my_text, current_utterance):
        from voice.engine.llm.providers.nucleo import NucleoLLMStream
        self._llm = _FakeBrain(current_utterance)
        self._turn_text = my_text
        self._superseded = NucleoLLMStream._superseded.__get__(self)


def test_an_old_fragment_knows_it_was_superseded():
    # T3 («…para ir») while the current sentence is already complete → superseded.
    assert _FakeStream(FRAGMENTS[0], FRAGMENTS[-1])._superseded() is True


def test_the_final_complete_turn_is_never_superseded():
    # T6 contains the full sentence and is the current utterance → it must proceed.
    assert _FakeStream(FRAGMENTS[-1], FRAGMENTS[-1])._superseded() is False


def test_a_turn_is_not_superseded_by_a_different_sentence():
    """The bug we do NOT want to introduce: discarding a legitimate turn because another sentence arrived."""
    assert _FakeStream(FRAGMENTS[-1], NEXT_SENTENCE)._superseded() is False


# ── 3. Turn boundaries: the values come from the module written for this purpose ─────────────────────────────────

def test_endpointing_uses_the_measured_values_not_livekit_defaults():
    """`voice/endpointing.py` was born from real sessions (INI-009) and remained ORPHANED: the engine moved to LiveKit
    and nobody wired it in, so the turn closed with the 0.5 s default. It is now the source of truth."""
    from voice import endpointing as ep
    from voice.engine.pipeline.agent import _endpointing_opts
    opts = _endpointing_opts()
    assert opts["min_delay"] == ep.HOLD_BASE
    assert opts["max_delay"] == ep.HOLD_MAX
    assert opts["min_delay"] > 0.5, "0,5 s es el default de LiveKit: es lo que partía la frase del operador"
    assert opts["mode"] == "dynamic", "hold creciente = lo que hold_secs() calculaba a mano"


def test_endpointing_is_tunable_without_touching_code(monkeypatch):
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "0.9")
    monkeypatch.setenv("ZAELAR_ENDPOINT_MAX_S", "3.5")
    assert _endpointing_opts() == {"mode": "dynamic", "min_delay": 0.9, "max_delay": 3.5}


def test_endpointing_never_lets_max_fall_below_min(monkeypatch):
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "2.0")
    monkeypatch.setenv("ZAELAR_ENDPOINT_MAX_S", "0.5")
    opts = _endpointing_opts()
    assert opts["max_delay"] >= opts["min_delay"]


def test_endpointing_survives_a_garbage_env(monkeypatch):
    from voice import endpointing as ep
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "no-es-un-numero")
    assert _endpointing_opts()["min_delay"] == ep.HOLD_BASE


def test_the_session_declares_its_turn_boundaries_in_one_place():
    """Turn settings used to be passed as LOOSE arguments, which LiveKit 1.6 deprecated. If anyone mixes the two
    forms in the same call again, this catches it."""
    import inspect
    from voice.engine.pipeline import agent
    src = inspect.getsource(agent)
    # Only the session CONSTRUCTION: `allow_interruptions` is also a legitimate `session.say()` argument,
    # which is per-utterance and has nothing to do with turn configuration.
    start = src.index("AgentSession(")
    ctor = src[start:src.index(")", src.index("turn_handling={", start))]
    assert "turn_handling={" in ctor
    for legacy in ("preemptive_generation=", "allow_interruptions=", "turn_detection=", "min_interruption_duration="):
        assert legacy not in ctor, f"{legacy} está deprecado en AgentSession: va dentro de turn_handling"


# ── 4. A turn that dies leaves a trace AND preserves the sentence ─────────────────────────────────────────────────

def test_a_cancelled_turn_keeps_the_operator_words_and_says_where_it_died(monkeypatch):
    """The real damage in T6: the ferry criteria were lost because the `push_user` that preserves them lived ONLY in
    the stream's `except`, and a cancellation before that phase silently carried them away."""
    from voice.engine.llm.providers import nucleo

    events = []
    monkeypatch.setattr(nucleo, "_last_user_text", lambda _ctx: FRAGMENTS[-1])

    import voice.observer as observer
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, **kw: events.append((kind, label, kw)))

    class _S:
        _chat_ctx = object()

        def __init__(self):
            self._llm = _FakeBrain("")
            self._phase = "montando el prompt"
            self._death_logged = False
            self._note_death = nucleo.NucleoLLMStream._note_death.__get__(self)

    s = _S()
    s._note_death("superado por otro turno")

    # (a) the operator's sentence survives → the next turn knows what was being discussed
    assert any(FRAGMENTS[-1] in str(t.get("text", t)) for t in s._llm._window), s._llm._window
    # (b) and an observability line remains with the PHASE in which it died
    assert events, "un turno que muere sin dejar rastro es justo el bug"
    kind, label, kw = events[-1]
    assert "descartado" in label
    assert kw["extra"]["phase"] == "montando el prompt"
    assert kw["extra"]["text_kept"] is True


def test_the_death_note_never_duplicates_the_barge_in_line(monkeypatch):
    """The stream's `except` already reports the cancellation with metrics; the wrapper must not emit a second one."""
    from voice.engine.llm.providers import nucleo

    events = []
    monkeypatch.setattr(nucleo, "_last_user_text", lambda _ctx: "hola")
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: events.append(label))

    class _S:
        _chat_ctx = object()

        def __init__(self):
            self._llm = _FakeBrain("")
            self._death_logged = True      # the stream already reported it
            self._note_death = nucleo.NucleoLLMStream._note_death.__get__(self)

    _S()._note_death("barge-in")
    assert events == []


# ── 5. Opening a BLANK surface is not «here you go» ───────────────────────────────────────────────────────────────

def test_an_empty_presentation_surface_is_detected(tmp_path, monkeypatch):
    """The session's false acknowledgment: `show_widget → search` on an empty screen + «Aquí lo tienes». Now the
    event carries `empty`, so it is no longer invisible in the log."""
    from voice.engine.llm.providers.nucleo import _surface_is_empty
    from widgets import store

    monkeypatch.setattr(store, "load", lambda wid, default=None, **kw: {"title": "Resultados", "items": []})
    assert _surface_is_empty("results") is True

    monkeypatch.setattr(store, "load",
                        lambda wid, default=None, **kw: {"title": "Resultados", "items": [{"title": "Plan A"}]})
    assert _surface_is_empty("results") is False


def test_emptiness_fails_open_when_it_cannot_be_known(monkeypatch):
    """We never claim «it is empty» when we cannot know (a widget without state, a read failure)."""
    from voice.engine.llm.providers.nucleo import _surface_is_empty
    from widgets import store

    def _boom(*a, **kw):
        raise RuntimeError("disco")

    monkeypatch.setattr(store, "load", _boom)
    assert _surface_is_empty("results") is False


# ── 6. The results ↔ search boundary is written where the model reads it ──────────────────────────────────────────

@pytest.mark.parametrize("query", ["muéstrame los resultados", "los resultados", "muéstrame las propuestas"])
def test_the_name_resolver_already_points_at_results(query):
    """Name/alias resolution (V2-082) DID work: it was the model, reading the catalog, that chose `search`.
    This test records that the resolver is not at fault—if it ever fails, that is another bug."""
    from widgets import runtime
    # The catalog is CACHED and other suites replace it with a synthetic one (test_selection_scale mounts 10,000
    # fake widgets). Without invalidation, this test measures another test's catalog, not the real one.
    runtime.invalidate()
    assert (runtime.identify(query) or {}).get("match") == "results"


def test_the_two_surfaces_declare_their_frontier():
    """`search` is the progress SIGNPOST; `results` is where findings land. Without saying so in the manifest—the
    only thing the model reads—«muéstrame los resultados» would open the empty spinner again."""
    import json
    import pathlib

    search = json.loads(pathlib.Path("widgets/search/manifest.json").read_text())
    results = json.loads(pathlib.Path("widgets/results/manifest.json").read_text())

    assert "results" in search["whenToUse"], "search debe remitir a results para los hallazgos"
    assert "search" in results["whenToUse"], "results debe decir que search es solo el progreso"
    # and results must warn that opening it produces nothing
    low = results["whenToUse"].lower()
    assert "no produce" in low or "en blanco" in low


# ── 7. FlashBrain NEVER gets stuck ────────────────────────────────────────────────────────────────────────────────
# Session 14:08:26: 23 consecutive turns without a response over 5 minutes. The operator asked «¿me estás escuchando?»
# and «¿estás operativo, sí o no?» and still got nothing. Measured in the log: turns of 35.7 s · 31.8 s · 32.2 s and one
# of 60.5 s, all with `partial_chars=0` and `ttft=None`—the model emitted not a single speakable token. The only
# deadline that existed was httpx's network timeout: 60 s. The operator's hard rule: FlashBrain always operational,
# even when the Brain Workers are slow.

def test_the_voice_turn_has_a_silence_deadline():
    from voice.engine.llm.providers.nucleo import _turn_budget_ms
    ms = _turn_budget_ms()
    assert 0 < ms <= 15000, "un turno de voz no puede tolerar más que unos segundos de silencio"
    assert ms < 60000, "60 s era el timeout de red de httpx: justo el agujero que dejó al operador sin respuesta"


def test_the_deadline_is_tunable_and_disablable(monkeypatch):
    from voice.engine.llm.providers.nucleo import _turn_budget_ms
    monkeypatch.setenv("ZAELAR_TURN_QUIET_MS", "4000")
    assert _turn_budget_ms() == 4000
    monkeypatch.setenv("ZAELAR_TURN_QUIET_MS", "0")
    assert _turn_budget_ms() > 10 ** 8, "0 = sin plazo (escotilla), no plazo cero"
    monkeypatch.setenv("ZAELAR_TURN_QUIET_MS", "no-numero")
    assert _turn_budget_ms() == 9000


def test_the_deadline_measures_stream_progress_not_speech():
    """FIXED 2026-08-12 after three HEALTHY turns died in two minutes. This test previously asserted the
    implementation detail (`wait_for` over `__anext__`), which let the bug through: the deadline measured «no voice
    comes out», and a turn whose response is an ACTION emits no speakable characters—the tool-call chunks are
    consumed by `stream()` without yielding. What is measured is that the STREAM advances."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    loop = src[src.index("_quiet_ms = _turn_budget_ms()"):]
    assert "if delta:" in loop and loop.count("_quiet_ms = _turn_budget_ms()") >= 2, \
        "el plazo debe renovarse con cada delta hablable"
    assert "stream_advancing(" in loop, "antes de declarar un atasco hay que mirar el latido del stream"
    assert "asyncio.wait_for(_chunks.get()" in loop, "el plazo va por trozo, no sobre el stream entero"


def test_a_turn_whose_answer_is_an_action_is_not_a_stall():
    """The REAL case (13:49:00 and 13:50:55): `ttft=1.50s`, `spoken_chars=0`, and the turn guillotined at 9 s. The
    model was emitting a tool-call—the operator had just said «no veo ningún resultado en pantalla»."""
    from voice.engine.llm.providers.nucleo import stream_advancing
    now = 1000.0
    # a chunk arrived 1 s ago with a 9 s deadline → the stream is ALIVE, even if no voice came out
    assert stream_advancing({"last_chunk_ts": now - 1.0, "chunks": 7}, 9000, now) is True


def test_a_provider_that_never_answers_is_still_a_stall():
    """The counterweight: reducing false positives must not hide the failure that the deadline exists to cut off."""
    from voice.engine.llm.providers.nucleo import stream_advancing
    now = 1000.0
    assert stream_advancing({}, 9000, now) is False                        # ni un chunk: atasco de verdad
    assert stream_advancing({"last_chunk_ts": 0}, 9000, now) is False      # sin sello = nada ha llegado
    assert stream_advancing({"last_chunk_ts": now - 30.0}, 9000, now) is False   # avanzó, pero hace rato


def test_the_stream_stamps_its_heartbeat_on_every_chunk():
    """The stamp must be applied by whoever SEES each chunk (`fast_client`), not whoever only receives chunks with text.

    `stream()` is a thin wrapper (V2-092 addendum, 2026-08-15: counts in-flight turns for deferred shutdown
    of ⏻) that delegates to `_stream_inner()`—the real streaming logic remains there unchanged."""
    import inspect
    from nucleo.flash.fast_client import FastClient
    src = inspect.getsource(FastClient._stream_inner)
    body = src[src.index("async for chunk in stream:"):]
    head = body[:body.index("text = getattr(delta")]
    assert "last_chunk_ts" in head, "el latido se sella ANTES de filtrar por texto, o los turnos de acción no cuentan"


def test_the_stream_is_torn_down_without_cancelling_a_call_in_flight():
    """Cancelling an `__anext__` midway and then calling `aclose()` leaves the generator in an undefined state—it was
    the previous approach and a candidate cause of voice-thread hangs. The TASK that iterates over it is cancelled;
    it is the sole owner of the `async for`."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    loop = src[src.index("_quiet_ms = _turn_budget_ms()"):]
    assert "_agen.aclose()" not in loop and "__anext__" not in loop
    assert "_pump_task.cancel()" in loop


def test_a_stall_is_treated_as_a_brain_failure_not_as_silence():
    """Getting stuck must produce a short, honest phrase + alert + red health status (`errored` branch), never a minute
    of silence that looks like a hang."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    # the FIRST `except asyncio.TimeoutError` in the function is for recall (something else); we need the one in the
    # streaming loop, which comes after the silence deadline.
    stall = src[src.index("_quiet_ms = _turn_budget_ms()"):]
    stall = stall[stall.index("except asyncio.TimeoutError:"):]
    assert "errored = True" in stall[:600]
    assert "ATASCADO" in stall[:900], "el atasco tiene que dejar rastro en la observabilidad"


def test_a_stalled_turn_is_a_warning_not_a_dead_provider():
    """FIXED 2026-08-12 with a live case: the deadline reused the entire error branch, so ONE turn
    cortado —del que la sesión se recupera al turno siguiente— dejaba el ◉ en ROJO con «no responde» y gritaba
    «Cerebro rápido caído». El modelo contestaba bien antes y después: el operador se queda mirando un LLM en rojo
    que funciona, y buscando una avería que no existe. Se separa el HECHO (este turno no salió) del DIAGNÓSTICO
    (el proveedor está caído). Sigue habiendo aviso — lo que no hay es un diagnóstico inventado."""
    import asyncio
    import json

    from voice import health_state
    from server.voice_api import status

    health_state.record("llm", "slow", "un turno se atascó (9000 ms sin respuesta) y lo corté")
    try:
        items = json.loads(bytes(asyncio.run(status()).body).decode("utf-8"))["items"]
        llm = next(i for i in items if i["key"] == "llm")
        assert llm["state"] == "warn", "un turno atascado avisa; no declara el proveedor caído"
        assert "atasc" in llm["detail"] and "no responde" not in llm["detail"]
    finally:
        health_state.clear("llm")


def test_a_real_provider_failure_still_goes_red():
    """The counterweight to the previous test: downgrading a stall must not downgrade a real outage."""
    import asyncio
    import json

    from voice import health_state, llm_health
    from server.voice_api import status

    assert llm_health.classify("connection refused") == "outage"
    health_state.record("llm", "outage", "connection refused")
    try:
        items = json.loads(bytes(asyncio.run(status()).body).decode("utf-8"))["items"]
        llm = next(i for i in items if i["key"] == "llm")
        assert llm["state"] == "error" and "no responde" in llm["detail"]
    finally:
        health_state.clear("llm")


def test_the_stall_path_says_stalled_not_dead():
    """The spoken/visible ALERT must not say «down» for a single turn either."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    stall = src[src.index("_quiet_ms = _turn_budget_ms()"):]
    stall = stall[stall.index("except asyncio.TimeoutError:"):]
    assert "stalled = True" in stall[:700]
    # V2-252: the classification (stall vs outage) is shared with the TEXT channel in
    # `nucleo/flash/provider_failure.py`, because writing it twice caused it to diverge three times. This checks that
    # this turn PASSES it the fact—`stalled=`—and that the shared module translates it to «slow», not «down».
    assert "stalled=bool(stalled)" in src
    import inspect as _i

    from nucleo.flash import provider_failure as _pf
    assert 'health_state.record("llm", "slow"' in _i.getsource(_pf.handle)
    assert "Un turno se atascó y lo corté" in src
