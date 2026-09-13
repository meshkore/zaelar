"""connector_briefs.py — the live CONNECTOR facts a turn needs, lifted out of `prompt.py` (V2-685).

Extracted, not added to: `prompt.py` was 12 lines over its ceiling and carried 5 lazy connector imports, and
the architecture ratchet's whole point is that a growing file is paid by EXTRACTING a module rather than by
raising a number. The V2-675 precedent is `live_blocks.py`, carved out of the same file for the same reason.

The rule these blocks all share, and the reason they live together now: **a model cannot decline what is not
in its prompt** (V2-540). Each connector family here has been through the same measured failure — given the
verbs and no state, the model narrates the outcome it assumes, and the receipts are in the docstrings below:
messaging's «you have no important messages» over a closed widget, video's four claims and zero connections,
and Google's whole reason for existing.

What is NOT here is the decision of WHEN a block is worth its tokens — each branch keeps its own gate, and
they are deliberately different, because «is this capability available at all» and «what is its connection
state» are two questions that become relevant at different moments.
"""
from __future__ import annotations


def for_prompt(open_ids: set[str]) -> str:
    """Connector briefs for the FlashBrain turn—#6 contributor to prompt bloat (V2-027): they appeared in EVERY
    turn even when unused. Normal turns now omit them; only **messaging** gets one, and ONLY while its widget is
    OPEN (in front of the operator). **architect** and **cluster/meshkore** briefs are rare, operator-only tag
    protocols, so they stay out of the hot prompt: the cluster channel uses its own brief (`bridge.for_brain`,
    stateless), and code/project tasks use `escalate_to_slowbrain`. If voice→architect/cluster is wanted later,
    reactivate it here gated by work IN PROGRESS, not by being 'configured'. Best-effort."""
    try:
        _msg_on = False
        try:
            from connectors.whatsapp import service as _wa
            _msg_on = _msg_on or _wa.enabled()
        except Exception:
            pass
        try:
            from connectors.telegram import service as _tg
            _msg_on = _msg_on or _tg.enabled()
        except Exception:
            pass
        out = ""
        if _msg_on:
            from connectors.messaging import brief as _mb
            # OPEN widget → full brief (protocol + live list, visible to the operator). CLOSED but messaging
            # CONFIGURED → connection STATE only (concise, ~2 lines): FlashBrain then knows whether it can read and
            # does NOT HALLUCINATE "you have no messages" when disconnected or unchecked (the headless test found
            # that it invented "you have no important messages" while the widget was closed).
            out = _mb.for_brain() if "mensajeria" in open_ids else _mb._platform_states()
        # V2-603 — VIDEO ACCOUNTS. TWO different gates, because they answer two different questions:
        #
        #   · the capability does NOT EXIST yet (no OAuth client anywhere) → ALWAYS, card open or not.
        #   · the account's connection STATE → only while the card is open (the messaging cost rule).
        #
        # The always-on half was learned the hard way, live, minutes after F2 shipped: with the block gated on
        # the open card, «Conéctame mi cuenta de YouTube» still answered «Te abro YouTube para que vincules tu
        # cuenta, ahí te guía paso a paso» — offering a door that had just been sealed. A model cannot decline
        # what is not in its prompt (V2-540), and «is this capability available at all» is exactly the fact a
        # turn needs BEFORE any card is open, since the offer is what opens it. It costs ~70 tokens and only
        # while the connector is off; once a client exists this branch disappears entirely.
        try:
            from connectors.video import service as _vs
            if not _vs.available() or "youtube" in open_ids:
                vstate = _vs.brain_state()
                if vstate:
                    out = (out + "\n\n" + vstate) if out else vstate
        except Exception:
            pass
        # V2-685 — GOOGLE, the account behind five of these cards, and MEET, a verb the engine has never
        # had before today. Same gate shape as video above and for the same reason: the fact is only worth
        # the tokens when the turn could plausibly act on it. It is in, however, whenever Google is NOT
        # fully usable — that is precisely the state in which a model with the verbs and no facts invents
        # «Hecho.», which is what `connectors/google/brain.py` exists to stop.
        try:
            from connectors.google import brain as _gb
            if open_ids & {"agenda", "mensajeria", "fotos", "archivos", "youtube"} or not _gb.connected_services():
                gstate = _gb.brain_state()
                if gstate:
                    out = (out + "\n\n" + gstate) if out else gstate
        except Exception:
            pass
        return out
    except Exception:
        pass
    return ""
