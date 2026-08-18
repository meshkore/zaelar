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


# ── proactividad y multi-intención (casos de uso del 2026-08-18) ─────────────────────────────────────────
def test_the_cron_line_makes_a_spoken_reminder_insufficient():
    """V2-121 · `remember-and-remind-deadline`. Decir «te lo recuerdo» no programa nada; el prompt tiene que
    decirlo con esas letras, porque la corrida midió tres turnos afirmando que estaba programado con cero
    mecanismo detrás."""
    line = prompt._cron_line()
    assert "[[cron.create]]" in line
    assert "EN ESE TURNO" in line
    assert "YYYY-MM-DD HH:MM" in line       # el formato que hace EXPRESABLE un aviso de una sola vez
    assert "add_meeting" in line            # apuntar y avisar son dos cosas, y se piden las dos


def test_live_state_lists_the_next_seven_days_with_their_dates():
    """Traducir «el miércoles» a una fecha absoluta debe ser una LECTURA, no aritmética de cabeza: un aviso mal
    fechado no se nota hasta el día que no suena."""
    import time as _t
    live = prompt.live_state()
    assert "Próximos días" in live
    for i in (1, 3, 7):
        assert _t.strftime("%Y-%m-%d", _t.localtime(_t.time() + i * 86400)) in live


def test_the_one_thing_per_turn_rule_is_about_actions_not_answers(fresh_db):
    """V2-120 · `quick-fact-opening-hours`. «UNA cosa por turno» se leía como permiso para contestar media
    pregunta: se pidieron la hora Y el precio en la misma frase y volvió una sola mitad, dos rondas seguidas."""
    system, _ = prompt.build_flash_system()
    assert "UNA ACCIÓN por turno" in system
    assert "las contestas LAS DOS en ese turno" in system


def test_a_background_task_with_no_reported_step_says_so(monkeypatch):
    """V2-133 — el patrón transversal: 8 de 12 casos NARRARON una fase que no existía («está en la fase de
    login» de un gimnasio cuyo nombre aún no tenía). El bloque pedía «di el PASO concreto» a secas, y sin paso
    reportado el modelo rellenaba el hueco. Ahora la ausencia se dice, y narrar se prohíbe con ejemplos."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "renovar la cuota del gimnasio", "secs": 63, "phase": "",
         "pct": -1, "done": 0, "total": 0, "note": ""}])
    live = prompt.live_state()
    assert "SIN paso reportado aún" in live.split("Si el operador pregunta")[0]
    assert "JAMÁS te inventes en qué punto va" in live


def test_a_background_task_that_DID_report_a_step_still_shows_it(monkeypatch):
    """La marca es para el hueco, no para toda tarea: una fase real se sigue diciendo tal cual."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "buscar monitores", "secs": 63, "phase": "conduciendo el navegador",
         "pct": -1, "done": 0, "total": 0, "note": ""}])
    # La marca se busca en la LISTA de tareas, no en el párrafo de instrucciones (que la cita para explicarla).
    tareas = prompt.live_state().split("Si el operador pregunta")[0]
    assert "conduciendo el navegador" in tareas
    assert "SIN paso reportado aún" not in tareas


def test_the_prompt_forbids_narrating_work_that_is_not_running(fresh_db):
    """La otra mitad de V2-133: sin NINGUNA tarea de fondo no hay nada corriendo, y la respuesta correcta
    cuando falta un dato o no se puede es decirlo — el criterio de esos casos la premia explícitamente."""
    system, _ = prompt.build_flash_system()
    assert "NO NARRES trabajo que no está pasando" in system
    assert "PÍDELO" in system


# ── un dato del operador que NO está en su ESTADO (V2-127, 2026-08-18) ───────────────────────────────────
def test_the_missing_location_is_NAMED_not_left_blank(tmp_path, monkeypatch):
    """`reorder-prescription__es` acabó preguntando por «la zona exacta de Soria» — una ciudad que el operador
    no había nombrado. Verificado con BD fresca: `state.read()["location"] is None`, o sea que el estado no
    autorizaba nombrar ninguna. El hueco silencioso se rellenó, igual que la fase de worker sin reportar."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "vacia.db"))
    from memory import db as memdb
    memdb.reset_db(); memdb.get_db()
    try:
        live = prompt.live_state()
        assert "NO SABES dónde vive el operador" in live
        assert "no supongas ninguna ciudad" in live
    finally:
        memdb.reset_db()


def test_a_known_location_costs_nothing(fresh_db):
    """La línea es para la AUSENCIA: con ubicación en el estado ni aparece (el prompt no engorda por esto)."""
    from memory import api as memory
    memory.set_state({"location": "Soria, Castilla y León"})
    assert "NO SABES dónde vive el operador" not in prompt.live_state()


def test_web_search_no_longer_orders_using_a_city_that_may_not_exist(fresh_db):
    """La cláusula mandaba usar «la ciudad ACTUAL del operador» sin contemplar que su estado no la tenga."""
    system, _ = prompt.build_flash_system()
    assert "si su estado NO dice dónde vive, no te la inventes" in system


def test_a_concrete_fact_about_the_operator_comes_from_state_or_is_asked(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "o está en tu ESTADO o NO LO SABES" in system
