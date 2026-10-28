"""Run state, the microphone switch, energy and the desktop epoch — the routes the ⏻ button and the top bar read (from
`server/voice_api.py`, refactor2710-13 T-03). Mounted through `voice_api.router`."""
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/energy")
async def energy():
    """The account Energy balance, for the top-bar BATTERY. Read-only, no-cache.

    Returns FACTS (balance, starting amount, whether this installation has a cloud account) and NOT the drawing
    scale: how many slots the battery has, how much each tick is worth, and which color it uses are PRESENTATION
    decisions that live in the frontend (`EnergyGauge.js`). That way the server does not need to know about colors
    and the scale can change without touching Python.

    On self-host it returns `cloud:false` and the frontend renders nothing: there is no balance to spend."""
    try:
        from nucleo.energy import limits as account_limits, account as cloud_account, lease as energy_lease, meter as energy_meter
        # The LEASE travels alongside the balance because they are the same question seen at two distances: the
        # balance is what the ACCOUNT has left, while the lease is what THIS machine may spend before asking again.
        # With the link down, only the second one is a locally verifiable fact.
        # `exhausted` and `account_url` ride here so a page opened AFTER the energy ran out still shows the notice
        # and where to top up — the SSE event that announced it is gone by then.
        return JSONResponse({**energy_meter.snapshot(), "lease": energy_lease.snapshot(),
                             "exhausted": account_limits.exhausted(), "account_url": cloud_account.account_url()},
                            headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"cloud": False, "known": False}, headers={"Cache-Control": "no-cache"})


@router.get("/api/run")
async def run_get():
    """V2-092: is the agent RUNNING or STOPPED? The server owns the truth (`nucleo/runstate.py`), not browser
    `localStorage` — the frontend seeds from here on boot, so reloading the page (or opening it in another browser)
    inherits the real state instead of resurrecting an agent the operator had stopped."""
    from nucleo import runstate
    return JSONResponse(runstate.snapshot(), headers={"Cache-Control": "no-cache"})


@router.post("/api/run/stop")
async def run_stop():
    """STOP the agent: freeze Brain Workers (SIGSTOP, reversible) and SUSPEND widgets that are producing (music,
    video…). The ⏻ button: freezes the workers and everything else. Returns what was frozen,
    so the operator log is not a list of intentions."""
    try:
        from nucleo import runstate
        return JSONResponse(await runstate.stop("operator"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/run/start")
async def run_start():
    """START the agent: frozen workers CONTINUE where they were. Widgets are deliberately NOT resumed — starting the
    music again is an operator gesture (see `nucleo/runstate.py`, "deliberate asymmetry")."""
    try:
        from nucleo import runstate
        return JSONResponse(await runstate.start("operator"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/desktop/epoch")
async def desktop_epoch():
    """Desktop WIPE epoch: `scripts/reset-memory.sh` bumps it on every wipeout. The frontend compares it with the
    value stored in localStorage and, if it is NEW, starts with an EMPTY desktop (blank session after a reset — open
    widgets live in browser localStorage, which a server-side deletion cannot reach)."""
    epoch = "0"
    try:
        _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          ".meshkore", "logs", "desktop-epoch")
        with open(_p, encoding="utf-8") as f:
            epoch = f.read().strip() or "0"
    except Exception:
        pass
    return JSONResponse({"epoch": epoch})


@router.post("/api/mic")
async def mic_switch(payload: dict):
    """V2-654 — THE microphone switch, told to the engine. The browser's `services/mic.js` is the only writer and
    it calls here on every change AND on every (re)connect; the session heartbeat re-asserts the same value every
    ~4s, so a divergence between icon and engine cannot outlive one beat.

    Before this route the mute existed ONLY in the browser and only as an icon signal: four of its six writers
    never touched the audio track, so the engine heard a microphone the operator had closed and had no way to
    know (session 85eec898). Reading it is `voice/mic_input.py`; the gate that uses it is in the turn path."""
    from voice import mic_input
    muted = bool((payload or {}).get("muted"))
    src = str((payload or {}).get("src") or "frontend")[:40]
    dev = str((payload or {}).get("dev") or "")[:40]
    from server.livekit_api import speaks_for_the_mic
    if not speaks_for_the_mic(dev):
        return JSONResponse({"ok": True, "muted": mic_input.is_muted(), "ignored": "not_the_voice_holder"})
    return JSONResponse(mic_input.set_muted(muted, source=src, dev=dev))


@router.get("/api/mic")
async def mic_state():
    """The engine's own answer, so the client can VERIFY instead of assuming its write landed."""
    from voice import mic_input
    return JSONResponse(mic_input.snapshot())
