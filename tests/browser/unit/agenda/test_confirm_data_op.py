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
