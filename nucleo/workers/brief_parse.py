"""The research brief's SHAPE: the composer's reply parsed into bounded fields, and the messages that ask for it.
Part of `nucleo.workers.brief`; the names that stay there are read through `_b`."""
from __future__ import annotations

import json
import time

from nucleo.workers import brief as _b


# V2-840 H1 — breadth is the composer's: how many must be evaluated so the selection is defensible depends on the
# domain and its market (boats ≠ pianos ≠ footballs), so there is no floor here and no reader of a said number. The
# only bound is a COST cap — a consequence (minutes and tokens), never a judgement of how wide to look.
_MIN_CANDIDATES_CAP = 200


# HOW MANY are delivered: TEN by operator decision (2026-08-12), so the near-misses are visible and the cut can be
# judged. A number the operator ASKS for ("give me three") wins; the brief takes it from the errand.
_N_FINAL_DEFAULT = 10


_N_FINAL_CAP = 20       # el tope antes era 10 y hacía INEXPRESABLE un "ponme veinte" del operador


_MAX_LIST = 12          # criterios/enriquecimientos/baremo: una lista que el worker pueda de verdad respetar


_MAX_ITEM_CHARS = 220


# A piece's ROLE is painted as a card BADGE («Hotel», «Ferry») and must fit; the model tends to return a content
# description instead. The prompt asks for short; this cap GUARANTEES it — a prompt is a request, a cap a contract.
_MAX_ROLE_CHARS = 28


# ── the CLOSED catalog of what a brief may say (same principle as evaluator.py: validate, do not trust) ──
def _strlist(raw, cap: int = _MAX_LIST, chars: int = _MAX_ITEM_CHARS) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for x in raw:
        s = str(x).strip()
        if s:
            out.append(s[:chars])
        if len(out) >= cap:
            break
    return out


def _roles(raw) -> list[str]:
    """Roles of the parts of a composite proposal. Short by contract (they appear on a badge) and without duplicates:
    two parts with the same role (“Hotel” and “Hotel”) are not a composite proposal; they are a malformed list.

    It is cut by WORD, never midway: “Ferry fare for 4 passengers (detailing…)” → “Ferry fare”, which is a readable
    badge; cutting by characters would produce “Ferry fare for 4 passe”, which is unusable on screen."""
    seen, out = set(), []
    for raw_role in _strlist(raw, cap=6, chars=200):
        # A descriptive phrase masquerading as a role is reduced to its first clause, where the real name is.
        r = raw_role.split("(")[0].split(",")[0].split(":")[0].strip(" -–—")
        words = [w for w in (r or raw_role).split() if w]
        r = " ".join(words[:_b._MAX_ROLE_WORDS])[:_MAX_ROLE_CHARS].strip(" -–—")
        k = r.lower()
        if r and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def parse(raw: str, request: str = "") -> dict | None:
    """Composer JSON → validated brief. None if there is no usable JSON or it says this is not research.

    `request` — the operator's own words, kept for the signature. A size he named («the five best») is read by the
    composer, which sees his words; a word reader beside it would be a second, weaker opinion (V2-840 H1)."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        p = json.loads(s[i:j + 1])
    except Exception:
        return None
    if not isinstance(p, dict):
        return None
    if not p.get("research"):
        return None                      # the model itself says this requires neither breadth nor a quality bar

    breadth = p.get("breadth") if isinstance(p.get("breadth"), dict) else {}
    try:
        minc = int(breadth.get("min_candidates") or 0)
    except (TypeError, ValueError):
        minc = 0
    minc = max(0, min(_MIN_CANDIDATES_CAP, minc))   # 0 = the composer declared none: the worker is told no number

    deliv = p.get("deliverable") if isinstance(p.get("deliverable"), dict) else {}
    try:
        nfin = int(deliv.get("n_final") or _N_FINAL_DEFAULT)
    except (TypeError, ValueError):
        nfin = _N_FINAL_DEFAULT
    nfin = max(1, min(_N_FINAL_CAP, nfin))

    brief = {
        "goal": str(p.get("goal") or "").strip()[:400],
        "domain": str(p.get("domain") or "").strip()[:120],
        "hard": _strlist(p.get("hard")),
        **({"subjects": _strlist(p["subjects"], cap=6, chars=60)} if isinstance(p.get("subjects"), list) else {}),
        "soft": _strlist(p.get("soft")),
        "assumed": _strlist(p.get("assumed")),
        "enrichments": _strlist(p.get("enrichments")),
        "breadth": {"min_candidates": minc, "angles": _strlist(breadth.get("angles"))},
        # V2-840 H3 — WHERE this is listed, for the request's own country and category, named by the composer.
        "sources": _strlist(p.get("sources")),
        **({"market": m} if (m := _market(p.get("market"))) else {}),
        "quality_bar": _strlist(p.get("quality_bar")),
        # V2-825 F6: which connected resource the errand reads and how far back it must reach (`workers/reach_gap`).
        **({"window": {k: str(p["window"][k])[:32] for k in ("resource", "before") if p["window"].get(k)}}
           if isinstance(p.get("window"), dict) else {}),
        "deliverable": {
            "widget": str(deliv.get("widget") or "results").strip()[:40] or "results",
            "n_final": nfin,
            "composite": bool(deliv.get("composite")),
            "parts": _roles(deliv.get("parts")),
        },
        "round": 1,
        "ts": time.time(),
    }
    if not brief["goal"]:
        return None                      # without a restated objective there is no brief to direct anything
    return brief


def _market(raw) -> dict:
    """`{country, category}` as the composer wrote them — the words a local would search with in that market."""
    if not isinstance(raw, dict):
        return {}
    return {k: str(raw[k]).strip()[:60] for k in ("country", "category") if str(raw.get(k) or "").strip()}


def build_messages(request: str, context: str = "", today: str = "") -> list[dict]:
    user = []
    if today:
        user.append(today)
    if context:
        user.append("LO QUE EL ASISTENTE YA SABE DEL OPERADOR (úsalo para no preguntar lo que ya consta, y para "
                    "afinar los criterios):\n" + context[:1500])
    user.append("PETICIÓN DEL OPERADOR (literal):\n" + (request or "").strip()[:3000])
    return [{"role": "system", "content": _b._SYSTEM}, {"role": "user", "content": "\n\n".join(user)}]
