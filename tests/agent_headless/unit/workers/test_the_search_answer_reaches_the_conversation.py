"""La búsqueda dio la respuesta perfecta y murió dentro del worker (V2-236).

Medido por el arnés el 2026-08-21 en `cheapest-monitor`, leyendo la observabilidad ENTERA (antes solo miraba el
38 % de 1291 eventos). Los eventos `kind='search'` (`🌐 web ↩`) traían, en texto limpio:

    «Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €»
    «Alurin CoreVision 27" IPS 4K Freesync — 149,99 €»

exactamente lo que el operador pidió. Y el recuento, con su corrección incluida: **búsquedas 7 · respuestas 5 ·
notas al cerebro desde ese canal 0**. Los tres modelos que sí se dijeron en voz alta (`27US500-W`, `S2725QS`)
llegaron por la URL del NAVEGADOR, no por la respuesta de búsqueda: ese canal no tenía camino de entrega.

El porqué: **5 de 8 workers devolvieron `ok:false`**. El worker se cae antes de entregar y el texto bueno se va
con él. Zaelar dijo «la búsqueda se ha caído sin terminar» — decía LA VERDAD, y el arnés se lo había puntuado
como vaguedad.

Es el mismo agujero que V2-223 cerró para lo que extrae el NAVEGADOR, por la otra puerta. Aquí se cierra en el
sustrato (`WorkerSession._on_event`), que es donde `where` ya viene normalizado, así que cubre a Claude Code, a
Codex y a Grok —y a las tools NATIVAS de cada CLI, que es donde el arnés midió la pérdida— con un solo sitio; y
además en `worker_api`, que es NUESTRA búsqueda prestada al worker.
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


# ── el caso medido, POR EL CAMINO REAL ───────────────────────────────────────────────────────────────────────
# El primer intento de estos tests llamaba a `_maybe_hand_web` a mano: con el enganche BORRADO de `_on_event`
# pasaban los dieciséis. Es la lección de V2-199 —un test que no recorre el camino real prueba que el código
# compila— y aquí el camino es el evento `step_result` del stream, que es el único que existe en producción.

def test_un_step_result_de_web_llega_a_la_conversacion(sesion):
    from nucleo.workers.base import WorkerEvent
    sesion._on_event(WorkerEvent(task_id="t1", type="step_result", data=_web(RESPUESTA)))
    notas = brain_notes.drain()
    assert notas, "el enganche no está en `_on_event`: en producción no se empuja nada"
    assert "Philips 27E1N1800A" in notas[0]


# ── el resto, sobre el predicado ─────────────────────────────────────────────────────────────────────────────

def test_lo_que_devuelve_la_busqueda_llega_a_la_conversacion(sesion):
    sesion._maybe_hand_web(_web(RESPUESTA))
    notas = brain_notes.drain()
    assert notas, "la respuesta vivía y moría dentro del worker"
    assert "Philips 27E1N1800A" in notas[0] and "159,00 €" in notas[0]


def test_va_por_el_camino_que_SI_llega(sesion):
    """Nota EMPUJADA y no línea de prompt: medido 3 de 3 contra 0 de 13 (V2-222). Y con su encargo delante, que
    es lo que permite al turno juzgar si la respuesta sirve."""
    sesion._maybe_hand_web(_web(RESPUESTA))
    n = brain_notes.drain()[0]
    assert n.startswith("[SISTEMA]")
    assert "el monitor más barato" in n


def test_el_JUICIO_se_queda_en_el_cerebro(sesion):
    """No se ordena anunciarlo: se entrega el hecho y se nombra la prueba. Una orden de «di esto» acabaría
    ofreciendo el primer resultado de una búsqueda fallida como si fuera la respuesta — es exactamente lo que
    V2-223 evitó con el espectáculo de flamenco de 25 €."""
    sesion._maybe_hand_web(_web(RESPUESTA))
    n = brain_notes.drain()[0]
    # V2-510 reescribió la REDACCIÓN («di si sirve» → «diciendo lo que ES», con la rama de la página
    # explícita) porque el imperativo viejo ordenaba entregar lo que fuera con nombre y precio, y lo que
    # vuelve de una búsqueda suele ser un artículo. El INVARIANTE de este test no cambia y es el que se
    # afirma ahora: se pide un JUICIO —qué es y si sirve—, nunca un anuncio a secas. Fijarlo al literal
    # habría obligado a elegir entre arreglar el defecto y conservar la guarda.
    assert "NÓMBRALO EN ESTE TURNO" in n
    assert "diciendo lo que ES" in n              # el juicio se le PIDE
    assert "si es un artículo" in n               # …y la rama de «no responde» sigue ahí
    assert "NUNCA lo ofrezcas como una opción" in n   # más fuerte que antes: no se ordena anunciar


def test_un_FALLO_de_la_tool_no_es_un_hallazgo(sesion):
    """Sensibilidad. Un `is_error` tiene su propio camino (el chip del panel, la puerta de permiso de V2-211);
    empujarlo como hallazgo metería un error de herramienta en la conversación como si fuera un resultado."""
    sesion._maybe_hand_web(_web("Error: quota exceeded", is_error=True))
    assert brain_notes.drain() == []


def test_un_paso_que_no_es_web_no_empuja_nada(sesion):
    """La otra dirección: si esto disparara con cualquier `step_result`, cada lectura de fichero y cada consulta
    a memoria del worker acabaría en la conversación."""
    for donde in ("memoria", "codigo", "archivo", "navegador", "sistema", ""):
        sesion._maybe_hand_web({"where": donde, "text": RESPUESTA})
    assert brain_notes.drain() == []


def test_la_misma_respuesta_dos_veces_no_son_dos_hallazgos(sesion):
    sesion._maybe_hand_web(_web(RESPUESTA))
    brain_notes.drain()
    sesion._maybe_hand_web(_web(RESPUESTA))
    assert brain_notes.drain() == []


def test_una_respuesta_DISTINTA_si_se_empuja(sesion):
    """Y la contraria, porque si no el dedup convertiría este arreglo en «solo la primera búsqueda cuenta»."""
    sesion._maybe_hand_web(_web(RESPUESTA))
    brain_notes.drain()
    sesion._maybe_hand_web(_web('MSI MP273U — 27" IPS — 164,00 €'))
    assert "MSI MP273U" in brain_notes.drain()[0]


def test_un_ok_pelado_no_es_un_hallazgo(sesion):
    for ruido in ("", "   ", "ok", "done"):
        sesion._maybe_hand_web(_web(ruido))
    assert brain_notes.drain() == []


def test_no_puede_tumbar_al_worker(sesion):
    """Corre DENTRO del bucle de eventos de una sesión viva: una excepción aquí mataría el worker que la trajo."""
    sesion._maybe_hand_web(None)
    sesion._maybe_hand_web({"where": "web"})
    assert True


# ── se recorta, no se resume ─────────────────────────────────────────────────────────────────────────────────

def test_una_respuesta_larga_se_RECORTA_y_dice_cuanto_falta():
    """Doctrina de `observability/evidence.py`: se recorta, no se resume, y nunca se calla que había más. Una
    respuesta de búsqueda puede ser una página entera y la conversación no es un volcado."""
    largo = "dato " * 400
    out = findings.clip(largo)
    assert len(out) < len(largo)
    assert "caracteres más en el registro" in out
    assert out.startswith("dato dato")


def test_lo_que_cabe_entero_no_se_toca():
    assert findings.clip("  Philips  27E1N1800A  —  159,00 €  ") == "Philips 27E1N1800A — 159,00 €"


# ── el renderizador de NUESTRA búsqueda ──────────────────────────────────────────────────────────────────────

def test_si_la_fuente_ya_sintetizo_se_entrega_ESO():
    """Perplexity/Tavily/AI Overview devuelven la respuesta ya compuesta: reescribirla sería meter una versión
    nuestra donde había una de la fuente."""
    assert findings.render_search({"answer": "El Prado abre de 10:00 a 20:00", "results": [{"title": "x"}]}) \
        == "El Prado abre de 10:00 a 20:00"


def test_sin_respuesta_sintetizada_van_las_filas_TAL_CUAL():
    out = findings.render_search({"answer": "", "results": [
        {"title": "Philips 27E1N1800A", "snippet": '27" UHD 4K', "url": "https://x.invalid/philips"},
        {"title": "Alurin CoreVision", "snippet": "IPS 4K", "url": "https://x.invalid/alurin"}]})
    assert out.startswith("Philips 27E1N1800A — 27\" UHD 4K — https://x.invalid/philips")
    assert "Alurin CoreVision" in out


def test_una_respuesta_vacia_no_produce_nota(sesion):
    """La cadena caída ya tiene su propio camino (`websearch.note_failure` + la línea de estado): empujar una
    nota vacía diría «he encontrado esto: nada»."""
    sesion._maybe_hand_web(_web(findings.render_search({"answer": "", "results": []})))
    assert brain_notes.drain() == []


# ── la memoria de hallazgos se va con la sesión ──────────────────────────────────────────────────────────────

def test_al_terminar_la_sesion_se_olvida_lo_entregado(sesion):
    sesion._maybe_hand_web(_web(RESPUESTA))
    brain_notes.drain()
    findings.forget("t1")
    sesion._maybe_hand_web(_web(RESPUESTA))
    assert brain_notes.drain(), "un encargo NUEVO tiene derecho a que le cuenten lo mismo otra vez"


def test_el_dispatcher_lo_olvida_de_verdad():
    """GUARDA DE CABLEADO: sin la llamada en `_run_session`, el diccionario crece durante toda la vida del
    proceso y una búsqueda repetida en OTRO encargo se tragaría en silencio. Es la lección de V2-199 — un test
    que no recorre el camino real prueba que el código compila."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert "findings.forget(key)" in src
