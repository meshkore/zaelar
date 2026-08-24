"""widgets/results/live.py — lo que la pestaña de PROCESO pinta MIENTRAS el encargo trabaja.

Extraído de `widgets/results/data.py` el 2026-08-24 para pagar el trinquete de arquitectura al añadir la
COSECHA (V2-296), y la frontera ya estaba dibujada: todo lo de aquí es DERIVADO del registro vivo del
dispatcher en cada lectura, mientras que lo que queda en `data.py` es el CONTENIDO de la hoja — sus fichas,
sus fuentes, sus criterios— que la hoja sí posee y guarda.

Son dos preguntas distintas sobre el mismo encargo y por eso viven separadas aunque se pinten juntas:
`_progress` cuenta QUÉ está haciendo (narración, recortada al anillo de las últimas 40 líneas) y `_harvest`
cuánto lleva hecho (aritmética, que recortada sería falsa).

Ninguna de las dos guarda nada: el dueño del relato es `nucleo/sheets.py` y el de los números la pestaña del
navegador. Con el encargo terminado el registro vivo desaparece y las dos caen a lo que la hoja persistió al
cerrarse — un informe sin la explicación de cómo se llegó a él cuenta la mitad de lo que pasó.
"""
from __future__ import annotations

_MAX_PHASES = 40           # el mismo anillo que guarda el registro vivo (`dispatch.PHASES_KEPT`)
_MAX_PHASE_CHARS = 160


def _clean_phases(raw) -> list:
    """Frases de proceso, acotadas. Vienen ya legibles de `nucleo/workers/progress.py`; aquí no se interpreta
    ninguna — se recortan y se filtran las vacías, que es todo lo que una superficie de presentación puede hacer
    con el relato de otro."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x)[:_MAX_PHASE_CHARS] for x in raw if str(x or "").strip()][-_MAX_PHASES:]


def _progress(data: dict, sheet: str = "") -> dict:
    """`{alive, phases}` — DERIVADO en cada lectura, nunca guardado, igual que `counts` (V2-227 ámbito C).

    El dueño de «qué está pasando» es el registro vivo del dispatcher: la hoja lo LEE. Guardarlo aquí sería
    tener el mismo estado en dos sitios, y el que se queda en pantalla siempre es el rancio.

    Con el encargo TERMINADO el registro ya no existe, así que se cae al historial que la propia hoja guardó al
    cerrarse (`process`). Esa es la única parte persistida y tiene su razón: el informe sobrevive a un reinicio,
    y un informe cuya explicación de cómo se llegó a él ha desaparecido cuenta la mitad de lo que pasó.

    Fail-soft: sin dispatcher (un test de la hoja sola, el widget montado fuera del motor) esto es la historia
    guardada y `alive: False`, que es exactamente lo que se ve — no un error.
    """
    live = {}
    try:
        from nucleo import dispatch as _disp
        # V2-259 — el relato de SU encargo. `dispatch._phrases` entrelazaba las fases de todos los encargos vivos
        # EN ORDEN DE TIEMPO, y eso era «la respuesta honesta mientras la hoja sea única»; con una hoja por
        # encargo deja de serlo: dos cajas contando las dos la misma historia mezclada es mentir con más
        # superficie, que es justo lo que V2-259 existe para no hacer.
        live = _disp.sheet_progress(sheet) or {}
    except Exception:  # noqa: BLE001
        live = {}
    if live.get("alive"):
        return {"alive": True, "phases": _clean_phases(live.get("phases"))}
    stored = _clean_phases(data.get("process"))
    return {"alive": False, "phases": _clean_phases(live.get("phases")) or stored}


def _harvest(data: dict, sheet: str = "") -> dict:
    """La COSECHA de este encargo: cuánto se ha mirado y qué ha sobrevivido a cada corte (V2-296).

    Petición del operador con la pestaña delante: el relato ya contaba QUÉ está haciendo («entrando en
    es.wallapop.com…») y no había nada que dijera CUÁNTO. Se mantiene separada de `progress` porque son dos cosas
    distintas — una es narración y la otra aritmética — y porque el relato se recorta a las últimas 40 líneas
    mientras que un total recortado es un total falso.

    DERIVADA en cada lectura como `counts` y `progress`: la dueña de los números es la pestaña del navegador, la
    hoja los LEE. Con el encargo terminado el registro vivo ya no existe, así que se cae a lo que la propia hoja
    guardó al cerrarse — mismo trato que el relato, y por la misma razón: un informe cuya explicación de cuánto
    costó llegar a él ha desaparecido cuenta la mitad de lo que pasó.

    `{}` significa «no lo sabemos», y NO se rellena con ceros: un cero dice «se miró y no había», que es un hecho
    distinto y que aquí sería falso.
    """
    live = {}
    try:
        from nucleo import dispatch as _disp
        live = _disp.sheet_harvest(sheet) or {}
    except Exception:  # noqa: BLE001
        live = {}
    if live:
        return live
    stored = data.get("harvest")
    return dict(stored) if isinstance(stored, dict) and any(stored.values()) else {}
