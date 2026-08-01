#!/usr/bin/env python3
"""Canal CHAT (voz OFF, V2-054) — conversación MULTI-TURNO headless por el probe del FlashBrain.

El operador puede teclear en el chat sin voz (sin STT ni TTS → cero latencia de audio); la RESPUESTA del cerebro es
la misma que por voz (mismo turno del FlashBrain, `note_directed`), solo cambia el transporte (no se sintetiza audio).
Este test valida el LADO CEREBRO/CONVERSACIÓN de ese canal — lo que `domain_sea.py` (single-shot) no cubre: que una
CONVERSACIÓN de varios turnos por texto SE MANTENGA COHERENTE, arrastre el CONTEXTO de los turnos previos (la ventana),
no DEGENERE ni entre en BUCLE, enrute bien un dato factual en medio de la charla, y responda RÁPIDO. Es la parte
headless del T1.4 pendiente (el mecanismo de audio-OFF a nivel LiveKit se prueba en el escenario de voz).

Cada HILO es una sesión persistente del probe (la ventana conversacional se conserva turno a turno). NO escribe a la
memoria durable (`ingest=False`) → NO ensucia la cuenta del operador; el contexto se prueba por la VENTANA del turno.

Uso:  ./.venv/bin/python -m tests.voice.e2e.agent.chat_convo
      BASE=http://localhost:43917 ./.venv/bin/python -m tests.voice.e2e.agent.chat_convo
"""
import json
import os
import time
import urllib.request

BASE = os.getenv("BASE", "http://localhost:43917").rstrip("/")
MAX_CHAT_MS = int(os.getenv("CHAT_MAX_MS", "3500"))   # un turno de charla > 3.5s por texto es sospechoso


def _post(path, body, t=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode())


def turn(text, sid):
    t0 = time.time()
    r = _post("/api/flash/say", {"text": text, "session": sid, "ingest": False})
    # loop_run es un ENTERO (nº de pasadas del bucle de diálogo; 1 = normal). Solo ≥2 = re-generación anti-bucle.
    return {"action": r.get("action", "") or "", "reply": (r.get("reply") or "").strip(),
            "degenerate": bool(r.get("degenerate")), "loop": (r.get("loop_run") or 0) > 1,
            "ms": round((time.time() - t0) * 1000)}


# HILOS de conversación: cada uno = lista de (frase_del_usuario, verificador(turn)->(ok,motivo)). Los verificadores
# comprueban lo OBSERVABLE del turno; el arrastre de contexto se comprueba con follow-ups que dependen del turno previo.
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
    # 1) charla fluida — coherencia turno a turno, todo chat, sin degeneración/bucle
    "smalltalk": [
        ("hola, ¿qué tal el día?", chat_ok("saludo")),
        ("pues yo un poco liado con el trabajo, la verdad", chat_ok("sigue la charla")),
        ("nada, cosas de la oficina. ¿tú te aburres ahí quieto?", chat_ok("responde con naturalidad")),
        ("jaja vale. oye pues nada, gracias por escuchar", chat_ok("cierre cordial")),
    ],
    # 2) arrastre de CONTEXTO — el follow-up depende del turno anterior (la ventana)
    "context": [
        ("estoy pensando en hacer una barbacoa el sábado en el jardín", chat_ok("plan")),
        ("¿y si llueve, qué se te ocurre?", alive("propone alternativa SIN perder el hilo de la barbacoa")),
        ("buena idea. ¿cuánta carne calculo para seis personas?", alive("responde a la cantidad, sigue en el plan")),
    ],
    # 3) dato factual EN MEDIO de la charla → search, y vuelta a la charla sin quedar enganchado
    "mixed": [
        ("qué ganas tengo de que llegue el finde", chat_ok("charla")),
        ("por cierto, ¿qué hora es ahora en Tokio?", search_ok("hora en el mundo → web_search")),
        ("gracias. bueno, sigo con lo mío entonces", chat_ok("vuelve a charla, no re-busca")),
    ],
    # 4) corrección/aclaración conversacional (no es memoria durable, es la ventana)
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
