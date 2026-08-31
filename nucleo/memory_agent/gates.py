"""Write-precision gates (V2-033 P0a · P0b · P0d) and the identity-slot tables.

Split out VERBATIM (audit 2026-08-23). The most delicate code in the subsystem: quarantine is a PROMISE
(reachable on explicit ask, never in the passive prompt), and every gate that stays silent leaves a trace —
a protection that fires in silence is indistinguishable from the bug it prevents.
"""
from __future__ import annotations

import re

from loguru import logger

from nucleo.memory_agent.lang_marks import (_RELOCATION_RE, _looks_like_injection,  # noqa: F401
                                            _talks_about_the_operator)


# ── V2-033 · WRITE PRECISION (the CORE does not dirty the long term) ───────────────────────────────────────────
# The small model does not reliably obey "discard requests/questions" through prompting (a project lesson:
# the guards that matter are DETERMINISTIC). These gates filter/adjust what the CORE (LLM or heuristic)
# would try to persist, so that ONLY substantive assertions get in.

# (P0a) A canonical ATOM that is actually a reified QUESTION or an ECHO of a request to the assistant is NOT an
# operator fact. A canonical fact is declarative in the 3rd person ("Es alérgico…", "Le interesa…"); it never has
# "?" or "el operador pregunta si…" and never starts with an imperative addressed to the assistant.
#   NOTE: We do NOT put the raw imperative echo ("búscame …") here — a CONCRETE TASK ("búscame vuelos a Tokio")
#   IS recordable ("¿qué te pedí?", `_COMMITMENT_RE`). The VAGUE echo ("búscame algo") is caught by
#   `_is_vague_request` in the pre-LLM layer (over the raw turn). Here we only reject the UNAMBIGUOUSLY non-facts:
#   interrogatives and reified questions/requests in the 3rd person (what the small LLM produces when turning a
#   question into a "fact").
_ATOM_NONFACT_RE = re.compile(
    r"\?|^\s*¿|"
    r"\bpregunt[aó]\s+(?:si|qu[eé]|cu[aá]l(?:es)?|cu[aá]ndo|d[oó]nde|c[oó]mo|cu[aá]nto|qui[eé]n|por\s+qu[eé])\b|"
    r"\bquiere\s+saber\b|\bse\s+pregunta\b|"
    r"\b(?:pide|pidi[oó]|quiere)\s+que\s+(?:le|se\s+le|me)\s+"
    r"(?:busque|busques|mire|mires|muestre|muestres|ense[ñn]e|ense[ñn]es|abra|abras|diga|digas|"
    r"recomiende|recomiendes|investigue|investigues)\b|"
    # Reified INFORMATION request: "(necesita|quiere|pide) (más) información/datos/detalles (…) sobre/de X".
    # Deliberately NARROW — requires the noun información/datos/detalles + preposition, so "Necesita gafas" or
    # "Necesita terminar el informe" (real facts/commitments) do NOT match. (V2-033 follow-up: slip of "Necesita
    # información sobre el viento" seen in the headless bombardment.)
    r"\b(?:necesit[ao]|quiere|pide|pidi[oó]|solicit[ao])\s+(?:m[aá]s\s+|una?\s+|nueva\s+)?"
    r"(?:informaci[oó]n|datos|detalles)(?:\s+\w+){0,2}\s+(?:sobre|de|del|acerca|respecto|para)\b|"
    # (P0c·C, V2-050) VAGUE reified request to the assistant with an indefinite object: "quiere que repitan algo",
    # "pide que le muestre eso". NARROW: requires a vague object (algo/eso/esto/lo mismo/lo de antes) → a CONCRETE
    # task ("quiere que le reserve la cita ITV") does NOT match (the COMMITMENT-net preserves it).
    r"\b(?:quiere|pide|pidi[oó]|necesita|dice)\s+que\s+\w+(?:\s+\w+){0,2}\s+"
    r"(?:algo|eso|esto|lo\s+mismo|lo\s+de\s+antes|una\s+cosa)\b",
    re.I,
)

# (P0c·B, V2-050) an IDENTITY slot (name/form of address/location…) is a STABLE ATTRIBUTE — never a request. The
# processor sometimes misassigns an order ("entra en la web y reserva") to the operator.treatment slot as if it were
# "how to address them". If an atom goes to an identity slot and its text is a reified request ("quiere/pide/
# necesita QUE …"), it is NOT that attribute → reject it (do not dirty identity). Slot-scoped → standalone life
# wishes (slot=None) are untouched.
_WANTS_THAT_RE = re.compile(r"\b(?:quiere|pide|pidi[oó]|necesita|solicit[ao]|dice)\s+que\b", re.I)

# (P0a) VAGUE request / without a concrete referent ("mira eso", "búscame algo", "¿puedes mirar eso por mí?"):
# noise, not a recordable task. DISTINCT from a CONCRETE task with data ("búscame vuelos a Tokio"), which IS
# remembered.
_VAGUE_REQUEST_RE = re.compile(
    r"\b(?:mira|revisa|checa|comprueba|ve|b[uú]scame|b[uú]sca|encu[eé]ntrame|mir[aá]|ens[eé][ñn]ame)\s+"
    r"(?:eso|esto|aquello|algo|lo\s+de\s+(?:antes|eso))\b|"
    r"\bpuedes\s+(?:mirar|ver|revisar|checar|comprobar|buscar)\s+(?:eso|esto|aquello|algo)\b",
    re.I,
)

# (P1) EPHEMERAL behavior directive about the screen/immediate action → session style, NOT a durable preference.
# It counts as ephemeral only if it has NO durability marker ("prefiero/siempre/nunca/en general…").
_EPHEMERAL_DIRECTIVE_RE = re.compile(
    r"\bno\s+me\s+(?:muestres|ense[ñn]es|abras|pongas|saques)\b|"
    r"\bno\s+(?:muestres|abras|ense[ñn]es)\s+(?:nada|eso|esto)\b|"
    r"^\s*(?:ahora|de\s+momento|por\s+ahora)\s+no\b",
    re.I,
)
_DURABLE_PREF_MARKER_RE = re.compile(
    r"\b(prefiero|preferir[íi]a|me\s+gusta(?:r[íi]a)?|siempre|nunca|en\s+general|"
    r"por\s+lo\s+general|de\s+ahora\s+en\s+adelante|a\s+partir\s+de\s+ahora|"
    # CONDITIONAL/RECURRING = GENERAL rule, not a session directive (battery v1 2026-07-20: «si es fin de
    # semana no me pongas recordatorios» was classified as ephemeral and a durable user rule was lost)
    r"si\s+es|si\s+estoy|si\s+hay|cuando\s+\w+|cada\s+vez\s+que|los\s+fines?\s+de\s+semana|"
    r"los\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados?|domingos?)|"
    r"por\s+las?\s+(?:ma[ñn]anas?|tardes?|noches?)|entre\s+semana|on\s+weekends?|when(?:ever)?\s+\w+)\b", re.I)


# (P0c) FORMAT VALIDITY of a TYPED slot (V2-050): an identity value with canonical format (email, phone)
# whose VALUE is malformed is NOT a durable fact — it is STT garble ("mi email es rjj.com" → 'rjj.com' without @
# is not an email). Without this, the broken value was stored in the slot and competed with the good one (ITV bug:
# rjj.com overwriting rjj@proars.com). Deterministic FORMAT validation, keyed ONLY by the slot already assigned by
# the processor → does NOT touch preferences ("prefiere el correo por la mañana" has no operator.email slot, so it
# is not filtered).
_EMAIL_OK_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)


def _atom_value_invalid(atom: dict) -> bool:
    """True if the atom targets a TYPED slot but its value is MALFORMED (do not dirty identity with garble)."""
    slot = (atom.get("slot") or "").strip().lower()
    hay = ((atom.get("value") or "") + " " + (atom.get("text") or "")).strip()
    if slot == "operator.email":
        return not _EMAIL_OK_RE.search(hay)
    if slot == "operator.phone":
        return len(re.sub(r"\D", "", hay)) < 7        # a real phone has ≥7 digits; fewer = truncated/garble
    return False


def _atom_is_nonfact(text: str) -> bool:
    """(P0a) The canonical atom is a reified question / request echo to the assistant → not a durable fact."""
    return bool(_ATOM_NONFACT_RE.search(text or ""))


def _is_ephemeral_directive(t: str) -> bool:
    """(P1) Ephemeral screen/action directive, without a durability marker → not a durable preference."""
    return bool(_EPHEMERAL_DIRECTIVE_RE.search(t or "")) and not _DURABLE_PREF_MARKER_RE.search(t or "")


def _is_vague_request(t: str) -> bool:
    """(P0a) Vague request without a concrete referent → noise, not a recordable task."""
    return bool(_VAGUE_REQUEST_RE.search(t or ""))


def _precision_reject_atom(atom: dict, *, raw: str) -> bool:
    """V2-033: would this atom dirty the long term? (reified question/request, or preference derived from an
    ephemeral directive). Applied to both LLM and heuristic output before writing."""
    if _atom_is_nonfact(atom.get("text") or ""):
        return True
    if _atom_value_invalid(atom):                 # (P0c) typed slot with malformed value (email without @, truncated phone)
        return True
    # (P0c·B) Reified request misassigned to an IDENTITY slot → it is not that attribute; reject it.
    if (atom.get("slot") or "").strip().lower() in _IDENTITY_SLOTS and _WANTS_THAT_RE.search(atom.get("text") or ""):
        return True
    if (atom.get("kind") == "pref" or atom.get("dest") == "state") and _is_ephemeral_directive(raw):
        return True
    return False


_DEMOTE_STOP = frozenset({"del", "los", "las", "una", "uno", "con", "por", "para", "que", "the", "and",
                          "gris", "azul", "rojo", "negro", "blanco", "verde"})


def _same_entity_refinement(cur: str, new: str) -> bool:
    """(P0b·V2-050) Is the NEW value a REFINEMENT of the SAME entity as the established one, not garble into another?
    Yes if they share a DISTINCTIVE token (len≥4, excluding colors/stopwords): 'Dacia Duster'↔'Duster gris'↔'Duster
    de Dacia' share «duster» → same car (facets), NOT quarantine → the slot supersedes ("the most recent WINS", ≤2
    facets, bot v2 #21). SAFE for identity garble: 'Ricard'↔'Teigano' or 'Ana García'↔'Ana Pérez' (ana<4,
    different surname) do NOT share a token len≥4 → remain quarantined."""
    import re as _re
    ta = {w for w in _re.findall(r"\w+", cur.lower()) if len(w) >= 4 and w not in _DEMOTE_STOP}
    tb = {w for w in _re.findall(r"\w+", new.lower()) if len(w) >= 4 and w not in _DEMOTE_STOP}
    return bool(ta & tb)


def _plausibility_demote(atom: dict, *, state: dict, is_correction: bool) -> dict:
    """(P0b) A singular IDENTITY slot whose NEW value contradicts the established one does NOT overwrite `state`
    in a single unconfirmed mention (typical STT garble): it is demoted to recoverable `long` with lower weight and
    no slot, leaving identity intact. Explicit CORRECTIONS ('no me llamo X sino Y') pass — the old value was already
    forgotten earlier in the flow. In an EMPTY profile (first datum) there is no conflict → it enters normally. A
    REFINEMENT of the same entity (sharing a distinctive token) is not garble either → supersedes (V2-050)."""
    if is_correction or atom.get("dest") != "state":
        return atom
    slot = atom.get("slot")
    field = _SLOT_TO_STATE_FIELD.get(slot or "")
    if slot in _GARBLE_GUARD_SLOTS and field:
        cur = str(state.get(field) or "").strip().lower()
        new = str((atom.get("state_patch") or {}).get(field) or "").strip().lower()
        # Contradicts an ALREADY established identity AND is not a refinement of the same entity → do not corrupt state.
        if cur and new and cur != new and not _same_entity_refinement(cur, new):
            a = dict(atom)
            a.update(dest="long", state_patch={}, slot=None, pinned=False,
                     importance=min(float(atom.get("importance", 0.5)), 0.4),
                     _quarantine=True)             # → meta.trust=untrusted in _write_atom: recoverable only via
            return a                               #   explicit query, NEVER surfaces in recall/prompt (anti-garble)
    return atom


def _slot_supersede_guard(atom: dict, *, is_correction: bool) -> dict:
    """(P0d, 2026-08-19) A contradicting value must not SUPERSEDE an established identity pill.

    `_plausibility_demote` (P0b) protects the `state`, and it does that job well — verified: after "El cumpleaños
    de Marta es el 3 de mayo", `operator_name` stayed Ricart and `birthday` stayed 12 February. But the
    destructive operation is not the state write, it is the **slot supersede**, and P0b cannot see it: it returns
    early on `dest != "state"`, and it then requires `_SLOT_TO_STATE_FIELD[slot]` to exist. A third party's fact
    arrives as `dest="long"` with `slot="operator.birthday"` — failing BOTH conditions — and the writer's "the
    most recent MANDA" rule invalidates the operator's own pill. Reproduced end to end: the operator's row went
    `valid=0` and `query("¿cuándo es mi cumpleaños?")` answered with Marta's date. The `state` still held the
    right value, so the ESTADO block in the prompt was fine and only the RECALL path lied — which is worse than a
    visible break, because it is the path the worker dossier and `compose_recall` read.

    Five identity slots had NO contradiction protection at all for this reason (`birthday`, `phone`, `email`,
    `address`, `diet`): the existing guard is keyed on having a `state_field`, which is an unrelated property.

    This is not a new heuristic — it is P0b's own rule (a contradicting value does not overwrite an established
    identity unless it is an explicit correction, and a refinement of the same entity is not a contradiction)
    applied at the layer where the loss happens. The DIFFERENCE from P0b is the disposal: a garbled name is junk
    and gets quarantined, whereas "Marta's birthday" is perfectly good information about someone else — so the
    pill is KEPT as a normal durable fact and only its `slot` is dropped. Quarantining it would fix the overwrite
    by throwing away the fact, which is the same data loss wearing a different hat.

    The prompt already forbids this ("slot: SOLO para ATRIBUTOS SINGULARES del operador", "personas del entorno →
    slot=null SIEMPRE") and the model does it anyway: 0/5 with an empty profile, 3/5 with an identity established
    — it misfires precisely when there is something to destroy. Small samples, so no rate is claimed; a
    deterministic backstop for a real, reproducible loss does not need one."""
    if is_correction:
        return atom                      # an explicit correction is exactly what SHOULD overwrite
    slot = _writer_canon(atom.get("slot"))
    if not slot or slot not in _IDENTITY_SLOTS or slot not in _GARBLE_GUARD_SLOTS:
        return atom
    new = str(atom.get("value") or "").strip().lower()
    if not new:
        return atom                      # no declared value → nothing to compare; keep today's behaviour
    cur = _established_slot_value(slot)
    if not cur or cur == new or _same_entity_refinement(cur, new):
        return atom                      # first value, same value, or a refinement of the same thing
    a = dict(atom, slot=None, state_patch={})
    _report_slot_guard(slot, cur, new, atom.get("text") or "")
    return a


def _writer_canon(slot) -> str:
    """Through the FACADE, not `memory.writer`. The contract test caught the direct reach and its message is the
    design ("move the new call to memory.api"), so `canon_slot` is re-exported there instead of the ceiling being
    raised — a ratchet you loosen when it fires is not a ratchet."""
    try:
        from memory import api as _api
        return (_api.canon_slot(slot) or "") if slot else ""
    except Exception:  # noqa: BLE001
        return str(slot or "")


def _established_slot_value(slot: str) -> str:
    """The value the slot currently holds, from the VALID pill — not from `state`, which is exactly the source
    that does not exist for the five slots this guard was written for. Reads `meta.value` (persisted since P0d),
    falling back to the state_patch a pill may carry. Returns "" when the established row predates P0d and
    recorded no value: the guard then declines to act rather than compare sentences, which the refinement test
    would misread as the same entity because they share the attribute word."""
    try:
        from memory import api as _api
        row = _api.as_of(slot)          # ts=None = now; the clock stays behind the facade (contract test)
        if not row:
            return ""
        meta = row.get("meta")
        if isinstance(meta, str):
            import json as _json
            meta = _json.loads(meta) if meta.strip() else {}
        meta = meta if isinstance(meta, dict) else {}
        v = meta.get("value")
        if not v:
            for candidate in (meta.get("state_patch") or {}).values():
                if isinstance(candidate, str) and candidate.strip():
                    v = candidate
                    break
        return str(v or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""                        # never block a write because the lookup failed


def _report_self_declared_change_ignored(slot: str, raw: str) -> None:
    """VISIBLE for the same reason as `_report_slot_guard`, and it also does a second job here.

    `_talks_about_the_operator` is an ENUMERATION of first-person markers, and an enumeration across languages
    is never complete: its gap does not cause over-writing, but failure to learn a legitimate move stated in a
    language the list does not cover. That failure would be silent —the operator would say «me he mudado» and
    memory would not know, with nothing on any screen— so whenever the gate silences a self-declaration it leaves
    a TRACE with the entire phrase. If a real move appears here, the list has a named gap rather than a complaint
    that it «does not remember».
    """
    detail = f"slot {slot}: self-declared `change` IGNORED — the turn is not about the operator: {raw[:160]!r}"
    try:
        from voice.observer import emit
        emit("memory", "identidad protegida de una autodeclaración", text=detail,
             extra={"module": "memory_agent.P0b", "slot": slot, "raw": raw[:200]})
    except Exception:  # noqa: BLE001
        pass
    logger.info(f"memory_agent P0b: {detail}")


def _report_slot_guard(slot: str, cur: str, new: str, text: str) -> None:
    """VISIBLE, because a protection that fires in silence is indistinguishable from the bug it prevents — the
    rule this module has already paid for three times. Not `health_state`: this is a guard working as designed,
    not a degradation."""
    detail = f"slot {slot} NOT superseded: established {cur!r} vs {new!r} — kept as a plain durable fact"
    try:
        from voice.observer import emit
        emit("memory", "slot de identidad protegido", text=detail,
             extra={"module": "memory_agent.P0d", "slot": slot, "pill": text[:120]})
    except Exception:  # noqa: BLE001
        pass
    logger.info(f"memory_agent P0d: {detail}")




# Slot↔state-field maps + IDENTITY set: derived from the CANONICAL registry `memory/slots.py`
# (2026-07-14 audit — before this they were a hand-kept sublist that drifted from the processor's prompt:
# operator.phone/address/diet were declared singular in the prompt yet had NO P0b gate protection).
from memory import slots as _memslots

_PATCH_TO_SLOT = _memslots.patch_to_slot()
# V2-033 P0b: inverse slot→state field + set of singular IDENTITY slots (a new value contradicting the established
# one must not overwrite state in a single unconfirmed mention — STT garble).
_SLOT_TO_STATE_FIELD = {v: k for k, v in _PATCH_TO_SLOT.items()}
_IDENTITY_SLOTS = _memslots.identity_slots()
_GARBLE_GUARD_SLOTS = _memslots.garble_guard_slots()   # P0b: garble-able identity (reformulable preferences NO)


def _slot_for_patch(patch: dict) -> str | None:
    """Canonical slot for a profile trace (the first one appearing in the patch). Fail-open: None if absent."""
    for k in patch:
        if k in _PATCH_TO_SLOT:
            return _PATCH_TO_SLOT[k]
    return None
