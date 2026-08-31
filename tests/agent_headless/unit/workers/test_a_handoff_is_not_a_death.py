"""A handoff is not a death (V2-238).

A worker runs out of provider quota and `_finish` does the right thing: it hands off. It relaunches the task with the
next tier and deliberately clears the delivery, so the operator does not see two. What it used to do was leave
`ok=False` and `status="error"` — that is, the handed-off session became **indistinguishable from a dead worker**. And
three things followed from that, all three measured or read in the code:

1. The engine pushed to the brain “the background task has DIED without a result and will not be retried on its own”
   (V2-222) **while the handoff was working**. A false warning, and an expensive one: it asks the operator to decide
   about something already in progress.
2. `_resumable` reads that exact `ok=False`, so in a web run it ALSO triggered the V2-049 auto-resume: **two escalations
   for one death**, two workers on the same task — and until V2-237 both resumed the SAME CLI session, which is how they
   died after 400 ms.
3. The harness counts deaths by reading observability, and counted this one. In `best-plumber-same-day` and
   `weekend-barber`, “worker 1 died after the provider handoff” (1459 and 1445 ms) was not a death.

The fix is a new FACT, not a heuristic: `rec.handoff` says where the baton went, and with it the session
has its own ending —`relevada`— instead of disguising itself as the neighboring ending.
"""
import asyncio

import pytest

from nucleo.workers.session import SessionRecord, WorkerSession


class _Backend:
    name = "fake"

    async def start(self, prompt, *, spec):
        pass

    async def send(self, text):
        pass

    async def events(self):
        return
        yield  # pragma: no cover

    async def stop(self):
        pass


@pytest.fixture
def sesion(monkeypatch):
    """Real session with a fake backend and intercepted escalation: what is measured here is what `_finish`
    LEAVES WRITTEN in the record, which is what dispatch, the sheet, and the panel read."""
    lanzadas = []
    from nucleo.flash import escalate as _esc
    monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                        lambda goal, context=None, **kw: lanzadas.append((goal, context or {})), raising=False)
    rec = SessionRecord(task_id="t1", goal="un fontanero que pueda venir hoy", kind="web")
    s = WorkerSession(_Backend(), type("S", (), {"model": "", "kind": "web"})(), rec)
    s._lanzadas = lanzadas
    return s


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ── the measured case ─────────────────────────────────────────────────────────────────────────────────────────

def test_un_relevo_de_proveedor_NO_termina_en_error(sesion):
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert sesion._lanzadas, "el relevo tiene que relanzar el encargo"
    assert rec.status == "relevada", "una sesión que pasó el testigo se leía igual que un worker muerto"
    assert rec.handoff and "deepseek" in rec.handoff


def test_el_relevo_dice_A_DONDE_paso_el_testigo(sesion):
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert "proveedor" in rec.handoff and "deepseek" in rec.handoff
    assert rec.phase == "relevada"


def test_compactar_y_continuar_tambien_es_un_relevo(sesion):
    """The other `_finish` handoff (V2-218): the context overflowed, and work resumes with what was learned. Same truth —the
    task continues— and therefore the same ending."""
    rec = sesion._rec
    rec.context_full = {"text": "context window", "tokens": 138000}
    _run(sesion._finish())
    assert sesion._lanzadas
    assert rec.status == "relevada" and "contexto" in rec.handoff


# ── the other direction: a genuine ending is STILL an error ──────────────────────────────────────────────────

def test_un_worker_que_muere_de_verdad_sigue_en_error(sesion):
    rec = sesion._rec
    rec.ok = False
    rec.result_summary = "No pude completar la tarea."
    _run(sesion._finish())
    assert rec.status == "error" and not rec.handoff
    assert rec.phase == "sin completar"


def test_un_relevo_SIN_a_donde_ir_es_una_muerte(sesion):
    """With no next tier there is no baton to pass: that really is over, and the operator needs to know."""
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "", "text": "insufficient balance"}
    _run(sesion._finish())
    assert not sesion._lanzadas
    assert rec.status == "error" and not rec.handoff
    assert "sin cuota" in rec.result_summary


def test_si_el_relanzamiento_FALLA_no_se_finge_un_relevo(sesion, monkeypatch):
    """Sensitivity. Marking the baton before knowing that someone took it would turn a silent death into
    a silent death AND without a warning: the operator would be left waiting for a handoff that never started."""
    from nucleo.flash import escalate as _esc
    monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no hay pool")), raising=False)
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert not rec.handoff and rec.status == "error"
    assert "no he podido relevarlo" in rec.result_summary


def test_una_cancelacion_no_se_convierte_en_relevo(sesion):
    rec = sesion._rec
    rec.status = "cancelled"
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "x"}
    _run(sesion._finish())
    assert not sesion._lanzadas and rec.status == "cancelled" and not rec.handoff


# ── what outsiders read ──────────────────────────────────────────────────────────────────────────────────────

def test_relevada_es_un_final_CLASIFICADO():
    """If it is not in the V2-198 enumeration, a handed-off session appears neither live nor finished in the live
    state, and the turn retains its memory of having started it."""
    from nucleo import dispatch
    assert "relevada" in dispatch.ENDED_SESSION_STATES
    assert not (dispatch.LIVE_SESSION_STATES & dispatch.ENDED_SESSION_STATES)


def test_el_aviso_de_MUERTE_no_se_empuja_sobre_un_relevo():
    """WIRING GUARD (V2-199): the predicate may be perfect while the caller continues announcing the death.
    This is what the operator HEARS, so this is the part that cannot go untested."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._remember_ended)
    assert 'getattr(rec, "handoff", "")' in src, "el aviso de muerte de V2-222 se empuja también sobre un relevo"


def test_un_relevo_NO_dispara_ADEMAS_el_auto_resume():
    """WIRING GUARD: two escalations for one death. `_finish` has already relaunched; if `_will_resume` keeps reading
    only `ok=False`, the V2-049 auto-resume launches a SECOND worker on the same task."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert "_handoff = str(getattr(rec, \"handoff\", \"\") or \"\")" in src
    assert "and not _handoff)" in src
    assert "_schedule_auto_resume" in src


def test_la_hoja_NO_se_cierra_cuando_el_encargo_continua():
    """The sheet belongs to the TASK, not the session: closing it on handoff would shut down the surface in front of
    the operator, where they are looking, with the handoff already working (V2-227 scope C)."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert "if not _continues and surfaces.opens_sheet" in src
    assert "_continues = bool(_will_resume or _handoff)" in src


# ── and the finding that emerged while writing these tests ───────────────────────────────────────────────────
# The three `_finish` branches that are NOT a handoff write a `result_summary` announcing a failure, and none
# touched `ok`, which starts as True. With the backend dead before it was closed, that sentence was delivered as a success:
# “Task completed: I have run out of provider quota…”. Seen in the log of this file's first run,
# not reasoned out.

@pytest.mark.parametrize("montaje", ["sin_relevo", "relevo_roto", "contexto_roto"])
def test_un_fallo_ANUNCIADO_no_se_entrega_como_tarea_completada(sesion, monkeypatch, montaje):
    rec = sesion._rec
    if montaje == "sin_relevo":
        rec.provider_down = {"provider": "z.ai", "next": "", "text": "insufficient balance"}
    else:
        from nucleo.flash import escalate as _esc
        monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no hay pool")), raising=False)
        if montaje == "relevo_roto":
            rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
        else:
            rec.context_full = {"text": "context window", "tokens": 138000}
    _run(sesion._finish())
    assert rec.ok is False, "una frase que ANUNCIA un fallo salía entregada como «Tarea completada: …»"
    assert rec.status == "error"


# ── V2-241: a SILENT ending after hitting our own door ──────────────────────────────────────────────────────
# The three measured cases died without saying anything, and the cause appeared only by cross-referencing the engine log via
# `span=worker:N`. If the session ends without a delivery or handoff but hit the door, THAT is what happened
# — and it is not a task failure; the route it chose is closed here.

def test_un_final_sin_entrega_tras_la_puerta_DICE_que_comando_paro(sesion):
    rec = sesion._rec
    rec.ok = False
    rec.perm_denied = 'curl -s "https://x.invalid/p"'
    _run(sesion._finish())
    assert "curl -s" in rec.result_summary, "moría sin decir por qué se quedó a medias"
    assert rec.status == "error"


def test_si_YA_entrego_algo_no_se_le_pisa_la_entrega(sesion):
    """Sensitivity: the worker's report takes precedence. Replacing it with the door warning would change a
    REAL partial result into an excuse."""
    rec = sesion._rec
    rec.ok = False
    rec.perm_denied = "cd /Users/x/zaelar/engine"
    rec.result_summary = "He encontrado dos fontaneros con guardia de 24 h."
    _run(sesion._finish())
    assert rec.result_summary.startswith("He encontrado dos")


def test_un_RELEVO_no_se_convierte_en_excusa_de_permiso(sesion):
    """The other direction: if the baton was passed, the delivery is deliberately cleared, and inserting the door warning here
    would tell the operator about an ending that did not happen."""
    rec = sesion._rec
    rec.perm_denied = "cd /Users/x/zaelar/engine"
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert rec.status == "relevada" and not rec.result_summary.strip()


def test_sin_choque_de_permiso_no_se_inventa_ninguno(sesion):
    rec = sesion._rec
    rec.ok = False
    rec.result_summary = ""
    _run(sesion._finish())
    assert "no está permitido" not in rec.result_summary
