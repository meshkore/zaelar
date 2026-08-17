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
        sys = (
            f"{_ANCHOR}\n\n## Lo que quieres conseguir\n{scenario.persona_brief}\n\n"
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
        self.history.append({"role": "assistant", "content": txt})
        # A closing line never ends in a question — still actively waiting for something if it just asked
        # one, no matter which other word it also contains (belt-and-suspenders on top of _CLOSING_RE).
        still_asking = "?" in txt or "¿" in txt
        if _CLOSING_RE.search(txt) and len(txt) < 200 and not still_asking:
            self.done = True
        return txt
