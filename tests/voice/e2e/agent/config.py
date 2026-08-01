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
