"""The DRIVE model — plays a real person making the scenario's request over text. Ported from the voice
tester's TesterBrain (tests/voice/e2e/agent/interlocutor/brain.py): a running history where zaelar's replies
become the next turn's context, so a clarifying question genuinely changes what gets said next — this is
not a scripted conversation.
"""
from __future__ import annotations

import re

from . import config, llm

# A live run (search-buy-used-car, 2026-08-17) ended after 3 turns on "Perfecto, quedo a la espera." — no
# question mark this time, so the earlier still_asking guard didn't catch it. "perfecto"/"gracias" alone are
# too common as plain mid-conversation acknowledgments in Spanish ("perfecto, dale", "vale, gracias por
# avisar") to mean a real goodbye. A genuine closing PAIRS one of them with an actual farewell — "gracias"
# at the very end of the line, or an explicit sign-off word — never just the word floating anywhere in an
# otherwise ordinary sentence. This is why the scenario's own system prompt already said "gracias' o
# 'perfecto' SEGUIDA de un cierre" — the code just hadn't matched that until now.
_CLOSING_RE = re.compile(
    r"(muchas\s+)?gracias[.!,]?\s*$|"                       # ends the message: "...gracias." / "muchas gracias"
    r"\bperfecto,?\s+(muchas\s+)?gracias\b|"                # "perfecto, gracias" / "perfecto, muchas gracias"
    r"\b(eso es todo|nada m[aá]s|hasta luego|adi[oó]s)\b",  # explicit sign-off words
    re.I)

def _today_note() -> str:
    """The DRIVE model needs the calendar as badly as the judge did, and for the same reason.

    Measured on 2026-08-20 (`weekend-adventure-sports-bilbao__es`): the persona asked for "this weekend,
    Saturday 22 and Sunday 23 August", zaelar correctly resolved it to 22-23 August 2026 — and the driver
    rejected it twice, "nada de 2026… es de este año, el próximo", burning three turns. The judge then filed
    zaelar for date confusion. The agent was right and the tester was wrong, so the round measured nothing.

    The judge got its calendar this same morning for the mirror-image bug. Giving it to one side and not the
    other just moves which participant is confidently wrong about the date.
    """
    import datetime as _dt
    hoy = _dt.date.today()
    dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    return (f"## Qué día es HOY (hecho, no opinión)\n"
            f"Hoy es {dias[hoy.weekday()]} {hoy.isoformat()}. El año en curso es {hoy.year}: una fecha de "
            f"{hoy.year} es de ESTE año, nunca del que viene. Cuando digas «este fin de semana» o «el "
            f"sábado», cuenta desde hoy. Si zaelar te da una fecha que cuadra con este calendario, NO la "
            f"corrijas — corregir una fecha correcta es el fallo más caro que puedes cometer en esta prueba.")


# Una respuesta con forma de ENTREGA (enlaces, viñetas, negritas, precios) no la escribe una persona
# pidiéndole algo a su asistente: la escribe el asistente. Es el disfraz que se le cae al DRIVE cuando se
# olvida de quién es, y medido el 2026-08-20 pasó: el turno del «tester» entregó la lista de opciones de surf
# y barranquismo con precios y URLs, y zaelar reaccionó con sensatez a un mensaje absurdo («el mensaje se te
# ha cortado, Marta»). Una ronda así no mide el producto, así que se detecta, se reintenta una vez, y si
# vuelve a pasar se marca la ronda como avería del arnés en vez de puntuarla.
_FLIP_URL = re.compile(r"https?://", re.I)
_FLIP_BULLETS = re.compile(r"^\s*[-*·]\s+\S", re.M)


def looks_like_the_assistant(txt: str) -> bool:
    """Does this line have the shape of a DELIVERABLE rather than a chat message?"""
    if len(txt) < 200:      # un mensaje de chat de verdad no llega aquí con enlaces Y viñetas Y negritas
        return False
    signals = 0
    if _FLIP_URL.search(txt):
        signals += 1
    if len(_FLIP_BULLETS.findall(txt)) >= 2:
        signals += 1
    if txt.count("**") >= 4:
        signals += 1
    return signals >= 2


_ANCHOR = (
    "IDENTIDAD FIJA — NO LA ROMPAS JAMÁS: eres una PERSONA real escribiéndole por texto a tu asistente "
    "personal 'zaelar' para pedirle algo. Los turnos con papel 'user' en este historial son lo que ZAELAR te "
    "dice A TI; tú respondes con lo que escribirías. Eres quien PIDE, nunca el asistente. PROHIBIDO: "
    "presentarte como zaelar o como un asistente, ofrecerte a hacer cosas por el usuario, o hablar como si "
    "tú fueras el sistema. Escribe como se escribe de forma natural por texto/chat: sin acotaciones, sin "
    "comillas, frases con la longitud que tendría un mensaje real (no un ensayo)."
)


class Driver:
    def __init__(self, scenario) -> None:
        self.scenario = scenario
        self.turns = 0
        self.done = False
        self.role_flips = 0
        sys = (
            f"{_ANCHOR}\n\n{_today_note()}\n\n## Lo que quieres conseguir\n{scenario.persona_brief}\n\n"
            "## Cuándo terminar\nCuando tu petición esté CLARAMENTE resuelta (o claramente fallada tras "
            "varios intentos razonables), despídete corto y natural incluyendo la palabra 'gracias' o "
            "'perfecto' seguida de un cierre — nunca sigas insistiendo sobre algo ya resuelto."
        )
        self.history: list[dict] = [{"role": "system", "content": sys}]

    def opening(self) -> str:
        self.turns += 1
        line = self.scenario.opening_line
        self.history.append({"role": "assistant", "content": line})
        return line

    def hears(self, zaelar_text: str) -> None:
        self.history.append({"role": "user", "content": zaelar_text or "(sin respuesta)"})

    def reply(self, *, nudge: str = "") -> str:
        """Next line. `nudge` (from the watchdog) is injected as a system aside when the conversation looks
        like it's drifted — e.g. correcting a wrong assumption zaelar made — without breaking the persona."""
        self.turns += 1
        msgs = list(self.history)
        if nudge:
            msgs.append({"role": "system", "content": f"Nota para tu próxima frase (no la reveles): {nudge}"})
        txt = llm.call(msgs, model=config.DRIVE_MODEL, temperature=0.7, max_tokens=200).strip()
        if looks_like_the_assistant(txt):
            # ONE retry with the identity said out loud again. Not silent: a flip that survives makes the
            # round an INFRA, because zaelar's reply to a nonsense turn says nothing about zaelar.
            self.role_flips += 1
            msgs.append({"role": "system", "content":
                         "Te has salido del papel: acabas de escribir la RESPUESTA del asistente (enlaces, "
                         "precios, una lista de opciones). Tú eres la PERSONA que pide. Escribe otra vez, "
                         "en una o dos frases, lo que TÚ le dirías a zaelar ahora."})
            txt = llm.call(msgs, model=config.DRIVE_MODEL, temperature=0.7, max_tokens=200).strip()
            if looks_like_the_assistant(txt):
                self.role_flips += 1
        self.history.append({"role": "assistant", "content": txt})
        # A closing line never ends in a question — still actively waiting for something if it just asked
        # one, no matter which other word it also contains (belt-and-suspenders on top of _CLOSING_RE).
        still_asking = "?" in txt or "¿" in txt
        if _CLOSING_RE.search(txt) and len(txt) < 200 and not still_asking:
            self.done = True
        return txt
