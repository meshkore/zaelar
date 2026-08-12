"""nucleo/rehydrate.py — REHIDRATACIÓN: recoger el trabajo que un reinicio dejó a medias.

El registro de sesiones vivas (`dispatch._SESSIONS`) es RAM: cuando el proceso muere —un `make restart`, un crash,
la homeostasis reviviendo el worker de voz— los Brain Workers en vuelo mueren **en silencio**. Observado en vivo
(2026-08-12, 12:19:46 → 12:21:15): el operador pidió una búsqueda de veleros en Wallapop, el worker abrió su
pestaña, y un reinicio lo borró del mapa. Ni un evento, ni una línea en el ledger, ni una palabra al operador: la
pantalla siguió pintando un navegador que ya no existía, y al recargar quedó en blanco. Ese es exactamente el
estado que engaña (regla del operador: un estado que puede engañar tiene que VERSE).

Esta pieza es el gancho de arranque que cierra el ciclo. Tres decisiones:

  · **Vive en un módulo aparte y se ejecuta UNA vez, al arrancar.** No es un subsistema: es una función que se
    dispara cuando se da la circunstancia (había trabajo en vuelo al morir) y no vuelve a tocar nada. El resto
    del sistema no la conoce; `dispatch` solo le deja el rastro (`remember`) y el `reset` lo borra (`forget`).
  · **El rastro NO va al ESTADO raíz** (el que viaja en cada prompt), va a `sys_kv` — es estado de PROCESO, no
    conciencia del operador; mismo criterio que el ledger de workers (V2-079). Un timestamp suelto en el estado
    se colaría en el prompt como «Sessions at: 1786530075.0.» (`memory.api.compose_state` vuelca los escalares
    custom).
  · **Nunca inventa: reanuda lo reanudable y ENTIERRA el resto, siempre visible.** Todo lo que estaba en vuelo
    entra en el ledger como `interrumpido` (lo ve el operador en «Procesos») y emite su evento. Lo que se puede
    continuar se re-escala con el mismo objetivo, que es lo que hace que la reanudación CONTINÚE en vez de
    empezar de cero: si era una gestión web, `dispatch._WEB_RESUME` (persistido) le devuelve el `native_sid` y
    el worker retoma su razonamiento.

Lo que NO se reanuda solo, a propósito:
  · `kind="code"` — el generador REESCRIBE el código de un widget. Reanudar eso sin que nadie lo pida puede pisar
    lo que el operador tenía. Se reporta y se queda quieto.
  · Sesiones PAUSADAS (⏻) — el operador las congeló a mano; revivirlas al arrancar sería desobedecerle.
  · Sesiones que esperaban RESPUESTA del operador — la reanudación real es que él conteste, y la pregunta ya no
    existe (el proceso que la sostenía murió). Se reporta.
  · Nada más viejo que `STALE_S` — «busca veleros» de hace tres días no es trabajo pendiente, es arqueología.

Anti-bucle: el rastro se CONSUME al leerlo (una caída en bucle no multiplica workers) y cada objetivo lleva un
contador durable (`RESUME_CAP`) para que un crash reproducible no respawnee lo mismo indefinidamente.
"""
from __future__ import annotations

import time

from loguru import logger

# sys_kv (NO el estado raíz): rastro de lo que estaba vivo + contador anti-bucle por objetivo.
_KEY = "live_sessions"
_MARKS = "rehydrate_marks"

STALE_S = 1800.0          # > 30 min sin señales de vida → se reporta, no se reanuda
RESUME_CAP = 2            # veces que un MISMO objetivo puede resucitar por rehidratación
MAX_RESUME = 3            # techo por arranque (un reinicio no dispara una tormenta de workers)
MARK_TTL_S = 6 * 3600.0   # los contadores caducan: mañana el mismo objetivo vuelve a tener sus 2 vidas
RESUME_DELAY_S = 6.0      # margen para que el listener de escaladas esté suscrito y el arranque respire

_LIVE = ("queued", "running")
# El generador de código queda FUERA del auto-resume (reescribe ficheros del operador); el resto continúa.
_NO_AUTO_RESUME_KINDS = ("code",)


# ── rastro durable (best-effort: su fallo no puede tumbar un arranque ni el cierre de una sesión) ─────────────
def remember(sessions: list[dict], *, now: float | None = None) -> None:
    """Deja el rastro de las sesiones VIVAS. Lo llama `dispatch.sync_state()`, que ya está coalescada y solo
    escribe cuando la proyección cambia de verdad — así esto no añade churn a SQLite."""
    try:
        from memory import api as _mem
        live = [s for s in (sessions or []) if isinstance(s, dict) and str(s.get("status") or "") in _LIVE]
        if not live:
            _mem.kv_del(_KEY)            # nada en vuelo → no dejamos rastro que rehidratar
            return
        _mem.kv_set(_KEY, {"at": float(now or time.time()), "sessions": live})
    except Exception:
        pass


def forget() -> None:
    """Borra el rastro. Lo llama el RESET del operador («empezamos de cero»): tras matar el trabajo a mano, el
    siguiente arranque NO debe resucitarlo. También se llama al consumirlo en `at_boot`."""
    try:
        from memory import api as _mem
        _mem.kv_del(_KEY)
    except Exception:
        pass


def snapshot() -> dict | None:
    """El rastro tal cual quedó, o None. Lectura pura."""
    try:
        from memory import api as _mem
        snap = _mem.kv_get(_KEY)
        if isinstance(snap, dict) and snap.get("sessions"):
            return snap
    except Exception:
        pass
    return None


def _goal_key(goal: str) -> str:
    """Firma estable de un objetivo (para el contador anti-bucle). Reusa la de `dispatch` — misma noción de "la
    misma gestión" que la continuidad web — y cae a una normalización local si no está disponible."""
    try:
        from nucleo.dispatch import _goal_key as _gk
        return _gk(goal or "")
    except Exception:
        return " ".join(sorted((goal or "").lower().split()))


def _marks(now: float) -> dict:
    """Contadores por objetivo, ya podados por TTL."""
    try:
        from memory import api as _mem
        raw = _mem.kv_get(_MARKS)
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items()
                if isinstance(v, dict) and (now - float(v.get("ts") or 0)) <= MARK_TTL_S}
    except Exception:
        return {}


def _bump(keys: list[str], now: float) -> None:
    try:
        from memory import api as _mem
        marks = _marks(now)
        for k in keys:
            ent = marks.get(k) or {"n": 0}
            marks[k] = {"n": int(ent.get("n") or 0) + 1, "ts": now}
        _mem.kv_set(_MARKS, marks)
    except Exception:
        pass


# ── el NÚCLEO de la decisión: puro, sin I/O → se puede probar entero ─────────────────────────────────────────
def classify(sessions: list[dict], *, at: float, now: float, marks: dict | None = None) -> dict:
    """Reparte lo que estaba en vuelo en `resume` (continúa sola) y `buried` (se reporta y se queda quieta).
    Cada entrada enterrada lleva `why` — el motivo EXACTO, que es lo que el operador necesita leer.

    `at` = cuándo se vio vivo por última vez; `now` = ahora. Sin efectos: quien decide no escribe."""
    marks = marks or {}
    age = max(0.0, float(now) - float(at))
    stale = age > STALE_S
    resume: list[dict] = []
    buried: list[dict] = []
    for s in (sessions or []):
        if not isinstance(s, dict) or str(s.get("status") or "") not in _LIVE:
            continue
        goal = str(s.get("goal") or "").strip()
        kind = str(s.get("kind") or "generic")
        ent = {"id": str(s.get("id") or "?"), "goal": goal, "kind": kind,
               "phase": str(s.get("phase") or ""), "age_s": int(age)}
        n = int((marks.get(_goal_key(goal)) or {}).get("n") or 0)
        if not goal:
            ent["why"] = "sin objetivo que reanudar"
        elif s.get("paused"):
            ent["why"] = "la habías pausado tú"
        elif str(s.get("waiting_on") or "") == "user":
            ent["why"] = "esperaba tu respuesta y la pregunta se perdió con el proceso"
        elif kind in _NO_AUTO_RESUME_KINDS:
            ent["why"] = "toca el código de un widget: no lo reanudo sin que me lo pidas"
        elif stale:
            ent["why"] = f"demasiado vieja ({int(age // 60)} min sin señales)"
        elif n >= RESUME_CAP:
            ent["why"] = f"ya la reanudé {n} vez/veces y volvió a caer"
        elif len(resume) >= MAX_RESUME:
            ent["why"] = f"tope de {MAX_RESUME} reanudaciones por arranque"
        else:
            resume.append(ent)
            continue
        buried.append(ent)
    return {"resume": resume, "buried": buried, "age_s": int(age), "stale": stale}


# ── el gancho: UNA llamada, al arrancar ──────────────────────────────────────────────────────────────────────
def at_boot(*, now: float | None = None, schedule: bool = True, delay: float | None = None) -> dict:
    """Recoge lo que el proceso anterior dejó a medias. Es el ÚNICO punto de entrada (lo llama el lifespan del
    server tras montar el dispatcher). No-op silencioso en el caso normal —no había nada en vuelo—, así que
    arrancar limpio no cuesta ni un evento.

    `schedule=False` (tests) devuelve el plan sin re-escalar nada."""
    now = float(now or time.time())
    snap = snapshot()
    # El rastro se CONSUME aquí: si el proceso vuelve a caer en el arranque, no reanudamos dos veces por el mismo
    # rastro. Lo que de verdad siga en vuelo lo volverá a escribir `sync_state` en cuanto se registre.
    forget()
    if not snap:
        return {"found": 0, "resume": [], "buried": []}

    sessions = [s for s in (snap.get("sessions") or []) if isinstance(s, dict)]
    plan = classify(sessions, at=float(snap.get("at") or now), now=now, marks=_marks(now))
    plan["found"] = len(sessions)

    # (1) VISIBLE, sin excepción: todo lo que estaba en vuelo queda en el ledger como `interrumpido` → el operador
    # lo ve en «Procesos» en vez de encontrarse un hueco donde había una tarea.
    try:
        from nucleo.workers import ledger as _ledger
        for ent in plan["buried"] + plan["resume"]:
            _ledger.record_finish(id=str(ent["id"]), kind=ent.get("kind", ""), goal=ent.get("goal", ""),
                                  status="interrumpido", started_at=None,
                                  finished_at=float(snap.get("at") or now), ok=False)
    except Exception:
        pass

    # (2) un evento por decisión — el operador puede leer QUÉ se reanuda y POR QUÉ lo demás no.
    try:
        from voice.observer import emit
        for ent in plan["resume"]:
            emit("task", "🔁 lo reanudo — se cortó al reiniciar", role="system", text=ent["goal"][:160],
                 extra={"id": ent["id"], "kind": ent["kind"], "age_s": ent["age_s"], "cat": "main"})
        for ent in plan["buried"]:
            emit("task", "✂️ se cortó al reiniciar y no la reanudo", role="system", text=ent["goal"][:160],
                 extra={"id": ent["id"], "kind": ent["kind"], "age_s": ent["age_s"],
                        "reason": ent.get("why", ""), "cat": "main"})
    except Exception:
        pass

    if plan["resume"]:
        _bump([_goal_key(e["goal"]) for e in plan["resume"]], now)
        logger.info("rehidratación: reanudo {} tarea(s) cortadas por el reinicio ({} enterradas)"
                    .format(len(plan["resume"]), len(plan["buried"])))
        if schedule:
            _schedule(plan["resume"], RESUME_DELAY_S if delay is None else float(delay))
    elif plan["buried"]:
        logger.info(f"rehidratación: {len(plan['buried'])} tarea(s) cortadas por el reinicio, ninguna reanudable")
    return plan


def _schedule(entries: list[dict], delay: float) -> None:
    """Re-escala en diferido. Diferido a propósito: el listener de escaladas tiene que estar suscrito (si no, el
    evento del bus se publica contra nadie) y el arranque tiene bastante con el prewarm. Mismo patrón que el
    auto-resume de continuidad web (`dispatch._schedule_auto_resume`)."""
    import asyncio

    async def _later() -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
            from nucleo.flash import escalate
            for ent in entries:
                try:
                    escalate.escalate_to_slowbrain(
                        ent["goal"], context={"kind": ent.get("kind") or "generic", "rehydrated": True})
                    logger.info(f"rehidratación: re-escalada «{ent['goal'][:70]}»")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"rehidratación: re-escalar «{ent['goal'][:40]}» falló: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"rehidratación: la reanudación diferida falló: {e}")

    try:
        asyncio.create_task(_later(), name="nucleo:rehydrate-resume")
    except RuntimeError:
        # Sin loop corriendo (llamada desde un script/test) — el plan se devuelve igual, no se reanuda nada.
        logger.warning("rehidratación: no hay loop; no se reanuda (plan devuelto)")
