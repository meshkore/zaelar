"""
TURN-TAKING BY MEANING (V2-095, 2026-08-14) — the turn boundary is no longer merely acoustic.

The operator dictated a long request, and every pause to think opened a turn that the next fragment
cancelled. Session b70a45d0, dictation segment:

    465s → 626s (161 s):  22 prompts · 18 cancelled · 20 waiting fillers · ZERO responses

…with prompts built on «del», «del software,», «a», «para que», «Un un superplanning». Across the entire session: 89
final transcriptions, 33 followed by cancellation, 53 prompts for 11 responses (79% of the spend wasted), and an
escalation to a worker launched on a truncated request that the operator had to cancel.

The cases in this file are the 89 REAL fragments. The corpus takes precedence over any grammatical intuition: the
first version of the rule («short and unfinished») held ALL of the operator's short commands —«pon música»,
«abre la agenda»— and this was caught by measuring, not reading.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import segmenter as sg


# ── WHAT MUST NEVER BE HELD ───────────────────────────────────────────────────────────────────────────────────
# A false positive here is worse than the original bug: the operator gives a command and the agent stays silent for 6 s.
# Short commands are what the operator says most often, and «sí» is how they authorize something irreversible.
@pytest.mark.parametrize("orden", [
    "abre la agenda", "sube el volumen", "pon música", "cierra eso", "enséñame la agenda",
    "siguiente canción", "vacía la agenda", "ponme el vídeo de Messi", "deja de buscar",
    # «para» by itself is a STOP command, even though it is also a preposition.
    "para", "para la música", "párala", "cancélalo", "sigue",
    # replies and confirmations: how the operator answers a question from the agent.
    "sí", "no", "vale", "gracias",
    # THE INCIDENT PHRASE: this is how they authorized the worker. Holding it would have been the same failure in reverse.
    "sí, te autorizo a borrar toda la agenda",
])
def test_las_ordenes_y_respuestas_nunca_se_retienen(orden):
    hold, why = sg.should_hold(orden)
    assert hold is False, f"«{orden}» se retendría por «{why}» — eso deja al operador esperando por nada"


# ── THE REAL FRAGMENTS THAT WERE INDEED INCOMPLETE ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("frag,motivo", [
    ("Bueno, si no me equivoco,", "coma"),
    ("del", "palabra función"),
    ("del software,", "coma"),
    ("Vale, me gustaría ahora que hagas un", "artículo colgado"),
    ("completa del", "preposición colgada"),
    ("código,", "coma"),
    ("porque necesitaré dejarle esto", "determinante colgado"),
    ("otras personas,", "coma"),
    ("para que", "conjunción colgada"),
    ("Entonces, necesito, de alguna manera,", "coma"),
    ("y me gustaría que lo", "pronombre colgado"),
    ("veremos cómo lo", "pronombre colgado"),
    ("y así podemos entregar el", "artículo colgado"),
    ("Siguen quedando cuatro ítems en", "preposición colgada"),
    ("Y tiene que haber", "verbo sin complemento"),
    ("Cierra todos los", "artículo colgado"),
    # STT inserts periods wherever it wants: ending in a period does NOT mean the request is finished.
    ("No el widget, los datos de la.", "acaba en «la» AUNQUE lleve punto"),
    ("planning de...", "acaba en «de» con puntos suspensivos"),
    # Continuations that BEGIN with a function word.
    ("de framework y y cómo hacer una auditoría", "empieza por «de»"),
])
def test_los_fragmentos_reales_a_medias_se_retienen(frag, motivo):
    hold, why = sg.should_hold(frag)
    assert hold is True, f"«{frag}» pasaría y abriría un turno a medias ({motivo})"
    assert why, "una retención sin motivo es un turno que no llega y nadie sabe por qué"


# ── WHAT IS A COMPLETE REQUEST (from the same session) ──────────────────────────────────────────────────────
@pytest.mark.parametrize("frase", [
    "Enséñame ahora mi agenda.",
    "Calendarios, tareas predeterminadas, déjamela vacía por completo.",
    "¿Me has oído?",
    "En el widget siguen apareciendo cosas.",
    "No está vacío.",
    "¿cómo es posible que el proceso no pueda eliminar todo eso?",
    "Vacía la agenda por completo.",
    "No, no está hecho, no estás comprobando que hagas las cosas.",
    "Vale, pues hazme un favor, lees lo que hay en la agenda.",
    "Lo borras y luego compruebas que lo hayas borrado.",
    "No, esto no era para ti, puedes pararme.",
    "Cancélalo, no tenía, el mensaje no era para ti.",
])
def test_las_peticiones_completas_pasan(frase):
    hold, why = sg.should_hold(frase)
    assert hold is False, f"«{frase}» está completa y se retendría por «{why}»"


# ── «mi»/«mí» — the detector ignored the actual operator (2026-08-16, session 1021eeee) ─────────────────────
# «dame los datos personales que conoces de mi» was held THREE times in a row without generating speech or an action — the
# accumulator (V2-096) has no time-based safety valve by design, so a sentence misclassified as incomplete
# remains unanswered FOREVER, not merely delayed. Cause: «mí» (pronoun, «de mí»/«sobre mí»/«para mí») is
# phonetically IDENTICAL to possessive «mi» without an accent, and STT rarely preserves the accent in a monosyllable — the
# accent exception (`_ACCENTED_NOT_FUNCTION`) only protected the rare case in which it DID preserve it.
@pytest.mark.parametrize("frase", [
    "dame los datos personales que conoces de mi",
    "cuéntame lo que sabes de mi",
    "¿qué opinas de mi?",
    "esto es para mi",
    "habla de mi",
    "dame los datos personales que conoces de mí",   # with accent: already worked, must not regress
])
def test_terminar_en_mi_sin_tilde_no_se_retiene_para_siempre(frase):
    hold, why = sg.should_hold(frase)
    assert hold is False, f"«{frase}» es una petición completa (pronombre «mí») y se retendría por «{why}»"


def test_mi_posesiva_sigue_incompleta_como_palabra_suelta():
    """The fix is ONLY for «mi» at the end of a sentence — as a standalone word («mi» by itself) it remains ambiguous,
    and possessive «mi» followed by a noun («mi coche…») never reaches this case because it does not end in «mi»."""
    hold, why = sg.should_hold("mi")
    assert hold is True, "una «mi» suelta sigue siendo ambigua, no una petición"


# ── INVARIANTS ────────────────────────────────────────────────────────────────────────────────────────────────
def test_el_techo_de_retencion_entrega_siempre():
    """The semantic layer may DELAY a turn, but never lose it. An operator who stops halfway («…y ponerlo
    en la») must not remain unanswered forever because of a comma."""
    frag = "y ponerlo en la"
    assert sg.should_hold(frag, held_s=0.0)[0] is True
    assert sg.should_hold(frag, held_s=sg.MAX_HOLD_S + 0.1) == (False, "techo de retención")


def test_fail_open_ante_cualquier_cosa_rara():
    """Holding too much turns a slow agent into a mute agent: when in doubt, PASS."""
    for raro in ["", "   ", "…", "!!!", "🙂", None]:
        assert sg.should_hold(raro)[0] is False, repr(raro)


def test_el_juez_esta_ENCENDIDO_por_defecto(monkeypatch):
    """V2-102: it is no longer opt-in (`ZAELAR_SEGMENTER_MODEL`, which nobody ever got around to reading — a declared
    but never wired gap). This codebase has already encountered "a capability whose default is off is a capability
    nobody has" three times (Whisper, REM, the segmenter itself) — this was not going to be the fourth. There is still
    a manual escape hatch, `ZAELAR_TURN_JUDGE=0`, for emergencies."""
    monkeypatch.delenv("ZAELAR_TURN_JUDGE", raising=False)
    assert sg.judge_enabled() is True
    monkeypatch.setenv("ZAELAR_TURN_JUDGE", "0")
    assert sg.judge_enabled() is False
    monkeypatch.setenv("ZAELAR_TURN_JUDGE", "1")
    assert sg.judge_enabled() is True


def test_parse_judge_lee_los_tres_veredictos():
    assert sg._parse_judge('{"verdict": "COMPLETE", "question": null}') == ("complete", "")
    assert sg._parse_judge('{"verdict": "INCOMPLETE", "question": null}') == ("incomplete", "")
    assert sg._parse_judge('{"verdict": "ASK", "question": "¿Qué canción?"}') == ("ask", "¿Qué canción?")


def test_parse_judge_ASK_sin_pregunta_hace_fail_open():
    """An ASK without question text is not actionable — there is nothing to say aloud."""
    assert sg._parse_judge('{"verdict": "ASK", "question": null}') == ("incomplete", "")


def test_parse_judge_tolera_code_fences_como_el_de_i18n():
    raw = '```json\n{"verdict": "COMPLETE", "question": null}\n```'
    assert sg._parse_judge(raw) == ("complete", "")


@pytest.mark.parametrize("raw", [None, "", "no es json", '{"verdict": "MAYBE"}', "{"])
def test_parse_judge_fail_open_ante_basura(raw):
    assert sg._parse_judge(raw) == ("incomplete", "")


def test_judge_deshabilitado_no_llama_a_nadie(monkeypatch):
    monkeypatch.setenv("ZAELAR_TURN_JUDGE", "0")

    async def _boom(*a, **kw):
        raise AssertionError("no debía llamar al modelo con el juez apagado")
    monkeypatch.setattr(asyncio, "to_thread", _boom)
    assert asyncio.run(sg.judge("dame los datos personales que conoces de mi")) == ("incomplete", "")


def test_judge_texto_vacio_no_llama_a_nadie(monkeypatch):
    async def _boom(*a, **kw):
        raise AssertionError("no debía llamar al modelo con texto vacío")
    monkeypatch.setattr(asyncio, "to_thread", _boom)
    assert asyncio.run(sg.judge("   ")) == ("incomplete", "")


def test_judge_llama_al_modelo_y_parsea_su_respuesta(monkeypatch):
    """The real case that motivated all this: the lexical layer already said incomplete (see test_segmenter.py above),
    and the judge corrects it."""
    captured = {}

    async def _fake_to_thread(fn, *args, **kwargs):
        captured["task"] = args[0]
        captured["text"] = args[2]
        return '{"verdict": "COMPLETE", "question": null}'
    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
    verdict, extra = asyncio.run(sg.judge("dame los datos personales que conoces de mi"))
    assert verdict == "complete"
    assert extra == ""
    assert captured["task"] == "turn_complete"
    assert captured["text"] == "dame los datos personales que conoces de mi"


def test_judge_fail_open_si_el_modelo_revienta(monkeypatch):
    async def _boom(*a, **kw):
        raise RuntimeError("red caída")
    monkeypatch.setattr(asyncio, "to_thread", _boom)
    assert asyncio.run(sg.judge("Ahora vamos a")) == ("incomplete", "")


# ── THE LIVEKIT DETECTOR ─────────────────────────────────────────────────────────────────────────────────────
class _Msg:
    def __init__(self, text, role="user"):
        self.role = role
        self.content = text


class _Ctx:
    def __init__(self, text):
        self.items = [_Msg("hola", "assistant"), _Msg(text, "user")]


def _predict(text, inner=None):
    import asyncio
    from voice.engine.speech.turn.semantic import SemanticTurnDetector
    return asyncio.run(SemanticTurnDetector(inner).predict_end_of_turn(_Ctx(text)))


def test_el_detector_veta_lo_incompleto_y_deja_pasar_lo_completo():
    assert _predict("del software,") < 0.5
    assert _predict("Vale, me gustaría ahora que hagas un") < 0.5
    assert _predict("pon música") > 0.5
    assert _predict("sí, te autorizo a borrar toda la agenda") > 0.5


def test_se_queda_con_la_probabilidad_MAS_BAJA_de_las_dos():
    """It composes with LiveKit's local detector rather than replacing it: whichever of the two says «not yet» wins.
    Our layer knows nothing about prosody; theirs knows nothing about dangling words."""
    class _Inner:
        model = "inner"
        async def unlikely_threshold(self, language=None): return 0.2
        async def supports_language(self, language=None): return True
        async def predict_end_of_turn(self, ctx, *, timeout=None): return 0.05

    assert _predict("pon música", _Inner()) == pytest.approx(0.05), "ignoró el veto del detector interior"
    assert _predict("del software,", _Inner()) <= 0.05, "ignoró su propio veto"


def test_un_detector_interior_roto_no_tumba_el_turno():
    class _Roto:
        model = "roto"
        async def unlikely_threshold(self, language=None): raise RuntimeError("boom")
        async def supports_language(self, language=None): return True
        async def predict_end_of_turn(self, ctx, *, timeout=None): raise RuntimeError("boom")

    assert _predict("pon música", _Roto()) > 0.5


def test_declara_soporte_para_cualquier_idioma():
    """Saying that we do not support a language would ALSO disable the inner detector. If the language is not es/en,
    lexical analysis finds nothing dangling and returns «complete» — the previous behavior."""
    import asyncio
    from voice.engine.speech.turn.semantic import SemanticTurnDetector
    d = SemanticTurnDetector(None)
    assert asyncio.run(d.supports_language("de")) is True
    assert _predict("Ich möchte einen Termin") > 0.5


def test_esta_registrado_como_proveedor():
    from voice.engine.speech.turn import registry
    import voice.engine.speech.turn.semantic  # noqa: F401  (registration occurs on import)
    assert registry.create("semantic") is not None


def test_esta_ENCENDIDO_por_defecto(monkeypatch):
    """El guarda que faltaba y que dejó V2-095 MUERTA al nacer: el detector estaba registrado y `turn_provider`
    valía `disabled`, así que nada lo seleccionaba y la capa léxica no corría en ninguna sesión. Un registro sin
    defecto es una pieza que existe y no está enchufada — el mismo fallo que Susurro leyendo claves inexistentes.

    Se comprueba el DEFECTO, no el valor actual del entorno: sin `ZAELAR_TURN` puesto, la pieza tiene que estar
    activa. Y el ensamblado tiene que devolver un detector, no `None`.
    """
    import importlib
    monkeypatch.delenv("ZAELAR_TURN", raising=False)
    # Reload ONLY `config` (it recalculates the default by reading the environment). Reloading the `turn` package does NOT work:
    # it creates a new, empty `Registry`, because the `@registry.register` decorators live in cached modules that are not re-executed.
    cfg = importlib.reload(importlib.import_module("voice.engine.core.config"))
    assert cfg.SETTINGS.turn_provider == "semantic", (
        f"el defecto de turn_provider es {cfg.SETTINGS.turn_provider!r}: con «disabled» el fin de turno vuelve a "
        f"ser silencio puro y toda V2-095 queda muerta sin que ningún test se entere")

    # Assembly must also return a real detector with that value (not `None`, which the «disabled» branch returns and
    # which the engine translates to `turn_detection="vad"`).
    # `SETTINGS` is a FROZEN dataclass (a field cannot be assigned): the module object is replaced with a copy carrying
    # the value, so the test does not depend on the operator's environment having `ZAELAR_TURN` set.
    import dataclasses
    from voice.engine.speech import turn as turn_mod
    monkeypatch.setattr(turn_mod, "SETTINGS",
                        dataclasses.replace(turn_mod.SETTINGS, turn_provider="semantic"))
    det = turn_mod.build_turn_detection()
    assert det is not None and getattr(det, "provider", "") == "zaelar"


def test_sin_modelo_ONNX_la_capa_lexica_sigue_decidiendo():
    """ONNX cannot load here (the job runs in a THREAD and its `InferenceRunner` requires the main thread), so the
    REAL production path is `inner=None`. That path must decide as well, or the detector would be a wrapper that does nothing."""
    from voice.engine.speech.turn.semantic import SemanticTurnDetector
    det = SemanticTurnDetector(inner=None)

    class _M:
        role = "user"
        def __init__(self, c): self.content = c

    class _Ctx:
        def __init__(self, c): self.items = [_M(c)]

    assert asyncio.run(det.predict_end_of_turn(_Ctx("y ponerlo en la"))) < 0.5      # retiene
    assert asyncio.run(det.predict_end_of_turn(_Ctx("páralo todo."))) > 0.5         # stop command: passes
    assert asyncio.run(det.predict_end_of_turn(_Ctx("pon música"))) > 0.5           # orden corta: pasa


# ── THE MEASUREMENT, as a test ───────────────────────────────────────────────────────────────────────────────
_SESION = [
    "Bueno, si no me equivoco,", "esta es nuestra instalación local, ¿verdad? Cierra todos los", "widgets,",
    "Enséñame ahora mi agenda.", "Vale,", "todos los datos de la agenda", "absolutamente.",
    "Futuro.", "Calendarios, tareas predeterminadas, déjamela vacía por completo.", "¿Me has oído?",
    "Parece que te has quedado tonto.", "En el widget siguen apareciendo cosas.", "Programadas.",
    "No está vacío.", "¿Vale?", "De hecho, tú mismo puedes leer los datos de la agenda",
    "Hay seis cosas ahora mismo puestas.", "Ser", "el día de hoy.", "Y tiene que haber", "cero",
    "¿cómo es posible que el proceso no pueda eliminar todo eso?", "Y el frontend visualizarlo vacío?",
    "En tiempo real.", "Siguen quedando cuatro ítems en", "la agenda.",
    "O los borras todos o no borras ninguno, pero solo borrar alguno, como", "cómo es?", "Posible?",
    "Vacía la agenda por completo.", "Hoy y siempre.", "No quiero ni los históricos,", "todo borrado.",
    "No, no está hecho, no estás comprobando que hagas las cosas.",
    "Vale, pues hazme un favor, lees lo que hay en la agenda.",
    "Lo borras y luego compruebas que lo hayas borrado.", "Seguramente, por error has abierto dos widths",
    "más.", "Con dos navegadores", "que aquí no se tenían que haber abierto para nada.",
    "Aparte de eso, obviamente,", "no estás consiguiendo borrar las cosas.",
    "Ahora ha desaparecido un nuevo ítem", "de la lista de la agenda.", "Pero solo uno.",
    "Sí, te autorizo a borrar toda la agenda.", "No el widget, los datos de la.",
    "Vale, podemos hacer una pequeña cosa,", "Me gustaría sacar el visor de la base de datos", "del",
    "del software,", "y ponerlo en la wiki.", "Puedes mover eso sin grandes",
    "Vale, me gustaría ahora que hagas un", "completa del", "código,", "porque necesitaré dejarle esto",
    "a", "otras personas,", "para que", "para que lo evalúen.", "Entonces, necesito, de alguna manera,",
    "que esté bien hecho, que no quede en código sucio,",
    "que todo esté perfectamente comentado, modularizado,", "Hemos, que el HTML", "esté perfecto,",
    "organizado por componentes,", "con los CSS bien estructurados,", "y tú ya sabes cómo es un proyecto",
    "utilizar una estructura", "de framework y y cómo hacer una auditoría",
    "perfecta a un proyecto así. Yo lo que haría es hacer un súper", "planning de...", "Un un superplanning",
    "de lo que habría que hacer para",
    "dejarlo todo perfecto, obviamente manteniendo el funcionamiento,", "y me gustaría que lo",
    "que prepararas ese ese plan de auditoría, y luego ya", "veremos cómo lo",
    "ejecutamos o cómo lo hacemos.", "Pero yo quiero entregar esto y quiero que se vea superprofesor",
    "que parezca que lo ha hecho un equipo de dos o tres personas,", "con mucha calidad,",
    "y así podemos entregar el", "el proyecto.", "No, esto no era para ti, puedes pararme.",
    "Cancélalo, no tenía, el mensaje no era para ti.", "Cancélalo.",
]


def test_sobre_la_sesion_real_evita_al_menos_un_tercio_de_las_llamadas():
    """The number that justifies all this. It is not an estimate: these are the session transcriptions.
    Measured today: 43 of 89 = 48%. The threshold is set at 1/3 so that fine-tuning the rule does not break the test,
    but a drop below that means the rule has lost its strength."""
    retenidos = [t for t in _SESION if sg.should_hold(t)[0]]
    assert len(retenidos) >= len(_SESION) // 3, (
        f"solo retiene {len(retenidos)}/{len(_SESION)}; el tramo de dictado volvería a costar 22 prompts")


def test_ninguna_frase_terminada_en_punto_con_verbo_se_retiene_por_error():
    """Damage control: of the 89, every item that ends in a period and does NOT end in a function word must pass.
    This is the normal form of a finished request, and holding it would be the costly false positive."""
    import re
    for t in _SESION:
        if re.search(r"[.!?]\s*$", t) and not sg.looks_incomplete(t)[0]:
            assert sg.should_hold(t)[0] is False
