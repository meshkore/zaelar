"""The research brief's LIFE after composition: criteria for the sheet, the worker's prompt block, the stored brief
and the rounds by objective. Part of `nucleo.workers.brief`; the names that stay there are read through `_b`."""
from __future__ import annotations

import logging
import time

from nucleo.workers import brief as _b

logger = logging.getLogger("zaelar.research")


def to_criteria(brief: dict) -> dict:
    """The brief translated into the payload for the CRITERIA tab of the results sheet.

    Why it exists: until now, the criteria being used for the search were something that could only be ASKED
    («¿qué has entendido?») y por tanto no se podía comprobar de un vistazo. Se siembran desde AQUÍ, en el
    pre-vuelo, y no desde el worker: si dependieran de que el ejecutor se acuerde de escribirlos, faltarían justo
    en las búsquedas que peor van. `goal` hace además de firma del encargo — un objetivo distinto vacía la hoja de
    the previous search, and round 2 (which preserves the objective) deletes nothing."""
    if not isinstance(brief, dict) or not brief.get("goal"):
        return {}
    b = brief.get("breadth") or {}
    d = brief.get("deliverable") or {}
    out = {"goal": brief["goal"], "round": int(brief.get("round") or 1)}
    if brief.get("domain"):
        out["domain"] = brief["domain"]
    if isinstance(brief.get("subjects"), list):      # the sheet's door reads these, never a sentence's capitals
        out["subjects"] = list(brief["subjects"])
    for k in ("hard", "soft", "assumed", "enrichments", "quality_bar"):
        if brief.get(k):
            out[k] = list(brief[k])
    # V2-782 T4.3 — the FIELDS the operator's words ask for (price · rating · availability) travel as hard criteria,
    # so the sheet's candidacy can say «no row shows the rating» when the worker presents bare names.
    try:
        from search import criteria as _crit
        for line in _crit.hard_criteria(str(brief.get("request") or "")):
            if line not in out.setdefault("hard", []):
                out["hard"].append(line)
    except Exception as e:  # noqa: BLE001 — a grammar never costs the criteria tab
        logger.debug("research: asked fields not read (%r)", e)
    if brief.get("feedback"):
        out["changes"] = list(brief["feedback"])     # what the operator corrected when rejecting the previous round
    if b.get("min_candidates"):
        out["min_candidates"] = b["min_candidates"]
    if d.get("n_final"):
        out["n_final"] = d["n_final"]
    return out


async def seed_criteria(brief: dict, rec=None) -> None:
    """Pour the freshly composed brief into the CRITERIA tab of the results sheet.

    Done in the PRE-FLIGHT, never inside the worker: if it depended on the executor remembering to write it,
    it would be missing in exactly the searches that go worst. Side effect — and wanted: `goal` is the errand's
    signature, so starting a DIFFERENT research empties the previous sheet (the operator once sat looking at
    the previous search's results believing they were his), while a round 2 preserves the objective so
    «sigue buscando» deletes nothing.

    Hard best-effort: this is the SCREEN, not the work. If the widget fails, the research continues.
    (Lived in `nucleo/dispatch.py` until V2-644; moved here to pay the architecture ratchet — same module
    that composes the brief and already owns `to_criteria`.)"""
    try:
        payload = to_criteria(brief)
        # The errand's OWN sheet (2026-10-11, photo round): with no `sheet` the criteria went to the BASE `results`
        # box, and a desktop showing that errand's sheet got an empty base card mounted over it. No sheet, no seed.
        sheet = str(getattr(rec, "sheet", "") or "") if rec is not None else ""
        if not payload or (rec is not None and not sheet):
            return
        from widgets.server_api import brain_action
        await brain_action("results", "criteria", {**payload, **({"sheet": sheet} if sheet else {})})
    except Exception as exc:                                # noqa: BLE001 — never brake a task for the view
        logger.debug(f"research: could not seed the criteria into the results sheet ({exc})")


# `to_prompt_block`'s formatting lives in research_prompts.py (a leaf, no import of this file — no cycle); this
# wrapper keeps `_MIN_CANDIDATES_FLOOR` single-sourced here.
def to_prompt_block(brief: dict) -> str:
    from nucleo.research_prompts import to_prompt_block as _to_prompt_block_impl
    return _to_prompt_block_impl(brief, _b._MIN_CANDIDATES_FLOOR)


def save(task_id, brief: dict) -> None:
    if not brief:
        return
    try:
        from memory import api as memory
        memory.kv_set(f"{_b._KV}:{task_id}", brief)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"research: no pude persistir el brief de {task_id} ({e})")


def load(task_id) -> dict | None:
    try:
        from memory import api as memory
        out = memory.kv_get(f"{_b._KV}:{task_id}")
        return out if isinstance(out, dict) and out.get("goal") else None
    except Exception:
        return None


# ── ROUNDS by OBJECTIVE: “I’m not convinced, keep searching” continues; it does not restart ───────────────────
# Keyed by the objective's signature (not task_id): the operator's follow-up is a new task with no reference, and
# it inherits the agreed criteria with wider breadth. Asking the SAME thing within the TTL is round 2 on purpose.
_KV_ROUND = "research_rounds"     # UN registro con todas las rondas vivas (el casado es difuso, no por clave)


_ROUND_TTL = 6 * 3600


_ROUND_MATCH = 0.5                # mismo umbral de solape que la reanudación web (`dispatch._find_resume`)


_ROUND_MAX = 40                   # cota del registro: investigaciones vivas, no un histórico


def _rounds() -> dict:
    try:
        from memory import api as memory
        out = memory.kv_get(_KV_ROUND)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def remember_round(goal_key: str, brief: dict) -> None:
    if not goal_key or not brief:
        return
    try:
        from memory import api as memory
        now = time.time()
        reg = {k: v for k, v in _rounds().items()
               if isinstance(v, dict) and now - float(v.get("ts") or 0) <= _ROUND_TTL}
        reg[goal_key] = {"brief": brief, "ts": now}
        if len(reg) > _ROUND_MAX:                     # oldest first
            reg = dict(sorted(reg.items(), key=lambda kv: -float(kv[1].get("ts") or 0))[:_ROUND_MAX])
        memory.kv_set(_KV_ROUND, reg)
    except Exception:
        pass


def previous_round(goal_key: str) -> dict | None:
    """Brief of the live investigation that BEST matches this objective, or None if this is a new search.

    El casado es DIFUSO (solape de palabras de contenido ≥0.5) y no exacto, porque la frase con la que el operador
    pide continuar nunca es la misma que la inicial: «busca vacaciones en Baleares…» y luego «esos no me valen,
    sigue buscando» comparten el objetivo pero no el texto. Con casado exacto la continuación se leía como búsqueda
    nueva y repetía la ronda 1 con la misma amplitud — es decir, le devolvía al operador lo mismo que acababa de
    rechazar."""
    want = set((goal_key or "").split())
    if not want:
        return None
    now = time.time()
    best, best_score = None, 0.0
    for key, ent in _rounds().items():
        if not isinstance(ent, dict) or now - float(ent.get("ts") or 0) > _ROUND_TTL:
            continue
        other = set(str(key).split())
        union = len(want | other)
        score = (len(want & other) / union) if union else 0.0
        if score >= _ROUND_MATCH and score > best_score:
            b = ent.get("brief")
            if isinstance(b, dict) and b.get("goal"):
                best, best_score = b, score
    return best
