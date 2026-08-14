"""
TURNOS POR SENTIDO (V2-095, 2026-08-14) — el límite del turno deja de ser solo acústico.

El operador dictaba una petición larga y cada pausa para pensar abría un turno que el fragmento siguiente
cancelaba. Sesión b70a45d0, tramo de dictado:

    465s → 626s (161 s):  22 prompts · 18 cancelados · 20 rellenos de espera · CERO respuestas

…con prompts montados sobre «del», «del software,», «a», «para que», «Un un superplanning». En toda la sesión: 89
transcripciones finales, 33 seguidas de cancelación, 53 prompts para 11 respuestas (79% del gasto tirado) y una
escalada a worker lanzada sobre una petición truncada que el operador tuvo que cancelar.

Los casos de este fichero son los 89 fragmentos REALES. El corpus manda sobre cualquier intuición gramatical: la
primera versión de la regla («corta y sin cerrar») retenía TODAS las órdenes cortas del operador —«pon música»,
«abre la agenda»— y se cazó midiendo, no leyendo.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import segmenter as sg


# ── LO QUE NO SE PUEDE RETENER NUNCA ───────────────────────────────────────────────────────────────────────────
# Un falso positivo aquí es peor que el bug original: el operador da una orden y el agente se queda 6 s callado.
# Las órdenes cortas son lo más frecuente que dice, y «sí» es cómo autoriza algo irreversible.
@pytest.mark.parametrize("orden", [
    "abre la agenda", "sube el volumen", "pon música", "cierra eso", "enséñame la agenda",
    "siguiente canción", "vacía la agenda", "ponme el vídeo de Messi", "deja de buscar",
    # «para» a secas es una ORDEN de parar, aunque también sea preposición.
    "para", "para la música", "párala", "cancélalo", "sigue",
    # respuestas y confirmaciones: cómo el operador contesta a una pregunta del agente.
    "sí", "no", "vale", "gracias",
    # LA FRASE DEL INCIDENTE: con esto autorizó al worker. Retenerla habría sido el mismo fallo por el otro lado.
    "sí, te autorizo a borrar toda la agenda",
])
def test_las_ordenes_y_respuestas_nunca_se_retienen(orden):
    hold, why = sg.should_hold(orden)
    assert hold is False, f"«{orden}» se retendría por «{why}» — eso deja al operador esperando por nada"


# ── LOS FRAGMENTOS REALES QUE SÍ IBAN A MEDIAS ────────────────────────────────────────────────────────────────
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
    # El STT pone puntos donde le parece: llevar punto NO significa estar acabada.
    ("No el widget, los datos de la.", "acaba en «la» AUNQUE lleve punto"),
    ("planning de...", "acaba en «de» con puntos suspensivos"),
    # Continuaciones que EMPIEZAN por palabra función.
    ("de framework y y cómo hacer una auditoría", "empieza por «de»"),
])
def test_los_fragmentos_reales_a_medias_se_retienen(frag, motivo):
    hold, why = sg.should_hold(frag)
    assert hold is True, f"«{frag}» pasaría y abriría un turno a medias ({motivo})"
    assert why, "una retención sin motivo es un turno que no llega y nadie sabe por qué"


# ── LO QUE SÍ ES UNA PETICIÓN COMPLETA (de la misma sesión) ───────────────────────────────────────────────────
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


# ── LOS INVARIANTES ────────────────────────────────────────────────────────────────────────────────────────────
def test_el_techo_de_retencion_entrega_siempre():
    """La capa semántica puede RETRASAR un turno, nunca perderlo. Un operador que se corta a mitad («…y ponerlo
    en la») no puede quedarse sin respuesta para siempre por una coma."""
    frag = "y ponerlo en la"
    assert sg.should_hold(frag, held_s=0.0)[0] is True
    assert sg.should_hold(frag, held_s=sg.MAX_HOLD_S + 0.1) == (False, "techo de retención")


def test_fail_open_ante_cualquier_cosa_rara():
    """Retener de más convierte un agente lento en un agente mudo: ante la duda, PASA."""
    for raro in ["", "   ", "…", "!!!", "🙂", None]:
        assert sg.should_hold(raro)[0] is False, repr(raro)


def test_el_modelo_es_OPT_IN(monkeypatch):
    """La capa 2 (modelo) no gasta un token mientras nadie la active. Los cortes observados los cubre la capa
    léxica, y meter una llamada por parcial sin medirlo sería repetir el error de las dos pasadas de 2026-08-02."""
    monkeypatch.delenv("ZAELAR_SEGMENTER_MODEL", raising=False)
    assert sg.model_enabled() is False
    monkeypatch.setenv("ZAELAR_SEGMENTER_MODEL", "algo")
    assert sg.model_enabled() is True


# ── EL DETECTOR DE LIVEKIT ────────────────────────────────────────────────────────────────────────────────────
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
    """Compone con el detector local de LiveKit, no lo sustituye: cualquiera de los dos que diga «aún no» manda.
    Nuestra capa no sabe de prosodia; la suya no sabe de palabras colgadas."""
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
    """Decir que no soportamos un idioma apagaría TAMBIÉN al detector interior. Si el idioma no es es/en, el
    análisis léxico no encuentra nada colgado y devuelve «completo» — el comportamiento de antes."""
    import asyncio
    from voice.engine.speech.turn.semantic import SemanticTurnDetector
    d = SemanticTurnDetector(None)
    assert asyncio.run(d.supports_language("de")) is True
    assert _predict("Ich möchte einen Termin") > 0.5


def test_esta_registrado_como_proveedor():
    from voice.engine.speech.turn import registry
    import voice.engine.speech.turn.semantic  # noqa: F401  (el registro ocurre al importar)
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
    # Se recarga SOLO `config` (recalcula el defecto leyendo el entorno). Recargar el paquete `turn` NO vale: crea un
    # `Registry` nuevo y vacío, porque los `@registry.register` viven en módulos ya cacheados que no se re-ejecutan.
    cfg = importlib.reload(importlib.import_module("voice.engine.core.config"))
    assert cfg.SETTINGS.turn_provider == "semantic", (
        f"el defecto de turn_provider es {cfg.SETTINGS.turn_provider!r}: con «disabled» el fin de turno vuelve a "
        f"ser silencio puro y toda V2-095 queda muerta sin que ningún test se entere")

    # Y el ensamblado tiene que devolver un detector de verdad con ese valor (no `None`, que es lo que devuelve la
    # rama «disabled» y lo que el motor traduce a `turn_detection="vad"`).
    # `SETTINGS` es un dataclass CONGELADO (no se le asigna un campo): se sustituye el objeto del módulo por una
    # copia con el valor puesto, así el test no depende de que el entorno del operador tenga `ZAELAR_TURN` a mano.
    import dataclasses
    from voice.engine.speech import turn as turn_mod
    monkeypatch.setattr(turn_mod, "SETTINGS",
                        dataclasses.replace(turn_mod.SETTINGS, turn_provider="semantic"))
    det = turn_mod.build_turn_detection()
    assert det is not None and getattr(det, "provider", "") == "zaelar"


def test_sin_modelo_ONNX_la_capa_lexica_sigue_decidiendo():
    """El ONNX no puede cargar aquí (el job corre en un HILO y su `InferenceRunner` exige el principal), así que el
    camino REAL de producción es `inner=None`. Ese camino tiene que decidir igual, o el detector sería un envoltorio
    que no hace nada."""
    from voice.engine.speech.turn.semantic import SemanticTurnDetector
    det = SemanticTurnDetector(inner=None)

    class _M:
        role = "user"
        def __init__(self, c): self.content = c

    class _Ctx:
        def __init__(self, c): self.items = [_M(c)]

    assert asyncio.run(det.predict_end_of_turn(_Ctx("y ponerlo en la"))) < 0.5      # retiene
    assert asyncio.run(det.predict_end_of_turn(_Ctx("páralo todo."))) > 0.5         # orden de parar: pasa
    assert asyncio.run(det.predict_end_of_turn(_Ctx("pon música"))) > 0.5           # orden corta: pasa


# ── LA MEDICIÓN, como test ────────────────────────────────────────────────────────────────────────────────────
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
    """El número que justifica todo esto. No es una estimación: son las transcripciones de la sesión.
    Medido hoy: 43 de 89 = 48%. El listón se pone en 1/3 para que un ajuste fino de la regla no rompa el test,
    pero una caída por debajo de eso significa que la regla se ha quedado sin fuerza."""
    retenidos = [t for t in _SESION if sg.should_hold(t)[0]]
    assert len(retenidos) >= len(_SESION) // 3, (
        f"solo retiene {len(retenidos)}/{len(_SESION)}; el tramo de dictado volvería a costar 22 prompts")


def test_ninguna_frase_terminada_en_punto_con_verbo_se_retiene_por_error():
    """Control de daños: de los 89, las que acaban en punto y NO acaban en palabra función tienen que pasar todas.
    Es la forma normal de una petición acabada, y retenerla sería el falso positivo caro."""
    import re
    for t in _SESION:
        if re.search(r"[.!?]\s*$", t) and not sg.looks_incomplete(t)[0]:
            assert sg.should_hold(t)[0] is False
