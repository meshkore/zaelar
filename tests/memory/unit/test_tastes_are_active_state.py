"""V2-498 — TASTES are active state: their own line, outside the ranking they always lose.

Operator rule (2026-08-29): *“tastes are part of the active state — they are not historical data or things
that happened in the past; they have to be there.”*

MEASURED against its live memory before touching anything: the passive block had TWO lines —a working rule and a
system `[RESET]`— and not a single taste, with 12 stored `pref` pills (Ferrari ×7, guitar ×2). They are not lost
when written: they lose the RANKING (0.3–0.494 against a 0.446 cutoff dominated by 0.99 pills).

Everything goes through `compose_state`, which is what actually composes the prompt — a case that called `tastes()`
manually would likewise pass with the state line removed (V2-199).
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
    """The exact defect: the pill is written correctly but does not arrive because it competes for a slot and loses."""
    for i in range(8):
        memwriter.insert_memory(f"Hecho pesado número {i} sobre su vida.",
                                level="long", kind="fact", weight=0.99, importance=0.95)
    memwriter.insert_memory("Le interesa la guitarra.", level="long", kind="pref",
                            weight=0.05, importance=0.5)      # the REAL weight of its guitar pill
    b = _bloque()
    assert "guitarra" in b, b


def test_SIN_gustos_no_hay_linea(fresh_db):
    # Sensitivity: a line that always appears stops being read, bloating every turn for no reason.
    memwriter.insert_memory("Vive en Soria.", level="long", kind="fact", weight=0.9)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" not in b, b


def test_un_gusto_NO_se_pinta_dos_veces(fresh_db):
    # It has its own line, so it leaves the outgoing profile: two appearances in the same prompt are pure cost.
    memwriter.insert_memory("Le interesa el buceo.", level="long", kind="pref", weight=0.99, importance=0.95)
    b = _bloque()
    assert b.count("Le interesa el buceo.") == 1, b


def test_los_ECOS_no_se_colapsan_por_PARECIDO_pero_el_texto_repetido_si(fresh_db):
    """Merging echoes is the work of `semantic_dedup` (it preserves the best and invalidates the rest), not of the
    rendering layer. And a lexical dedup would NOT work here either: measured in the operator's memory, its seven
    Ferrari echoes are in TWO languages ('He is interested in Ferrari and sports cars' vs 'Le interesan los Ferrari'),
    so they share no content words and no lexical threshold brings them together. What is removed is the
    IDENTICAL text, which requires no guessing."""
    memwriter.insert_memory("He is interested in Ferrari and sports cars.", level="long", kind="pref", weight=0.5)
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref", weight=0.4)
    b = _bloque()
    assert "He is interested in Ferrari" in b and "Le interesan los Ferrari" in b, b


def test_una_pildora_de_FONDO_no_es_un_gusto(fresh_db):
    # Same exclusion as the passive block: namespaced (`:`) slots belong to widgets/cluster, not the operator.
    memwriter.insert_memory("Tiempo en Soria ahora: 14,5 °C.", level="long", kind="pref",
                            slot="meteo-soria:weather:soria", weight=0.99, importance=0.9)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" not in b, b


def test_lo_que_dice_un_PEER_no_es_un_gusto_suyo(fresh_db):
    memapi.ingest_message("cluster", "zalo", "Le encantan los coches deportivos.", trust="untrusted", durable=True)
    b = _bloque()
    assert "GUSTOS Y PREFERENCIAS" not in b, b


def test_un_hecho_CRITICO_no_se_duplica_en_la_linea_de_gustos(fresh_db):
    # Critical items have their own line (V2-491) and are a different class: repeating them here uses a slot and dilutes
    # the line that exists so an allergy is not forgotten.
    mid = memwriter.insert_memory("Es alérgico a los frutos secos.", level="long", kind="pref", weight=0.99)
    memdb.get_db().execute("UPDATE memories SET meta=json_object('critical','health') WHERE id=?", (mid,))
    b = _bloque()
    assert "CRÍTICO" in b, b
    assert "GUSTOS Y PREFERENCIAS" not in b, b
