"""The two lab agents: one who lives in Spain, one who lives in the United States.

WHY TWO AND NOT ONE. Most of what this suite measures is an errand aimed at the real world — find a
plumber who can come today, get tickets for a play, book a table tonight — and every one of those
resolves against WHERE THE PERSON LIVES. One shared agent would have to be told the city in every
scenario (which stops measuring memory and starts measuring the prompt), and worse, the two silos would
fight over the same identity slot: `operator.location` is a supersede slot, so the last case to run wins
and every case after it searches the wrong country. Two agents, two databases, two ports, two identities
that never meet.

WHY THEY ARE PRE-SEEDED AND NOT TAUGHT. The seed is written DIRECTLY into the sandbox's database before
the engine ever boots, with explicit slots — not said to the agent over the probe channel. Saying it
would route through the memory CORAZÓN, which is an LLM call: slow, and (measured repeatedly this month)
the first thing to break when a provider is degraded. A profile that fails to land silently is worse than
no profile: the case still runs, still scores, and its failure looks like the agent's.

WHAT DOES **NOT** GO IN A PROFILE. Nothing about the errands. No favourite sites, no "in Madrid people
use X to find a plumber", no preferences that a scenario is about to ask for. That is the operator's
standing rule for this whole tree — harden the RESOURCES, leave the REASONING open — and a profile that
pre-loads the answer measures the seed, not the agent. What lives here is only who the person is and
where they are: the same handful of facts a real installation learns in its first conversation.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LabProfile:
    key: str                     # "es" | "us"
    port: int                    # FIXED. The operator bookmarks it; see stage.py on why it never drifts.
    language: str                # ZAELAR_LANGUAGE — the engine is monolingual per process (langs.py)
    title: str                   # what the operator sees in the terminal
    # The fixed `state` row (memory/state.py): read on EVERY prompt, no search, microseconds. This is the
    # layer that makes "búscame un fontanero" resolve to the right country without anyone saying a city.
    state: dict = field(default_factory=dict)
    # Durable pills, pinned, one per identity slot. The state row above is the fast path; these are what a
    # recall or a worker's dossier finds when the errand actually needs the fact in words.
    pills: tuple[tuple[str, str], ...] = ()   # (slot, text)

    def persona_ground(self) -> str:
        """Lo que el AGENTE ya sabe de esta persona, escrito para que lo lea el conductor del caso.

        Existe por un fallo MEDIDO el 2026-08-24 en `search-buy-guitar__es`. El agente resolvió «una guitarra
        cerca para probarla» a Madrid —que es EXACTAMENTE la función de este perfil, y está escrita en la
        cabecera de este fichero: «la capa que hace que "búscame un fontanero" resuelva al país correcto sin
        que nadie diga una ciudad»— y el conductor, que no sabía nada del perfil, lo leyó como un error y lo
        corrigió: «yo no he dicho que sea en Madrid». Es literalmente cierto (el USUARIO no lo dijo) y no
        viene al caso: lo sabía por memoria. El daño fue doble y el segundo es el caro:

          · cinco de los diez turnos de la ronda se fueron en una discusión fabricada, y
          · el agente se disculpó y ESCRIBIÓ la corrección: `operator.location` acabó diciendo «Marc no ha
            confirmado que viva en Madrid». La memoria se comparte entre los casos de una tanda, así que un
            caso destruyó el perfil sembrado para todos los que venían detrás.

        Se DERIVA de `state` en vez de escribirse a mano al lado, por la misma razón que el arnés lee la hoja
        por los ids que él mismo vio abrirse: dos copias de un mismo hecho se separan, y aquí separarse
        significa que el conductor vuelva a discutir con el perfil sin que falle nada.
        """
        loc = str((self.state or {}).get("location") or "").strip()
        name = str((self.state or {}).get("operator_name") or "").strip()
        if not (loc or name):
            return ""
        en = self.language.startswith("en")
        who = []
        if name:
            who.append(f"your name is {name}" if en else f"te llamas {name}")
        if loc:
            who.append(f"you live in {loc}" if en else f"vives en {loc}")
        if en:
            return ("## Who you are (and what your assistant already knows)\n"
                    f"You are a real person: {', and '.join(who)}. Your assistant has been with you a while "
                    "and ALREADY KNOWS THIS — you do not need to tell it.\n"
                    "So if it takes your name or your city as given, or searches near where you live without "
                    "you having said so in this conversation, **it is doing the right thing**: it remembers, "
                    "it is not guessing. Do NOT correct it, do not say \"I never said that\", and do not ask "
                    "it to ask you what it already knows. Correcting it there is correcting it for "
                    "remembering you.")
        return ("## Quién eres (y qué sabe ya tu asistente)\n"
                f"Eres una persona real: {', y '.join(who)}. Tu asistente lleva tiempo contigo y ESTO YA LO "
                "SABE — no hace falta que se lo digas.\n"
                "Por eso, si da por sabido tu nombre o tu ciudad, o busca cerca de donde vives sin que tú se "
                "lo hayas dicho en esta conversación, **está haciendo lo correcto**: lo recuerda, no se lo "
                "está inventando. NO lo corrijas, no le digas «yo no he dicho eso» y no le pidas que pregunte "
                "lo que ya sabe. Corregirle ahí es corregirle por acordarse de ti.")


ES = LabProfile(
    key="es",
    port=43921,
    language="es",
    title="agente ES — vive en Madrid",
    state={
        "operator_name": "Marc",
        "location": "Madrid, España",
        "language": "es",
        "treatment": "directo, sin narrar",
    },
    pills=(
        ("operator.name", "Se llama Marc."),
        ("operator.location", "Vive en Madrid, España."),
    ),
)

US = LabProfile(
    key="us",
    port=43922,
    language="en",
    title="agente US — lives in San Francisco",
    state={
        "operator_name": "Alex",
        "location": "San Francisco, California, USA",
        "language": "en",
        "treatment": "direct, no narration",
    },
    pills=(
        ("operator.name", "Their name is Alex."),
        ("operator.location", "They live in San Francisco, California."),
    ),
)

PROFILES: dict[str, LabProfile] = {p.key: p for p in (ES, US)}


def get(key: str) -> LabProfile:
    try:
        return PROFILES[key]
    except KeyError:
        raise SystemExit(f"no such lab agent: {key!r} (have: {', '.join(sorted(PROFILES))})") from None
