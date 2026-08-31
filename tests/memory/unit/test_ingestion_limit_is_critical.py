"""V2-499 — an INGESTION limitation stated without a category word is also a critical fact.

The medical-safety detector matched the CATEGORY («allergic», «celiac», «intolerant»), which is how people
say it half the time. The other half says what they CANNOT DO: «cannot eat gluten». That sentence contains no
catalog word, so it was not marked `critical`, did not reach the ⚠️ CRITICAL line, and remained competing for a
ranking slot — the failure that V2-490 measured with macaroni offered to a celiac.

Authorized by the operator on 2026-08-29, ACCEPTING false positives. This file leaves them MEASURED and named,
rather than leaving them as a vague note: what is accepted is written down, because here a false positive uses
a slot in a capped line and can displace a pacemaker (V2-491).
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
    """It is the only qualification, and the one that makes the rest acceptable: a sentence that NAMES a moment
    speaks about that moment, not the person. Without this, «today I cannot eat with you» uses a slot in a capped line."""
    colados = [t for t in MOMENTOS if memwriter._is_critical_health(t)]
    assert not colados, colados


def test_lo_que_no_va_de_ingerir_sigue_FUERA():
    # Sensitivity: without this, a detector broadened to «cannot …» would turn half the conversation into
    # critical facts, and the line would stop meaning anything.
    colados = [t for t in NADA_QUE_VER if memwriter._is_critical_health(t)]
    assert not colados, colados


def test_las_categorias_de_SIEMPRE_no_se_tocan():
    for t in ("Es alérgico a los frutos secos.", "Es celíaco.", "Lleva un marcapasos.",
              "Es diabética.", "She is allergic to penicillin."):
        assert memwriter._is_critical_health(t), t


def test_el_FALSO_POSITIVO_aceptado_queda_MEDIDO_y_con_nombre():
    """What the operator accepted, stated as a number rather than as «some false positives».

    Without a temporal marker, satiety cannot be distinguished from a restriction without UNDERSTANDING the
    sentence, and in case of doubt this line exists to err on the side of excess — a dish that is not offered
    costs one question; a forgotten allergy costs something else. If someone narrows the detector, this case
    will show them what is changing."""
    aceptados = ["No puedo comer más.", "No puedo comer nada de eso, me sienta fatal."]
    assert all(memwriter._is_critical_health(t) for t in aceptados)
    # and the total cost across this file's corpus: only those, and no others
    universo = LIMITACIONES_REALES + MOMENTOS + NADA_QUE_VER
    assert sum(memwriter._is_critical_health(t) for t in universo) == len(LIMITACIONES_REALES)


def test_la_marca_llega_a_la_PILDORA_no_solo_al_predicado(tmp_path, monkeypatch):
    """The real path: the guard lives in the writer, the only point through which ALL writes pass. A case
    covering the predicate alone would pass just the same with the guard disconnected from the insert (V2-199)."""
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
