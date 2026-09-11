"""
Runtime settings — what the ⚙ config panel (server/config_api.py + frontend ConfigPanel.js) writes, so you can
swap STT/TTS/voice/language BY HAND instead of editing files. Defaults still come pre-set from the LiveKit engine
(voice/engine/core/config.py); this only stores explicit OVERRIDES.

How it applies:
- STT / TTS / voice / language → env vars the voice pipeline reads when a session STARTS. We update os.environ
  live + persist to config/settings.json (loaded at boot). Effect: RECONNECT the voice session to apply.

The BRAIN's model routing (fast layer + brain-worker CodeAgent) is NOT here — it lives in `config/v2.py` (its own
UI-managed store with a redacted public view, model PER INVOCATION). This panel is only the voice knobs.

Whitelisted on purpose: only these knobs are settable from the web. No secrets here (keys stay in the
credentials store / .env fallback).
"""
import json
import os
from pathlib import Path

from loguru import logger

from nucleo import workspace as _workspace

# `<workspace>/config/settings.json` — unset `ZAELAR_WORKSPACE` (self-host, today's behavior) is
# byte-identical to the old `Path(__file__).resolve().parent / "settings.json"`.
SETTINGS_FILE = _workspace.root() / "config" / "settings.json"

# knob -> env var it overrides (applied to os.environ at boot + on save). Since the LiveKit engine reads
# its config from ZAELAR_* env vars (voice/engine/core/config.py SETTINGS), the ⚙ writes THOSE names. NOTE:
# SETTINGS is frozen at process import, so an STT/TTS/language change takes full effect on the next zaelar start;
# the env write is what the engine reads then. The TTS *voice* is handled apart (see below): it's an INDEX into
# the chosen provider's voice list (server.state["voice"], the lever the orb cycles), not a plain env var.
ENV_KEYS = {
    "stt_provider": "ZAELAR_STT",
    "tts_provider": "ZAELAR_TTS",
    "stt_language": "ZAELAR_LANGUAGE",
    # Voice-engine profile (V2-040): written by `config/profiles.apply()` as part of the coordinated package, and
    # `load_into_env()` reapplies it on boot → the frozen dataclass (voice/engine/core/profile) reads it.
    "zaelar_profile": "ZAELAR_PROFILE",
    # Attention gate (V2-015): with the mic always open, decides which turn is ADDRESSED to zaelar. Applies
    # INSTANTLY (voice/attention.py reads these envs each turn) — no reconnect required.
    "attention_mode": "ZAELAR_ATTENTION",
    "attention_window": "ZAELAR_ATTENTION_WINDOW",
}

# Boolean knobs (not env-provider mapped): persisted in settings.json, default when absent. Read via get().
# `memory_observability` (V2-014): live tinting layer for the memory viewer (create/overwrite/query).
# Default ON; can be disabled from the UI if it adds unwanted fine-grained traffic. env fallback
# ZAELAR_MEM_OBSERVABILITY.
BOOL_DEFAULTS = {"memory_observability": True}


def get(key: str, default=None):
    """Read a persisted knob (settings.json). For boolean knobs, falls back to the declared default when absent."""
    d = _read()
    if key in d:
        return d[key]
    if key in BOOL_DEFAULTS:
        return BOOL_DEFAULTS[key]
    return default

# Valid engine provider names (mirror the voice/engine/speech/{stt,tts} registries — hardcoded so boot doesn't
# import the heavy LiveKit plugins just to validate). Used to reconcile Pipecat-era values persisted in
# settings.json: map legacy names where we can (kokoro → kokoro_local), drop unknown ones (auto/browser/deepgram-
# TTS…) so a stale ⚙ value can't poison the engine's ZAELAR_* env. The operator re-picks a valid one in the ⚙.
_ENGINE_STT = {"voxtral", "deepgram", "whisper_local"}
_ENGINE_TTS = {"cartesia", "elevenlabs", "kokoro_local"}   # elevenlabs = TTS cloud fiable (V2-035)
_LEGACY_TTS_ALIAS = {"kokoro": "kokoro_local"}   # old zaelar catalog name → engine name (preserve the choice)


def _read() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(d: dict):
    # The parent is created HERE and not only at boot (`nucleo/workspace.ensure`). A directory can be removed
    # while the process lives, and this write is best-effort at every call site: the caller logs a WARNING and
    # steps over it, so a missing parent costs the operator a preference that will not stick — measured on a
    # cloud Machine 2026-09-03, where `/data/config` never existed and the language onboarding therefore ran
    # again on EVERY cold boot. Cheap (`exist_ok`), and it makes the failure impossible rather than unlikely.
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def load_into_env():
    """Boot hook: apply persisted overrides to os.environ BEFORE the voice pipeline reads them."""
    d = _read()
    # Reconcile Pipecat-era persisted provider names with the LiveKit engine (INI-012): map legacy aliases,
    # drop values the engine can't build so they don't poison ZAELAR_STT/ZAELAR_TTS (would break STT/TTS).
    if d.get("tts_provider") in _LEGACY_TTS_ALIAS:
        d["tts_provider"] = _LEGACY_TTS_ALIAS[d["tts_provider"]]
    if d.get("tts_provider") and d["tts_provider"] not in _ENGINE_TTS:
        logger.warning(f"settings: TTS '{d['tts_provider']}' no existe en el motor LiveKit → ignorado "
                       f"(usa el default del motor); re-elige en ⚙")
        d.pop("tts_provider", None)
    if d.get("stt_provider") and d["stt_provider"] not in _ENGINE_STT:
        logger.warning(f"settings: STT '{d['stt_provider']}' no existe en el motor LiveKit → ignorado "
                       f"(usa el default del motor); re-elige en ⚙")
        d.pop("stt_provider", None)
    applied = []
    for k, env in ENV_KEYS.items():
        if d.get(k):
            os.environ[env] = str(d[k]); applied.append(k)
    av = d.get("assistant_voice")
    if av:   # restore the chosen voice as an INDEX into the current provider (the orb lever)
        try:
            from voice.engine.speech.voices import tts_provider, voices_for
            from server import state as S
            prov = tts_provider()
            vs = voices_for(prov)
            S.STATE["voice"] = next((i for i, v in enumerate(vs) if v["voice"] == av), 0)
            # The concrete voice id itself is read back by the engine TTS builders via
            # voice.engine.speech.voices.selected_voice() (from this same assistant_voice), so no env mirror.
        except Exception as e:
            logger.warning(f"settings: no pude restaurar el índice de voz ({e})")
        applied.append("assistant_voice")
    if applied:
        logger.info(f"settings: overrides aplicados desde settings.json → {applied}")


# Labels for the LiveKit engine's STT/TTS providers (engine names → human labels for the ⚙ dropdowns).
_STT_LABELS = {"voxtral": "Voxtral · Mistral (cloud)", "deepgram": "Deepgram Nova-3 (cloud)",
               "whisper_local": "Whisper local (privado · gratis)"}
_TTS_LABELS = {"cartesia": "Cartesia Sonic (cloud)", "kokoro_local": "Kokoro local (privado · gratis)",
               "elevenlabs": "ElevenLabs (cloud · voz nativa por idioma)"}


def _ui_languages() -> list[dict]:
    """The language rows the ⚙ offers. Falls back to the two shipped ones if the catalog cannot be read —
    a settings panel that renders an EMPTY language dropdown is worse than one with two entries."""
    try:
        from i18n.catalog import picker
        rows = picker()
        if rows:
            return rows
    except Exception as e:  # noqa: BLE001
        logger.warning(f"settings: no pude leer el catálogo de idiomas ({e})")
    return [{"code": "en", "native": "English", "flag": "🇺🇸"},
            {"code": "es", "native": "Español", "flag": "🇪🇸"}]


def effective() -> dict:
    """Current values + option lists for the ⚙ UI. STT/TTS/voice options are DERIVED FROM THE LIVEKIT ENGINE
    (voice/engine): the STT/TTS registries for the provider lists, voice.engine.speech.voices for the catalog."""
    from voice.engine.core.config import SETTINGS
    from voice.engine.speech.stt import available as stt_available
    from voice.engine.speech.tts import available as tts_available
    from voice.engine.speech.voices import tts_provider, voices_for

    stt_opts = [(_STT_LABELS.get(n, n), n) for n in stt_available()]
    tts_opts = [(_TTS_LABELS.get(n, n), n) for n in tts_available()]

    # Voice knob: options = the CURRENT provider's voices; value = whichever is active (server.state index, the
    # same one the orb cycles). voices_by_provider lets the front repopulate the list when the provider dropdown
    # changes — keyed by the ENGINE provider name so the dropdown value resolves directly.
    prov = tts_provider()
    vs = voices_for(prov)
    try:
        from server import state as S
        cur_idx = int(S.STATE.get("voice", 0)) % len(vs)
    except Exception:
        cur_idx = 0
    voice_opts = [(v["label"], v["voice"]) for v in vs]
    voices_by_provider = {n: [{"label": v["label"], "value": v["voice"]} for v in voices_for(n)]
                          for n in tts_available()}

    def knob(key, label, value, options, applies, note=""):
        return {"key": key, "label": label, "value": value,
                "options": [{"label": l, "value": v} for l, v in options], "applies": applies, "note": note}

    knobs = [
        knob("stt_provider", "STT · voz→texto", os.getenv("ZAELAR_STT", SETTINGS.stt_provider), stt_opts,
             "session", "STT server-side (LiveKit). Whisper local = gratis y privado."),
        knob("tts_provider", "TTS · texto→voz", os.getenv("ZAELAR_TTS", SETTINGS.tts_provider), tts_opts,
             "session", "Cartesia = cloud (multilingüe); Kokoro = local gratis."),
        knob("assistant_voice", "Voz · dentro del proveedor", vs[cur_idx]["voice"] if vs else "", voice_opts,
             "session", "elige la voz (se aplica al reconectar; también puedes rotarla tocando el orbe). "
                        "Con ElevenLabs y Kokoro la lista son voces NATIVAS de tu idioma primero"),
        # V2-672 — the SAME catalog the first-run picker offers (`i18n/catalog.py`, 40 languages), not
        # `langs.supported()`. Those are two answers to one question and they disagreed: onboarding could
        # lock German and the ⚙ could not switch back to it, because `langs` only lists the languages we
        # have a verified NATIVE Kokoro voice for — which is the right rule for THAT module and the wrong
        # list for this dropdown. `langs.spec()` falls back to English for the parts that genuinely need a
        # native voice, exactly as it already does for a language chosen at onboarding.
        knob("stt_language", "Idioma", os.getenv("ZAELAR_LANGUAGE", SETTINGS.language),
             [(f"{row['flag']} {row['native']}", row["code"]) for row in _ui_languages()], "session",
             "multilingüe; al cambiar, STT, voz TTS y respuestas se re-alinean al idioma (aplica al reconectar)"),
        knob("attention_mode", "Atención · micro abierto", os.getenv("ZAELAR_ATTENTION", "always"),
             [("Inteligente (wake-word + conversación)", "smart"),
              ("Solo wake-word («zaelar»)", "wakeword"),
              ("Pulsar para hablar", "ptt"),
              ("Siempre activo (todo es orden)", "always")], "live",
             "smart = solo actúa si le hablas a zaelar («zaelar») o sigues una conversación; el resto lo ignora (ambiente)"),
        # ⚠️ 5s is a HARD ceiling in smart mode (operator rule 2026-09-10: no pause over 5 seconds) — the
        # engine clamps whatever this knob says (voice/attention.py::window_s), so the options only shorten.
        knob("attention_window", "Atención · ventana de conversación", os.getenv("ZAELAR_ATTENTION_WINDOW", "5"),
             [("3 s", "3"), ("4 s", "4"), ("5 s (máximo)", "5")], "live",
             "segundos que sigue atendiendo sin repetir «zaelar» tras dirigirte a él (modo inteligente); "
             "tope duro de 5 s"),
    ]
    # Read-only, for the orb's 🤖 tooltip (2026-09-09): the wake-word IS the current spoken name (renamed via
    # voice, `nucleo/flash/identity_actions.py`), not the literal "zaelar" the tooltip used to hardcode.
    try:
        from memory import api as _mem
        assistant_name = (_mem.state().get("assistant_name") or "Zaelar").strip() or "Zaelar"
    except Exception:
        assistant_name = "Zaelar"
    return {"knobs": knobs, "free_text": [], "voices_by_provider": voices_by_provider, "theme": theme(),
            "wallpaper": wallpaper(), "assistant_name": assistant_name}


import re as _re

# Appearance (V2-617): the ⚙ Apariencia tab persists the design profile + custom knobs HERE so the choice
# belongs to the ACCOUNT (settings.json travels with a cloud Machine's Volume), not to one browser's
# localStorage. The backend stores and sanitizes; the CATALOG of valid profiles/fonts lives in the frontend
# (app/core/themes.js), which already falls back to the default on an id it does not know — so a slug is
# validated for SHAPE here, never against a mirrored list that would drift.
_SLUG_RE = _re.compile(r"^[a-z0-9_-]{1,32}$")
_HEX_RE = _re.compile(r"^#[0-9a-fA-F]{6}$")


def _sanitize_theme_custom(raw) -> dict:
    """Keep only the knobs the theme service understands, each shape-checked. Unknown keys and malformed
    values are DROPPED silently: this dict is echoed into inline CSS on every client, so it is the one
    place a stored value must never be able to carry anything but a color, a size step or a font id."""
    out = {}
    if not isinstance(raw, dict):
        return out
    if _HEX_RE.match(str(raw.get("accent") or "")):
        out["accent"] = str(raw["accent"])
    if str(raw.get("fs") or "") in ("s", "m", "l"):
        out["fs"] = str(raw["fs"])
    if _SLUG_RE.match(str(raw.get("font") or "")):
        out["font"] = str(raw["font"])
    return out


def theme() -> dict:
    """The persisted appearance choice, for /api/settings GET (the boot reconcile in services/theme.js)."""
    d = _read()
    return {"profile": d.get("theme_profile") or "", "custom": _sanitize_theme_custom(d.get("theme_custom"))}


def _sanitize_wallpaper(raw) -> dict:
    """The desktop wallpaper (V2-641) is a URL the client echoes into a CSS `url("…")` value, so this is a
    security seam exactly like `_sanitize_theme_custom`: only http(s), no quote/backslash/angle/whitespace
    characters that could break out of the quoted CSS string, bounded length. Anything malformed collapses
    to {} — which the client reads as "no wallpaper", never as a partially trusted value."""
    if not isinstance(raw, dict):
        return {}
    url = str(raw.get("url") or "").strip()
    if not (8 < len(url) <= 2000) or not url.startswith(("http://", "https://")):
        return {}
    if any(c in url for c in "\"'\\<>\n\r\t ") or any(ord(c) < 0x20 for c in url):
        return {}
    out = {"url": url}
    title = str(raw.get("title") or "").strip()[:120]
    if title:
        out["title"] = title
    return out


def wallpaper() -> dict:
    """The persisted desktop wallpaper, for /api/settings GET ({} = none)."""
    return _sanitize_wallpaper(_read().get("wallpaper"))


def update(payload: dict) -> dict:
    """Validate + persist + apply. Returns {ok, applied, needs_reconnect, note}."""
    d = _read()
    applied, needs_reconnect = [], False
    # Appearance (V2-617) — applies LIVE on the client, never needs a reconnect.
    if "theme_profile" in payload:
        prof = str(payload.get("theme_profile") or "").strip()
        if _SLUG_RE.match(prof):
            d["theme_profile"] = prof
            applied.append("theme_profile")
    if "theme_custom" in payload:
        d["theme_custom"] = _sanitize_theme_custom(payload.get("theme_custom"))
        applied.append("theme_custom")
    if "wallpaper" in payload:
        # None/{}/invalid all CLEAR it — «quita el fondo» must not need a second vocabulary.
        d["wallpaper"] = _sanitize_wallpaper(payload.get("wallpaper"))
        applied.append("wallpaper")
    for k, env in ENV_KEYS.items():
        if k in payload and str(payload[k]).strip():
            val = str(payload[k]).strip()
            changed = d.get(k) != val
            d[k] = val
            os.environ[env] = val
            applied.append(k); needs_reconnect = True
            # Attention-mode flips close the standing conversation window NOW (operator, 2026-09-10: the orb
            # must go grey within seconds of activating the wake-word mode, not ride out the previous mode's
            # window). Only on a real CHANGE — a bulk save re-sending the same mode must not wipe a live
            # window. This is the single seam every writer goes through (⚙, the 🤖 button, the voice directive).
            if k == "attention_mode" and changed:
                try:
                    from voice import attention
                    attention.on_mode_change(val)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"update: attention.on_mode_change failed ({e})")
    # Boolean knobs (apply live, without reconnecting): e.g. memory_observability.
    for k in BOOL_DEFAULTS:
        if k in payload:
            d[k] = bool(payload[k]) if not isinstance(payload[k], str) else payload[k].strip().lower() not in ("0", "false", "no", "off", "")
            applied.append(k)
    # Language change → keep the VOICE aligned. ZAELAR_LANGUAGE was just set live above, so the catalogs
    # below already reflect the new language. If the operator did not also pick a voice and the persisted
    # one is not native to the new language, it is reset to that language's default — a Spanish voice must
    # never end up in the English pipeline.
    #
    # V2-672: this covered KOKORO only, and ElevenLabs — the cloud TTS the canonical table names as the
    # titular — fell through it entirely. So a language change moved the STT, the UI and the replies while
    # the voice stayed whatever it was, which is the operator's own report. `default_voice_for` /
    # `voices_for` answer for whichever provider is live, so Cartesia (genuinely multilingual: one voice
    # speaks any language) correctly resolves to '' and nothing is realigned for it.
    if "stt_language" in applied and not str(payload.get("assistant_voice", "")).strip():
        try:
            from voice.engine.speech.voices import (default_voice_for, tts_provider, voice_is_aligned,
                                                     voices_for)
            prov = str(payload.get("tts_provider", "")).strip().lower() or tts_provider()
            lang = str(d.get("stt_language") or "").strip().lower()
            want = default_voice_for(prov, lang)
            if want and not voice_is_aligned(prov, str(d.get("assistant_voice") or ""), lang):
                d["assistant_voice"] = want
                try:
                    from server import state as S
                    vs = voices_for(prov, lang)
                    S.STATE["voice"] = next(
                        (i for i, v in enumerate(vs) if v["voice"] == d["assistant_voice"]), 0)
                except Exception:
                    pass
                applied.append("assistant_voice(realineada al idioma)")
        except Exception as e:
            logger.warning(f"update: no pude realinear la voz al idioma ({e})")

    # Voice: resolve the picked voice id → INDEX within the provider that will be effective (payload's
    # tts_provider wins, else the current one) and set it live in server.state — the orb lever. The persisted
    # assistant_voice is what the engine TTS builders read back via voices.selected_voice() on reconnect.
    av = str(payload.get("assistant_voice", "")).strip()
    if av:
        from voice.engine.speech.voices import tts_provider, voices_for
        prov = str(payload.get("tts_provider", "")).strip().lower() or tts_provider()
        vs = voices_for(prov)
        idx = next((i for i, v in enumerate(vs) if v["voice"] == av), 0)
        try:
            from server import state as S
            S.STATE["voice"] = idx
        except Exception as e:
            logger.warning(f"update: no pude fijar el índice de voz ({e})")
        d["assistant_voice"] = av
        applied.append("assistant_voice"); needs_reconnect = True
    if d:
        _write(d)
    note = "recarga la sesión de voz (Reconnect) para aplicar STT/TTS/voz/idioma" if needs_reconnect else "sin cambios"
    return {"ok": bool(applied), "applied": applied, "needs_reconnect": needs_reconnect, "note": note}


# ── FACTORY RESET: which knobs belong to the INSTALLATION and which to the AGENT (V2-670) ─────────────────
# The operator's test is «onboard a brand-new agent in another language, as if it were the first time». The
# blocker was measured 2026-09-11: `i18n.init.detect.should_detect()` — the gate that decides whether the
# first-run language ceremony fires at all — is True only while `stt_language` is EMPTY here, and this file
# sat in `reset-memory.sh`'s KEEP_ALWAYS list, untouched even with both checkboxes ticked. So every «clean»
# test still spoke Spanish with the voice already chosen, and the ceremony never ran.
#
# Deleting the file whole is the WRONG fix and that was measured too: the default profile is `remote`, whose
# defaults are Voxtral + Cartesia, so wiping it silently swaps which paid provider does STT/TTS. The
# ceremony is SPOKEN — a factory reset that changes the microphone stack is a test about the wrong thing.
#
# So the split is by OWNERSHIP, not by file: what the MACHINE is set up with survives, what the AGENT knows
# and what the operator PREFERRED does not. `tests/infrastructure` fails if a knob this module declares is
# in neither list — a new preference must not survive a factory reset by simply having been added later
# (the V2-548 class: a seed list that falls behind on its own, silently).

INSTALL_KEYS = frozenset({
    "stt_provider",       # which paid STT this machine uses — setup, not identity
    "tts_provider",       # idem for TTS
    "zaelar_profile",     # remote/local voice-engine profile
    "config_profile",     # the coordinated profile package (wizard V2-040)
    # V2-671 — was on the AGENT side, and that was the whole defect the operator hit. Dropping it made the
    # first-run wizard fire after a factory reset; the wizard applied a profile; and `profiles.apply()` writes
    # settings.json AND config/v2.json together — so the four keys above were faithfully preserved and then
    # overwritten twenty seconds later, along with the model routing the dialog promises never to touch. The
    # wizard no longer auto-opens at all (`server/wizard_api._first_run`), and this belongs here anyway: it
    # records something about the INSTALLATION, not about the agent's identity or the operator's taste.
    "wizard_done",
})

AGENT_KEYS = frozenset({
    "stt_language",       # THE onboarding gate — must be empty for the ceremony to fire
    "assistant_voice",    # the ceremony picks a native voice for the chosen language
    "assistant_name",     # a rename the operator gave it
    "attention_mode",     # his preference
    "attention_window",   # his preference
    "wallpaper",          # V2-641, his desktop photo
    "theme",              # V2-617 skin profile
    "theme_custom",       # V2-617 custom knobs
    "memory_observability",
})


def factory_reset() -> dict:
    """Strip settings.json down to what a FRESH INSTALL would have: the installation's own setup, nothing else.

    Returns `{"kept": [...], "dropped": [...]}`. Called by `scripts/reset-memory.sh --factory` (the Reset
    dialog's «empezar de cero» checkbox), never on the hot path. Unknown keys are DROPPED, because the
    promise of this button is «as if for the first time» and an unrecognised key is by definition not part of
    the installation setup we deliberately preserve — the ratchet is what stops that from being a surprise.
    """
    try:
        d = _read()
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    kept = {k: v for k, v in d.items() if k in INSTALL_KEYS}
    dropped = sorted(k for k in d if k not in INSTALL_KEYS)
    try:
        SETTINGS_FILE.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"factory_reset: no pude reescribir settings.json ({e})")
        return {"kept": [], "dropped": [], "error": str(e)}
    return {"kept": sorted(kept), "dropped": dropped}
