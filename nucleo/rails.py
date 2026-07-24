"""nucleo/rails.py — RAILS: comportamientos comunes CONDUCIDOS (V2-042, patrón de orquestación del FlashBrain).

Un **RAIL** es un comportamiento habitual que sabemos conducir de una forma determinada — música difusa, vídeo,
estudios de datos, búsquedas complejas en sites, mensajería, agenda, búsquedas recursivas (cron+búsqueda). El
nombre es del operador: son "raíles" por los que circula la acción. Cada rail aporta cuatro piezas MODULARES:

  1. una **cadena determinista en CÓDIGO** (resolver→validar→actuar, p.ej. `nucleo/flash/music_flow.py`) — el
     FlashBrain sigue NO-razonador: él solo dispara la tool; el rail conduce;
  2. su **tool** en `router.TOOLS` (y nada más: el "cuándo SÍ/NO" vive en la descripción, V2-035);
  3. sus **RUNS vivos** — este módulo: registro RAM proyectado al ESTADO (`state.rails`) → el prompt de cada turno
     sabe qué se busca, qué suena, y qué quedó SIN RESOLVER (aislado, con intentos) para continuarlo cuando el
     operador aporte datos ("era de Sinatra");
  4. su **writeback a memoria** (vía tipada `memory.ingest_message(source=…)`) → historial + gustos → zaelar conoce
     al operador y afina las siguientes conducciones.

**Prompts aislados, solo cuando hacen falta** (idea del operador): además del run en el ESTADO, un rail puede
aportar una línea de GUÍA al prompt únicamente mientras tiene un run vivo (`prompt_lines()` ← `_GUIDANCE`) — cero
coste de prompt cuando el rail está en reposo.

Es el hermano LIGERO de las sesiones de `nucleo/dispatch.py` (workers pesados): un run NO es un proceso — es el
ESTADO de una conducción que hace el propio FlashBrain en sus turnos. Diseño:
  · **Singleton por `kind`**: un run nuevo del mismo kind SUSTITUYE al anterior (no se acumulan).
  · **Fallos AISLADOS con TTL**: un run fallido queda `sin_resolver` (15 min) — ni contamina ni se pierde.
  · **Escrituras SIEMPRE off-hot-path**: los callers llaman desde `asyncio.to_thread` (V2-011). `project()` hace
    el `memory.set_state` best-effort (nunca lanza). Transiciones observables (evento `rail` en /debug).
"""
from __future__ import annotations

import threading
import time

from loguru import logger

# kind → run vivo {kind, label, status, detail, attempts, created, updated}
_RUNS: dict[str, dict] = {}
_lock = threading.Lock()

# TTL por estado (segundos): cuánto vive un run sin que nadie lo toque antes de expirar solo.
_TTL = {
    "searching": 10 * 60,        # una búsqueda en curso abandonada
    "sin_resolver": 15 * 60,     # el fallo AISLADO: se conserva para retomarlo, expira si nadie lo retoma
    "playing": 4 * 60 * 60,      # algo sonando (larga: una sesión de música)
    "paused": 60 * 60,
}
_TTL_DEFAULT = 30 * 60

# GUÍA situacional por rail (kind → línea de prompt + estados en que aplica): se INYECTA solo mientras el rail
# tiene un run vivo en ese estado (prompt_lines()). Modular: el prompt no paga rails en reposo.
_GUIDANCE = {
    "music.search": (("sin_resolver",),
                     "Hay una búsqueda de canción SIN RESOLVER en tus rails: si el operador aporta un dato "
                     "(artista, año, otra palabra de la letra), vuelve a llamar a play_music con la query "
                     "ENRIQUECIDA (pista original + dato nuevo)."),
    # Sesión 22:40 2026-07-16: con música sonando, «no se oye» escaló a un worker que investigó la VOZ de zaelar.
    # Con un run de reproducción vivo, TODA queja de audio se refiere a ESA música — y si aun así escalas, la
    # petición debe decirlo (el worker no ve esta conversación).
    "music.playing": (("playing", "paused"),
                      "Hay MÚSICA SONANDO ahora (mírala en tus rails). Si el operador dice que «no se oye», «no "
                      "suena», «súbelo», «quita eso» o cualquier queja/orden de audio, se refiere a ESA música — "
                      "resuélvelo TÚ con play_music (volume_up/resume/pause/stop), no lo trates como un problema "
                      "de tu voz ni del equipo. Si necesitas escalarlo, di EXPLÍCITAMENTE en la petición que se "
                      "trata de la música que está sonando (título incluido)."),
}


def upsert(kind: str, label: str = "", *, status: str = "", detail: str = "", bump: bool = False) -> dict:
    """Crea/actualiza el run de un `kind` (singleton: sustituye al anterior). `bump` incrementa intentos.
    Devuelve el run. Llamar OFF-LOOP (to_thread)."""
    kind = (kind or "").strip()
    if not kind:
        return {}
    now = time.time()
    # V2-044: trace de la frase que CONDUCE este run (ctxvar del turno; viaja por to_thread). Un run nuevo lo
    # adopta; uno vivo lo conserva — así las transiciones posteriores (fail/resolve off-turn) siguen encadenadas.
    try:
        from voice import trace as _trace
        _tid = _trace.current()
    except Exception:
        _tid = ""
    with _lock:
        a = _RUNS.get(kind)
        if a is None or (label and a.get("label") != label):
            # run nuevo (o el mismo kind con OTRO objetivo → sustituye; los intentos empiezan de cero)
            a = {"kind": kind, "label": label or (a or {}).get("label", ""), "status": status or "searching",
                 "detail": detail, "attempts": 1 if bump else 0, "created": now, "updated": now,
                 "trace": _tid}
        else:
            if status:
                a["status"] = status
            if detail:
                a["detail"] = detail
            if label:
                a["label"] = label
            if bump:
                a["attempts"] = int(a.get("attempts") or 0) + 1
            a["updated"] = now
        _RUNS[kind] = a
        snap = dict(a)
    _observe("upsert", snap)
    project()
    return snap


def resolve(kind: str) -> None:
    """El run terminó BIEN → desaparece del estado. Llamar OFF-LOOP."""
    with _lock:
        a = _RUNS.pop((kind or "").strip(), None)
    if a:
        _observe("resolve", a)
    project()


def fail(kind: str, reason: str = "") -> None:
    """El run falló → queda AISLADO como `sin_resolver` (con su label/intentos) hasta que alguien lo retome con
    más datos o expire su TTL. NO desaparece: es el estado que permite continuar («era de Sinatra»)."""
    snap = None
    with _lock:
        a = _RUNS.get((kind or "").strip())
        if a is not None:
            a["status"] = "sin_resolver"
            if reason:
                a["detail"] = reason
            a["updated"] = time.time()
            snap = dict(a)
    if snap:
        _observe("fail", snap)
    project()


def get(kind: str) -> "dict | None":
    with _lock:
        a = _RUNS.get((kind or "").strip())
        return dict(a) if a else None


def live() -> list[dict]:
    """Runs vigentes (barre los expirados por TTL). Orden: más reciente primero."""
    now = time.time()
    with _lock:
        dead = [k for k, a in _RUNS.items()
                if now - float(a.get("updated") or 0) > _TTL.get(a.get("status") or "", _TTL_DEFAULT)]
        for k in dead:
            _RUNS.pop(k, None)
        return sorted((dict(a) for a in _RUNS.values()), key=lambda a: -float(a.get("updated") or 0))


def prompt_lines() -> list[str]:
    """GUÍA situacional de los rails con run vivo — se inyecta al prompt SOLO cuando aplica (idea del operador:
    prompts aislados por comportamiento, cero coste en reposo)."""
    out = []
    for a in live():
        spec = _GUIDANCE.get(a.get("kind") or "")
        if spec and (a.get("status") or "") in spec[0]:
            out.append(spec[1])
    return out


def project() -> None:
    """Proyecta el registro RAM → ESTADO de memoria (`state.rails`). Best-effort, nunca lanza. Los callers ya
    están off-loop (to_thread), así que el write µs de state es seguro (V2-011)."""
    try:
        from memory import api as memory
        memory.set_state({"rails": [
            {"kind": a["kind"], "label": (a.get("label") or "")[:120], "status": a.get("status") or "",
             "detail": (a.get("detail") or "")[:100], "attempts": int(a.get("attempts") or 0)}
            for a in live()[:6]
        ]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"rails.project saltado: {e!r}")


def _observe(op: str, run: dict) -> None:
    """Transición OBSERVABLE (evento `rail` → /debug + SSE): visibilidad de cada conducción. Best-effort."""
    try:
        from voice.observer import emit
        extra = {"kind": run.get("kind"), "status": run.get("status"), "label": (run.get("label") or "")[:80],
                 "attempts": int(run.get("attempts") or 0), "op": op}
        # V2-044: encadena la transición a la frase que conduce el run (aunque ocurra off-turn, p.ej. un fail
        # posterior) + span=rail:<kind> para el nivel 2 del árbol de Trazas.
        _tid = run.get("trace") or ""
        if _tid:
            extra["trace"] = _tid
            extra["span"] = f"rail:{run.get('kind')}"
        emit("rail", f"🛤 {op} {run.get('kind')}", role="system", extra=extra)
    except Exception:
        pass


def clear_all() -> None:
    """Limpieza total (reset/tests)."""
    with _lock:
        _RUNS.clear()
    project()
