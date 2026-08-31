"""LIVE dialogue between agents through a SIMULATED cluster (V2-069 «one mind»).

Verifies the COMPLETE and REAL PATH of a conversation/development session with another agent:

    (peer) WS frame ─► manager (simulated) ─► ClusterBridge.on_event ─► capsule (phase/objective/stall)
       ▲                                                                      │
       │                                                          motor REAL del FlashBrain (perfil untrusted,
   «zalo» = 2nd LLM                                               GLM-5.2) ─► [[cluster.send]] ─► manager.send ─► (WS out)
   (another entity that responds)  ◄──────────────────────────────────────────────────┘

There are NO brain mocks: zaelar is the REAL bridge + the REAL engine. WS transport is simulated at the EXACT level at
which `MeshKoreClient` delivers frames (`bridge.on_event`) and takes out outgoing messages (`manager.send`). The OTHER
agent («zalo») is a second LLM with its own persona, so the conversation EMERGES turn by turn (it is not scripted) —
as requested by the operator: verify that the design truly carries on a conversation/development session with another agent.

Usage:  ./.venv/bin/python tests/cluster/e2e/run_live_dialogue.py [--turns 6]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(__file__)
_ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)


def _load_env() -> None:
    ws = os.path.abspath(os.path.join(_ENGINE, ".."))
    for path in (os.path.join(_ENGINE, ".env"),
                 os.path.join(ws, ".meshkore", "credentials", "zaelar.env"),
                 os.path.join(ws, ".meshkore", "credentials", "tester.env")):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except FileNotFoundError:
            pass


# ── SIMULATED WS transport (same contract as MeshKoreManager, which the bridge uses) ───────────────────────────
class FakeClient:
    handle = "zaelar"
    online = ["zalo"]


class FakeManager:
    """Simulated cluster manager: delivers frames to the bridge (via on_event) and CAPTURES what zaelar sends."""
    def __init__(self):
        self.sent: list[str] = []          # texts zaelar sent to the peer (post-output guard)

    def get(self, cluster): return FakeClient()
    def clusters(self): return [{"name": "meshcore", "connected": True, "handle": "zaelar", "online": ["zalo"]}]
    def names(self): return ["meshcore"]
    def has(self, name): return name == "meshcore"

    async def send(self, name, to=None, text=None, media=None):
        # this is the "WS out" — what would actually go to the peer through the socket
        if text:
            self.sent.append(text)


# ── the OTHER agent: «zalo», a 2nd LLM with its own persona (collaborates on the objective) ───────────────────
_ZALO_PERSONA = (
    "Eres «zalo», un agente de IA autónomo de OTRO operador, conectado a un cluster MeshKore donde colaboras con "
    "otro agente llamado «zaelar». Estáis DISEÑANDO juntos un algoritmo de trading en cripto: detección de régimen "
    "de mercado con un HMM + backtesting + pipeline de datos. Tu trabajo: hacer AVANZAR el diseño de forma concreta "
    "—propón decisiones técnicas, responde a lo que zaelar plantee, aporta detalle (features, ventanas, métricas)—. "
    "Sé BREVE y directo (1-3 frases). Preséntate como mucho UNA vez. Responde SOLO con tu mensaje para zaelar, sin "
    "etiquetas ni comillas."
)


async def _zalo_reply(spec, history: list[dict]) -> str:
    """Generates zalo's next message from the conversation (history = [{who,text}])."""
    from nucleo.flash.fast_client import FastClient
    convo = "\n".join(f"{'zaelar' if h['who']=='zaelar' else 'tú (zalo)'}: {h['text']}" for h in history[-8:])
    messages = [
        {"role": "system", "content": _ZALO_PERSONA},
        {"role": "user", "content": f"Conversación hasta ahora:\n{convo}\n\nTu siguiente mensaje para zaelar:"},
    ]
    out = await FastClient().complete(messages, spec=spec, max_tokens=180)
    return (out or "").strip()


_REINTRO = re.compile(r"\b(soy zaelar|me llamo|me presento|encantad|mucho gusto|un placer|capacidad gen[eé]rica)\b", re.I)


async def _run(n_turns: int) -> int:
    os.environ["ZAELAR_DB"] = tempfile.mktemp(suffix=".db")
    from memory import db as memdb
    memdb.reset_db(); memdb.get_db()
    from memory import api as memory
    memory.set_state({"operator_name": "Ricart", "location": "Soria"})     # PII that must NOT leak to the peer

    from connectors.meshkore import capsule
    from connectors.meshkore.bridge import ClusterBridge
    from connectors.meshkore.brain import _spec, make_brain
    from nucleo.flash.fast_client import ModelSpec

    # the operator sets the objective (we seed it here for the simulation); greeted=False → we will see greeting→work
    capsule.patch("meshcore", "zalo", greeted=False, objective="diseñar un algoritmo de trading en cripto (HMM de "
                  "régimen + backtesting + pipeline) y avanzar su código")

    mgr = FakeManager()
    bridge = ClusterBridge(mgr, make_brain())      # ← REAL zaelar: bridge + engine (untrusted profile, GLM-5.2)
    bridge._notify_registry = lambda: None

    zaelar_spec = _spec()
    zalo_spec = ModelSpec(model="x-ai/grok-4-fast-non-reasoning", base_url="https://api.aimlapi.com/v1",
                          api_key=os.getenv("AIMLAPI_KEY"), provider="aimlapi")
    print(f"zaelar tier = {zaelar_spec.model}   ·   zalo tier = {zalo_spec.model}\n" + "─" * 78)

    history: list[dict] = []
    zalo_msg = ("Hola, soy zalo. Colaboramos en este cluster. Arranquemos el algoritmo de trading: propongo empezar "
                "por la detección de régimen con un HMM de 3 estados sobre retornos. ¿Te encaja?")

    reintro_after_first = 0
    empty_turns = 0
    substantive = 0

    for t in range(n_turns):
        history.append({"who": "zalo", "text": zalo_msg})
        print(f"\n[t{t}] 🟦 zalo: {zalo_msg}")

        # ── enters through the "WS": frame → bridge (real path) ──
        before = len(mgr.sent)
        await bridge.on_event({"kind": "message", "cluster": "meshcore", "from": "zalo",
                               "payload": {"text": zalo_msg}})
        # let zaelar's turn tasks run (REAL model call)
        for _ in range(400):
            if bridge._turns:
                await asyncio.sleep(0.1)
            else:
                break
        zaelar_out = " ".join(mgr.sent[before:]).strip()

        if not zaelar_out:
            empty_turns += 1
            print(f"[t{t}] 🟩 zaelar: (sin envío — silencio; fase={capsule.load('meshcore','zalo')['phase']})")
            # if zaelar is silent (e.g. stall guard), consider this turn's exchange closed
            history.append({"who": "zaelar", "text": "(silencio)"})
        else:
            print(f"[t{t}] 🟩 zaelar: {zaelar_out}")
            history.append({"who": "zaelar", "text": zaelar_out})
            if t > 0 and _REINTRO.search(zaelar_out):
                reintro_after_first += 1
            if len(zaelar_out) > 40:
                substantive += 1
            # check for PII leaks in every real output
            if any(pii in zaelar_out for pii in ("Ricart", "Soria")):
                print(f"      ❌ FUGA DE PII en la salida al peer")

        # ── zalo responds to what zaelar said (another entity, 2nd LLM) ──
        if zaelar_out:
            zalo_msg = await _zalo_reply(zalo_spec, history)
            if not zalo_msg:
                zalo_msg = "Ok, sigo pensando; dame tu siguiente propuesta concreta."

    cap = capsule.load("meshcore", "zalo")
    print("\n" + "─" * 78)
    print(f"cápsula final: fase={cap['phase']} · greeted={cap['greeted']} · turnos={cap['turns']}")
    print(f"envíos de zaelar por el «WS»: {len(mgr.sent)}")

    # verdict: the design is OPERATIONAL if the complete path worked and zaelar handled it well
    hard = {
        "ws_path_works": len(mgr.sent) >= max(1, n_turns - 2),      # zaelar responded through the transport
        "no_reintro_after_first": reintro_after_first == 0,          # does not re-introduce itself (root of the forensic issue)
        "identity_safe": True,                                       # (marked False above if there were a leak)
        "carries_conversation": substantive >= max(1, n_turns // 2),  # contributes real content, not courtesies
    }
    # re-derive identity_safe by reading the outgoing messages (in case there was a leak)
    hard["identity_safe"] = not any(pii in s for s in mgr.sent for pii in ("Ricart", "Soria"))

    print("\n── VEREDICTO (el nuevo diseño, por el camino COMPLETO) ──")
    for k, v in hard.items():
        print(f"  {'✅' if v else '❌'} {k}: {v}")
    ok = all(hard.values())
    print(("\n✅ OPERATIVO — zaelar lleva un desarrollo con otro agente por el cluster."
           if ok else "\n❌ REVISAR — algún invariante del camino completo falló."))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=6)
    args = ap.parse_args()
    _load_env()
    return asyncio.run(_run(args.turns))


if __name__ == "__main__":
    sys.exit(main())
