"""voice/attention_judge.py — the judge `voice/attention.py` asks about a line it cannot decide by the mode alone.

Moved out of `attention.py` (V2-812 T-03), whose size ratchet went red the day the judge learnt its second question:
EXTRACT, never raise. The cut is clean — the prompt, the call and the parsing need nothing of the gate's state but
the assistant's current name — and `attention.py` imports every name back, so callers and tests keep reading
`attention._parse_directed`, `attention._DIRECTED_SYSTEM` and injecting a double through
`attention.set_directed_judge`.
"""
from __future__ import annotations

import asyncio
import json

from loguru import logger

# ⚠️ FRAMING measured 2026-09-01 (session 701fcc1b): the old prompt presented the phrase as loose audio plus a
# note of "what was being done" — and the judge returned {"directed": false} on «I told you that you have already
# opened it.» and «Are you listening to me?», 15/15 reproductions, because without the DIALOGUE frame a second-person
# sentence reads as two people in the room talking to each other. Presenting the assistant's own last utterance
# as "Zaelar acaba de decir …" flips those exact phrases to directed (3/3 each). The judge is still fallible —
# which is why `evaluate_content` no longer consults it at all inside an active conversation (see below) — but
# for the cold-start turns it does keep judging, this frame is the one that was measured to read replies-to-Zaelar
# as replies-to-Zaelar.
_DIRECTED_SYSTEM = (
    "Eres el filtro de atención de Zaelar, un asistente de voz con el MICRÓFONO SIEMPRE ABIERTO — no hay "
    "palabra de activación, así que además de a su operador oye conversación de fondo (familia, TV, terceros, "
    "llamadas) que NO va dirigida a él.\n\n"
    "Te doy lo último que dijo Zaelar (si habló) y la frase que se acaba de transcribir. Decide dos cosas.\n\n"
    "«directed»: ¿es el operador hablándole A ZAELAR? Le contesta, le pregunta, le corrige, se queja de lo que "
    "Zaelar ha hecho o dicho, le da datos o le pide algo. Es AMBIENTE solo si claramente habla con OTRA persona "
    "o es ruido sin relación con la conversación con Zaelar. Ante la duda, marca DIRIGIDO — dejar sin atender "
    "al operador es peor que procesar un poco de ruido.\n\n"
    "«request»: ¿le PIDE algo a Zaelar sin ambigüedad — que haga algo, que le busque o le diga algo, o un sí "
    "inequívoco a algo que Zaelar le acaba de ofrecer hacer? Un comentario, una queja, una exclamación, un "
    "asentimiento que puede estar confirmando lo que Zaelar dijo, o una frase dirigida a otra persona NO lo es. "
    "Ante la duda, marca que NO: lo que Zaelar fuera a hacer por esta frase se le preguntará antes.\n\n"
    'Responde SOLO con JSON: {"directed": true|false, "request": true|false}. Nada más.'
)


async def default_directed_judge(text: str, context: str) -> dict | None:
    """`{"directed": bool, "request": bool|None}`, or None if the judge failed (the caller fails open to
    directed). Off the hot path of the real turn thanks to `asyncio.to_thread` — same pattern as
    `segmenter.judge()`.

    V2-812 T-03 — the judge answers a SECOND question beside «is this for the agent?»: «is it a clear request
    to it?». The two are different and the car session needed both: «¿Seguro que no está silenciado?» is
    addressed and asks something, «Eso es.» after a statement-plus-offer is addressed and asks nothing. The
    first decides whether the line renews the window; the second whether a side effect may start from it
    without asking (`licence()`). The renamed assistant's name goes into the frame, because a judge that does
    not know «Johnny» is the agent reads «Johnny, ¿cuál es…» as two people talking."""
    try:
        from nucleo.memory_agent.processor import llm
        from voice import attention as _a
        name = _a.assistant_name().strip()
        who = f"Zaelar (se llama «{name}»)" if name and _a._norm(name) not in _a._DEFAULT_WAKEWORDS else "Zaelar"
        # Dialogue frame, not an activity note — see the measurement above `_DIRECTED_SYSTEM`.
        user = (f"{who} acaba de decir: «{context}»\n\nEl micrófono ha oído: «{text}»" if context
                else f"El micrófono ha oído: «{text}»")
        raw = await asyncio.to_thread(
            llm.chat_sync, "directed", _DIRECTED_SYSTEM, user,
            max_tokens=30, temperature=0.0, timeout=4.0,
        )
        return _parse_judgement(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"attention._default_directed_judge: failed ({str(e)[:160]}) — fail-open to directed")
        return None


def _parse_judgement(raw: str | None) -> dict | None:
    """Tolerant of a code fence (same problem as `segmenter._parse_judge`). None if it could not be read;
    `request` is None when the judge did not answer it (an older reply shape)."""
    if not raw:
        return None
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
    except Exception as e:  # noqa: BLE001 — an unreadable reply is «no verdict»; the caller fails open
        logger.debug(f"attention_judge: unreadable reply ({e!r}): {s[:80]!r}")
        return None
    v = d.get("directed") if isinstance(d, dict) else None
    if not isinstance(v, bool):
        return None
    r = d.get("request")
    return {"directed": v, "request": r if isinstance(r, bool) else None}


def _parse_directed(raw: str | None) -> bool | None:
    j = _parse_judgement(raw)
    return None if j is None else j["directed"]


def _as_judgement(out) -> tuple[bool | None, bool | None]:
    """A judge may answer the old way (a bare bool, `set_directed_judge` doubles) or the new one (a dict):
    `(directed, request)`, each None when unknown."""
    if isinstance(out, dict):
        d, r = out.get("directed"), out.get("request")
        return (d if isinstance(d, bool) else None), (r if isinstance(r, bool) else None)
    return (out if isinstance(out, bool) else None), None
