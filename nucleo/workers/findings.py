"""nucleo/workers/findings.py — lo que un worker ENCUENTRA llega a la conversación en cuanto existe.

V2-223 cerró esto para lo que extrae el NAVEGADOR: el hallazgo se empuja como nota de sistema en el momento en
que aparece, no al final de la sesión. Lo que quedaba fuera —y es el mismo agujero con otra puerta— es lo que
devuelve una BÚSQUEDA WEB, que en un worker es la vía que más veces produce el dato bueno ya limpio.

Medido por el arnés el 2026-08-21 en `cheapest-monitor`, leyendo la observabilidad entera: los eventos
`kind='search'` (`🌐 web ↩`) traían

    «Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €»
    «Alurin CoreVision 27" IPS 4K Freesync — 149,99 €»

exactamente lo que el operador había pedido, en texto limpio. **Búsquedas 7, respuestas 5, notas al cerebro
desde ese canal 0.** Y el porqué: **5 de 8 workers devolvieron `ok:false`** — se caen antes de entregar, y el
texto bueno se va con ellos. Zaelar dijo «la búsqueda se ha caído sin terminar», que era LA VERDAD.

Tres decisiones que hacen que esto no se convierta en ruido:

  · **El JUICIO se queda en el cerebro.** La nota entrega el hecho y nombra la prueba; no ordena anunciarlo.
    Una orden de «di esto» acabaría ofreciendo el primer resultado de una búsqueda fallida como la respuesta.
  · **UNA sola instrucción** (V2-226): la bifurcación va DENTRO del imperativo, nunca como segunda orden.
  · **Se recorta, no se resume, y se dice cuánto se dejó fuera** (doctrina de `observability/evidence.py`). Una
    respuesta de búsqueda puede ser una página entera; lo que se empuja es su principio, con la cuenta de lo
    que falta, y nunca una versión reescrita por nosotros.
"""
from __future__ import annotations

MAX_CHARS = 700          # lo que cabe en una nota sin convertir la conversación en un volcado
MIN_CHARS = 12           # por debajo no hay hallazgo que contar («ok», «done», una línea vacía)

#: task_id → firmas ya entregadas. La MISMA respuesta repetida no es un hallazgo nuevo; una búsqueda repetida
#: sí lo sería si trajera otra cosa, así que se compara por CONTENIDO y no por el hecho de haber buscado.
_HANDED: dict[str, set] = {}


def clip(text: str) -> str:
    """El principio del hallazgo, con la cuenta de lo que queda fuera. Nunca una versión reescrita."""
    t = " ".join(str(text or "").split())
    if len(t) <= MAX_CHARS:
        return t
    return t[:MAX_CHARS].rstrip() + f"… [+{len(t) - MAX_CHARS} caracteres más en el registro]"


def forget(task_id) -> None:
    """La sesión terminó: su memoria de hallazgos se va con ella."""
    _HANDED.pop(str(task_id), None)


def render_search(res: dict, k: int = 4) -> str:
    """`{answer, results:[{title,snippet,url}]}` → el texto que se le entrega al cerebro.

    Se prefiere `answer` cuando la fuente ya lo sintetizó (Perplexity/Tavily/AI Overview): es lo que esa fuente
    devolvió, no una reescritura nuestra. Sin él, las primeras filas TAL CUAL. Aquí no se juzga cuál sirve — eso
    es del cerebro — y por eso tampoco se reordena.
    """
    if not isinstance(res, dict):
        return ""
    ans = " ".join(str(res.get("answer") or "").split())
    if ans:
        return ans
    rows = []
    for r in (res.get("results") or [])[:max(1, k)]:
        if not isinstance(r, dict):
            continue
        bits = [str(r.get("title") or "").strip()[:90], str(r.get("snippet") or "").strip()[:160],
                str(r.get("url") or "").strip()[:120]]
        row = " — ".join(b for b in bits if b)
        if row:
            rows.append(row)
    return "; ".join(rows)


def hand_web_finding(task_id, text: str, goal: str = "") -> bool:
    """Empuja al cerebro lo que una búsqueda web acaba de devolver. Devuelve si se empujó.

    Fail-soft entero: esto corre dentro del bucle de eventos de un worker vivo y no puede tumbarlo.
    """
    body = clip(text)
    if len(body) < MIN_CHARS:
        return False
    key = str(task_id)
    seen = _HANDED.setdefault(key, set())
    sig = body[:200]
    if sig in seen:
        return False
    seen.add(sig)
    what = str(goal or "").strip()[:70] or "la tarea de fondo"
    try:
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] Una búsqueda web ha devuelto esto, trabajando en «{what}»: {body}. Nadie más lo sabe: no "
            f"está en la conversación hasta que tú lo digas, y el worker puede morirse antes de entregarlo. "
            f"NÓMBRALO EN ESTE TURNO y, en la misma frase, di si sirve: si responde a lo que pidió el operador, "
            f"dáselo con nombre, precio o dato y enlace; si no responde, dilo y di qué haces ahora. No digas que "
            f"no hay resultados ni que sigues buscando sin más.")
        return True
    except Exception:  # noqa: BLE001
        return False


def _row(i: dict) -> str:
    """One extracted row as the conversation needs it. The PHONE travels with it: in a service errand it is the
    datum that RESOLVES («call this number») and the one that separates a business card from a directory link."""
    bits = [str(i.get("title") or "").strip()[:80], str(i.get("price") or "").strip()[:24],
            str(i.get("tel") or "").strip()[:24], str(i.get("url") or "").strip()[:120]]
    return " — ".join(b for b in bits if b)


def hand_sheet_finding(task_id, items, goal: str = "") -> bool:
    """The FINAL sweep's rows → the conversation. Returns whether it pushed.

    WHY THIS EXISTS. `results.intake.push` is the one door for the rows (V2-257) but it has no note path — the
    note is the caller's job, and of the three callers only two do it (`act_api._hand_over`, `owner.py`). The
    third, `dispatch._finalize_web`, does its own `extract_listings()` when the worker finishes or dies and
    writes those rows to the sheet with nobody telling the conversation. Measured 2026-08-24: rows landed in the
    sheet 42-113 s before the last turn and the agent still said «todavía no tengo nada».

    ONLY IF NOBODY HAS TOLD IT YET, and the condition is deliberately about the TAB and not about these rows:
    `act_api._HANDED` holds the tabs whose extraction already went out as a note. If the tab is in there the
    conversation has been told, and the final sweep is mostly the same page again — a second note would be the
    same findings twice, which reads as «it found more» when it found the same.
    """
    rows = [_row(i) for i in (items or []) if isinstance(i, dict)]
    rows = [r for r in rows if r][:3]
    if not rows:
        return False
    try:
        from widgets.navegador.act_api import _HANDED as _already
        if str(task_id) in _already:
            return False
    except Exception:  # noqa: BLE001
        pass                                  # cannot tell → tell the conversation; silence is the worse failure
    what = str(goal or "").strip()[:70] or "la tarea del navegador"
    tail = f" (y {len(items) - len(rows)} más)" if len(items or []) > len(rows) else ""
    try:
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] La tarea del navegador ha terminado y esto es lo que quedó en la página, trabajando en "
            f"«{what}»: {'; '.join(rows)}{tail}. Ya está en la hoja de resultados, pero NADIE se lo ha dicho al "
            f"operador todavía. NÓMBRALO EN ESTE TURNO y di si sirve: si responde a lo que pidió, dáselo con "
            f"nombre, precio o dato y enlace; si no responde, dilo y di qué haces ahora. No digas que no hay "
            f"resultados.")
        return True
    except Exception:  # noqa: BLE001
        return False


def hand_search_rows(rec, res: dict) -> int:
    """A search return → the errand's SHEET. Returns how many rows were handed over.

    V2-320, measured on `kid-friendly-activity-nearby` (2026-08-25 12:37): a worker resolved the errand by
    SEARCH alone — 709 s alive, 8 web searches, 7 returns — and the sheet stayed empty the whole time, because
    a search return had exactly one path out: `hand_web_finding` → a note the brain reads once. The rows were
    never rejected by the sheet (`intake._to_item` keeps a title+url row without a price); they simply had no
    door. Searching is a legitimate way to resolve «activities near X», so its findings are findings.

    Same door as everything else (V2-257: `results.intake.push`), same rows the NOTE carries (`render_search`'s
    top-k — one yardstick for «what the conversation saw» and «what the sheet holds»). Untitled rows (bare
    Perplexity citations) drop at the door, which is the door's own honesty rule. The sheet dedups by
    title+url, so eight overlapping searches converge instead of piling.
    """
    try:
        rows = [{"title": str(r.get("title") or "").strip(),
                 "subtitle": str(r.get("snippet") or "").strip()[:160],
                 "url": str(r.get("url") or "").strip()}
                for r in (res.get("results") or [])[:4] if isinstance(r, dict)]
        rows = [r for r in rows if r["title"]]
        if not rows:
            return 0
        from widgets.results import intake
        return intake.push(rows, sheet=str(getattr(rec, "sheet", "") or ""),
                           source_name=f"búsqueda web ({str(res.get('source') or 'web')})")
    except Exception:  # noqa: BLE001
        return 0                              # best-effort: perder una fila es malo, tumbar el turno es peor
