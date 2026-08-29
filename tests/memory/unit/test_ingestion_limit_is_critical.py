"""V2-499 — una limitación de INGESTIÓN dicha sin palabra de categoría también es un hecho crítico.

El detector de seguridad médica casaba la CATEGORÍA («alérgico», «celíaco», «intolerante»), que es como la gente
lo dice la mitad de las veces. La otra mitad dice lo que NO PUEDE HACER: «no puede comer gluten». Esa frase no
contiene ninguna palabra del catálogo, así que no se marcaba `critical`, no llegaba a la línea ⚠️ CRÍTICO y
quedaba compitiendo por una plaza del ranking — el fallo que V2-490 midió con macarrones ofrecidos a un celíaco.

Autorizado por el operador el 2026-08-29 ACEPTANDO los falsos positivos. Este fichero los deja MEDIDOS y por su
nombre, en vez de dejarlos como una nota vaga: lo que se acepta se escribe, porque aquí un falso positivo gasta
una plaza de una línea con cap y puede expulsar un marcapasos (V2-491).
"""
from memory import writer as memwriter


LIMITACIONES_REALES = [
    "No puede comer gluten.",
    "No puedo tomar lactosa.",
    "No puede beber alcohol por la medicación.",
    "No debe comer marisco.",
    "He can't eat gluten.",
    "She cannot drink alcohol.",
    "I must not take ibuprofen.",
    "No puedo comer frutos secos.",
]

MOMENTOS = [
    "Hoy no puedo comer contigo.",
    "Ahora no puedo tomar nada, acabo de desayunar.",
    "Esta noche no puedo cenar con ellos.",
    "I can't eat right now.",
    "Tonight I can't drink, conduzco yo.",
]

NADA_QUE_VER = [
    "Le interesan los Ferrari y los coches deportivos.",
    "Vive en Soria.",
    "Mañana tiene cita con el dentista.",
    "Quiere aprender a tocar la guitarra.",
    "Me he quedado sin cuota en el proveedor.",
    "No puede venir a la reunión del jueves.",
    "No puedo pagar tanto por un monitor.",
]


def test_una_limitacion_de_ingestion_ES_critica():
    fallan = [t for t in LIMITACIONES_REALES if not memwriter._is_critical_health(t)]
    assert not fallan, fallan


def test_una_restriccion_de_UN_MOMENTO_no_lo_es():
    """Es la única acotación, y la que hace aceptable el resto: una frase que NOMBRA un momento habla de ese
    momento, no de la persona. Sin esto, «hoy no puedo comer contigo» gasta una plaza de una línea con cap."""
    colados = [t for t in MOMENTOS if memwriter._is_critical_health(t)]
    assert not colados, colados


def test_lo_que_no_va_de_ingerir_sigue_FUERA():
    # Sensibilidad: sin esto, un detector que se ensanchara a «no puede …» convertiría media conversación en
    # hechos críticos y la línea dejaría de significar nada.
    colados = [t for t in NADA_QUE_VER if memwriter._is_critical_health(t)]
    assert not colados, colados


def test_las_categorias_de_SIEMPRE_no_se_tocan():
    for t in ("Es alérgico a los frutos secos.", "Es celíaco.", "Lleva un marcapasos.",
              "Es diabética.", "She is allergic to penicillin."):
        assert memwriter._is_critical_health(t), t


def test_el_FALSO_POSITIVO_aceptado_queda_MEDIDO_y_con_nombre():
    """Lo que el operador aceptó, dicho como número y no como «algunos falsos positivos».

    Sin marca temporal no se puede distinguir una saciedad de una restricción sin ENTENDER la frase, y ante la
    duda esta línea existe para pecar de más — un plato que no se ofrece cuesta una pregunta, una alergia
    olvidada cuesta otra cosa. Si alguien estrecha el detector, este caso le dirá qué está cambiando."""
    aceptados = ["No puedo comer más.", "No puedo comer nada de eso, me sienta fatal."]
    assert all(memwriter._is_critical_health(t) for t in aceptados)
    # y el precio total sobre el corpus de este fichero: solo esos, ninguno más
    universo = LIMITACIONES_REALES + MOMENTOS + NADA_QUE_VER
    assert sum(memwriter._is_critical_health(t) for t in universo) == len(LIMITACIONES_REALES)


def test_la_marca_llega_a_la_PILDORA_no_solo_al_predicado(tmp_path, monkeypatch):
    """Por el camino real: el guard vive en el writer, el único punto por el que pasa TODA escritura. Un caso
    sobre el predicado a secas pasaría igual con el guard desconectado del insert (V2-199)."""
    import json
    from memory import db as memdb
    from memory import embeddings as mememb
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    try:
        mid = memwriter.insert_memory("No puede comer gluten.", level="long", kind="fact")
        row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
        assert json.loads(row["meta"] or "{}").get("critical") == "health"
    finally:
        memdb.reset_db()
        mememb.reset()
