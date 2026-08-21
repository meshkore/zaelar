"""V2-227 ámbito C — el CABLEADO de la hoja como superficie del progreso en vivo.

El contrato de PANTALLA ya estaba en verde (`tests/browser/e2e/results/render_process_tab.py`, 6/6): ese fichero
monta `widget.js` en una página en blanco y le pasa a mano tres cargas útiles, así que prueba que la hoja SE
COMPORTA cuando le llegan los datos. Lo que no puede probar —y es justo lo que faltaba para que el operador viera
algo— es que alguien PRODUZCA esos datos: `view_data()` no devolvía `progress` en absoluto, y nadie abría la hoja
al encargar. Un contrato cumplido en un test y ausente en el producto.

Lo que se fija aquí, en el orden en que ocurre un encargo:

  1. Con nada en marcha la hoja no afirma trabajo (`alive: False`), que es distinto de callarse.
  2. Al ENCARGAR se abre — y se abre VACÍA y sin la pestaña que el operador eligió para el encargo anterior.
  3. Está viva ANTES de la primera fase: ese hueco de segundos es la pantalla en blanco que el operador pidió
     quitar, así que es la parte que más importa.
  4. Las fases del registro VIVO llegan a la hoja en orden, sin guardarse en ella.
  5. Al TERMINAR el loader para y la historia se queda — persistida, porque el informe también lo está.

Y las dos direcciones en cada sitio donde el arreglo podría pasarse de frenada: una superficie que NO es la hoja
no pinta aquí, y un encargo que llega con otro trabajando no le borra a ése lo que ya había entregado.
"""
import time

import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Store AISLADO y registro de sesiones AISLADO.

    Lo segundo no es simetría: `sheet_progress()` lee `dispatch._SESSIONS`, que es estado de PROCESO — sin
    vaciarlo, un test que deja una sesión dentro le pinta un «Trabajando…» al siguiente y el fallo no señala a
    nada suyo. Y lo primero ya costó caro en este mismo directorio: la primera versión de los tests de la hoja
    limpiaba el store REAL y le borró al operador el informe que tenía en pantalla.
    """
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _live(tid: str, goal: str, surface: str = "lista", phases=()) -> SessionRecord:
    """Una sesión VIVA en el registro, sellada por la misma puerta que la sella en producción."""
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, surface)
    rec.status = "running"
    dispatch._SESSIONS[tid] = rec
    for ph in phases:
        dispatch.session_phase(tid, ph)
    return rec


# ── 1) sin nada en marcha, la hoja no afirma trabajo ─────────────────────────────────────────────────────────

def test_sin_encargo_vivo_la_hoja_no_dice_que_trabaja():
    assert sheet.view_data()["progress"] == {"alive": False, "phases": []}


# ── 2) al ENCARGAR se abre la hoja ───────────────────────────────────────────────────────────────────────────

def test_encargar_abre_SU_hoja_y_la_anterior_no_se_toca(monkeypatch):
    """V2-259 — antes esto se llamaba «abre la hoja VACÍA»: la hoja era única, así que estrenarla significaba
    BORRAR la búsqueda anterior, que es literalmente el «error de borrar búsquedas» que el operador pidió quitar.
    Ahora un encargo abre la SUYA (`results::<task_id>`) y la de antes sigue entera donde estaba. La propiedad no
    se ha relajado: se ha vuelto más fuerte, y por eso se comprueban las dos hojas."""
    shown = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda k, l, **kw: shown.append((k, l, kw.get("extra", {}).get("id"))))
    sheet.apply_action("present", {"title": "Coches en Levante",
                                   "items": [{"title": "de la búsqueda ANTERIOR"}]})
    sheet.apply_action("tab", {"tab": "sources"})       # …y el operador mirando otra pestaña

    rec = SessionRecord(task_id="t1", goal="Busca hoteles de 4 estrellas en Sevilla", kind="web")
    surfaces.set_once(rec, "lista")
    dispatch._sheet_open(rec)

    assert ("widget", "show", "results::t1") in shown, (
        "la hoja tiene que ABRIRSE al encargar, no al entregar — y con el id de SU instancia, que es lo que hace "
        "que el canvas pinte una tarjeta nueva en vez de reusar la de la búsqueda anterior")
    nueva = sheet.view_data("t1")
    assert nueva["items"] == [], "la hoja del encargo nuevo empieza en blanco"
    assert nueva["title"] == "Busca hoteles de 4 estrellas en Sevilla"
    assert nueva.get("tab") is None, "la pestaña elegida era del encargo ANTERIOR; arrastrarla tapa el proceso"

    vieja = sheet.view_data()
    assert [i["title"] for i in vieja["items"]] == ["de la búsqueda ANTERIOR"], (
        "estrenar dejó de significar borrar: la búsqueda anterior sigue en SU hoja")
    assert vieja["title"] == "Coches en Levante"


def test_dos_encargos_a_la_vez_son_dos_hojas_y_ninguno_pisa_al_otro():
    """La petición del operador, palabra por palabra: «si hacemos 2 búsquedas a la vez, se abrirán 2 browsers y 2
    widgets de results, cada uno con su correlation_id». Antes esto era un compromiso —la hoja era única, así que
    el segundo encargo la reutilizaba sin vaciarla para no borrarle al primero— y el precio era que el operador
    veía los resultados de una búsqueda bajo el título de la otra."""
    _live("t1", "Busca hoteles en Sevilla")
    sheet.apply_action("present", {"sheet": "t1", "title": "Hoteles en Sevilla",
                                   "items": [{"title": "Bécquer"}]})

    rec2 = SessionRecord(task_id="t2", goal="Busca restaurantes en Madrid", kind="web")
    surfaces.set_once(rec2, "lista")
    dispatch._sheet_open(rec2)

    a, b = sheet.view_data("t1"), sheet.view_data("t2")
    assert [i["title"] for i in a["items"]] == ["Bécquer"], "al primero no se le toca nada"
    assert a["title"] == "Hoteles en Sevilla"
    assert b["items"] == [] and b["title"] == "Busca restaurantes en Madrid"
    assert sheet.sheet_key("t1") != sheet.sheet_key("t2"), "dos encargos, dos claves"


# ── 3) viva ANTES de la primera fase ─────────────────────────────────────────────────────────────────────────

def test_la_hoja_esta_viva_antes_de_la_primera_fase():
    """El hueco entre encargar y la primera fase son segundos de pantalla en blanco — exactamente lo que el
    operador pidió quitar. `alive` es «hay un encargo en marcha», no «ha dicho algo»."""
    _live("t1", "Busca hoteles en Sevilla")
    assert sheet.view_data()["progress"] == {"alive": True, "phases": []}


# ── 4) las fases del registro vivo llegan a la hoja ──────────────────────────────────────────────────────────

def test_las_fases_llegan_en_orden_desde_el_registro_vivo():
    _live("t1", "Busca hoteles en Sevilla",
          phases=["entrando en booking.com…", "aplicando filtro 4 estrellas…", "lanzando la búsqueda…"])
    pr = sheet.view_data()["progress"]
    assert pr["alive"] is True
    assert pr["phases"] == ["entrando en booking.com…", "aplicando filtro 4 estrellas…",
                            "lanzando la búsqueda…"]


def test_una_superficie_que_no_es_la_hoja_no_pinta_aqui():
    """Sensibilidad. Un encargo que se cuenta por voz no tiene por qué abrir ni mover la hoja: si `alive` se
    encendiera con cualquier worker, la hoja diría «Trabajando…» sobre trabajo que no va a aterrizar en ella."""
    for surface in ("voz", "silenciosa", "widget"):
        dispatch._SESSIONS.clear()
        _live("t1", "Ponme música", surface=surface, phases=["buscando la canción…"])
        assert sheet.view_data()["progress"] == {"alive": False, "phases": []}, surface


def test_el_progreso_es_DERIVADO_y_no_se_guarda_en_la_hoja():
    """Guardarlo sería tener el mismo estado en dos sitios, y el que se queda en pantalla siempre es el rancio —
    un «Trabajando…» congelado sobre un worker que ya no existe."""
    _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    sheet.apply_action("present", {"title": "Hoteles", "items": [{"title": "Bécquer"}]})
    guardado = store.load("results", {})
    assert "progress" not in guardado
    assert "counts" not in guardado


def test_la_hoja_SIN_instancia_sigue_entrelazando_los_encargos_vivos():
    """V2-259 le da a cada encargo su hoja, y ahí `sheet_progress(task_id)` cuenta solo lo suyo. Pero la hoja SIN
    instancia sigue existiendo —es la que el operador abre a mano, sin encargo detrás— y para ELLA el entrelazado
    en orden de tiempo sigue siendo la respuesta honesta: quedarse con un encargo escondería que hay otro."""
    a = _live("t1", "Busca hoteles en Sevilla")
    b = _live("t2", "Busca restaurantes en Madrid")
    a.phases.append({"t": 100.0, "s": "entrando en booking.com…"})
    b.phases.append({"t": 101.0, "s": "entrando en thefork.es…"})
    a.phases.append({"t": 102.0, "s": "aplicando filtro 4 estrellas…"})
    assert sheet.view_data()["progress"]["phases"] == [
        "entrando en booking.com…", "entrando en thefork.es…", "aplicando filtro 4 estrellas…"]


# ── 5) al TERMINAR ───────────────────────────────────────────────────────────────────────────────────────────

def test_al_terminar_el_loader_para_y_la_historia_se_queda():
    rec = _live("t1", "Busca hoteles en Sevilla",
                phases=["entrando en booking.com…", "lanzando la búsqueda…"])
    sheet.apply_action("present", {"title": "Hoteles en Sevilla", "items": [{"title": "Bécquer"}]})

    rec.status = "done"
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)

    pr = sheet.view_data("t1")["progress"]
    assert pr["alive"] is False, "nadie más avisa del final: sin esta escritura la tarjeta sigue «Trabajando…»"
    assert pr["phases"] == ["entrando en booking.com…", "lanzando la búsqueda…"]


def test_la_historia_sobrevive_al_informe_porque_se_PERSISTE():
    """La hoja sobrevive a un reinicio; un informe cuya explicación de cómo se llegó a él ha desaparecido cuenta
    la mitad de lo que pasó."""
    rec = _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)
    assert store.load(sheet.sheet_key("t1"), {}).get("process") == ["entrando en booking.com…"]
    assert sheet.view_data("t1")["progress"]["phases"] == ["entrando en booking.com…"]


def test_un_encargo_que_no_dijo_una_sola_fase_no_inventa_historia():
    rec = _live("t1", "Busca hoteles en Sevilla")
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)
    assert sheet.view_data("t1")["progress"] == {"alive": False, "phases": []}
    assert "process" not in store.load(sheet.sheet_key("t1"), {})


def test_el_encargo_siguiente_estrena_su_historia_y_la_del_anterior_SIGUE():
    """Un relato viejo debajo de un encargo nuevo es peor que ninguno: explica un resultado que ya no está. Con
    hojas separadas eso se cumple sin borrar nada — y la comprobación tiene que mirar LAS DOS, porque después de
    V2-259 preguntarle a la hoja pelada da vacío siempre y el caso pasaría sin probar nada."""
    rec = _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)

    rec2 = SessionRecord(task_id="t2", goal="Busca restaurantes en Madrid", kind="web")
    surfaces.set_once(rec2, "lista")
    dispatch._sheet_open(rec2)
    assert sheet.view_data("t2")["progress"]["phases"] == [], "el encargo nuevo no hereda el relato del viejo"
    assert sheet.view_data("t1")["progress"]["phases"] == ["entrando en booking.com…"], (
        "…y el viejo conserva el suyo: estrenar dejó de significar borrar")


# ── el clic del operador en «Proceso» tiene que PERSISTIR ────────────────────────────────────────────────────

def test_el_operador_puede_quedarse_en_la_pestana_de_proceso():
    """`process` faltaba de `_TABS`, así que el clic volvía `ok:false` y no se guardaba. La pestaña se pintaba
    igual (el widget conmuta en el acto) y al siguiente refresco de datos —que durante un encargo vivo llega con
    CADA fase— el derivado se lo llevaba de vuelta a Resultados."""
    sheet.apply_action("present", {"title": "Hoteles", "items": [{"title": "Bécquer"}]})
    assert sheet.apply_action("tab", {"tab": "process"})["ok"] is True
    assert sheet.view_data().get("tab") == "process"
    assert sheet.apply_action("tab", {"tab": "proceso"})["tab"] == "process"


def test_una_pestana_inventada_sigue_rechazandose():
    assert sheet.apply_action("tab", {"tab": "inventada"})["ok"] is False


# ── fail-soft: la hoja se monta también sin dispatcher ───────────────────────────────────────────────────────

def test_sin_dispatcher_la_hoja_ensena_lo_guardado_y_no_revienta(monkeypatch):
    """Un test de la hoja sola, o el widget montado fuera del motor: eso es `alive: False` con su historia, que
    es exactamente lo que se ve — no un error."""
    rec = _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)

    def _boom():
        raise RuntimeError("sin dispatcher")

    monkeypatch.setattr(dispatch, "sheet_progress", _boom)
    assert sheet.view_data("t1")["progress"] == {"alive": False, "phases": ["entrando en booking.com…"]}


# ── guarda de ORDEN: la hoja lee el registro vivo, así que el final se escribe DESPUÉS del pop ───────────────

def test_el_cierre_de_la_hoja_va_despues_de_sacar_la_sesion_del_registro():
    """Al revés, `sheet_progress()` seguiría viendo la sesión y la hoja se guardaría diciendo que trabaja. Es una
    guarda de ORDEN sobre el código: reordenar dos líneas no falla con ruido, deja el loader girando para siempre."""
    import inspect
    src = inspect.getsource(dispatch._run_session)
    pop = src.rindex('_SESSIONS.pop(key, None)')
    cierre = src.rindex('_sheet_close(rec)')
    assert pop < cierre, "el `_sheet_close` tiene que ir DESPUÉS de sacar la sesión del registro"
