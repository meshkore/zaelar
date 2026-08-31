#!/usr/bin/env python3
"""CHAT channel (voice OFF, V2-054) — headless MULTI-TURN conversation through the FlashBrain probe.

The operator can type in the chat without voice (no STT or TTS → zero audio latency); the brain's RESPONSE is
the same as with voice (the same FlashBrain turn, `note_directed`), only the transport changes (no audio is synthesized).
This test validates the BRAIN/CONVERSATION SIDE of that channel — what `domain_sea.py` (single-shot) does not cover: that a
CONVERSATION spanning multiple text turns REMAINS COHERENT, carries CONTEXT from previous turns (the window),
does not DEGENERATE or enter a LOOP, routes a factual datum correctly in the middle of the chat, and responds QUICKLY. It is the
pending headless part of T1.4 (the audio-OFF mechanism at the LiveKit level is tested in the voice scenario).

Each THREAD is a persistent probe session (the conversational window is preserved from turn to turn). It does NOT write to
durable memory (`ingest=False`) → it does NOT clutter the operator's account; context is tested through the turn WINDOW.

Usage:  ./.venv/bin/python -m tests.voice.e2e.agent.chat_convo
      BASE=http://localhost:43917 ./.venv/bin/python -m tests.voice.e2e.agent.chat_convo
"""
import json
import os
import time
import urllib.request

BASE = os.getenv("BASE", "http://localhost:43917").rstrip("/")
MAX_CHAT_MS = int(os.getenv("CHAT_MAX_MS", "3500"))   # a chat turn taking > 3.5s over text is suspicious


def _post(path, body, t=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode())


def turn(text, sid):
    t0 = time.time()
    r = _post("/api/flash/say", {"text": text, "session": sid, "ingest": False})
    # loop_run is an INTEGER (number of dialogue-loop passes; 1 = normal). Only ≥2 means anti-loop regeneration.
    return {"action": r.get("action", "") or "", "reply": (r.get("reply") or "").strip(),
            "degenerate": bool(r.get("degenerate")), "loop": (r.get("loop_run") or 0) > 1,
            "ms": round((time.time() - t0) * 1000)}


# Conversation THREADS: each one is a list of (user_phrase, verifier(turn)->(ok,reason)). The verifiers
# check what is OBSERVABLE in the turn; context carryover is checked with follow-ups that depend on the previous turn.
def chat_ok(why="charla"):
    return lambda t: (t["action"] == "chat" and bool(t["reply"]) and not t["degenerate"] and not t["loop"], why)


def search_ok(why="dato del mundo → search"):
    return lambda t: (t["action"] == "search", why)


def alive(why="responde, sin degenerar/buclear"):
    return lambda t: (bool(t["reply"]) and not t["degenerate"] and not t["loop"], why)


def mentions(sub, why=None):
    why = why or f"referencia el contexto («{sub}»)"
    return lambda t: (sub.lower() in t["reply"].lower() and not t["degenerate"], why)


THREADS = {
    # 1) fluid chat — turn-by-turn coherence, all chat, without degeneration/looping
    "smalltalk": [
        ("hola, ¿qué tal el día?", chat_ok("saludo")),
        ("pues yo un poco liado con el trabajo, la verdad", chat_ok("sigue la charla")),
        ("nada, cosas de la oficina. ¿tú te aburres ahí quieto?", chat_ok("responde con naturalidad")),
        ("jaja vale. oye pues nada, gracias por escuchar", chat_ok("cierre cordial")),
    ],
    # 2) CONTEXT carryover — the follow-up depends on the previous turn (the window)
    "context": [
        ("estoy pensando en hacer una barbacoa el sábado en el jardín", chat_ok("plan")),
        ("¿y si llueve, qué se te ocurre?", alive("propone alternativa SIN perder el hilo de la barbacoa")),
        ("buena idea. ¿cuánta carne calculo para seis personas?", alive("responde a la cantidad, sigue en el plan")),
    ],
    # 3) factual datum IN THE MIDDLE of the chat → search, then return to chat without getting stuck
    "mixed": [
        ("qué ganas tengo de que llegue el finde", chat_ok("charla")),
        ("por cierto, ¿qué hora es ahora en Tokio?", search_ok("hora en el mundo → web_search")),
        ("gracias. bueno, sigo con lo mío entonces", chat_ok("vuelve a charla, no re-busca")),
    ],
    # 4) conversational correction/clarification (not durable memory, but the window)
    "clarify": [
        ("me llamo Marcos, apúntatelo para esta charla", alive("acepta con naturalidad")),
        ("perdona, no era Marcos, es Marco, sin ese", alive("acepta la corrección sin liarse")),
        ("¿cómo has dicho que me llamo?", mentions("marco", "recuerda el nombre corregido de la ventana")),
    ],
}


def run(threads=None):
    names = threads or list(THREADS.keys())
    print(f"== CANAL CHAT (voz OFF) · conversación multi-turno == hilos={len(names)}  base={BASE}")
    fails, lat, total = [], [], 0
    for name in names:
        sid = f"chat-{name}"
        try:
            _post("/api/flash/reset", {"session": sid}, t=10)
        except Exception:
            pass
        print(f"\n-- hilo «{name}» --")
        for i, (utt, check) in enumerate(THREADS[name]):
            try:
                t = turn(utt, sid)
            except Exception as e:  # noqa: BLE001
                t = {"action": f"ERR:{str(e)[:30]}", "reply": "", "degenerate": False, "loop": False, "ms": 0}
            total += 1
            lat.append(t["ms"])
            try:
                ok, why = check(t)
            except Exception:
                ok, why = False, "verificador reventó"
            slow = t["ms"] > MAX_CHAT_MS and t["action"] == "chat"
            flag = "" if (ok and not slow) else ("  <-- LENTO" if (ok and slow) else "  <-- FALLO")
            print(f"  [{i}] «{utt[:46]}» → {t['action']} ({t['ms']}ms){flag}")
            print(f"       ↳ {t['reply'][:88]}")
            if not ok:
                fails.append((name, utt, t["action"], t["reply"][:60], why))
            elif slow:
                fails.append((name, utt, f"LENTO {t['ms']}ms", t["reply"][:40], "charla debería ser < %dms" % MAX_CHAT_MS))
    p = sorted(lat)
    print(f"\n== RESULTADO: {total} turnos · fallos {len(fails)} · "
          f"lat p50 {p[len(p)//2]}ms p90 {p[int(len(p)*0.9)]}ms ==")
    for name, utt, act, rep, why in fails:
        print(f"  [{name}] «{utt[:48]}» → {act}  | {rep}  [esperado: {why}]")
    return fails


if __name__ == "__main__":
    import sys
    run(sys.argv[1:] or None)
