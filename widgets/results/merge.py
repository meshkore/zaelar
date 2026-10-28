"""widgets/results/merge.py — the sections delivered ALONGSIDE present/append (sources, summary, criteria,
rejected) merged over what the sheet already holds, and the spoken tab names normalised to the declared tabs.
`data` re-exports both names.
"""
from .clean import (
    _MAX_REJECTED, _MAX_SOURCES, _MAX_STEPS, _clean_criteria, _clean_rejected, _clean_sources, _clean_summary)


# The tab arrives by VOICE ("show me the sources", "how is it going?"), so the name comes in the operator's language
# and through STT. This is not an intent table —the model decides that— but normalization of the argument it already
# chose: the same role the ordinal plays in `detail`.
_TAB_ALIASES = {
    "resultados": "results", "resultado": "results", "lista": "results", "fichas": "results",
    "sumario": "summary", "resumen": "summary", "estado": "summary", "progreso": "summary",
    "fuentes": "sources", "fuente": "sources", "webs": "sources", "paginas": "sources", "páginas": "sources",
    "criterios": "criteria", "criterio": "criteria", "brief": "criteria", "encargo": "criteria",
    "proceso": "process", "process": "process", "curso": "process", "avance": "process",
}


def _merge_sections(data: dict, payload: dict) -> None:
    """`sources`/`summary`/`criteria` delivered ALONGSIDE present/append. They are merged over what already existed:
    whoever delivers results does not always have in front of them what they reported five minutes ago."""
    src = _clean_sources(payload.get("sources"))
    if src:
        cur = list(data.get("sources") or [])
        for s in src:
            key = (s.get("url") or "").strip().lower() or (s.get("name") or "").strip().lower()
            hit = next((c for c in cur
                        if ((c.get("url") or "").strip().lower() or (c.get("name") or "").strip().lower()) == key),
                       None)
            if hit:
                hit.update(s)
            else:
                cur.append(s)
        data["sources"] = cur[:_MAX_SOURCES]
    summ = _clean_summary(payload.get("summary"))
    if summ:
        cur = dict(data.get("summary") or {})
        steps = list(cur.get("steps") or []) + [s for s in summ.pop("steps", []) if s not in (cur.get("steps") or [])]
        cur.update(summ)
        if steps:
            cur["steps"] = steps[-_MAX_STEPS:]
        data["summary"] = cur
    crit = _clean_criteria(payload.get("criteria"))
    if crit:
        cur = dict(data.get("criteria") or {})
        cur.update(crit)
        data["criteria"] = cur
    # The rejected pile GROWS across rounds (a worker reports as it goes) and dedupes on url-or-title, by
    # the same rule `append` uses for the kept list: the same finding reported twice is one finding.
    rej = _clean_rejected(payload.get("rejected"))
    if rej:
        cur = list(data.get("rejected") or [])
        seen = {(x.get("url") or x.get("title") or "").strip().lower() for x in cur}
        for r in rej:
            key = (r.get("url") or r.get("title") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                cur.append(r)
        data["rejected"] = cur[:_MAX_REJECTED]
