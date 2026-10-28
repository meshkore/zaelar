"""The writer's pure rules: semantic-dedup calibration, text normalisation, the critical-health detector, base
importance per kind, canonical slots, the clock and vector packing. No writes."""
import json
import os
import re
import struct

from .. import embeddings as _emb
from .. import slots as _slots

# SEMANTIC dedup on insert (V2-013 · T125): before creating a DURABLE slotless memory, look for a near-identical
# one by MEANING; L2 distance (normalised vectors) ≤ this → REINFORCE the existing one instead. Calibrated on
# embeddinggemma: the same fact in other words ≤0.51, facts that only share an ENTITY ≥0.80. 0.45 is CONSERVATIVE
# («Laura is my boss» vs «Laura asked me for the report» must NOT merge): a harmless near-duplicate beats a merge
# that loses information. Configurable (`MEM_DEDUP_MAX_DIST` / `MEM_SEMANTIC_DEDUP`).
#
# ⚠️ BACKEND-DEPENDENT: 0.45 is ONE model's geometry. Measured on fastembed, completely unrelated sentences fell
# under 0.45 and MERGED (the new message lost). Without a per-backend calibration study, semantic dedup only runs
# on the calibrated backend; any other falls back to exact/slot dedup (deterministic, no false positives).
SEMANTIC_DEDUP_MAX_DIST = float(os.getenv("MEM_DEDUP_MAX_DIST", "0.45"))
_SEMANTIC_DEDUP_CALIBRATED_BACKENDS = {"ollama"}   # the only backend with the distance study behind the threshold


def _semantic_dedup_on() -> bool:
    if os.getenv("MEM_SEMANTIC_DEDUP", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return _emb.active_backend() in _SEMANTIC_DEDUP_CALIBRATED_BACKENDS


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Normalises text for comparison (exact dedup by slot): trim + lowercase + collapsed whitespace."""
    return _WS.sub(" ", (text or "").strip().lower())


# MEDICAL SAFETY: an ALLERGY/intolerance is an ADDITIVE, CRITICAL fact. The LLM used to put it in the SINGULAR
# slot `operator.diet`, so a later diet SUPERSEDED (deleted) the allergy — a safety failure. A DETERMINISTIC
# detector (es/en) for the writer's guard, the ONE chokepoint every write passes through → universal protection.
_CRITICAL_HEALTH_RE = re.compile(
    r"\b(al[eé]rgic[oa]s?|alergia|anafila|intoleran(?:te|cia)|"
    r"allerg(?:ic|y)|intoleran(?:t|ce)|"
    r"celiac[oa]|cel[íi]ac[oa]|diab[eé]tic[oa]|diabetes|epil[eé]p|marcapasos|anticoagul|"
    r"asm[aá]tic[oa])\b", re.I)


# AN INGESTION LIMIT DOES NOT ALWAYS CARRY ITS CATEGORY WORD (V2-499, false positives accepted by the operator):
# half the time people say what they CANNOT do («no puede comer gluten»), which matches no category word above.
# ⚠️ The cost is real: the critical line is capped (6), so a social false positive can EVICT a pacemaker. Hence the
# only bound that needs no guessing: a restriction that NAMES A MOMENT («hoy no puedo comer») is about the moment,
# not the person, and stays out. The ambiguous undated case is kept on purpose — this line exists to err on more.
_INGESTION_LIMIT_RE = re.compile(
    r"(?:\bno\s+(?:puede[ns]?|puedo|debe[ns]?|debo)\s+(?:comer|tomar|beber|ingerir|probar|consumir)\b"
    r"|\b(?:can(?:no|')?t|cannot|must\s+not|mustn'?t)\s+(?:eat|drink|have|take|consume)\b)", re.I)

# A restriction dated to a concrete moment is not a durable fact about the person.
_MOMENTARY_RE = re.compile(
    r"\b(hoy|ahora\s+mismo|ahora|esta\s+noche|este\s+rato|luego|m[aá]s\s+tarde|"
    r"today|tonight|right\s+now|later)\b", re.I)


def _is_critical_health(text: str) -> bool:
    t = text or ""
    if _CRITICAL_HEALTH_RE.search(t):
        return True
    return bool(_INGESTION_LIMIT_RE.search(t)) and not _MOMENTARY_RE.search(t)


def _stamp_critical(meta):
    """Stamps meta.critical='health', keeping whatever was there (dict/JSON/None)."""
    if isinstance(meta, dict):
        return {**meta, "critical": "health"}
    if isinstance(meta, str) and meta.strip():
        try:
            d = json.loads(meta)
            if isinstance(d, dict):
                d["critical"] = "health"
                return d
        except Exception:
            pass
        return meta
    return {"critical": "health"}

# base importance per memory kind (I0). Tunable per profile.
_IMPORTANCE_BY_KIND = {
    "fact": 0.7,
    "pref": 0.7,
    "insight": 0.65,
    "summary": 0.55,
    "event": 0.5,
    "msg": 0.4,
}


def _now() -> int:
    from ..clock import now
    return now()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


# SLOT NORMALISATION: the LLM emits slot names freely ('location', 'ubicacion'…) while the heuristics use the
# canonical ones ('operator.location') → TWO lineages of one singular fact that never supersede each other. Every
# write passes through the writer, so it is normalised HERE. The vocabulary and aliases live in ONE registry,
# `memory/slots.py`. Unknown/namespaced slots pass lowercased/stripped.
def canon_slot(slot: str | None) -> str | None:
    """Canonical slot: lowercase + strip + alias → one slot language for the exact supersede."""
    return _slots.canonical(slot)
