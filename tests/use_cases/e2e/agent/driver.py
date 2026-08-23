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
    r"\b(eso es todo|nada m[aá]s|hasta luego|adi[oó]s)\b|"  # explicit sign-off words
    # …and the SAME closings in English. Until 2026-08-23 this regex was Spanish-only while 60 of the 133
    # scenarios are the US locale, whose personas speak English — so a US driver could never end by saying
    # goodbye, burned its full turn budget every round by construction, and ate an efficiency penalty the ES
    # twin never faced. The market-twins guard (same signals, same turns) missed it because the bias lived in
    # the driver, not the scenario.
    r"(many\s+)?thanks[.!,]?\s*$|thank\s+you[.!,]?\s*$|"    # ends the message: "...thanks." / "thank you"
    r"\bperfect,?\s+thanks?\b|\bgreat,?\s+thanks?\b|"       # "perfect, thanks" / "great, thanks"
    # `take care(?!\s+of)`: "take care of the booking" is an ERRAND, not a goodbye.
    r"\b(that'?s\s+(all|everything)|nothing\s+else|good\s*bye|bye\s+for\s+now|see\s+you|take\s+care(?!\s+of))\b",
    re.I)

def _today_note(locale: str = "es") -> str:
    """The DRIVE model needs the calendar as badly as the judge did, and for the same reason.

    Measured on 2026-08-20 (`weekend-adventure-sports-bilbao__es`): the persona asked for "this weekend,
    Saturday 22 and Sunday 23 August", zaelar correctly resolved it to 22-23 August 2026 — and the driver
    rejected it twice, "nada de 2026… es de este año, el próximo", burning three turns. The judge then filed
    zaelar for date confusion. The agent was right and the tester was wrong, so the round measured nothing.

    The judge got its calendar this same morning for the mirror-image bug. Giving it to one side and not the
    other just moves which participant is confidently wrong about the date.

    In the persona's OWN language (see `_ANCHOR_EN`'s note): a US persona whose system prompt names the day
    as «miércoles» is being primed to answer in Spanish.
    """
    import datetime as _dt
    hoy = _dt.date.today()
    if (locale or "es") == "us":
        days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        return (f"## What day is TODAY (fact, not opinion)\n"
                f"Today is {days[hoy.weekday()]} {hoy.isoformat()}. The current year is {hoy.year}: a "
                f"{hoy.year} date is THIS year, never next year. When you say 'this weekend' or 'on "
                f"Saturday', count from today. If zaelar gives you a date consistent with this calendar, do "
                f"NOT correct it — correcting a correct date is the most expensive mistake you can make in "
                f"this test.")
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
# Face 1 — announcing a FIND. Shape signals (links, bullets, bold) miss this entirely: on 2026-08-20 the
# driver wrote plain prose — "He encontrado una opción que encaja: Hotel Silken Al-Andalus Palace, 560 €"
# — and the agent then agreed with a hotel the TESTER had invented. A round like that reads as the case
# finally delivering, which is the most expensive way this harness can be wrong.
_FLIP_FOUND = re.compile(
    r"\b(he\s+encontrado|he\s+mirado|he\s+buscado|encontré|te\s+propongo|te\s+paso|aquí\s+tienes|"
    r"i\s+found|here\s+are)\b", re.I)
# Face 2 — offering to ACT FOR the other party.
_FLIP_OFFERS = re.compile(
    r"(¿\s*te\s+lo\s+(dejo|reservo)|¿\s*quieres\s+que\s+(lo\s+)?(mire|busque|reserve|siga)|"
    r"te\s+lo\s+dejo\s+reservado|¿\s*(te\s+)?lo\s+reservo|shall\s+i\s+book)", re.I)
# Face 3 — TAKING OVER the errand: announcing the work and asking the other to wait. Same round, one turn
# later: "Entendido, voy a filtrar solo hoteles de 4 estrellas... Dame un momento." Nobody is the user
# there either, and it is the half the first two faces do not see.
_FLIP_TAKES_OVER = re.compile(r"\bvoy\s+a\s+(buscar|filtrar|mirar|revisar|comprobar|comparar|localizar)\b", re.I)
_FLIP_STANDBY = re.compile(r"(dame\s+un\s+momento|te\s+aviso|en\s+cuanto\s+(lo\s+)?tenga|te\s+digo\s+algo)", re.I)
# ...unless what they are going off to check is their OWN, which a real person does all the time.
_FLIP_OWN = re.compile(r"\b(mi|mis)\s+(calendario|agenda|fechas|correo|email|cuenta|banco|móvil|notas)\b", re.I)


def looks_like_the_assistant(txt: str) -> bool:
    """Is this line the ASSISTANT's job rather than the person's?

    Four readings, because the flip has more faces than the first version saw — and shape was the tidy
    one. Both prose faces were measured on 2026-08-20 in the SAME round, one turn apart, and neither
    tripped the shape guard:
    · SHAPE — a deliverable (links + bullets + bold in a long block).
    · FOUND + OFFERS — announcing a candidate and offering to book it for the other party.
    · TAKES OVER — announcing the search itself and asking the other to hold on.

    Announcing a find is not enough on its own (people do look things up themselves), and neither is
    going off to check something — as long as what they check is their OWN calendar, inbox or dates.
    """
    if _FLIP_OFFERS.search(txt) and _FLIP_FOUND.search(txt):
        return True
    if _FLIP_TAKES_OVER.search(txt) and _FLIP_STANDBY.search(txt) and not _FLIP_OWN.search(txt):
        return True
    if len(txt) < 200:      # a real chat message does not arrive with links AND bullets AND bold
        return False
    signals = 0
    if _FLIP_URL.search(txt):
        signals += 1
    if len(_FLIP_BULLETS.findall(txt)) >= 2:
        signals += 1
    if txt.count("**") >= 4:
        signals += 1
    if _FLIP_OFFERS.search(txt) or _FLIP_FOUND.search(txt):
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

# The SAME anchor in the persona's own language. Until 2026-08-23 the one Spanish anchor served all 133
# scenarios — including the 60 US ones, whose personas are written in English and talk to an agent living in
# San Francisco. A persona instructed in Spanish to close with «gracias» is being steered out of character on
# every turn, and its sign-off could then never match the (Spanish-only) closing regex either.
_ANCHOR_EN = (
    "FIXED IDENTITY — NEVER BREAK IT: you are a real PERSON texting your personal assistant 'zaelar' to ask "
    "for something. The 'user'-role turns in this history are what ZAELAR says TO YOU; you answer with what "
    "you would type back. You are the one ASKING, never the assistant. FORBIDDEN: introducing yourself as "
    "zaelar or as an assistant, offering to do things for the user, or speaking as if you were the system. "
    "Write like people actually text: no stage directions, no quotes, message-length sentences (not an essay)."
)


class Driver:
    def __init__(self, scenario) -> None:
        self.scenario = scenario
        self.turns = 0
        self.done = False
        self.role_flips = 0
        locale = getattr(scenario, "locale", "es") or "es"
        if locale == "us":
            sys = (
                f"{_ANCHOR_EN}\n\n{_today_note(locale)}\n\n## What you want\n{scenario.persona_brief}\n\n"
                "## When to stop\nOnce your request is CLEARLY resolved (or clearly failed after a few "
                "reasonable attempts), sign off short and natural — end your message with 'thanks' or say "
                "'that's all' — and never keep pushing on something already settled."
            )
        else:
            sys = (
                f"{_ANCHOR}\n\n{_today_note(locale)}\n\n## Lo que quieres conseguir\n{scenario.persona_brief}\n\n"
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
            if (getattr(self.scenario, "locale", "es") or "es") == "us":
                msgs.append({"role": "system", "content":
                             "You broke character: you just wrote the ASSISTANT's reply (links, prices, a "
                             "list of options). You are the PERSON asking. Write again, in one or two "
                             "sentences, what YOU would say to zaelar now."})
            else:
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
