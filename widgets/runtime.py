#
# Widget runtime — catalog + identification (HANDOFF §3). Built to scale to thousands: one folder per widget,
# each with a manifest.json; the catalog is just the index; code (widget.js) loads lazily in the browser.
# This module is the ONLY thing the rest of the app talks to for widgets — fully isolated from the voice core.
#
import difflib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# Catalog cache (scales to thousands of widgets): parse manifests once and reuse until a manifest mtime changes.
# Avoids re-reading + json-parsing every manifest on every call (identify() runs on every transcript).
_cache = {"sig": None, "list": []}


def _signature() -> tuple:
    sig = []
    for name in sorted(os.listdir(HERE)):
        man = os.path.join(HERE, name, "manifest.json")
        js = os.path.join(HERE, name, "widget.js")
        # A widget needs BOTH a manifest AND a widget.js to be usable. A folder with only a manifest is debris from
        # a generation that died half-way — skipping it keeps broken widgets OUT of the catalog + the brain's brief,
        # so a failed build can never poison show()/identify() ("a widget must not break the rest of the system").
        if not os.path.isfile(js):
            continue
        try:
            sig.append((name, os.path.getmtime(man)))
        except OSError:
            pass
    return tuple(sig)


def catalog() -> list[dict]:
    """Scan each widget folder's manifest.json → the capability catalog (cached; reloads only on manifest change)."""
    sig = _signature()
    if sig == _cache["sig"]:
        return _cache["list"]
    out = []
    for name, _ in sig:
        try:
            out.append(json.load(open(os.path.join(HERE, name, "manifest.json"), encoding="utf-8")))
        except Exception:
            pass
    _cache["sig"], _cache["list"] = sig, out
    return out


def get(widget_id: str) -> dict | None:
    return next((w for w in catalog() if w.get("id") == widget_id), None)


def invalidate() -> None:
    """Force the catalog + identify caches to rebuild on next access. The signature is mtime-based so a
    deleted/added folder self-heals anyway, but a widget lifecycle op (create/delete) calls this so the change
    is visible IMMEDIATELY (same tick) without waiting for the next mtime-triggered reload."""
    _cache["sig"] = None
    _index["sig"] = None


def _norm(s: str) -> str:
    """Accent-insensitive lowercase normalization ('Previsión' → 'prevision') — voice STT is inconsistent
    about accents, and keyword matching must not depend on them."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", s).strip()


# Identification index, rebuilt only when the catalog changes (same signature as the catalog cache). Holds the
# pre-normalized keyword phrases + descriptive tokens per widget so identify() — which runs on every transcript —
# does no normalization work per call beyond the query itself. This keeps it viable for catalogs of thousands.
_index = {"sig": None, "rows": []}

_STOP = set("el la los las un una de del en al a y o que con para por me mi tu su es hay este esta ese esa lo se "
            "the a an of in on to and or is are my".split())


def _identify_index() -> list[dict]:
    sig = _signature()
    if sig == _index["sig"]:
        return _index["rows"]
    rows = []
    for w in catalog():
        kws = [_norm(k) for k in (w.get("keywords") or [])]
        name_tokens = set(_norm(w.get("id", "")).split()) | set(_norm(w.get("title", "")).split())
        desc_tokens = (set(_norm(w.get("description", "")).split()) |
                       set(_norm(w.get("whenToUse", "")).split())) - _STOP
        rows.append({"w": w, "kws": [k for k in kws if k], "kw_tokens": {t for k in kws for t in k.split()} - _STOP,
                     "name": _norm(w.get("id", "")), "title": _norm(w.get("title", "")),
                     "name_tokens": name_tokens - _STOP, "desc_tokens": desc_tokens})
    _index["sig"], _index["rows"] = sig, rows
    return rows


def identify(query: str, open_ids: list | None = None) -> dict:
    """Map a free-text/voice request to a widget. Returns the best match + ranked candidates so the assistant
    can DISAMBIGUATE ('do you mean this widget or that one?') when it's not clear (HANDOFF §0).

    Lexical-semantic scoring, stdlib-only (the step before real embeddings — see W-5 in INI-006):
    accent-insensitive · keyword PHRASE hits keep their classic weights · single query tokens also match keyword
    tokens with a fuzzy tolerance (difflib, catches voice-typos) · id/title hits dominate · description/whenToUse
    token overlap adds a small tiebreak signal, capped so prose can never beat a real keyword.

    `open_ids` = widgets abiertos ahora en el canvas (contexto de UI del ESTADO): cuando varios candidatos empatan,
    el que el operador tiene DELANTE gana ("modifica el widget de X" apuntando a lo que está en pantalla)."""
    q = _norm(query)
    if not q:
        return {"match": None, "ambiguous": False, "candidates": []}
    q_padded = f" {q} "
    q_tokens = [t for t in q.split() if t not in _STOP]
    scored = []
    for row in _identify_index():
        score = 0.0
        for kw in row["kws"]:
            if f" {kw} " in q_padded:                       # whole keyword phrase, word-aligned
                score += 2 if len(kw) > 4 else 1
        # fuzzy per-token: 'tarrgona'≈'tarragona' (voice/typos). Only for meaningful tokens (>3 chars).
        for t in q_tokens:
            if len(t) > 3 and t not in row["kw_tokens"] and \
                    difflib.get_close_matches(t, row["kw_tokens"], n=1, cutoff=0.84):
                score += 1
        if (row["name"] and row["name"] in q) or (row["title"] and row["title"] in q):
            score += 3
        overlap = len(set(q_tokens) & row["desc_tokens"])
        if overlap:
            score += min(0.5 * overlap, 1.5)               # weak signal, capped below one keyword hit
        if score >= 1:                                      # description alone (<1) never surfaces a widget
            scored.append((score, row["w"]))
    scored.sort(key=lambda s: (-s[0], s[1].get("id", "")))
    cands = [{"id": w["id"], "title": w["title"], "score": s} for s, w in scored]
    top = scored[0][1] if scored else None
    # clear winner only if there is a unique top score
    ambiguous = len(scored) > 1 and scored[0][0] == scored[1][0]
    # Desempate por CONTEXTO DE UI: si el top empata pero UNO de los empatados está ABIERTO en pantalla, ese gana.
    if ambiguous and open_ids:
        open_set = {str(i).split("::", 1)[0].strip().lower() for i in open_ids if str(i).strip()}
        tied_open = [w for s, w in scored if s == scored[0][0] and w.get("id", "").lower() in open_set]
        if len(tied_open) == 1:
            top, ambiguous = tied_open[0], False
    return {"match": (top["id"] if (top and not ambiguous) else None),
            "ambiguous": ambiguous, "candidates": cands}
