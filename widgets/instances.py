"""widgets/instances.py — QUÉ TARJETA quiere decir el operador cuando una pieza tiene varias abiertas (V2-259 F3).

Petición del operador, literal: «si hay 2 widgets de results y el usuario dice "cierra los resultados", la orden
debería generar una pregunta de: ¿cuál de las 2 búsquedas cierro, la del coche o la del fontanero?».

Es una AMBIGÜEDAD NUEVA, de otro eje que la que ya resolvía `runtime.identify()`. Aquella decide QUÉ PIEZA
(«resultados» → `results`) y pregunta cuando no hay match de nombre o alias (V2-082). Ésta llega después: la
pieza está clara y lo que no se sabe es CUÁL DE SUS TARJETAS. Antes no podía existir, porque la única pieza
instanciada era el navegador y sus tarjetas se cierran solas al terminar la tarea; desde que la hoja se instancia
(V2-259) el operador tiene dos cajas idénticas de nombre delante.

TRES DECISIONES, y cada una tiene su contraria obvia:

  · **Preguntar, no elegir.** Con dos hojas, cerrar «la primera» o «la última» acierta la mitad de las veces y la
    otra mitad le borra al operador la búsqueda que estaba mirando — sin decírselo. Es la misma regla de V2-082,
    que ya está escrita: sin certeza, se PREGUNTA.
  · **La pregunta nombra los ENCARGOS, no los ids.** «¿results::t1 o results::t2?» no es una pregunta, es un
    volcado. El título de cada hoja ya es lo que pidió el operador («Fontaneros en Madrid centro»), así que la
    pregunta se escribe sola con lo que él mismo dijo.
  · **Una sola decisión para los TRES sitios que cierran.** `voice/engine/llm/providers/nucleo.py` emite
    `widget/close` con id desde tres puntos distintos (el guard cerrar≠borrar, el backstop del turno y el
    fallback de canvas). Escribir la regla tres veces es exactamente cómo se llega a que falte en uno — cuarta
    vez esta semana, y en V2-256 la copia que faltaba costó que un envío fallara en silencio.

Puro y sin estado: recibe lo que hay abierto y devuelve la decisión. Fail-soft en el sentido que importa aquí —
ante la duda sobre si hay ambigüedad, NO pregunta: una pregunta espuria en cada cierre sería peor que el fallo
que esto quita.
"""
from __future__ import annotations

SEP = "::"


def base_of(widget_id) -> str:
    """`results::t7` → `results`. Un id sin instancia es su propia base."""
    return str(widget_id or "").split(SEP, 1)[0].strip().lower()


def instances_of(base: str, open_ids) -> list[str]:
    """Las tarjetas ABIERTAS de esta pieza, con su id completo y en el orden en que las reportó el canvas."""
    b = base_of(base)
    out: list[str] = []
    for wid in (open_ids or []):
        w = str(wid or "").strip()
        if w and base_of(w) == b and w not in out:
            out.append(w)
    return out


def _label(widget_id: str) -> str:
    """Cómo se llama ESTA tarjeta para el operador: el encargo que pintó, no su id.

    Solo la hoja sabe titularse hoy; para cualquier otra pieza se cae al sufijo, que al menos distingue. Nunca
    revienta: esto se llama en mitad de un turno de voz.
    """
    inst = str(widget_id or "").split(SEP, 1)[1] if SEP in str(widget_id or "") else ""
    if base_of(widget_id) == "results":
        try:
            from widgets.results import data as _sheet
            t = str((_sheet.view_data(inst) or {}).get("title") or "").strip()
            # «Resultados» es el relleno que `view_data` pone cuando no hay título (setdefault), no un nombre:
            # devolverlo haría que dos hojas sin encargo se llamaran igual y la pregunta no distinguiera nada.
            if t and t.lower() != "resultados":
                return t
        except Exception:  # noqa: BLE001
            pass
    return inst or str(widget_id or "")


def _distinguibles(etiquetas: list[str], ids: list[str]) -> list[str]:
    """Una pregunta que no se puede contestar no es una pregunta.

    Dos hojas sin título, o con el mismo, producirían «¿cuál cierro, «Resultados» o «Resultados»?», que es peor
    que no preguntar: obliga al operador a contestar algo que no distingue nada. Cuando las etiquetas colisionan
    se les añade lo único que seguro es distinto — su instancia.
    """
    if len(set(etiquetas)) == len(etiquetas):
        return etiquetas
    out = []
    for et, wid in zip(etiquetas, ids):
        inst = str(wid).split(SEP, 1)[1] if SEP in str(wid) else str(wid)
        out.append(f"{et} ({inst})" if et and et != inst else inst)
    return out


_EVERY_RE = _re.compile(
    r"\b(?:ambos|ambas|todas?|todos|both|all\s+of\s+them|"
    r"(?:los|las)\s+(?:dos|tres|cuatro|\d+))\b", _re.I)


def wants_every(text: str) -> bool:
    """Does the operator mean ALL the open cards of this piece, rather than one of them?

    Measured 2026-08-31 (session `7cab1afd`): with two results sheets open the operator said «cierra los dos»
    and got the disambiguation question BACK — «¿cuál te enseño, "…" o "…"?» — then said «cierra las dos» and
    got it again. He had answered it. The question asks WHICH ONE and the answer was BOTH, an option the
    resolver had no way to express, so every rephrasing round-tripped into the same question.

    A QUANTIFIER, not a verb table: «los dos», «ambas», «todas», «both». What to DO with them is already
    decided by the caller — this only says how many cards the order reaches.
    """
    if not text:
        return False
    return bool(_EVERY_RE.search(_strip_accents(str(text))))


def _strip_accents(text: str) -> str:
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c))


def resolve_close(target, open_ids, text: str = "") -> dict:
    """A QUÉ tarjeta va un «ciérralo».

    Devuelve `{"id": <id a cerrar> | None, "ids": [...], "ask": <pregunta> | "", "options": [...]}`:

      · el operador ya nombró una instancia (`results::t7`)          → esa, sin preguntar
      · la pieza tiene 0 o 1 tarjetas abiertas                       → el id tal cual (cerrar una ya cerrada es
                                                                        un no-op inofensivo, y ese era el
                                                                        comportamiento de siempre)
      · dos o más, y el turno dice CUÁNTAS («los dos», «todas»)      → todas, sin preguntar (V2-530)
      · dos o más                                                    → `ask`, y `id` a None

    `ids` es la lista a cerrar y viene SIEMPRE — un llamante que recorra `ids` está bien escrito para los cuatro
    casos, y ésa es la diferencia con leer `id` y perderse la respuesta «los dos» en dos de los tres sitios que
    cierran. `id` se conserva para no romper a nadie.
    """
    tid = str(target or "").strip()
    if not tid:
        return {"id": None, "ids": [], "ask": "", "options": []}
    if SEP in tid:
        return {"id": tid, "ids": [tid], "ask": "", "options": []}   # ya vino desambiguado; nada que preguntar
    abiertas = instances_of(tid, open_ids)
    if len(abiertas) <= 1:
        _one = abiertas[0] if abiertas else tid
        return {"id": _one, "ids": [_one], "ask": "", "options": abiertas}
    if wants_every(text):
        return {"id": None, "ids": list(abiertas), "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    if len(etiquetas) == 2:
        cuales = f"«{etiquetas[0]}» o «{etiquetas[1]}»"
    else:
        cuales = ", ".join(f"«{e}»" for e in etiquetas[:-1]) + f" o «{etiquetas[-1]}»"
    return {"id": None, "ids": [], "ask": f"Tienes {len(abiertas)} abiertas: ¿cuál cierro, {cuales}?",
            "options": abiertas}


def resolve_show(target, open_ids, text: str = "") -> dict:
    """A QUÉ tarjeta va un «enséñamelo» — el espejo de `resolve_close`, medido por el lado contrario (V2-300).

    Ronda 24 de `search-buy-guitar__es` (2026-08-24): la hoja del encargo (`results::58c1af-1`) estaba ABIERTA
    con 20 filas, el operador pidió ver un resultado, el modelo mostró `results` a secas… y el canvas abrió la
    caja PELADA, vacía — «Te lo abro, aunque de momento está vacío» sobre una pantalla con la entrega al lado.
    El guard de V2-209 hizo su parte (dijo la verdad sobre la caja equivocada); lo que faltaba era abrir la
    caja CORRECTA. Mismo contrato que el cierre: la base con UNA instancia viva delante resuelve a esa
    instancia; con varias se PREGUNTA nombrando encargos; sin ninguna, la base de siempre.
    """
    tid = str(target or "").strip()
    if not tid:
        return {"id": None, "ids": [], "ask": "", "options": []}
    if SEP in tid:
        return {"id": tid, "ids": [tid], "ask": "", "options": []}   # ya vino desambiguado
    abiertas = instances_of(tid, open_ids)
    if not abiertas:
        return {"id": tid, "ids": [tid], "ask": "", "options": []}   # sin instancias: la base, como siempre
    if len(abiertas) == 1:
        return {"id": abiertas[0], "ids": [abiertas[0]], "ask": "", "options": abiertas}
    if wants_every(text):
        return {"id": None, "ids": list(abiertas), "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    if len(etiquetas) == 2:
        cuales = f"«{etiquetas[0]}» o «{etiquetas[1]}»"
    else:
        cuales = ", ".join(f"«{e}»" for e in etiquetas[:-1]) + f" o «{etiquetas[-1]}»"
    return {"id": None, "ids": [], "ask": f"Tienes {len(abiertas)} abiertas: ¿cuál te enseño, {cuales}?",
            "options": abiertas}
