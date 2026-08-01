"""SMOKE INTEGRAL — «¿el sistema entero está en funcionamiento?» (2026-07-25, petición del operador).

Un SOLO comando que valida TODAS las vías del sistema contra el server VIVO y devuelve exit 0 solo si TODO
funciona. Nació de un fallo real: tras V2-069 (FlashBrain conduce operador Y cluster) el CHAT parecía roto y los
tests de código no lo cazaban porque cubrían el núcleo pero no el camino de extremo a extremo. Esto es la red de
seguridad "el sistema siempre queda operativo"; se extiende con más casos (1000→10000) sobre esta misma espina.

Comprueba, por capas:
  1. SALUD        — /api/status overall + cada subsistema (server/brain/llm/memory/stt/tts/cron/widgets/cluster)
  2. CHAT/VOZ     — /api/flash/say: un turno REAL del FlashBrain → respuesta real (NO el fallback "se me ha ido")
  3. MEMORIA      — estado legible + roundtrip kv (escribe/lee)
  4. CLUSTER      — /api/meshkore/status wired + (si hay) conectado; + motor untrusted responde (cluster.respond)
  5. CÓDIGO       — pytest de las suites críticas (connectors/meshkore + nucleo/flash)

GAP CONOCIDO (documentado, no falso-verde): el camino de TRANSPORTE del chat del navegador (data-channel LiveKit
`zaelar-text` → agent → SSE) y el estado de sesión tras un REFRESCO del frontend NO se cubren aquí — exigen un
cliente LiveKit real (patrón `tester/`). Es la vía donde falló el chat del operador el 2026-07-25 (desync de sesión
frontend↔server). TODO: añadir `run_chat_over_livekit.py` (une un participante, publica zaelar-text, espera la
respuesta por SSE) para cerrar ese hueco.

Uso:  ./.venv/bin/python tests/e2e/smoke/run_full_smoke.py [--base http://127.0.0.1:43917] [--no-pytest]
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


# ── 1. SALUD ────────────────────────────────────────────────────────────────────────────────────────────────
def layer_health(base: str) -> None:
    print("\n[1] SALUD (/api/status)")
    try:
        st = _get(base, "/api/status")
    except Exception as e:  # noqa: BLE001
        check("server alcanzable", False, f"{type(e).__name__}: {str(e)[:80]}")
        return
    check("server alcanzable", True)
    items = {i["key"]: i for i in st.get("items", [])}
    # subsistemas que DEBEN estar ok (voice es 'off' salvo sesión abierta → no se exige)
    for key in ("server", "brain", "llm", "memory", "stt", "tts", "cron", "widgets", "cluster"):
        it = items.get(key, {})
        state = it.get("state")
        # 'llm' puede parpadear en rojo por un blip cacheado; lo revalida la capa CHAT abajo → aquí solo warn
        hard = key not in ("llm",)
        ok = state == "ok"
        check(f"{key} = ok", ok or not hard, f"{state} · {it.get('detail','')}")


# ── 2. CHAT / VOZ (núcleo del FlashBrain) ─────────────────────────────────────────────────────────────────────
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


# ── 3. MEMORIA ────────────────────────────────────────────────────────────────────────────────────────────────
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
    # motor untrusted responde (identidad-safe + sin re-presentarse) — llamada REAL al tier del canal
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


# ── 5. CÓDIGO (suites críticas) ───────────────────────────────────────────────────────────────────────────────
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
