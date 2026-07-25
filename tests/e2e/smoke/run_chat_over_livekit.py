"""E2E del CHAT por el transporte REAL — cliente LiveKit → data-channel → agent → respuesta (2026-07-25).

Cierra el hueco que dejó pasar el fallo del 2026-07-25: el chat del operador quedó sin respuesta porque el MOTOR
LiveKit del server se había degradado (wait_pc_connection timed out) → el agent no formaba la sala → el handler del
data-channel `zaelar-text` nunca se activaba. El smoke server-side (probe) NO lo cazaba porque el probe no usa
LiveKit. ESTE test sí: reproduce el camino EXACTO del navegador.

Qué hace:
  1. pide token + url (/api/token, /api/livekit) — como el frontend
  2. conecta una sala LiveKit REAL (rtc.Room) — si el motor está degradado, esto falla → cazado
  3. publica un mensaje en el data-topic `zaelar-text` (idéntico a session-lk.js::sendText)
  4. espera la respuesta de zaelar en el stream de observabilidad (timeline: transcript de zaelar posterior)
  5. PASS si llega respuesta; FAIL si no (chat roto) — exit≠0

Uso:  ./.venv/bin/python tests/e2e/smoke/run_chat_over_livekit.py [--base http://127.0.0.1:43917]
Requiere el server arrancado (make run) y el SDK livekit (ya usado por tester/).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(__file__)
_ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
_TIMELINE = os.path.join(_ENGINE, "..", ".meshkore", "logs", "timeline-latest.jsonl")


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read().decode())


def _timeline_size() -> int:
    try:
        return os.path.getsize(_TIMELINE)
    except OSError:
        return 0


def _new_zaelar_replies(since: int) -> list[str]:
    """Transcripts de zaelar (role assistant / label 'zaelar') aparecidos tras el offset `since`."""
    out = []
    try:
        with open(_TIMELINE, "rb") as f:
            f.seek(since)
            for raw in f.read().decode("utf-8", "replace").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                if d.get("kind") == "transcript" and (d.get("role") == "assistant" or d.get("label") == "zaelar"):
                    t = (d.get("text") or "").strip()
                    if t:
                        out.append(t)
    except OSError:
        pass
    return out


async def _run(base: str) -> int:
    try:
        from livekit import rtc
    except Exception as e:  # noqa: BLE001
        print(f"❌ SDK livekit no disponible: {e}")
        return 1

    url = _get(base, "/api/livekit").get("url") or "ws://127.0.0.1:7880"
    tok = _get(base, "/api/token?identity=smoke-chat").get("token")
    if not tok:
        print("❌ no se obtuvo token de /api/token")
        return 1

    room = rtc.Room()
    try:
        # 1+2. conectar la sala REAL — si el motor LiveKit está degradado, esto lanza (cazado)
        await asyncio.wait_for(room.connect(url, tok), timeout=20)
        print(f"✅ sala LiveKit conectada ({url})")
    except Exception as e:  # noqa: BLE001
        print(f"❌ NO se pudo conectar la sala LiveKit: {type(e).__name__}: {str(e)[:120]}")
        print("   → el motor LiveKit/agent no forma la sala (justo el fallo del 2026-07-25).")
        return 1

    try:
        await asyncio.sleep(4)                       # deja pasar el kickoff (saludo al conectar)
        since = _timeline_size()
        msg = f"prueba e2e chat {int(time.time())}: responde OK en una palabra"
        payload = json.dumps({"t": "zaelar-text", "text": msg}).encode()
        # 3. publicar en el data-topic EXACTO del chat del frontend
        await room.local_participant.publish_data(payload, reliable=True, topic="zaelar-text")
        print(f"✅ mensaje publicado en data-topic 'zaelar-text'")

        # 4. esperar la respuesta de zaelar (timeline) hasta ~25s
        reply = None
        for _ in range(25):
            await asyncio.sleep(1)
            reps = _new_zaelar_replies(since)
            if reps:
                reply = reps[-1]
                break
        if reply:
            print(f"✅ zaelar respondió por el camino REAL del chat: {reply[:80]!r}")
            return 0
        print("❌ SIN respuesta al mensaje de chat en 25s — el camino data-channel→agent→cerebro está ROTO")
        return 1
    finally:
        try:
            await room.disconnect()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:43917")
    args = ap.parse_args()
    print("═" * 60 + "\nE2E CHAT sobre LiveKit (transporte real)\n" + "═" * 60)
    rc = asyncio.run(_run(args.base))
    print(("\n✅ CHAT OPERATIVO de extremo a extremo" if rc == 0
           else "\n❌ CHAT ROTO — el sistema NO responde por el transporte real"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
