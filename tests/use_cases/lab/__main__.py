"""The lab's control surface.

    python -m tests.use_cases.lab up es            # boot it: full engine, voice on its OWN LiveKit room
    python -m tests.use_cases.lab up es --quiet     # no voice — headless only, the screen stays on the splash
    python -m tests.use_cases.lab up all            # both agents
    python -m tests.use_cases.lab status            # who is up, on what port, since when
    python -m tests.use_cases.lab reset es          # wipe its memory, reseed the profile, SAME port
    python -m tests.use_cases.lab say es "..."      # drive one turn by text while you watch
    python -m tests.use_cases.lab logs es           # tail its engine log
    python -m tests.use_cases.lab down all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from tests.use_cases.lab import screen, shot, stage
from tests.use_cases.lab.profiles import PROFILES, LabProfile, get

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _targets(key: str) -> list[LabProfile]:
    return list(PROFILES.values()) if key == "all" else [get(key)]


def _report(st: stage.LabState) -> None:
    p = st.profile
    if st.foreign:
        print(f"  ✗ {p.key}  {st.base_url}  ALGO RESPONDE EN ESE PUERTO Y NO ES NUESTRO — no lo toco")
        return
    if not st.running:
        print(f"  ⬜ {p.key}  {st.base_url}  parado          ({p.title})")
        return
    age = time.time() - st.started_at if st.started_at else 0
    mins = f"{age/60:.0f} min" if age >= 60 else f"{age:.0f} s"
    voice = "voz ON " if st.voice else "voz off"
    print(f"  ✅ {p.key}  {st.base_url}  {voice} · pid {st.pid} · {mins}   ({p.title})")
    if st.chain:
        print(f"       cadena: {st.chain}")
    # Se dice SIEMPRE, y en los dos sentidos. Pedir la limpieza no es haberla conseguido, y el sitio donde
    # eso se paga es el ◷: una ronda leída sobre el canvas de la anterior no se puede interpretar.
    print(f"       sesión: {'EN BLANCO (memoria y perfil intactos)' if st.cleaned else 'NO se pudo limpiar al arrancar — puede arrastrar pantalla y procesos de antes'}")


def _watch_lines(st: stage.LabState) -> None:
    print(f"     ▸ MÍRALO EN VIVO   {st.base_url}")
    print(f"     ▸ eventos/flujos   {st.base_url}/api/observability/flows?limit=30")
    print(f"     ▸ log              {stage._log_path(st.profile)}")


def cmd_up(args) -> int:
    rc = 0
    for p in _targets(args.agent):
        st = stage.status(p)
        if st.foreign:
            _report(st)
            rc = 1
            continue
        if st.running:
            print(f"  ✔ {p.key} ya estaba en marcha")
            _report(st)
            _watch_lines(st)
            continue
        print(f"▶ arrancando {p.key} en 127.0.0.1:{p.port} ({p.title}, "
              f"idioma={p.language}, voz={'off' if args.quiet else 'ON'})…")
        try:
            _, st = stage.up(p, voice=not args.quiet, fresh=args.fresh)
        except Exception as e:
            print(f"  ✗ {p.key} no arrancó: {e}")
            print(f"     log: {stage._log_path(p)}")
            rc = 1
            continue
        _report(st)
        _watch_lines(st)
        print(f"     ▸ condúcelo por chat: python -m tests.use_cases.lab say {p.key} \"…\"")
        if args.quiet:
            print("     ▸ ⚠️ --quiet: SIN voz. La pantalla se queda en el splash — esto es para lotes "
                  "sin nadie mirando, no para ver.")
    return rc


def cmd_down(args) -> int:
    for p in _targets(args.agent):
        stopped = stage.down(p)
        print(f"  {'⏹ parado' if stopped else '· no estaba en marcha'}: {p.key}")
    return 0


def cmd_status(args) -> int:
    for p in _targets(args.agent):
        _report(stage.status(p))
    return 0


def cmd_reset(args) -> int:
    rc = 0
    for p in _targets(args.agent):
        print(f"▶ {p.key}: borrando memoria y sembrando el perfil de nuevo (mismo puerto {p.port})…")
        try:
            _, st = stage.reset(p, voice=False if args.quiet else None)
        except Exception as e:
            print(f"  ✗ {p.key} no volvió a arrancar: {e}")
            rc = 1
            continue
        _report(st)
        _watch_lines(st)
    return rc


def cmd_clean(args) -> int:
    """Dejar la sesión en BLANCO sin reiniciar: canvas, procesos de fondo y ventana de observabilidad.

    `up` ya lo hace al arrancar y el runner lo hace antes de CADA caso, así que esto es para el agente que
    lleva rato en pie y al que se le va a mirar algo — la norma del operador es que un test empiece con la
    pantalla limpia para poder centrar el ◷ en la tarea en curso. La memoria y el perfil NO se tocan: para
    eso está `reset`, que es otra cosa y lo dice.
    """
    rc = 0
    for p in _targets(args.agent):
        st = stage.status(p)
        if not st.running:
            print(f"  ⬜ {p.key} no está en marcha — nada que limpiar")
            continue
        out = stage.clean_session(p)
        if not out:
            print(f"  ✗ {p.key} NO se pudo limpiar — sigue con la pantalla y los procesos de antes")
            rc = 1
            continue
        r = out.get("reset") or {}
        blanked = ", ".join((r.get("widgets") or {}).get("blanked") or []) or "nada abierto"
        killed = r.get("killed") or {}
        print(f"  ✅ {p.key} sesión EN BLANCO (memoria y perfil intactos) · sesión nueva "
              f"{str(out.get('session') or '')[:8]}")
        print(f"       canvas: {blanked}")
        print(f"       trabajo parado: {killed}")
    return rc


def cmd_say(args) -> int:
    p = get(args.agent)
    st = stage.status(p)
    if not st.running:
        print(f"  ✗ {p.key} no está en marcha (`up {p.key}` primero)")
        return 1
    body = json.dumps({"text": args.text, "session": args.session, "execute": True,
                       "ingest": True}).encode()
    req = urllib.request.Request(f"{st.base_url}/api/flash/say", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            out = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP {e.code}: {e.read()[:400].decode('utf-8', 'replace')}")
        return 1
    except Exception as e:
        print(f"  ✗ {e}")
        return 1
    print(f"  tú     · {args.text}")
    # `reply`, not `text` — read from `nucleo/flash/probe.py::run_turn`'s actual payload, not from
    # memory. Guessing the field name printed "(sin respuesta)" over a perfectly good answer, which reads
    # exactly like a dead provider: a wrong field does not fail, it INVENTS a fact about the product.
    said = (out.get("reply") or "").strip()
    if said:
        print(f"  zaelar · {said}")
    else:
        # A turn that comes back empty ALWAYS has a reason and the engine always puts it in the payload.
        # Printing "(sin respuesta)" and stopping there cost eight hours of measuring window on
        # 2026-08-21: the 402 was in hand and the terminal said "look at the log". If you have the
        # answer, print it.
        why = str(out.get("error") or out.get("reason") or "").strip()
        spec = str(out.get("spec") or "").strip()
        print("  zaelar · (turno VACÍO)")
        if why:
            print(f"           ▸ lo que dijo el motor: {why[:400]}")
        if spec:
            print(f"           ▸ escalón que se intentó: {spec}")
        if not why:
            print(f"           ▸ el motor no dio motivo — mira el log: "
                  f"`python -m tests.use_cases.lab logs {args.agent}`")
    act = out.get("action")
    if act:
        print(f"           ▸ acción: {act}")
    if out.get("trace"):
        print(f"           ▸ flujo:  {st.base_url}/api/observability/flow/{out['trace']}")
    return 0


def cmd_screen(args) -> int:
    """What is on screen and what is inside it — read from the engine, no browser involved."""
    p = get(args.agent)
    st = stage.status(p)
    if not st.running:
        print(f"  ✗ {p.key} no está en marcha")
        return 1
    snap = screen.read(st.base_url, with_data=not args.no_data)
    print(screen.render(snap))
    if args.trail:
        print("TRAZA de widgets (en orden):")
        for e in snap["widget_trail"][-args.trail:]:
            print(f"   {e['id']:>6}  {e['label']:<9} {e['widget']:<22} ← {e['src'] or '?'}")
    return 0


def cmd_shot(args) -> int:
    """A screenshot, as reinforcement for a VISUAL claim. See lab/shot.py on what it cannot tell you."""
    p = get(args.agent)
    st = stage.status(p)
    if not st.running:
        print(f"  ✗ {p.key} no está en marcha")
        return 1
    out = stage.workspace_of(p) / "shots" / f"{args.name}.png"
    try:
        facts = shot.grab(st.base_url, out, settle_ms=int(args.settle * 1000))
    except Exception as e:
        print(f"  ✗ no pude capturar: {e}")
        return 1
    print(f"  ✓ {facts['path']}")
    print(f"    velo puesto: {facts['veil']} · orbe: {facts['orb']} · tarjetas: {facts['cards']}")
    if facts["errors"]:
        print(f"    errores de página: {facts['errors']}")
    return 0


def cmd_logs(args) -> int:
    p = get(args.agent)
    path = stage._log_path(p)
    if not path.exists():
        print(f"  · sin log todavía: {path}")
        return 1
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-args.n:]))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.use_cases.lab", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    agents = sorted(PROFILES) + ["all"]

    up = sub.add_parser("up", help="arrancar")
    up.add_argument("agent", choices=agents, nargs="?", default="all")
    up.add_argument("--quiet", action="store_true",
                    help="SIN pipeline de voz. Headless de verdad: la pantalla NO se puede mirar "
                         "(el velo de arranque no se retira sin LiveKit — ver stage.env_for).")
    up.add_argument("--fresh", action="store_true", help="borrar la memoria antes de arrancar")
    up.set_defaults(fn=cmd_up)

    dn = sub.add_parser("down", help="parar")
    dn.add_argument("agent", choices=agents, nargs="?", default="all")
    dn.set_defaults(fn=cmd_down)

    stt = sub.add_parser("status", help="qué hay en pie")
    stt.add_argument("agent", choices=agents, nargs="?", default="all")
    stt.set_defaults(fn=cmd_status)

    cl = sub.add_parser("clean", help="sesión en BLANCO sin reiniciar (canvas + procesos; memoria intacta)")
    cl.add_argument("agent", nargs="?", default="all", choices=["es", "us", "all"])
    cl.set_defaults(fn=cmd_clean)

    rs = sub.add_parser("reset", help="borrar memoria + resembrar perfil, MISMO puerto")
    rs.add_argument("agent", choices=agents, nargs="?", default="all")
    rs.add_argument("--quiet", action="store_true", help="además, volver sin voz (no mirable)")
    rs.set_defaults(fn=cmd_reset)

    sy = sub.add_parser("say", help="un turno por texto (para conducirlo mientras miras)")
    sy.add_argument("agent", choices=sorted(PROFILES))
    sy.add_argument("text")
    sy.add_argument("--session", default="lab")
    sy.add_argument("--timeout", type=float, default=180.0)
    sy.set_defaults(fn=cmd_say)

    sc = sub.add_parser("screen", help="qué hay en pantalla y qué lleva dentro (sin navegador)")
    sc.add_argument("agent", choices=sorted(PROFILES))
    sc.add_argument("--no-data", action="store_true", help="solo la lista, sin abrir el contenido")
    sc.add_argument("--trail", type=int, default=0, help="además, las N últimas órdenes de widget")
    sc.set_defaults(fn=cmd_screen)

    sh = sub.add_parser("shot", help="captura (REFUERZO de una afirmación visual, no la vía normal)")
    sh.add_argument("agent", choices=sorted(PROFILES))
    sh.add_argument("--name", default="now")
    sh.add_argument("--settle", type=float, default=20.0, help="segundos de espera antes de disparar")
    sh.set_defaults(fn=cmd_shot)

    lg = sub.add_parser("logs", help="cola del log del motor")
    lg.add_argument("agent", choices=sorted(PROFILES))
    lg.add_argument("-n", type=int, default=60)
    lg.set_defaults(fn=cmd_logs)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
