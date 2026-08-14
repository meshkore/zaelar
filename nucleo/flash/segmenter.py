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
«para que», «los») o en coma. Eso es una regla léxica, determinista, de coste cero y latencia cero. El modelo se
reserva para lo genuinamente ambiguo y es OPT-IN (`ZAELAR_SEGMENTER_MODEL`): mientras nadie lo active, esta capa no
gasta un token.

## Invariantes

  - **Nunca atasca el turno.** Es una capa de RETENCIÓN sobre el endpointing acústico, no un sustituto: pasado
    `MAX_HOLD_S` se entrega lo que haya. La acústica sigue siendo el techo.
  - **Fail-open.** Cualquier duda, error o texto raro → «completo» (comportamiento de antes). Retener de más
    convertiría a un agente lento en un agente mudo.
  - **Determinista y sin I/O** en su capa 1: se puede probar sola, y se prueba contra los 89 fragmentos de la
    sesión real.
"""
from __future__ import annotations

import os
import re
import unicodedata

# Techo de retención: por encima de esto se entrega SIEMPRE, diga lo que diga el análisis. Un operador que se corta
# a mitad («…y ponerlo en la») no puede quedarse sin respuesta para siempre por una coma.
MAX_HOLD_S = float(os.getenv("ZAELAR_SEGMENTER_MAX_HOLD_S", "6.0"))

# Palabras FUNCIÓN: si la frase acaba en una de estas, falta lo que gobiernan. Salen de los fragmentos REALES de la
# sesión, no de una gramática: preposiciones, artículos, determinantes, conjunciones y relativos.
_DANGLING = {
    # preposiciones y locuciones
    "a", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante", "en", "entre", "hacia", "hasta",
    "mediante", "para", "por", "segun", "sin", "sobre", "tras", "al",
    # artículos y determinantes
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "mi", "mis", "tu", "tus", "su", "sus",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella",
    "otro", "otra", "otros", "otras", "mucho", "mucha", "muchos", "muchas", "todo", "toda", "todos", "todas",
    "cada", "cualquier", "algun", "alguna", "algunos", "algunas", "ningun", "ninguna",
    # conjunciones, relativos y adverbios de enlace
    "y", "e", "o", "u", "ni", "que", "quien", "quienes", "cuyo", "cuya", "como", "cuando", "donde", "porque",
    "pero", "aunque", "si", "pues", "entonces", "ademas", "tambien", "tampoco", "ya", "mas", "menos",
    "muy", "tan", "casi", "solo", "incluso", "asi",
    # inglés (el operador mezcla)
    "the", "a", "an", "of", "to", "for", "with", "and", "or", "but", "in", "on", "at", "from", "by", "that",
    "which", "who", "very", "so", "then", "also",
}

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

    # 2) Acaba en PALABRA FUNCIÓN, con o sin punto detrás. Salvo que sea UNA SOLA palabra que también es verbo:
    #    «para» a secas es una orden de parar, no una preposición colgada — y es de las más importantes que existen.
    if len(ws) == 1 and ws[0] in _ALSO_A_VERB:
        return False, ""

    # 2b) Acaba en PALABRA FUNCIÓN, con o sin punto detrás. Lo de «con o sin» importa: el STT pone puntos donde le
    #    parece, y «No el widget, los datos de la.» o «planning de...» llevan punto y están a medias igual.
    if ws[-1] in _DANGLING:
        return True, f"acaba en «{ws[-1]}», que gobierna algo que aún no ha dicho"

    # 3) Una sola palabra FUNCIÓN («del», «a», «que»): no puede ser un turno. Cualquier otra palabra suelta SÍ
    #    puede serlo —«Cancélalo», «Sigue», «Gracias»— y se deja pasar a propósito: el coste es asimétrico. Colar un
    #    turno de más cuesta una llamada; retener «cancélalo» seis segundos deja al operador viendo cómo el agente
    #    ignora una orden de parar. Ante la duda, PASA.
    if len(ws) == 1 and ws[0] in _DANGLING:
        return True, f"una sola palabra función («{ws[0]}»)"

    # 4) Acaba en un verbo que pide complemento y no hay cierre: «Y tiene que haber».
    if not _TERMINAL_RE.search(raw) and ws[-1] in _NEEDS_OBJECT:
        return True, f"acaba en «{ws[-1]}» y falta el complemento"

    # 5) EMPIEZA por palabra función y no cierra: es la CONTINUACIÓN del fragmento anterior, no una frase nueva —
    #    «Con dos navegadores», «de framework y y cómo hacer una auditoría», «Un un superplanning».
    #    Aquí había una regla «corta y sin cerrar» (≤3 palabras) que hubo que quitar: retenía TODAS las órdenes
    #    cortas de voz —«abre la agenda», «sube el volumen», «pon música», «cierra eso»—, o sea justo lo más
    #    frecuente que dice el operador. El techo de 6 s lo habría degradado a un retraso en vez de una pérdida,
    #    pero 6 s de espera en «pon música» es una regresión gorda. Lo que de verdad tienen en común esos
    #    fragmentos no es ser cortos: es EMPEZAR por una palabra que solo tiene sentido pegada a lo anterior.
    # OJO al acento: «sí» (confirmación) y «si» (conjunción) se escriben igual una vez normalizado, y la frase que
    # autorizó al worker en la sesión era «Sí, te autorizo a borrar toda la agenda» — retenerla habría sido
    # exactamente el fallo que estamos arreglando, por el otro lado. Se mira el texto CRUDO para no perder la tilde.
    _first_raw = (_WORD_RE.sub(" ", raw).split() or [""])[0].lower()
    if (not _TERMINAL_RE.search(raw) and ws[0] in _DANGLING and ws[0] not in _ALSO_A_VERB
            and _first_raw not in ("sí", "sí,", "mas")):
        return True, f"empieza por «{ws[0]}»: continúa lo anterior"

    return False, ""


def should_hold(text: str, *, held_s: float = 0.0) -> tuple[bool, str]:
    """¿RETENER el turno en vez de dispararlo ya? Es la pregunta que responde a la acústica.

    `held_s` = cuánto llevamos ya retenido este mismo enunciado. Pasado `MAX_HOLD_S` se entrega SIEMPRE: la capa
    semántica puede retrasar un turno, nunca perderlo."""
    if held_s >= MAX_HOLD_S:
        return False, "techo de retención"
    try:
        inc, why = looks_incomplete(text)
    except Exception:
        return False, ""                      # fail-open duro: mejor un turno de más que un agente mudo
    return inc, why


def model_enabled() -> bool:
    """¿Está activada la capa 2 (modelo)? OPT-IN: mientras nadie ponga `ZAELAR_SEGMENTER_MODEL`, el segmentador no
    gasta un solo token. La capa 1 cubre los cortes observados en la sesión real; el modelo se reserva para lo
    genuinamente ambiguo, y su sitio es AQUÍ —fuera del camino crítico, mientras el operador habla— no en el camino
    que se midió y se descartó el 2026-08-02 (dos llamadas DESPUÉS de que callara: +4,3 s)."""
    return bool((os.getenv("ZAELAR_SEGMENTER_MODEL") or "").strip())
