"""config/doctor.py — system capability DETECTOR (V2-040).

Evaluates the machine and installed software so the **first-run wizard** (and a headless deploy) know WHAT can be
used and what is missing: hardware (Apple Silicon/CUDA/RAM), local services (Ollama + its models), binaries
(`claude` CLI, `livekit-server`, Playwright Chromium), optional Python dependencies, and which **credentials** are
set (only the FACT, never the secret). Recommends a profile (`local` if Ollama + Apple Silicon are present;
otherwise `cloud`).

TWO mouths, one detector (operator decision 2026-07-15):
  - **CLI**:  `python -m config.doctor`  → writes the JSON report to `.meshkore/logs/system-report.json` and prints
    it readably. Usable during installation or on a headless/cloud boot.
  - **Web**:  the (local) server calls it live (`report(refresh=True)`) from the wizard — a "re-analyze" button.

Design: LIGHT and DEFENSIVE imports. Do not import heavy LiveKit plugins just to probe; every probe fails softly
(an undetected capability = `False`/`"unknown"`, never an exception that breaks boot).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
REPORT_PATH = _ROOT / ".meshkore" / "logs" / "system-report.json"

# Report format: bump the version when the schema changes so the web knows to reread.
SCHEMA = 2


# ── known credentials (presence only, never the value) ─────────────────────────────────────────────────────
# Catalog of keys the system understands, WHAT each enables, and which profile it is RELEVANT for. The web uses it
# to ask only for what the chosen profile lacks. `env` = variable(s) that provide it (the 1st non-empty one counts).
CREDENTIALS = [
    {"key": "aimlapi", "env": ["AIMLAPI_KEY", "FAST_API_KEY"], "enables": "FlashBrain en la nube (escalón de relevo del broker)",
     "profiles": ["cloud"]},
    {"key": "deepgram", "env": ["DEEPGRAM_API_KEY"], "enables": "STT/TTS Deepgram (nube)", "profiles": ["cloud"]},
    {"key": "mistral", "env": ["MISTRAL_API_KEY"], "enables": "STT Voxtral (Mistral, nube)", "profiles": ["cloud"]},
    {"key": "cartesia", "env": ["CARTESIA_API_KEY"], "enables": "TTS Cartesia Sonic (nube)", "profiles": ["cloud"]},
    {"key": "elevenlabs", "env": ["ELEVENLABS_API_KEY"], "enables": "TTS ElevenLabs (nube, fiable)",
     "profiles": ["cloud"]},
    {"key": "openai", "env": ["OPENAI_API_KEY"], "enables": "reranker/embeddings en la nube (opcional)",
     "profiles": ["cloud"]},
    {"key": "gemini", "env": ["GEMINI_API_KEY"], "enables": "FlashBrain Gemini (alternativa nube)",
     "profiles": []},
    {"key": "perplexity", "env": ["PERPLEXITY_API_KEY", "PPLX_API_KEY"], "enables": "búsqueda web con síntesis (mejor)",
     "profiles": []},
    {"key": "tavily", "env": ["TAVILY_API_KEY"], "enables": "búsqueda web (alternativa)", "profiles": []},
    {"key": "brave", "env": ["BRAVE_SEARCH_KEY", "BRAVE_API_KEY"], "enables": "búsqueda web (snippets)",
     "profiles": []},
    {"key": "spotify", "env": ["SPOTIFY_CLIENT_ID"], "enables": "música por voz (Spotify, V2-041)",
     "profiles": []},
]


def _key_present(spec: dict) -> bool:
    return any((os.getenv(e) or "").strip() for e in spec["env"])


def credentials() -> list[dict]:
    """REDACTED state for each known credential: `{key, enables, profiles, set: bool, env}`. `set` is only the FACT
    that a value exists — the secret NEVER leaves. Reads the env chain already loaded by `server/common.py`
    (credential store > .env > process)."""
    return [{"key": c["key"], "enables": c["enables"], "profiles": c["profiles"],
             "env": c["env"], "set": _key_present(c)} for c in CREDENTIALS]


# ── hardware ───────────────────────────────────────────────────────────────────────────────────────────────
def hardware() -> dict:
    """Available local acceleration. Reuses the voice-engine detector (`accel.detect`) and adds host type —
    container vs bare-metal — because cloud deploys (Linux/container) have NO Metal path."""
    hw: dict = {"platform": "unknown", "arch": "unknown", "apple_silicon": False,
                "metal": False, "cuda": False, "rocm": False, "ram_gb": None}
    try:
        from voice.engine.core import accel
        hw.update(accel.detect())
    except Exception:
        import platform
        hw["platform"] = platform.system()
        hw["arch"] = platform.machine()
    hw["container"] = _in_container()
    return hw


def _in_container() -> bool:
    try:
        if os.path.exists("/.dockerenv"):
            return True
        cg = Path("/proc/1/cgroup")
        if cg.exists() and any(m in cg.read_text() for m in ("docker", "kubepods", "containerd")):
            return True
    except Exception:
        pass
    return False


# ── Ollama (local service + models) ───────────────────────────────────────────────────────────────────────
def _ollama_url() -> str:
    base = (os.getenv("ZAELAR_EMBED_HOST") or os.getenv("OLLAMA_HOST")
            or os.getenv("ZAELAR_LOCAL_LLM_URL") or "http://localhost:11434").strip()
    # normalize a dangling `/v1` (the tags API lives at the root, not in the OpenAI shim)
    return base[:-3].rstrip("/") if base.endswith("/v1") else base.rstrip("/")


def ollama(timeout: float = 2.0) -> dict:
    """Is Ollama running? Which models are pulled? — used to know whether the `local` profile is viable safely."""
    url = _ollama_url()
    out = {"reachable": False, "url": url, "models": []}
    try:
        import urllib.request
        with urllib.request.urlopen(url + "/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode())
        out["reachable"] = True
        out["models"] = sorted({m.get("name") for m in (data.get("models") or []) if m.get("name")})
    except Exception:
        pass
    return out


def _has_ollama_model(models: list[str], want: str) -> bool:
    """Is `want` (e.g. 'qwen2.5:7b-instruct' or 'embeddinggemma') among the models? Matches by tag prefix (a
    `qwen2.5:7b-instruct` satisfies 'qwen2.5', and conversely a bare name matches any tag)."""
    w = (want or "").strip().lower()
    wbase = w.split(":")[0]
    for m in models:
        ml = m.lower()
        if ml == w or ml.split(":")[0] == wbase:
            return True
    return False


# ── binaries / tooling ──────────────────────────────────────────────────────────────────────────────────
def _find_claude() -> str | None:
    """Locate the `claude` CLI (Claude Code) the same way workers do (`nucleo/workers/claude_session`)."""
    env = (os.getenv("CLAUDE_BIN") or "").strip()
    if env and Path(env).exists():
        return env
    which = shutil.which("claude")
    if which:
        return which
    import glob
    for pat in (str(Path.home() / ".nvm/versions/node/*/bin/claude"),
                "/opt/homebrew/bin/claude", "/usr/local/bin/claude",
                str(Path.home() / ".local/bin/claude")):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def _playwright_chromium() -> bool:
    """Is the Playwright Chromium binary installed (not just the pip package)?"""
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: F401
    except Exception:
        return False
    # ~/.cache/ms-playwright/chromium-* (Linux/Mac) or %USERPROFILE%\AppData\Local\ms-playwright (Win)
    import glob
    roots = [Path.home() / ".cache" / "ms-playwright",
             Path.home() / "Library" / "Caches" / "ms-playwright",
             Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright" if os.getenv("LOCALAPPDATA") else None]
    for root in filter(None, roots):
        if glob.glob(str(root / "chromium-*")) or glob.glob(str(root / "chromium_headless_shell-*")):
            return True
    return False


def _pip_has(mod: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def tooling() -> dict:
    """Binarios y dependencias opcionales que habilitan capacidades locales."""
    return {
        "claude_cli": _find_claude(),                          # SlowBrain / widget generator (None = absent)
        "codex_cli": shutil.which(os.getenv("CODEX_BIN", "codex")),
        "livekit_server": shutil.which("livekit-server"),      # native media server (Docker fallback otherwise)
        "docker": shutil.which("docker"),
        "playwright_chromium": _playwright_chromium(),         # browser + free Google search
        "deps": {
            "mlx_whisper": _pip_has("mlx_whisper"),             # STT Metal (Apple Silicon)
            "mlx_audio": _pip_has("mlx_audio"),                # TTS Metal (Apple Silicon)
            "faster_whisper": _pip_has("faster_whisper"),      # STT CPU/CUDA universal
            "fastembed": _pip_has("fastembed"),                # local embeddings + reranker (fallback)
            "playwright": _pip_has("playwright"),
            "telethon": _pip_has("telethon"),                  # Telegram
            "sqlite_vec": _pip_has("sqlite_vec"),              # memory vector store
        },
    }


# ── current config (what is selected now) ─────────────────────────────────────────────────────────────────
def current_config() -> dict:
    """What the system has selected NOW (profile, brain, providers) — so the wizard can show the starting state and
    detect inconsistencies."""
    cfg: dict = {"profile": os.getenv("ZAELAR_PROFILE", "remote")}
    try:
        from config import v2
        cfg["brain"] = v2.active_brain()
        cfg["fast"] = {"provider": v2.get("fast").get("provider"), "model": v2.get("fast").get("model")}
        mem = v2.get("memory")
        cfg["memory"] = {"embed_provider": mem.get("embed_provider"), "rerank_provider": mem.get("rerank_provider"),
                         "mem_processor_model": mem.get("mem_processor_model")}
    except Exception:
        pass
    try:
        from config import settings
        cfg["stt"] = os.getenv("ZAELAR_STT") or settings.get("stt_provider")
        cfg["tts"] = os.getenv("ZAELAR_TTS") or settings.get("tts_provider")
        cfg["language"] = os.getenv("ZAELAR_LANGUAGE") or settings.get("stt_language")
    except Exception:
        pass
    return cfg


# ── profile recommendation ───────────────────────────────────────────────────────────────────────────────
def recommend(hw: dict, oll: dict, tool: dict) -> dict:
    """Suggested profile + why. `local` if there is real local muscle (Apple Silicon with Metal or CUDA) AND Ollama
    is running; otherwise `cloud` (the deploy target). Never decides for the user — only pre-selects."""
    local_hw = bool(hw.get("metal") or hw.get("cuda"))
    ollama_up = bool(oll.get("reachable"))
    if hw.get("container"):
        return {"profile": "cloud", "why": "entorno de contenedor — sin rutas de modelo local (Metal/Ollama)."}
    if local_hw and ollama_up:
        return {"profile": "local", "why": "hay aceleración local (Metal/CUDA) y Ollama está corriendo → voz y "
                                           "memoria en la máquina, sin coste ni red."}
    if local_hw and not ollama_up:
        return {"profile": "local", "why": "hay aceleración local pero Ollama no responde — arranca Ollama y baja "
                                           "los modelos para el perfil local (o usa cloud)."}
    return {"profile": "cloud", "why": "sin aceleración local detectada → proveedores en la nube (keys)."}


# ── full report ──────────────────────────────────────────────────────────────────────────────────────────
def build() -> dict:
    """Compose the FULL report (does not write to disk). All probes are fail-open."""
    hw = hardware()
    oll = ollama()
    tool = tooling()
    return {
        "schema": SCHEMA,
        "ts": int(time.time()),
        "hardware": hw,
        "ollama": oll,
        "tooling": tool,
        "credentials": credentials(),
        "current": current_config(),
        "recommend": recommend(hw, oll, tool),
    }


def write(report: dict | None = None, path: Path | None = None) -> Path:
    """Persist the report to `path` (default `.meshkore/logs/system-report.json`) so the web can read it. Atomic."""
    report = report or build()
    p = path or REPORT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    Path(tmp).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return p


def report(refresh: bool = False, max_age_s: int = 3600) -> dict:
    """Return the web report: disk copy if recent, or a new one (and persist it) if `refresh` or stale/missing. The
    web "re-analyze" button passes `refresh=True`."""
    if not refresh and REPORT_PATH.exists():
        try:
            data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == SCHEMA \
                    and (time.time() - int(data.get("ts", 0))) < max_age_s:
                return data
        except Exception:
            pass
    rep = build()
    try:
        write(rep)
    except Exception:
        pass
    return rep


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────────────
def _fmt(rep: dict) -> str:
    hw, oll, tool = rep["hardware"], rep["ollama"], rep["tooling"]
    rec = rep["recommend"]
    ok = lambda b: "✓" if b else "✗"  # noqa: E731
    lines = ["zaelar · informe del sistema", "─" * 44]
    lines.append(f"host        {hw.get('platform')}/{hw.get('arch')}"
                 f"{' · Apple Silicon' if hw.get('apple_silicon') else ''}"
                 f"{' · contenedor' if hw.get('container') else ''}"
                 f"  · RAM {hw.get('ram_gb') or '?'} GB")
    lines.append(f"aceleración  Metal {ok(hw.get('metal'))}  CUDA {ok(hw.get('cuda'))}  ROCm {ok(hw.get('rocm'))}")
    lines.append(f"Ollama       {ok(oll.get('reachable'))}  ({oll.get('url')})"
                 + (f"  · {len(oll.get('models', []))} modelos" if oll.get("reachable") else ""))
    if oll.get("models"):
        lines.append("             " + ", ".join(oll["models"][:12]))
    lines.append(f"claude CLI   {ok(bool(tool.get('claude_cli')))}"
                 f"   livekit-server {ok(bool(tool.get('livekit_server')))}"
                 f"   chromium {ok(tool.get('playwright_chromium'))}")
    deps = tool.get("deps", {})
    lines.append("deps         " + "  ".join(f"{k} {ok(v)}" for k, v in deps.items()))
    lines.append("credenciales " + "  ".join(f"{c['key']} {ok(c['set'])}" for c in rep["credentials"]))
    lines.append("─" * 44)
    lines.append(f"perfil sugerido → {rec['profile'].upper()}  ({rec['why']})")
    return "\n".join(lines)


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Detector de capacidades de zaelar (V2-040)")
    ap.add_argument("--json", action="store_true", help="imprime el informe JSON completo")
    ap.add_argument("--no-write", action="store_true", help="no persiste el informe a disco")
    args = ap.parse_args()
    rep = build()
    if not args.no_write:
        p = write(rep)
        if not args.json:
            print(f"(informe → {p})\n")
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else _fmt(rep))


if __name__ == "__main__":
    _main()
