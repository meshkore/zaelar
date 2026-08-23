"""V2-259 — dos búsquedas son dos hojas, y estrenar deja de significar borrar.

LO QUE PIDIÓ EL OPERADOR (2026-08-21, literal): «si tenemos un widget de results abierto, búsqueda terminada, y
lanzamos otra, se abre un widget nuevo. Con esta regla no cometeremos errores de borrar búsquedas.»

Y el borrado que temía ESTABA EN EL CÓDIGO, con su comentario: `dispatch._sheet_open()` llamaba a
`begin_task(fresh=True)`, que estrenaba la hoja —título nuevo, sin resultados ni historial— en cuanto llegaba el
encargo siguiente. La hoja era única (`store.load(WIDGET_ID)`, una sola clave), así que la disyuntiva era: o
estrenar y borrarle lo entregado a quien siguiera escribiendo, o reutilizar y enseñar los resultados de la
búsqueda anterior bajo el título de ésta. Ninguna de las dos es buena; las dos estaban medidas.

LA CLAVE ES EL ENCARGO, NO EL NAVEGADOR. Es la continuación exacta de V2-257: la tarjeta del navegador MUESTRA
(N tarjetas) y la hoja GUARDA los hallazgos vengan del navegador que vengan. Así que dos navegadores del mismo
encargo siguen cayendo en la misma hoja, y dos encargos son dos hojas.

Lo que se fija aquí es la frontera y sus dos filos: que dos encargos no se pisen, y que quien ESCRIBE sepa en
cuál — un escritor sin hoja escribe en la de nadie mientras el operador mira la suya, que es un fallo mudo.
"""
from pathlib import Path

import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.results import data as sheet, intake

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _encargo(tid: str, goal: str, nav: str = "") -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    rec.sheet = dispatch.sheet_id_for(tid)      # lo sella `_sheet_open` en producción; aquí igual
    rec.status = "running"
    if nav:
        rec.nav_task = nav
    dispatch._SESSIONS[tid] = rec
    return rec


# ── 1) la clave ──────────────────────────────────────────────────────────────────────────────────────────────

def test_the_bare_sheet_keeps_its_key_byte_for_byte():
    """La hoja de hoy tiene datos en disco bajo la clave vieja. Cambiarla dejaría DOS linajes vivos — la forma
    exacta de V2-242, donde `weather:soria` y `meteo-soria:weather:soria` convivieron los dos con `valid=1`."""
    assert sheet.sheet_key("") == "results"
    assert sheet.sheet_key("t1") == "results--t1"
    assert sheet.instance_id("t1") == "results::t1", "el canvas usa «::»; el disco no lo admite"


def test_a_hostile_correlation_id_cannot_escape_its_directory():
    assert sheet.sheet_key("../../etc") == "results--etc"
    assert sheet.sheet_key("a b/c:d") == "results--abcd"
    assert sheet.sheet_key("   ") == "results", "un id en blanco no es una instancia"


# ── 2) dos encargos no se pisan ──────────────────────────────────────────────────────────────────────────────

def test_two_errands_do_not_overwrite_each_other():
    _encargo("t1", "Busca fontaneros en Madrid")
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})

    rec2 = _encargo("t2", "Busca un coche de segunda mano")
    dispatch._sheet_open(rec2)

    assert [i["title"] for i in sheet.view_data(dispatch.sheet_id_for("t1"))["items"]] == ["Relatores"]
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["items"] == []
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["title"] == "Fontaneros"
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["title"] == "Busca un coche de segunda mano"


def test_the_next_errand_no_longer_wipes_the_finished_one():
    """El caso EXACTO del operador: búsqueda terminada, llega otra. Antes esto borraba la primera."""
    rec1 = _encargo("t1", "Busca fontaneros en Madrid")
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})
    rec1.status = "done"
    dispatch._SESSIONS.pop("t1")
    dispatch._sheet_close(rec1)

    dispatch._sheet_open(_encargo("t2", "Busca un coche"))
    assert [i["title"] for i in sheet.view_data(dispatch.sheet_id_for("t1"))["items"]] == ["Relatores"], (
        "la búsqueda TERMINADA se borraba al llegar la siguiente — es el «error de borrar búsquedas» que el "
        "operador pidió quitar")


def test_each_card_tells_ITS_own_story():
    """Con la hoja única las fases se entrelazaban en orden de tiempo, y era la respuesta honesta. Con hojas
    separadas, dos cajas contando la misma historia mezclada es mentir con más superficie."""
    a, b = _encargo("t1", "hoteles"), _encargo("t2", "restaurantes")
    a.phases.append({"t": 100.0, "s": "entrando en booking.com…"})
    b.phases.append({"t": 101.0, "s": "entrando en thefork.es…"})
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["progress"]["phases"] == ["entrando en booking.com…"]
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["progress"]["phases"] == ["entrando en thefork.es…"]
    assert sheet.view_data()["progress"]["phases"] == ["entrando en booking.com…", "entrando en thefork.es…"], (
        "la hoja SIN encargo detrás —la que el operador abre a mano— sigue mereciendo el relato completo")


# ── 3) quien ESCRIBE sabe en cuál ────────────────────────────────────────────────────────────────────────────

def test_two_browsers_of_the_SAME_errand_land_in_the_SAME_sheet():
    """La frontera de V2-257 sigue en pie: la hoja es del ENCARGO, no del navegador."""
    _encargo("t1", "Busca fontaneros", nav="nav-A")
    assert dispatch.sheet_for_nav_task("nav-A") == dispatch.sheet_id_for("t1")
    intake.push([{"title": "Relatores", "tel": "910"}], sheet=dispatch.sheet_for_nav_task("nav-A"))
    _encargo("t1b", "otro navegador del mismo encargo")     # ruido: no cuelga de nav-A
    dispatch._SESSIONS["t1"].nav_task = "nav-A"
    intake.push([{"title": "GASFONCLIMA", "tel": "911"}], sheet=dispatch.sheet_for_nav_task("nav-A"))
    assert [i["title"] for i in sheet.view_data(dispatch.sheet_id_for("t1"))["items"]] == ["Relatores", "GASFONCLIMA"]


def test_a_browser_with_no_errand_behind_it_writes_the_bare_sheet():
    """El operador conduciendo el navegador a mano: no hay encargo, así que la hoja de siempre es la correcta."""
    assert dispatch.sheet_for_nav_task("suelto") == ""
    intake.push([{"title": "algo"}], sheet=dispatch.sheet_for_nav_task("suelto"))
    assert [i["title"] for i in sheet.view_data()["items"]] == ["algo"]


@pytest.mark.parametrize("rel", ["widgets/navegador/act_api.py", "widgets/navegador/owner.py",
                                 "nucleo/dispatch.py"])
def test_no_writer_pushes_without_naming_its_sheet(rel):
    """El guardarraíl que hace falta aquí y no en V2-257: entonces sobraba con que llamaran a la puerta; ahora
    tienen que decir a QUÉ hoja. Un `push` sin `sheet=` no falla — escribe en la caja que no mira nadie."""
    src = (ENGINE / rel).read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines()):
        if "intake.push(" in line and "def " not in line:
            bloque = "\n".join(src.splitlines()[i:i + 3])
            assert "sheet=" in bloque, f"{rel}:{i + 1} entrega a la hoja sin decir a cuál"


def test_the_worker_bridge_resolves_the_sheet_so_the_worker_never_has_to():
    """El prompt del worker dice «entrega en la hoja `results`» (V2-257) y con instancias ese nombre pelado deja
    de ser una dirección. Lo resuelve el PUENTE: un worker no debería conocer ids de instancia."""
    src = (ENGINE / "nucleo/worker_api.py").read_text(encoding="utf-8")
    assert 'wid == "results"' in src and '"sheet"' in src, (
        "sin esto el worker escribe en la hoja de nadie mientras el operador mira la de su encargo")


# ── 4) el cerebro ve TODAS las hojas ─────────────────────────────────────────────────────────────────────────

def test_the_brain_sees_every_open_sheet_and_says_which_is_which():
    """Leer solo una no avisa de nada: el turno contestaría con seguridad sobre la búsqueda que no era. «La
    número dos» con dos hojas en pantalla son dos cosas distintas."""
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t2"), "title": "Coches", "items": [{"title": "Ibiza 2019"}]})

    refs = sheet.ref_index()
    assert {r["id"] for r in refs} == {"Relatores", "Ibiza 2019"}
    assert all("de «" in r["hint"] for r in refs), "cada referencia dice de qué hoja es"

    dig = sheet.prompt_digest()
    assert "Fontaneros" in dig and "Coches" in dig
    assert "Relatores" in dig and "Ibiza 2019" in dig

    solo = sheet.prompt_digest(dispatch.sheet_id_for("t1"))
    assert "Relatores" in solo and "Ibiza 2019" not in solo, "y se puede pedir UNA cuando se sabe cuál"


def test_with_one_sheet_the_digest_says_nothing_about_sheets():
    """Sin dos búsquedas no hay ambigüedad que desambiguar, y meter la cabecera igualmente sería ruido en cada
    prompt de cada turno."""
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})
    assert "── HOJA" not in sheet.prompt_digest()
    assert all("de «" not in r["hint"] for r in sheet.ref_index())


# ── 5) la hoja persiste, así que N hojas necesitan techo ─────────────────────────────────────────────────────

def test_the_sheets_do_not_grow_without_a_ceiling():
    """La hoja PERSISTE a propósito (un informe sobrevive a un reinicio, V2-233). N instancias persistidas crecen
    sin fin, y un recorte silencioso es peor que uno contado."""
    for n in range(sheet._MAX_SHEETS + 3):
        sheet.apply_action("present", {"sheet": f"t{n}", "title": f"Búsqueda {n}",
                                       "items": [{"title": f"r{n}"}]})
    assert len([s for s in sheet.sheets() if s]) == sheet._MAX_SHEETS + 3
    tiradas = sheet.prune_sheets()
    quedan = [s for s in sheet.sheets() if s]
    assert tiradas == 3 and len(quedan) == sheet._MAX_SHEETS
    assert f"t{sheet._MAX_SHEETS + 2}" in quedan, "se conservan las MÁS RECIENTES"
    assert "t0" not in quedan


def test_pruning_never_touches_the_bare_sheet():
    """No es de ningún encargo: no le toca a nadie borrarla."""
    sheet.apply_action("present", {"title": "la de siempre", "items": [{"title": "x"}]})
    for n in range(sheet._MAX_SHEETS + 2):
        sheet.apply_action("present", {"sheet": f"t{n}", "items": [{"title": f"r{n}"}]})
    sheet.prune_sheets()
    assert [i["title"] for i in sheet.view_data()["items"]] == ["x"]


# ── 6) el id de hoja tiene que sobrevivir a un REINICIO ──────────────────────────────────────────────────────

def test_the_sheet_id_does_not_repeat_across_restarts():
    """Lo cazó el arnés sobre esta misma iniciativa recién construida, y es el defecto que V2-259 existe para
    quitar, reintroducido por la puerta de atrás: `escalate._seq` arranca en 0 en CADA proceso, así que los
    `task_id` se repiten entre reinicios. Con la hoja nombrada por el `task_id` a secas, el primer encargo de un
    arranque nuevo caía en `results--1` —la hoja de la sesión anterior— y `begin_task(fresh=True)` la ESTRENA,
    o sea la borra. Un informe que el operador quería conservar, destruido en silencio.

    Así que el id lleva un sello del PROCESO. La hoja se guarda en disco y sobrevive al reinicio (V2-233): su
    nombre tiene que sobrevivir igual de bien.
    """
    assert dispatch.sheet_id_for("1") != "1", "el id de hoja no puede ser el task_id a pelo"
    assert dispatch.sheet_id_for("1").endswith("-1")
    # F5 (2026-08-23): el sello ya no es un `_BOOT` privado de este módulo — lo emite el DUEÑO de la identidad
    # de proceso (`nucleo/runtime_ids.py`), que es lo que impide que nazca el siguiente contador suelto. Lo que
    # este caso afirma no cambia: el id de hoja compone un sello que es distinto en cada arranque.
    from nucleo import runtime_ids
    assert runtime_ids.boot_id() and runtime_ids.boot_id() in dispatch.sheet_id_for("1")
    # dos «arranques» distintos, el mismo task_id, dos hojas
    otro = "otroboot"
    assert sheet.sheet_key(dispatch.sheet_id_for("1")) != sheet.sheet_key(f"{otro}-1")


def test_the_sheet_is_stamped_ONCE_like_the_surface():
    """Mismo criterio que `surfaces.set_once`: cambiar de hoja a mitad no es corregir, es mover lo que el
    operador ya está mirando."""
    rec = _encargo("t1", "Busca fontaneros")
    primero = dispatch.sheet_of(rec)
    dispatch._sheet_open(rec)
    assert dispatch.sheet_of(rec) == primero


def test_an_errand_with_no_sheet_writes_the_bare_one():
    """`sheet_of` NO reconstruye el id desde el task_id: un encargo cuya hoja nunca se abrió no tiene hoja, y
    fabricarle una haría que un encargo de voz —sin superficie— escribiera en una caja que nadie abrió."""
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id="t9", goal="dime la hora", kind="generic")
    assert dispatch.sheet_of(rec) == ""
