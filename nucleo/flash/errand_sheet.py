"""Which SHEET belongs to an errand — the one question V2-432 turned out to hinge on.

Extracted from `live_blocks` on 2026-08-28, and not to dodge a line count: the architecture ratchet fired
while instrumenting this resolution, and it was right to. Resolving the errand's box is a subject of its own —
it has two paths, it is read by three different callers, and when it fails it fails MUTE, which is exactly the
defect measured that night (45 of the 48 rounds whose sheet had named rows had turns where the live block told
the model the task was stalled).

A file that is about one thing can say what it is about. Inside `live_blocks` this was a helper among twenty.
"""
from __future__ import annotations


def _sheet_of_tab(nav_task_id: str) -> str:
    """La hoja de este encargo, resuelta como la resuelve QUIEN ESCRIBE (V2-352).

    Hay dos caminos y el escritor (`navegador.act_api._sheet_for`, que alimenta `_hand_over`) usa los dos:

      1. el SELLO de la pestaña — durable, sobrevive a que al worker le releven o se muera, que es justo cuando
         más falta hace (V2-281). Pero **se escribe una sola vez, en `tasks.create()`**: si el registro aún no
         tenía hoja sellada en ese instante, queda vacío PARA SIEMPRE, y el propio comentario de `create` lo
         avisa. Ese cero es también la «tarjeta fantasma» que el arnés reporta: sin hoja resuelta, los hallazgos
         caen en la caja `results` desnuda, la que no es de nadie.
      2. el REGISTRO de sesiones vivas — sabe contestar mientras el worker viva.

    Los LECTORES se paraban en el primero, y eso les dejaba ciegos justo en la ronda que lo destapó: medido en
    `search-buy-used-car` ronda 12 (1/5), el backstop de entrega emitió su silencio NUEVE veces con `rows=0`
    mientras la hoja tenía DOCE coches con nombre, precio y enlace — escritos por el camino 2, ilegibles por el
    1. El operador preguntó cinco veces «¿ya tienes algo?» y oyó cinco negativas.

    El ORDEN no cambia y es deliberado: sello primero, registro de RESPALDO. Ni más ni menos que el escritor.
    """
    try:
        from widgets.navegador import tasks as _t
        sello = str(((_t.get(str(nav_task_id)) or {}).get("sheet")) or "").strip()
        if sello:
            return sello
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import dispatch as _disp
        _reg = str(_disp.sheet_for_nav_task(str(nav_task_id)) or "").strip()
    except Exception:  # noqa: BLE001
        _reg = ""
    if not _reg:
        # NI SELLO NI REGISTRO, y sin decirlo el fallo es MUDO: se devuelve "" y el prompt se compone como si
        # no hubiera nada, indistinguible de que no lo haya. Firma de V2-432. Aquí porque los dos mueren acá.
        try:
            from voice.observer import emit
            emit("perf", "🧾 hoja del encargo SIN RESOLVER", role="system", extra={"nav_task": str(nav_task_id)})
        except Exception:  # noqa: BLE001 — instrumentar no puede tumbar el prompt
            pass
    return _reg


def boxes_of_tab(nav_task_id: str) -> list[str]:
    """TODAS las cajas que este encargo puede tener, en orden: el sello primero, el registro después.

    `_sheet_of_tab` devuelve la PRIMERA que resuelva, y esa es la identidad correcta para escribir. Para LEER
    no basta, y el 2026-08-28 se midió por qué: en `compare-flights-madrid-lisboa` el bloque vivo miró
    `f1743e-2` siete veces —vacía— mientras las filas estaban en `f1743e-1`, y el prompt le dijo al modelo que
    no tenía nada durante cuatro turnos.

    La causa la documenta `nucleo/sheets.py` y tiene nombre: **«A RELAY IS NOT A NEW ERRAND»**. Cuando el
    proveedor se queda sin cuota, el relanzamiento del MISMO objetivo HEREDA la hoja de su predecesor — pero el
    **sello de la pestaña** «se escribe una sola vez, en `tasks.create()`», y el relevo crea pestaña nueva. Así
    que el sello apunta a la caja nueva (vacía) y los hallazgos siguen en la heredada. El sello no está
    ausente, está RANCIO, y su docstring solo contemplaba lo primero.

    Esto es SOLO PARA LEER (`_sheet_has_rows`, `_sheet_top_rows`): quien escribe resuelve por su cuenta, y
    dárselo aquí no cambia dónde cae ni una fila. Se ordena sello → registro para no invertir la identidad de
    nadie: solo se mira la segunda cuando la primera no tiene lo que se busca.
    """
    fuera: list[str] = []
    for candidato in (_sheet_of_tab(nav_task_id), _registro_de_tab(nav_task_id)):
        c = str(candidato or "").strip()
        if c and c not in fuera:
            fuera.append(c)
    return fuera


def _registro_de_tab(nav_task_id: str) -> str:
    """La hoja que el REGISTRO de sesiones vivas da para esta pestaña — la heredada, en un relevo."""
    try:
        from nucleo import dispatch as _disp
        return str(_disp.sheet_for_nav_task(str(nav_task_id)) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def aviso_sin_filas(nav_task_id: str, cajas: list[str]) -> None:
    """La cara dice que hay algo y la hoja no da ni una fila — el cuarto camino, y el único que quedaba mudo.

    La cara se enciende con `_p["has_results"]` **o** con `_found_candidates`, y ese `or` hace CORTOCIRCUITO:
    si el primero es cierto, `_sheet_has_rows` ni se llama y sus tres avisos no existen. Entonces
    `_sheet_top_rows` resuelve por su cuenta, no encuentra caja con filas, y el turno sale diciendo «ya ha
    encontrado algo, pero sus nombres AÚN NO están escritos» — con los nombres escritos.

    Medido en `reorder-prescription__us` (2026-08-28): tres turnos a 32, 72 y 111 segundos DESPUÉS de que la
    hoja tuviera seis farmacias con nombre y dirección, avisados de que había algo y con cero filas. El modelo
    nombró cero de seis.

    Lleva las CAJAS que miró Y EL CENSO de todas las hojas EN ESE INSTANTE (V2-440), porque sin lo segundo las
    dos causas se ven idénticas y piden arreglos opuestos: si en ese momento NINGUNA hoja tiene filas es un
    DESFASE (el worker aún no ha entregado y el aviso es correcto); si otra caja SÍ las tiene es RESOLUCIÓN
    (miramos donde no era, y ahí sí hay un defecto). El 2026-08-28 se pasaron horas sin poder decidir entre las
    dos leyendo el estado FINAL de la ronda, que es el que ya no distingue nada — para entonces la caja que se
    miró tenía 35 filas y la pregunta era si las tenía cuando se miró.

    El censo es un recuento, nunca contenido: los títulos de la hoja son datos del mundo y esto es una fila de
    observabilidad.
    """
    censo = ""
    try:
        from widgets.results import data as _sheet
        _miradas = {str(c or "").strip() for c in (cajas or [])}
        cuenta: list[tuple[str, int]] = []
        for sid in (_sheet.sheets() or []):
            items = (_sheet.view_data(sid) or {}).get("items") or []
            cuenta.append((str(sid or ""), sum(1 for i in items
                                               if str((i or {}).get("title") or "").strip())))
        # El campo va ACOTADO, así que el ORDEN decide qué sobrevive al corte y no puede ser el del almacén:
        # primero las cajas que se MIRARON (son el ancla de la pregunta — sin ellas el censo no se puede
        # interpretar), después las que más filas tienen. Una hoja con catorce filas explica una ronda; tres
        # con una cada una, no.
        cuenta.sort(key=lambda t: (t[0] not in _miradas, -t[1], t[0]))
        censo = " ".join(f"{sid or '(base)'}:{n}" for sid, n in cuenta[:12])[:300]
    except Exception:  # noqa: BLE001 — un censo ilegible no puede empeorar el aviso que acompaña
        censo = "?"
    try:
        from voice.observer import emit
        emit("perf", "🧾 la cara dice que hay filas y la hoja no las da", role="system",
             extra={"nav_task": str(nav_task_id), "cajas": ", ".join(cajas or [])[:120], "censo": censo})
    except Exception:  # noqa: BLE001 — instrumentar no puede tumbar el prompt
        pass


def rows_of_sheet(sheet: str, n: int = 3) -> list[str]:
    """Las primeras filas CON NOMBRE de una hoja, como «título — precio». Keyed por la HOJA, no por la pestaña.

    `_sheet_top_rows` (en `live_blocks`) resuelve la hoja DESDE la pestaña del navegador, así que solo puede
    contestar cuando hay navegador. Un encargo resuelto por BÚSQUEDA no lo tiene, y el 2026-08-28 se midió el
    coste en `cheapest-monitor__us`: `navegador_task_id` VACÍO, seis monitores con nombre y precio en la hoja,
    `shown_to_model: false` en los doce turnos y el juez de bloqueador «respondió con una promesa vacía… la
    hoja ya tenía 6». No es que la resolución fallara: es que el bloque de filas no se compone si no hay
    pestaña, y entonces ni siquiera se emite el aviso de V2-438 —porque vive dentro de la función que nadie
    llama—. Un hueco que no falla con ruido: falla saliendo vacío.

    Mismo formato que la otra, a propósito: es el mismo dato en el mismo prompt y dos redacciones distintas
    obligan al modelo a decidir si son lo mismo.
    """
    try:
        from widgets.results import data as _sheet
        out: list[str] = []
        for i in ((_sheet.view_data(str(sheet or "")) or {}).get("items") or []):
            title = str((i or {}).get("title") or "").strip()
            if not title:
                continue
            price = str((i or {}).get("price") or "").strip()
            out.append(f"«{title[:60]} — {price[:24]}»" if price else f"«{title[:60]} — SIN PRECIO»")
            if len(out) >= max(1, int(n)):
                break
        return out
    except Exception:  # noqa: BLE001 — leer la hoja no puede tumbar el prompt
        return []
