"""nucleo/scheduler.py — cron PROPIO del cerebro v2 (V2-005 · T71).

Sustituye al **cron nativo de Hermes** (`brains/hermes/cron.py`, que muere con Hermes en V2-009). Las tareas
programadas se **persisten en `memory.journal`** (continuidad tras reinicio) y las dispara el loop orquestador
(`nucleo/loop.py`, ~1 Hz). No hay proceso ni binario externo: el disparo y la entrega viven en NUESTRO proceso.

Formatos de `schedule` (mismos que enseñaba el brief de cron, agnósticos del idioma en el parser):
  - **una vez, relativo**: `"30m"`, `"2h"`, `"1d"`, `"45s"` (también `"en 30m"`, `"in 2h"`, `"+1h"`).
  - **una vez, FECHA ABSOLUTA**: `"2026-08-19 09:00"` (o `"2026-08-19T09:00"`, o `"2026-08-19"` → 09:00 por
    defecto). Añadido 2026-08-18 (V2-121): sin esto NO había forma de programar un aviso de una sola vez en un
    DÍA concreto — «recuérdamelo el miércoles» solo se podía expresar como un cron 5-campos `0 9 * * 3`, que es
    RECURRENTE (avisa todos los miércoles para siempre) o contando días a mano (`2d`), que es frágil y opaco.
    El caso de uso `remember-and-remind-deadline` lo midió: el aviso no llegaba a existir.
  - **recurrente por intervalo**: `"every 30m"`, `"cada 2h"`.
  - **cron 5-campos**: `"0 9 * * *"` (min hora dom mes dow; soporta `* , - /`).

El scheduler NO ejecuta un agente por tarea (Hermes lo hacía): entrega el `prompt` de la tarea por los raíles
proactivos (voz + UI), que es lo que necesita un recordatorio. Una tarea con condición/razonamiento se escala
al SlowBrain (V2-006/007); hasta entonces el prompt se entrega tal cual (recordatorio autocontenido).
"""
from __future__ import annotations

import re
import time

from memory import journal as _journal

_KIND = "scheduled"

# Unidades de tiempo → segundos (parser agnóstico del idioma).
_UNIT_S = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "day": 86400}

_RE_EVERY = re.compile(r"^(?:every|cada)\s+(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", re.I)
_RE_ONCE = re.compile(r"^(?:in\s+|en\s+|\+)?(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", re.I)
# Fecha ABSOLUTA de una sola vez (V2-121): ISO `YYYY-MM-DD` con hora opcional separada por espacio o `T`.
# Deliberadamente SOLO ISO: el prompt del cerebro ya lleva la fecha de hoy y de mañana en ese mismo formato
# (`prompt.live_state`), así que el modelo no tiene que inventarse una gramática de fechas — traduce «el
# miércoles» a la fecha que ya tiene delante. Un formato local ambiguo (19/08 vs 08/19) se rechaza a propósito.
_RE_ABS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?$")
# Hora por defecto cuando se da un día sin hora: un recordatorio «el miércoles» se entrega por la mañana.
_DEFAULT_HOUR = 9


# ── una expresión de tiempo HABLADA → la fecha ISO que `parse_schedule` ya entiende ──────────────────────
#
# V2-146 — «apúntame que el jueves… y recuérdamelo el miércoles» acabó con `scheduled_jobs.created` VACÍO: el
# modelo prometió el aviso en prosa y no emitió ninguna tag. El ejecutor de crons funciona (verificado en
# V2-134), el prompt lo pide con todas las letras — lo que faltaba era el backstop, y un backstop necesita
# resolver «el miércoles» POR SU CUENTA.
#
# Esto NO contradice la decisión de arriba de aceptar solo ISO en `parse_schedule`. Aquella dice que el MODELO
# no tenga que inventarse una gramática de fechas teniendo la lista de días delante, y sigue en pie: esta
# función no la usa el modelo, la usa el backstop cuando el modelo ya no hizo nada. Y es aritmética, no
# adivinación: devuelve "" en cuanto la expresión no es inequívoca, porque un aviso mal fechado no se nota
# hasta el día que no suena (V2-121).
_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_RE_AT_HOUR = re.compile(r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\b|\bat\s+(\d{1,2})(?::(\d{2}))?\b", re.I)
_RE_DAY_OF_MONTH = re.compile(r"\bel\s+d[ií]a\s+(\d{1,2})\b|\bon\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)


def _strip_accents_sched(text: str) -> str:
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()


def parse_when(text: str, now: float | None = None) -> str:
    """A spoken time expression → the `YYYY-MM-DD [HH:MM]` spec `parse_schedule` accepts, or "" if unsure.

    Only the forms that are unambiguous on their own: tomorrow, a named weekday, and a day of the month, each
    with an optional «a las HH(:MM)». «esta tarde», «pronto» or «cuando puedas» return "" on purpose — a
    reminder placed on a guessed date is worse than none, because the operator believes it is set.
    """
    now = time.time() if now is None else now
    n = _strip_accents_sched(text)
    if not n.strip():
        return ""
    m = _RE_AT_HOUR.search(n)
    hh, mi = _DEFAULT_HOUR, 0
    if m:
        hh = int(m.group(1) or m.group(3) or _DEFAULT_HOUR)
        mi = int(m.group(2) or m.group(4) or 0)
        if not (0 <= hh <= 23 and 0 <= mi <= 59):
            return ""

    def _iso(ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(ts)) + f" {hh:02d}:{mi:02d}"

    def _at(day_ts: float) -> float:
        lt = time.localtime(day_ts)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mi, 0, 0, 1, -1))

    if re.search(r"\b(manana|tomorrow)\b", n):
        return _iso(now + 86400)
    # TWO weekdays in the same sentence («el jueves tengo que… y recuérdamelo el miércoles») is ambiguous for a
    # backstop: which one is the reminder is exactly what we cannot know without understanding the sentence.
    # Answering "" sends it back to whoever has the context, instead of picking whichever the dict listed first.
    found = {t for name, t in _WEEKDAYS.items() if re.search(rf"\b{name}\b", n)}
    if len(found) > 1:
        return ""
    if found:
        target = found.pop()
        today = time.localtime(now).tm_wday
        delta = (target - today) % 7
        if delta == 0 and _at(now) <= now:          # today, but the hour already went by → next week
            delta = 7
        return _iso(now + delta * 86400)
    m = _RE_DAY_OF_MONTH.search(n)
    if m:
        day = int(m.group(1) or m.group(2))
        if not (1 <= day <= 31):
            return ""
        lt = time.localtime(now)
        for month_offset in (0, 1):
            year, month = lt.tm_year + (lt.tm_mon + month_offset - 1) // 12, (lt.tm_mon + month_offset - 1) % 12 + 1
            try:
                ts = time.mktime((year, month, day, hh, mi, 0, 0, 1, -1))
            except (OverflowError, ValueError):
                return ""
            if ts > now and time.localtime(ts).tm_mday == day:
                return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        return ""
    return ""


# ── parseo del schedule ──────────────────────────────────────────────────────────────────────────────────
def parse_schedule(spec: str, now: float | None = None) -> dict | None:
    """Devuelve un dict de schedule normalizado (con `next_run` en epoch) o None si no se reconoce."""
    now = time.time() if now is None else now
    s = (spec or "").strip()
    if not s:
        return None
    m = _RE_EVERY.match(s)
    if m:
        iv = int(m.group(1)) * _UNIT_S[m.group(2).lower()]
        if iv <= 0:
            return None
        return {"type": "interval", "interval_s": iv, "next_run": int(now + iv),
                "display": f"cada {m.group(1)}{m.group(2).lower()}"}
    m = _RE_ONCE.match(s)
    if m:
        iv = int(m.group(1)) * _UNIT_S[m.group(2).lower()]
        if iv <= 0:
            return None
        return {"type": "once", "interval_s": iv, "next_run": int(now + iv),
                "display": f"en {m.group(1)}{m.group(2).lower()}"}
    m = _RE_ABS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4)) if m.group(4) is not None else _DEFAULT_HOUR
        mi = int(m.group(5)) if m.group(5) is not None else 0
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 23 and 0 <= mi <= 59):
            return None
        try:
            # mktime interpreta la tupla en HORA LOCAL, que es la del operador — igual que `next_cron`.
            ts = time.mktime((y, mo, d, hh, mi, 0, 0, 1, -1))
        except (OverflowError, ValueError):
            return None
        # Una fecha ya PASADA no se programa: entregar «ya» un aviso del jueves pasado es peor que rechazarlo,
        # porque el operador cree que quedó puesto para el que viene.
        if ts <= now:
            return None
        return {"type": "once", "interval_s": int(ts - now), "next_run": int(ts),
                "display": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))}
    if len(s.split()) == 5:
        nr = next_cron(s, now)
        if nr is not None:
            return {"type": "cron", "cron": s, "next_run": int(nr), "display": s}
    return None


def _advance(sch: dict, fired_at: float) -> dict | None:
    """Recalcula `next_run` tras un disparo. `once` → None (se cierra). Recurrente → siguiente ocurrencia."""
    t = sch.get("type")
    if t == "once":
        return None
    if t == "interval":
        sch = dict(sch)
        sch["next_run"] = int(fired_at + sch["interval_s"])
        return sch
    if t == "cron":
        nr = next_cron(sch["cron"], fired_at)
        if nr is None:
            return None
        sch = dict(sch)
        sch["next_run"] = int(nr)
        return sch
    return None


# ── cron 5-campos (min hora dom mes dow) ─────────────────────────────────────────────────────────────────
_FIELD_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]  # dow: 0=domingo


def _parse_field(field: str, lo: int, hi: int) -> set[int] | None:
    """Expande un campo cron a un conjunto de valores permitidos. None si es inválido."""
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            return None
        step = 1
        if "/" in part:
            base, _, st = part.partition("/")
            if not st.isdigit() or int(st) <= 0:
                return None
            step = int(st)
            part = base
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            aa, _, bb = part.partition("-")
            if not (aa.isdigit() and bb.isdigit()):
                return None
            a, b = int(aa), int(bb)
        elif part.isdigit():
            a = b = int(part)
        else:
            return None
        if a < lo or b > hi or a > b:
            return None
        out.update(range(a, b + 1, step))
    return out or None


def _cron_fields(expr: str):
    parts = expr.split()
    if len(parts) != 5:
        return None
    fields = []
    for raw, (lo, hi) in zip(parts, _FIELD_BOUNDS):
        f = _parse_field(raw, lo, hi)
        if f is None:
            return None
        # ¿estaba restringido (no era comodín completo)?
        restricted = raw.strip() != "*" and not raw.strip().startswith("*/")
        fields.append((f, restricted, raw.strip()))
    return fields


def next_cron(expr: str, after: float) -> float | None:
    """Siguiente epoch (>= after+60s, alineado al minuto) que casa la expresión cron. None si no casa en ~1 año
    o la expresión es inválida. Búsqueda minuto a minuto (acotada) — barata para uso ocasional."""
    fields = _cron_fields(expr)
    if fields is None:
        return None
    (mins, _, _), (hours, _, _), (doms, dom_r, _), (months, _, _), (dows, dow_r, _) = fields
    # arranca en el próximo minuto entero tras `after`.
    t = (int(after) // 60 + 1) * 60
    cap = t + 366 * 86400
    while t <= cap:
        lt = time.localtime(t)
        # cron: si dom Y dow están restringidos, casa si CUALQUIERA de los dos casa (semántica estándar).
        dow0 = lt.tm_wday  # lunes=0..domingo=6
        cron_dow = (dow0 + 1) % 7  # cron: domingo=0..sábado=6
        dom_ok = lt.tm_mday in doms
        dow_ok = cron_dow in dows
        day_ok = (dom_ok or dow_ok) if (dom_r and dow_r) else (dom_ok and dow_ok)
        if lt.tm_min in mins and lt.tm_hour in hours and lt.tm_mon in months and day_ok:
            return float(t)
        t += 60
    return None


# ── CRUD de tareas programadas (respaldado por memory.journal) ───────────────────────────────────────────
def create(prompt: str, schedule: str, name: str = "", repeat: str = "",
           now: float | None = None) -> dict:
    """Programa una tarea. Devuelve {'ok':bool,'id':int|None,'schedule':dict|None,'error':str|None,'display':str}."""
    now = time.time() if now is None else now
    # `repeat` heredado del brief de Hermes: si viene, fuerza recurrencia por intervalo.
    spec = schedule
    if repeat and not _RE_EVERY.match((schedule or "").strip()):
        spec = f"every {repeat}"
    sch = parse_schedule(spec, now=now)
    if sch is None:
        return {"ok": False, "id": None, "schedule": None,
                "error": f"schedule no reconocido: {schedule!r}", "display": ""}
    title = (name or prompt or "recordatorio").strip()[:120]
    detail = {"kind": _KIND, "schedule": sch, "prompt": (prompt or "").strip(),
              "name": (name or "").strip(), "fire_count": 0}
    jid = _journal.add(title, status="pending", detail=detail)
    return {"ok": True, "id": jid, "schedule": sch, "error": None, "display": sch.get("display", "")}


def _scheduled(entries: list[dict]) -> list[dict]:
    return [e for e in entries if (e.get("detail") or {}).get("kind") == _KIND]


def list_jobs(active_only: bool = True) -> list[dict]:
    """Tareas programadas en una vista amigable (para el brief del cerebro / verificación)."""
    entries = _journal.list_entries(status="pending" if active_only else None)
    out = []
    for e in _scheduled(entries):
        d = e["detail"]
        sch = d.get("schedule") or {}
        out.append({
            "id": e["id"], "name": d.get("name") or e["title"], "prompt": d.get("prompt") or "",
            "schedule": sch.get("display") or "", "type": sch.get("type"),
            "next_run": sch.get("next_run"), "status": e["status"], "fire_count": d.get("fire_count", 0),
        })
    return out


def for_brain() -> str:
    """Brief de arranque para el cerebro: las tareas programadas activas (o vacío si no hay). Mismo papel que
    tenía el brief de cron de Hermes en el kickoff — sin nada que enseñar, no añade ruido al prompt."""
    jobs = list_jobs(active_only=True)
    if not jobs:
        return ""
    lines = ["[SCHEDULED TASKS — your own reminders/proactive jobs; mention only if relevant]"]
    for j in jobs[:12]:
        when = j.get("schedule") or "?"
        what = (j.get("name") or j.get("prompt") or "recordatorio").strip()
        lines.append(f"  · {what} — {when}")
    return "\n".join(lines)


def due(now: float | None = None) -> list[dict]:
    """Tareas programadas VENCIDAS (pending, next_run <= now). Devuelve las entradas de journal (con detail)."""
    now = time.time() if now is None else now
    out = []
    for e in _scheduled(_journal.list_entries(status="pending")):
        nr = (e["detail"].get("schedule") or {}).get("next_run")
        if isinstance(nr, (int, float)) and nr <= now:
            out.append(e)
    return out


def mark_fired(entry: dict, now: float | None = None) -> dict | None:
    """Marca una tarea como disparada. Una-vez → status='done'. Recurrente → recalcula next_run (sigue pending).
    Devuelve el schedule nuevo (o None si se cerró)."""
    now = time.time() if now is None else now
    d = dict(entry["detail"])
    sch = d.get("schedule") or {}
    d["fire_count"] = int(d.get("fire_count", 0)) + 1
    d["last_fired"] = int(now)
    nxt = _advance(sch, now)
    if nxt is None:
        d["schedule"] = sch
        _journal.update(entry["id"], status="done", detail=d)
        return None
    d["schedule"] = nxt
    _journal.update(entry["id"], status="pending", detail=d)
    return nxt


def cancel(ref: str) -> bool:
    """Cancela una tarea por nombre (o id numérico). Devuelve True si canceló alguna."""
    ref = (ref or "").strip()
    if not ref:
        return False
    hit = False
    for e in _scheduled(_journal.list_entries(status="pending")):
        d = e["detail"]
        if str(e["id"]) == ref or (d.get("name") or "").strip().lower() == ref.lower() \
                or (e.get("title") or "").strip().lower() == ref.lower():
            _journal.update(e["id"], status="done", detail=d)
            hit = True
    return hit
