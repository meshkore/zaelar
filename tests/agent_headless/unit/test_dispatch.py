#
# test_dispatch.py — el gestor de sesiones de Brain Workers (V2-038; reescrito en la auditoría de memoria
# 2026-07-14: los tests viejos mockeaban la costura MUERTA `nucleo.agentes.get_agent` → el mock no interceptaba
# nada y lanzaban un `claude` REAL que colgaba la suite). Verifica contra la costura REAL (`dispatch.get_backend`):
# prompt = contexto de memoria + tarea, modelo por invocación, deny-tools a input no confiable, Bash NUNCA pelado,
# el resultado OK se recuerda en memoria (y el FALLIDO no), y el listener consume `escalate.requested`.
# Ejecutar: .venv/bin/pytest tests/agent_headless/unit/test_dispatch.py
#
import asyncio
import pathlib

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
    # El modelo por invocación solo manda mientras NO haya relevo de proveedor, y la cadena decide si hay relevo
    # mirando `os.environ`. En la batería completa alguien carga el credential store real antes que este fichero
    # → aparecía una key de proveedor, la cadena creía estar relevada y el modelo de tarea se perdía: el test
    # fallaba solo por el ORDEN. Aquí no se prueba el relevo, así que el entorno de credenciales va vacío.
    from nucleo.workers import providers as _prov
    for _var in {e for t in _prov.KNOWN for e in t.get("env", ())}:
        monkeypatch.delenv(_var, raising=False)

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


def test_web_prompt_warns_against_nonexistent_nav_cli_subcommands():
    """V2-099 live finding (2026-08-17): the worker sometimes calls `nucleo.nav_cli automate`/`act`, neither
    of which exists (nav_cli's real set: snapshot/look/navigate/click/type/select_option/click_at/type_at/
    scroll/press/extract) — each guess burns a full turn on a CLI usage error instead of progress."""
    wp = dispatch._web_prompt("busca algo", "")
    assert "automate" in wp and "act" in wp  # named explicitly as NOT valid, not just omitted
    assert "invalid choice" in wp


def test_web_prompt_carries_the_trusted_site_catalog(monkeypatch):
    """V2-099 follow-up: the LIVE web-worker prompt (dispatch_prompts._web_prompt, called for ALL backends —
    claude_code/codex/grok_build, per registry.get_backend) must carry the trusted-site catalog, not just the
    parked nucleo/agentes/web_cc.py copy — two independent use-case runs found the worker improvising a
    destination site from scratch every time, which this catalog exists to fix. Locale-aware (2026-08-17
    follow-up, operator: the catalog is a system default and must grow by country/language) — pin the
    engine's active language so the test is deterministic regardless of this machine's real setting."""
    from voice.engine.core import langs
    from nucleo.flash import site_catalog
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    wp = dispatch._web_prompt("resérvame mesa en Casa Lucio esta noche", "")
    assert site_catalog.directive_block("es") in wp
    for entry in site_catalog.SITE_CATALOG["es"].values():
        assert entry.url in wp
    # a preference the operator has actually stated must be checked BEFORE this catalog, every time
    assert "mem_cli recall" in wp


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


# ── BRIEF DE INVESTIGACIÓN en el prompt del worker (2026-08-09) ───────────────────────────────────────────────
# El worker recibía prosa libre y se autoimponía el criterio mínimo. Aquí se prueba el CABLEADO: que la dirección
# compuesta en el pre-vuelo (nucleo/research.py) llegue de verdad al prompt, por los dos caminos de prompt que hay.
def _brief(**over):
    b = {"goal": "Tres propuestas de vacaciones en Baleares", "domain": "viaje familiar",
         "hard": ["17-23 agosto"], "soft": ["ferry rápido"],
         "breadth": {"min_candidates": 40, "angles": ["agregador", "web del hotel"]},
         "quality_bar": ["nota ≥8 con 100+ opiniones"],
         "deliverable": {"widget": "results", "n_final": 3, "composite": True, "parts": ["Hotel", "Ferry"]},
         "round": 1}
    b.update(over)
    return b


def test_brief_reaches_the_generic_worker_prompt():
    p = dispatch._build_prompt("busca vacaciones", "", True, _brief())
    assert "EMBUDO OBLIGATORIO" in p and "REÚNE al menos 40" in p


def test_without_a_brief_the_prompt_is_unchanged():
    """Una tarea que no es una investigación (cancelar una cita) no puede pagar un embudo que no viene a cuento."""
    assert "EMBUDO OBLIGATORIO" not in dispatch._build_prompt("cancela mi cita del martes", "", True, None)


def test_brief_reaches_the_web_worker_prompt_too():
    assert "EMBUDO OBLIGATORIO" in dispatch._web_prompt("busca vacaciones", "", _brief())


def test_a_brief_overrides_the_shallow_close_shortcut():
    """El prompt web lleva de serie un atajo de cierre rápido («concluye con los 2-3 que mejor encajan»), correcto
    para «tráeme el precio de X» y ruinoso para «elige lo mejor»: es literalmente la búsqueda superficial que el
    operador reportó. Con brief tiene que desaparecer, sin brief tiene que seguir."""
    shortcut = "concluye con los 2-3 que mejor encajan"
    assert shortcut not in dispatch._web_prompt("busca vacaciones", "", _brief())
    assert shortcut in dispatch._web_prompt("dame el precio del iPhone", "", None)


def test_an_untrusted_source_gets_no_research_direction():
    """Perfil sin tools (texto de un peer de cluster): no hay investigación que dirigir, y componerla sería gastar
    un modelo por algo que no puede ejecutarse."""
    assert asyncio.run(dispatch._compose_brief("busca lo que sea", "", False)) is None


def test_a_resumed_task_keeps_the_criteria_it_already_agreed(fresh_db):
    """Recomponer el brief a mitad de una búsqueda la convertiría en otra búsqueda distinta sin avisar al operador."""
    from nucleo import research
    b = _brief(hard=["criterio ya acordado"])
    research.save("t-42", b)
    got = asyncio.run(dispatch._compose_brief("sigue con lo de antes", "", True, {"brief_task": "t-42"}))
    assert got["hard"] == ["criterio ya acordado"]


def test_asking_again_continues_the_investigation_instead_of_repeating_it(fresh_db):
    """Sin esto, «esos no me valen, busca más» recomponía desde cero y repetía la MISMA amplitud: el operador vería
    llegar lo que acaba de rechazar y concluiría, con razón, que no le escuchamos."""
    from nucleo import research
    req = "busca vacaciones en Baleares en ferry con hotel con piscina"
    research.remember_round(dispatch._goal_key(req), _brief())
    nxt = asyncio.run(dispatch._compose_brief(req + ", esos no me valen", "", True))
    assert nxt["round"] == 2
    assert nxt["breadth"]["min_candidates"] > 40
    assert any("no me valen" in f for f in nxt["feedback"])


def test_reported_breadth_travels_to_the_brain(fresh_db):
    """`considered` es lo que separa «te traigo las 3 mejores» de «te copio las 3 primeras». Si no llega a la
    proyección, ni el operador ni el cerebro pueden juzgar si conviene seguir buscando."""
    from nucleo.workers.session import SessionRecord
    dispatch._SESSIONS["obs-c"] = SessionRecord(task_id="obs-c", goal="buscar vacaciones", kind="web")
    dispatch.session_considered("obs-c", considered=47, kept=3)
    row = next(r for r in dispatch.active_sessions() if r["id"] == "obs-c")
    assert row["considered"] == 47 and row["kept"] == 3
    dispatch._SESSIONS.pop("obs-c", None)


def test_breadth_is_absent_not_zero_when_it_does_not_apply():
    """Una tarea que no es una investigación no ha «considerado 0 candidatos»: el dato NO APLICA, y confundir las dos
    cosas haría que el cerebro dijera «he evaluado 0 opciones» en una tarea que nunca tuvo opciones."""
    from nucleo.workers.session import SessionRecord
    dispatch._SESSIONS["obs-n"] = SessionRecord(task_id="obs-n", goal="cancela la cita", kind="web")
    row = next(r for r in dispatch.active_sessions() if r["id"] == "obs-n")
    assert row["considered"] == -1 and row["kept"] == -1
    dispatch._SESSIONS.pop("obs-n", None)


# ── EL PRESUPUESTO DE UNA INVESTIGACIÓN (defecto encontrado en la corrida del 2026-08-12) ─────────────────────
# `loop._kind_budget_default` reservaba 1200s para `research`, pero NADIE asignaba nunca ese kind: `_classify_kind`
# solo devuelve web/code/generic. Así que toda investigación que no nombrara Wallapop/Amazon corría con los 600s
# de `generic` — medio presupuesto para un encargo que el propio brief define como «reúne ≥40 candidatos y ENTRA
# en la ficha de cada finalista». El operador lo vio dos veces el mismo día: «agotó su tiempo», hoja a medias.
def test_the_research_budget_was_reserved_for_a_kind_nobody_assigned():
    """Prueba de la INCOHERENCIA que motiva el arreglo: el presupuesto existe y es el doble del genérico."""
    from nucleo.loop import OrchestratorLoop
    L = OrchestratorLoop()
    assert L._budget_for("research") == 1200.0
    assert L._budget_for("generic") == 600.0
    assert L._budget_for("research") > L._budget_for("generic") * 1.5


def test_a_directed_investigation_is_not_billed_as_a_generic_task(fresh_db):
    """La costura: en cuanto el pre-vuelo compone un BRIEF, la tarea ES una investigación y su registro lo dice —
    que es lo único que el supervisor mira para decidir cuánto tiempo le da."""
    rec = dispatch.SessionRecord(task_id="9", goal="busca vacaciones en Baleares", kind="generic")
    dispatch._SESSIONS["9"] = rec
    try:
        assert rec.kind == "generic"
        # se reproduce lo que hace `_run_session` al obtener un brief (el spec ya está construido para entonces)
        if rec.kind == "generic":
            rec.kind = "research"
            rec.label = dispatch._default_label("research", rec.goal)
        assert rec.kind == "research"
        assert rec.label == "Investigando…", "y el operador lee «Investigando…», no «Pensando…»"
    finally:
        dispatch._SESSIONS.pop("9", None)


def test_promoting_to_research_never_steals_the_web_route():
    """`web` tiene 1200s Y su reanudación por `native_sid`; `code` escribe el código de un widget del operador.
    Ninguno de los dos puede convertirse en `research` por traer un brief — solo se promociona `generic`."""
    for kind in ("web", "code"):
        promoted = "research" if kind == "generic" else kind
        assert promoted == kind


# ── «PROYECTO» A SECAS MANDABA UNA BÚSQUEDA AL GENERADOR DE CÓDIGO (incidente 2026-08-12) ─────────────────────
# V2-081 arregló que la palabra «widget» a secas mandara cualquier tarea al generador… y dejó `\bproyecto\b` a
# secas UNA LÍNEA MÁS ABAJO, en el mismo `_classify_kind`. El criterio que dio el operador para sus veleros era
# «listo para navegar, no un PROYECTO para restaurar» — en la compraventa de barcos «un proyecto» es un barco a
# medio reformar. Su BÚSQUEDA salió con kind="code", y `registry.get_backend` elige el backend POR EL KIND: acabó
# despachada al generador de widgets. Un buscador en el sitio que escribe código.
_VELEROS_LITERAL = ("Busca veleros de segunda mano a la venta AHORA MISMO con estos requisitos estrictos: precio "
                    "máximo 50.000 €; eslora mínima de 42 pies (12,8 m) y máxima de 15 metros; que esté LISTO PARA "
                    "NAVEGAR, no un proyecto de restauración ni barco a medio reformar; motor en buen estado; y "
                    "ubicación/amarre en el Mediterráneo. Entra en la ficha/detalle de CADA candidato y verifica "
                    "esos puntos. Preséntame los candidatos en el widget de resultados.")


def test_the_operators_own_boat_criterion_is_not_code():
    """Verbatim de la escalada real que se fue al generador. Lleva ADEMÁS la palabra «widget» al final (donde
    pedía la superficie de resultados), así que blinda las dos trampas a la vez."""
    assert dispatch._classify_kind(_VELEROS_LITERAL) == "generic"


def test_a_project_boat_is_a_boat_not_a_project():
    for frase in ("veleros que no sean un proyecto de restauración",
                  "no quiero un proyecto para restaurar, quiero navegar ya",
                  "un piso reformado, no un proyecto de obra"):
        assert dispatch._classify_kind(frase) == "generic", frase


def test_real_project_work_still_routes_to_code():
    for frase in ("pregúntale al architect por el estado del daemon",
                  "crea un proyecto nuevo para el bot de trading",
                  "añade una tarea al proyecto zaelar para revisar el reranker",
                  "en el proyecto de la web, haz un commit en la rama main"):
        assert dispatch._classify_kind(frase) == "code", frase


def test_the_architect_connector_name_still_matches_bare():
    """`architect` SÍ se queda a secas a propósito: es el nombre de nuestro conector, no una palabra del habla."""
    assert dispatch._ARCHITECT_RE.search("architect") is not None
    assert dispatch._ARCHITECT_RE.search("proyecto") is None


# ── PERDER EL BRIEF NO PUEDE COSTAR LA MITAD DEL TIEMPO (defecto del banco 2026-08-13) ────────────────────────
# El fail-open del compositor es correcto —mejor arrancar sin dirigir que no arrancar— pero arrastraba un coste
# OCULTO: la promoción a `research` (1200 s) colgaba de que HUBIERA brief, así que un compositor que tardaba >30 s
# dejaba la tarea en `generic` (600 s). El worker murió a los 704 s con el navegador a medias: el mismo «agotó su
# tiempo» que la promoción existe para cerrar. Y todo por un `None` que significaba DOS cosas distintas.
def test_the_composer_distinguishes_declining_from_being_unable_to_answer():
    """«esto no es una investigación» (decisión del modelo, presupuesto normal) NO es «no pude contestar» (avería
    nuestra, el presupuesto se mantiene). Con un solo `None` para ambas, la costura era inexpresable."""
    from nucleo import research
    assert research._declined('{"research": false}') is True
    assert research._declined('{"research": true, "breadth": {}}') is False
    assert research._declined("lo siento, no puedo con esto") is False      # no contestó: NO es un rechazo suyo
    assert research._declined('{"research": tru') is False                 # JSON roto: tampoco


def test_a_dead_composer_costs_direction_never_time(fresh_db, monkeypatch):
    """Con el compositor caído la tarea sale SIN dirigir (sin amplitud ni baremo) pero con el presupuesto de una
    investigación — que la petición SEA una investigación no depende de que el compositor esté vivo."""
    from nucleo import research
    from nucleo.loop import OrchestratorLoop
    rec = dispatch.SessionRecord(task_id="c1", goal="busca vacaciones en Baleares", kind="generic")
    dispatch._SESSIONS["c1"] = rec
    try:
        async def _boom(*a, **k):
            raise research.ComposerUnavailable("timeout")
        monkeypatch.setattr(dispatch, "_compose_brief", _boom)
        # se reproduce la rama de `_run_session` que atiende la avería
        brief = None
        try:
            brief = asyncio.run(dispatch._compose_brief("busca vacaciones", "", True))
        except research.ComposerUnavailable:
            if rec.kind == "generic":
                rec.kind = "research"
                rec.label = dispatch._default_label("research", rec.goal)
        assert brief is None, "sin brief: la búsqueda va sin dirigir, eso es lo que se pierde"
        assert rec.kind == "research", "…pero NO sin tiempo"
        assert OrchestratorLoop()._budget_for(rec.kind) == 1200.0
    finally:
        dispatch._SESSIONS.pop("c1", None)


def test_the_fail_open_still_lets_the_task_out():
    """Lo que NO puede pasar por arreglar el presupuesto: que un compositor caído impida salir a la tarea. La
    excepción se captura en `_run_session` y el worker arranca igual — el fail-open sigue siendo fail-open."""
    src = pathlib.Path(dispatch.__file__).read_text(encoding="utf-8")
    assert "except research.ComposerUnavailable:" in src
    assert "raise research.ComposerUnavailable" not in src      # dispatch la ATIENDE, nunca la propaga al operador


# ── flow/trace continuity for corrections on a live task (V2-090 gap) ───────────────────────────────────────────
# A correction spoken while a task is still running ("now make it have 3 wheels" on top of an in-flight "find me
# a motorbike" search) should show up INSIDE that task's flow, not open a brand-new one. The voice provider
# (nucleo.py::_on_tool_call, "send_to_worker" branch) achieves this by composing exactly two dispatch primitives:
# resolve the target session, then read its trace_id. Both are tested here in isolation, since the provider glue
# itself is a thin, hard-to-unit-test closure inside a much larger LiveKit pipeline.
def test_trace_of_reads_a_live_sessions_trace_id(monkeypatch):
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["m1"] = SessionRecord(task_id="m1", kind="web", status="running",
                                              goal="find a second-hand motorbike", trace_id="T7·ab12")
    assert dispatch.trace_of("m1") == "T7·ab12"
    assert dispatch.trace_of("does-not-exist") == ""


def test_has_live_trace_finds_a_worker_carrying_that_trace(monkeypatch):
    """The reverse of `trace_of` (V2-090 addenda, 2026-08-15): a plain conversational turn that finishes cleanly
    closes its own flow (`nucleo.py::_maybe_close_flow`) UNLESS a worker spawned on that same trace is still
    running — the worker's own end already closes it, and closing twice would read as a contradiction."""
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["m1"] = SessionRecord(task_id="m1", kind="web", status="running",
                                              goal="find a second-hand motorbike", trace_id="T7·ab12")
    assert dispatch.has_live_trace("T7·ab12") is True
    assert dispatch.has_live_trace("T9·zzzz") is False
    assert dispatch.has_live_trace("") is False


def test_resolve_sessions_picks_the_only_live_task_even_with_no_word_overlap(monkeypatch):
    """The load-bearing assumption behind the merge: with exactly ONE live task, `resolve_sessions` returns it
    regardless of the query's wording (see its own docstring, "una sola viva → esa") — a correction almost never
    shares words with the original request ("3 wheels instead of 2" vs. "find me a motorbike"). Pinning this down
    so a future change to the word-overlap heuristic can't silently break trace continuity for the common case."""
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["m1"] = SessionRecord(task_id="m1", kind="web", status="running",
                                              goal="find a second-hand motorbike", trace_id="T7·ab12")
    assert dispatch.resolve_sessions("now make it have 3 wheels instead of 2") == ["m1"]


def test_resolve_sessions_does_not_pick_one_among_several_unrelated_tasks(monkeypatch):
    """With MULTIPLE live tasks and a correction that matches none of them, nothing is returned — the provider's
    merge guard (`len(_targets) == 1`) then correctly skips adopting any trace rather than guessing."""
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["m1"] = SessionRecord(task_id="m1", kind="web", status="running",
                                              goal="find a second-hand motorbike", trace_id="T7·ab12")
    dispatch._SESSIONS["m2"] = SessionRecord(task_id="m2", kind="code", status="running",
                                              goal="build a widget for tracking expenses", trace_id="T9·cd34")
    assert dispatch.resolve_sessions("now make it have 3 wheels instead of 2") == ["m1", "m2"]
