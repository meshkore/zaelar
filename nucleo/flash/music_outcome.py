"""nucleo/flash/music_outcome.py — the turn words what the music act really did (V2-833 F3).

Measured 2026-11-01 on a hosted engine: the model said «te la pongo» and the engine then appended a canned line from
the connector — «No he dado con esa canción. ¿Me dices el artista…?» — ten times, while the real cause was ours (the
catalogue lookup came back empty without saying why) and Spotify was connected the whole time. Two contradicting
sentences per turn, and the operator blamed for our failure.

The mechanism: a failed music act hands its FACTS (what was asked, what was said, why it ended — unreachable · no
track · no source — what was looked up and by whom, and the options this install really has) to the same follow-up
pass that confirms or corrects first words (`follow_up_pass`): SKIP when what was said still holds, else one or two
spoken sentences in his language. Its instructions are language data (`music.outcome_*` in the voice pack). No
sentence is canned here, and none asks him for details unless the facts say the catalogue answered and found nothing.
"""
from __future__ import annotations

from loguru import logger


def _options(reason: str) -> list[str]:
    """The options this install really has for this outcome (keys of `music.outcome_options`)."""
    connectable = False
    try:
        from connectors.music import registry
        connectable = not any(getattr(p, "plays_elsewhere", False) for p in registry.available())
    except Exception as e:  # noqa: BLE001 — unknown: the account option is not offered
        logger.debug(f"music outcome: sources unreadable: {e!r}")
    if reason == "no_track":
        return ["more_words", "another"]
    return ["retry"] + (["connect"] if connectable else [])


def system(lang_lock: str, asked: str, said: str, res) -> str:
    """The pass's instructions, in his language, with this act's facts."""
    from i18n import langs
    w = langs.words("music", default={}) or {}
    reason = str(getattr(res, "reason", "") or "error")
    extra = getattr(res, "extra", None) or {}
    labels, opts = w.get("outcome_labels") or {}, w.get("outcome_options") or {}
    facts = [str((w.get("outcome_reasons") or {}).get(reason) or reason)]
    if extra.get("tried") or extra.get("looked_up"):
        facts.append(f"{labels.get('tried', 'looked up')}: «{extra.get('tried') or extra.get('looked_up')}»")
    if extra.get("identified_by"):
        facts.append(f"{labels.get('identified_by', 'named by')}: {extra['identified_by']}")
    facts.append(f"{labels.get('options', 'options')}: " + "; ".join(str(opts.get(k, k)) for k in _options(reason)))
    body = str(w.get("outcome_pass") or "").format(asked=asked, said=said or "—", facts=" · ".join(facts))
    return f"{(lang_lock or '').rstrip()}\n{body}".strip()


async def say(*, lang_lock: str, asked: str, said: str, res, spec, emit, send, speech) -> str:
    """Word the failed act. With words already out, the pass runs DETACHED (SKIP keeps them, else a follow-up); with
    none (or on the typed channel), it is the turn's answer, said now. Returns what was sent here ("" if detached)."""
    from nucleo.flash import follow_up_pass
    sys2 = system(lang_lock, asked, said, res)
    emit("brain", "🎵 music outcome → the turn words it", role="system", text=str(getattr(res, "reason", ""))[:40],
         extra={"cat": "flash", "reason": getattr(res, "reason", ""), "provider": getattr(res, "provider", "")})
    if follow_up_pass.detach(sys2, asked, said, spec, 160, "music outcome", emit):
        return ""
    from nucleo.llm.fast_client import FastClient
    out = "".join([d async for d in follow_up_pass.measured(FastClient(), sys2, asked, spec, 160, "music outcome")])
    text = speech.sanitize(out, drop_metadata=False).strip()
    if not text or text.upper().startswith("SKIP"):
        return ""
    send((" " if said and not said[-1:].isspace() else "") + text)
    return text
