"""widgets/refs.py — resolving natural-language REFERENCES to items (V2-026).

The operator speaks natural language ("mark the daemon task done", "postpone the Reddit thing"); they do NOT know a
widget item's internal ids, and a fast model that tries to guess them INVENTS them (V2-026 bug: FlashBrain emitted
`done` with `taskId="09:00–11:00"` —the time range— instead of "t_daemon"). Solution: the model passes a
natural-language REFERENCE (`item`) and HERE it is resolved to the REAL id against the widget's LIVE items.

Widget contract (OPTIONAL, in its `data.py`):

    def ref_index() -> list[dict]:
        '''Voice-referenceable items: [{"id","label","field"[,"hint"]}]. `field` = the payload key that identifies
        that item in manifest actions (e.g. "taskId" for a task, "projectId" for a project). `label` = human text for
        matching the reference (task title, project name...). Optional `hint` = extra brief context (status, time...).'''

The field to fill is inferred from the OWN manifest: the action's declared `payload` already names its id field
(agenda `done`→{"taskId":...}, `drop_project`→{"projectId":...}). The reference is resolved ONLY against items whose
`field` matches that field → "discard the Atlas project" (`drop_project`→`projectId`) points to the PROJECT,
not to the "Atlas review" task. Stdlib fuzzy matching (token overlap + difflib), accent-insensitive. Returns an
AMBIGUITY/NO-MATCH signal instead of guessing (better to ask than act on the wrong item).
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from . import runtime


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ ]+", " ", s).strip()


_STOP = set("el la los las un una de del en al a y o que con para por mi tu su lo se me the a an of to my "
            "tarea tareas cita citas item proyecto la de lo eso esa ese esta este cosa asunto".split())


def _ref_index(widget_id: str) -> list[dict]:
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{widget_id}.data")
        if hasattr(mod, "ref_index"):
            idx = mod.ref_index()
            return [i for i in idx if isinstance(i, dict) and i.get("id") and i.get("field")]
    except Exception:
        pass
    return []


def _exposes_ref_index(widget_id: str) -> bool:
    """Does this widget PUBLISH its items? (to distinguish "empty" from "does not publish" — see items_line)."""
    try:
        import importlib
        return hasattr(importlib.import_module(f"widgets.{widget_id}.data"), "ref_index")
    except Exception:
        return False


def id_field_for_action(widget_id: str, action: str) -> str | None:
    """Payload key for this action that identifies an existing item (ends in 'Id', e.g. `taskId`, `projectId`,
    `chatId`), read from the manifest. None if the action does not operate on a preexisting item (e.g. `add_meeting`,
    which CREATES one) → there is nothing to resolve."""
    try:
        spec = ((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}
        payload = spec.get("payload")
        if not isinstance(payload, dict):
            return None
        for k in payload:
            if str(k).lower().endswith("id"):
                return k
    except Exception:
        pass
    return None


def _score(ref_n: str, label_n: str) -> float:
    if not ref_n or not label_n:
        return 0.0
    r_tokens = [t for t in ref_n.split() if t not in _STOP and len(t) > 2]
    l_tokens = [t for t in label_n.split() if t not in _STOP]
    if not r_tokens:
        return 0.0
    hits = 0.0
    for t in r_tokens:
        if t in l_tokens or any(t in lt or lt in t for lt in l_tokens):
            hits += 1
        elif difflib.get_close_matches(t, l_tokens, n=1, cutoff=0.82):
            hits += 0.8
    token_score = hits / len(r_tokens)                       # fraction of the reference covered
    ratio = difflib.SequenceMatcher(None, ref_n, label_n).ratio()
    return token_score * 2.0 + ratio                          # token overlap weighs more than the raw ratio


# Result of reference resolution.
class RefResult:
    def __init__(self, ok, payload=None, needs=None, candidates=None):
        self.ok = ok                    # True if resolved (or no resolution was needed)
        self.payload = payload          # payload actualizado con el id real (si ok)
        self.needs = needs              # 'ref' | 'ambiguous' | 'no_match' when ok=False
        self.candidates = candidates or []   # candidate labels (to ask the operator)


def resolve(widget_id: str, action: str, ref: str, payload: dict | None = None) -> RefResult:
    """Resolve a natural-language reference to the real item id for `action`. Returns a `RefResult`:
    - ok=True + payload (with the real id filled) if resolved, or if the action does not act on an existing item.
    - ok=False with `needs` ('ref'|'ambiguous'|'no_match') and `candidates` so the caller ASKS instead of inventing
      an id. NEVER raises."""
    payload = dict(payload or {})
    field = id_field_for_action(widget_id, action)
    if not field:
        return RefResult(True, payload)                       # nothing to resolve (e.g. add_meeting)

    idx = [i for i in _ref_index(widget_id) if i.get("field") == field]

    # If the model ALREADY gave an id that really EXISTS, respect it (do not overwrite it).
    given = str(payload.get(field) or "").strip()
    if given and any(i["id"] == given for i in idx):
        return RefResult(True, payload)

    # Text to search for: the model's explicit ref, or —if it did not give one— what it put in the id field (often an
    # invented description/value that sometimes matches by text, e.g. the task title).
    query = _norm(ref) or _norm(given)
    if not query:
        return RefResult(False, needs="ref", candidates=[i["label"] for i in idx][:6])
    if not idx:
        return RefResult(False, needs="no_match")

    scored = sorted(((_score(query, _norm(i["label"])), i) for i in idx), key=lambda s: -s[0])
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 1.0:
        return RefResult(False, needs="no_match", candidates=[i["label"] for i in idx][:6])
    if len(scored) > 1 and (best_score - second) < 0.5:       # tie → do not guess, ask
        close = [i["label"] for s, i in scored if best_score - s < 0.5][:4]
        return RefResult(False, needs="ambiguous", candidates=close)
    payload[field] = best["id"]
    return RefResult(True, payload)


def label_for(widget_id: str, field: str, item_id: str) -> str:
    """HUMAN label for widget item `item_id` (`field`) — to compose a readable message (e.g. confirmation text)
    without exposing the internal id. '' if not found. Generic (reads `ref_index`)."""
    iid = str(item_id or "").strip()
    if not iid:
        return ""
    for i in _ref_index(widget_id):
        if i.get("field") == field and str(i.get("id")) == iid:
            return str(i.get("label") or "").strip()
    return ""


_MAX_DIGEST_CHARS = 1800


def prompt_digest(widget_id: str) -> str:
    """REAL content of an OPEN widget, so the brain can REASON about what the operator has in front of them — not just
    name it. OPTIONAL contract in the widget's `data.py`:

        def prompt_digest() -> str:
            '''Text summary of what is inside NOW. Compact: travels in every turn prompt.'''

    Why it exists (2026-08-09): `items_line` only publishes `label (hint)`, so when asked "does the hotel in proposal
    2 have wifi?" —a fact WRITTEN in the card the operator is looking at— the brain did not have it in the prompt:
    it either guessed or escalated a new search to recover something it already had. That is the difference between a
    screen the agent SEES and one it has merely rendered.

    Intentionally bounded (`_MAX_DIGEST_CHARS`): this is a summary for reasoning, not the full record — complete
    detail lives in the widget itself (its detail view), not in every turn prompt. Only requested for OPEN widgets, so
    a large catalog pays nothing for this.
    Best-effort: a broken widget cannot break the turn."""
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{widget_id}.data")
        fn = getattr(mod, "prompt_digest", None)
        if not callable(fn):
            return ""
        out = str(fn() or "").strip()
    except Exception:
        return ""
    if len(out) > _MAX_DIGEST_CHARS:
        out = out[:_MAX_DIGEST_CHARS].rsplit("\n", 1)[0] + "\n… (recortado — el resto está en la propia tarjeta)"
    return out


def items_line(widget_id: str) -> str:
    """Compact line with the widget's LIVE items (label + hint) for the brain brief, so it knows WHAT exists and can
    reference it naturally. No internal ids (the model references by language).

    EMPTY ≠ NO INDEX (fix 2026-08-02): a widget that exposes `ref_index` but has nothing inside SAYS so. Previously it
    returned "" in both cases, so the brain could not distinguish "this card is open and empty" from "this card does
    not publish its items" — and with the results sheet open and blank it answered "here it is" to the operator, who
    saw nothing. An empty widget is a fact the brain must see."""
    if not _exposes_ref_index(widget_id):
        return ""
    idx = _ref_index(widget_id)
    if not idx:
        return ("items ahora: NINGUNO — la tarjeta está ABIERTA pero VACÍA: el operador no ve NADA dentro, así que "
                "no des por entregado lo que hay que poner ahí")
    bits = []
    for i in idx[:12]:
        h = str(i.get("hint") or "").strip()
        bits.append(f"«{i['label']}»" + (f" ({h})" if h else ""))
    return "items ahora: " + " · ".join(bits)
