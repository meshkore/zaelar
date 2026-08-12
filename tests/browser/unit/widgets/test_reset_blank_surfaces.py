"""
UN RESET DEJA LAS SUPERFICIES EN BLANCO — pero no borra el registro del operador.

Fallo REAL (2026-08-12, reporte del operador). Apretó Reset «para que se pare todo y podamos empezar de cero»,
pidió una búsqueda NUEVA de veleros, y al abrirse la hoja de resultados le salió ENTERA la búsqueda anterior —los
ferrys a Ibiza del día 10— mientras el worker de la nueva seguía trabajando. El reset cerraba las tarjetas pero no
tocaba sus DATOS: el contenido viejo seguía en `widgets/_data/<id>/state.json` esperando a que alguien abriera la
tarjeta. Un widget que enseña el trabajo de antes como si fuera el de ahora engaña igual que un agente caído
pintado en azul.

Las dos mitades que hay que sostener a la vez, y por eso está todo en el mismo fichero:
  · lo DERIVADO se vacía (resultados, informes, gráficas, la lista de mensajes) — es reproducible;
  · lo que es REGISTRO del operador NO (la agenda: sus proyectos, tareas y citas reales), y las credenciales,
    conexiones y perfiles de navegador tampoco — es lo que el diálogo del reset le promete.
"""
import json
import os

import pytest

from widgets import store


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Aísla `widgets/_data/` — estos tests BORRAN estado de widgets; jamás contra los datos reales del operador."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    yield tmp_path
    store._last_hash.clear()


def _seed(wid: str, data: dict) -> None:
    store.save(wid, data)


def _read(wid: str) -> dict:
    p = os.path.join(store.data_dir(wid), "state.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ── 1. lo derivado se va ──────────────────────────────────────────────────────────────────────────────────────
def test_the_previous_search_does_not_survive_a_reset(data_dir):
    """El caso exacto del incidente: la hoja de los ferrys no puede reaparecer en la búsqueda siguiente."""
    from widgets import reset as wreset
    _seed("results", {"title": "Ferry a Ibiza · Ida lun 17 ago", "items": [{"title": "Dénia ↔ Ibiza · Baleària"}]})
    out = wreset.blank_all()
    assert "results" in out["blanked"]
    body = _read("results")
    assert not body.get("items"), "la hoja de resultados tiene que quedar vacía"
    assert "Ibiza" not in json.dumps(body, ensure_ascii=False)


def test_a_widget_without_a_data_module_is_blanked_too(data_dir):
    """Los widgets que el operador se ha hecho (o los que ya no existen y dejaron datos) también se vacían: si no,
    el único que quedaría limpio sería el que alguien se acordó de instrumentar."""
    from widgets import reset as wreset
    _seed("no-existe-xyz", {"lo": "que sea", "items": [1, 2, 3]})
    out = wreset.blank_all()
    assert "no-existe-xyz" in out["blanked"]
    assert _read("no-existe-xyz") == {}


def test_blanking_does_not_leave_the_next_save_stuck(data_dir):
    """`store.save` tiene un anti-flood por hash: si se toca el fichero por fuera sin olvidar la huella, el
    siguiente guardado IDÉNTICO se salta y el widget se queda vacío en pantalla con datos que nunca se escribieron."""
    from widgets import reset as wreset
    payload = {"title": "Veleros", "items": [{"title": "Bavaria 50"}]}
    _seed("results", payload)
    wreset.blank_all()
    store.save("results", payload)                     # el worker vuelve a publicar exactamente lo mismo
    assert _read("results").get("items"), "el guardado posterior tiene que llegar al disco"


# ── 2. lo que es del operador se queda ────────────────────────────────────────────────────────────────────────
def test_the_operators_own_record_is_not_wiped(data_dir):
    """La agenda declara `data.durable` en su manifest: son citas y proyectos REALES, no la salida de un trabajo.
    Borrarlos sería pérdida de datos — del orden de borrar la memoria, que exige marcar su casilla."""
    from widgets import reset as wreset
    assert wreset.is_durable("agenda") is True, "el manifest de la agenda tiene que declararlo"
    _seed("agenda", {"meetings": [{"title": "ITV del coche", "date": "2026-08-20"}], "projects": ["Zaelar"]})
    out = wreset.blank_all()
    assert "agenda" in out["kept"] and "agenda" not in out["blanked"]
    assert _read("agenda")["meetings"][0]["title"] == "ITV del coche"


def test_the_default_is_to_blank_so_the_exception_has_to_be_declared(data_dir):
    """Sin declaración → se vacía. Es lo que pidió el operador («todos los widgets de resultados, de
    visualizaciones, etc. se tienen que inicializar en blanco») y deja la excepción explícita y revisable."""
    from widgets import reset as wreset
    assert wreset.is_durable("results") is False
    assert wreset.is_durable("mensajeria") is False


def test_messages_go_but_the_connection_stays(data_dir):
    """El reset promete NO tocar credenciales ni conexiones. Un vaciado a lo bruto dejaría las tres plataformas en
    `off` → parecería que el reset te ha desconectado de WhatsApp con la cuenta todavía enlazada."""
    from widgets import reset as wreset
    _seed("mensajeria", {"platforms": {"whatsapp": {"status": "linked", "qr": None},
                                       "telegram": {"status": "off", "qr": None},
                                       "email": {"status": "linked", "qr": None}},
                         "items": [{"id": "m1", "text": "hola"}, {"id": "m2", "text": "qué tal"}],
                         "pending_read": ["m1"]})
    wreset.blank_all()
    body = _read("mensajeria")
    assert body["items"] == [] and body["pending_read"] == []
    assert body["platforms"]["whatsapp"]["status"] == "linked", "la conexión NO es contenido"
    assert body["platforms"]["email"]["status"] == "linked"


def test_the_browser_profile_and_media_survive(data_dir):
    """Lo más caro de perder: `widgets/_data/navegador/profile/` guarda las sesiones que el operador abrió A MANO
    (Wallapop, Google…). Se vacía `state.json`, NUNCA la carpeta — que es lo que hace `store.delete`, pensado para
    cuando el widget MUERE."""
    from widgets import reset as wreset
    _seed("navegador", {"mode": "page", "url": "https://wallapop.com", "title": "Wallapop"})
    prof = os.path.join(store.data_dir("navegador"), "profile")
    os.makedirs(prof, exist_ok=True)
    with open(os.path.join(prof, "Cookies"), "w", encoding="utf-8") as f:
        f.write("sesion-del-operador")
    shot = os.path.join(store.data_dir("navegador"), "shot.png")
    with open(shot, "wb") as f:
        f.write(b"PNG")

    wreset.blank_all()
    with open(os.path.join(prof, "Cookies"), encoding="utf-8") as f:
        assert f.read() == "sesion-del-operador", "un reset que te desloguea de todo no es un reset"
    assert os.path.exists(shot)


def test_nothing_is_created_for_a_widget_that_had_no_data(data_dir):
    from widgets import reset as wreset
    out = wreset.blank_all()
    assert out == {"blanked": [], "kept": []}
    assert not os.listdir(str(data_dir))


# ── 3. el ESTADO que describe todo eso ────────────────────────────────────────────────────────────────────────
def test_the_reset_clears_the_state_that_describes_widgets_and_workers():
    """«El estado tiene que limpiarse, al menos el estado que depende de los widgets, de los brainworkers.» Sin
    esto el cerebro arrancaba la prueba nueva leyendo widgets abiertos que ya no están y un MRU que apunta a la
    prueba anterior — y decidía sobre un mundo desmontado."""
    import inspect

    from nucleo import reset as nreset
    src = inspect.getsource(nreset.reset_all)
    for key in ("open_widgets", "recent_widgets", "rails"):
        assert f'"{key}": []' in src, f"el reset no vacía `{key}`"
    assert "canvas_layout" in src, "el escritorio guardado en el server también tiene que irse"
    assert "blank_all()" in src, "el reset tiene que dejar las superficies en blanco"


# ── 4. la hoja se llena MIENTRAS se trabaja (la otra mitad de la queja) ───────────────────────────────────────
def test_the_worker_is_told_to_fill_the_sheet_while_it_works():
    """Una investigación tarda 5-15 min y el brief solo pedía entregar AL FINAL: el operador se quedaba mirando una
    hoja vacía —o la de la búsqueda anterior— sin saber si pasaba algo, y sin poder corregir el rumbo a tiempo."""
    from nucleo import research
    brief = {"goal": "veleros de 49 pies de segunda mano", "min_candidates": 40, "n_final": 3,
             "hard": ["velero", "segunda mano"], "soft": ["ubicación"]}
    text = research.to_prompt_block(brief)
    low = text.lower()
    assert "append" in low and "present" in low
    assert "provisional" in low, "lo no verificado tiene que ir marcado COMO provisional"
    assert "final" in low, "y el cierre reemplaza lo provisional por la selección definitiva"


def test_the_sheet_documents_the_live_contract_for_whoever_reads_it():
    """El worker aprende el contrato leyendo el manifest (`widget_cli read results`): si la convención no está ahí,
    no existe."""
    with open("widgets/results/manifest.json", encoding="utf-8") as f:
        man = json.load(f)
    assert "append" in (man.get("actions") or {})
    assert "MIENTRAS SE TRABAJA" in man["usage"]


# ── VACIAR UN WIDGET NO PUEDE SER SILENCIOSO (2026-08-10) ─────────────────────────────────────────────────────
# Punto ciego encontrado en carne propia: a otra sesión se le vació la hoja de resultados DOS VECES en mitad de una
# prueba (la causa fue un fixture de test que llamaba al reset real), y no había forma de saberlo — porque el
# camino genérico de vaciado borra el `state.json` a mano y `store.save()` es el ÚNICO punto que anuncia «este
# widget ha cambiado». Sin evento no hay fila en el registro, y sin señal el canvas sigue enseñando datos que en
# disco ya no existen. Parecía un fallo de persistencia del widget: se fue un buen rato buscando una avería
# inexistente. Un camino que MUTA datos sin anunciarlo es un agujero en la observabilidad, no un detalle.
def _emitted(monkeypatch):
    """Captura lo que se emite al observador, sin tocar el registro real."""
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit",
                        lambda kind, label, text="", role="", extra=None: seen.append((kind, label, extra or {})))
    return seen


def test_wiping_a_widget_leaves_an_audit_row_and_repaints_the_canvas(data_dir, monkeypatch):
    from widgets import reset as wreset

    (data_dir / "hoja").mkdir()
    (data_dir / "hoja" / "state.json").write_text(json.dumps({"items": [1, 2, 3]}), encoding="utf-8")
    seen = _emitted(monkeypatch)

    assert wreset._blank_one("hoja") == "wiped"
    labels = [(k, l) for k, l, _ in seen]
    assert ("widget", "blank") in labels, "sin fila de auditoría, vaciar un widget es indistinguible de perder datos"
    assert ("widget", "data") in labels, (
        "sin la señal que escucha el canvas, la tarjeta abierta sigue mostrando lo que ya no está en disco")
    blank = next(e for k, l, e in seen if l == "blank")
    assert blank["id"] == "hoja" and blank["how"] == "wiped"


def test_the_widgets_own_blank_also_leaves_the_audit_row_without_duplicating_the_signal(data_dir, monkeypatch):
    """El camino que pasa por `store.save()` ya avisa al canvas él solo; lo que le faltaba es DECIR que fue un
    reset — un `data` a secas no distingue «lo vaciaron» de «lo actualizaron»."""
    from widgets import reset as wreset

    (data_dir / "msg").mkdir()
    (data_dir / "msg" / "state.json").write_text(json.dumps({"items": [1]}), encoding="utf-8")
    monkeypatch.setattr(wreset, "_data_module", lambda wid: type("M", (), {"blank": staticmethod(lambda: {"items": []})}))
    seen = _emitted(monkeypatch)

    assert wreset._blank_one("msg") == "blank"
    labels = [l for _, l, _ in seen]
    assert "blank" in labels
    assert labels.count("data") == 1, (
        "`save()` ya emitió el refresco: emitir un segundo `data` haría al canvas re-pintar dos veces por nada")


def test_announcing_can_never_break_the_wipe(data_dir, monkeypatch):
    """Vaciar un widget es la operación; contarlo es un efecto. Si el observador falla, el reset SIGUE."""
    from widgets import reset as wreset
    import voice.observer as obs

    (data_dir / "x").mkdir()
    (data_dir / "x" / "state.json").write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("observer caído")

    monkeypatch.setattr(obs, "emit", boom)
    assert wreset._blank_one("x") == "wiped"
    assert not (data_dir / "x" / "state.json").exists()
