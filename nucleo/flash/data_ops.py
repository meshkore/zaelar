"""How many data-ops of widget ejecuta UN turn, and cuales (V2-391).

La regla era «UNA by turn», in the two canales, and su reason esta measured: the model small a veces DUPLICA
a `add_meeting` (cita doble) or ENUMERA actions ante «muestrame the agenda» (done/drop/snooze…). Las two son
reales and the two siguen bloqueadas here.

Lo that the regla no contemplaba es that a veces VARIAS son the request. Medido in
`build-a-video-playlist-from-links` (2026-08-27 13:36): the operator pega DOS enlaces and says «montame a lista
with ellos»; `add` only admite a video, so that two enlaces son two llamadas — and only entro the first
(`widget_ops: add: 1`). Despues the `next` is encontro the lista with a only video, the widget devolvio «No there is
mas videos», and the turn anuncio that sonaba the second igualmente: the titulo it sabia by the URL, no by the
lista. 1/5 in result by a alucinacion that empieza siendo a cap nuestro.

El criterion new es mas ESTRECHO that the viejo justo donde importa, and mas wide only donde no: is admiten
varias of the MISMO widget and the MISMA action with payloads DISTINTOS. Un duplicado exacto is colapsa (the cita
doble) and a action DISTINTA sobre the same widget no entra (the enumeracion). El cap continues puesto by if the
model is desboca.

Nota of security: here only llegan the FAST — a action irreversible es CONFIRM and continues necesitando the si
of the operator, so that ampliar esto no amplia it that is can romper without permission.

Vive in su own module and no inside of `router_guards` by the trinquete of file-dios: it that importa es
that the decision sea UNA and shared by the two canales, no in what file esta. `router_guards` already estaba
in su cap, and the trinquete pide extraer, no subirlo.
"""
from __future__ import annotations

import json as _json

#: Techo of data-ops by turn. Cinco enlaces pegados of a vez es a request; cincuenta es a model roto.
MAX_DATA_OPS = 5


def _ident(args: dict) -> tuple[str, str, str]:
    """La identidad of a data-op: widget + action + payload, comparable."""
    a = args if isinstance(args, dict) else {}
    pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
    return (str(a.get("widget_id") or "").strip().lower(),
            str(a.get("action") or "").strip(),
            _json.dumps(pl, sort_keys=True, ensure_ascii=False, default=str))


def admite_data_op(args: dict, ya: list[dict]) -> bool:
    """¿Se ejecuta ESTA data-op, habiendo ejecutado already `already`? Decision shared by the two canales."""
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
