"""nucleo/flash/segmenter.py — ¿ESTO YA ES UNA PETICIÓN CON SENTIDO? (V2-095, 2026-08-14).

## El fallo

El límite de un turno lo ponía SOLO la acústica: `voice/endpointing.py` decide con silencio, energía y duración —
nunca con el CONTENIDO. Un operador que piensa en voz alta pausa a mitad de frase, y cada pausa abría un turno
completo que el fragmento siguiente cancelaba. Medido en la sesión b70a45d0:

    465s → 626s (161 s):  22 prompts · 18 cancelados · 20 rellenos de espera · CERO respuestas

…con prompts montados sobre trozos como «del», «del software,», «Un un superplanning» o «a». En toda la sesión:
89 transcripciones finales del operador, **33 seguidas de cancelación**, 53 prompts para 11 respuestas — el 79%
del gasto tirado, y una escalada a worker lanzada sobre una petición truncada que el operador tuvo que cancelar.

## La decisión de diseño (y por qué NO es la que se descartó)

El 2026-08-02 se midió partir el turno en dos peticiones al LLM y se DESCARTÓ con números: el prompt bajaba de
9.729 a 1.221 tokens pero el turno subía de 1.938 a 6.208 ms, porque cada ida y vuelta cuesta 1,5-4,5 s. Aquello
ponía las DOS llamadas en el camino crítico, después de que el operador callara.

Esto es distinto: la primera etapa decide **dónde acaba la frase**, y corre MIENTRAS EL OPERADOR HABLA — en tiempo
que ya estamos esperando. No añade latencia percibida porque no está en el camino crítico.

Y hay una segunda diferencia que sale de mirar los datos antes de escribir el código: **la mayoría de los cortes no
necesitan un modelo**. De los 89 fragmentos reales, los que iban a medias acaban en palabra función («del», «a»,
«para que», «los») o en coma. Eso es una regla léxica, determinista, de coste cero y latencia cero.

The model (layer 2, `judge()`, V2-102) is reserved for the genuinely ambiguous case — called from
`nucleo/flash/accumulator.py::offer()` ONLY when this layer 1 says incomplete, so most turns still spend no
token at all. No longer opt-in: `judge_enabled()` is ON by default (kill-switch `ZAELAR_TURN_JUDGE=0`) — see
the section below.

## Invariantes

  - **Nunca atasca el turno.** Es una capa de RETENCIÓN sobre el endpointing acústico, no un sustituto: pasado
    `MAX_HOLD_S` se entrega lo que haya. La acústica sigue siendo el techo.
  - **Fail-open.** Cualquier duda, error o texto raro → «completo» (comportamiento de antes). Retener de más
    convertiría a un agente lento en un agente mudo.
  - **Determinista y sin I/O** en su capa 1: se puede probar sola, y se prueba contra los 89 fragmentos de la
    sesión real.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata

from loguru import logger

# Techo de retención: por encima de esto se entrega SIEMPRE, diga lo que diga el análisis. Un operador que se corta
# a mitad («…y ponerlo en la») no puede quedarse sin respuesta para siempre por una coma.
MAX_HOLD_S = float(os.getenv("ZAELAR_SEGMENTER_MAX_HOLD_S", "6.0"))

# Palabras FUNCIÓN en DOS clases, y la distinción NO es cosmética — es la que separa retener un dictado a medias de
# retener una orden de parar. Salió de medir contra las 195 sesiones del registro (ver `should_hold`): la primera
# versión tenía UNA sola lista y trataba el punto final como irrelevante, así que **«Y que lo pares todo.» y
# «Ciérralo todo y páralo todo.» se retenían** por acabar en «todo». Retrasar una orden de PARAR es exactamente lo
# que V2-092 («parar es parar») prohíbe, y era el peor caso posible de esta capa.
#
# _HARD = no pueden cerrar un enunciado en castellano NUNCA, diga lo que diga la puntuación. «de.» sigue siendo un
# fragmento aunque el STT le ponga un punto (y se lo pone: pone puntos donde le parece).
_HARD = {
    # preposiciones y locuciones
    "a", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante", "en", "entre", "hacia", "hasta",
    "mediante", "para", "por", "segun", "sin", "sobre", "tras", "al",
    # artículos y posesivos
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "mi", "mis", "tu", "tus", "su", "sus",
    # conjunciones y relativos
    "y", "e", "o", "u", "ni", "que", "quien", "quienes", "cuyo", "cuya", "porque", "pero", "aunque", "pues",
    # inglés (el operador mezcla)
    "the", "an", "of", "to", "for", "with", "and", "or", "but", "in", "on", "at", "from", "by", "that",
    "which", "who",
}

# _SOFT = suelen continuar, pero SÍ pueden cerrar una frase legítima («páralo todo.», «no quiero más.», «¿cómo?»).
# Para estas la puntuación final MANDA: solo delatan continuación si el STT no cerró la frase. La puntuación es una
# señal REAL, medida en el corpus — la llevan el 74% de los enunciados completos y solo el 29% de los fragmentos.
_SOFT = {
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella",
    "otro", "otra", "otros", "otras", "mucho", "mucha", "muchos", "muchas", "todo", "toda", "todos", "todas",
    "cada", "cualquier", "algun", "alguna", "algunos", "algunas", "ningun", "ninguna",
    "como", "cuando", "donde", "si", "entonces", "ademas", "tambien", "tampoco", "ya", "mas", "menos",
    "muy", "tan", "casi", "solo", "incluso", "asi",
    "very", "so", "then", "also",
}

_DANGLING = _HARD | _SOFT

# El **acento diacrítico** distingue pares que al normalizar se vuelven la MISMA palabra, y en cada par uno de los
# dos es función y el otro no. Ya costó un fallo con «sí»/«si» (la frase que autorizó al worker en la sesión real
# era «Sí, te autorizo a borrar toda la agenda»), y el corpus grande sacó el mismo patrón con «estás»/«estas»:
# «¿Qué tal? ¿Cómo estás?» se retenía por leerse como el demostrativo. Se mira el token CRUDO, con su tilde.
# OJO: NO se puede generalizar a «cualquier palabra con tilde no es función» — `según`, `además`, `también`, `así`,
# `algún` y `ningún` llevan tilde y SÍ lo son.
_ACCENTED_NOT_FUNCTION = {"sí", "está", "estás", "él", "tú", "mí", "sé", "dé", "té", "más", "aún", "sólo"}

# `mí` (disjunctive pronoun: «de mí», «sobre mí», «para mí» — extremely common on "what do you know about me"
# asks) is PHONETICALLY IDENTICAL to the possessive determiner «mi» once the tilde is gone, and STT drops
# accents on monosyllables far more often than it keeps them — so gating the exemption on `_ACCENTED_NOT_FUNCTION`
# (which only fires when the tilde survived) missed the common case and held these turns FOREVER (no ceiling
# applies here — see `accumulator.py`'s "no hay válvula de tiempo" — reproduced live 2026-08-16: «dame los datos
# personales que conoces de mi» repeated three times, zero responses). The fix doesn't need the accent at all: a
# possessive determiner can NEVER legally be the LAST word of a Spanish sentence (it always needs a following
# noun — «mi coche», never bare «mi»), so trailing «mi» always means either the pronoun or a genuine mid-word
# cut. Same asymmetric-cost call as `_ALSO_A_VERB`: retaining a real request forever is worse than occasionally
# firing early on someone who got cut off naming the noun. Scoped to the ENDING check only (rules 2b/2c below) —
# a fragment that STARTS with «mi» and doesn't close (rule 5, "continues the previous chunk") is unaffected.
_ENDING_PRONOUN_HOMOPHONE = {"mi"}

# Verbos/auxiliares que EXIGEN complemento: «y tiene que haber», «puedes mover eso sin grandes» → falta el objeto.
_NEEDS_OBJECT = {"haber", "hacer", "poner", "dar", "tener", "ser", "estar", "ir", "decir", "ver", "querer"}

# Palabras que en castellano son función Y TAMBIÉN verbo en imperativo, así que NO pueden delatar por sí solas una
# continuación. «para la música» es una orden completísima, y retenerla 6 s sería una regresión de las gordas: es de
# las cosas que el operador dice más. Se excluyen del arranque de la regla 5.
_ALSO_A_VERB = {"para", "sigue", "deja", "sobre", "como", "cuando", "donde", "salva", "baja", "sube", "pon"}

_TERMINAL_RE = re.compile(r"[.!?…]\s*$")
_WORD_RE = re.compile(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]+", re.UNICODE)


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def _words(s: str) -> list[str]:
    return [w for w in _WORD_RE.sub(" ", _norm(s)).split() if w]


def _raw_last(s: str) -> str:
    """El último token CON su tilde (para `_ACCENTED_NOT_FUNCTION`). `_words` normaliza y perdería la información."""
    toks = _WORD_RE.sub(" ", s or "").split()
    return toks[-1].lower() if toks else ""


def looks_incomplete(text: str) -> tuple[bool, str]:
    """Capa 1, DETERMINISTA: ¿le falta algo a esta frase? Devuelve `(incompleta, por_qué)`.

    El «por qué» no es adorno: es lo que se emite al timeline para que una retención equivocada se pueda ver y
    corregir, en vez de ser un turno que no llega y nadie sabe por qué."""
    raw = (text or "").strip()
    if not raw:
        return False, ""                      # nada que retener; que lo resuelva la acústica
    ws = _words(raw)
    if not ws:
        return False, ""

    # 0) BACKCHANNEL o confirmación («sí», «no», «vale», «gracias», «vale vale»): es un turno COMPLETO por
    #    definición, y a menudo el más importante — es cómo el operador responde a una pregunta o autoriza algo
    #    irreversible. Se reusa el mismo juego que ya usa el turno acústico, en vez de mantener otra lista.
    #    (Sin esto, «sí» se retenía porque el «si» sin tilde es conjunción y está en `_DANGLING`.)
    try:
        from voice import endpointing as _ep
        if _ep.is_backchannel(raw):
            return False, ""
    except Exception:
        pass

    # 1) Acaba en COMA (o en dos puntos / punto y coma): el operador va a seguir. Es el caso más frecuente de la
    #    sesión — «Vale,», «del software,», «con mucha calidad,», «Entonces, necesito, de alguna manera,».
    if re.search(r"[,;:]\s*$", raw):
        return True, "acaba en coma"

    # 2) Salvo que sea UNA SOLA palabra que también es verbo: «para» a secas es una orden de parar, no una
    #    preposición colgada — y es de las más importantes que existen.
    if len(ws) == 1 and ws[0] in _ALSO_A_VERB:
        return False, ""

    closed = bool(_TERMINAL_RE.search(raw))
    last_raw = _raw_last(raw)

    # 2b) Acaba en palabra función DURA → a medias, con punto o sin él. El STT pone puntos donde le parece, y
    #     «No el widget, los datos de la.» o «planning de...» llevan punto y están a medias igual.
    # 2c) Acaba en palabra función BLANDA → solo si el STT no cerró la frase. Sin esta rama se retenían órdenes de
    #     PARAR («páralo todo.») y preguntas cerradas («¿cómo estás?»); ver el comentario de `_SOFT`/`_HARD`.
    if ws[-1] not in _ENDING_PRONOUN_HOMOPHONE and last_raw not in _ACCENTED_NOT_FUNCTION:
        if ws[-1] in _HARD:
            return True, f"acaba en «{ws[-1]}», que gobierna algo que aún no ha dicho"
        if ws[-1] in _SOFT and not closed:
            return True, f"acaba en «{ws[-1]}» y la frase no está cerrada"

    # 3) Una sola palabra FUNCIÓN («del», «a», «que»): no puede ser un turno. Cualquier otra palabra suelta SÍ
    #    puede serlo —«Cancélalo», «Sigue», «Gracias»— y se deja pasar a propósito: el coste es asimétrico. Colar un
    #    turno de más cuesta una llamada; retener «cancélalo» seis segundos deja al operador viendo cómo el agente
    #    ignora una orden de parar. Ante la duda, PASA.
    if len(ws) == 1 and ws[0] in _DANGLING:
        return True, f"una sola palabra función («{ws[0]}»)"

    # 4) Acaba en un verbo que pide complemento y no hay cierre: «Y tiene que haber».
    if not closed and ws[-1] in _NEEDS_OBJECT:
        return True, f"acaba en «{ws[-1]}» y falta el complemento"

    # 5) EMPIEZA por palabra función y no cierra: es la CONTINUACIÓN del fragmento anterior, no una frase nueva —
    #    «Con dos navegadores», «de framework y y cómo hacer una auditoría», «Un un superplanning».
    #    Aquí había una regla «corta y sin cerrar» (≤3 palabras) que hubo que quitar: retenía TODAS las órdenes
    #    cortas de voz —«abre la agenda», «sube el volumen», «pon música», «cierra eso»—, o sea justo lo más
    #    frecuente que dice el operador. El techo de 6 s lo habría degradado a un retraso en vez de una pérdida,
    #    pero 6 s de espera en «pon música» es una regresión gorda. Lo que de verdad tienen en común esos
    #    fragmentos no es ser cortos: es EMPEZAR por una palabra que solo tiene sentido pegada a lo anterior.
    # OJO al acento (mismo motivo que en 2b/2c, ver `_ACCENTED_NOT_FUNCTION`): «sí» y «si» se escriben igual una vez
    # normalizado, y la frase que autorizó al worker en la sesión era «Sí, te autorizo a borrar toda la agenda» —
    # retenerla habría sido exactamente el fallo que estamos arreglando, por el otro lado.
    _first_raw = (_WORD_RE.sub(" ", raw).split() or [""])[0].lower()
    if (not closed and ws[0] in _DANGLING and ws[0] not in _ALSO_A_VERB
            and _first_raw not in _ACCENTED_NOT_FUNCTION):
        return True, f"empieza por «{ws[0]}»: continúa lo anterior"

    return False, ""


def should_hold(text: str, *, held_s: float = 0.0) -> tuple[bool, str]:
    """¿RETENER el turno en vez de dispararlo ya? Es la pregunta que responde a la acústica.

    `held_s` = cuánto llevamos ya retenido este mismo enunciado. Pasado `MAX_HOLD_S` se entrega SIEMPRE: la capa
    semántica puede retrasar un turno, nunca perderlo.

    ⚠️ **Investigated 2026-08-15 (session d4b2bc35): NO production caller ever passes `held_s`, so this ceiling
    is never actually reached — and that is not an oversight, it's REDUNDANT by construction.** The only site
    that vetoes an individual ACOUSTIC turn's close is `voice/engine/speech/turn/semantic.py`, which calls
    `looks_incomplete()` directly (no `held_s`); but LiveKit already imposes its OWN, smaller ceiling ahead of
    it — `HOLD_MAX` in `voice/endpointing.py`, **2.2s by default**, always below `MAX_HOLD_S` (6s) — so the
    semantic veto never gets to wait long enough for `MAX_HOLD_S` to matter. "The acoustics remain the ceiling"
    (the invariant above) is true, but the ceiling doing the actual work is LiveKit's, not this function's. The
    FULL fragment chain (V2-096, `nucleo/flash/accumulator.py`) doesn't use it either, and there it's deliberate:
    that layer replaced "delay with a ceiling" with "accumulate with no clock" (see the accumulator module's
    docstring) precisely because a fixed ceiling covered less than half the real pauses measured. Conclusion: no
    need to wire `should_hold` in anywhere new — `HOLD_MAX`'s 2.2s already keeps the promise this docstring
    makes, by a different route. The function (and its tests) stay because they document a real invariant and
    remain the right call for the day `ZAELAR_ENDPOINT_MAX_S` is raised past 6s; today it is pure code with no
    observable effect, not a security gap.
    """
    if held_s >= MAX_HOLD_S:
        return False, "techo de retención"
    try:
        inc, why = looks_incomplete(text)
    except Exception:
        return False, ""                      # fail-open duro: mejor un turno de más que un agente mudo
    return inc, why


def judge_enabled() -> bool:
    """Layer 2 (LLM) — ON by default (V2-102, 2026-08-16). Used to be OPT-IN behind `ZAELAR_SEGMENTER_MODEL`,
    which NOTHING ever read to actually call a model — a declared, never-wired extension point (confirmed by
    grep: zero real callers). This codebase has hit "a capability whose default is off is a capability nobody
    has" three times already (Susurro, REM, this very module's own turn-detector wiring) — an opt-in judge would
    just be the fourth. Kill-switch `ZAELAR_TURN_JUDGE=0` for emergencies (a broken/unreachable model must not
    block voice — `judge()` fails open to "incomplete" regardless, this flag is a manual escape hatch on top)."""
    return os.getenv("ZAELAR_TURN_JUDGE", "1") == "1"


_JUDGE_SYSTEM = (
    "You judge whether a voice assistant's user has FINISHED a request, or is still mid-sentence. You get the "
    "text of their utterance so far (it may be a fragment, possibly built by gluing several pauses together). "
    "The person may speak ANY language — judge by MEANING, never by a fixed word list.\n\n"
    "Give exactly ONE verdict:\n"
    "  COMPLETE — a full, actionable request or question. Casual/short is fine. Includes a sentence that trails "
    "off on a dropped-accent pronoun or a subject casual speech omits (e.g. Spanish ending in unaccented \"mi\" "
    "meaning \"mí\" — \"give me what you know about mi\" reads oddly in English but is complete in Spanish).\n"
    "  ASK — actionable-shaped, but missing one specific piece a real assistant would need and would ask about, "
    "rather than silently guess or silently wait.\n"
    "  INCOMPLETE — clearly trails off mid-thought (an unfinished clause, a dangling connector) and the person "
    "is very likely about to keep talking.\n\n"
    "Reply with STRICT JSON only, no prose, no code fences: "
    "{\"verdict\": \"COMPLETE\"|\"ASK\"|\"INCOMPLETE\", \"question\": string or null}. "
    "`question` is a SHORT, natural clarifying question IN THE SAME LANGUAGE as the utterance, ONLY when verdict "
    "is ASK — otherwise null."
)


def _parse_judge(raw: str | None) -> tuple[str, str]:
    """Strict-ish JSON parse with the same tolerant brace-slicing `i18n/init/generate.py::_parse` uses (a model
    occasionally wraps its answer in a code fence despite the instruction not to). Fail-open to "incomplete"."""
    if not raw:
        return "incomplete", ""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
    except Exception:
        return "incomplete", ""
    verdict = str(d.get("verdict") or "").strip().upper()
    if verdict == "COMPLETE":
        return "complete", ""
    if verdict == "ASK":
        q = d.get("question")
        q = str(q).strip() if isinstance(q, str) else ""
        return ("ask", q) if q else ("incomplete", "")   # ASK with no question text isn't actionable — fail open
    return "incomplete", ""


async def judge(text: str) -> tuple[str, str]:
    """Layer 2, LLM: the safety net for whatever layer 1 (`looks_incomplete`) called ambiguous. Real intelligence
    instead of more hardcoded rules — works in any language the operator speaks, not just the es/en `_HARD`/
    `_SOFT` vocabularies above. Returns `(verdict, extra)`: verdict ∈ "complete"|"ask"|"incomplete"; `extra` is
    the clarifying question (only for "ask") or "". Off the hot path (`asyncio.to_thread`, same pattern as
    `i18n/init/detect.py::_by_llm`) and DELIBERATELY fail-open to `("incomplete", "")` on ANY error (unreachable
    model, malformed JSON, disabled) — never let a broken judge block or mis-fire a turn; `accumulator.py`'s gap
    valve still gets a second `judge()` call before anything is discarded, so "incomplete" here is never final."""
    if not judge_enabled():
        return "incomplete", ""
    text = (text or "").strip()
    if not text:
        return "incomplete", ""
    try:
        from nucleo import memllm
        raw = await asyncio.to_thread(
            memllm.chat_sync, "turn_complete", _JUDGE_SYSTEM, text,
            max_tokens=120, temperature=0.0, timeout=6.0,
        )
        return _parse_judge(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"segmenter.judge: failed ({str(e)[:160]}) — fail-open to incomplete")
        return "incomplete", ""
