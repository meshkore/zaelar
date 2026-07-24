"""config/doctor.py — DETECTOR de capacidades del sistema (V2-040).

Evalúa la máquina y el software instalado para que el **wizard de primer arranque** (y un deploy headless) sepan
QUÉ se puede usar y qué falta: hardware (Apple Silicon/CUDA/RAM), servicios locales (Ollama + sus modelos), binarios
(`claude` CLI, `livekit-server`, Chromium de Playwright), dependencias Python opcionales, y qué **credenciales** hay
puestas (solo el HECHO, nunca el secreto). Recomienda un perfil (`local` si hay Ollama + Apple Silicon; si no,
`cloud`).

DOS bocas, un solo detector (decisión del operador 2026-07-15):
  - **CLI**:  `python -m config.doctor`  → escribe el informe JSON a `.meshkore/logs/system-report.json` y lo
    imprime legible. Usable en la instalación o en un arranque headless/cloud.
  - **Web**:  el server (local) lo llama en caliente (`report(refresh=True)`) desde el wizard — un botón «re-analizar».

Diseño: import-LIGERO y DEFENSIVO. Nada de importar los plugins pesados de LiveKit solo para sondear; cada sonda
falla-blando (una capacidad no detectada = `False`/`"unknown"`, nunca una excepción que tumbe el arranque).
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

# Formato del informe: subir la versión cuando cambie el esquema para que la web sepa releer.
SCHEMA = 2


# ── credenciales conocidas (solo presencia, jamás el valor) ────────────────────────────────────────────────
# Catálogo de las keys que el sistema entiende, con QUÉ habilita cada una y en qué perfil es RELEVANTE. La web lo
# usa para pedir solo lo que falta del perfil elegido. `env` = variable(s) que la aportan (la 1ª no vacía cuenta).
CREDENTIALS = [
    {"key": "aimlapi", "env": ["AIMLAPI_KEY", "FAST_API_KEY"], "enables": "FlashBrain en la nube (Haiku/Grok)",
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
    """Estado (redactado) de cada credencial conocida: `{key, enables, profiles, set: bool, env}`. `set` es solo el
    HECHO de que hay valor — el secreto NUNCA sale. Lee la cadena de env que ya carga `server/common.py` (store de
    credenciales > .env > proceso)."""
    return [{"key": c["key"], "enables": c["enables"], "profiles": c["profiles"],
             "env": c["env"], "set": _key_present(c)} for c in CREDENTIALS]


# ── hardware ───────────────────────────────────────────────────────────────────────────────────────────────
def hardware() -> dict:
    """Aceleración local disponible. Reusa el detector del motor de voz (`accel.detect`) y añade el tipo de host —
    contenedor vs bare-metal — porque el deploy cloud (Linux/contenedor) NO tiene ninguna ruta Metal."""
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


# ── Ollama (servicio local + modelos) ────────────────────────────────────────────────────────────────────
def _ollama_url() -> str:
    base = (os.getenv("ZAELAR_EMBED_HOST") or os.getenv("OLLAMA_HOST")
            or os.getenv("ZAELAR_LOCAL_LLM_URL") or "http://localhost:11434").strip()
    # normaliza un `/v1` colgando (la API de tags vive en la raíz, no en el shim OpenAI)
    return base[:-3].rstrip("/") if base.endswith("/v1") else base.rstrip("/")


def ollama(timeout: float = 2.0) -> dict:
    """¿Corre Ollama? ¿qué modelos tiene pulled? — para saber si el perfil `local` es viable sin tirar nada."""
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
    """¿Está `want` (p.ej. 'qwen2.5:7b-instruct' o 'embeddinggemma') entre los modelos? Casa por prefijo de tag
    (un `qwen2.5:7b-instruct` cumple 'qwen2.5' y viceversa el nombre pelado casa cualquier tag)."""
    w = (want or "").strip().lower()
    wbase = w.split(":")[0]
    for m in models:
        ml = m.lower()
        if ml == w or ml.split(":")[0] == wbase:
            return True
    return False


# ── binarios / tooling ──────────────────────────────────────────────────────────────────────────────────
def _find_claude() -> str | None:
    """Localiza el `claude` CLI (Claude Code) igual que los workers (`nucleo/workers/claude_session`)."""
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
    """¿Está el binario de Chromium de Playwright instalado (no solo el paquete pip)?"""
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: F401
    except Exception:
        return False
    # ~/.cache/ms-playwright/chromium-* (Linux/Mac) o %USERPROFILE%\AppData\Local\ms-playwright (Win)
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
        "claude_cli": _find_claude(),                          # SlowBrain / generador de widgets (None = ausente)
        "codex_cli": shutil.which(os.getenv("CODEX_BIN", "codex")),
        "livekit_server": shutil.which("livekit-server"),      # media server nativo (si no, Docker fallback)
        "docker": shutil.which("docker"),
        "playwright_chromium": _playwright_chromium(),         # navegador + búsqueda Google gratis
        "deps": {
            "mlx_whisper": _pip_has("mlx_whisper"),             # STT Metal (Apple Silicon)
            "mlx_audio": _pip_has("mlx_audio"),                # TTS Metal (Apple Silicon)
            "faster_whisper": _pip_has("faster_whisper"),      # STT CPU/CUDA universal
            "fastembed": _pip_has("fastembed"),                # embeddings + reranker locales (fallback)
            "playwright": _pip_has("playwright"),
            "telethon": _pip_has("telethon"),                  # Telegram
            "sqlite_vec": _pip_has("sqlite_vec"),              # store vectorial de la memoria
        },
    }


# ── config actual (qué está seleccionado ahora) ──────────────────────────────────────────────────────────
def current_config() -> dict:
    """Lo que el sistema tiene seleccionado AHORA (perfil, cerebro, proveedores) — para que el wizard muestre el
    estado de partida y detecte incoherencias."""
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


# ── recomendación de perfil ───────────────────────────────────────────────────────────────────────────────
def recommend(hw: dict, oll: dict, tool: dict) -> dict:
    """Perfil sugerido + por qué. `local` si hay músculo local real (Apple Silicon con Metal o CUDA) Y Ollama
    corriendo; si no, `cloud` (el objetivo del deploy). Nunca decide por el usuario — solo pre-selecciona."""
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


# ── informe completo ─────────────────────────────────────────────────────────────────────────────────────
def build() -> dict:
    """Compone el informe COMPLETO (no escribe a disco). Todas las sondas son fail-open."""
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
    """Persiste el informe a `path` (default `.meshkore/logs/system-report.json`) para que la web lo lea. Atómico."""
    report = report or build()
    p = path or REPORT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    Path(tmp).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return p


def report(refresh: bool = False, max_age_s: int = 3600) -> dict:
    """Devuelve el informe para la web: el de disco si es reciente, o uno nuevo (y lo persiste) si `refresh` o si
    está viejo/ausente. El botón «re-analizar» de la web pasa `refresh=True`."""
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
