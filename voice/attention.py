#
# attention.py — ATTENTION gate (zaelar v2 “Colmena”, V2-015 · T134/T135/T136).
#
# With the microphone ALWAYS open, zaelar heard EVERYTHING (an entire meeting) and ACTED on ambient speech: it hallucinated,
# opened widgets, and escalated tasks to the SlowBrain based on phrases that were not addressed to it. This gate decides whether a turn
# is DIRECTED at zaelar; if not, the turn is marked `ambient` and produces NO action or response.
#
# Modes (`ZAELAR_ATTENTION`, managed by the UI in config/settings.py; env = power-user fallback):
#   - `smart`    (default): directed if (a) there is a wake word ("zaelar" / "oye zaelar") or (b) it falls within an
#                           active conversation WINDOW (N s after the last directed turn).
#   - `wakeword` : always requires a wake word (no window).
#   - `ptt`      : push-to-talk — directed only while the frontend PTT signal is active (set_ptt()).
#   - `always`   : old behavior (every turn is directed). Still available; not the default.
#
# PROCESS-level state (zaelar = one live voice session): the conversation window + the PTT flag.
# Pure and cheap: `evaluate()` READS (does not mutate); the caller invokes `note_directed()` when it HANDLES a turn to
# open/refresh the window. `hard_interrupt()` (T136) detects a hard STOP (close/stop/mute) that is ALWAYS handled,
# bypassing the gate. `clamp_input()` (T135) bounds the turn while preserving the explicit command.
#
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass

from loguru import logger

# ── configuration (UI-managed; env = fallback) ──────────────────────────────────────────────────────────
_VALID_MODES = ("smart", "wakeword", "ptt", "always")
_DEFAULT_MODE = "always"   # robot OFF = always listens and responds; the UI toggle switches to wake-word
_DEFAULT_WINDOW_S = 30.0

# Wake word: "zaelar". Extendable via env (`ZAELAR_WAKEWORDS`, comma-separated) with phonetic variants that STT
# might confuse — the previous ones (harvey/arbi/jarbi…) were specific mishearings of "harbee" and no longer apply.
# They are searched for as a complete word in the normalized text (without accents).
_DEFAULT_WAKEWORDS = ("zaelar",)

# ── process state ───────────────────────────────────────────────────────────────────────────────────
_state = {"last_directed": 0.0, "ptt": False}


def _norm(text: str) -> str:
    """Lowercase without accents (robust es/en STT comparison)."""
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def mode() -> str:
    m = (os.getenv("ZAELAR_ATTENTION") or _DEFAULT_MODE).strip().lower()
    return m if m in _VALID_MODES else _DEFAULT_MODE


def window_s() -> float:
    try:
        v = float((os.getenv("ZAELAR_ATTENTION_WINDOW") or "").strip() or _DEFAULT_WINDOW_S)
        return v if v > 0 else _DEFAULT_WINDOW_S
    except Exception:
        return _DEFAULT_WINDOW_S


def _wakewords() -> tuple[str, ...]:
    env = (os.getenv("ZAELAR_WAKEWORDS") or "").strip()
    if env:
        ws = tuple(_norm(w) for w in env.split(",") if w.strip())
        if ws:
            return ws
    return _DEFAULT_WAKEWORDS


def has_wakeword(text: str) -> bool:
    n = _norm(text)
    return any(re.search(r"\b" + re.escape(w) + r"\b", n) for w in _wakewords())


@dataclass
class Verdict:
    directed: bool
    reason: str        # 'wakeword' | 'active_window' | 'always' | 'ptt' | 'ambient'


def evaluate(text: str, *, now: float | None = None) -> Verdict:
    """Is this turn DIRECTED at zaelar? PURE — does not mutate state (the caller invokes `note_directed()` if it handles it)."""
    m = mode()
    if m == "always":
        return Verdict(True, "always")
    if has_wakeword(text):
        return Verdict(True, "wakeword")
    if m == "wakeword":
        return Verdict(False, "ambient")
    if m == "ptt":
        return Verdict(True, "ptt") if _state["ptt"] else Verdict(False, "ambient")
    # smart: active conversation window
    now = time.time() if now is None else now
    if _state["last_directed"] and (now - _state["last_directed"]) <= window_s():
        return Verdict(True, "active_window")
    return Verdict(False, "ambient")


# ── CONTENT, not just mode (2026-08-16) ────────────────────────────────────────────────────────────────────
# `evaluate()` in `always` mode (the default: microphone ALWAYS open, WITHOUT a wake word — a permanent decision by the
# operator, not something to revert) is a no-op: EVERY turn is directed. With a real family in the room, this caused
# background noise ("Look wherever you want, but give me the go-ahead...", phrases involving "daughter") to run through the
# FULL turn — prompt, tool decision, and in one real case a `web_search` that took 3.3s and completed —
# before being discarded as superseded. Real cost, zero value.
#
# `evaluate_content()` is the version that DOES judge: it still does not require a wake word (that does not change), but in `always`
# it consults the fast model — the only signal left when there is no activation word is the NATURE of
# the phrase: question, concrete fact, continuation of an ongoing task = directed; unrelated conversation/noise = no —.
# `evaluate()` (synchronous, without network access) remains unchanged for callers that cannot afford a round trip (tests, probe,
# accumulator, agent.py's non-hot-path uses) — the REAL voice turn is its only caller.
# ⚠️ FRAMING measured 2026-09-01 (session 701fcc1b): the old prompt presented the phrase as loose audio plus a
# note of "what was being done" — and the judge returned {"directed": false} on «I told you that you have already
# opened it.» and «Are you listening to me?», 15/15 reproductions, because without the DIALOGUE frame a second-person
# sentence reads as two people in the room talking to each other. Presenting the assistant's own last utterance
# as "Zaelar acaba de decir …" flips those exact phrases to directed (3/3 each). The judge is still fallible —
# which is why `evaluate_content` no longer consults it at all inside an active conversation (see below) — but
# for the cold-start turns it does keep judging, this frame is the one that was measured to read replies-to-Zaelar
# as replies-to-Zaelar.
_DIRECTED_SYSTEM = (
    "Eres el filtro de atención de Zaelar, un asistente de voz con el MICRÓFONO SIEMPRE ABIERTO — no hay "
    "palabra de activación, así que además de a su operador oye conversación de fondo (familia, TV, terceros, "
    "llamadas) que NO va dirigida a él.\n\n"
    "Te doy lo último que dijo Zaelar (si habló) y la frase que se acaba de transcribir. Decide si la frase es "
    "el operador hablándole A ZAELAR: le contesta, le pregunta, le corrige, se queja de lo que Zaelar ha hecho "
    "o dicho, le da datos o le pide algo. Es AMBIENTE solo si claramente habla con OTRA persona o es ruido sin "
    "relación con la conversación con Zaelar.\n\n"
    "Ante la duda, marca DIRIGIDO — dejar sin atender al operador es peor que procesar un poco de ruido.\n\n"
    'Responde SOLO con JSON: {"directed": true} o {"directed": false}. Nada más.'
)


async def _default_directed_judge(text: str, context: str) -> bool | None:
    """True/False, or None if the judge failed (the caller fails open to directed=True). Off the hot path of the
    real turn thanks to `asyncio.to_thread` — same pattern as `segmenter.judge()`."""
    try:
        from nucleo import memllm
        # Dialogue frame, not an activity note — see the measurement above `_DIRECTED_SYSTEM`.
        user = (f"Zaelar acaba de decir: «{context}»\n\nEl micrófono ha oído: «{text}»" if context
                else f"El micrófono ha oído: «{text}»")
        raw = await asyncio.to_thread(
            memllm.chat_sync, "directed", _DIRECTED_SYSTEM, user,
            max_tokens=20, temperature=0.0, timeout=4.0,
        )
        return _parse_directed(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"attention._default_directed_judge: failed ({str(e)[:160]}) — fail-open to directed")
        return None


def _parse_directed(raw: str | None) -> bool | None:
    """Tolerant of a code fence (same problem as `segmenter._parse_judge`). None if it could not be read."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
    except Exception:
        return None
    v = d.get("directed")
    return bool(v) if isinstance(v, bool) else None


_directed_judge = _default_directed_judge


def set_directed_judge(fn) -> None:
    """Replaces the `evaluate_content()` judge in `always` mode. Signature: `async (text, context) -> bool | None`.
    Injectable for tests (avoids a real network call) and for an alternative judge if one is ever needed.
    `None` restores `_default_directed_judge`."""
    global _directed_judge
    _directed_judge = fn or _default_directed_judge


async def evaluate_content(text: str, *, context: str = "", now: float | None = None) -> Verdict:
    """Like `evaluate()`, but in `always` mode judges CONTENT instead of treating everything as directed — see the
    comment above. `smart`/`wakeword`/`ptt` do not change (their heuristic already discriminates without needing the network).

    INSIDE AN ACTIVE CONVERSATION, NOBODY JUDGES (2026-09-01, session 701fcc1b). `always` mode maintained the
    conversation window (`note_directed()` on every handled turn) and never consulted it: EVERY turn went to the
    LLM judge, including the operator's answer four seconds after Zaelar itself asked him a question. Measured
    live: the judge returned {"directed": false} on 8 consecutive directed turns — «I see you have already opened it»,
    «Are you listening to me?», «I told you that you have already opened it», «there are no messages in the list» — 15/15 on
    replay, and the agent went deaf mid-dialogue until the operator gave up. Third occurrence of this family
    (2026-08-16 noise-cost incident created the judge; 2026-08-17 filler-context dropped 4 follow-ups; today).
    A binary coin-flip must not sit between the operator and an agent that JUST spoke to him: within the window
    the turn is directed, full stop, and the judge only decides COLD turns — session start, or speech after
    `window_s()` of silence, which is exactly the "session sitting in a meeting" case it was built for. The
    known cost is honest: background noise within the window now runs a turn, and the module's own rule already
    chose that side — better to process some noise than to leave the operator unattended."""
    m = mode()
    if m != "always":
        return evaluate(text, now=now)
    if has_wakeword(text):
        return Verdict(True, "wakeword")   # free shortcut — no need to ask the model about the obvious
    t = (text or "").strip()
    if not t:
        return Verdict(False, "ambient")
    now = time.time() if now is None else now
    if _state["last_directed"] and (now - _state["last_directed"]) <= window_s():
        return Verdict(True, "active_window")
    try:
        directed = await _directed_judge(t, context)
    except Exception as e:  # noqa: BLE001 — fail-open here ALSO covers an injected judge (set_directed_judge)
        # if it blows up, not just the default: nothing replacing the judge may leave the agent mute.
        logger.warning(f"attention.evaluate_content: judge failed ({str(e)[:160]}) — fail-open to directed")
        directed = None
    if directed is None:
        return Verdict(True, "always")     # fail-open: a broken judge must never leave the agent mute
    return Verdict(directed, "always" if directed else "llm_ambient")


def note_directed(now: float | None = None) -> None:
    """Marks that a directed turn was HANDLED → opens/refreshes the active conversation window (smart mode)."""
    _state["last_directed"] = time.time() if now is None else now


def set_ptt(active: bool) -> None:
    """Push-to-talk state (set by the frontend through the `zaelar-ptt` data topic). Only counts in ptt mode."""
    _state["ptt"] = bool(active)


def reset() -> None:
    """Closes the window / clears PTT (new voice session or test)."""
    _state["last_directed"] = 0.0
    _state["ptt"] = False


# ── HARD interruption (T136): STOP always handled, BYPASSES the gate, DETERMINISTIC (does not depend on the LLM) ────
# ENCLITIC PRONOUN (fix 2026-08-12, REAL live failure): in Spanish, the imperative is ATTACHED to the pronoun —
# «close-it all», «stop-it all», «remove-them» — and `\bcierra\b` does NOT match «cierralo» (after 'cierra' come
# more word characters, so there is no boundary). Measured result (13:01:51): the operator said «Close it all
# and stop it all», the detector returned None, the command ENDED UP IN THE MODEL — which stalled on that turn — and nothing was closed.
# Exactly what this deterministic path exists to prevent: closing and stopping cannot depend on the LLM.
# This is not a phrase table: it is the MORPHOLOGY of the Spanish imperative (up to two pronouns: «devuélveMeLO»), so it
# covers any verb in the list and any that are added.
_ENCLITIC = r"(?:(?:me|te|se|nos|os|lo|la|le|los|las|les){1,2})?"
# Close EVERYTHING: closing verb + "everything/widgets" word. Short, language-agnostic (es/en).
_CLOSE_VERB_RE = re.compile(
    r"\b(?:cierra|cierre|cierr|quita|elimina|esconde|oculta|limpia|despeja)" + _ENCLITIC + r"\b"
    r"|\b(?:close|hide|clear)\b")
_ALL_RE = re.compile(
    r"\b(todo|todos|todas|all|widgets|tarjetas|ventanas|pantalla|escritorio|everything)\b")
# REAL BUG 2026-07-23 (new fullscreen feature): "exit fullscreen" (exit fullscreen for ONE
# widget) matched "close/remove the SCREEN" (closing verb + 'pantalla' from _ALL_RE) and triggered closing
# ALL widgets — "fullscreen"/"full screen" is a mode of ONE widget, not a synonym for "everything".
_FULLSCREEN_RE = re.compile(r"\bpantalla\s+completa\b|\bfull\s*screen\b", re.I)
# Unambiguous STOP (triggers even if the turn is long).
_STOP_HARD_RE = re.compile(
    r"\b(silencio|calla(?:te|os|d)?|basta|stop|shh+|quiet[oa]|detente|para\s+ya|para\s+de|parate|shut\s*up)\b"
    # An attached pronoun is NOT the preposition «para», so it is unambiguous AS A VERB — but that is not the
    # same as being unambiguous ABOUT WHAT. V2-393: only the REFLEXIVE/DATIVE («stop yourself», «stop», «stop me») refers
    # to zaelar; the 3rd-person ACCUSATIVE («stop it», «stop her») has a DIRECT OBJECT, meaning it refers to a THING — and a
    # barge-in has no object: it means silence. Measured in `watch-a-video-not-listen-to-it` (2026-08-27 14:04), which
# had passed 5/5 two hours earlier: «Stop it now, please» about a loaded video consumed the ENTIRE turn
# — the hard stop generates no response — and the backstop «Can you repeat that?» appeared. The tester repeated it with other
# words («Stop the video») and it worked on the first try: the command was clear, the guard was ours.
    r"|\b(?:para|pare|deten|detenga)(?:me|te|se|nos|os|le|les){1,2}\b"
    # …unless the object is EVERYTHING: «stop it all» is global, and there the object is not a specific thing.
    r"|\b(?:para|pare|deten|detenga)(?:lo|la|los|las)\s+(?:todo|toda|todos|todas)\b")
# Ambiguous STOP ("para"/"pare"/"espera" — also a preposition): only as a SHORT imperative (avoids "para la cena").
_STOP_SOFT_RE = re.compile(r"\b(para|pare|espera)\b")
# V2-584: a stop verb followed by DETERMINER + NOUN names a THING — «para el vídeo», «stop the video»,
# «para la música». That is an order ABOUT something, not a silence order, and swallowing it here is how a
# pause order stopped the SPEECH and left the video playing (measured live 2026-09-05, twice, with the
# operator's explicit complaint in the transcript). Structural, never a phrase table: the determiner is what
# separates «para el vídeo» (object) from «para ya» / «para por favor» (no object → still a barge-in stop).
# The pronoun forms («para eso», «páralo») deliberately stay OUT: a bare pronoun after a stop verb is how
# people silence an ongoing speech, and V2-038's worker-stop precedence already handles «para eso» over live
# workers one level up.
_STOP_OBJECT_RE = re.compile(
    r"\b(?:para|pare|espera|stop)\s+"
    r"(?:el|la|los|las|un|una|este|esta|ese|esa|mi|tu|su|the|this|that|my|your)\s+\w+")


def hard_interrupt(text: str) -> str | None:
    """Detects a hard STOP that is ALWAYS executed immediately (bypasses the attention gate):
      - 'close'  → close ALL widgets ("close the widgets / close everything").
      - 'stop'   → silence/stop (LiveKit's barge-in already cut the TTS; no new response is generated).
    Returns the type or None. The 'close' case was the real bug: it was buried in a huge turn and truncated.
    A stop verb that NAMES a thing («para el vídeo») is not a hard interrupt: the turn must run so the model
    (or the action map) can act on that thing — the barge-in upstream already silenced the voice either way."""
    n = _norm(text)
    if _CLOSE_VERB_RE.search(n) and _ALL_RE.search(n) and not _FULLSCREEN_RE.search(n):
        return "close"
    has_object = bool(_STOP_OBJECT_RE.search(n))
    if _STOP_HARD_RE.search(n) and not has_object:
        return "stop"
    if _STOP_SOFT_RE.search(n) and not has_object and len(n.split()) <= 4:
        return "stop"
    return None


# ── bounded turn end + command preservation (T135) ───────────────────────────────────────────────
# Explicit command clause (open/close/show/stop…), so a length-based truncation NEVER loses it.
_COMMAND_RE = re.compile(
    r"[^.!?\n]*\b(cierra|cierre|abre|abra|muestra|muestrame|ensena|ensename|pon|saca|sube|para|pare|stop|"
    r"silencio|calla|basta|close|open|show|hide|clear|quita|oculta|esconde|limpia|despeja)\b[^.!?\n]*")


def clamp_input(text: str, max_len: int) -> tuple[str, bool]:
    """Bounds the turn text to `max_len` chars while PRESERVING the explicit command (close/stop/show…): if the
    turn is long and contains a command, its clause is preserved (rather than blindly truncating the last N chars, which
    caused "close the widgets" to end up OUTSIDE the excerpt). Returns (text, truncated?)."""
    if max_len <= 0 or len(text) <= max_len:
        return text, False
    tail = text[-max_len:]
    cmds = [m.group(0).strip() for m in _COMMAND_RE.finditer(text)]
    cmd = cmds[-1] if cmds else ""      # the last command = the most recent thing the operator requested
    if cmd and cmd not in tail:
        keep = cmd[: max(0, max_len // 2)]
        room = max_len - len(keep) - 3   # " … "
        tail = keep + " … " + (tail[-room:] if room > 0 else "")
    return tail, True
