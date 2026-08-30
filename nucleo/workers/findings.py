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

import re as _re

#: A monetary amount as sources actually write one: $1,299.99 · 199,99 € · €249 · USD 249 · 249 USD · £99.
#: Currencies, not categories — recognising money is domain-agnostic; recognising products would not be.
_AMOUNT_RE = _re.compile(
    r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£]|€)|(?:USD|EUR|GBP)\s?\d[\d.,]*|\d[\d.,]*\s?(?:USD|EUR|GBP))",
    _re.I)


def _lone_amount(text: str) -> str:
    """The ONE monetary amount `text` names, or "" when it names none — or several (V2-471).

    Several amounts is ambiguity («was $399 now $279», «from $199 to $499») and picking one would be
    inventing a datum with the shape of an observation; absence is honest and `fila()` says it out loud."""
    hits = [h.strip() for h in _AMOUNT_RE.findall(str(text or ""))]
    return hits[0][:20] if len(hits) == 1 else ""


#: Un enlace, como lo escribe cualquier fuente. Reconocer un enlace es agnóstico del dominio; reconocer un
#: producto no lo sería.
_URL_RE = _re.compile(r"https?://\S{4,}", _re.I)

#: El ENVOLTORIO de una tool: su propia transcripción, con el JSON de enlaces dentro. Es ESTRUCTURA (un
#: array de objetos detrás de dos puntos), no una frase — por eso no hace falta reconocer el idioma en que
#: cada CLI redacta su cabecera, que es la carrera que este repo lleva perdiendo desde V2-364.
_ENVELOPE_RE = _re.compile(r':\s*\[\s*\{\s*"')


def looks_like_a_finding(text: str) -> bool:
    """¿Este texto TRAE algo, o solo CUENTA lo que pasó?

    V2-511. `_maybe_hand_web` empuja el texto CRUDO de cualquier paso web que no sea `is_error`, y una tool
    que devuelve un rechazo CON ÉXITO no lo es. Medido en `cheapest-monitor__us` (20260830-130649) con la
    hoja VACÍA y 17 notas ofrecidas al cerebro: siete eran errores HTTP o negativas del propio worker
    («The server returned HTTP 404…», «Based on the content provided, I'm unable to summarize…») y **once
    eran el envoltorio del buscador del CLI** («Web search results for query: … Links: [{"title":…»). Cero
    fichas. El juez llevaba cuatro rondas archivando «presenta candidatos irrelevantes» y el agente no
    elegía mal: le dábamos eso.

    DOS cortes, los dos ESTRUCTURALES — no una lista de frases en inglés, que es la cinta de correr que
    V2-364 ya midió («perseguir el idioma es una carrera que no se gana») y que además dejaría fuera a
    cualquier CLI que redacte su cabecera de otra forma:

      · un ENVOLTORIO de tool (JSON de enlaces dentro) es su transcripción, no un resultado que nadie vetó;
      · un hallazgo trae un DATO DURO —un enlace o un importe—. Una narración sobre la página no trae
        ninguno de los dos, y ese es justo su parecido de familia: cuenta, no entrega.

    COSTE ACEPTADO Y DICHO: un hallazgo cuyo único dato accionable sea un TELÉFONO (el encargo de servicio
    de V2-240) no pasa este corte por esta puerta. No se añade aquí a propósito — «nueve a catorce dígitos»
    sobre prosa libre es la trampa que V2-321 pagó (una fecha leída como teléfono), y la hoja SÍ conserva el
    teléfono por su propio camino. Antes de ensancharlo, medirlo.
    """
    t = " ".join(str(text or "").split())
    if not t:
        return False
    if _ENVELOPE_RE.search(t):
        return False
    return bool(_URL_RE.search(t) or _AMOUNT_RE.search(t))


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
    # V2-511 — lo que CUENTA lo que pasó no se empuja como si TRAJERA algo. V2-510 arregló el imperativo
    # (una página no es un candidato); esto quita de en medio lo que ni siquiera es una página.
    if not looks_like_a_finding(body):
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
            # V2-510 — ESTO ES UNA PISTA HASTA QUE SE DEMUESTRE QUE ES UN CANDIDATO, y el imperativo lo tiene
            # que decir. Lo que vuelve de una búsqueda son casi siempre PÁGINAS: titulares de comparativa, la
            # portada de una tienda, el cuerpo de un 403. Ordenar «dáselo con nombre, precio y enlace» sobre
            # eso es ordenar ofrecer un artículo como si fuera el producto — medido en `cheapest-monitor__us`
            # (20260830-125532): el turno 4 entregó «The 6 Best Budget And Cheap Monitors of 2026 -
            # RTINGS.com» mientras los ocho monitores REALES esperaban en la hoja.
            f"OJO CON LO QUE ES: lo que vuelve de una búsqueda suele ser una PÁGINA —el titular de una "
            f"comparativa, un listado, un error del sitio—, y una página NO es un candidato. NÓMBRALO EN ESTE "
            f"TURNO diciendo lo que ES: si trae ya la cosa concreta con su nombre y su precio, dásela como "
            f"resultado; si es un artículo, un buscador o un error, cuéntalo como por dónde vas a mirar y "
            f"NUNCA lo ofrezcas como una opción para elegir. No digas que no hay resultados ni que sigues "
            f"buscando sin más.")
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
        # V2-376 — LO QUE VUELVE DE UNA BÚSQUEDA ES UNA PISTA, NO UN CANDIDATO, y hasta ahora entraba en la
        # hoja sin distinguirse de una ficha extraída de un listado. Medido en
        # `weekend-adventure-sports-bilbao__es` (2026-08-27): **52 «candidatos con nombre»** de UNA sola
        # fuente, y sus títulos eran páginas —«Descensos de Barranquismo en Vizcaya: 9 precios y ofertas
        # 2026», «Bilbao despliega ocho escenarios de música gratis», «Top actividad en Bilbao - Reserva con
        # cancelación gratis»—. La misma forma que los ocho títulos de Google que se contaron como coches de
        # alquiler el mismo día.
        #
        # V2-320 NO se deshace y esto es lo que hay que conservar: buscar es una forma legítima de resolver
        # «actividades cerca de X», así que sus hallazgos son hallazgos y la hoja no puede quedarse vacía. Lo
        # que faltaba es que la fila DIGA lo que es. Viaja por `facts`, que es vocabulario que la hoja ya
        # conserva —es por donde va el teléfono— así que no hace falta tocar el contrato del widget.
        rows = [{"title": str(r.get("title") or "").strip(),
                 "subtitle": str(r.get("snippet") or "").strip()[:160],
                 "url": str(r.get("url") or "").strip(),
                 "facts": [{"label": "Origen", "value": "búsqueda web"}]}
                for r in (res.get("results") or [])[:4] if isinstance(r, dict)]
        rows = [r for r in rows if r["title"]]
        # V2-471 — the price the snippet already NAMES travels as the row's datum. Measured in
        # `cheapest-monitor__us` round 12: 46 rows, all `price: None`, while titles carried the figure
        # («…S2725QS for $279.99») — the model's «let me confirm the price» loop was honest, and the
        # delivery backstop cannot append what the rows do not carry. One unambiguous amount in the title
        # (else exactly one in the snippet) is the source's own claim; with several amounts nothing is
        # guessed — absence is said by `fila()`, a guess is invented data (V2-430's whole family).
        for r in rows:
            p = _lone_amount(r["title"]) or _lone_amount(r.get("subtitle") or "")
            if p:
                r["price"] = p
        if not rows:
            return 0
        from widgets.results import intake
        return intake.push(rows, sheet=str(getattr(rec, "sheet", "") or ""),
                           source_name=f"búsqueda web ({str(res.get('source') or 'web')})")
    except Exception:  # noqa: BLE001
        return 0                              # best-effort: perder una fila es malo, tumbar el turno es peor
