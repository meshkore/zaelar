"""The search produced the perfect answer and died inside the worker (V2-236).

Measured by the harness on 2026-08-21 in `cheapest-monitor`, reading the COMPLETE observability output (previously it only looked at
38% of 1291 events). The `kind='search'` events (`🌐 web ↩`) contained, in clean text:

    «Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €»
    «Alurin CoreVision 27" IPS 4K Freesync — 149,99 €»

exactly what the operator asked for. And the count, including its correction: **searches 7 · answers 5 ·
brain notes from that channel 0**. The three models that were actually spoken aloud (`27US500-W`, `S2725QS`)
came through the BROWSER URL, not the search answer: that channel had no delivery path.

Why: **5 of 8 workers returned `ok:false`**. The worker crashes before delivering, and the good text goes
with it. Zaelar said “the search crashed before finishing” — it was telling THE TRUTH, and the harness had scored it
as vagueness.

It is the same hole that V2-223 closed for what the BROWSER extracts, through the other door. Here it is closed in the
substrate (`WorkerSession._on_event`), where `where` is already normalized, so it covers Claude Code, Codex, and Grok
—and each CLI’s NATIVE tools, where the harness measured the loss— in one place; and
and also in `worker_api`, which is OUR search lent to the worker.
"""
import pytest

from nucleo.workers import findings
from nucleo.workers.session import SessionRecord, WorkerSession
from voice import brain_notes

RESPUESTA = ('Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €. '
             'Alurin CoreVision 27" IPS 4K Freesync — 149,99 €.')


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
def sesion():
    rec = SessionRecord(task_id="t1", goal="el monitor más barato que sirva para trabajar", kind="web")
    s = WorkerSession(_Backend(), type("S", (), {"model": "", "kind": "web"})(), rec)
    findings.forget(rec.task_id)
    brain_notes.drain()
    yield s
    findings.forget(rec.task_id)
    brain_notes.drain()


def _web(text, **kw):
    return {"where": "web", "text": text, "tool": "WebSearch", **kw}


# ── the measured case, THROUGH THE REAL PATH ─────────────────────────────────────────────────────────────────
# The first attempt at these tests called `_maybe_hand_web` by hand: with the hook in `_on_event` DELETED,
# all sixteen passed. This is the lesson of V2-199 —a test that does not traverse the real path only proves that the code
# compiles— and here the path is the stream’s `step_result` event, the only one that exists in production.

def test_un_step_result_de_web_llega_a_la_conversacion(sesion):
    from nucleo.workers.base import WorkerEvent
    sesion._on_event(WorkerEvent(task_id="t1", type="step_result", data=_web(RESPUESTA)))
    notas = brain_notes.drain()
    assert notas, "el enganche no está en `_on_event`: en producción no se empuja nada"
    assert "Philips 27E1N1800A" in notas[0]


# ── the rest, about the predicate ───────────────────────────────────────────────────────────────────────────

def test_lo_que_devuelve_la_busqueda_llega_a_la_conversacion(sesion):
    sesion._maybe_hand_web(_web(RESPUESTA))
    notas = brain_notes.drain()
    assert notas, "la respuesta vivía y moría dentro del worker"
    assert "Philips 27E1N1800A" in notas[0] and "159,00 €" in notas[0]


def test_va_por_el_camino_que_SI_llega(sesion):
    """PUSHED note, not a prompt line: measured 3 out of 3 versus 0 out of 13 (V2-222). And with its task in front of it, which
    is what lets the turn judge whether the answer is useful."""
    sesion._maybe_hand_web(_web(RESPUESTA))
    n = brain_notes.drain()[0]
    assert n.startswith("[SISTEMA]")
    assert "el monitor más barato" in n


def test_el_JUICIO_se_queda_en_el_cerebro(sesion):
    """It is not instructed to announce it: the fact is delivered and the evidence is named. An instruction to “say this” would end up
    offering the first result of a failed search as though it were the answer — exactly what
    V2-223 avoided with the €25 flamenco show."""
    sesion._maybe_hand_web(_web(RESPUESTA))
    n = brain_notes.drain()[0]
    # V2-510 rewrote the WORDING (“say whether it is useful” → “saying what it IS”, with the page branch
    # made explicit) because the old imperative ordered delivery of anything with a name and price, and what
    # comes back from a search is usually an item. The INVARIANT of this test does not change and is what it
    # now asserts: a JUDGMENT is requested —what it is and whether it is useful—, never an advertisement alone. Pinning it to the literal
    # would have forced a choice between fixing the defect and preserving the guard.
    assert "NÓMBRALO EN ESTE TURNO" in n
    assert "diciendo lo que ES" in n              # the judgment is REQUESTED
    assert "si es un artículo" in n               # …and the “does not respond” branch is still there
    assert "NUNCA lo ofrezcas como una opción" in n   # stronger than before: it is not instructed to advertise


def test_un_FALLO_de_la_tool_no_es_un_hallazgo(sesion):
    """Sensitivity. An `is_error` has its own path (the panel chip, V2-211’s permission gate);
    pushing it as a finding would put a tool error into the conversation as though it were a result."""
    sesion._maybe_hand_web(_web("Error: quota exceeded", is_error=True))
    assert brain_notes.drain() == []


def test_un_paso_que_no_es_web_no_empuja_nada(sesion):
    """The reverse direction: if this fired on every `step_result`, every file read and every query
    to the worker’s memory would end up in the conversation."""
    for donde in ("memoria", "codigo", "archivo", "navegador", "sistema", ""):
        sesion._maybe_hand_web({"where": donde, "text": RESPUESTA})
    assert brain_notes.drain() == []


def test_la_misma_respuesta_dos_veces_no_son_dos_hallazgos(sesion):
    sesion._maybe_hand_web(_web(RESPUESTA))
    brain_notes.drain()
    sesion._maybe_hand_web(_web(RESPUESTA))
    assert brain_notes.drain() == []


def test_una_respuesta_DISTINTA_si_se_empuja(sesion):
    """And the converse, because otherwise deduplication would turn this fix into “only the first search counts”."""
    sesion._maybe_hand_web(_web(RESPUESTA))
    brain_notes.drain()
    sesion._maybe_hand_web(_web('MSI MP273U — 27" IPS — 164,00 €'))
    assert "MSI MP273U" in brain_notes.drain()[0]


def test_un_ok_pelado_no_es_un_hallazgo(sesion):
    for ruido in ("", "   ", "ok", "done"):
        sesion._maybe_hand_web(_web(ruido))
    assert brain_notes.drain() == []


def test_no_puede_tumbar_al_worker(sesion):
    """Runs INSIDE the event loop of a live session: an exception here would kill the worker that brought it."""
    sesion._maybe_hand_web(None)
    sesion._maybe_hand_web({"where": "web"})
    assert True


# ── clipped, not summarized ─────────────────────────────────────────────────────────────────────────────────

def test_una_respuesta_larga_se_RECORTA_y_dice_cuanto_falta():
    """Doctrine of `observability/evidence.py`: clip it, do not summarize it, and never hide that there was more. A
    search answer can be an entire page, and the conversation is not a dump."""
    largo = "dato " * 400
    out = findings.clip(largo)
    assert len(out) < len(largo)
    assert "caracteres más en el registro" in out
    assert out.startswith("dato dato")


def test_lo_que_cabe_entero_no_se_toca():
    assert findings.clip("  Philips  27E1N1800A  —  159,00 €  ") == "Philips 27E1N1800A — 159,00 €"


# ── the renderer for OUR search ─────────────────────────────────────────────────────────────────────────────

def test_si_la_fuente_ya_sintetizo_se_entrega_ESO():
    """Perplexity/Tavily/AI Overview return the answer already composed: rewriting it would insert one of
    our versions where there was a source version."""
    assert findings.render_search({"answer": "El Prado abre de 10:00 a 20:00", "results": [{"title": "x"}]}) \
        == "El Prado abre de 10:00 a 20:00"


def test_sin_respuesta_sintetizada_van_las_filas_TAL_CUAL():
    out = findings.render_search({"answer": "", "results": [
        {"title": "Philips 27E1N1800A", "snippet": '27" UHD 4K', "url": "https://x.invalid/philips"},
        {"title": "Alurin CoreVision", "snippet": "IPS 4K", "url": "https://x.invalid/alurin"}]})
    assert out.startswith("Philips 27E1N1800A — 27\" UHD 4K — https://x.invalid/philips")
    assert "Alurin CoreVision" in out


def test_una_respuesta_vacia_no_produce_nota(sesion):
    """The failure string already has its own path (`websearch.note_failure` + the status line): pushing an
    empty note would say “I found this: nothing”."""
    sesion._maybe_hand_web(_web(findings.render_search({"answer": "", "results": []})))
    assert brain_notes.drain() == []


# ── the findings memory goes away with the session ──────────────────────────────────────────────────────────

def test_al_terminar_la_sesion_se_olvida_lo_entregado(sesion):
    sesion._maybe_hand_web(_web(RESPUESTA))
    brain_notes.drain()
    findings.forget("t1")
    sesion._maybe_hand_web(_web(RESPUESTA))
    assert brain_notes.drain(), "un encargo NUEVO tiene derecho a que le cuenten lo mismo otra vez"


def test_el_dispatcher_lo_olvida_de_verdad():
    """WIRING GUARD: without the call in `_run_session`, the dictionary grows for the entire lifetime of the
    process and a repeated search in ANOTHER task would be silently swallowed. This is the lesson of V2-199 — a test
    that does not traverse the real path only proves that the code compiles."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert "findings.forget(key)" in src
