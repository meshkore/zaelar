"""The DRIVE model — plays a real person making the scenario's request over text. Ported from the voice
tester's TesterBrain (tests/voice/e2e/agent/interlocutor/brain.py): a running history where zaelar's replies
become the next turn's context, so a clarifying question genuinely changes what gets said next — this is
not a scripted conversation.
"""
from __future__ import annotations

from . import config, llm

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
        lowered = txt.lower()
        # A real live run (cheapest-monitor, 2026-08-17) closed the conversation after only 2 turns on "Vale,
        # perfecto. ¿Ya tienes algo?" — a plain mid-conversation acknowledgment, not a goodbye, but "perfecto"
        # alone matched. A closing line NEVER ends in a question — the driver is still actively waiting for
        # something if it just asked one, no matter which word preceded it.
        closing_words = ("gracias", "perfecto", "genial, eso es", "vale, listo")
        still_asking = "?" in txt or "¿" in txt
        if any(w in lowered for w in closing_words) and len(txt) < 200 and not still_asking:
            self.done = True
        return txt
