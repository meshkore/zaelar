"""The language-mark bank: every deterministic es/en(+ca/fr/it/pt/de) pattern the write path reads.

Split out of the old monolithic memory_agent.py (architecture audit 2026-08-23) VERBATIM — this file is DATA
expressed as regexes, and its known failure class is MUTE: an enumeration of first-person marks that misses a
language does not over-write, it silently fails to learn (see `_report_self_declared_change_ignored`). Growing
a language means growing patterns here, nowhere else.
"""
from __future__ import annotations

import re


# ── Classification heuristic (es/en) ────────────────────────────────────────────────────────────────────────
# PROFILE data → the `state` table. Triggers are case-insensitive via `(?i:...)` while captures keep the text's
# case (a global `re.I` makes `[A-Z]` match lower case: «soy feliz» would become `operator_name`). Too-ambiguous
# triggers («soy», «estoy en», «I'm») are left out; captures stop at « y »/« and ».
_PROFILE_NAME_RE = re.compile(
    r"(?:(?i:me\s+llamo|mi\s+nombre\s+es|my\s+name\s+is))\s+"
    r"([A-ZÁÉÍÓÚÑa-záéíóúñ][\wÁÉÍÓÚÑáéíóúñ'’\-]{1,30}(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ][\wÁÉÍÓÚÑáéíóúñ'’\-]{1,30}){0,2})",
)
# MOVE (V2-038 #2): the real spoken variants; a missing one left the OLD city in the state.
_MOVE_VERBS = (
    r"me\s+(?:he\s+)?mud(?:o|[eé]|ado)\s+a|nos\s+(?:hemos\s+)?mud(?:amos|ado)\s+a|"
    r"(?:me|nos)\s+acab(?:o|amos)\s+de\s+mudar(?:me|nos)?\s+a|acab(?:o|amos)\s+de\s+mudar(?:me|nos)\s+a|"
    r"me\s+estoy\s+mudando\s+a|nos\s+estamos\s+mudando\s+a|"
    r"me\s+(?:he\s+)?traslad(?:o|[eé]|ado)\s+a|nos\s+(?:hemos\s+)?traslad(?:amos|ado)\s+a|"
    r"i\s+(?:just\s+)?moved\s+to|i'?ve\s+(?:just\s+)?moved\s+to|i'?m\s+moving\s+to|i\s+relocated\s+to|"
    r"i\s+now\s+live\s+in"
)
_PROFILE_LOC_RE = re.compile(
    r"(?:(?i:vivo\s+en|resido\s+en|mi\s+ciudad\s+es|i\s+live\s+in|" + _MOVE_VERBS + r")"
    # «ahora estoy en X» ONLY with a Capitalised city, never an article or a common place (STT all-caps too).
    r"|(?i:ahora\s+estoy\s+en)(?=\s+[A-ZÁÉÍÓÚÑ])(?!\s+(?i:el|la|los|las|un|una|mi|tu|su|casa|clase|trabajo|"
    r"coche|cama|medio)\b))\s+"
    r"([A-ZÁÉÍÓÚÑa-záéíóúñ][\w\sÁÉÍÓÚÑáéíóúñ'’\-]{1,40}?)(?=[.,;\n]|\s+y\s+|\s+and\s+|$)",
)
# The SAME move as a «correction» signal (V2-033 P0b): a declared change of life is not STT garble, so it may
# OVERWRITE the established location (the slot supersedes the old pill). «ahora/ya vivo en» count too.
_RELOCATION_RE = re.compile(
    r"\b(?i:" + _MOVE_VERBS + r"|(?:ahora|ya)\s+vivo\s+en|ahora\s+estoy\s+viviendo\s+en)\b|"
    # (?i:) scoped to the verb so the Capital lookahead stays case-sensitive; the stopword one is not (STT caps):
    r"\b(?i:ahora\s+estoy\s+en)\s+(?=[A-ZÁÉÍÓÚÑ])"
    r"(?!(?i:el|la|los|las|un|una|mi|tu|su|casa|clase|trabajo|coche|cama|medio)\b)")
# Prompt-INJECTION preamble: phrases that try to ANNUL the established context. A legitimate correction never
# uses them, so with one present an IDENTITY slot cannot be overwritten by the self-declared `change` signal.
_INJECTION_RE = re.compile(
    r"\b(?:ignora|olvida|haz\s+caso\s+omiso\s+de)\s+(?:todo\s+)?lo\s+anterior"
    r"|\bignore\s+(?:the\s+)?(?:all\s+)?(?:previous|above|prior|earlier)"
    r"|\bdisregard\s+(?:the\s+)?(?:previous|above|prior)"
    r"|\bforget\s+(?:everything|all|the)\s+(?:above|previous|prior)"
    r"|\b(?:nuevas\s+instrucciones|new\s+instructions)\b", re.I)


def _looks_like_injection(t: str) -> bool:
    return bool(_INJECTION_RE.search(t or ""))


# A turn that CHANGES an identity fact is a turn where the operator talks about HIMSELF. First-person markers in
# the languages this product speaks; deliberately NOT a full grammar — the point is a cheap anchor, not parsing.
#: ELIDED clitics live OUTSIDE the `\b…\b` below: in «m'acabo de traslladar» the apostrophe is the boundary.
#: A category of the Romance languages (ca/fr/it), pinned by `test_llm_change_signal_updates_state_and_supersedes`.
_SELF_REF_ELIDED_RE = re.compile(r"(?:^|[\s(¿¡\"'])[mjt]['’]", re.I)

_SELF_REF_RE = re.compile(
    r"\b(?:"
    r"yo|me|mi|mis|m[ií]o|m[ií]a|conmigo|vivo|estoy|soy|tengo|me\s+mud|me\s+llamo|me\s+he\s+mudado|"          # es
    r"jo|meu|meva|visc|s[oó]c|tinc|em\s+dic|em|acabo|"                                                           # ca
    r"i|i'm|im|my|mine|me|myself|i've|i\s+live|i\s+am|"                                                          # en
    r"je|mon|ma|mes|moi|"                                                                                         # fr
    r"io|mio|mia|abito|sono|"                                                                                     # it
    r"eu|meu|minha|moro|"                                                                                         # pt
    r"ich|mein|meine|wohne"                                                                                       # de
    r")\b", re.I)


def _talks_about_the_operator(t: str) -> bool:
    """Does this utterance predicate something of the OPERATOR, or does it merely NAME a value?

    The discriminator behind P0b's self-declared-`change` gate (2026-08-21): a spelled-out clarification of a place
    in an ERRAND («que se llama Calatayut, ciudad de Calatayut») moved `state.location`. An utterance that
    legitimately moves an identity ALWAYS speaks in the first person, in any language; a clarification does not.
    """
    t = t or ""
    return bool(_SELF_REF_RE.search(t) or _SELF_REF_ELIDED_RE.search(t))


_PROFILE_TREATMENT_RE = re.compile(
    r"\b(tut[eé]ame|tr[aá]tame\s+de\s+t[uú]|tr[aá]tame\s+de\s+usted|"
    r"s[eé]\s+(?:breve|conciso|directo)|h[aá]blame\s+en\s+(?:corto|breve)|"
    r"be\s+(?:brief|concise|direct)|call\s+me\s+by\s+my\s+first\s+name)\b",
    re.I,
)
_PROFILE_HW_RE = re.compile(
    r"(?:tengo|uso|trabajo\s+con|i\s+have|i\s+use)\s+un[a]?\s+"
    r"((?:macbook|imac|mac\s+mini|mac\s+pro|pc|port[aá]til|laptop|desktop|windows|linux|thinkpad|surface)"
    r"[\w\s\d\-]{0,40}?)(?=[.,;\n]|\s+y\s+|\s+and\s+|$)",
    re.I,
)
_PROFILE_CAR_RE = re.compile(
    r"(?:tengo|conduzco|mi\s+coche\s+es|i\s+drive|my\s+car\s+is)\s+(?:un[a]?\s+|a\s+|an\s+)?"
    r"((?:tesla|bmw|audi|mercedes|volkswagen|vw|seat|renault|peugeot|toyota|honda|ford|hyundai|kia|"
    r"volvo|mazda|nissan|citroen|fiat|opel|dacia|skoda|cupra)[\w\s\d\-]{0,40}?)(?=[.,;\n]|\s+y\s+|\s+and\s+|$)",
    re.I,
)

# The operator's CURRENT goal/project → STATE (his «stack»; asked for explicitly in V2-013).
_PROFILE_GOAL_RE = re.compile(
    r"(?:(?i:mi\s+objetivo(?:\s+actual)?\s+es|mi\s+meta\s+es|my\s+goal\s+is|my\s+objective\s+is))\s+"
    r"(.{3,90}?)(?=[.;\n]|$)",
)
_PROFILE_PROJECT_RE = re.compile(
    r"(?:(?i:mi\s+proyecto(?:\s+de\s+trabajo)?\s+es|estoy\s+trabajando\s+en|"
    r"my\s+project\s+is|i(?:'m|\s+am)\s+working\s+on))\s+"
    r"(.{3,90}?)(?=[.;\n]|$)",
)

# Durable wishes/preferences → `long`. A bare «quiero/necesito» counts only before an INFINITIVE or a noun phrase;
# with an object clitic in front («y LA quiero escuchar») it is a session action, not a preference.
_DESIRE_RE = re.compile(
    r"\b(me\s+gustar[íi]a|me\s+encantar[íi]a|prefiero|preferir[íi]a|mi\s+objetivo\s+es|planeo|"
    r"i(?:'d|\s+would)\s+like|i\s+prefer|my\s+goal\s+is|i\s+plan\s+to)\b"
    r"|(?<!la\s)(?<!lo\s)(?<!las\s)(?<!los\s)(?<!me\s)(?<!te\s)"
    r"\b(quiero|necesito|i\s+want\s+to|i\s+need\s+to)\s+"
    r"(?:\w+(?:ar|er|ir)(?:me|te|se|nos|lo|la|los|las)?\b|(?:una?s?|el|la|los|las)\b)",
    re.I,
)

# Ephemeral trivia (greetings, yes/no, short commands) → not stored. A turn made ONLY of fillers, however many,
# is a discard; the `+$` demands the WHOLE sentence be filler, so «bueno, me mudo a Madrid» still passes.
_TRIVIA_SKIP_RE = re.compile(
    r"^\s*(?:(?:aj[aá]|aj[aá]m|vale|s[íi]|no|ya|ya\s+est[aá]|claro|eso|exacto|correcto|entendido|"
    r"genial|perfecto|estupendo|guay|okey|oki|dale|listo|"
    # loose fillers of real speech (conversational noise)
    r"ah|eh|em|mmm+|hmm+|nada|bueno|venga|hombre|uf|vaya|anda|"
    r"hola|hey|qu[eé]\s+tal|buenas|adi[oó]s|gracias|de\s+nada|ok|okay|"
    r"hi|hello|bye|thanks|thank\s+you|yeah|yep|nope|nah|uh|um|mm+|ah\s+ok(?:ay)?)[\s,!¡¿?.…]*)+$",
    re.I,
)

# FORGET ON REQUEST (dim N): imperative AT THE START, excluding «no (te) olvides X» (a reminder). Captures the
# object to forget (LIKE over it): an assistant must be able to UNLEARN when asked.
_FORGET_RE = re.compile(
    # real speech's opening fillers, 0-3 before the verb
    r"^\s*(?:(?:oye|mira|pues|eh|bueno|vale|perdona|por\s+favor)[,\s]+){0,3}"
    # forget verb + optional enclitic («bórrame/bórralo/olvídame/bórramelo»)
    r"(?:olv[ií]da(?:te|me|lo|la)?|b[oó]rra(?:te|me|lo|la|melo|mela)?|elimina|descarta)\b"
    # a LOOSE «eso,»/«lo,» (no «de» after it): without it the pronoun dragged the next sentence into the object
    r"\s+(?:lo\s+de\s+|lo\s+del\s+|eso\s+de\s+|eso[,]?\s+|lo[,]?\s+|de\s+|del\s+|que\s+te\s+dije\s+de\s+|que\s+)?"
    # {1,80}: «olvida el 9» (a one-digit hour or amount) is a valid object
    r"(?:mi\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.{1,80}?)"
    # drops real speech's tails (the DECISION or its reason, the HARD forget's emphasis): their tokens would be
    # REQUIRED by forget()'s AND-match and the forget would match NOTHING (measured twice in 2026-07)
    r"(?:,?\s+(?:que\s+.*|porque\s+.*|ya\s+no\s+.*|al\s+final\b.*|mejor\s+(?:no|que\s+no)\b.*|"
    r"no\s+quiero\s+.*|nunca\s+m[aá]s.*|no\s+vuelvas?\s+a\s+.*))?[\s.,!¡¿?]*$",
    re.I,
)

# FORGET VERB AT THE END: «en realidad no me gusta el fútbol, OLVÍDALO» — the retraction first, the verb as a tag.
_FORGET_TRAILING_RE = re.compile(
    r"^\s*(?:(?:pues|vale|mira|oye|bueno|en\s+realidad)[,\s]+){0,2}"
    r"(.{1,100}?)"
    r",?\s+(?:olv[ií]da(?:te|me|lo|la)?|b[oó]rra(?:te|me|lo|la|melo|mela)?|elim[ií]na(?:lo|la)?|descarta(?:lo|la)?)"
    r"[\s.,!¡¿?]*$",
    re.I,
)

# NEGATED RESTATEMENT after a loose connector («olvida eso, NO TENGO ninguna alergia»): applied AFTER extracting
# `obj`, it trims a leading negation of possession, or its tokens would be REQUIRED by forget()'s AND-match.
_NEGATION_PREFIX_RE = re.compile(
    r"^no\s+(?:tengo|hay|tiene|soy|es|est[aá]|estoy|queda|había|hab[ií]a)\s+(?:ning[uú]n[oa]?\s+|nada\s+de\s+)?",
    re.I,
)

# HARD FORGET (privacy): delete for real, no trace — against the SOFT forget that hides and keeps history.
_FORGET_HARD_RE = re.compile(
    r"\b(del\s+todo|para\s+siempre|permanentemente|definitivamente|por\s+completo|sin\s+dejar\s+(?:ni\s+)?rastro|"
    r"que\s+no\s+quede\s+(?:ni\s+)?rastro)\b", re.I)

# UNFORGET (dim N): the counterpart of _FORGET_RE — he retracts a forget. Imperative at the start + object.
_UNFORGET_RE = re.compile(
    r"^\s*(?:(?:oye|mira|pues|eh|bueno|vale|perdona|espera|no|por\s+favor)[,\s]+){0,3}"
    r"(?:recup[eé]ra(?:me|te)?|restaura|vuelve\s+a\s+(?:acordarte|recordar)|acu[eé]rdate\s+otra\s+vez)\b"
    r"\s+(?:lo\s+de\s+|lo\s+del\s+|eso\s+de\s+|de\s+|del\s+|que\s+te\s+dije\s+de\s+)?"
    r"(?:mi\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.{2,80}?)"
    r"[\s.,!¡¿?]*$",
    re.I,
)

# Write-side ABSTENTION (dim E): only UNAMBIGUOUS requests to the assistant (a city's weather, a recommendation);
# a question that carries a fact («¿sabes que me mudé a Madrid?») does not match.
_ASSISTANT_QUERY_RE = re.compile(
    r"¿?\s*(?:oye\s+)?(?:zaelar[,\s]+)?"
    r"(?:qu[eé]\s+tiempo\s+(?:va\s+a\s+hacer|har[aá]|hace)\b|"
    r"(?:qu[eé]\s+)?me\s+recomiendas\b|puedes\s+recomendarme\b|qu[eé]\s+me\s+aconsejas\b)",
    re.I,
)

# Explicit CORRECTION (dim M): «no es X sino Y» — the WRONG value (before «sino», a digit allowed) is forgotten
# and the turn goes on to store the new one.
_CORRECTION_RE = re.compile(
    r"\bno\s+[^.,;]*?\b([\wÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ'’\-]{2,})\s+sino\b", re.I)
# «ya no trabajo en Telefónica, ahora en Amazon» → forget the negated PROPER name. No re.I: `[A-Z]` stays upper.
_CORRECTION_YANO_RE = re.compile(
    r"[Yy]a\s+[Nn]o\s+[^.,;]*?\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’\-]{2,})")

# «salgo a las 17, NO a las 18» — the right value first, the wrong one after «, no», with no «sino».
_CORRECTION_TRAILING_NO_RE = re.compile(
    # {1,40}: a LOOSE digit («...son 2, no 3») is a valid value
    r",\s*no\s+(?:a\s+las\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.{1,40}?)[\s.,!¡¿?]*$", re.I)

# ROUTINES / HABITS (dim O) are always memorable: a strong RECURRENCE mark keeps them even if the LLM drops them.
_ROUTINE_RE = re.compile(
    r"\b(cada\s+(?:d[ií]a|noche|ma[ñn]ana|tarde|semana|mes|finde|lunes|martes|mi[eé]rcoles|jueves|viernes|"
    r"s[aá]bado|domingo)|todos\s+los\b|todas\s+las\b|suelo\b|solemos\b|acostumbro|siempre\s+que|"
    # USUAL PLACE of an object («las llaves las guardo siempre en…»): «¿dónde dejé las llaves?» needs it
    r"(?:dejo|guardo|pongo|meto|dejamos|guardamos)\s+siempre|siempre\s+(?:lo|la|los|las)\s+(?:dejo|guardo|pongo|meto)|"
    r"antes\s+de\s+(?:dormir|acostarme)|al\s+levantarme|every\s+(?:day|night|morning|week|monday))\b",
    re.I,
)

# OBSERVACIONES / AUTOCONOCIMIENTO (dim I) → un patrón personal que el operador nota de SÍ MISMO ("he notado que
# rindo por las mañanas", "cuando ceno tarde duermo mal") es memorable: un asistente lo usa para aconsejar. El LLM
# heart a veces lo descarta por "charla". Backstop DETERMINISTA (como rutinas): marca explícita de observación.
_OBSERVATION_RE = re.compile(
    r"\b(he\s+notado|me\s+he\s+dado\s+cuenta|he\s+observado|me\s+he\s+fijado|he\s+visto|me\s+he\s+percatado)"
    r"\s+(?:de\s+)?que\b", re.I)

# REVERSIÓN / CESE (dim M) → "ya no bebo café", "ya no trabajo allí", "ya no me gusta X": un CAMBIO DE ESTADO
# memorable (dejó un hábito/gusto/situación). El LLM a veces lo descarta por "charla" y `_CORRECTION_YANO_RE` solo
# olvida el valor viejo si es NOMBRE PROPIO (mayúscula) → una reversión de objeto común-minúscula se PERDÍA. Backstop
# determinista: guarda el nuevo estado ("ya no…") para que el cerebro sepa que eso YA NO aplica.
_REVERSAL_RE = re.compile(r"\bya\s+no\s+\S+\s+\S+", re.I)

# EVENTOS DE SALUD / VIDA SERIOS (dim C · salud) → un humano JAMÁS olvida una operación, un diagnóstico o una
# enfermedad seria, propios o de un allegado cercano. El LLM heart a veces los DESCARTA por "pasado" o "charla"
# ("hace tres años me operaron del corazón" → descartado). Backstop DETERMINISTA como el de compromisos: marca
# médica inequívoca → se guarda a LARGO aunque el LLM lo tire. CONSERVADOR (verbos/sustantivos médicos claros; no
# un simple "me duele la cabeza").
_HEALTH_RE = re.compile(
    r"\b(me\s+operaron|me\s+oper[eé]|nos\s+operaron|me\s+intervin|oper[aá]ci[oó]n(?:es)?\b|cirug[ií]a|"
    r"diagn[oó]stic|me\s+diagnosticaron|infarto|ictus|trombo|c[aá]ncer|tumor|trasplante|quimio|radioterapia|"
    r"hospitaliz|me\s+ingresaron|ingres[eé]\s+en\s+el\s+hospital|enfermedad\s+(?:grave|seria|cr[oó]nica)|"
    r"fisioterap[a-z]*|al\s+fisio\b|rehabilitaci[oó]n|lesi[oó]n|problema\s+de\s+espalda|"
    r"soy\s+(?:diab[eé]tic[oa]s?|cel[ií]ac[oa]s?|hipertens[oa]s?|asm[aá]tic[oa]s?)|padezco|sufro\s+de|"
    r"tengo\s+(?:diabetes|c[aá]ncer))\b",
    re.I,
)

# PERFIL DURABLE BIOGRÁFICO → un humano NO olvida su PRIMER perro, su coche ANTERIOR, su EX pareja. El LLM heart,
# con mucho contexto acumulado, a veces los descarta por "charla". Backstop DETERMINISTA: "mi PRIMER/ANTERIOR/
# ANTIGUO/EX <algo>" → LARGO. OJO: NO incluye "FAVORITO/PREFERIDO" — esas son PREFERENCIAS que el CORAZÓN gestiona
# por SLOT (supersede/dedup); forzarlas aquí duplicaría (rompía los tests de dedup de 'color/plato favorito').
_PROFILE_DURABLE_RE = re.compile(
    r"\bmi\s+(?:primer[ao]?|anterior|antigu[oa]|ex)\s+\w+|\bmi\s+\w+\s+(?:anterior|antigu[oa])\b", re.I)

# MENSAJE ENTRANTE / info RELATADA de un tercero → durable (backstop V2-050, hermano de _COMMITMENT_RE): "me
# escribió/me dijo/me mandó/me contó/me llamó X: <contenido>". El CORAZÓN LLM a veces ALUCINA un placeholder de
# fewshot ("X me pidió Y para el día Z") en vez del contenido → el dato ('viernes'…) se pierde (bot v1 #24/#29). Es
# un safety-net de PRESERVACIÓN del texto crudo, NO routing. NARROW: exige "me <verbo-de-comunicación>" (un tercero
# me comunicó algo), y se cae si es una NEGACIÓN vacía ("no me dijo nada"). _COMMITMENT_RE ya cubre "me pidió/encargó".
_INCOMING_MSG_RE = re.compile(
    # OJO: 'llamó' con acento (3ª persona, «me llamó Carlos») — NUNCA 'llamo' sin acento («me llamo Ramón» = IDENTIDAD).
    r"\bme\s+(?:escrib\w*|ha\s+escrito|dij\w*|ha\s+dicho|mand\w*|ha\s+mandado|cont[oó]|ha\s+contado|"
    r"coment\w*|ha\s+comentado|llam[óò]|llamaron|ha\s+llamado|avis[oó]|ha\s+avisado)\b", re.I)
_EMPTY_MSG_RE = re.compile(r"\bno\s+me\s+\w+\s+(?:nada|na)\b", re.I)

# Compromisos / peticiones / citas dirigidos al operador → NUNCA se olvidan aunque el LLM los descarte por error
# (backstop DETERMINISTA, V2-013). Un humano recuerda que su jefa le pidió un informe para el miércoles. Distinto
# de un hecho pasado trivial ("la reunión terminó a las cinco"): aquí exigimos verbo de PETICIÓN/COMPROMISO o cita.
_COMMITMENT_RE = re.compile(
    r"\b(me\s+(?:ha\s+)?pidi[oó]|me\s+pidieron|me\s+(?:ha[n]?\s+)?encarg|me\s+(?:ha\s+)?ped[ií]|"
    r"tengo\s+que|tengo\s+cita|tengo\s+reuni[oó]n|qued[eé]\s+con|recu[eé]rdame|no\s+(?:te\s+)?olvid|"
    r"hay\s+que\s+entregar|entregar\s+.*\bpara\b|para\s+el\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|"
    r"s[aá]bado|domingo)|ask(?:ed)?\s+me\s+to|remind\s+me|i\s+have\s+to|due\s+(?:on|by)|"
    # A TASK he GIVES the assistant («búscame vuelos», «resérvame mesa»): an assistant must remember what it was
    # asked («¿qué te pedí?») without the LLM. Canvas commands are filtered by _COMMAND_RE before this.
    r"b[uú]sca(?:me)?|encu[eé]ntra(?:me)?|escr[ií]be(?:me)?|red[aá]cta(?:me)?|prep[aá]ra(?:me)?|"
    r"reserv[aá](?:me)?|ap[uú]nta(?:me)?|organ[ií]za(?:me)?|planif[ií]ca(?:me)?|c[oó]mpra(?:me)?|"
    r"cons[ií]gue(?:me)?|res[uú]me(?:me)?|m[aá]nda(?:me)?|a[ñn][aá]de(?:me)?|"
    r"quiero\s+que\s+(?:me\s+)?(?:busques|encuentres|escribas|prepares|reserves|mires|resumas|compres|organices)|"
    r"puedes\s+(?:buscar|escribir|preparar|reservar|mirar|resumir|encontrar|comprar|organizar)|"
    r"ask(?:ed)?\s+me\s+to|book\s+me|find\s+me|write\s+me|remind\s+me\s+to)\b",
    re.I,
)

# Comandos al asistente (no van al store: los ejecuta el FlashBrain). OJO: NO incluir "para" — es una preposición
# comunísima ("un regalo para mi madre", "el informe para el miércoles") y confundía frases memorables con el
# comando de parada "para". Las órdenes de parada (para/silencio/basta/stop) las gobierna `voice/attention.py`
# (hard_interrupt), no la memoria. Aquí solo dejamos verbos de comando de canvas inequívocos.
_COMMAND_RE = re.compile(
    r"\b(cierra|abre|muestra|esc[oó]ndete|oculta|"
    # media/playback (2026-07-19 H2: «pon música» became a durable FACT). \b after «pon» never matches «pongas»;
    # «sube/baja» only with volume/brightness («la gasolina sube» is a memorable fact).
    r"pon(?:me)?|reproduce|reprod[uú]ce(?:me)?|pausa|reanuda|apaga|enciende|silencia|"
    r"(?:sube|baja)\s+(?:el\s+|la\s+)?(?:volumen|brillo|m[uú]sica)|"
    r"close|open|show|hide|mute|play|pause)\b",
    re.I,
)

