"""What a provider's failure IS: exhausted until a reset, a context overflow, a broken request, a tool limit.
Part of nucleo.workers.providers; every package name is read through _p, so a patch of providers.<name> reaches it."""
from __future__ import annotations

import re

from nucleo.workers import providers as _p


# ── detección de agotamiento y relevo ─────────────────────────────────────────────────────────────────────
# El proveedor ANUNCIA cuándo vuelve, y lo dice de tres formas distintas. Solo se leía la primera:
#   · fecha            «will reset at 2026-08-30»          → límite semanal/mensual
#   · fecha + hora     «reset at 2026-08-12 23:15:37»
#   · SOLO la hora     «Usage limit reached for 5 hour … reset at 23:15:37»  → límite de VENTANA, del mismo día
# Leer solo la fecha convertía el tercer caso en «medianoche pasada» → epoch en el pasado → caía al suelo de media
# hora, y a partir de ahí cada worker volvía a elegir ese proveedor y a comerse un 429. Con el reset a las 23:15,
# eso son SIETE HORAS de reintentos quemados de uno en uno (hallazgo de un e2e real, 2026-08-10).
# V2-309 — la hora viene como el proveedor quiera escribirla, y `6:10am` (un dígito + sufijo) no casaba: el
# cooldown caía al suelo por defecto (30 min) en vez de a las 6:10, así que a los 30 minutos otro worker iba
# a morir contra el mismo límite. Se acepta 1-2 dígitos y el am/pm opcional, que es como lo escribe el CLI.
_RESET_RE = re.compile(
    r"reset(?:s|ting)?(?:\s+(?:at|on|in))?\s*[:\s]\s*"
    r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?)", re.I)


_ZAI_CODE_RE = re.compile(r"\[1[23]\d\d\]")


# Un límite de VENTANA (5 h, diario) no es un rate-limit pasajero: no se arregla reintentando en dos segundos, se
# arregla esperando a la hora que el propio proveedor dice. Tratarlo como `rate` era no ponerle cooldown NI relevar.
# V2-309 — «session limit» es la MISMA clase y no casaba con ninguna: medido el 2026-08-25 04:36, el worker
# murió al instante con «You've hit your session limit · resets 6:10am (Europe/Madrid)», `classify_failure`
# devolvió "" (no es fallo de proveedor) → sin cooldown y sin relevo, así que CADA worker nuevo iba al mismo
# escalón muerto y moría igual. Es literalmente lo que este patrón existe para cerrar, con otra redacción del
# proveedor. Y el «resets 6:10am» es su hora: se respeta como en cualquier ventana.
_WINDOW_RE = re.compile(
    r"usage limit reached|limit reached for\s+\d+\s*(?:hour|hr|minute|min|day)|"
    r"(?:hit|reached|exceeded)\s+(?:your|the)\s+session limit|session limit\b[^.]{0,40}\breset|"
    r"limit will reset|quota (?:will )?reset", re.I)


# Señales de CUOTA/PLAN agotado, más específicas que el `credit` genérico de `llm_health` (que también pilla un
# rate-limit pasajero). Aquí importa distinguir «espera 20s» de «hasta el jueves».
_EXHAUSTED_RE = re.compile(
    r"limit exhausted|quota exceeded|insufficient (?:balance|credit|quota)|out of credit|"
    r"monthly limit|weekly limit|plan limit|saldo insuficiente", re.I)


# ── A BLOWN CONTEXT IS NOT A SICK PROVIDER (incident 2026-08-18) ─────────────────────────────────────────────
# The worker of session `08f54c0c` died with "API Error: The model has reached its context window limit." and that
# text was handed to the operator as if it were their report. `classify_failure` did not recognize it (returned
# ""), so there was no relay and no alert: the very hole closed for quota on 2026-08-10, still open for this.
#
# This gets its OWN family rather than living inside `classify_failure`, for a substantive reason: a blown context
# is not an unhealthy provider. Folding it into `exhausted` would put a perfectly working tier on cooldown and
# migrate the fault to the next one — which would blow up identically, because the cause is the SIZE of the
# context, not who serves it. The correct answer is COMPACT AND CONTINUE (`session._context_handoff`), not relay.
#
# Two ways of saying the same thing, and both must be caught: the CLI's SYNTHETIC message talks about a "context
# window", but the real `apiError` in the incident was `max_output_tokens` — the provider rejects the call once the
# accumulated input PLUS the requested output reservation no longer fit its window. That is why it died at 138k
# and not at 200k.
_CONTEXT_RE = re.compile(
    r"context window|context[_ ]length|max_output_tokens|maximum context|"
    r"too many tokens|prompt is too long|input length and `max_tokens`", re.I)


def is_context_overflow(text: str) -> bool:
    """True if the error says the CONTEXT (input + output reservation) no longer fits the model's window.

    It must ALSO not be a quota problem: a 429 that happens to mention tokens is the other thing, and confusing
    the two would send us compacting when the right move is to relay to another provider."""
    t = text or ""
    if not _p._CONTEXT_RE.search(t):
        return False
    return _p.classify_failure(t) == ""


# V2-243 — UN SALDO AGOTADO NO ES UNA CUOTA, y decirlo mal es el defecto, no un matiz de redacción. Una CUOTA
# anuncia cuándo vuelve y vuelve sola; un SALDO no vuelve hasta que el operador recargue. Los dos caen hoy en
# `exhausted`, así que el saldo heredaba el suelo de media hora y el panel escribía «sin cuota hasta las 03:02»
# — una fecha en la que no va a pasar nada. Medido en producción el 2026-08-21: `Insufficient Balance` de
# DeepSeek (HTTP 402) dos veces, con «sin cuota hasta el 21 Aug 03:02 · SIN RELEVO disponible», y el arnés paró
# de medir porque el cerebro se quedó sin proveedor.
#
# Predicado APARTE y no un valor nuevo de `classify_failure` a propósito: esa función la comparte
# `nucleo/flash/provider_chain.py`, que ramifica sobre sus tres valores y devolvería None (ni cooldown ni relevo)
# ante uno desconocido. Misma razón por la que `is_context_overflow` vive aparte, escrita ahí arriba.
_DEPLETED_RE = re.compile(
    r"insufficient (?:balance|credit|funds)|out of credit|no credit|balance is insufficient|"
    r"saldo insuficiente|sin saldo|recharge|top ?[- ]?up", re.I)


def is_depleted(text: str) -> bool:
    """True si el proveedor dice que se quedó SIN SALDO y NO anuncia cuándo vuelve.

    La ausencia de fecha es parte del predicado: un plan con forfait que dice «reset at …» sí vuelve solo, y
    tratarlo como saldo lo apagaría durante horas de más."""
    t = str(text or "")
    if not _p._DEPLETED_RE.search(t):
        return False
    return not _p._RESET_RE.search(t)


# V2-682 — A PROVIDER THAT REJECTS THE REQUEST ITSELF IS DOWN FOR US, even though it answers instantly.
#
# Measured on the operator's own engine, 2026-09-12 (English session, 19:53 → 20:46): **15 escalations, 15
# deaths**, every one of them the same line —
#
#     API Error: 400 [1210][Invalid API parameter, please check the documentation.]
#
# — from `glm-5.3`. He heard «That task couldn't be completed — a provider failure» seven times and asked
# «What fucking provider failed?». Nothing relayed, nothing went on cooldown, nothing reached the status
# panel: `classify_failure` knows quota, credentials and rate-limits, and a 400 is none of the three, so it
# returned '' and `note_failure` walked away. The next errand picked the SAME broken tier, and the one after
# that. An outage that is total and permanent looked, to the relay, like an ordinary error.
#
# It is the third face of a lesson already written twice in this repo: **a capability is MEASURED, never
# read**. `research.py` met this exact provider code (1210, «This model always engages in thinking and cannot
# be disabled») and closed it for ITS caller with a local predicate; this closes it for the class.
#
# A SEPARATE predicate, not a fourth value of `classify_failure`, for the reason written above `is_depleted`:
# that function is shared with `nucleo/flash/provider_chain.py`, which branches on its three values and would
# return None for an unknown one — silently no-oping in the very module that has to relay.
#
# The failure directions are deliberately asymmetric. Marking a HEALTHY tier broken costs one relay to the
# next tier, which is exactly what the chain is for; NOT marking a broken one costs every errand, for as long
# as it stays broken. So a reading this cannot classify errs towards relaying — and the cooldown is SHORT,
# because unlike an empty wallet a rejected parameter is our config or their deploy, and both get fixed in
# minutes rather than days.
_BROKEN_RE = re.compile(
    r"\b(?:400|404|422)\b|invalid[ _]?(?:api[ _]?)?parameter|invalid[ _]request|"
    r"unsupported[ _](?:parameter|model)|model[ _](?:not[ _]found|does[ _]not[ _]exist)|unknown[ _]model|"
    # The Claude Code CLI's own wording: it swallows the provider's answer (measured 2026-09-28: a Z.ai
    # `429 [1310] Weekly/Monthly Limit Exhausted` came out as only this line, no status code), so the CLI
    # sentence is all we get. Either reading — model gone or access gone — means THIS tier cannot serve.
    r"issue with the selected model|may not have access to it",
    re.I)


def is_broken_request(text: str) -> bool:
    """True when the provider REJECTED the call itself — a deterministic 4xx that will repeat identically.

    Three things it must NOT be, and each exclusion is load-bearing:
      · a quota / credential / rate problem — `classify_failure` owns those and answers them better;
      · a blown CONTEXT, which is very often a 400 too and whose answer is COMPACT AND CONTINUE
        (`handoff.context_handoff`): relaying it would blow up identically on the next tier, because the cause
        is the size of the conversation and not who serves it;
      · anything with no 4xx signature at all — a timeout or a 5xx is transient and retrying is right."""
    t = str(text or "")
    if not _p._BROKEN_RE.search(t):
        return False
    if _p.classify_failure(t):
        return False
    return not _p.is_context_overflow(t)


def classify_failure(text: str) -> str:
    """'exhausted' (plan/cuota agotada, hay que relevar) · 'auth' · 'rate' (pasajero) · '' (no es de proveedor)."""
    t = (text or "")
    if _p._EXHAUSTED_RE.search(t):
        return "exhausted"
    low = t.lower()
    if any(x in low for x in ("401", "403", "invalid api key", "unauthorized", "authentication")):
        return "auth"
    # VENTANA AGOTADA ≠ RATE-LIMIT (2026-08-10). Un «Usage limit reached for 5 hour» o cualquier 429 que ANUNCIE su
    # hora de reset no se arregla reintentando: hay que esperar a esa hora y, mientras, usar otro escalón. Caía en
    # `rate`, y `rate` no pone cooldown ni releva — así que el proveedor seguía siendo el elegido durante horas y
    # cada worker nuevo quemaba su reintento contra él.
    if _p._WINDOW_RE.search(t) or ("429" in low and _p._RESET_RE.search(t)):
        return "exhausted"
    if "429" in low or "too many requests" in low or "rate limit" in low:
        return "rate"
    return ""


# ── UN WORKER CIEGO NO ES UN WORKER CAÍDO (2026-08-10) ────────────────────────────────────────────────────────
# Hallazgo de una prueba e2e real: el plan de un proveedor se agota por DOS vías que no son la misma cosa.
#
#   · el MODELO se agota → la llamada falla → `note_failure` releva de escalón y el worker sigue en otro sitio.
#     Esto ya funcionaba (y se vio funcionar: relevó a la licencia local y entregó).
#   · las TOOLS INTEGRADAS del proveedor se agotan (búsqueda web y lector de páginas servidos por él) → la llamada
#     al modelo NO falla. El worker sigue razonando perfectamente… pero **CIEGO**: no puede buscar ni leer una
#     página. El error viaja dentro de un `tool_result`, que hasta ayer se descartaba como ruido interno, así que
#     no había alerta, ni relevo, ni una línea en el registro. El worker parecía sano y entregaba conclusiones
#     sin material.
#
# Es exactamente el modo de fallo que más caro sale aquí: un estado que ENGAÑA. Lo que hace esta función es
# separar las dos cosas para poder DECIRLO. Deliberadamente NO pone el escalón en cooldown: sus tools están
# agotadas, su modelo no, y castigar al modelo por eso apagaría un proveedor que funciona para todo lo demás.
# Qué hacer con esa política (¿relevar igualmente? ¿solo para tareas de investigación?) es decisión del operador,
# no un efecto colateral de instrumentar.
_TOOL_LIMIT_RE = re.compile(
    r"web_search|websearch_prime|web_search_prime|webreader|web_reader|"          # las tools integradas por nombre
    r"search.{0,20}(?:quota|limit)|(?:quota|limit).{0,20}search", re.I)


def classify_tool_failure(text: str) -> str:
    """'blind' si el error de un `tool_result` es una cuota agotada de las TOOLS del proveedor · '' si no lo es.

    Se exige que sea (a) un problema de cuota/límite Y (b) que hable de las tools: un 429 pelado del modelo no es
    ceguera, es el caso que ya cubre `note_failure`, y confundirlos daría una alerta equivocada."""
    t = text or ""
    if not _p._TOOL_LIMIT_RE.search(t):
        return ""
    return "blind" if (_p.classify_failure(t) in ("exhausted", "rate")) else ""
