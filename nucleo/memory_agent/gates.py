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


# ── V2-033 · PRECISIÓN de escritura (el CORAZÓN no ensucia el largo plazo) ─────────────────────────────────────
# El modelo pequeño no obedece de forma fiable "descarta peticiones/preguntas" por prompt (lección del proyecto:
# los guards que importan son DETERMINISTAS). Estos gates filtran/ajustan lo que el CORAZÓN (LLM o heurística)
# intentaría persistir, para que SOLO entren afirmaciones con sustancia.

# (P0a) Un ÁTOMO ya canónico que en realidad es una PREGUNTA reificada o un ECO de petición al asistente — NO es un
# hecho del operador. Un hecho canónico es declarativo en 3ª persona ("Es alérgico…", "Le interesa…"); nunca lleva
# "?" ni "el operador pregunta si…" ni empieza por un imperativo dirigido al asistente.
#   OJO: NO metemos aquí el eco de imperativo crudo ("búscame …") — una TAREA CONCRETA ("búscame vuelos a Tokio")
#   SÍ es recordable ("¿qué te pedí?", `_COMMITMENT_RE`). El eco VAGO ("búscame algo") lo caza `_is_vague_request`
#   en la capa pre-LLM (sobre el turno crudo). Aquí solo lo INEQUÍVOCAMENTE no-hecho: interrogativos y preguntas/
#   peticiones REIFICADAS en 3ª persona (lo que el LLM pequeño produce al convertir una pregunta en "hecho").
_ATOM_NONFACT_RE = re.compile(
    r"\?|^\s*¿|"
    r"\bpregunt[aó]\s+(?:si|qu[eé]|cu[aá]l(?:es)?|cu[aá]ndo|d[oó]nde|c[oó]mo|cu[aá]nto|qui[eé]n|por\s+qu[eé])\b|"
    r"\bquiere\s+saber\b|\bse\s+pregunta\b|"
    r"\b(?:pide|pidi[oó]|quiere)\s+que\s+(?:le|se\s+le|me)\s+"
    r"(?:busque|busques|mire|mires|muestre|muestres|ense[ñn]e|ense[ñn]es|abra|abras|diga|digas|"
    r"recomiende|recomiendes|investigue|investigues)\b|"
    # petición de INFORMACIÓN reificada: "(necesita|quiere|pide) (más) información/datos/detalles (…) sobre/de X".
    # NARROW a propósito — exige el sustantivo información/datos/detalles + preposición, así "Necesita gafas" o
    # "Necesita terminar el informe" (hechos/compromisos reales) NO caen. (V2-033 follow-up: slip de "Necesita
    # información sobre el viento" visto en el bombardeo headless.)
    r"\b(?:necesit[ao]|quiere|pide|pidi[oó]|solicit[ao])\s+(?:m[aá]s\s+|una?\s+|nueva\s+)?"
    r"(?:informaci[oó]n|datos|detalles)(?:\s+\w+){0,2}\s+(?:sobre|de|del|acerca|respecto|para)\b|"
    # (P0c·C, V2-050) petición VAGA reificada al asistente con objeto indefinido: "quiere que repitan algo",
    # "pide que le muestre eso". NARROW: exige objeto vago (algo/eso/esto/lo mismo/lo de antes) → una tarea CONCRETA
    # ("quiere que le reserve la cita ITV") NO cae (la conserva el COMMITMENT-net).
    r"\b(?:quiere|pide|pidi[oó]|necesita|dice)\s+que\s+\w+(?:\s+\w+){0,2}\s+"
    r"(?:algo|eso|esto|lo\s+mismo|lo\s+de\s+antes|una\s+cosa)\b",
    re.I,
)

# (P0c·B, V2-050) un slot de IDENTIDAD (nombre/trato/ubicación…) es un ATRIBUTO ESTABLE — jamás una petición. El
# procesador a veces mis-asigna una orden ("entra en la web y reserva") al slot operator.treatment como si fuera
# "cómo tratarle". Si un átomo va a un slot de identidad y su texto es una petición reificada ("quiere/pide/
# necesita QUE …"), NO es ese atributo → se rechaza (no ensucia la identidad). Slot-scoped → los deseos de vida
# sueltos (slot=None) no se tocan.
_WANTS_THAT_RE = re.compile(r"\b(?:quiere|pide|pidi[oó]|necesita|solicit[ao]|dice)\s+que\b", re.I)

# (P0a) Petición VAGA / sin referente concreto ("mira eso", "búscame algo", "¿puedes mirar eso por mí?"): ruido, no
# una tarea recordable. DISTINTA de una tarea CONCRETA con dato ("búscame vuelos a Tokio"), que SÍ se recuerda.
_VAGUE_REQUEST_RE = re.compile(
    r"\b(?:mira|revisa|checa|comprueba|ve|b[uú]scame|b[uú]sca|encu[eé]ntrame|mir[aá]|ens[eé][ñn]ame)\s+"
    r"(?:eso|esto|aquello|algo|lo\s+de\s+(?:antes|eso))\b|"
    r"\bpuedes\s+(?:mirar|ver|revisar|checar|comprobar|buscar)\s+(?:eso|esto|aquello|algo)\b",
    re.I,
)

# (P1) Directiva de comportamiento EFÍMERA sobre la pantalla/acción inmediata → estilo de sesión, NO preferencia
# durable. Solo cuenta como efímera si NO trae marca de durabilidad ("prefiero/siempre/nunca/en general…").
_EPHEMERAL_DIRECTIVE_RE = re.compile(
    r"\bno\s+me\s+(?:muestres|ense[ñn]es|abras|pongas|saques)\b|"
    r"\bno\s+(?:muestres|abras|ense[ñn]es)\s+(?:nada|eso|esto)\b|"
    r"^\s*(?:ahora|de\s+momento|por\s+ahora)\s+no\b",
    re.I,
)
_DURABLE_PREF_MARKER_RE = re.compile(
    r"\b(prefiero|preferir[íi]a|me\s+gusta(?:r[íi]a)?|siempre|nunca|en\s+general|"
    r"por\s+lo\s+general|de\s+ahora\s+en\s+adelante|a\s+partir\s+de\s+ahora|"
    # CONDICIONAL/RECURRENTE = regla GENERAL, no directiva de sesión (batería v1 2026-07-20: «si es fin de
    # semana no me pongas recordatorios» caía como efímera y se perdía una user-rule durable)
    r"si\s+es|si\s+estoy|si\s+hay|cuando\s+\w+|cada\s+vez\s+que|los\s+fines?\s+de\s+semana|"
    r"los\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados?|domingos?)|"
    r"por\s+las?\s+(?:ma[ñn]anas?|tardes?|noches?)|entre\s+semana|on\s+weekends?|when(?:ever)?\s+\w+)\b", re.I)


# (P0c) VALIDEZ DE FORMATO de un slot TIPADO (V2-050): un dato de identidad con formato canónico (email, teléfono)
# cuyo VALOR está malformado NO es un hecho durable — es garble del STT ("mi email es rjj.com" → 'rjj.com' sin @ no
# es un email). Sin esto el valor roto se guardaba en el slot y competía con el bueno (bug ITV: rjj.com pisando
# rjj@proars.com). Validación de FORMATO determinista, keyed SOLO por el slot que el procesador ya asignó → NO toca
# preferencias ("prefiere el correo por la mañana" no lleva slot operator.email, así que no se filtra).
_EMAIL_OK_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)


def _atom_value_invalid(atom: dict) -> bool:
    """True si el átomo va a un slot TIPADO pero su valor está MALFORMADO (no ensuciar la identidad con garble)."""
    slot = (atom.get("slot") or "").strip().lower()
    hay = ((atom.get("value") or "") + " " + (atom.get("text") or "")).strip()
    if slot == "operator.email":
        return not _EMAIL_OK_RE.search(hay)
    if slot == "operator.phone":
        return len(re.sub(r"\D", "", hay)) < 7        # un teléfono real tiene ≥7 dígitos; menos = cortado/garble
    return False


def _atom_is_nonfact(text: str) -> bool:
    """(P0a) El átomo canónico es una pregunta reificada / eco de petición al asistente → no es un hecho durable."""
    return bool(_ATOM_NONFACT_RE.search(text or ""))


def _is_ephemeral_directive(t: str) -> bool:
    """(P1) Directiva efímera de pantalla/acción, sin marca de durabilidad → no es preferencia durable."""
    return bool(_EPHEMERAL_DIRECTIVE_RE.search(t or "")) and not _DURABLE_PREF_MARKER_RE.search(t or "")


def _is_vague_request(t: str) -> bool:
    """(P0a) Petición vaga sin referente concreto → ruido, no tarea recordable."""
    return bool(_VAGUE_REQUEST_RE.search(t or ""))


def _precision_reject_atom(atom: dict, *, raw: str) -> bool:
    """V2-033: ¿este átomo ensuciaría el largo plazo? (pregunta/petición reificada, o pref derivada de directiva
    efímera). Se aplica a la salida del LLM Y de la heurística antes de escribir."""
    if _atom_is_nonfact(atom.get("text") or ""):
        return True
    if _atom_value_invalid(atom):                 # (P0c) slot tipado con valor malformado (email sin @, tel cortado)
        return True
    # (P0c·B) petición reificada mis-asignada a un slot de IDENTIDAD → no es ese atributo, se rechaza.
    if (atom.get("slot") or "").strip().lower() in _IDENTITY_SLOTS and _WANTS_THAT_RE.search(atom.get("text") or ""):
        return True
    if (atom.get("kind") == "pref" or atom.get("dest") == "state") and _is_ephemeral_directive(raw):
        return True
    return False


_DEMOTE_STOP = frozenset({"del", "los", "las", "una", "uno", "con", "por", "para", "que", "the", "and",
                          "gris", "azul", "rojo", "negro", "blanco", "verde"})


def _same_entity_refinement(cur: str, new: str) -> bool:
    """(P0b·V2-050) ¿el valor NUEVO es un REFINAMIENTO del MISMO ente que el establecido, no un garble a otro? Sí si
    comparten un token DISTINTIVO (len≥4, sin colores/stopwords): 'Dacia Duster'↔'Duster gris'↔'Duster de Dacia'
    comparten «duster» → mismo coche (facetas), NO cuarentena → el slot superseda («el más reciente MANDA», ≤2
    facetas, bot v2 #21). SEGURO para garble de identidad: 'Ricard'↔'Teigano' o 'Ana García'↔'Ana Pérez' (ana<4,
    apellido distinto) NO comparten token len≥4 → siguen cuarentenados."""
    import re as _re
    ta = {w for w in _re.findall(r"\w+", cur.lower()) if len(w) >= 4 and w not in _DEMOTE_STOP}
    tb = {w for w in _re.findall(r"\w+", new.lower()) if len(w) >= 4 and w not in _DEMOTE_STOP}
    return bool(ta & tb)


def _plausibility_demote(atom: dict, *, state: dict, is_correction: bool) -> dict:
    """(P0b) Un slot de IDENTIDAD singular cuyo valor NUEVO contradice el ya establecido NO sobrescribe el `state`
    en una mención única no confirmada (típico garble del STT): se degrada a `long` recuperable con menor peso y sin
    slot, dejando la identidad intacta. Las CORRECCIONES explícitas ('no me llamo X sino Y') sí pasan — ya olvidaron
    el valor viejo antes en el flujo. En un perfil VACÍO (primer dato) no hay conflicto → entra normal. Un
    REFINAMIENTO del mismo ente (comparte token distintivo) tampoco es garble → supersede (V2-050)."""
    if is_correction or atom.get("dest") != "state":
        return atom
    slot = atom.get("slot")
    field = _SLOT_TO_STATE_FIELD.get(slot or "")
    if slot in _GARBLE_GUARD_SLOTS and field:
        cur = str(state.get(field) or "").strip().lower()
        new = str((atom.get("state_patch") or {}).get(field) or "").strip().lower()
        # contradice una identidad YA establecida Y no es un refinamiento del mismo ente → no corromper el estado
        if cur and new and cur != new and not _same_entity_refinement(cur, new):
            a = dict(atom)
            a.update(dest="long", state_patch={}, slot=None, pinned=False,
                     importance=min(float(atom.get("importance", 0.5)), 0.4),
                     _quarantine=True)             # → meta.trust=untrusted en _write_atom: recuperable solo por
            return a                               #   consulta explícita, NUNCA aflora en recall/prompt (anti-garble)
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
    """VISIBLE por la misma razón que `_report_slot_guard`, y aquí hace además un segundo trabajo.

    `_talks_about_the_operator` es una ENUMERACIÓN de marcas de primera persona, y una enumeración por idiomas
    nunca está completa: el hueco que deja no es escribir de más, es NO aprender una mudanza legítima dicha en
    una lengua que la lista no cubre. Ese fallo sería mudo —el operador diría «me he mudado» y la memoria no se
    enteraría, sin nada en ninguna pantalla— así que cada vez que la puerta calla una autodeclaración deja
    RASTRO con la frase entera. Si aparece aquí una mudanza de verdad, la lista tiene un agujero con nombre y
    apellidos en vez de una queja de que «no se acuerda».
    """
    detail = f"slot {slot}: `change` autodeclarado IGNORADO — el turno no habla del operador: {raw[:160]!r}"
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
# V2-033 P0b: inverso slot→campo de state + conjunto de slots de IDENTIDAD singular (un valor nuevo que contradiga
# el establecido no debe sobrescribir el estado en una mención única no confirmada — garble del STT).
_SLOT_TO_STATE_FIELD = {v: k for k, v in _PATCH_TO_SLOT.items()}
_IDENTITY_SLOTS = _memslots.identity_slots()
_GARBLE_GUARD_SLOTS = _memslots.garble_guard_slots()   # P0b: identidad garble-able (las prefs reformulables NO)


def _slot_for_patch(patch: dict) -> str | None:
    """Slot canónico para una traza de perfil (el primero que aparezca en el patch). Fail-open: None si no hay."""
    for k in patch:
        if k in _PATCH_TO_SLOT:
            return _PATCH_TO_SLOT[k]
    return None


