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

from widgets import paths

HERE = paths.BUILTIN_ROOT      # kept for callers that import it; new code asks `paths` instead

# Catalog cache (scales to thousands of widgets): parse manifests once and reuse until a manifest mtime changes.
# Avoids re-reading + json-parsing every manifest on every call (identify() runs on every transcript).
_cache = {"sig": None, "list": []}


def _signature() -> tuple:
    # (id, folder, manifest mtime). The FOLDER travels in the signature because a widget can live in either
    # root (see widgets/paths.py) and the catalog below has to read the manifest it actually signed — not
    # re-resolve the id and risk reading a different one.
    sig = []
    for name, folder in paths.iter_folders():
        man = os.path.join(folder, "manifest.json")
        js = os.path.join(folder, "widget.js")
        # A widget needs BOTH a manifest AND a widget.js to be usable. A folder with only a manifest is debris from
        # a generation that died half-way — skipping it keeps broken widgets OUT of the catalog + the brain's brief,
        # so a failed build can never poison show()/identify() ("a widget must not break the rest of the system").
        if not os.path.isfile(js):
            continue
        try:
            sig.append((name, folder, os.path.getmtime(man)))
        except OSError:
            pass
    return tuple(sig)


def catalog() -> list[dict]:
    """Scan each widget folder's manifest.json → the capability catalog (cached; reloads only on manifest change)."""
    sig = _signature()
    if sig == _cache["sig"]:
        return _cache["list"]
    out = []
    for _name, folder, _mtime in sig:
        try:
            out.append(json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8")))
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
    """Accent-insensitive lowercase normalization ('Forecast' → 'forecast') — voice STT is inconsistent
    about accents, and keyword matching must not depend on them."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", s).strip()


# Identification index, rebuilt only when the catalog changes (same signature as the catalog cache). Holds the
# pre-normalized ALIAS phrases + alias tokens per widget so identify() — which runs on every transcript — does no
# normalization work per call beyond the query itself. Viable for catalogs of thousands.
_index = {"sig": None, "rows": []}

_STOP = set("el la los las un una de del en al a y o que con para por me mi tu su es hay este esta ese esa lo se "
            "the a an of in on to and or is are my".split())

# The word "widget" (and synonyms the operator uses) is a namespace SELECTOR (V2-082): if it appears, the user refers
# to a PIECE they built → resolve ONLY against user widgets, never against a system surface ("open the messaging
# widget" never lands in system chat). LEXICAL mirror of router._WIDGET_SYN (here, not imported, so runtime remains
# stdlib-only and cycle-free).
_WIDGET_WORD_RE = re.compile(r"\b(widget|gadget|tablero|contador|cuadro de mando|mini ?app|tarjeta)\b")


def _aliases_of(w: dict) -> list[str]:
    """Widget IDENTITY aliases (V2-082): `name`|`title`|id + manifest `aliases` (or legacy `keywords` as seed —
    keyword ≡ alias). ONLY opening signal; description no longer opens anything. Normalized, deduped."""
    name = str(w.get("name") or w.get("title") or w.get("id") or "").strip()
    seed = w.get("aliases") or w.get("keywords") or []
    out, seen = [], set()
    for a in [name, *seed]:
        a = _norm(a)
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _identify_index() -> list[dict]:
    sig = _signature()
    if sig == _index["sig"]:
        return _index["rows"]
    rows = []
    for w in catalog():
        aliases = _aliases_of(w)
        rows.append({"w": w, "aliases": aliases,
                     "alias_tokens": {t for a in aliases for t in a.split() if t not in _STOP}})
    _index["sig"], _index["rows"] = sig, rows
    return rows


# ── SYSTEM surfaces in the same namespace (V2-082) ────────────────────────────────────────────────────────────
_sys_index = {"loaded": False, "rows": []}


def _system_index() -> list[dict]:
    """Lexical index for system surfaces (chat, config, debug...): id + normalized FIXED aliases. Source:
    `widgets/system_surfaces.py` (front mirror). Loaded once (the list is static, does not change at runtime)."""
    if _sys_index["loaded"]:
        return _sys_index["rows"]
    rows = []
    try:
        from . import system_surfaces
        for s in system_surfaces.surfaces():
            als, seen = [], set()
            for a in [s["name"], *s["aliases"]]:
                a = _norm(a)
                if a and a not in seen:
                    seen.add(a)
                    als.append(a)
            rows.append({"id": s["id"], "name": s["name"], "aliases": als,
                         "alias_tokens": {t for a in als for t in a.split() if t not in _STOP}})
    except Exception:
        rows = []
    _sys_index["loaded"], _sys_index["rows"] = True, rows
    return rows


def _alias_score(q: str, q_padded: str, q_tokens: list, aliases: list, alias_tokens: set) -> float:
    """Score a piece against the query ONLY by NAME/ALIAS (never by description). Word-aligned alias phrase = strong
    signal; fuzzy query token over a distinctive alias token = voice tolerance. Certainty: description does not
    participate, so nothing opens by thematic similarity."""
    score = 0.0
    for a in aliases:
        if f" {a} " in q_padded:                            # whole alias, word-aligned
            score += 3 if (" " in a or len(a) > 6) else 2
    fuzzy = 0.0
    for t in q_tokens:                                      # tolerance for voice typos: 'watsap'≈'wasap'
        if len(t) > 4 and t not in alias_tokens:
            m = difflib.get_close_matches(t, [x for x in alias_tokens if len(x) > 4], n=1, cutoff=0.84)
            if m:
                fuzzy += 2 if len(m[0]) > 4 else 1
    return score + min(fuzzy, 2.0)                          # fuzzy helps surface candidates but never beats a phrase


_THRESHOLD = 2.0            # below 2, open nothing → ask (certainty, V2-082)


def _tiebreak_by_context(scored, top_score, ids, key: str):
    """Return the ONLY tied item (score == top_score) whose id is in `ids`, or None if there are 0 or >1. `key` only
    documents the layer (open/recent) for the caller. Normalizes instance ids (navegador::t1 → navegador)."""
    ctx = {str(i).split("::", 1)[0].strip().lower() for i in (ids or []) if str(i).strip()}
    if not ctx:
        return None
    tied = [w for s, w in scored if s == top_score and w.get("id", "").lower() in ctx]
    return tied[0] if len(tied) == 1 else None


def _match_system(q: str, q_padded: str, q_tokens: list):
    """Does the query name a SYSTEM SURFACE (chat/config/debug...)? Return (id, score) for the best match or (None,0).
    Same alias-only scoring as widgets — so 'open chat' resolves to system, not to a homonymous widget."""
    best_id, best = None, 0.0
    for row in _system_index():
        s = _alias_score(q, q_padded, q_tokens, row["aliases"], row["alias_tokens"])
        if s > best:
            best_id, best = row["id"], s
    return (best_id, best) if best >= _THRESHOLD else (None, 0.0)


def rank(query: str, limit: int = 8) -> list[tuple[float, dict]]:
    """PUBLIC widget ranking against a phrase, ONLY by name/alias — the same signal (and cached index) used by
    `identify()`, but returning the top N instead of requiring an unambiguous winner.

    Exists for PROGRESSIVE SELECTION (`widgets/selection.py`): with a catalog of thousands, the prompt cannot carry
    the whole catalog, so the widget the operator NAMES in the phrase is PROMOTED to the top-K through this path —
    without it, a widget at position 4,000 would be invisible to the model. This is RETRIEVAL, not understanding: it
    does not interpret verb or intent, only name/alias similarity.

    Returns [(score, manifest)] sorted desc, already filtered by `_THRESHOLD` (below that there is no real signal).
    Cost: O(N) over an already normalized in-RAM index (~µs per widget); does no I/O and does not re-parse manifests."""
    q = _norm(query)
    if not q:
        return []
    q_padded = f" {q} "
    q_tokens = [t for t in q.split() if t not in _STOP]
    scored = []
    for row in _identify_index():
        s = _alias_score(q, q_padded, q_tokens, row["aliases"], row["alias_tokens"])
        if s >= _THRESHOLD:
            scored.append((s, row["w"]))
    scored.sort(key=lambda sw: (-sw[0], str(sw[1].get("id", ""))))
    return scored[:max(0, int(limit))]


def identify(query: str, open_ids: list | None = None, recent_ids: list | None = None) -> dict:
    """Resolve a voice/text request to a PIECE by NAME or ALIAS, with CERTAINTY (V2-082).

    Hard rules (reverse previous fuzzy matching, which caused confusion):
    - **Only NAME/ALIAS opens.** `description`/`whenToUse` no longer scores — no more "opened by thematic similarity".
      Voice tolerance (difflib) ONLY over alias tokens.
    - **The word "widget"** in the phrase scopes to USER widgets (ignore system surfaces).
    - **Named system object** (chat/config/debug...) → `system` = its id and `match` = None (a surface is never
      returned as a user widget). The caller routes the surface (show_panel / toggle).
    - **No name/alias match → `match` = None.** The caller does NOT open the most similar one: it ASKS naturally.
      Only nuance: if no alias matches but there is ONE open widget, operate on it (`by_context`) — it is what the
      operator has in front of them (data-op over the piece on screen), not a blind open.

    Returns {match, ambiguous, candidates, score, system, by_context}. `open_ids`/`recent_ids` break ties by priority:
    open > recently used (V2-078)."""
    q = _norm(query)
    if not q:
        return {"match": None, "ambiguous": False, "candidates": [], "score": 0.0,
                "system": None, "by_context": False}
    q_padded = f" {q} "
    q_tokens = [t for t in q.split() if t not in _STOP]
    has_widget_word = bool(_WIDGET_WORD_RE.search(q))

    # 1) does it name a system surface? (unless it explicitly says "widget" → user only)
    system_id, system_score = (None, 0.0) if has_widget_word else _match_system(q, q_padded, q_tokens)

    # 2) USER widget scoring, ONLY by alias/name
    scored = []
    for row in _identify_index():
        s = _alias_score(q, q_padded, q_tokens, row["aliases"], row["alias_tokens"])
        if s >= _THRESHOLD:
            scored.append((s, row["w"]))
    scored.sort(key=lambda s: (-s[0], s[1].get("id", "")))
    cands = [{"id": w["id"], "title": w.get("title", ""), "score": s} for s, w in scored]
    top = scored[0][1] if scored else None
    top_score = scored[0][0] if scored else 0.0
    ambiguous = len(scored) > 1 and scored[0][0] == scored[1][0]
    if ambiguous:
        winner = _tiebreak_by_context(scored, scored[0][0], open_ids, "open") \
            or _tiebreak_by_context(scored, scored[0][0], recent_ids, "recent")
        if winner is not None:
            top, ambiguous = winner, False
    match = top["id"] if (top and not ambiguous) else None

    # 3) a named system surface beats a WEAK widget: if the system scores >= the best widget, do NOT return a widget
    #    (prevents 'open chat' from landing on a widget with 'chats' as alias).
    if system_id is not None and system_score >= top_score:
        match, ambiguous = None, False

    # 4) CONTEXT fallback: without alias or surface match, if there is ONE open widget, operate on it (what is IN
    #    FRONT of the operator) — NEVER a blind open of the "most similar" one.
    by_context = False
    if match is None and system_id is None and not ambiguous:
        singles = {str(i).split("::", 1)[0].strip().lower() for i in (open_ids or []) if str(i).strip()}
        if len(singles) == 1:
            only = next(iter(singles))
            if get(only) is not None:
                match, by_context = only, True

    return {"match": match, "ambiguous": ambiguous, "candidates": cands, "score": top_score,
            "system": (system_id if match is None else None), "by_context": by_context}
