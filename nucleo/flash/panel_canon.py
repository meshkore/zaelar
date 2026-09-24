"""nucleo/flash/panel_canon.py — which ChatWall destination the model's `panel` argument means (V2-728 · V2-744).

Extracted from `router.py` when V2-728 gave «Procesos» four sub-tabs: the canon grew two keyword lists and a
docstring that matters, and `router.py` was already at its architecture ceiling. The ratchet's answer to a
file over its ceiling is «extract a module, do not raise the ceiling», and this is a cohesive thing to cut —
a pure string→string function with no state and one caller.
"""
from __future__ import annotations

import re


def canon_panel(v) -> str:
    """Normalizes the `show_panel` `panel` to a canonical ChatWall destination.

    V2-728 — the wall now has four tabs, and «Procesos» has four SUB-tabs. This still answers a single
    string, because that is what the frontend's one door (`store.setChatTab`) takes: `chat` · `clusters` ·
    `conectores` · `apps` (V2-761, the widget catalogue — `apps-custom` for its Custom sub-tab) · `procesos`
    (En curso) · `crons` (Periódicos) · `programadas` (Programados).

    ⚠️ V2-744 — «TAREA» NO LONGER MEANS THIS PANEL, and that is the whole point of the rename. The
    operator's rule: *«a las tareas que yo hago las llamo procesos (jobs en inglés) y las separo de las
    tareas personales del operador que van en su agenda»*. His tasks are numbered lists inside the AGENDA
    widget and are opened with `agenda:show_tasks`, so the word is gone from the keyword list below: a
    `panel` argument saying «tareas» can only reach `procesos` through the final default, which is what a
    caller that named no known panel gets anyway. What steers the model away from calling this at all is
    the tool description and the agenda's own `whenToUse`, where the two words are told apart in prose.
    The canonical string `tareas` is still ACCEPTED verbatim, because an action-map row the operator
    recorded before today carries it and it meant this panel when he recorded it; the frontend maps it.

    The split that MATTERS here is «periódica» vs «programada», and it is not cosmetic: one repeats forever
    and the other fires once. They used to collapse onto `crons` together, so «enséñame las tareas
    programadas» opened the list of things that repeat — the wrong list, with no error to notice it by.

    Synonyms the model may produce in the ARGUMENT only; the 'when' (synonyms in the request) lives in the
    tool description, not here. Default `procesos`, the most requested case.
    """
    p = str(v or "").strip().lower()
    if p in ("chat", "procesos", "crons", "programadas", "clusters", "conectores", "tareas", "apps", "apps-custom"):
        return "procesos" if p == "tareas" else p
    # 'clusters' BEFORE the rest: "cluster" contains the substring "clus", not "cron", but the order makes
    # explicit that the network is evaluated first — and prevents a future ambiguous synonym from landing on the wrong side.
    if any(k in p for k in ("cluster", "meshkore", "mesh", "red", "malla", "peer", "network", "conexion", "conexión")):
        return "clusters"
    if any(k in p for k in ("conector", "connector", "integracion", "integración")):
        return "conectores"
    # V2-761 — the widget catalogue. AFTER the connectors on purpose: «app» is inside «whatsapp», so it is
    # matched as a WORD, and a connector named in the argument keeps winning.
    if re.search(r"\b(apps?|widgets?|aplicacion(es)?|aplicación)\b", p):
        return "apps-custom" if re.search(r"\b(custom|personaliz|propi|mios|mías|mias|míos)", p) else "apps"
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
    if any(k in p for k in ("proces", "process", "job", "worker", "trabajo", "encarg", "activ", "curso", "marcha")):
        return "procesos"
    return "procesos"
