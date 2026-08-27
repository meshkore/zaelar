"""Cuántas data-ops de widget ejecuta UN turno, y cuáles (V2-391).

La regla era «UNA por turno», en los dos canales, y su motivo está medido: el modelo pequeño a veces DUPLICA
un `add_meeting` (cita doble) o ENUMERA acciones ante «muéstrame la agenda» (done/drop/snooze…). Las dos son
reales y las dos siguen bloqueadas aquí.

Lo que la regla no contemplaba es que a veces VARIAS son la petición. Medido en
`build-a-video-playlist-from-links` (2026-08-27 13:36): el operador pega DOS enlaces y dice «móntame una lista
con ellos»; `add` solo admite un vídeo, así que dos enlaces son dos llamadas — y solo entró la primera
(`widget_ops: add: 1`). Después el `next` se encontró la lista con un solo vídeo, el widget devolvió «No hay
más vídeos», y el turno anunció que sonaba el segundo igualmente: el título lo sabía por la URL, no por la
lista. 1/5 en resultado por una alucinación que empieza siendo un tope nuestro.

El criterio nuevo es más ESTRECHO que el viejo justo donde importa, y más ancho solo donde no: se admiten
varias del MISMO widget y la MISMA acción con payloads DISTINTOS. Un duplicado exacto se colapsa (la cita
doble) y una acción DISTINTA sobre el mismo widget no entra (la enumeración). El techo sigue puesto por si el
modelo se desboca.

Nota de seguridad: aquí solo llegan las FAST — una acción irreversible es CONFIRM y sigue necesitando el sí
del operador, así que ampliar esto no amplía lo que se puede romper sin permiso.

Vive en su propio módulo y no dentro de `router_guards` por el trinquete de fichero-dios: lo que importa es
que la decisión sea UNA y compartida por los dos canales, no en qué fichero está. `router_guards` ya estaba
en su techo, y el trinquete pide extraer, no subirlo.
"""
from __future__ import annotations

import json as _json

#: Techo de data-ops por turno. Cinco enlaces pegados de una vez es una petición; cincuenta es un modelo roto.
MAX_DATA_OPS = 5


def _ident(args: dict) -> tuple[str, str, str]:
    """La identidad de una data-op: widget + acción + payload, comparable."""
    a = args if isinstance(args, dict) else {}
    pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
    return (str(a.get("widget_id") or "").strip().lower(),
            str(a.get("action") or "").strip(),
            _json.dumps(pl, sort_keys=True, ensure_ascii=False, default=str))


def admite_data_op(args: dict, ya: list[dict]) -> bool:
    """¿Se ejecuta ESTA data-op, habiendo ejecutado ya `ya`? Decisión compartida por los dos canales."""
    wid, accion, payload = _ident(args)
    if not wid or not accion:
        return False
    if len(ya) >= MAX_DATA_OPS:
        return False
    for previa in ya:
        p_wid, p_accion, p_payload = _ident(previa)
        if (wid, accion, payload) == (p_wid, p_accion, p_payload):
            return False                      # duplicado exacto → la cita doble
        if wid == p_wid and accion != p_accion:
            return False                      # otra acción sobre el mismo widget → la enumeración
    return True
