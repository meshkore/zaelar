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
# Per-MODE window, because the two modes err on opposite sides. `always` keeps 30s: within it nobody judges
# (V2-531 — the LLM judge went deaf mid-dialogue), and there is no wake word to recover with, so the window errs
# long. `smart` (wake word) closes on 12s of REAL silence (2026-09-09, session 49e13093): with 30s, a
# conversation the operator was having with a THIRD person kept re-entering the window turn after turn — each
# handled turn refreshed it, so it never died while anyone in the room spoke at least every 30s. His own
# expectation, verbatim: 10-15s without talking to zaelar should close it — and recovery there is cheap (say the
# name again). Pauses-to-think (1-3s) stay comfortably inside; zaelar's own speech no longer eats the window
# either (see `note_bot_speech`), so this measures actual conversational silence.
_DEFAULT_WINDOW_S = 30.0
_SMART_WINDOW_S = 12.0

# Wake word: "zaelar". Extendable via env (`ZAELAR_WAKEWORDS`, comma-separated) with phonetic variants that STT
# might confuse — the previous ones (harvey/arbi/jarbi…) were specific mishearings of "harbee" and no longer apply.
# They are searched for as a complete word in the normalized text (without accents).
_DEFAULT_WAKEWORDS = ("zaelar",)

# ── process state ───────────────────────────────────────────────────────────────────────────────────
_state = {"last_directed": 0.0, "ptt": False, "assistant_name": "", "bot_hold": False,
          "window_hint": 0.0,      # per-reply dynamic window (attention_window.hint); 0 = use the mode default
          "recent_directed": [],   # timestamps of recent directed turns → dialogue depth for the hint
          "spotted_at": 0.0,       # last instant wake-word spot (interim STT) — dedupe for the orb signal
          "ambient_tail": [],      # (ts, text) of recently-DISCARDED ambient turns — reclaimed by a wake word
          "typed_at": 0.0}         # V2-646: last TYPED (chat/paste) turn — a typed message is never ambient


def _norm(text: str) -> str:
    """Lowercase without accents (robust es/en STT comparison)."""
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def mode() -> str:
    m = (os.getenv("ZAELAR_ATTENTION") or _DEFAULT_MODE).strip().lower()
    return m if m in _VALID_MODES else _DEFAULT_MODE


def window_s() -> float:
    # smart: the window is DYNAMIC per reply (operator directive 2026-09-09, `voice/attention_window.py` —
    # 4-15s by what the exchange looks like); the env override stays the power-user escape hatch for both modes.
    dflt = (_state["window_hint"] or _SMART_WINDOW_S) if mode() == "smart" else _DEFAULT_WINDOW_S
    try:
        v = float((os.getenv("ZAELAR_ATTENTION_WINDOW") or "").strip() or dflt)
        return v if v > 0 else dflt
    except Exception:
        return dflt


def _wakewords() -> tuple[str, ...]:
    env = (os.getenv("ZAELAR_WAKEWORDS") or "").strip()
    if env:
        ws = tuple(_norm(w) for w in env.split(",") if w.strip())
        if ws:
            return ws
    # A renamed assistant's own name is ALSO a wake word (2026-09-09, session a9b3a813): the operator
    # renamed zaelar to "Johnny" mid-session, and every following "Johnny, …" turn was marked `ambient`
    # forever — this list was still hardcoded to "zaelar" and nothing had ever wired the rename to it. See
    # `set_assistant_name()` below for who calls in. Additive, never a replacement: "zaelar" keeps working
    # even after a rename (habit, or a stray "oye zaelar" from before it).
    custom = _norm(_state["assistant_name"])
    if custom and custom not in _DEFAULT_WAKEWORDS:
        return _DEFAULT_WAKEWORDS + (custom,)
    return _DEFAULT_WAKEWORDS


def set_assistant_name(name: str | None) -> None:
    """PROCESS-level cache of zaelar's current spoken name (renamed via voice — the rename guard in
    `nucleo/flash/router_guards.extract_name_change`, wired from both channels). Extends `_wakewords()` so a
    rename does not silently break `wakeword`/`smart` mode. Deliberately no DB access HERE — this module never
    touches memory (see the file docstring): the caller reads `state.assistant_name` and pushes it in, the
    same shape `note_directed()`/`set_ptt()` already use for other process-level facts. Called (a) immediately
    by the rename handler, session-layer, and (b) off-hot-path by `nucleo/flash/memory_cache` on every state
    refresh, so a reconnect or another surface renaming it (e.g. the ⚙ panel, if one is ever added) also reaches
    here without a code change."""
    _state["assistant_name"] = (name or "").strip()


def assistant_name() -> str:
    """The name pushed by `set_assistant_name()` — '' if never set (nothing to add beyond the default)."""
    return _state["assistant_name"]


def has_wakeword(text: str) -> bool:
    n = _norm(text)
    return any(re.search(r"\b" + re.escape(w) + r"\b", n) for w in _wakewords())


def strip_leading_wakeword(text: str) -> str:
    """The utterance with its LEADING vocative wake word removed («Johnny, pausa el vídeo» → «pausa el
    vídeo»), '' when there is nothing to strip or nothing left. The name is the ADDRESS, never part of the
    order — in wakeword/smart mode every command carries it, so the action map's exact whole-utterance
    lookup (V2-539) went dead on precisely the orders it exists for: measured 2026-09-09 (session 34386d8f),
    «Johnny pausa el vídeo» missed the verbatim «pausa el video» seed, fell to the model, and the model
    re-emitted its previous fullscreen (V2-635). Only the KNOWN wake words come off — courtesy prefixes stay
    forbidden (normalize.py doctrine: «por favor…» is another seed entry, not something a matcher may
    understand). Returns normalized text; fine for a lookup whose store normalizes the same way."""
    n = _norm(text).strip()
    for w in sorted(_wakewords(), key=len, reverse=True):
        m = re.match(r"^(?:oye\s+|hey\s+)?" + re.escape(w) + r"[\s,.!:;]+(?=\S)", n)
        if m:
            return n[m.end():].strip()
    return ""


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
    # smart: active conversation window. `bot_hold` covers a barge-in while zaelar is STILL TALKING inside an
    # open conversation — a long reply must not let the window die mid-sentence (see `note_bot_speech`).
    now = time.time() if now is None else now
    if _state["bot_hold"]:
        return Verdict(True, "active_window")
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
    now = time.time() if now is None else now
    _state["last_directed"] = now
    rd = [t for t in _state["recent_directed"] if now - t <= 90.0]
    rd.append(now)
    _state["recent_directed"] = rd[-10:]


def note_typed(now: float | None = None) -> None:
    """The operator TYPED this turn (chat/paste). Stamped by the text-packet handler in `pipeline/agent.py`,
    beside its `note_directed()`, because the two facts are different: `directed` says the turn is for us,
    `typed` says it CANNOT be ambient chatter — nobody sits down and types by accident. That distinction is
    what the mute backstop needs (V2-646): the exemptions that keep us silent over dragged-in noise must
    never apply to a sentence the operator wrote."""
    _state["typed_at"] = time.time() if now is None else now


def was_typed(within_s: float = 45.0, now: float | None = None) -> bool:
    """Was the turn being handled right now a TYPED one? Time-bounded so a chat message from minutes ago
    never re-classifies a later spoken turn."""
    now = time.time() if now is None else now
    ts = _state.get("typed_at") or 0.0
    return bool(ts) and (now - ts) <= within_s


def note_reply(text: str, now: float | None = None) -> None:
    """The reply that just finished sizes the window it re-anchors (operator directive 2026-09-09): a reply
    that asks, or an errand running for him, earns the long pause; a bare «Hecho.» to a one-shot order earns
    the short one. Deterministic — `voice/attention_window.hint()`; called from the assistant-transcript seam
    (pipeline/agent.py), so it needs nothing from the provider."""
    try:
        from voice import attention_window as _aw
        now = time.time() if now is None else now
        depth = len([t for t in _state["recent_directed"] if now - t <= 90.0])
        _state["window_hint"] = _aw.hint(text or "", dialogue_turns=depth)
    except Exception:
        _state["window_hint"] = 0.0


def note_bot_speech(speaking: bool, now: float | None = None) -> None:
    """Zaelar's OWN speech is conversation activity (2026-09-09, session 49e13093): the window used to be
    anchored only to the operator's last turn, so a reply longer than the window left the operator's next
    answer marked ambient — and conversely nothing distinguished 'zaelar just finished talking' from '30s of
    dead air'. While zaelar talks inside an OPEN window the window cannot expire (`bot_hold`), and when it
    finishes the window is re-anchored to that instant — so `window_s()` measures REAL silence after its last
    word. Never OPENS a window from nothing: the kickoff greeting and a proactive announcement deliberately do
    not grant hands-free attention (documented decision at the caller, nucleo.py) — only a window some directed
    turn already opened is held/extended."""
    now = time.time() if now is None else now
    if speaking:
        _state["bot_hold"] = (_state["bot_hold"] or
                              bool(_state["last_directed"]) and (now - _state["last_directed"]) <= window_s())
    elif _state["bot_hold"]:
        _state["bot_hold"] = False
        _state["last_directed"] = now


def note_wakeword_spotted(now: float | None = None) -> None:
    """INSTANT visual (operator 2026-09-09): the orb used to light 1-3s after the wake word — STT-final plus
    the whole turn gate sat in between. The INTERIM transcript stream already carries the words as they are
    heard, and `has_wakeword` is a regex — so the caller (pipeline/agent.py, interim branch) spots the word
    the moment it appears and this emits the SAME `ambient` event the frontend already lights on. Deduped
    (interims repeat per utterance); the real turn verdict is untouched — this is signal, never permission."""
    now = time.time() if now is None else now
    if now - _state["spotted_at"] < 3.0:
        return
    _state["spotted_at"] = now
    try:
        from voice.observer import emit
        emit("ambient", "👂 wake word oída (interim)",
             extra={"directed": True, "reason": "wakeword_interim", "window_s": window_s()})
    except Exception:
        pass


def note_ambient(text: str, now: float | None = None) -> None:
    """Remembers a just-DISCARDED ambient turn so a wake word seconds later can reclaim it (operator
    2026-09-09): «Ostras, para la música, Johnny» arrives as fragments, and the ones BEFORE the name were
    judged ambient and dropped — the model then saw only «Johnny» and the order was lost. Bounded: 4 entries."""
    t = (text or "").strip()
    if not t:
        return
    now = time.time() if now is None else now
    _state["ambient_tail"] = ([(ts, x) for ts, x in _state["ambient_tail"] if now - ts <= 12.0] + [(now, t)])[-4:]


def reclaim_ambient_tail(text: str, now: float | None = None, within_s: float = 10.0) -> str:
    """Glues the ambient speech of the last `within_s` seconds IN FRONT of a wake-word turn, and consumes it
    (a tail must not feed two turns). «para la música,» + «Johnny» → «para la música, Johnny»."""
    now = time.time() if now is None else now
    tail = [x for ts, x in _state["ambient_tail"] if now - ts <= within_s]
    _state["ambient_tail"] = []
    return (" ".join(tail) + " " + (text or "")).strip() if tail else (text or "")


def set_ptt(active: bool) -> None:
    """Push-to-talk state (set by the frontend through the `zaelar-ptt` data topic). Only counts in ptt mode."""
    _state["ptt"] = bool(active)


def reset() -> None:
    """Closes the window / clears PTT (new voice session or test)."""
    _state["last_directed"] = 0.0
    _state["ptt"] = False
    _state["bot_hold"] = False
    _state["window_hint"] = 0.0
    _state["recent_directed"] = []
    _state["spotted_at"] = 0.0
    _state["ambient_tail"] = []


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
# «completamente» is how the STT renders «pantalla completa» often enough to matter (measured live 2026-09-05,
# session 3050e623: «Cierra la pantalla completamente.» → the guard missed, close-ALL fired, and re-fired on
# every glued fragment of the chain — the operator's own next words were «te he dicho que cerraras la pantalla
# completa, no que cerraras el widget»). A false veto here just hands the turn to the model, which can still
# close; a miss destroys the whole canvas instantly, so the guard errs wide.
_FULLSCREEN_RE = re.compile(r"\bpantalla\s+completa(?:mente)?\b|\bfull\s*screen\b|\bfullscreen\b", re.I)


def mentions_fullscreen(text: str) -> bool:
    """True when the turn talks about «pantalla completa»/fullscreen — a SCREEN-STATE subject, not a close
    order. Consumed by the generic close BACKSTOPS (voice provider + probe mirror): a turn that mentions
    fullscreen next to a close verb is asking to leave that mode (or narrating it), and the backstop closing
    the whole widget there is the measured failure of 2026-09-05 — it closed `youtube` twice more while the
    operator was DESCRIBING the first close. One copy of the decision, read by both channels (V2-252)."""
    return bool(_FULLSCREEN_RE.search(_norm(text)))
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
