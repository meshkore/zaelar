"""
Runtime settings — what the ⚙ config panel (server/config_api.py + frontend ConfigPanel.js) writes, so you can
swap STT/TTS/voice/language BY HAND instead of editing files. Defaults still come pre-set from the LiveKit engine
(voice/engine/core/config.py); this only stores explicit OVERRIDES.

How it applies:
- STT / TTS / voice / language → env vars the voice pipeline reads when a session STARTS. We update os.environ
  live + persist to config/settings.json (loaded at boot). Effect: RECONNECT the voice session to apply.

The BRAIN's model routing (fast layer + brain-worker CodeAgent) is NOT here — it lives in `config/v2.py` (its own
UI-managed store with a redacted public view, model POR INVOCACIÓN). This panel is only the voice knobs.

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
# SETTINGS is frozen at process import, so an STT/TTS/idioma change takes full effect on the next zaelar start;
# the env write is what the engine reads then. The TTS *voice* is handled apart (see below): it's an INDEX into
# the chosen provider's voice list (server.state["voice"], the lever the orb cycles), not a plain env var.
ENV_KEYS = {
    "stt_provider": "ZAELAR_STT",
    "tts_provider": "ZAELAR_TTS",
    "stt_language": "ZAELAR_LANGUAGE",
    # Perfil del motor de voz (V2-040): lo escribe `config/profiles.apply()` como parte del paquete coordinado, y
    # `load_into_env()` lo re-aplica en el arranque → el dataclass congelado (voice/engine/core/profile) lo lee.
    "zaelar_profile": "ZAELAR_PROFILE",
    # Gate de atención (V2-015): con el micro siempre abierto, decide qué turno va DIRIGIDO a zaelar. Se aplica
    # AL INSTANTE (voice/attention.py lee estas env cada turno) — no requiere reconectar.
    "attention_mode": "ZAELAR_ATTENTION",
    "attention_window": "ZAELAR_ATTENTION_WINDOW",
}

# Boolean knobs (not env-provider mapped): persisted in settings.json, default when absent. Read via get().
# `memory_observability` (V2-014): capa de tintado en vivo del visor de memoria (alta/sobrescritura/query).
# Default ON; se puede apagar desde la UI si añade tráfico fino no deseado. env fallback ZAELAR_MEM_OBSERVABILITY.
BOOL_DEFAULTS = {"memory_observability": True}


def get(key: str, default=None):
    """Lee un knob persistido (settings.json). Para knobs booleanos, cae al default declarado si no está."""
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
_TTS_LABELS = {"cartesia": "Cartesia Sonic (cloud)", "kokoro_local": "Kokoro local (privado · gratis)"}


def effective() -> dict:
    """Current values + option lists for the ⚙ UI. STT/TTS/voice options are DERIVED FROM THE LIVEKIT ENGINE
    (voice/engine): the STT/TTS registries for the provider lists, voice.engine.speech.voices for the catalog."""
    from voice.engine.core.config import SETTINGS
    from voice.engine.core.langs import supported as langs_supported
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
        knob("assistant_voice", "Voz · dentro del proveedor", vs[cur_idx]["voice"], voice_opts,
             "session", "elige la voz (se aplica al reconectar; también puedes rotarla tocando el orbe)"),
        knob("stt_language", "Idioma", os.getenv("ZAELAR_LANGUAGE", SETTINGS.language),
             [(s.native, s.code) for s in langs_supported()], "session",
             "multilingüe; al cambiar, STT, voz TTS y respuestas se re-alinean al idioma (aplica al reconectar)"),
        knob("attention_mode", "Atención · micro abierto", os.getenv("ZAELAR_ATTENTION", "always"),
             [("Inteligente (wake-word + conversación)", "smart"),
              ("Solo wake-word («zaelar»)", "wakeword"),
              ("Pulsar para hablar", "ptt"),
              ("Siempre activo (todo es orden)", "always")], "live",
             "smart = solo actúa si le hablas a zaelar («zaelar») o sigues una conversación; el resto lo ignora (ambiente)"),
        knob("attention_window", "Atención · ventana de conversación", os.getenv("ZAELAR_ATTENTION_WINDOW", "30"),
             [("15 s", "15"), ("30 s", "30"), ("60 s", "60"), ("120 s", "120")], "live",
             "segundos que sigue atendiendo sin repetir «zaelar» tras dirigirte a él (modo inteligente)"),
    ]
    return {"knobs": knobs, "free_text": [], "voices_by_provider": voices_by_provider}


def update(payload: dict) -> dict:
    """Validate + persist + apply. Returns {ok, applied, needs_reconnect, note}."""
    d = _read()
    applied, needs_reconnect = [], False
    for k, env in ENV_KEYS.items():
        if k in payload and str(payload[k]).strip():
            val = str(payload[k]).strip()
            d[k] = val
            os.environ[env] = val
            applied.append(k); needs_reconnect = True
    # Boolean knobs (aplican en caliente, sin reconectar): p.ej. memory_observability.
    for k in BOOL_DEFAULTS:
        if k in payload:
            d[k] = bool(payload[k]) if not isinstance(payload[k], str) else payload[k].strip().lower() not in ("0", "false", "no", "off", "")
            applied.append(k)
    # Language change → keep the VOICE aligned. ZAELAR_LANGUAGE was just set live above, so
    # voices_for("kokoro") already reflects the new language. If the operator didn't also pick a voice
    # and the persisted Kokoro voice isn't native to the new language, reset it to that language's
    # default — a Spanish voice must never end up in the English pipeline (Cartesia is multilingual, skip).
    if "stt_language" in applied and not str(payload.get("assistant_voice", "")).strip():
        try:
            from voice.engine.speech.voices import kokoro_default_voice, tts_provider, voices_for
            prov = str(payload.get("tts_provider", "")).strip().lower() or tts_provider()
            if prov in ("kokoro", "kokoro_local"):
                vs = voices_for("kokoro")
                if d.get("assistant_voice") not in {v["voice"] for v in vs}:
                    d["assistant_voice"] = kokoro_default_voice()
                    try:
                        from server import state as S
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
