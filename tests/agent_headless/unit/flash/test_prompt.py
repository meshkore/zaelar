"""Tests de nucleo/flash/prompt.py (V2-004 · T67) — el prompt del FlashBrain compone MEMORIA propia (state+query)."""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import memory_cache, prompt


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
    memory_cache.reset()   # el caché de sesión (T114) es global; empieza limpio por test
    yield
    memory_cache.reset()
    memdb.reset_db()


def test_prompt_injects_operator_from_state(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "treatment": "directo, sin narrar"})
    system, _ids = prompt.build_flash_system()
    assert "Ricart" in system
    assert "directo, sin narrar" in system
    # V2-027: el ESTADO compuesto trae la MISIÓN (QUIÉN ERES) + el situacional (QUIÉN TIENES DELANTE)
    assert "QUIÉN ERES" in system
    assert "QUIÉN TIENES DELANTE" in system
    # el lock de idioma y la capa TERSA de recursos siempre están
    assert "IDIOMA" in system
    assert "widget_data" in system and "web_search" in system


def test_prompt_recall_pulls_relevant_memory(fresh_db):
    memapi.write_now("el coche del operador está en el taller hasta el viernes", kind="fact", level="long")
    system, ids = prompt.build_flash_system(recall_query="¿dónde está mi coche?")
    assert "taller" in system
    assert ids            # devolvió ids de memoria usados (para refuerzo/registro)


def test_prompt_empty_memory_no_crash(fresh_db):
    system, ids = prompt.build_flash_system(recall_query="hola")
    assert isinstance(system, str) and "IDIOMA" in system
    assert ids == []      # sin recuerdos → sin ids


def test_directive_block(fresh_db):
    system, _ = prompt.build_flash_system(directive="tutéame y sé breve")
    assert "tutéame y sé breve" in system
    assert "INSTRUCCIÓN DE ESTILO ACTIVA" in system


@pytest.mark.parametrize("text", [
    "where is my car",
    "where's my car?",
    "¿dónde está mi coche?",
    "do you remember what I told you?",
    "¿te acuerdas de mi cita del dentista?",
    "what did I tell you about the meeting",
    "recuérdame qué dije de la reunión",   # 'que dije de'
])
def test_needs_recall_true(text):
    assert prompt.needs_recall(text) is True


@pytest.mark.parametrize("text", [
    "hola, buenos días",
    "¿qué tal estás?",
    "let's talk about my weekend plans",
    "show me the clock please",
    "cuéntame un chiste",
    "¿me pones el tiempo en pantalla?",
])
def test_needs_recall_false(text):
    assert prompt.needs_recall(text) is False


@pytest.mark.parametrize("lang,needle", [("es", "corto o largo plazo"), ("en", "short/long-term memory")])
def test_prompt_never_exposes_memory_layers(fresh_db, monkeypatch, lang, needle):
    """El FlashBrain NUNCA debe hablarle al operador de sus capas internas ('memoria de corto/largo plazo').
    Regla dura tras el bug en vivo 2026-07-10; en V2-027 vive en la MISIÓN sembrada (langs), no en un `_FAST_RULES`
    estático — así el prompt ensamblado la sigue llevando.

    El IDIOMA se fija, y se comprueban LOS DOS: la prohibición vive en la misión, que es POR IDIOMA, así que
    heredar el idioma ambiente hacía que este test pasara en la máquina del operador (castellano en su config) y
    fallara en cualquier otra y en CI — sin que el producto tuviera nada malo. Y comprobar solo el castellano
    dejaba sin guardia justo el idioma con el que ARRANCA el producto desde 2026-08-09: si la prohibición se
    cayera del inglés, nadie se enteraría."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    system, _ = prompt.build_flash_system()
    assert needle in system                  # aparece SOLO en la prohibición de la misión
