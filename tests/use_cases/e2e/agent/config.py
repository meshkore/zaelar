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


# Path to the sandbox engine's own DB, set by `run._sandbox_batch` once it is up. Empty against the operator's
# live engine — the harness reads a database it created, never theirs.
SANDBOX_DB = ""

_CODE_STAMP: dict | None = None


def code_stamp() -> dict:
    """WHICH CODE was measured: the engine's short HEAD sha plus the non-test files that were dirty at boot.

    A round is only comparable to another round if you know what was running in it, and this suite runs the
    WORKING TREE (the sandbox boots `python -m server` from `engine/`), not a checked-out commit. On 2026-08-20
    the fixing agent had to ask "did my 15:54 commit actually run in your 16:26 round, or did you reuse a server
    from before it?" — a question that took reading boot timestamps by hand to answer, and that every future
    round would raise again. Worse, a round measured while somebody is MID-EDIT measures a half-applied change
    and looks exactly like a round measured on a coherent tree.

    `tests/` is excluded from `dirty` on purpose: the harness editing itself does not change the engine under
    test, and counting it would make every round look dirty and the flag mean nothing. Fails soft to an empty
    stamp — not knowing the sha must never cost a measured round.
    """
    global _CODE_STAMP
    if _CODE_STAMP is not None:
        return _CODE_STAMP
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]

    def _git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=str(root), capture_output=True, text=True,
                              timeout=15).stdout.strip()

    try:
        sha = _git("rev-parse", "--short", "HEAD")
        # `l[2:].strip()`, not `l[3:]`: porcelain's two status columns are followed by a variable amount of
        # whitespace, and slicing a fixed 3 ate the first letter of every path ("ests/…"), which quietly broke
        # the `tests/` exclusion — every round would have been reported dirty.
        paths = [l[2:].strip() for l in _git("status", "--porcelain").splitlines()]
        dirty = sorted(p for p in paths if p and not p.startswith("tests/"))
        _CODE_STAMP = {"sha": sha, "n_dirty": len(dirty), "dirty": dirty[:12]}
    except Exception as e:
        _CODE_STAMP = {"sha": "", "n_dirty": 0, "dirty": [], "error": str(e)[:120]}
    return _CODE_STAMP


# Reasoning-capable tier, not voice's low-latency flash default — negotiating an open-ended request and
# noticing when it's gone off track needs real reasoning, and this suite runs far less often than every
# voice turn so the extra cost/latency per call is the right trade.
DRIVE_MODEL = _env("USE_CASES_DRIVE_MODEL", "deepseek/deepseek-v4-pro")
# The watchdog (mid-scenario off-track detector) can reuse DRIVE or run cheaper/faster — default same tier.
WATCHDOG_MODEL = _env("USE_CASES_WATCHDOG_MODEL", DRIVE_MODEL)

# ── Provider order (operator norm, 2026-08-19) ────────────────────────────────────────────────────────────
# DeepSeek V4 DIRECT from its own provider is the PRIMARY option; the AIMLAPI broker is the fallback; an
# OpenAI/Anthropic model is the last resort. Measured reasons this order is not arbitrary: direct is ~30%
# cheaper than the same model through the broker, and the broker ACCEPTS `thinking:disabled` while still
# reasoning (TTFT p50 4.24s vs 1.01s) — see the V2-097 entry in CLAUDE.md. The same day the broker also ran
# out of funds mid-loop, which is the other half of why a chain beats a single endpoint.
#
# The model NAME differs per endpoint and that is the trap: the broker namespaces it (`deepseek/deepseek-v4-pro`)
# and the native API does not (`deepseek-v4-pro`). Sending the broker's name to the direct endpoint gets a 400
# listing the accepted names — exactly how the workers' DeepSeek tier shipped broken (`model="sonnet"`), which
# nobody could see because a relay tier only runs once the titular is already down.
DEEPSEEK_BASE = _env("TESTER_DEEPSEEK_BASE", "https://api.deepseek.com")


def deepseek_key() -> str:
    """The direct DeepSeek credential. Store first, env as the power-user fallback (repo convention)."""
    k = _env("DEEPSEEK_API_KEY")
    if k:
        return k
    try:
        from config import credentials as _C
        return (_C.get("DEEPSEEK_API_KEY") or "").strip()
    except Exception:
        return ""


def native_model(model: str) -> str:
    """Broker name → native name (`deepseek/deepseek-v4-pro` → `deepseek-v4-pro`)."""
    return model.split("/", 1)[-1] if model else model


# Último escalón, solo si los DOS caminos de DeepSeek están inalcanzables: GLM por Z.AI. **Ningún modelo de
# OpenAI aquí** (norma del operador, 2026-08-19: «no quiero usar modelos de OpenAI»; la formulación inicial de
# la norma nombraba OpenAI/Anthropic como último recurso y se corrigió el mismo día). No hace falta ninguno: el
# escalón existe para que una corrida desatendida DEGRADE en vez de morir, y Z.AI ya está aquí con su
# credencial. Cuesta independencia —el JUEZ vive en ese proveedor— y por eso la ronda queda SELLADA como no
# comparable; ese coste es real, pero es el mismo que tendría cualquier tercer escalón y no mejora por ser de
# otro vendedor.
LAST_RESORT_MODEL = _env("USE_CASES_LAST_RESORT_MODEL", "")   # vacío = usa el escalón Z.AI, sin modelo propio

RUNS_DIR = voice_config.ZAELAR_ROOT / "tests" / "runs" / "use_cases"

# Loopback default: no ZAELAR_OBS_TOKEN needed when the tester runs on the same machine as the engine.
OBS_TOKEN = _env("ZAELAR_OBS_TOKEN", "")
