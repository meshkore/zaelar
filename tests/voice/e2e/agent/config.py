"""Tester configuration — one place for every knob. Reads zaelar's root .env (for the dedicated tester key +
provider keys). The tester's providers are INDEPENDENT of zaelar's (it has its own voice + ears + brain)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ZAELAR_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(ZAELAR_ROOT / ".env")
# Tester credentials live gitignored under .meshkore/credentials/ (per operator, 2026-07-07).
load_dotenv(ZAELAR_ROOT / ".meshkore" / "credentials" / "tester.env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# --- zaelar under test ------------------------------------------------------------------------------------------
ZAELAR_URL = _env("TESTER_ZAELAR_URL", "http://localhost:43917")   # web server (token + SSE + chat)
TESTER_IDENTITY = _env("TESTER_IDENTITY", "tester")               # LiveKit participant identity

# --- MODEL ROUTING (operator directive 2026-07-07) --------------------------------------------------------------
# DRIVE (what the tester says to zaelar) → DeepSeek via AIMLAPI (cheap). JUDGE (competent evaluation/reasoning) →
# GLM via Z.AI when it has balance, else FALL BACK to DeepSeek. NEVER expensive AIMLAPI models (opus…) → burns balance.
AIMLAPI_BASE = _env("TESTER_AIMLAPI_BASE", "https://api.aimlapi.com/v1")
TESTER_KEY = _env("TESTER_AIMLAPI_KEY") or _env("AIMLAPI_KEY")     # dedicated tester key; falls back to zaelar's
DRIVE_MODEL = _env("TESTER_DRIVE_MODEL", "deepseek/deepseek-v4-flash")   # decides what the tester says (DeepSeek)

# Z.AI (GLM) — competent judge/reasoning. Key in .meshkore/credentials/tester.env (⚠ needs balance / recharge).
ZAI_KEY = _env("TESTER_ZAI_KEY")
ZAI_BASE = _env("TESTER_ZAI_BASE", "https://api.z.ai/api/anthropic")   # coding-plan endpoint (Anthropic-compatible)
ZAI_JUDGE_MODEL = _env("TESTER_ZAI_JUDGE_MODEL", "glm-4.6")        # glm-4.6/glm-5/glm-5.2 (see z.ai model list)
JUDGE_MODEL = _env("TESTER_JUDGE_MODEL", "deepseek/deepseek-v4-flash")   # DeepSeek fallback when GLM unavailable

# DeepSeek DIRECT — the operator's provider order (2026-08-19) puts the vendor's own endpoint FIRST and the
# AIMLAPI broker second, and on 2026-08-20 that order was worth three measured rounds: with Z.AI's weekly limit
# exhausted the judge fell to the broker, the broker answered 429/503/504, and `book-hotel-night-known__es` lost
# three complete eight-minute conversations to a missing verdict. The engine was reaching api.deepseek.com fine
# throughout the same runs, so the leg that was missing was the direct one.
# The MODEL NAME travels with the endpoint: the vendor takes `deepseek-v4-flash`, the broker `deepseek/…`.
def _engine_key(name: str) -> str:
    """One named key out of the engine's own credentials file, WITHOUT loading it into the environment.

    The tester already falls back to zaelar's AIMLAPI key when it has no dedicated one, so borrowing a provider
    key is the established shape here. Loading the whole file with `load_dotenv` is not: that env carries engine
    settings (a stale `MEM_PROCESSOR_MODEL` among them, which cost a day of 404s elsewhere) and pulling all of
    it into the tester process to get one value invites a confound nobody would look for.
    """
    path = ZAELAR_ROOT / ".meshkore" / "credentials" / "zaelar.env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


DEEPSEEK_KEY = _env("TESTER_DEEPSEEK_KEY") or _env("DEEPSEEK_API_KEY") or _engine_key("DEEPSEEK_API_KEY")
DEEPSEEK_BASE = _env("TESTER_DEEPSEEK_BASE", "https://api.deepseek.com")
# V2-338b — el relevo del juez usa el PRO, no el flash. Medido el 2026-08-26 juzgando en diferido la ronda del
# coche: el flash rompió el JSON del veredicto tres veces seguidas («Expecting ',' delimiter: line 8») y la
# ronda quedó INFRA con el relevo FUNCIONANDO. Un juez es salida estructurada larga — exactamente lo que
# distingue al pro del flash — y se le llama poco (una vez por ronda), así que el coste extra no pesa.
DEEPSEEK_JUDGE_MODEL = _env("TESTER_DEEPSEEK_JUDGE_MODEL", "deepseek-v4-pro")
# Prefer GLM for judging when a Z.AI key is present; the client falls back to DeepSeek on any Z.AI error (no balance).
JUDGE_PROVIDER = _env("TESTER_JUDGE_PROVIDER", "zai" if ZAI_KEY else "aimlapi")

# --- tester VOICE (what it speaks to zaelar) — cloud plugins, self-contained (no zaelar imports) ----------------
TESTER_TTS = _env("TESTER_TTS", "cartesia")                       # cartesia | deepgram
TESTER_TTS_VOICE = _env("TESTER_TTS_VOICE", "")                   # provider-specific voice id (empty = default)
# --- tester EARS (transcribe zaelar's replies) ------------------------------------------------------------------
TESTER_STT = _env("TESTER_STT", "deepgram")                       # deepgram
TESTER_LANG = _env("TESTER_LANG", "es")                           # zaelar es un asistente en CASTELLANO (default es)

# --- provider keys (read where the plugin expects them) ---------------------------------------------------------
CARTESIA_API_KEY = _env("CARTESIA_API_KEY")
DEEPGRAM_API_KEY = _env("DEEPGRAM_API_KEY")

# --- output -----------------------------------------------------------------------------------------------------
RUNS_DIR = ZAELAR_ROOT / "tests" / "runs" / "agent"
