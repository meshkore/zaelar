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
# pre-normalized ALIAS phrases + alias tokens per widget so identify() — which runs on every transcript — does no
# normalization work per call beyond the query itself. Viable for catalogs of thousands.
_index = {"sig": None, "rows": []}

_STOP = set("el la los las un una de del en al a y o que con para por me mi tu su es hay este esta ese esa lo se "
            "the a an of in on to and or is are my".split())

# La palabra "widget" (y sinónimos que usa el operador) es un SELECTOR de espacio de nombres (V2-082): si aparece,
# el usuario se refiere a una PIEZA construida por él → se resuelve SOLO contra widgets de usuario, nunca contra una
# superficie de sistema ("abre el widget de mensajería" jamás cae en el chat de sistema). Espejo LÉXICO de
# router._WIDGET_SYN (aquí, no importado, para que runtime siga stdlib-only y sin ciclos).
_WIDGET_WORD_RE = re.compile(r"\b(widget|gadget|tablero|contador|cuadro de mando|mini ?app|tarjeta)\b")


def _aliases_of(w: dict) -> list[str]:
    """Alias de IDENTIDAD de un widget (V2-082): `name`|`title`|id + `aliases` del manifest (o `keywords` legacy como
    semilla — keyword ≡ alias). ÚNICA señal de apertura; la descripción ya NO abre nada. Normalizados, dedup."""
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


# ── Superficies de SISTEMA en el mismo espacio de nombres (V2-082) ──────────────────────────────────────────────
_sys_index = {"loaded": False, "rows": []}


def _system_index() -> list[dict]:
    """Índice léxico de las superficies de sistema (chat, config, debug…): id + alias FIJOS normalizados. Fuente:
    `widgets/system_surfaces.py` (espejo del front). Se carga una vez (la lista es estática, no cambia en runtime)."""
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
    """Puntuación de una pieza contra la query SOLO por NOMBRE/ALIAS (nunca por descripción). Frase de alias
    alineada a palabra = señal fuerte; token de query difuso sobre un token de alias distintivo = tolerancia de
    voz. Con certeza: la descripción no participa, así nada abre por parecido temático."""
    score = 0.0
    for a in aliases:
        if f" {a} " in q_padded:                            # alias entero, alineado a palabra
            score += 3 if (" " in a or len(a) > 6) else 2
    fuzzy = 0.0
    for t in q_tokens:                                      # tolerancia a erratas de voz: 'watsap'≈'wasap'
        if len(t) > 4 and t not in alias_tokens:
            m = difflib.get_close_matches(t, [x for x in alias_tokens if len(x) > 4], n=1, cutoff=0.84)
            if m:
                fuzzy += 2 if len(m[0]) > 4 else 1
    return score + min(fuzzy, 2.0)                          # el difuso ayuda a aflorar pero nunca domina una frase


_THRESHOLD = 2.0            # por debajo de 2 no se abre nada → se pregunta (certeza, V2-082)


def _tiebreak_by_context(scored, top_score, ids, key: str):
    """Devuelve el ÚNICO empatado (score == top_score) cuyo id esté en `ids`, o None si hay 0 o >1. `key` solo
    documenta la capa (open/recent) para el llamante. Normaliza ids de instancia (navegador::t1 → navegador)."""
    ctx = {str(i).split("::", 1)[0].strip().lower() for i in (ids or []) if str(i).strip()}
    if not ctx:
        return None
    tied = [w for s, w in scored if s == top_score and w.get("id", "").lower() in ctx]
    return tied[0] if len(tied) == 1 else None


def _match_system(q: str, q_padded: str, q_tokens: list):
    """¿La query nombra una SUPERFICIE DE SISTEMA (chat/config/debug…)? Devuelve (id, score) del mejor o (None,0).
    Mismo scoring alias-only que los widgets — así 'abre el chat' resuelve a sistema y no a un widget homónimo."""
    best_id, best = None, 0.0
    for row in _system_index():
        s = _alias_score(q, q_padded, q_tokens, row["aliases"], row["alias_tokens"])
        if s > best:
            best_id, best = row["id"], s
    return (best_id, best) if best >= _THRESHOLD else (None, 0.0)


def rank(query: str, limit: int = 8) -> list[tuple[float, dict]]:
    """Ranking PÚBLICO de widgets contra una frase, SOLO por nombre/alias — la misma señal (y el mismo índice
    cacheado) que usa `identify()`, pero devolviendo los N mejores en vez de exigir un ganador inequívoco.

    Existe para la SELECCIÓN PROGRESIVA (`widgets/selection.py`): con un catálogo de miles, el prompt no puede
    llevar el catálogo entero, así que el widget que el operador NOMBRA en su frase se PROMOCIONA al top-K por
    esta vía — sin ella, un widget en la posición 4.000 sería invisible para el modelo. Es RECUPERACIÓN
    (retrieval), no comprensión: no interpreta el verbo ni la intención, solo mide parecido de nombre/alias.

    Devuelve [(score, manifest)] ordenado desc, ya filtrado por `_THRESHOLD` (por debajo no hay señal real).
    Coste: O(N) sobre un índice ya normalizado en RAM (~µs por widget); no hace I/O ni re-parsea manifests."""
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
    """Resuelve una petición de voz/texto a una PIEZA por su NOMBRE o ALIAS, con CERTEZA (V2-082).

    Reglas duras (invierten el matching difuso anterior, causa de las confusiones):
    - **Solo NOMBRE/ALIAS abren.** La `description`/`whenToUse` ya NO puntúa — se acabó el "abrió por parecido
      temático". Tolerancia de voz (difflib) SOLO sobre tokens de alias.
    - **La palabra "widget"** en la frase acota a widgets de USUARIO (ignora superficies de sistema).
    - **Objeto de sistema nombrado** (chat/config/debug…) → `system` = su id y `match` = None (una superficie
      jamás se devuelve como widget de usuario). El llamante rutea la superficie (show_panel / toggle).
    - **Sin match de nombre/alias → `match` = None.** El llamante NO abre el más parecido: PREGUNTA con
      naturalidad. Único matiz: si no casa ningún alias pero hay UN solo widget ABIERTO, opera sobre él
      (`by_context`) — es lo que el operador tiene delante (data-op sobre la pieza en pantalla), no una apertura
      a ciegas.

    Devuelve {match, ambiguous, candidates, score, system, by_context}. `open_ids`/`recent_ids` desempatan
    empates por prioridad abiertos > usados hace poco (V2-078)."""
    q = _norm(query)
    if not q:
        return {"match": None, "ambiguous": False, "candidates": [], "score": 0.0,
                "system": None, "by_context": False}
    q_padded = f" {q} "
    q_tokens = [t for t in q.split() if t not in _STOP]
    has_widget_word = bool(_WIDGET_WORD_RE.search(q))

    # 1) ¿nombra una superficie de sistema? (salvo que diga explícitamente "widget" → solo usuario)
    system_id, system_score = (None, 0.0) if has_widget_word else _match_system(q, q_padded, q_tokens)

    # 2) scoring de widgets de USUARIO, SOLO por alias/nombre
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

    # 3) una superficie de sistema nombrada gana sobre un widget FLOJO: si el sistema puntúa >= al mejor widget,
    #    NO devolvemos widget (evita que 'abre el chat' caiga en un widget con 'chats' de alias).
    if system_id is not None and system_score >= top_score:
        match, ambiguous = None, False

    # 4) fallback de CONTEXTO: sin match de alias ni superficie, si hay UN solo widget abierto, opera sobre él
    #    (lo que tiene DELANTE) — NUNCA una apertura a ciegas del "más parecido".
    by_context = False
    if match is None and system_id is None and not ambiguous:
        singles = {str(i).split("::", 1)[0].strip().lower() for i in (open_ids or []) if str(i).strip()}
        if len(singles) == 1:
            only = next(iter(singles))
            if get(only) is not None:
                match, by_context = only, True

    return {"match": match, "ambiguous": ambiguous, "candidates": cands, "score": top_score,
            "system": (system_id if match is None else None), "by_context": by_context}
