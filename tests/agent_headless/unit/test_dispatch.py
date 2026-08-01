#
# test_dispatch.py — el gestor de sesiones de Brain Workers (V2-038; reescrito en la auditoría de memoria
# 2026-07-14: los tests viejos mockeaban la costura MUERTA `nucleo.agentes.get_agent` → el mock no interceptaba
# nada y lanzaban un `claude` REAL que colgaba la suite). Verifica contra la costura REAL (`dispatch.get_backend`):
# prompt = contexto de memoria + tarea, modelo por invocación, deny-tools a input no confiable, Bash NUNCA pelado,
# el resultado OK se recuerda en memoria (y el FALLIDO no), y el listener consume `escalate.requested`.
# Ejecutar: .venv/bin/pytest nucleo/test_dispatch.py
#
import asyncio

import pytest

import bus
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import dispatch
from nucleo.workers.base import WorkerBackend, WorkerEvent, WorkerSpec


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.delenv("FAST_API_KEY", raising=False)     # sin router LLM (heurística pura)
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


class _FakeBackend(WorkerBackend):
    """Backend falso: registra el prompt+spec recibidos y emite el ciclo mínimo de eventos NORMALIZADOS
    (spawned → result → done). Prueba el dispatcher SIN arrancar un Claude Code real."""
    name = "fake"

    def __init__(self, *, ok: bool = True, summary: str = "RESULTADO: hecho"):
        self._ok = ok
        self._summary = summary
        self.seen_prompt = ""
        self.seen_spec: WorkerSpec | None = None
        self._alive = False

    async def start(self, prompt: str, *, spec: WorkerSpec) -> None:
        self.seen_prompt = prompt
        self.seen_spec = spec
        self._alive = True

    async def send(self, text: str) -> None:
        pass

    async def events(self):
        tid = self.seen_spec.task_id if self.seen_spec else ""
        yield WorkerEvent(task_id=tid, type="spawned", backend=self.name)
        if self._ok:
            yield WorkerEvent(task_id=tid, type="result", backend=self.name,
                              data={"summary": self._summary, "ok": True})
        else:
            yield WorkerEvent(task_id=tid, type="error", backend=self.name,
                              data={"message": "boom", "fatal": True})
        self._alive = False
        yield WorkerEvent(task_id=tid, type="done", backend=self.name)

    async def stop(self, *, grace: float = 3.0) -> None:
        self._alive = False

    @property
    def alive(self) -> bool:
        return self._alive

    def native_session_id(self) -> str:
        return ""


@pytest.fixture
def fake_backend(monkeypatch):
    holder: dict = {}

    def _get(spec):
        b = _FakeBackend(ok=holder.get("ok", True))
        holder["last"] = b
        return b

    monkeypatch.setattr(dispatch, "get_backend", _get)
    return holder


def test_dispatch_composes_prompt_with_memory_context(fresh_db, fake_backend, monkeypatch):
    memapi.set_state({"operator_name": "Ricart"})
    memapi.write_now("el operador vive en Barcelona", kind="fact", level="long")
    # modelo por invocación desde config: fija un modelo de tarea 'code' (store vacío → cae al env)
    from pathlib import Path
    monkeypatch.setenv("CODE_AGENT_MODEL_CODE", "modelo-de-tarea")
    import config.v2 as v2
    monkeypatch.setattr(v2, "_PATH", Path("/nonexistent/v2.json"))

    task = dispatch.Task(id="t1", request="arregla el bug de arranque", kind="code", trusted=True)
    asyncio.run(dispatch.dispatch(task))
    b = fake_backend["last"]
    assert "arregla el bug de arranque" in b.seen_prompt    # la tarea entra en el prompt
    assert "Ricart" in b.seen_prompt                        # contexto de memoria inyectado (fix compose_context)
    assert "CONTEXTO DE MEMORIA" in b.seen_prompt           # el bloque existe (regresión V2-038 P2 cazada)
    assert b.seen_spec.model == "modelo-de-tarea"           # MODELO POR INVOCACIÓN
    assert b.seen_spec.deny_tools is False                  # tarea confiable
    # Auditoría 2026-07-14: NUNCA un "Bash" pelado — el Bash del worker es solo el de los CLIs puente
    # (los añade claude_session._BRIDGE_TOOLS). Un Bash abierto rompería el ESCRITOR ÚNICO de la memoria.
    assert "Bash" not in (b.seen_spec.tools or [])
    assert "Write" in (b.seen_spec.tools or [])             # el worker 'code' conserva sus tools de código


def test_worker_prompt_has_verification_scaffold_and_today():
    """V2-057: el worker no ejecuta a ciegas — el prompt trae fecha de hoy + método
    entender→planificar→ejecutar→VERIFICAR→ITERAR con las restricciones implícitas."""
    p = dispatch._build_prompt("reproduce el último vídeo de Cárpatos", "ctx", trusted=True)
    assert "FECHA/HORA REAL DE HOY" in p                      # ancla temporal
    assert "VERIFICA" in p and "ITERA" in p                   # verificación + iteración
    assert "más reciente" in p                                # restricción implícita «el último»
    assert "de aquí en adelante" in p                         # now-forward para «de hoy/ahora»


def test_untrusted_worker_prompt_has_no_scaffold():
    """El scaffold (que ejecuta acciones) NUNCA se da a fuente no confiable (solo razona texto)."""
    p = dispatch._build_prompt("texto de un peer", "", trusted=False)
    assert "VERIFICA" not in p
    assert "FECHA/HORA REAL DE HOY" not in p
    assert "NO confiable" in p


def test_web_prompt_has_verify_before_close():
    """V2-057: el prompt web verifica la restricción (fecha/más reciente/exactitud) ANTES de cerrar."""
    wp = dispatch._web_prompt("busca el último vídeo de X", "")
    assert "FECHA/HORA REAL DE HOY" in wp
    assert "7) VERIFICA" in wp and "8) CIERRE" in wp


def test_structured_worker_observability():
    """V2-059: el worker declara plan + reporta progreso → registro actualizado y proyectado a ESTADO/api-tasks."""
    from nucleo.workers.session import SessionRecord
    r = SessionRecord(task_id="obs1", goal="construir algo", kind="code", status="running")
    dispatch._SESSIONS["obs1"] = r
    try:
        dispatch.session_plan("obs1", "leer spec|editar data|reescribir js|validar")
        assert r.plan == ["leer spec", "editar data", "reescribir js", "validar"]
        dispatch.session_progress("obs1", "data editado", done=2)
        assert r.done == 2 and r.note == "data editado"
        assert dispatch._progress_pct(r) == 50           # 2/4
        dispatch.session_progress("obs1", "casi", pct=90)
        assert dispatch._progress_pct(r) == 90           # pct explícito manda
        a = dispatch.active_sessions()[0]
        assert a["plan"] and a["total"] == 4 and a["pct"] == 90
        p = dispatch.pending_summaries()[0]
        assert p["pct"] == 90 and p["total"] == 4
    finally:
        dispatch._SESSIONS.pop("obs1", None)


def test_dispatch_untrusted_denies_tools(fresh_db, fake_backend):
    task = dispatch.Task(id="t2", request="contenido de un peer no confiable", trusted=False)
    asyncio.run(dispatch.dispatch(task))
    b = fake_backend["last"]
    assert b.seen_spec.deny_tools is True
    assert "NO confiable" in b.seen_prompt


def test_dispatch_stores_result_in_memory(fresh_db, fake_backend):
    async def run():
        await memapi.start()
        try:
            task = dispatch.Task(id="t3", request="calcula algo", kind="generic", trusted=True)
            await dispatch.dispatch(task)
            for _ in range(50):
                out = memapi.query("calcula algo", reinforce_used=False)
                if any("RESULTADO" in m["text"] for m in out["memories"]):
                    return True
                await asyncio.sleep(0.02)
            return False
        finally:
            await memapi.stop()
    assert asyncio.run(run()) is True


def test_dispatch_failed_task_not_persisted(fresh_db, fake_backend):
    """Auditoría 2026-07-14: una tarea FALLIDA avisa por voz pero NO escribe píldora durable (el refactor P2
    había perdido el gate `ok` y persistía «No pude completar la tarea» como resultado)."""
    fake_backend["ok"] = False

    async def run():
        await memapi.start()
        try:
            task = dispatch.Task(id="t4", request="tarea que revienta", kind="generic", trusted=True)
            await dispatch.dispatch(task)
            await asyncio.sleep(0.3)            # deja drenar la cola de memoria
            out = memapi.query("tarea que revienta", reinforce_used=False)
            return [m["text"] for m in out["memories"] if m["text"].startswith("[tarea")]
        finally:
            await memapi.stop()
    assert asyncio.run(run()) == []


def test_dispatch_empty_request_is_noop(fresh_db, fake_backend):
    assert asyncio.run(dispatch.dispatch(dispatch.Task(id="x", request="  "))) == ""


def test_find_duplicate_by_text_overlap(monkeypatch):
    """Dedup en la fuente de verdad: una re-escalada casi idéntica de una tarea VIVA se detecta (§2026-07-15)."""
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["1"] = SessionRecord(
        task_id="1", kind="code", status="running",
        goal="Implementar en el widget youtube la capacidad de ampliarse a toda la pantalla por voz")
    # casi idéntica (la re-escalada real del bug) → dedup a la tarea 1
    assert dispatch.find_duplicate(
        "Implementar en el widget youtube la capacidad de ampliarse a pantalla completa por voz", "code") == "1"
    # petición DISTINTA → no dedup
    assert dispatch.find_duplicate("busca un piso de alquiler en Madrid por menos de 900 euros", "web") is None
    # una tarea que ya NO está viva no cuenta
    dispatch._SESSIONS["1"].status = "done"
    assert dispatch.find_duplicate(
        "Implementar en el widget youtube la capacidad de ampliarse a pantalla completa por voz", "code") is None


def test_listener_dedups_second_identical_escalation(fresh_db, fake_backend, monkeypatch):
    """Con una tarea VIVA, una 2ª escalada casi idéntica se INYECTA, NO relanza (el bug de los dos chips). Se
    pre-siembra una sesión viva para no depender del timing de arranque de la 1ª."""
    from nucleo.flash import escalate
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    injected: list = []

    async def _fake_inject(which, msg):
        injected.append((which, msg))
        return [which]
    monkeypatch.setattr(dispatch, "inject", _fake_inject)

    async def run():
        bus.reset(); escalate.reset()
        # tarea VIVA ya en curso sobre el widget youtube
        dispatch._SESSIONS["live"] = SessionRecord(
            task_id="live", kind="code", status="running",
            goal="Implementar en el widget youtube la capacidad de ampliarse a pantalla completa por voz")
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        # re-escalada casi idéntica (como la del bug: llegó en un turno ambiente)
        escalate.escalate_to_slowbrain(
            "Implementar en el widget youtube la capacidad de ampliarse a pantalla completa por voz rápido",
            context={"kind": "code"})
        await asyncio.sleep(0.2)
        new_keys = [k for k in dispatch._SESSIONS if k != "live"]
        stop.set(); await asyncio.sleep(0.05); task.cancel()
        return new_keys

    new_keys = asyncio.run(run())
    assert new_keys == []                        # NO se creó una 2ª sesión
    assert injected and injected[0][0] == "live" and "rápido" in injected[0][1]   # se inyectó a la viva


def test_listener_consumes_escalate_requested(fresh_db, fake_backend):
    from nucleo.flash import escalate

    async def run():
        bus.reset()
        escalate.reset()
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)               # deja que se suscriba
        tid = escalate.escalate_to_slowbrain("busca un piso")   # publica escalate.requested por el bus
        # espera a que el listener lo despache y lo marque resuelto. Margen holgado: desde el fix de
        # compose_context (auditoría 2026-07-14) el despacho paga un recall REAL (~2s con reranker local).
        done = False
        for _ in range(300):
            if not any(p["id"] == tid for p in escalate.pending()):
                done = True
                break
            await asyncio.sleep(0.05)
        stop.set()
        await asyncio.sleep(0.05)
        task.cancel()
        return done, fake_backend.get("last")

    done, b = asyncio.run(run())
    assert done is True                          # la escalada quedó resuelta (escalate.finish)
    assert b is not None and "busca un piso" in b.seen_prompt   # el listener despachó la petición al worker
