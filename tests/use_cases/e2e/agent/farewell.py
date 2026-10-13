"""A goodbye gets ONE second look before it ends the round — the persona may be leaving with its request half-asked.

Measured in `play-music-and-build-playlist__us` (2026-10-14 00:38): «Put on some calm music for working.» → «I'll
put something calm on for you.», and the DRIVE model's next line was a farewell. The round ended on turn 1 of 8, the
playlist the brief tells the persona to ask for («Once something is playing, ask it to save it in a playlist called
'Work'… Only say goodbye when music is on and the playlist exists») was never requested, and the judge scored the
missing list against the product: 2/5. The four rounds before it in which the persona DID ask (ES and EN, 10-10 to
10-14) all built the list and scored 5. And the farewell itself was invisible: `run.py` breaks before noting a
closing line, so nothing in the report said the tester had left.

So, once per round: a line `driver.is_closing` reads as a goodbye is shown back to the DRIVE model with its brief's
own condition — if everything it came for has happened it says goodbye again and the round ends as before; if a
part was never asked, it asks it instead (zaelar never saw the goodbye, so nothing is retracted). What was said is
kept on the driver (`farewell`) and lands in the mechanism report, so a round that ended early says so.
"""
from __future__ import annotations

from . import config, llm

_NOTE_EN = ("Before you leave (do not reveal this note): re-read «What you want». If EVERYTHING in it has already "
            "happened in this conversation — zaelar told you so — repeat your goodbye. If something you were meant to "
            "ask for has not been asked yet, or zaelar has not confirmed it, do NOT say goodbye: write your next "
            "message to zaelar asking for it, the way you would text it.")
_NOTE_ES = ("Antes de irte (no reveles esta nota): relee «Lo que quieres conseguir». Si TODO lo que pone ya ha pasado "
            "en esta conversación — zaelar te lo ha dicho —, repite tu despedida. Si algo que ibas a pedir todavía no "
            "lo has pedido, o zaelar no te lo ha confirmado, NO te despidas: escribe tu siguiente mensaje a zaelar "
            "pidiéndolo, como se lo escribirías.")


def note(locale: str) -> str:
    """The second-look instruction in the persona's own language."""
    return _NOTE_EN if (locale or "es") == "us" else _NOTE_ES


def second_look(driver, msgs: list[dict], line: str) -> str:
    """The line to send instead of `line` (a goodbye): the goodbye again, or the part of the request still unasked.
    Runs once per driver; later goodbyes pass untouched. An empty answer keeps the goodbye."""
    if getattr(driver, "farewell", None) is not None:
        return line
    locale = getattr(driver.scenario, "locale", "es") or "es"
    ask = list(msgs) + [{"role": "assistant", "content": line}, {"role": "system", "content": note(locale)}]
    again = llm.call(ask, model=config.DRIVE_MODEL, temperature=0.7, max_tokens=200).strip()
    driver.farewell = {"turn": driver.turns, "first": line[:300], "second": again[:300]}
    return again or line


def judge_line(seen: dict | None) -> str:
    """What the judge is told about the goodbye (`mech["farewell"]`) — "" when the persona never said one. The
    goodbye never reaches the transcript (zaelar never heard it), so without this the judge cannot tell a round the
    persona LEFT from one zaelar finished; the line is in the judge's language, like the rest of its facts."""
    if not isinstance(seen, dict) or not seen.get("first"):
        return ""
    from .driver import is_closing
    first, second = str(seen.get("first") or "")[:200], str(seen.get("second") or "")[:200]
    if second and not is_closing(second):
        return (f"· El usuario empezó a despedirse en su turno {seen.get('turn')} («{first}») y, al releer lo que "
                f"quería, siguió con «{second}». Esa despedida NO le llegó a zaelar: no la juzgues.")
    return (f"· ⚠️ EL USUARIO SE DESPIDIÓ en su turno {seen.get('turn')} («{second or first}») y la ronda acabó "
            f"ahí. Lo que su encargo pedía y él NUNCA llegó a pedirle a zaelar no es un fallo del producto: "
            f"no lo puntúes como entrega a medias; juzga solo lo que sí se pidió.")
