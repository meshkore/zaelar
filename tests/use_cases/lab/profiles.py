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
