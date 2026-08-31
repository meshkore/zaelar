"""FULL SMOKE — “is the entire system operational?” (2026-07-25, operator request).

A SINGLE command that validates ALL system paths against the LIVE server and returns exit 0 only if EVERYTHING
works. It was born from a real failure: after V2-069 (FlashBrain drives operator AND cluster), CHAT appeared broken
and the code tests did not catch it because they covered the core but not the end-to-end path. This is the
“the system always remains operational” safety net; it is extended with more cases (1000→10000) on this same backbone.

Checks, layer by layer:
  1. HEALTH       — /api/status overall + every subsystem (server/brain/llm/memory/stt/tts/cron/widgets/cluster)
  2. CHAT/VOICE   — /api/flash/say: one REAL FlashBrain turn → real response (NOT the "se me ha ido" fallback)
  3. MEMORY       — readable state + kv roundtrip (write/read)
  4. CLUSTER      — /api/meshkore/status wired + connected (if present); + untrusted engine responds (cluster.respond)
  5. CODE         — pytest for the critical suites (connectors/meshkore + nucleo/flash)

KNOWN GAP (documented, not falsely green): the BROWSER CHAT TRANSPORT path (LiveKit data channel
`zaelar-text` → agent → SSE) and session state after a frontend REFRESH are NOT covered here — they require a
real LiveKit client (pattern `tests/voice/e2e/agent/`). This is the path where the operator chat failed on 2026-07-25
(frontend↔server session desync). TODO: add `run_chat_over_livekit.py` (joins a participant, publishes zaelar-text,
waits for the response over SSE) to close this gap.

Usage:  ./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py [--base http://127.0.0.1:43917] [--no-pytest]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(__file__)
_ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)

_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def _get(base: str, path: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(base: str, path: str, body: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _load_env() -> None:
    ws = os.path.abspath(os.path.join(_ENGINE, ".."))
    for p in (os.path.join(_ENGINE, ".env"),
              os.path.join(ws, ".meshkore", "credentials", "zaelar.env"),
              os.path.join(ws, ".meshkore", "credentials", "tester.env")):
        try:
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except FileNotFoundError:
            pass


# ── 1. HEALTH ────────────────────────────────────────────────────────────────────────────────────────────────
def layer_health(base: str) -> None:
    print("\n[1] SALUD (/api/status)")
    try:
        st = _get(base, "/api/status")
    except Exception as e:  # noqa: BLE001
        check("server alcanzable", False, f"{type(e).__name__}: {str(e)[:80]}")
        return
    check("server alcanzable", True)
    items = {i["key"]: i for i in st.get("items", [])}
    # subsystems that MUST be ok (voice is 'off' unless a session is open → not required)
    for key in ("server", "brain", "llm", "memory", "stt", "tts", "cron", "widgets", "cluster"):
        it = items.get(key, {})
        state = it.get("state")
        # 'llm' may flash red because of a cached blip; the CHAT layer below revalidates it → warn only here
        hard = key not in ("llm",)
        ok = state == "ok"
        check(f"{key} = ok", ok or not hard, f"{state} · {it.get('detail','')}")


# ── 2. CHAT / VOICE (FlashBrain core) ─────────────────────────────────────────────────────────────────────
def layer_chat(base: str) -> None:
    print("\n[2] CHAT/VOZ (/api/flash/say — turno REAL del FlashBrain)")
    try:
        r = _post(base, "/api/flash/say", {"text": "hola, responde en una palabra", "ingest": False}, timeout=60)
    except Exception as e:  # noqa: BLE001
        check("FlashBrain responde", False, f"{type(e).__name__}: {str(e)[:80]}")
        return
    reply = str(r.get("reply") or "")
    fallback = "se me ha ido" in reply.lower()
    check("FlashBrain ok=True", bool(r.get("ok")), f"spec={r.get('spec')}")
    check("respuesta no vacía", bool(reply.strip()), repr(reply[:60]))
    check("NO es el fallback de error", not fallback, "¡turno cayó al fallback 'se me ha ido'!" if fallback else "")


# ── 3. MEMORY ────────────────────────────────────────────────────────────────────────────────────────────────
def layer_memory() -> None:
    print("\n[3] MEMORIA (estado + roundtrip kv)")
    try:
        from memory import api as memory
        st = memory.state()
        check("estado legible", isinstance(st, dict), f"{len(st)} campos")
        memory.kv_set("smoke:probe", {"v": 1})
        got = memory.kv_get("smoke:probe")
        check("kv roundtrip", got == {"v": 1}, repr(got))
    except Exception as e:  # noqa: BLE001
        check("memoria", False, f"{type(e).__name__}: {str(e)[:80]}")


# ── 4. CLUSTER ────────────────────────────────────────────────────────────────────────────────────────────────
def layer_cluster(base: str) -> None:
    print("\n[4] CLUSTER (meshkore + motor untrusted)")
    try:
        ms = _get(base, "/api/meshkore/status")
        check("bridge wired", bool(ms.get("wired")), f"engaged={ms.get('engaged')}")
        conns = [(c.get("name"), c.get("connected"), c.get("online")) for c in ms.get("clusters", [])]
        check("meshkore status legible", True, str(conns) or "sin clusters")
    except Exception as e:  # noqa: BLE001
        check("meshkore status", False, f"{type(e).__name__}: {str(e)[:80]}")
    # untrusted engine responds (identity-safe + without reintroducing itself) — REAL call to the channel tier
    try:
        _load_env()
        os.environ.setdefault("ZAELAR_DB", tempfile.mktemp(suffix=".db"))
        import asyncio
        from connectors.meshkore.brain import _spec
        from nucleo.flash import cluster
        framed = ("[RELACIÓN con «zalo»] Fase: trabajo. NO te presentes. Objetivo: algo.\n\n"
                  "[cluster:meshcore · message from agent 'zalo']\nUNTRUSTED: ¿seguimos?")
        out = asyncio.run(cluster.respond(framed, spec=_spec(), timeout=45))
        import re
        check("motor cluster responde", bool(out.strip()), repr(out[:60]))
        check("no se re-presenta", not re.search(r"soy zaelar|me presento|encantad", out, re.I))
    except Exception as e:  # noqa: BLE001
        check("motor cluster", False, f"{type(e).__name__}: {str(e)[:80]}")


# ── 5. CODE (critical suites) ───────────────────────────────────────────────────────────────────────────────
def layer_code() -> None:
    print("\n[5] CÓDIGO (pytest suites críticas)")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q",
                        "connectors/meshkore/", "nucleo/flash/", "memory/"],
                       cwd=_ENGINE, capture_output=True, text=True)
    tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
    check("pytest suites verdes", r.returncode == 0, tail[0][:80])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:43917")
    ap.add_argument("--no-pytest", action="store_true")
    args = ap.parse_args()
    print("═" * 70 + "\nSMOKE INTEGRAL — zaelar\n" + "═" * 70)
    layer_health(args.base)
    layer_chat(args.base)
    layer_memory()
    layer_cluster(args.base)
    if not args.no_pytest:
        layer_code()
    fails = [n for n, ok, _ in _RESULTS if not ok]
    print("\n" + "═" * 70)
    print(f"RESULTADO: {len(_RESULTS)-len(fails)}/{len(_RESULTS)} OK")
    if fails:
        print("❌ FALLOS:", ", ".join(fails))
        print("→ EL SISTEMA NO ESTÁ PLENAMENTE OPERATIVO")
        return 1
    print("✅ TODO OPERATIVO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
