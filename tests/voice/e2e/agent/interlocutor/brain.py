"""The tester's 'user' brain — simulates a person talking to zaelar. Ported from the sim candidate: persona +
behaviors + phase rules, but driven by the tester LLM (DeepSeek via AIMLAPI) and framed as a zaelar USER (not an
interviewee). From this brain's POV, what IT says = 'assistant' turns; zaelar's replies = 'user' input."""
from __future__ import annotations

import os
import random

from .. import config, llm

HERE = os.path.dirname(os.path.abspath(__file__))

# Temperaments (seeded per run) so we don't overfit zaelar to one easy user.
BEHAVIORS = {
    "neutral":     {"ramble": 0.3, "desc": "friendly, says what's needed, natural pauses"},
    "rambler":     {"ramble": 0.8, "desc": "chatty, gives long-winded requests"},
    "terse":       {"ramble": 0.0, "desc": "very short, one line at a time"},
    "demanding":   {"ramble": 0.4, "desc": "asks for concrete actions, expects follow-through"},
}


class TesterBrain:
    def __init__(self, persona: str = "curious_user", behavior: str = "neutral", goal: str = ""):
        self.behavior = BEHAVIORS.get(behavior, BEHAVIORS["neutral"])
        self.behavior_name = behavior
        self.turns = 0
        # Speak zaelar's language so the test is coherent (zaelar's default is Spanish). config.TESTER_LANG controls it.
        lang = (getattr(config, "TESTER_LANG", "es") or "es").lower()
        lname = {"es": "castellano (español)", "en": "English"}.get(lang, lang)
        bye = "adiós" if lang == "es" else "bye"
        path = os.path.join(HERE, "personas", f"{persona}.md")
        persona_txt = open(path, encoding="utf-8").read() if os.path.exists(path) else (
            f"Eres una persona real hablando con tu asistente de voz personal, zaelar. Habla con naturalidad.")
        persona_name = "Ricart"   # the human user portrayed by the tester (real profile: Ricart, Soria, ES)
        # HARD role anchor (2026-07-07): the DRIVE model (qwen) was reversing the roles — since zaelar arrives with
        # the 'user' role and the tester's lines with the 'assistant' role, the model thought it was the ASSISTANT ("I
        # am zaelar, how can I help?", "would you like me to show a screen?"). That invalidates the test. This anchor
        # fixes it as the USER.
        anchor = (
            f"IDENTIDAD FIJA — NO LA ROMPAS JAMÁS: TÚ eres una PERSONA humana llamada {persona_name} que USA por voz "
            "al asistente 'zaelar'. En este diálogo, los turnos con papel 'user' son lo que ZAELAR (el asistente) te "
            "dice A TI; tú respondes como {you} con lo que dirías EN VOZ ALTA. Eres QUIEN PIDE y es ayudado, no al "
            "revés. PROHIBIDO ABSOLUTAMENTE: presentarte como 'zaelar' o como asistente; llamar 'zaelar' o 'Alex' al "
            "asistente; ofrecerte a mostrar/abrir pantallas o widgets; decir '¿en qué te ayudo?' o '¿quieres que "
            "muestre…?'. TÚ eres quien PIDE ver widgets, consultar la agenda, etc. Si dudas, haz una petición o "
            "pregunta propia de un usuario.\n\n"
        ).replace("{you}", persona_name)
        sys = (anchor + persona_txt + f"\n\n## IDIOMA (OBLIGATORIO)\nHabla SIEMPRE en {lname}. zaelar funciona en ese idioma; "
               "si le hablas en otro idioma el test no vale.\n"
               f"## Tu carácter hoy\n{self.behavior['desc']}.\n"
               f"Devuelve SOLO lo que dirías EN VOZ ALTA (sin acotaciones ni comillas). Habla natural en {lname}, "
               "varía la longitud como una persona real. NO repitas saludos ni muletillas turno tras turno.\n"
               "REGLA DE FASE: en el saludo, responde BREVE (1 línea) y di tu nombre; no sueltes toda la lista de "
               "tareas de golpe — ten una conversación de ida y vuelta.")
        if goal:
            sys += (f"\n\n## Tu objetivo esta sesión\n{goal}\nPersíguelo conversando a lo largo de los turnos; cuando "
                    f"esté claramente hecho (o claramente fallado), despídete corto y natural incluyendo la palabra '{bye}'.")
        self.history = [{"role": "system", "content": sys}]

    def hears(self, zaelar_text: str) -> None:
        self.history.append({"role": "user", "content": zaelar_text or "(silence)"})

    def reply(self) -> str:
        early = self.turns < 1
        self.turns += 1
        long = (not early) and random.random() < self.behavior["ramble"]
        hint = ("Give a fuller turn (2-3 sentences) with a concrete request." if long
                else "Keep it short, one or two sentences.")
        msgs = self.history + [{"role": "system", "content": hint}]
        txt = llm.call(msgs, model=config.DRIVE_MODEL, temperature=0.9,
                       max_tokens=220 if long else 90).strip()
        self.history.append({"role": "assistant", "content": txt})
        return txt
