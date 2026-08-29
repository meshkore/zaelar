#
# test_critical_health.py — auditoría de memoria 2026-07-14 (hallazgo de SEGURIDAD del corpus v3):
#   una ALERGIA/intolerancia es un hecho médico ADITIVO y CRÍTICO. Dos fallos cerrados:
#   (A) el CORAZÓN la mis-asignaba al slot SINGULAR operator.diet → una DIETA declarada después la BORRABA
#       (supersede por slot). Guard del writer: alergia + slot de identidad → se retira el slot (queda aditiva),
#       pinned + importancia alta, meta.critical='health'.
#   (B) bajo densidad, la alergia se enterraba fuera del cap de salient_long. compose_state la surface SIEMPRE en
#       una línea CRÍTICO propia (critical_facts), independiente del ranking.
# Determinista: sin red (embeddings hash) ni LLM. Ejecutar:
#   .venv/bin/pytest tests/memory/unit/test_critical_health.py -q
#
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEM_PROCESSOR", "0")
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


def _alive(substr):
    return memdb.get_db().query_one(
        "SELECT count(*) c FROM memories WHERE valid=1 AND lower(text) LIKE ?", (f"%{substr}%",))["c"]


# ── FIX A · una dieta NO borra una alergia ─────────────────────────────────────────────────────────────────

def test_allergy_never_takes_singular_diet_slot(fresh_db):
    mid = writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    row = memdb.get_db().query_one("SELECT slot, pinned, meta FROM memories WHERE id=?", (mid,))
    assert row["slot"] is None, "la alergia NO debe conservar un slot singular (la borraría un dato posterior)"
    assert row["pinned"] == 1
    assert "critical" in (row["meta"] or ""), "la alergia debe marcarse meta.critical='health'"


def test_diet_statement_does_not_erase_allergy(fresh_db):
    writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    writer.insert_memory("Es vegetariana.", level="long", kind="pref", slot="operator.diet")   # dieta REAL
    assert _alive("penicilina") == 1, "la dieta declarada NO puede borrar la alergia crítica"
    assert _alive("vegetariana") == 1, "la dieta sí se guarda"


def test_multiple_allergies_coexist(fresh_db):
    writer.insert_memory("Soy alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    writer.insert_memory("Soy alérgica a los frutos secos.", level="long", kind="fact", slot="diet")
    writer.insert_memory("Soy intolerante a la lactosa.", level="long", kind="fact")
    assert _alive("penicilina") == 1 and _alive("frutos secos") == 1 and _alive("lactosa") == 1


def test_real_diet_supersede_still_works(fresh_db):
    # regresión inversa: una DIETA (no alergia) con slot SÍ debe superseder normalmente (no rompemos el mecanismo)
    writer.insert_memory("Es vegetariana.", level="long", kind="pref", slot="operator.diet")
    writer.insert_memory("Ahora es vegana.", level="long", kind="pref", slot="operator.diet")
    assert _alive("vegetariana") == 0 and _alive("vegana") == 1, "una dieta sí supersede a otra dieta"


# ── FIX B · la alergia se surface SIEMPRE, incluso bajo densidad ───────────────────────────────────────────

def test_critical_fact_surfaces_under_density(fresh_db):
    memapi.set_state({"operator_name": "Amaia", "location": "Logroño"})
    writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    for j in range(130):   # densidad: entierra la alergia bajo ruido de mayor recencia
        writer.insert_memory(f"Mensaje {j} sobre la escalada y el manuscrito.",
                             level="long", kind="msg", importance=0.6, weight=0.7)
    block, _op, _st = memapi.compose_state(mission_fallback="m")
    low = block.lower()
    assert "penicilina" in low, "la alergia debe surfacearse en el estado aunque esté enterrada bajo densidad"
    assert "crítico" in low, "debe ir en la línea CRÍTICO propia"
    # y NO se duplica en el bloque de perfil saliente
    assert not any("penicilina" in (m["text"] or "").lower() for m in memapi.salient_long(limit=8)), \
        "los críticos van SOLO en su línea, no también en salient_long (sin dup)"


def test_critical_facts_reader(fresh_db):
    writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref")
    writer.insert_memory("Lleva marcapasos.", level="long", kind="fact")
    facts = memapi.critical_facts()
    joined = " ".join(facts).lower()
    assert "penicilina" in joined and "marcapasos" in joined


# ── V2-491 · una frase deja DOS píldoras críticas, y el corte se aplicaba a PÍLDORAS ────────────────────────
#
# La destilada por el CORAZÓN y la literal de la red de salud (`ingest.py`) son textos DISTINTOS, así que el
# dedup por cadena exacta no las colapsaba y cada hecho ocupaba dos de las seis plazas. Medido: con cuatro
# hechos críticos distintos, el cuarto DESAPARECE de la línea más prominente del prompt.

def _par(destilada: str, cruda: str) -> None:
    """Las dos píldoras que una sola frase del operador deja hoy: la del CORAZÓN (con `meta.raw`) y la que
    guarda la red de seguridad de salud (el enunciado literal, sin `raw`)."""
    writer.insert_memory(destilada, level="long", kind="fact",
                         meta={"source": "voice", "path": "llm", "raw": cruda[:120]})
    writer.insert_memory(cruda, level="long", kind="fact", meta={"source": "voice", "path": "health-net"})


def test_la_copia_de_la_red_no_expulsa_a_otro_hecho_critico(fresh_db):
    from memory import _prompt
    _par("El operador es celíaco y no puede comer nada con gluten.",
         "Oye, apúntate una cosa mía: soy celíaco, no puedo tomar nada con gluten.")
    _par("Es alérgico a los frutos secos.", "Soy alérgico a los frutos secos, ojo.")
    _par("Es diabético y se pincha insulina.", "Soy diabético.")
    _par("Lleva marcapasos desde 2019.", "Llevo marcapasos, que lo sepas.")
    crit = " · ".join(_prompt.critical_facts(limit=6)).lower()
    for tema in ("celíac", "frutos secos", "diabét", "marcapasos"):
        assert tema in crit, f"«{tema}» expulsado de la línea crítica por una copia"


def test_sobrevive_la_DESTILADA_y_no_el_enunciado_crudo(fresh_db):
    from memory import _prompt
    _par("El operador es celíaco y no puede comer nada con gluten.",
         "Oye, apúntate una cosa mía: soy celíaco, no puedo tomar nada con gluten.")
    crit = _prompt.critical_facts(limit=6)
    assert len(crit) == 1
    assert crit[0].startswith("El operador es celíaco")


def test_DOS_ALERGIAS_DISTINTAS_siguen_conviviendo(fresh_db):
    """La dirección contraria, y es la que importa: aquí un falso positivo BORRA una restricción médica.
    Deduplicar por PARECIDO se midió y se descartó — el par que sí debe fundirse puntúa POR DEBAJO de éstos."""
    from memory import _prompt
    for t in ("Es alérgico a los frutos secos.", "Es alérgico al marisco.", "Es alérgico a la penicilina."):
        writer.insert_memory(t, level="long", kind="fact")
    crit = " · ".join(_prompt.critical_facts(limit=6)).lower()
    assert "frutos secos" in crit and "marisco" in crit and "penicilina" in crit


def test_una_pildora_que_declara_su_origen_NUNCA_se_retira(fresh_db):
    """Solo se retira la COPIA — la que no dice de dónde viene. Si se retirara la destilada, el hecho se
    quedaría en el prompt con las palabras del operador en vez de con el dato limpio, o peor: sin ninguna."""
    from memory import _prompt
    writer.insert_memory("Es celíaco.", level="long", kind="fact",
                         meta={"source": "voice", "path": "llm", "raw": "Es celíaco."})
    crit = _prompt.critical_facts(limit=6)
    assert crit == ["Es celíaco."]


def test_un_enunciado_MAS_LARGO_que_el_recorte_sigue_reconociendose(fresh_db):
    """`meta.raw` viaja recortado a 120 caracteres, así que la copia se reconoce por PREFIJO. Sin eso, toda
    frase larga del operador volvería a ocupar dos plazas."""
    from memory import _prompt
    larga = ("Oye, apúntate una cosa importante sobre mí que conviene que tengas siempre presente: "
             "soy celíaco y no puedo tomar absolutamente nada que lleve gluten, ni una miga.")
    assert len(larga) > 120
    _par("El operador es celíaco y no puede comer nada con gluten.", larga)
    assert _prompt.critical_facts(limit=6) == ["El operador es celíaco y no puede comer nada con gluten."]
