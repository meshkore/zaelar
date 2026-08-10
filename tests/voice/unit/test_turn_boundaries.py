#
# test_turn_boundaries.py — UNA FRASE = UN TURNO, y un turno que muere deja rastro.
#
# Anclado a una sesión REAL: `.meshkore/logs/sessions/9748acc2-….jsonl` (2026-08-10, 13:20:50). El operador dictó
# «Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a Ibiza el día diecisiete de agosto… para un coche de cinco
# metros… y cuatro personas, entre ellas dos niños de nueve y once años.» y el STT lo entregó en OCHO transcripciones
# FINALES. Consecuencias, todas visibles en ese log:
#   · T3/T4/T5 abrieron turno con MEDIA frase; T5 llegó a hablar («¿De Denia a dónde, Ricart?») preguntando por el
#     destino que el operador estaba diciendo en ese instante.
#   · T6 llevaba la petición COMPLETA y se quedó sin respuesta: 13 ms después entró «Muéstrame los resultados» y
#     LiveKit lo canceló montando el prompt. Ni una línea en el log explicándolo, y los criterios se perdieron →
#     el turno siguiente habló de «los resultados» sin saber de qué y abrió una hoja en blanco diciendo
#     «Aquí lo tienes».
# Los tres mecanismos que lo cierran se fijan aquí para que no puedan volver a soltarse.
#
import os

import pytest

# Fragmentos VERBATIM de la sesión (eventos i=59/62/69/83…104), en el orden en que llegaron.
FRAGMENTS = [
    "Fenomenal. ¿Me vas a buscar un ferry para ir",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a Ibiza el día diecisiete de agosto, si es lunes, si no, "
    "pues el día dieciocho de agosto. Quiero que sea el más rápido posible, para un coche de cinco metros, metro "
    "ochenta de alto, y cuatro personas, entre ellas dos niños de nueve y once años.",
]
NEXT_SENTENCE = "Muéstrame los resultados."


# ── 1. La señal de fragmento es ESTRUCTURAL (nada de tablas de verbos ni de idioma) ───────────────────────────────

def test_each_real_fragment_is_a_prefix_of_the_next():
    from voice.engine.llm.providers.nucleo import _extends
    for prev, cur in zip(FRAGMENTS, FRAGMENTS[1:]):
        assert _extends(prev, cur), f"{prev!r} debería detectarse como fragmento de {cur[:40]!r}"


def test_a_new_sentence_is_not_a_fragment():
    """«Muéstrame los resultados» es otra frase, no la continuación: el guarda NO debe tragársela."""
    from voice.engine.llm.providers.nucleo import _extends
    assert not _extends(FRAGMENTS[-1], NEXT_SENTENCE)
    assert not _extends(NEXT_SENTENCE, FRAGMENTS[0])


def test_identical_text_is_not_an_extension():
    """Repetir la misma frase NO es un fragmento superado — si no, un turno se descartaría a sí mismo."""
    from voice.engine.llm.providers.nucleo import _extends
    assert not _extends("pon música", "pon música")
    assert not _extends("", "cualquier cosa")     # sin frase previa no hay nada que superar


def test_extension_ignores_spacing_and_case():
    """El STT reformatea espacios/mayúsculas entre entregas parciales; eso no debe romper la detección."""
    from voice.engine.llm.providers.nucleo import _extends
    assert _extends("Busca un   hotel", "busca un hotel en Ibiza")


def test_the_signal_is_language_agnostic():
    """Mecanismo GENÉRICO: mismo criterio dictando en inglés o escribiendo un programa."""
    from voice.engine.llm.providers.nucleo import _extends
    assert _extends("write a function that", "write a function that returns the sum")
    assert _extends("お腹が", "お腹がすいた")


# ── 2. Un turno superado no habla ni actúa ────────────────────────────────────────────────────────────────────────

class _FakeBrain:
    def __init__(self, utterance_text):
        self._utterance = {"text": utterance_text, "at": 0.0}
        self._window = []


class _FakeStream:
    """Sonda mínima: reutiliza los métodos REALES del stream sobre un brain de mentira."""

    def __init__(self, my_text, current_utterance):
        from voice.engine.llm.providers.nucleo import NucleoLLMStream
        self._llm = _FakeBrain(current_utterance)
        self._turn_text = my_text
        self._superseded = NucleoLLMStream._superseded.__get__(self)


def test_an_old_fragment_knows_it_was_superseded():
    # T3 («…para ir») mientras la frase en curso ya es la completa → superado.
    assert _FakeStream(FRAGMENTS[0], FRAGMENTS[-1])._superseded() is True


def test_the_final_complete_turn_is_never_superseded():
    # T6 lleva la frase entera y es la utterance en curso → debe seguir adelante.
    assert _FakeStream(FRAGMENTS[-1], FRAGMENTS[-1])._superseded() is False


def test_a_turn_is_not_superseded_by_a_different_sentence():
    """El bug que NO queremos introducir: que un turno legítimo se descarte porque llegó otra frase distinta."""
    assert _FakeStream(FRAGMENTS[-1], NEXT_SENTENCE)._superseded() is False


# ── 3. Fronteras de turno: los valores salen del módulo que se escribió para esto ──────────────────────────────────

def test_endpointing_uses_the_measured_values_not_livekit_defaults():
    """`voice/endpointing.py` nació de sesiones reales (INI-009) y estuvo HUÉRFANO: el motor pasó a LiveKit y nadie
    lo cableó, así que el turno cerraba con el default de 0,5 s. Ahora es su fuente de verdad."""
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
    """Los ajustes de turno se pasaban como argumentos SUELTOS que LiveKit 1.6 deprecó. Si alguien vuelve a
    mezclar las dos formas en la misma llamada, esto lo caza."""
    import inspect
    from voice.engine.pipeline import agent
    src = inspect.getsource(agent)
    # Solo la CONSTRUCCIÓN de la sesión: `allow_interruptions` también es argumento legítimo de `session.say()`,
    # que es por-locución y no tiene nada que ver con la configuración del turno.
    start = src.index("AgentSession(")
    ctor = src[start:src.index(")", src.index("turn_handling={", start))]
    assert "turn_handling={" in ctor
    for legacy in ("preemptive_generation=", "allow_interruptions=", "turn_detection=", "min_interruption_duration="):
        assert legacy not in ctor, f"{legacy} está deprecado en AgentSession: va dentro de turn_handling"


# ── 4. Un turno que muere deja rastro Y conserva la frase ─────────────────────────────────────────────────────────

def test_a_cancelled_turn_keeps_the_operator_words_and_says_where_it_died(monkeypatch):
    """El daño real de T6: los criterios del ferry se perdieron porque el `push_user` que los conserva vivía SOLO en
    el `except` del stream, y una cancelación anterior a esa fase se los llevaba en silencio."""
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

    # (a) la frase del operador sobrevive → el turno siguiente sabe de qué se hablaba
    assert any(FRAGMENTS[-1] in str(t.get("text", t)) for t in s._llm._window), s._llm._window
    # (b) y queda una línea en la observabilidad con la FASE en la que murió
    assert events, "un turno que muere sin dejar rastro es justo el bug"
    kind, label, kw = events[-1]
    assert "descartado" in label
    assert kw["extra"]["phase"] == "montando el prompt"
    assert kw["extra"]["text_kept"] is True


def test_the_death_note_never_duplicates_the_barge_in_line(monkeypatch):
    """El `except` del stream ya relata la cancelación con métricas; la envoltura no debe emitir una segunda."""
    from voice.engine.llm.providers import nucleo

    events = []
    monkeypatch.setattr(nucleo, "_last_user_text", lambda _ctx: "hola")
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: events.append(label))

    class _S:
        _chat_ctx = object()

        def __init__(self):
            self._llm = _FakeBrain("")
            self._death_logged = True      # el stream ya lo contó
            self._note_death = nucleo.NucleoLLMStream._note_death.__get__(self)

    _S()._note_death("barge-in")
    assert events == []


# ── 5. Abrir una hoja EN BLANCO no es «aquí lo tienes» ────────────────────────────────────────────────────────────

def test_an_empty_presentation_surface_is_detected(tmp_path, monkeypatch):
    """El acuse falso de la sesión: `show_widget → search` sobre una pantalla vacía + «Aquí lo tienes». Ahora el
    evento lleva `empty`, así que deja de ser invisible en el log."""
    from voice.engine.llm.providers.nucleo import _surface_is_empty
    from widgets import store

    monkeypatch.setattr(store, "load", lambda wid, default=None, **kw: {"title": "Resultados", "items": []})
    assert _surface_is_empty("results") is True

    monkeypatch.setattr(store, "load",
                        lambda wid, default=None, **kw: {"title": "Resultados", "items": [{"title": "Plan A"}]})
    assert _surface_is_empty("results") is False


def test_emptiness_fails_open_when_it_cannot_be_known(monkeypatch):
    """Nunca afirmamos «está vacía» si no lo podemos saber (un widget sin estado, un fallo de lectura)."""
    from voice.engine.llm.providers.nucleo import _surface_is_empty
    from widgets import store

    def _boom(*a, **kw):
        raise RuntimeError("disco")

    monkeypatch.setattr(store, "load", _boom)
    assert _surface_is_empty("results") is False


# ── 6. La frontera results ↔ search queda escrita donde el modelo la lee ──────────────────────────────────────────

@pytest.mark.parametrize("query", ["muéstrame los resultados", "los resultados", "muéstrame las propuestas"])
def test_the_name_resolver_already_points_at_results(query):
    """La resolución por nombre/alias (V2-082) SÍ acertaba: el que eligió `search` fue el modelo, leyendo el
    catálogo. Este test deja constancia de que el resolver no es el culpable — si algún día falla, es otro bug."""
    from widgets import runtime
    # El catálogo está CACHEADO y otras suites lo sustituyen por uno sintético (test_selection_scale monta 10.000
    # widgets falsos). Sin invalidar, este test mide el catálogo de otro test, no el real.
    runtime.invalidate()
    assert (runtime.identify(query) or {}).get("match") == "results"


def test_the_two_surfaces_declare_their_frontier():
    """`search` es el CARTEL de progreso; `results` es donde aterrizan los hallazgos. Sin decirlo en el manifest —
    lo único que el modelo lee— «muéstrame los resultados» volvería a abrir el spinner vacío."""
    import json
    import pathlib

    search = json.loads(pathlib.Path("widgets/search/manifest.json").read_text())
    results = json.loads(pathlib.Path("widgets/results/manifest.json").read_text())

    assert "results" in search["whenToUse"], "search debe remitir a results para los hallazgos"
    assert "search" in results["whenToUse"], "results debe decir que search es solo el progreso"
    # y results debe advertir que abrirla no produce nada
    low = results["whenToUse"].lower()
    assert "no produce" in low or "en blanco" in low


# ── 7. El FlashBrain NUNCA se queda parado ────────────────────────────────────────────────────────────────────────
# Sesión 14:08:26: 23 turnos seguidos sin respuesta durante 5 minutos. El operador preguntó «¿me estás escuchando?»
# y «¿estás operativo, sí o no?» y tampoco obtuvo nada. Medido en el log: turnos de 35,7 s · 31,8 s · 32,2 s y uno
# de 60,5 s, todos con `partial_chars=0` y `ttft=None` — el modelo no emitió UN solo token hablable. El único plazo
# que existía era el timeout de red de httpx: 60 s. Regla dura del operador: el FlashBrain siempre operativo,
# aunque los Brain Workers vayan lentos.

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


def test_the_deadline_measures_silence_not_total_length():
    """Clave del diseño: cada trozo hablable renueva el plazo, así una respuesta larga y legítima sale ENTERA y
    solo se corta lo que de verdad no avanza."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    loop = src[src.index("_quiet_ms = _turn_budget_ms()"):]
    assert "if delta:" in loop and loop.count("_quiet_ms = _turn_budget_ms()") >= 2, \
        "el plazo debe renovarse con cada delta hablable"
    assert "asyncio.wait_for(_agen.__anext__()" in loop, "el plazo va por trozo, no sobre el stream entero"


def test_a_stall_is_treated_as_a_brain_failure_not_as_silence():
    """Atascarse debe dar frase corta y honesta + alerta + salud en rojo (rama `errored`), nunca un minuto de
    silencio que parece un cuelgue."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    # el PRIMER `except asyncio.TimeoutError` de la función es el del recall (otra cosa); nos interesa el del
    # bucle de streaming, que va después del plazo de silencio.
    stall = src[src.index("_quiet_ms = _turn_budget_ms()"):]
    stall = stall[stall.index("except asyncio.TimeoutError:"):]
    assert "errored = True" in stall[:600]
    assert "ATASCADO" in stall[:900], "el atasco tiene que dejar rastro en la observabilidad"


def test_a_stall_is_classified_as_an_outage_so_the_status_icon_goes_red():
    from voice import llm_health
    assert llm_health.classify("flash brain stalled: 9000 ms sin salida hablable") == "outage"
