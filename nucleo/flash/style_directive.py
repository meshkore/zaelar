"""The set_style_directive handler, whole (V2-046 A1 + V2-633; extracted from the voice provider paying the
architecture ratchet). One directive does three things, in this order: identity actions get first refusal
(a rename / the attention-mode toggle ride the same tool); the STYLE FLAGS that govern the engine's own
mouths (fast-lane ack, never-mute backstops, lead-in filler — `nucleo/style_policy`) move synchronously, so
the rule governs the very NEXT turn; and the rule text persists as a USER RULE in the state (off-loop —
it rides compose_state §B into every prompt). Add-vs-retract is decided by a deterministic guard over the
operator's own sentence, never by the LLM.
"""
from __future__ import annotations

import asyncio

from loguru import logger


def handle(directive: str, text: str, brain, emit, spawn) -> bool:
    """Run the whole directive path. Returns True when identity_actions consumed the turn — the caller must
    stop there (the identity handler speaks and acts on its own)."""
    from nucleo.flash import identity_actions as _ident   # rename/attention-mode toggle
    if _ident.handle_voice(directive, emit, spawn):
        return True

    async def _persist_rule(d: str, removal: bool) -> None:
        try:
            from memory import api as _mem
            if removal:
                _, gone = await asyncio.to_thread(_mem.remove_user_rule, d)
                emit("brain", "🧬 user rule retirada" if gone else "🧬 user rule: sin match para retirar",
                     text=(gone or d)[:100], role="system")
            else:
                await asyncio.to_thread(_mem.add_user_rule, d)
                emit("brain", "🧬 user rule guardada (persiste)", text=d[:100], role="system")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"user rule no persistida (voz sigue): {e}")

    from nucleo import style_policy as _stylep
    from nucleo.flash import router as _router
    if _router.looks_like_rule_removal(text):
        brain._directive = ""            # the immediate layer drops the retired rule too
        try:
            released = _stylep.retract_directive(directive)
            if released:
                emit("brain", "🧬 flags de estilo liberados (vuelven al génesis)",
                     text=", ".join(released), role="system")
        except Exception:
            pass
        spawn(_persist_rule(directive, True), "user-rule")
    else:
        brain._directive = directive
        emit("brain", "🎯 directiva de estilo fijada", text=directive, role="system")
        try:
            flags = _stylep.apply_directive(directive)
            if flags:
                emit("brain", "🧬 flags de estilo aplicados (rigen ya)",
                     text=", ".join(f"{k}={v}" for k, v in flags.items()), role="system")
        except Exception:
            pass
        spawn(_persist_rule(directive, False), "user-rule")
    return False


def prompt_lines(mstate: dict) -> list[str]:
    """The runtime-mode lines the prompt's last layer appends — both teach or ride THIS module's tool.
    Wake-word: the attention mode is runtime config, so the line reflects its current state and tells the
    model the toggle is a set_style_directive call. Silent-orders (V2-633): while the style policy says a
    short order runs in silence, the MODEL's own mouth must match the gated engine mouths — the backstop no
    longer injects «Hecho.», and the model saying it itself would be the same noise."""
    lines: list[str] = []
    try:
        from config import settings as _cfg_att
        att_mode = str(_cfg_att.get("attention_mode") or "always")
        att_name = (mstate.get("assistant_name") or "Zaelar").strip() or "Zaelar"
        att_now = ("ACTIVADO (solo atiendes los turnos que dicen tu nombre, o los que siguen a uno reciente)"
                   if att_mode in ("smart", "wakeword") else "desactivado (escuchas siempre)")
        lines.append(
            f"MODO WAKE WORD — el modo en el que solo respondes cuando dicen tu palabra de activación, que ES "
            f"tu nombre («{att_name}»; nunca preguntes cuál es la palabra ni cómo se llama el operador: ambos "
            f"están en tu ESTADO). Ahora está {att_now}. Si el operador pide activarlo o desactivarlo («activa "
            f"el modo wake word», «escúchame/respóndeme solo cuando diga tu nombre», «vuelve a escucharme "
            f"siempre»), LLAMA a set_style_directive con esa orden tal cual — el sistema lo aplica al instante; "
            f"no pidas ningún dato más y nunca digas que está hecho sin haber llamado a la tool.")
        if att_mode in ("smart", "wakeword"):
            # V2-657 — the ASIDE exit. Measured at the 2026-09-10 dinner: «Acostaros» got «Buenas noches»,
            # «Luis, disfrutemos de las noticias» got a clarifying question — the model had no way to let a
            # turn PASS, so it answered room talk and every answer kept the conversation window alive.
            lines.append(
                "CONVERSACIÓN CON GENTE DELANTE — hay más personas en la sala y el micro lo oye todo. Si el "
                "turno va CLARAMENTE dirigido a otra persona (la nombra por su nombre, o es charla doméstica "
                "de la sala sin ninguna petición ni pregunta para ti), responde EXACTAMENTE con [[aparte]] y "
                "nada más: ni una palabra, ninguna tool. Nunca contestes a lo que no era para ti ni preguntes "
                "qué significaba. Ante la MÍNIMA duda de que sí te hablaba a ti, contesta con normalidad.")
    except Exception:
        pass
    try:
        from nucleo import style_policy as _stylep
        sl = _stylep.prompt_line()
        if sl:
            lines.append(sl)
    except Exception:
        pass
    return lines


async def handle_probe(d: str, text: str, sess, ingest: bool):
    """Probe-channel mirror (parallel impl — this module owns the tool in BOTH channels). Returns the
    identity action label when identity_actions consumed the directive, else None after moving the style
    flags and persisting the rule (both gated to real turns, like the provider)."""
    from nucleo.flash import identity_actions as _ident
    act = await _ident.handle_probe(d, ingest=ingest) if d else None
    if act or not d:
        return act
    from nucleo import style_policy as _stylep
    from nucleo.flash import router as _router
    if _router.looks_like_rule_removal(text):
        sess.directive = ""
        if ingest:
            try:
                from memory import api as _memapi
                _stylep.retract_directive(d)
                await asyncio.to_thread(_memapi.remove_user_rule, d)
            except Exception:
                pass
    else:
        sess.directive = d
        if ingest:
            try:
                from memory import api as _memapi
                _stylep.apply_directive(d)
                await asyncio.to_thread(_memapi.add_user_rule, d)
            except Exception:
                pass
    return None
