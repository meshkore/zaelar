"""CONTEXT PACKS — prompt that exists only during a PHASE, and then is archived (V2-675).

The operator's direction (2026-09-11): *«un sistema de prompts que podamos inyectar en ciertas fases o en
ciertos momentos o en ciertas situaciones… De momento solo tendrá esta parte inicial, pero me gusta que
montemos el sistema bien hecho dentro de la arquitectura»*, and, about the first pack: *«cuando ya hemos
terminado con eso, esos prompts iniciales desaparecen y ya pasamos a la fase normal»*.

**What this is NOT.** Three things already put text in the turn and none of them is this:

  · `_lang_lock` / `_flash_layer` — what the agent ALWAYS is and always has. Permanent, and cached as the
    stable prefix (V2-536), which is exactly why a phase block must never be written in there.
  · `_directive_block` — ONE style instruction the operator gave this session. A preference, not a phase.
  · `live_state()` — facts about this second (the clock, an open card, a running worker). True now and
    false in a minute; a pack is true for a STRETCH of the relationship.

A pack is the fourth thing: **a stretch of the relationship has its own instructions, and when the stretch
ends they are gone for good.** Today there is exactly one (the introduction). The registry exists so the
next ones — a trade, a country, an age, an interest the operator has told us about — are a file and a row,
not another special case grafted onto the prompt builder.

**Three rules the registry enforces, so a pack cannot become a permanent tax:**

  1. **A pack that is over is never composed again.** `active()` is asked on every turn; an archived pack
     answers False for good, and its text stops being paid for.
  2. **A pack costs nothing while inactive.** The check has to be a cheap local read (a settings flag, a
     memory slot) — never a model call, never network. It runs on the hot path of every single turn.
  3. **A pack never raises.** A broken pack is skipped with a warning; the turn goes out without it. The
     alternative is a phase of the relationship taking the conversation down with it.

Ordering is explicit (`order`) rather than registration order, and packs go into the prompt AFTER the
operator's own style directive: a directive is his instruction and a pack is ours, so his wins by being
read last.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from loguru import logger


@dataclass(frozen=True)
class Pack:
    """One phase's contribution to the prompt.

    `active` and `block` are callables and not values because a pack is re-judged EVERY turn — the phase can
    end mid-conversation (the introduction closes the moment the judge says it happened), and a pack whose
    text was computed once would keep being spoken after its own phase was over.
    """
    id: str
    title: str                      # human name, for observability and the state endpoint
    order: int                      # lower goes first; explicit so registration order cannot decide it
    active: Callable[[], bool]
    block: Callable[[], str]


_REGISTRY: list[Pack] = []


def register(pack: Pack) -> None:
    """Add a pack, replacing any earlier one with the same id (so a reload cannot double a block)."""
    global _REGISTRY
    _REGISTRY = sorted([p for p in _REGISTRY if p.id != pack.id] + [pack], key=lambda p: (p.order, p.id))


def registered() -> list[Pack]:
    return list(_REGISTRY)


def active_ids() -> list[str]:
    """Which packs would contribute to THIS turn. Used by observability and by lanes that must stand aside
    while a phase is running (the phrasebook does: during the introduction, «hola» is not small talk — it is
    the first move of a conversation that has somewhere to go)."""
    out = []
    for p in _REGISTRY:
        try:
            if p.active():
                out.append(p.id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"context_packs[{p.id}]: active() failed, treated as inactive: {e!r}")
    return out


def blocks() -> list[str]:
    """The text every active pack contributes, in order. Empty list is the normal steady state."""
    out: list[str] = []
    for p in _REGISTRY:
        try:
            if not p.active():
                continue
            text = (p.block() or "").strip()
            if text:
                out.append(text)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"context_packs[{p.id}]: skipped this turn: {e!r}")
    return out


def compose() -> str:
    """The whole contribution as ONE prompt section, or "" when no phase is running.

    The header is not decoration: without it the model reads a phase instruction as a permanent rule about
    who it is, which is the one thing a pack must never become."""
    try:
        parts = blocks()
    except Exception as e:  # noqa: BLE001 — the registry already catches per pack; this is the second net,
        logger.warning(f"context_packs: no phase context this turn: {e!r}")   # and it is on the hot path
        return ""
    if not parts:
        return ""
    return ("\n\n── CONTEXTO DE FASE (temporal: gobierna AHORA y desaparecerá solo; no es parte de quién "
            "eres) ──\n" + "\n\n".join(parts))


def state() -> dict:
    """What is running, for `/api/status` and the timeline. Cheap: the same reads `blocks()` makes."""
    act = set(active_ids())
    return {"packs": [{"id": p.id, "title": p.title, "active": p.id in act} for p in _REGISTRY]}


def _install() -> None:
    """Register the packs that ship. Explicit, never auto-discovery: a pack that appears in the prompt
    because a file was dropped in a folder is a prompt nobody decided to pay for."""
    try:
        from . import introduction
        introduction.install()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs: introduction pack not installed: {e!r}")


_install()
