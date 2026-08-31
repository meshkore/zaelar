"""tests/voice/e2e/agent/youtube_flow_probe.py — Headless re-simulation of the YouTube-by-voice flow (2026-07-15 session).

FAST and RELIABLE companion to the `youtube_voice` voice scenario (tests/voice/e2e/agent/scenarios.py). Through
FlashBrain's headless TEST channel (`POST /api/flash/say`, V2-032, CLEAN INPUT without STT), it reproduces the subset of
DETERMINISTIC checks from the flow that broke during the manual session and was fixed in P0/P1:

  · d78d457 (P0): un worker por objetivo · modify≠create · naming.
  · dc436cc (P1): comentario≠orden · "cierra el resto" uno-a-uno · hecho-conocido→buscar · captura forense del turno.
  · 5367200:     estado de tarea = paso + tiempo (no frase-loro).

WHAT THIS PROBE COVERS (deterministic routing, without voice):
  - un COMENTARIO ambiente NO dispara acción (→ chat).
  - un HECHO PÚBLICO conocido se responde/busca, no se interroga.
  - "modifica/implementa/amplía el widget youtube" ESCALA (no responde de memoria ni se queda corto).
  - montar el widget del vídeo ESCALA a un worker.

WHAT IT CANNOT COVER (requires the `youtube_voice` VOICE scenario + actual execution):
  - dedup real de workers (`task/start` vs `task/dedup`) y "un solo chip"  → test automatizado + voz.
  - la decisión modify-vs-create la toma el WORKER (nucleo/agentes/code.widget_action), no el FlashBrain → voz/e2e.
  - "cierra el resto" uno-a-uno exige widgets ABIERTOS en el estado (viene del frontend) → voz/e2e.
  - voz ambiente DURANTE el trabajo, estado de tarea con paso+tiempo → voz/e2e.

Usage (server running; `make run` or `make flash-serve`):
    ./.venv/bin/python -m tests.voice.e2e.agent.youtube_flow_probe
"""
from __future__ import annotations
import json, urllib.request

BASE = "http://localhost:43917"

def say(text, sid, ingest=False):
    req = urllib.request.Request(BASE + "/api/flash/say",
                                 data=json.dumps({"text": text, "session": sid, "ingest": ingest}).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

# (id, text, evaluator(res)->bool, expected description)
def is_chat(r):    return r.get("action") == "chat"
def is_escalate(r):return "escalate" in (r.get("action") or "")
def answered_maradona(r):
    rep = (r.get("reply") or "").lower()
    return ("maradona" in rep or "1986" in rep or "argentina" in rep) or ("search" in (r.get("action") or ""))

# NOTE: AMBIENT voice FILTERING (undirected comment → nothing) is handled by the ATTENTION GATE, which lives in the
# VOICE path (attention.py), NOT in the FlashBrain core that runs the probe. The probe treats EVERYTHING as
# directed → it cannot test ambient filtering: the `youtube_voice` voice scenario covers that. Only
# deterministic FlashBrain decisions with directed, clean input belong here.
CHECKS = [
    ("comment_old",  "Va, este vídeo es bastante antiguo.", is_chat,
     "COMENTARIO sobre el vídeo → charla, sin cerrar/abrir (bug arreglado: 'era antiguo' cerraba youtube)"),
    ("known_fact",   "¿Quién marcó el gol de la mano de Dios?", answered_maradona,
     "hecho PÚBLICO conocido → responde/busca (Maradona 1986), sin interrogar"),
    # NB: "móntame un widget que reproduzca X" does NOT go here: with the `youtube` widget ALREADY existing, zaelar (correctly)
    # LOADS the video into it (widget_data) instead of CREATING one; and on a fresh start it CREATES one (escalate). Both
    # are correct depending on whether the widget exists → this is not deterministic headless. The CREATE path is covered by the
    # `youtube_voice` voice scenario (it starts without the widget).
    ("modify_impl",  "Implementa en el widget youtube la capacidad de ampliarse por voz.", is_escalate,
     "implementar EN youtube (la frase EXACTA que creaba basura) → escala; el worker decide MODIFY, no CREATE"),
    ("modify_add",   "Añádele al widget de youtube un control de velocidad de reproducción, para verlo a 1.5x y 2x.", is_escalate,
     "AÑADIR una función NUEVA (el widget no tiene control de velocidad) → escala a MODIFICAR youtube, no crea uno nuevo"),
]

def main():
    print("═══ RE-SIMULACIÓN headless · flujo YouTube-por-voz (2026-07-15) ═══")
    print("(input LIMPIO, sin STT; subconjunto determinista — lo e2e/voz lo cubre `youtube_voice`)\n")
    passed = 0
    for i, (cid, text, ok_fn, desc) in enumerate(CHECKS, 1):
        try:
            r = say(text, sid=f"yt_{cid}")
        except Exception as e:
            print(f"  {i}. {cid:12} ✗ ERROR {str(e)[:50]}"); continue
        ok = bool(r.get("ok")) and ok_fn(r)
        passed += ok
        print(f"  {i}. {cid:12} [{(r.get('action') or '?'):14}] {'✓' if ok else '✗'}  {desc}")
        print(f"       «{(r.get('reply') or '')[:80]}»")
    print(f"\n  RESULTADO: {passed}/{len(CHECKS)} checks deterministas OK")
    print("  (para dedup de workers / un-solo-chip / modify-vs-create real / cerrar-resto / ambiente-durante-trabajo:")
    print("   correr el escenario de VOZ:  ./.venv/bin/python -m tests.voice.e2e.agent.run --scenario youtube_voice )")

if __name__ == "__main__":
    main()
