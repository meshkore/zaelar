"""The language-mark bank: every deterministic es/en(+ca/fr/it/pt/de) pattern the write path reads.

Split out of the old monolithic memory_agent.py (architecture audit 2026-08-23) VERBATIM — this file is DATA
expressed as regexes, and its known failure class is MUTE: an enumeration of first-person marks that misses a
language does not over-write, it silently fails to learn (see `_report_self_declared_change_ignored`). Growing
a language means growing patterns here, nowhere else.
"""
from __future__ import annotations

import re


# ── Heurística de clasificación (es/en) ─────────────────────────────────────────────────────────────────────
# Datos de PERFIL del operador → tabla `state`. Los TRIGGERS son case-insensitive vía `(?i:...)`, pero los
# grupos de captura siguen la case del texto (evita el bug clásico: con `re.I` global, `[A-Z]` también matchea
# minúsculas y "soy feliz" acabaría en `operator_name`). Se descartan triggers demasiado ambiguos ("soy",
# "estoy en", "I'm") — devolverían perfiles-basura. Corte en " y "/" and " para no engullir la frase siguiente.
_PROFILE_NAME_RE = re.compile(
    r"(?:(?i:me\s+llamo|mi\s+nombre\s+es|my\s+name\s+is))\s+"
    r"([A-ZÁÉÍÓÚÑa-záéíóúñ][\wÁÉÍÓÚÑáéíóúñ'’\-]{1,30}(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ][\wÁÉÍÓÚÑáéíóúñ'’\-]{1,30}){0,2})",
)
# MUDANZA (V2-038 #2, ampliada en el retest 2026-07-14): las variantes REALES del habla — "me he mudado a",
# "me acabo de mudar a", "acabo de mudarme a", "me mudé a", "me he trasladado a", "nos trasladamos a",
# "me estoy mudando a", "I (just) moved to"… El fraseo que faltara dejaba la ciudad VIEJA en el state (el gate
# anti-garble mandaba el cambio legítimo a cuarentena) y el tiempo respondía con ella.
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
    # "ahora estoy en X" SOLO con ciudad Capitalizada y NO artículo/lugar común (si no, "ahora estoy en el
    # trabajo/casa" — o su versión EN MAYÚSCULAS del STT — pisaría location).
    r"|(?i:ahora\s+estoy\s+en)(?=\s+[A-ZÁÉÍÓÚÑ])(?!\s+(?i:el|la|los|las|un|una|mi|tu|su|casa|clase|trabajo|"
    r"coche|cama|medio)\b))\s+"
    r"([A-ZÁÉÍÓÚÑa-záéíóúñ][\w\sÁÉÍÓÚÑáéíóúñ'’\-]{1,40}?)(?=[.,;\n]|\s+y\s+|\s+and\s+|$)",
)
# La MISMA mudanza, como señal de "corrección" (V2-033 P0b): una declaración explícita de cambio de vida NO es un
# garble del STT → debe poder SOBRESCRIBIR la identidad establecida (location), no ir a cuarentena. El slot
# operator.location hace el supersede exacto de la píldora vieja ("el más reciente MANDA"). "ahora vivo en" /
# "ya vivo en" también son cambio declarado (el "vivo en" a secas de un perfil vacío no necesita la señal).
_RELOCATION_RE = re.compile(
    r"\b(?i:" + _MOVE_VERBS + r"|(?:ahora|ya)\s+vivo\s+en|ahora\s+estoy\s+viviendo\s+en)\b|"
    # "ahora estoy en X" SOLO con Capital y NO artículo/lugar común (la (?i:) va scopeada al verbo para que el
    # lookahead de Capital sea sensible; el de stopwords vuelve a ser insensible por el all-caps del STT):
    r"\b(?i:ahora\s+estoy\s+en)\s+(?=[A-ZÁÉÍÓÚÑ])"
    r"(?!(?i:el|la|los|las|un|una|mi|tu|su|casa|clase|trabajo|coche|cama|medio)\b)")
# Preámbulo de INYECCIÓN de prompt (2ª auditoría 2026-07-14, hallazgo del corpus v2 con 7b): frases que intentan
# ANULAR el contexto/identidad establecidos. Una corrección o mudanza LEGÍTIMA nunca las usa → sirven para que un
# slot de IDENTIDAD no pueda sobrescribirse por la señal `change` que el modelo capaz fabrica al obedecer la
# inyección. es/en (los dos idiomas objetivo del sistema).
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
#: Los clíticos ELIDIDOS van FUERA del `\b…\b` de abajo: en «m'acabo de traslladar» el apóstrofo ya es la
#: frontera, y un `\b` delante de `m'` no casa. Es una CATEGORÍA de las lenguas románicas (ca/fr/it), no un caso
#: suelto — lo descubrió `test_llm_change_signal_updates_state_and_supersedes`, que es justo el contrato
#: multilingüe que este arreglo no puede romper.
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

    The discriminator behind P0b's self-declared-`change` gate (2026-08-21). Measured on the operator's own
    machine: Deepgram mangled «Calatayud» into `cal a` / `Kalatayut` / `valch`, zaelar kept asking, and the
    operator clarified — «que se llama Calatayut,, ciudad de Calatayut». The distiller read that fragment of an
    ERRAND about routes as a fact about where he lives, self-declared `change=update`, and that self-declaration
    alone switched OFF the guard whose own docstring names «típico garble del STT». `state.location` went from
    Soria to Calatayud and stayed there.

    The utterance that legitimately moves an identity ALWAYS speaks in the first person — «me he mudado a X»,
    «ara visc a Girona», «I live in X» — while a clarification of a third-party entity does not. That is the
    difference the deterministic detectors were missing, and it holds across languages, which the Spanish-only
    `_RELOCATION_RE` does not.
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

# Objetivo/proyecto ACTUAL del operador → ESTADO (la "pila": qué persigue/en qué anda ahora). Lo pidió el
# operador explícitamente (V2-013): el nombre, el objetivo y el proyecto de trabajo son de lo más importante.
_PROFILE_GOAL_RE = re.compile(
    r"(?:(?i:mi\s+objetivo(?:\s+actual)?\s+es|mi\s+meta\s+es|my\s+goal\s+is|my\s+objective\s+is))\s+"
    r"(.{3,90}?)(?=[.;\n]|$)",
)
_PROFILE_PROJECT_RE = re.compile(
    r"(?:(?i:mi\s+proyecto(?:\s+de\s+trabajo)?\s+es|estoy\s+trabajando\s+en|"
    r"my\s+project\s+is|i(?:'m|\s+am)\s+working\s+on))\s+"
    r"(.{3,90}?)(?=[.;\n]|$)",
)

# Deseos/preferencias durables → `long` (no pinned; puede evolucionar). Auditoría 2026-07-19 (H3) + refinado
# 2026-07-20: el "quiero" con CLÍTICO de objeto delante ("y LA quiero escuchar, no se oyen") es acción de sesión,
# no preferencia — quedaba como pref de LARGO plazo. El quiero/necesito pelado cuenta solo seguido de INFINITIVO
# ("quiero comprarme una moto", "quiero aprender japonés") o de sintagma nominal ("necesito unas vacaciones");
# los verbos inequívocamente durables (prefiero/me gustaría/mi objetivo es/planeo) siguen bastando solos.
_DESIRE_RE = re.compile(
    r"\b(me\s+gustar[íi]a|me\s+encantar[íi]a|prefiero|preferir[íi]a|mi\s+objetivo\s+es|planeo|"
    r"i(?:'d|\s+would)\s+like|i\s+prefer|my\s+goal\s+is|i\s+plan\s+to)\b"
    r"|(?<!la\s)(?<!lo\s)(?<!las\s)(?<!los\s)(?<!me\s)(?<!te\s)"
    r"\b(quiero|necesito|i\s+want\s+to|i\s+need\s+to)\s+"
    r"(?:\w+(?:ar|er|ir)(?:me|te|se|nos|lo|la|los|las)?\b|(?:una?s?|el|la|los|las)\b)",
    re.I,
)

# Trivia efímera (saludos, sí/no, comandos cortos) → no guardar. Anti-ruido.
# Un turno hecho SOLO de interjecciones/asentimientos (aunque sean varios, repetidos o separados por comas:
# "ajá, vale vale", "sí sí claro") = relleno conversacional → DESCARTE. El `+$` exige que TODA la frase sea
# relleno, así "bueno, me mudo a Madrid" NO cae (tiene contenido). Antes solo casaba UNA interjección → "Ajá,
# vale vale" se colaba al LLM y este lo guardaba por error.
_TRIVIA_SKIP_RE = re.compile(
    r"^\s*(?:(?:aj[aá]|aj[aá]m|vale|s[íi]|no|ya|ya\s+est[aá]|claro|eso|exacto|correcto|entendido|"
    r"genial|perfecto|estupendo|guay|okey|oki|dale|listo|"
    # muletillas/asentimientos sueltos del habla real (ruido conversacional): ah/eh/em/mmm/hmm/bueno/venga/…
    r"ah|eh|em|mmm+|hmm+|nada|bueno|venga|hombre|uf|vaya|anda|"
    r"hola|hey|qu[eé]\s+tal|buenas|adi[oó]s|gracias|de\s+nada|ok|okay|"
    r"hi|hello|bye|thanks|thank\s+you|yeah|yep|nope|nah|uh|um|mm+|ah\s+ok(?:ay)?)[\s,!¡¿?.…]*)+$",
    re.I,
)

# OLVIDO A PETICIÓN (dim N): "olvida lo del regalo", "bórrate mi contraseña vieja". Imperativo AL INICIO (evita
# falsos positivos a mitad de frase) y EXCLUYE "no (te) olvides X" — que es un RECORDATORIO, no un olvido. Captura
# el objeto a olvidar (LIKE sobre él). Necesidad humana: un asistente debe poder DESAPRENDER cuando se lo piden.
_FORGET_RE = re.compile(
    # muletillas de arranque del habla real (oye/mira/pues/eh/bueno/vale/perdona/por favor), 0-3 antes del verbo
    r"^\s*(?:(?:oye|mira|pues|eh|bueno|vale|perdona|por\s+favor)[,\s]+){0,3}"
    # verbo de olvido + enclítico opcional ("bórrame/bórralo/olvídame/bórramelo" — habla natural, muy común)
    r"(?:olv[ií]da(?:te|me|lo|la)?|b[oó]rra(?:te|me|lo|la|melo|mela)?|elimina|descarta)\b"
    # "eso,?\s+"/"lo,?\s+" SUELTO (sin "de" detrás) — maratón 2026-07-22: "olvida ESO, no tengo ninguna alergia"
    # es tan habitual como "olvida ESO DE la alergia"; sin este conector el pronombre entraba como parte del
    # objeto y arrastraba toda la frase siguiente.
    r"\s+(?:lo\s+de\s+|lo\s+del\s+|eso\s+de\s+|eso[,]?\s+|lo[,]?\s+|de\s+|del\s+|que\s+te\s+dije\s+de\s+|que\s+)?"
    # {1,80} no {2,80}: "olvida el 9" (una hora/cantidad de un solo dígito) es un objeto válido y corto.
    r"(?:mi\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.{1,80}?)"
    # descarta coletillas del habla real ("... que era sorpresa", "... porque ya no vale", "... ya no hace falta",
    # "... al final no [me apunto]", "... mejor no") — la DECISIÓN/justificación NO es parte del objeto a olvidar;
    # si se colara, sus tokens ("final"…) entrarían como EXIGIDOS por el AND-match del writer (memory.forget) y el
    # olvido no casaría NADA (bot v2 #65, 2026-07-17: "olvida lo de las clases de cerámica de los jueves, al final
    # no" → obj arrastraba "final" → 0 recuerdos invalidados).
    # Maratón de testing 2026-07-22: MISMO fallo con la coletilla del OLVIDO DURO en sí ("...para siempre, no
    # quiero que lo sepas nunca más") — "no quiero (que)…"/"nunca más"/"no vuelvas a…" no estaban en la lista,
    # así que el objeto arrastraba toda la frase de énfasis y el forget() real no encontraba nada que invalidar
    # (el FlashBrain decía "vale, lo olvido" de todos modos — acuse sin acción, mismo patrón que otros bugs
    # de esta maratón). El olvido DURO es precisamente el caso que MÁS necesita casar de verdad.
    r"(?:,?\s+(?:que\s+.*|porque\s+.*|ya\s+no\s+.*|al\s+final\b.*|mejor\s+(?:no|que\s+no)\b.*|"
    r"no\s+quiero\s+.*|nunca\s+m[aá]s.*|no\s+vuelvas?\s+a\s+.*))?[\s.,!¡¿?]*$",
    re.I,
)

# VERBO DE OLVIDO AL FINAL (maratón 2026-07-22): "en realidad no me gusta el fútbol, OLVÍDALO" — orden de
# palabras completamente distinto a `_FORGET_RE` (que exige el verbo AL PRINCIPIO): aquí la persona primero dice
# la retractación y remata con el verbo como coletilla. Sin este patrón el turno entero pasaba de largo (0 match)
# y el FlashBrain decía "vale, sin problema" sin ejecutar NINGÚN olvido real — la orden se perdía por completo.
_FORGET_TRAILING_RE = re.compile(
    r"^\s*(?:(?:pues|vale|mira|oye|bueno|en\s+realidad)[,\s]+){0,2}"
    r"(.{1,100}?)"
    r",?\s+(?:olv[ií]da(?:te|me|lo|la)?|b[oó]rra(?:te|me|lo|la|melo|mela)?|elim[ií]na(?:lo|la)?|descarta(?:lo|la)?)"
    r"[\s.,!¡¿?]*$",
    re.I,
)

# RESTATEMENT NEGADO tras un conector suelto (maratón 2026-07-22): "olvida eso, NO TENGO ninguna alergia" — el
# operador no dice el nombre del dato, RENIEGA de él con una frase completa. Sin esto el objeto extraído arrastra
# "no tengo ninguna" como tokens EXIGIDOS por el AND-match de memory.forget(), que nunca aparecen en el texto
# canónico guardado ("La alergia del operador es a los frutos secos.") → 0 recuerdos invalidados. Se aplica DESPUÉS
# de extraer `obj`: si empieza por una negación de posesión/estado, se recorta a lo que queda (el núcleo real).
_NEGATION_PREFIX_RE = re.compile(
    r"^no\s+(?:tengo|hay|tiene|soy|es|est[aá]|estoy|queda|había|hab[ií]a)\s+(?:ning[uú]n[oa]?\s+|nada\s+de\s+)?",
    re.I,
)

# OLVIDO DURO (dim N/privacidad): el operador quiere BORRAR de verdad, sin dejar rastro ("bórralo del todo", "para
# siempre", "sin dejar rastro"). Distingue el olvido SOFT (oculta, recuperable, conserva histórico) del HARD
# (elimina; derecho al olvido para datos sensibles: una contraseña vieja, un dato médico que no quiere guardado).
_FORGET_HARD_RE = re.compile(
    r"\b(del\s+todo|para\s+siempre|permanentemente|definitivamente|por\s+completo|sin\s+dejar\s+(?:ni\s+)?rastro|"
    r"que\s+no\s+quede\s+(?:ni\s+)?rastro)\b", re.I)

# DES-OLVIDO / RECUPERAR (dim N): "recupera lo del regalo", "vuelve a acordarte de X", "acuérdate otra vez de X".
# Contraparte de _FORGET_RE: el operador se retracta de un olvido. Imperativo al inicio + captura el objeto.
_UNFORGET_RE = re.compile(
    r"^\s*(?:(?:oye|mira|pues|eh|bueno|vale|perdona|espera|no|por\s+favor)[,\s]+){0,3}"
    r"(?:recup[eé]ra(?:me|te)?|restaura|vuelve\s+a\s+(?:acordarte|recordar)|acu[eé]rdate\s+otra\s+vez)\b"
    r"\s+(?:lo\s+de\s+|lo\s+del\s+|eso\s+de\s+|de\s+|del\s+|que\s+te\s+dije\s+de\s+)?"
    r"(?:mi\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.{2,80}?)"
    r"[\s.,!¡¿?]*$",
    re.I,
)

# ABSTENCIÓN write-side (dim E): PREGUNTAS que el operador le hace a zaelar y que NO son hechos suyos → descartar.
# CONSERVADOR: solo patrones INEQUÍVOCOS de petición al asistente (el tiempo de una ciudad, una recomendación); NO
# toca preguntas que traen un dato ("¿sabes que me mudé a Madrid?") porque esas no casan estos patrones concretos.
_ASSISTANT_QUERY_RE = re.compile(
    r"¿?\s*(?:oye\s+)?(?:zaelar[,\s]+)?"
    r"(?:qu[eé]\s+tiempo\s+(?:va\s+a\s+hacer|har[aá]|hace)\b|"
    r"(?:qu[eé]\s+)?me\s+recomiendas\b|puedes\s+recomendarme\b|qu[eé]\s+me\s+aconsejas\b)",
    re.I,
)

# CORRECCIÓN explícita (dim M): "no se llama Toby SINO Nala", "no es X sino Y", "no quiero café sino té". Un humano
# corrige y DESAPRENDE el dato viejo. Captura el valor ERRÓNEO (la palabra antes de "sino") → se olvida (forget),
# y el turno sigue su curso normal para GUARDAR el valor nuevo. Conservador: solo el patrón "... X sino Y".
# El valor erróneo puede empezar por DÍGITO (un PIN, un código, un número): "no es 4471 sino 8890" → captura 4471.
_CORRECTION_RE = re.compile(
    r"\bno\s+[^.,;]*?\b([\wÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ'’\-]{2,})\s+sino\b", re.I)
# "ya no trabajo en Telefónica, ahora en Amazon" → olvida el nombre PROPIO negado (Telefónica). Sin re.I para que
# `[A-Z]` sea de verdad mayúscula (nombre propio) y no engulla verbos en minúscula.
_CORRECTION_YANO_RE = re.compile(
    r"[Yy]a\s+[Nn]o\s+[^.,;]*?\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’\-]{2,})")

# Maratón de testing 2026-07-22: "salgo a las 17, NO a las 18" — el valor CORRECTO va primero y el ERRÓNEO
# detrás de una coma + "no", sin la palabra "sino" (que exige `_CORRECTION_RE`). Es tan común en el habla como
# el patrón con "sino" y sin esto el valor viejo (18) sobrevivía intacto tras una corrección hablada y confirmada
# — el mismo patrón de fondo (regex demasiado estrecha) que los otros bugs de olvido de esta sesión.
_CORRECTION_TRAILING_NO_RE = re.compile(
    # {1,40} no {2,40}: un dígito SUELTO ("...son 2, no 3") es un valor válido y corto — el mínimo de 2
    # lo dejaba fuera de la captura (bug real 2026-07-22, encontrado tras el fix de longitud en forget()).
    r",\s*no\s+(?:a\s+las\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.{1,40}?)[\s.,!¡¿?]*$", re.I)

# RUTINAS / HÁBITOS recurrentes (dim O) → memorables SIEMPRE (definen la vida de la persona). El LLM heart a veces
# descarta un hábito por "trivial" ("cada noche leo un rato"); un humano SÍ recuerda las costumbres de otro. Backstop
# determinista, como el de compromisos: si hay marca fuerte de RECURRENCIA, se guarda aunque el LLM lo tire.
_ROUTINE_RE = re.compile(
    r"\b(cada\s+(?:d[ií]a|noche|ma[ñn]ana|tarde|semana|mes|finde|lunes|martes|mi[eé]rcoles|jueves|viernes|"
    r"s[aá]bado|domingo)|todos\s+los\b|todas\s+las\b|suelo\b|solemos\b|acostumbro|siempre\s+que|"
    # UBICACIÓN HABITUAL de un objeto ("el mando lo dejo SIEMPRE en la guantera", "las llaves las guardo siempre
    # en…"): dónde se guarda algo es memoria útil ("¿dónde dejé las llaves?"). Verbo de guardar + "siempre".
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
    # TAREA que el operador ENCARGA al asistente (personal-agent): "búscame vuelos", "escríbeme un libro",
    # "prepárame un widget", "resérvame mesa", "apúntame en la agenda"… Un asistente DEBE recordar lo que le
    # mandan hacer (para "¿qué te pedí?") — NO depende del LLM heart. OJO: los comandos triviales de canvas
    # (abre/muestra/cierra) los filtra _COMMAND_RE ANTES y no llegan aquí. Verbo+dativo -me o "puedes/quiero que".
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
    # media/reproducción (auditoría 2026-07-19 H2: "pon música"/"apaga el video" acababan como HECHOS durables por
    # el fail-open). \b tras "pon" NO casa "pongas" (lección del widget-fallback espurio). "sube/baja" SOLO con
    # volumen/brillo — a secas aparecen en hechos memorables ("la gasolina sube").
    r"pon(?:me)?|reproduce|reprod[uú]ce(?:me)?|pausa|reanuda|apaga|enciende|silencia|"
    r"(?:sube|baja)\s+(?:el\s+|la\s+)?(?:volumen|brillo|m[uú]sica)|"
    r"close|open|show|hide|mute|play|pause)\b",
    re.I,
)

