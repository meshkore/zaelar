"""Conversational style policy (V2-633): who may SPEAK when a short order runs, and when a wait filler may
sound. Three engine mouths talk without the model — the fast lane's ack (V2-572), the provider's never-mute
backstops («Hecho.» / «Aquí lo tienes», V2-026), and the lead-in filler (V2-529) — and none of them consulted
any rule, so the operator's own directive («al recibir órdenes no responder nada») was obeyed by the model
and then overridden by the engine putting words in its mouth. Measured live (session 6c715232, 2026-09-09):
the rule was set and persisted at 16:40:41 and «Reproduce el vídeo» still produced «Déjame ver…» + «Hecho.».

Layering, exactly as the operator ordered it:
  1. GENESIS (`nucleo/genesis.json`, ships with the engine): the factory defaults every install starts from.
     Today: short orders run in SILENCE (the visible effect is the answer) and fillers are "smart" (never on
     a turn that is itself a short order — a thinking sound before «pausa» reads as incomprehension, V2-572).
  2. USER OVERRIDES (`<workspace>/config/style.json`): persisted the moment a style directive is understood
     (`apply_directive`, called from the set_style_directive handler in the same turn) and read per use with
     an mtime cache — so a rule given by voice or chat GOVERNS THE VERY NEXT TURN, and survives restarts.
     Removing the rule (`retract_directive`) deletes the override and the genesis default is back.

Scope: these flags gate the VOICE mouths only. The chat channel keeps its text acks — a written «Hecho.»
interrupts nobody, while an empty chat bubble looks broken; the probe (text-channel parity harness) is
untouched for the same reason.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path

_GENESIS_PATH = Path(__file__).resolve().parent / "genesis.json"

_FILLER_MODES = ("off", "smart", "on")

_cache: dict = {"path": None, "mtime": None, "data": {}, "at": 0.0}
_genesis_cache: dict | None = None


def _overrides_path() -> Path:
    from nucleo import workspace as _ws
    return _ws.root() / "config" / "style.json"


def _genesis() -> dict:
    global _genesis_cache
    if _genesis_cache is None:
        try:
            _genesis_cache = dict(json.loads(_GENESIS_PATH.read_text()).get("style") or {})
        except Exception:
            _genesis_cache = {}
    return dict(_genesis_cache)


def _overrides() -> dict:
    """Read the per-install overrides, mtime-cached (an os.stat per call, never a parse unless it changed)."""
    p = _overrides_path()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        if _cache["path"] == str(p):
            _cache.update(mtime=None, data={})
        return {}
    if _cache["path"] == str(p) and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        data = json.loads(p.read_text())
        data = data if isinstance(data, dict) else {}
    except Exception:
        data = {}
    _cache.update(path=str(p), mtime=mtime, data=data)
    return data


def _write_overrides(data: dict) -> None:
    p = _overrides_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, p)
    _cache.update(path=str(p), mtime=None)      # force re-read; the write must win instantly


def policy() -> dict:
    """genesis ⊕ overrides — the effective style flags."""
    eff = _genesis()
    for k, v in _overrides().items():
        if k in eff:
            eff[k] = v
    return eff


def confirm_short_actions() -> bool:
    """May a VOICE mouth speak a bare ack («Hecho.») after a short order ran with nothing else to say?"""
    return bool(policy().get("confirm_short_actions", False))


def filler_mode() -> str:
    m = str(policy().get("fillers", "smart")).lower()
    return m if m in _FILLER_MODES else "smart"


def filler_allowed(kind: str = "neutral") -> bool:
    """May the lead-in filler sound on a turn of this `filler_audio.filler_kind`? "smart" (genesis default)
    keeps it for thinking turns (questions, requests that take real work) and drops it on ACTION turns —
    the operator's literal complaint: «te digo reproduce esta canción y me dices vale, un segundo — me
    molestas»."""
    m = filler_mode()
    if m == "off":
        return False
    if m == "on":
        return True
    return kind != "action"


# ── Directive parsing: a spoken rule flips concrete flags, deterministically ─────────────────────────────
# The LLM already receives the rule TEXT (state.rules rides every prompt); this is for the mouths the model
# does not control. Coarse on purpose: only concepts we can match without understanding flip a flag.

def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())

_NEG_CONFIRM_RE = re.compile(
    r"\b(?:sin confirmar|no (?:me )?confirmes|no confirmar|no respond\w+ nada|no (?:me )?dig\w+ nada|"
    r"no dec\w+ nada|ejecuta\w* directamente|sin decir nada|sin comentar|no coment\w+ (?:nada|lo hecho)|"
    r"no repit\w+ lo hecho|menos verborrea|"
    r"no (?:verbal )?confirm\w*|without confirm\w*|don'?t confirm|no need to confirm|say nothing|"
    r"don'?t say anything|execute (?:it )?directly|stop confirming)\b")
_POS_CONFIRM_RE = re.compile(
    r"\b(?:confirmame\w*|quiero que (?:me )?confirmes|dime (?:ok|vale|hecho) cuando|avisame cuando (?:lo )?"
    r"hag\w+|vuelve a confirmar|confirm (?:my|the) (?:orders|commands)|tell me when (?:it'?s )?done|"
    r"confirm again|start confirming)\b")
_NEG_FILLER_RE = re.compile(
    r"\b(?:sin (?:muletillas|coletillas|rellenos?)|no (?:me )?dig\w+ (?:un segundo|un momento|espera)|"
    r"nada de (?:muletillas|coletillas|frases de espera|rellenos?)|quita (?:las muletillas|los rellenos)|"
    r"no (?:fillers?|filler words)|stop saying (?:one second|wait|just a (?:sec|moment)))\b")
_POS_FILLER_RE = re.compile(
    r"\b(?:con muletillas|puedes decir muletillas|vuelve a (?:las muletillas|los rellenos)|"
    r"avisa(?:me)? mientras piensas|fillers? (?:are )?(?:ok|fine)|bring back (?:the )?fillers?)\b")


def _flags_for(text: str) -> dict:
    """Which style flags this directive names, and their target values. {} when it names none."""
    n = _norm(text)
    flags: dict = {}
    if _NEG_CONFIRM_RE.search(n):
        flags["confirm_short_actions"] = False
    elif _POS_CONFIRM_RE.search(n):
        flags["confirm_short_actions"] = True
    if _NEG_FILLER_RE.search(n):
        flags["fillers"] = "off"
    elif _POS_FILLER_RE.search(n):
        flags["fillers"] = "on"
    return flags


def apply_directive(text: str) -> dict:
    """Persist the flags a directive names (instantly effective). Returns what changed ({} = the directive
    is prose the mouths cannot act on — the LLM still gets it as a rule, nothing is lost)."""
    flags = _flags_for(text)
    if not flags:
        return {}
    data = dict(_overrides())
    data.update(flags)
    data["_set_at"] = int(time.time())
    _write_overrides(data)
    return flags


# A retraction names the TOPIC, not a direction («olvida lo de confirmarme las órdenes») — so releasing an
# override matches by concept, not by the signed patterns above.
_CONFIRM_TOPIC_RE = re.compile(r"\bconfirm\w*|verborrea|responder nada|decir nada|repetir lo hecho\b")
_FILLER_TOPIC_RE = re.compile(r"\bmuletilla\w*|coletilla\w*|relleno\w*|frases? de espera|fillers?\b")


def retract_directive(text: str) -> dict:
    """Remove the overrides a retired rule had set — back to genesis. Returns the keys released."""
    n = _norm(text)
    keys = []
    if _CONFIRM_TOPIC_RE.search(n):
        keys.append("confirm_short_actions")
    if _FILLER_TOPIC_RE.search(n):
        keys.append("fillers")
    data = dict(_overrides())
    released = {k: data.pop(k) for k in keys if k in data}
    if released:
        _write_overrides(data)
    return released


def prompt_line() -> str:
    """One prompt line so the MODEL's own mouth matches the engine's: under silent-orders it must not say
    «Hecho.» itself (the backstops are gated, but the model's text is its own)."""
    if confirm_short_actions():
        return ""
    return ("ÓRDENES CORTAS EN SILENCIO: cuando ejecutas una orden directa con una tool (pausa, reproduce, "
            "volumen, abrir/cerrar un widget, siguiente canción…), NO digas nada — ni «hecho» ni «un "
            "segundo»: el efecto visible es la respuesta. Habla solo si algo falló, falta un dato, o el "
            "encargo es largo (di brevemente qué vas a hacer). Esta es una regla base; una regla del "
            "OPERADOR más específica manda sobre ella.")


def _reset_for_tests() -> None:
    global _genesis_cache
    _genesis_cache = None
    _cache.update(path=None, mtime=None, data={}, at=0.0)
