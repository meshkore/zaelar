"""V2-498 — los GUSTOS son estado activo: línea propia, fuera del ranking que siempre pierden.

Norma del operador (2026-08-29): *«los gustos forman parte del estado activo — no son datos históricos ni cosas
que hayan sucedido en el pasado, sino que tienen que estar ahí»*.

MEDIDO sobre su memoria viva antes de tocar nada: el bloque pasivo tenía DOS líneas —una regla de trabajo y un
`[RESET]` del sistema— y ni un gusto, con 12 píldoras `pref` guardadas (Ferrari ×7, guitarra ×2). No se pierden
al escribirse: pierden el RANKING (0,3-0,494 contra un corte de 0,446 dominado por píldoras de 0,99).

Todo entra por `compose_state`, que es lo que compone el prompt de verdad — un caso que llamara a `tastes()` a
mano pasaría igual con la línea del estado borrada (V2-199).
"""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
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


def _bloque() -> str:
    return memapi.compose_state(mission_fallback="m")[0]


def test_un_gusto_llega_al_bloque_pasivo(fresh_db):
    memwriter.insert_memory("Le interesan los Ferrari y los coches deportivos.",
                            level="long", kind="pref", weight=0.4, importance=0.55)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" in b, b
    assert "Ferrari" in b, b


def test_llega_AUNQUE_PIERDA_el_ranking_del_perfil(fresh_db):
    """El defecto exacto: la píldora se escribe bien y no llega porque compite por una plaza y la pierde."""
    for i in range(8):
        memwriter.insert_memory(f"Hecho pesado número {i} sobre su vida.",
                                level="long", kind="fact", weight=0.99, importance=0.95)
    memwriter.insert_memory("Le interesa la guitarra.", level="long", kind="pref",
                            weight=0.05, importance=0.5)      # el peso REAL de su píldora de guitarra
    b = _bloque()
    assert "guitarra" in b, b


def test_SIN_gustos_no_hay_linea(fresh_db):
    # Sensibilidad: una línea que sale siempre deja de leerse, y engorda todos los turnos por nada.
    memwriter.insert_memory("Vive en Soria.", level="long", kind="fact", weight=0.9)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" not in b, b


def test_un_gusto_NO_se_pinta_dos_veces(fresh_db):
    # Tiene línea propia, así que sale del perfil saliente: dos apariciones en el mismo prompt es coste puro.
    memwriter.insert_memory("Le interesa el buceo.", level="long", kind="pref", weight=0.99, importance=0.95)
    b = _bloque()
    assert b.count("Le interesa el buceo.") == 1, b


def test_los_ECOS_no_se_colapsan_por_PARECIDO_pero_el_texto_repetido_si(fresh_db):
    """Fundir ecos es trabajo de `semantic_dedup` (conserva la mejor e invalida el resto), no de la capa que
    pinta. Y aquí un dedup léxico NO serviría igualmente: medido en la memoria del operador, sus siete ecos de
    Ferrari están en DOS idiomas ('He is interested in Ferrari and sports cars' vs 'Le interesan los Ferrari'),
    así que no comparten palabras de contenido y ningún umbral léxico los junta. Lo que sí se retira es el texto
    IDÉNTICO, que no exige adivinar nada."""
    memwriter.insert_memory("He is interested in Ferrari and sports cars.", level="long", kind="pref", weight=0.5)
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref", weight=0.4)
    b = _bloque()
    assert "He is interested in Ferrari" in b and "Le interesan los Ferrari" in b, b


def test_una_pildora_de_FONDO_no_es_un_gusto(fresh_db):
    # Misma exclusión que el pasivo: los slots namespaced (`:`) son de widgets/cluster, no del operador.
    memwriter.insert_memory("Tiempo en Soria ahora: 14,5 °C.", level="long", kind="pref",
                            slot="meteo-soria:weather:soria", weight=0.99, importance=0.9)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" not in b, b


def test_lo_que_dice_un_PEER_no_es_un_gusto_suyo(fresh_db):
    memapi.ingest_message("cluster", "zalo", "Le encantan los coches deportivos.", trust="untrusted", durable=True)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" not in b, b


def test_un_hecho_CRITICO_no_se_duplica_en_la_linea_de_gustos(fresh_db):
    # Los críticos tienen su propia línea (V2-491) y son de otra clase: repetirlos aquí gasta plaza y diluye
    # la línea que existe para que no se olvide una alergia.
    mid = memwriter.insert_memory("Es alérgico a los frutos secos.", level="long", kind="pref", weight=0.99)
    memdb.get_db().execute("UPDATE memories SET meta=json_object('critical','health') WHERE id=?", (mid,))
    b = _bloque()
    assert "CRÍTICO" in b, b
    assert "GUSTOS Y PREFERENCIAS" not in b, b
