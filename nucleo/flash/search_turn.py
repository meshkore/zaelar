"""nucleo/flash/search_turn.py — the WEB SEARCH turn, composed ONCE for both channels (V2-676).

## What this exists to stop

Measured on the operator's own English session (`af4429e0`, 2026-09-11, 22:02–22:04). He asked for the
weather in New York. FIVE searches fired, with good queries, and every one came back `n: 0` carrying the
reason:

    failure: {kind: "captcha",
              detail: "google: bloqueado (captcha/tráfico inusual) · ddg: DuckDuckGo served an anti-bot
                       challenge («made by a human»)"}

What he heard back was this:

    «I actually don't have live internet access to fetch real-time information like current weather
     conditions. I can only work with knowledge from my training data, which has a cutoff date.»

The search module did its job. Observability recorded the reason faithfully. And the ONE reader who had to
explain the emptiness — the model composing the answer — was handed `RESULTADOS:\n(sin resultados)` and
nothing else, so it reached for the only story a language model has for an empty world: it denied having the
internet at all. **The evidence went to the timeline and never to the reader.**

So this module carries two things that used to be missing, and one that used to exist twice:

  1. `compose_system()` — the composing prompt, now INCLUDING why the results are empty when they are. It is
     shared by the live voice channel and the probe channel, which is why extracting it also retires a
     parallel implementation the two files had been apologising for since V2-135 (`probe.py` was at its
     architecture ceiling; a shared home pays that ratchet instead of raising it).
  2. `denial_repair()` — the backstop. A prompt is an instruction, not a guarantee: when the reply denies the
     capability anyway, the sentence is REPLACED by a true one from the language table. An agent telling its
     owner it has no internet is not a bad answer, it is a false claim about the product.

## The asymmetry that decides the wording

Telling the truth about a blocked search costs one honest sentence. Denying the capability costs the
operator's belief that the product works at all — he wrote «no entiendo cómo después de dos meses de pruebas
el sistema falla y dice que no sabe buscar». So the instruction is blunt and names the forbidden sentence
rather than merely asking for honesty.
"""
from __future__ import annotations

# Spoken-answer budget for the composing pass. Same on both channels.
MAX_TOKENS = 240


def _why_empty(res: dict) -> str:
    """What the model is told when the search came back with nothing. `res["failure"]` is what
    `websearch.search()` already records when the whole chain collapses — this is the seam that finally
    hands it to the reader who needs it."""
    fail = (res or {}).get("failure") or {}
    kind = str(fail.get("kind") or "").lower()
    if kind == "captcha":
        why = ("el buscador te ha respondido con una VERIFICACIÓN ANTI-ROBOT (captcha) y por eso no hay "
               "resultados")
    elif kind == "quota":
        why = "el buscador ha agotado su cuota por ahora y por eso no hay resultados"
    elif kind:
        why = f"la búsqueda ha fallado ({kind}) y por eso no hay resultados"
    else:
        why = "la búsqueda no ha devuelto nada útil esta vez"
    # The forbidden sentence is NAMED. «Be honest» is advice; «never say this» is a rule, and the sentence it
    # bans is the one measured coming out of the product.
    return (f"\n\nOJO — LA BÚSQUEDA SÍ SE HA HECHO: {why}. "
            "Dilo tal cual: que has mirado y que esta vez no has podido traer el dato, y ofrécete a mirarlo "
            "a fondo con el navegador. "
            "PROHIBIDO decir que no tienes acceso a internet, que no puedes consultar información en tiempo "
            "real, que solo tienes datos de entrenamiento o que tienes una fecha de corte: es FALSO —tienes "
            "buscador y navegador— y quien te escucha es el dueño de este sistema.")


def compose_system(operator_text: str, query: str, res: dict, ctx: str, *, today: str = "") -> str:
    """The system prompt for the pass that turns web results into one spoken answer."""
    from . import prompt as _prompt
    head = _prompt._lang_lock()
    if today:
        head += f"\nHOY es {today}."
    body = (
        "\nEl operador preguntó algo que requería BUSCAR en la web. Con estos RESULTADOS, responde a su "
        "pregunta en 1-2 frases HABLADAS: natural, sin markdown, sin emojis, sin leer URLs ni números de "
        "fuente. Si la pregunta es SENSIBLE A LA FECHA (el tiempo, una cotización, un resultado, algo «de "
        "hoy/ahora»): da el dato VIGENTE de hoy en adelante, nunca uno caducado, y si procede menciona el "
        "día. "
        # V2-135 — this pass used to read the QUERY as if it were the question, and the query is the model's
        # own reformulation: «¿a qué hora abre el Prado Y cuánto cuesta la entrada?» searched as «horario
        # Museo del Prado» arrived here as a one-fact question, so the price half was gone before composing.
        "Contesta TODO lo que preguntó (si pidió dos datos, los dos); si los resultados solo cubren una "
        "parte, di CUÁL falta y ofrécete a mirarla — no la dejes caer en silencio. "
        "Si los resultados NO contienen la respuesta clara, dilo con naturalidad; NO inventes datos que no "
        "estén en ellos."
    )
    tail = ("" if (res or {}).get("results") else _why_empty(res))
    return (head + body + tail
            + f"\n\nPREGUNTA DEL OPERADOR: {operator_text}"
            + f"\nBÚSQUEDA REALIZADA: {query}\n\nRESULTADOS:\n{ctx or '(sin resultados)'}")


def denial_repair(reply: str, res: dict) -> str:
    """The backstop, applied to the composed answer. Returns the reply unchanged, or the TRUE sentence in the
    operator's own language when the model denied the capability anyway.

    Deliberately NOT conditional on the search having failed: the denial is false whenever it is said. It is
    said most often over an empty result, which is why it lives on this path, but a reply claiming no internet
    access over seven good results would be just as wrong and is repaired the same way."""
    from . import answer_guards as _ag
    if not _ag.a_reply_denies_the_world(reply):
        return reply
    try:
        from i18n import langs as _lg
        spec = _lg.current_language()
        # A blocked chain has its own sentence (it names what happened); anything else falls back to the
        # «I could not check it» line, which claims nothing either way.
        return spec.search_blocked if ((res or {}).get("failure") or {}).get("kind") else spec.unverified_fact
    except Exception:  # noqa: BLE001
        return ("He mirado, pero esta vez no he podido traerte el dato. ¿Lo intento a fondo con el navegador?")
