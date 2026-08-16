"""Configuration for the use-case tester. Deliberately thin: credentials, provider endpoints and the JUDGE
model are already solved by the voice tester (tests/voice/e2e/agent/config.py + llm.py) and reused as-is —
duplicating key-loading/client code here would just be a second place for it to drift. The one thing this
suite genuinely needs different is the DRIVE model: these scenarios are open-ended negotiations (invent a
plausible city, notice when the conversation drifted, decide when the goal is done), not the fixed-goal
turn-taking voice's flash model is tuned for — so DRIVE defaults to the reasoning-capable tier.
"""
from __future__ import annotations

from tests.voice.e2e.agent import config as voice_config

ZAELAR_URL = voice_config.ZAELAR_URL
AIMLAPI_BASE = voice_config.AIMLAPI_BASE
TESTER_KEY = voice_config.TESTER_KEY
ZAI_KEY = voice_config.ZAI_KEY
ZAI_BASE = voice_config.ZAI_BASE
ZAI_JUDGE_MODEL = voice_config.ZAI_JUDGE_MODEL
JUDGE_MODEL = voice_config.JUDGE_MODEL
JUDGE_PROVIDER = voice_config.JUDGE_PROVIDER


def _env(name: str, default: str = "") -> str:
    import os
    return os.getenv(name, default).strip()


# Reasoning-capable tier, not voice's low-latency flash default — negotiating an open-ended request and
# noticing when it's gone off track needs real reasoning, and this suite runs far less often than every
# voice turn so the extra cost/latency per call is the right trade.
DRIVE_MODEL = _env("USE_CASES_DRIVE_MODEL", "deepseek/deepseek-v4-pro")
# The watchdog (mid-scenario off-track detector) can reuse DRIVE or run cheaper/faster — default same tier.
WATCHDOG_MODEL = _env("USE_CASES_WATCHDOG_MODEL", DRIVE_MODEL)

RUNS_DIR = voice_config.ZAELAR_ROOT / "tests" / "runs" / "use_cases"

# Loopback default: no ZAELAR_OBS_TOKEN needed when the tester runs on the same machine as the engine.
OBS_TOKEN = _env("ZAELAR_OBS_TOKEN", "")
