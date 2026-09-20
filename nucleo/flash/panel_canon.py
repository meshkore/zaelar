"""nucleo/flash/panel_canon.py — which ChatWall destination the model's `panel` argument means (V2-728).

Extracted from `router.py` when V2-728 gave «Tareas» four sub-tabs: the canon grew two keyword lists and a
docstring that matters, and `router.py` was already at its architecture ceiling. The ratchet's answer to a
file over its ceiling is «extract a module, do not raise the ceiling», and this is a cohesive thing to cut —
a pure string→string function with no state and one caller.
"""
from __future__ import annotations


def canon_panel(v) -> str:
    """Normalizes the `show_panel` `panel` to a canonical ChatWall destination.

    V2-728 — the wall now has four tabs, and «Tareas» has four SUB-tabs. This still answers a single string,
    because that is what the frontend's one door (`store.setChatTab`) takes: `chat` · `clusters` ·
    `conectores` · `tareas` (En curso) · `crons` (Periódicas) · `programadas` (Programadas). The old
    `procesos` is still answered and still lands correctly; nothing downstream had to learn a new shape.

    The split that MATTERS here is «periódica» vs «programada», and it is not cosmetic: one repeats forever
    and the other fires once. They used to collapse onto `crons` together, so «enséñame las tareas
    programadas» opened the list of things that repeat — the wrong list, with no error to notice it by.

    Synonyms the model may produce in the ARGUMENT only; the 'when' (synonyms in the request) lives in the
    tool description, not here. Default `tareas`, the most requested case.
    """
    p = str(v or "").strip().lower()
    if p in ("chat", "tareas", "crons", "programadas", "clusters", "conectores", "procesos"):
        return p
    # 'clusters' BEFORE the rest: "cluster" contains the substring "clus", not "cron", but the order makes
    # explicit that the network is evaluated first — and prevents a future ambiguous synonym from landing on the wrong side.
    if any(k in p for k in ("cluster", "meshkore", "mesh", "red", "malla", "peer", "network", "conexion", "conexión")):
        return "clusters"
    if any(k in p for k in ("conector", "connector", "integracion", "integración")):
        return "conectores"
    # …and 'periódica' BEFORE 'programada': a recurring job IS scheduled, so the narrower word has to win or
    # everything lands on the same list, which is the defect this split exists to remove.
    if any(k in p for k in ("cron", "periodic", "periódic", "recurren", "cada semana", "cada dia", "cada día",
                            "semanal", "diaria", "diario", "mensual", "repit", "repet")):
        return "crons"
    if any(k in p for k in ("programad", "agendad", "schedul", "recordatorio", "aviso", "para luego",
                            "para mañana", "la semana que viene")):
        return "programadas"
    if any(k in p for k in ("chat", "texto", "muro", "escrib", "message", "mensaj")):
        return "chat"
    if any(k in p for k in ("proces", "worker", "tarea", "trabajo", "encarg", "activ", "curso", "marcha")):
        return "tareas"
    return "tareas"
