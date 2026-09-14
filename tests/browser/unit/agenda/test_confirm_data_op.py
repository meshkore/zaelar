"""Confirming an IRREVERSIBLE data-op must EXECUTE it — by voice and by button (session 319252e7, 2026-08-15).

The operator: *“agenda deletion does not work.”* The complete session log:

    12:15:11  operator  “Well, look, I want you to delete and clear the agenda.”
    12:15:17  system    data:clear_all (mode=confirm) → question
    12:15:50  operator  “I confirmed it with the button.”      ← and the agenda was still full
    12:15:51  operator  “But I still see items in the agenda.”
    12:16:14  system    data:clear_all (mode=confirm) → **the SAME question again**
    12:16:16  whisper   “the system did not execute the actual action after confirmation, repeating the question
                         without making progress”  → escalates to a worker, which hits the SAME gate and asks again

The cause: `POST /widgets/{id}/confirm` only knew how to execute the `delete` class. With a data-op it returned
`400 unsupported action: data` — but `confirm.resolve()` **had already consumed the pending confirmation**.
Pressing “Yes” therefore DESTROYED the saved mutation without executing anything, leaving the system with nothing
to resolve when “yes” was subsequently spoken: hence the loop.

What made the bug difficult to see is that the VOICE half was already complete: the same action worked when
saying “yes” and did not work when pressing “Yes”. And it was already partly known — the docstring of
`_request_cluster_confirm` (V2-086) says that “BUTTON confirmation never worked for connect”, and instead of
fixing it at the source, that case was moved to another surface.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store: without this, the test would empty the operator’s REAL agenda."""
    from widgets import confirm, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    confirm.reset()
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["projects"] = [{"id": "p1", "name": "Reddit", "priority": 1, "status": "active"}]
    db["tasks"] = [{"id": "t1", "projectId": "p1", "title": "Calendario de posts", "status": "todo"}]
    db["meetings"] = [{"title": "Revisión", "date": "2026-08-15", "startTime": "17:00", "endTime": "18:00"}]
    store.save(ag.WIDGET_ID, db)
    return ag


def test_el_boton_Si_EJECUTA_la_data_op(agenda):
    """The exact bug from the session: pressing “Yes” while the agenda remained full."""
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    res = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert json.loads(res.body)["ok"] is True, "el botón tiene que ejecutar, no devolver «acción no soportada»"

    db = agenda.load_db()
    assert db["meetings"] == [], "se confirmó y la agenda sigue con citas"
    assert all(t["status"] in ("dropped", "done") for t in db["tasks"]), "se confirmó y quedan tareas pendientes"


def test_un_Si_que_no_ejecuta_no_puede_QUEMAR_la_confirmacion(agenda):
    """What turned a bug into a LOOP. If a branch does not know how to execute, the least it can do is let the operator
    try again; previously the confirmation was consumed anyway and the subsequent spoken “yes” found nothing
    to resolve, so the model opened ANOTHER confirmation. Six times."""
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    # After a “Yes” that DOES execute, the confirmation is consumed — correct. The reverse must not happen:
    # consuming it without executing. This is checked through its effect, which is what the operator experiences.
    assert not confirm.pending(), "una confirmación ya ejecutada no puede quedarse colgada"
    assert agenda.load_db()["meetings"] == []


def test_el_No_cancela_y_no_toca_nada(agenda):
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    res = asyncio.run(server_api.confirm_widget("agenda", {"ok": False}))
    assert json.loads(res.body)["cancelled"] is True
    assert agenda.load_db()["meetings"], "un «no» no puede vaciar nada"


def test_una_confirmacion_sin_accion_guardada_no_ejecuta_a_ciegas(agenda):
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿?", op={"action": "", "payload": {}})
    res = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert res.status_code == 400
    assert agenda.load_db()["meetings"], "sin acción declarada no se toca nada"


# ── EARLY resolution, before streaming (V2-090 addendum, 2026-08-15) ────────────────────────────────────────────
# Real session f4d3c7cc: the operator said “Yes, empty the whole thing.” and that turn was cancelled by barge-in (the
# operator kept speaking) before reaching the usual deterministic backstop, which runs only AFTER the model’s complete
# streaming. The confirmation remained pending forever; the agenda did not change, and NO execution or cancellation
# event was recorded — the response was silently lost, not rejected. `_resolve_pending_confirm` is the function now
# called EARLY (before any slow work) so that a clear yes/no does not depend on the turn surviving in full. Here its
# execution logic is tested directly (without an HTTP server), the same logic used by the button endpoint and the late
# backstop — one function, three callers.
def test_resolve_pending_confirm_ejecuta_la_data_op(agenda):
    """The actual execution goes through `_spawn` -> `asyncio.create_task` (fire-and-forget, as in the real voice turn):
    a LIVE loop and a tick are needed for the created task to run, just as in production (`_run_inner` is a coroutine
    inside the agent loop, never a plain synchronous call)."""
    from voice.engine.llm.providers.nucleo import _resolve_pending_confirm
    from widgets import confirm

    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    async def _run():
        assert _resolve_pending_confirm(True) is True
        await asyncio.sleep(0.05)   # let the fire-and-forget task dispatch the actual mutation

    asyncio.run(_run())

    db = agenda.load_db()
    assert db["meetings"] == [], "se confirmó y la agenda sigue con citas"
    assert all(t["status"] in ("dropped", "done") for t in db["tasks"]), "se confirmó y quedan tareas pendientes"


def test_resolve_pending_confirm_no_hace_nada_sin_confirmacion_pendiente():
    from voice.engine.llm.providers.nucleo import _resolve_pending_confirm
    from widgets import confirm

    confirm.reset()
    assert _resolve_pending_confirm(True) is False


def test_resolve_pending_confirm_adopta_el_trace_de_quien_pregunto(agenda):
    """The ask and response run in different turns/traces — without this, the master sees TWO flows where the
    operator sees ONE action (see [[project_flows_board_and_trace_continuity]] from this same initiative)."""
    from voice import trace
    from voice.engine.llm.providers.nucleo import _resolve_pending_confirm
    from widgets import confirm

    trace.adopt("")
    asking_tid = trace.begin("borra toda la agenda", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    trace.adopt("")   # the response turn starts with ITS OWN trace, as in production

    async def _run():
        assert _resolve_pending_confirm(True) is True
        # The check occurs INSIDE the same coroutine/context: `asyncio.run()` copies the context on entry and does not
        # propagate it back on exit — as in a real turn, where all of this occurs in a SINGLE chain of coroutines
        # with no `asyncio.run()` boundary in between.
        assert trace.current() == asking_tid
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    trace.adopt("")


# ── Voice-only widget: WITHOUT a visual overlay, voice remains unchanged (2026-08-15, operator request) ─────────
def test_confirm_ui_false_no_pinta_overlay_pero_la_confirmacion_sigue_pendiente():
    """`agenda/manifest.json` declares `confirm_ui: false` — “the agenda widget is handled by voice only”. The
    confirmation record (so that spoken “yes”/“no” can resolve it) must be IDENTICAL; the only change is that the
    `widget/confirm` event used by the UI to render the button is not emitted."""
    from widgets.confirm import ui_paints as _confirm_ui_paints   # moved out of the provider (V2-515 ratchet)
    from voice import observer
    from widgets import confirm

    assert _confirm_ui_paints("agenda") is False

    before = len(observer.debug_events(kind="widget"))
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}},
                     notify_ui=_confirm_ui_paints("agenda"))
    after = observer.debug_events(kind="widget")
    assert len(after) == before, "confirm_ui:false no puede seguir emitiendo el evento que pinta el overlay"
    assert confirm.pending().get("agenda"), "la confirmación sigue registrada pese a no pintar overlay"


def test_confirm_ui_defaults_true_para_widgets_sin_el_flag():
    from widgets.confirm import ui_paints as _confirm_ui_paints   # moved out of the provider (V2-515 ratchet)

    assert _confirm_ui_paints("meteo-soria") is True
    assert _confirm_ui_paints("no-existe-este-widget") is True


# ── The QUESTION read aloud to the operator ───────────────────────────────────────────────────────────────────
def test_la_pregunta_no_recita_las_instrucciones_del_MODELO():
    """The operator heard this entire text as a question:

        “Careful, this is permanent: “EMPTY the entire agenda at once: discard all pending tasks,
         freeze all projects, and delete all appointments and blocks. **Use it when the operator asks** to leave it
         empty “completely”/“entirely”/“today and forever”, instead of removing items one by one.” Shall I confirm?”

    The manifest’s `desc` is the TOOL description: text written for the MODEL. Reading it to the operator is a
    category error — we were reciting our internal instructions and asking them to say “yes”.
    """
    from voice.engine.llm.providers.nucleo import _human_confirm_question
    q = _human_confirm_question("agenda", "clear_all", {})
    assert "Úsala cuando" not in q, f"la pregunta lleva guía de uso del modelo: {q}"
    assert len(q) < 120, f"una pregunta hablada de {len(q)} chars no es una pregunta: {q}"
    # A question MUST be present; it need not end in “?”: “¿Vacío la agenda entera? Es permanente.” is a
    # question followed by its warning, and that sounds better aloud than the reverse.
    assert "?" in q, f"tiene que preguntar algo: {q}"


def test_confirm_q_esta_declarada_donde_se_pide_confirmacion():
    """Every `confirm:true` agenda action needs its HUMAN question. Without it, it falls back to `desc`, which is what
    caused the failure above."""
    man = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    sin_pregunta = [n for n, s in (man.get("actions") or {}).items()
                    if s.get("confirm") and not str(s.get("confirm_q") or "").strip()]
    assert not sin_pregunta, f"acciones que piden confirmación sin pregunta humana: {sin_pregunta}"


# ── V2-693 · «MENOS ESTOS DOS» ES OTRA ACCIÓN, Y LA PREGUNTA DICE CUÁNTAS SE LLEVA ──────────────────────

def test_clear_range_borra_el_tramo_y_conserva_lo_que_el_NOMBRA(agenda):
    """⚠️ Su orden, 2026-09-14: «limpia todo los items de esta semana, menos lo de mañana a las 15h y el
    inicio de instituto de lunes». La única herramienta en bloque era `clear_all`, cuyo alcance es TODO y
    para siempre — así que el modelo la eligió y describió un borrado selectivo que esa acción no sabe
    hacer. De haberse confirmado, las dos citas que pidió CONSERVAR se habrían ido igual."""
    from widgets.agenda import data as ag
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [
        {"title": "Dentista", "date": "2026-09-15", "startTime": "17:00", "endTime": "18:00"},
        {"title": "Dentista", "date": "2026-09-16", "startTime": "10:00", "endTime": "11:00"},
        {"title": "Gavin/Ricart zerohash blockchain intro", "date": "2026-09-15", "startTime": "15:00"},
        {"title": "Inicio curso instituto", "date": "2026-09-14"},
        {"title": "Notario", "date": "2026-10-02", "startTime": "17:00"},   # FUERA del tramo
    ]
    store.save(ag.WIDGET_ID, db)

    r = ag.apply_action("clear_range", {"from": "2026-09-14", "to": "2026-09-20",
                                        "keep": [{"date": "2026-09-15", "time": "15:00"},
                                                 {"title": "Inicio curso instituto"}]})

    assert r["ok"] and r["result"]["removed"] == 2
    left = sorted(m["title"] for m in ag.load_db()["meetings"])
    assert left == ["Gavin/Ricart zerohash blockchain intro", "Inicio curso instituto", "Notario"], left


def test_un_tramo_NUNCA_toca_lo_de_fuera(agenda):
    """La diferencia entera con `clear_all`: una semana es una semana."""
    from widgets.agenda import data as ag
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [{"title": "Dentro", "date": "2026-09-15", "startTime": "10:00"},
                      {"title": "Antes", "date": "2026-09-13", "startTime": "10:00"},
                      {"title": "Despues", "date": "2026-09-21", "startTime": "10:00"}]
    store.save(ag.WIDGET_ID, db)
    ag.apply_action("clear_range", {"from": "2026-09-14", "to": "2026-09-20"})
    assert sorted(m["title"] for m in ag.load_db()["meetings"]) == ["Antes", "Despues"]


def test_un_keeper_por_TITULO_encuentra_la_cita_aunque_el_nombre_sea_mas_largo(agenda):
    """«el zerohash» tiene que encontrar «Gavin/Ricart zerohash blockchain intro» — se compara como en el
    resto de este widget: sin acentos, sin mayúsculas y por contención."""
    from widgets.agenda import data as ag
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [{"title": "Gavin/Ricart zerohash blockchain intro", "date": "2026-09-15",
                       "startTime": "15:00"},
                      {"title": "Dentista", "date": "2026-09-15", "startTime": "17:00"}]
    store.save(ag.WIDGET_ID, db)
    ag.apply_action("clear_range", {"from": "2026-09-14", "to": "2026-09-20", "keep": "el zerohash"})
    assert [m["title"] for m in ag.load_db()["meetings"]] == ["Gavin/Ricart zerohash blockchain intro"]


def test_un_keeper_con_HORA_no_salva_el_resto_de_su_dia(agenda):
    """«mañana a las 15h» es una fecha Y una hora. Casar solo por la fecha conservaría el día entero, que es
    justo lo contrario de lo que pidió."""
    from widgets.agenda import data as ag
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [{"title": "Salvada", "date": "2026-09-15", "startTime": "15:00"},
                      {"title": "Va fuera", "date": "2026-09-15", "startTime": "17:00"}]
    store.save(ag.WIDGET_ID, db)
    ag.apply_action("clear_range", {"from": "2026-09-15", "to": "2026-09-15",
                                    "keep": [{"date": "2026-09-15", "time": "15:00"}]})
    assert [m["title"] for m in ag.load_db()["meetings"]] == ["Salvada"]


def test_la_pregunta_dice_CUANTAS_se_lleva_y_QUE_conserva(agenda):
    """Una confirmación que no cuenta lo que se lleva por delante es una a la que se dice que sí sin mirar.
    La enlatada decía «¿Vacío la agenda entera?» — verdad de la acción, y sin relación con lo que él pidió."""
    from voice.engine.llm.providers.confirm_gate import _human_confirm_question
    from widgets.agenda import data as ag
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [{"title": "Dentista", "date": "2026-09-15", "startTime": "17:00"},
                      {"title": "Consejo", "date": "2026-09-16", "startTime": "10:00"},
                      {"title": "Zerohash", "date": "2026-09-15", "startTime": "15:00"}]
    store.save(ag.WIDGET_ID, db)

    q = _human_confirm_question("agenda", "clear_range",
                                {"from": "2026-09-14", "to": "2026-09-20", "keep": "Zerohash"})

    assert "2 citas" in q, q
    assert "«Zerohash»" in q, "lo que se conserva se NOMBRA, o no se puede comprobar antes de decir que sí"
    assert "permanente" in q.lower() and q.strip().endswith("?")


def test_un_tramo_VACIO_lo_dice_en_vez_de_pedir_permiso_para_nada(agenda):
    from voice.engine.llm.providers.confirm_gate import _human_confirm_question
    q = _human_confirm_question("agenda", "clear_range", {"from": "2027-01-01", "to": "2027-01-02"})
    assert "No hay ninguna cita" in q


def test_una_confirmacion_abierta_no_puede_quedarse_MUDA_bajo_la_frase_del_modelo():
    """⚠️ Medido el 2026-09-14 en su sesión, y es la razón por la que creyó que la agenda se había limpiado.

        él      «limpia todo los items de esta semana, mnos lo de mañana a las 15h y el inicio de instituto»
        sistema  data:clear_all (mode=confirm) → abre «¿Vacío la agenda entera? Es permanente.»
        zaelar  «Clearing this week from your calendar — keeping tomorrow at 15:00 and the school start…»
        (nada se borró, y la pregunta no se dijo NUNCA)

    La condición exigía `not spoken_text`, razonando «si el modelo ya dijo algo, ya formuló él la pregunta».
    Aquí dijo una acción TERMINADA que ni se había despachado, y cuyo alcance real era el calendario entero.
    Es exactamente la lección que el bloque de `clarify` aprendió el 2026-07-22 —una señal determinista no
    puede perder contra una frase inventada— y que este no había heredado.

    Ratchet de FUENTE porque el bloque vive dentro del turno del proveedor de voz, que no se monta aislado;
    el mismo patrón que `test_both_channels_wire_the_repair`. Lo que congela es la condición, no el texto."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    i = src.index('if confirm_state.get("opened")')
    cond = src[i:src.index(":\n", i)]
    assert "not spoken_text" not in cond, \
        "la pregunta de una confirmación abierta vuelve a callarse cuando el modelo habla"
    assert 'spoken_text = confirm_state["opened"]' in src[i:i + 400], \
        "y SUSTITUYE lo que dijo el modelo: su frase habla de algo que no ha pasado"
    j = src.index('if clarify["msg"]')
    assert "not spoken_text" not in src[j:src.index(":\n", j)], \
        "el hermano de esta guarda perdió la suya"


def test_una_cita_que_GOOGLE_no_borra_se_QUEDA_y_se_dice(agenda, monkeypatch):
    """⚠️ La causa de fondo del 2026-09-14, y la más cara porque MIENTE: `delete_google` se tragaba tanto la
    excepción como el `{"ok": False}` del servicio, así que un rechazo, un 404, un token caducado y un corte
    de red eran indistinguibles de un éxito. La fila local se iba igual, el resultado decía «borradas: 42» —
    y la siguiente sincronización traía de vuelta las que Google nunca había perdido."""
    from widgets.agenda import data as ag, gcal
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [
        {"title": "Se va", "date": "2026-09-15", "startTime": "10:00", "source": "google",
         "googleId": "g1", "googleCalendarId": "c"},
        {"title": "No se deja", "date": "2026-09-15", "startTime": "11:00", "source": "google",
         "googleId": "g2", "googleCalendarId": "c"},
    ]
    store.save(ag.WIDGET_ID, db)
    monkeypatch.setattr(gcal, "delete_google", lambda m: m.get("googleId") != "g2")

    r = ag.apply_action("clear_range", {"from": "2026-09-15", "to": "2026-09-15"})

    assert r["ok"] is False, "un trabajo a medias no puede contestar «hecho»"
    assert r["result"]["removed"] == 1 and r["result"]["failed"] == ["No se deja"]
    assert "No se deja" in r["error"], "se NOMBRA la que no pudo, no se cuenta"
    left = [m["title"] for m in ag.load_db()["meetings"]]
    assert left == ["No se deja"], \
        "la fila que Google conserva se QUEDA: tirarla aquí la resucita en la siguiente sincronización"


def test_delete_google_distingue_el_exito_del_silencio(agenda, monkeypatch):
    from widgets.agenda import gcal
    row = {"source": "google", "googleId": "g", "googleCalendarId": "c", "title": "X"}

    monkeypatch.setattr(gcal, "svc", lambda: type("S", (), {"delete_event": staticmethod(lambda m: {"ok": True})})())
    assert gcal.delete_google(row) is True

    monkeypatch.setattr(gcal, "svc", lambda: type("S", (), {
        "delete_event": staticmethod(lambda m: {"ok": False, "error": "no existe"})})())
    assert gcal.delete_google(row) is False, "el servicio ya lo decía; era el envoltorio quien lo tiraba"

    def _boom(m):
        raise RuntimeError("red caída")
    monkeypatch.setattr(gcal, "svc", lambda: type("S", (), {"delete_event": staticmethod(_boom)})())
    assert gcal.delete_google(row) is False

    monkeypatch.setattr(gcal, "svc", lambda: None)
    assert gcal.delete_google(row) is False, "sin conector no se puede afirmar que Google la haya perdido"
    assert gcal.delete_google({"title": "local"}) is True, "una cita que no viene de Google no debe nada allí"
