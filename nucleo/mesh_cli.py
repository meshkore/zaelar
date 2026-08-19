"""nucleo/mesh_cli.py — `hbmesh`: the bridge a Brain Worker uses to ask the mesh BEFORE opening a browser.

    python -m nucleo.mesh_cli find "hotel en Madrid esta noche 2 personas"
    python -m nucleo.mesh_cli serve "hotel en Madrid" --prompt "hotel in Madrid check-in 2026-09-10 \\
                                                                check-out 2026-09-11 for 2 guests"

`find` only asks WHO could do it (cheap, ~1 s). `serve` finds and asks in one go, preferring the agent that
already served this kind of errand. Both print JSON on stdout and never fail hard: no mesh, no agent, or an
agent that will not answer all come back as `{"ok": false, "reason": …}`, and the worker carries on with the
browser exactly as it does today.

Sibling of `nav_cli` (`hbweb`) and deliberately its OPPOSITE in cost: a browser errand is minutes of driving a
real Chromium through defences built to stop it — measured, an entire run spent on Booking's anti-bot
challenge — while this is one HTTP round-trip. So the order in the worker's method is: ask the mesh, and only
open a browser when nobody answers.

**Ask in ENGLISH.** Measured: «vuelo de Madrid a Roma» resolves to no agent at all while "flight from Madrid
to Rome" returns `aerocast`, free, with ten real offers. The Oracle's intent parser is markedly better in
English, so the errand is phrased in English even when the operator spoke Spanish — and what comes back is
checked, because the mapping is loose at the edges (a restaurant query answers with a hotel agent).

**Dates are the caller's job.** Pass absolute ISO dates in `--prompt`, never «esta noche»: measured live, an
agent asked in relative terms resolved check-in to the previous year and returned nothing, and the same
request with explicit dates returned ten real offers.

Free agents only (enforced in `nucleo/mesh_agents.py`, not here and not in a prompt). An agent that charges
comes back as `{"ok": false, "reason": "«X» cobra por esto"}` and is never paid.
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hbmesh", description="preguntar a la red MeshKore quién puede hacer esto")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_find = sub.add_parser("find", help="quién puede servir este encargo (no lo pide)")
    p_find.add_argument("errand")
    p_find.add_argument("--limit", type=int, default=5)

    p_serve = sub.add_parser("serve", help="buscar Y pedirlo, reutilizando la ruta ya aprendida")
    p_serve.add_argument("errand")
    p_serve.add_argument("--prompt", default="", help="el encargo con FECHAS ABSOLUTAS y todos los datos")

    a = ap.parse_args(argv)
    try:
        from nucleo import mesh_agents
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "reason": f"la red no está disponible: {e}"}, ensure_ascii=False))
        return 0

    if a.cmd == "find":
        res = mesh_agents.find(a.errand, limit=a.limit)
        # Only what the worker needs to decide, not the Oracle's full record: an agent id, where it serves and
        # what it says it does. Dumping the raw result would put ~20 scoring fields into the worker's context
        # on every errand, and V2-117 is what that costs.
        print(json.dumps({"ok": bool(res.get("agents")), "intent": res.get("intent"),
                          "agents": [{"agent_id": x.get("agent_id"), "endpoint": x.get("endpoint"),
                                      "capabilities": x.get("capabilities") or []}
                                     for x in res.get("agents") or []]}, ensure_ascii=False))
        return 0

    res = mesh_agents.serve(a.errand, a.prompt or a.errand)
    print(json.dumps(res, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
