"""widgets/results/lifecycle.py — the ERRAND's three gates on the sheet: it OPENS it, NAMES it and CLOSES it.

Extracted from `data.py` on 2026-08-31 (V2-530) because the architecture ratchet asked for a module instead of a
higher ceiling, and the cut was already drawn in the comment these gates carried: they are NOT actions of
`apply_action`'s vocabulary — nobody asks for them from a prompt, the errand's LIFECYCLE fires them, and putting
them in that vocabulary would put them within a worker's reach, which is exactly who must not decide when the
sheet is opened, renamed or closed.

Everything here writes through `data`'s own store seams (`_empty` / `view_data` / `_save` / `_clip`), so the sheet
has a single writer as it always did. `data.py` re-exports the three names: no caller changed.
"""
from __future__ import annotations

from widgets.results.live import _clean_phases

# The sheet's STORE layer (`view_data` / `_save` / `_empty` / `_clip`) still lives in `data.py`, and `data.py`
# re-exports these three gates, so the import has to be late or the two modules would deadlock at import time.
# Naming the debt rather than hiding it: the cycle disappears the day that store layer becomes its own module,
# which is a bigger cut than the ratchet was asking for tonight.


def _empty():
    from . import data as _d
    return _d._empty()


def _save(data, sheet=""):
    from . import data as _d
    return _d._save(data, sheet)


def view_data(sheet: str = "") -> dict:
    from . import data as _d
    return _d.view_data(sheet)


def _clip(text, key: str) -> str:
    from . import data as _d
    return _d._clip(text, key)


# ── EL ENCARGO ABRE Y CIERRA LA HOJA (V2-227 ámbito C) ───────────────────────────────────────────────────────
# Las dos únicas puertas que el dispatcher usa para que el operador VEA el trabajo mientras pasa. No son acciones
# del vocabulario de `apply_action`: nadie las pide desde un prompt, las dispara el ciclo de vida del encargo —
# meterlas ahí las pondría al alcance de un worker, que es justo quien no debe decidir cuándo se estrena la hoja.

def begin_task(title: str = "", fresh: bool = True, sheet: str = "") -> dict:
    """El encargo acaba de salir: la hoja se abre en PROCESO, sin nada dentro todavía.

    `fresh` ESTRENA la hoja (título = lo que pidió el operador, sin resultados ni historial de la búsqueda
    anterior). Se apaga cuando otro encargo sigue escribiendo aquí: vaciarla entonces le borraría a ése lo que ya
    había entregado, y la hoja es única mientras C4 («dos búsquedas = dos hojas») no exista.

    En los dos casos se quita la pestaña PERSISTIDA. Es lo que hace que la hoja se abra en Proceso: `data.tab`
    manda sobre el derivado —y debe mandar, es donde el operador decidió mirar— pero esa decisión era del encargo
    ANTERIOR, y arrastrarla dejaría al operador mirando una lista vacía mientras el relato pasa en la de al lado.
    """
    data = _empty() if fresh else view_data(sheet)
    if fresh:
        t = " ".join(str(title or "").split())
        if t:
            data["title"] = _clip(t, "sheet_title")
    else:
        data = {k: v for k, v in data.items() if k not in ("counts", "progress")}
    data.pop("tab", None)
    data.pop("view", None)                   # el detalle abierto era de un resultado del encargo anterior
    data.pop("focus", None)
    data.pop("process", None)                # el relato que viene es el de ESTE encargo
    data.pop("harvest", None)                # …y sus números también (V2-296)
    _save(data, sheet)
    return {"ok": True, "fresh": bool(fresh), "title": data.get("title", "")}


def rename_task(title: str, sheet: str = "") -> dict:
    """Change ONLY this sheet's name, leaving everything it holds alone (V2-530).

    Separate from `begin_task` because that one ESTRENA — it is the errand's opening gesture and it wipes items,
    tabs and process. Renaming happens later, on a sheet the operator is already looking at, once the errand's
    title has been composed; reusing `begin_task(fresh=True)` for it would erase the very results it is naming.
    """
    t = " ".join(str(title or "").split())
    if not t:
        return {"ok": False, "error": "sin título"}
    data = view_data(sheet)
    data["title"] = _clip(t, "sheet_title")
    _save(data, sheet)
    return {"ok": True, "title": data["title"]}


def end_task(phases, sheet: str = "") -> dict:
    """El encargo terminó: se guarda su relato con el informe y se para el loader.

    Se PERSISTE porque la hoja lo es: un informe sobrevive a un reinicio y su explicación de cómo se llegó a él
    tiene que sobrevivir con él. Y la escritura es además lo que APAGA el loader — el emisor de fases solo dispara
    al CAMBIAR una fase, así que sin este guardado la tarjeta seguiría diciendo «Trabajando…» sobre un worker que
    ya no existe.
    """
    lines = _clean_phases(phases)
    data = {k: v for k, v in view_data(sheet).items() if k not in ("counts", "progress")}
    if lines:
        data["process"] = lines
    else:
        data.pop("process", None)            # sin una sola fase no hay historia que contar; no se inventa una
    # …y sus NÚMEROS con él (V2-296). `view_data` acaba de derivarlos del registro vivo, que en un instante deja de
    # existir: si no se guardan aquí, el informe queda sin la cuenta de lo que costó llegar a él.
    if not isinstance(data.get("harvest"), dict) or not any((data.get("harvest") or {}).values()):
        data.pop("harvest", None)            # sin un solo número no hay cuenta que dar; no se guardan ceros
    _save(data, sheet)
    return {"ok": True, "phases": len(lines)}
