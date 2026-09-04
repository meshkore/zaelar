"""zaelar-daemon — the LOCAL DAEMON (V2-575 · P0).

⚠️ NAME COLLISION, read this before deleting anything. `CLAUDE.md` §Daemon says "this repo does NOT start or
include a daemon of its own — do not create `.meshkore/daemon.py`, no `make meshkore` targets, do not bind port
5570". That rule is about the **MeshKore Standard daemon** (`daemon.meshkore.com`, the shared dev/onboarding
service) and it is STILL IN FORCE. This is a different thing entirely: the **Zaelar Local Daemon**, a product
component that runs on the end user's own computer. Package and binary are called `zaelar-daemon`; it binds
45817, never 5570, and it has nothing to do with MeshKore.

WHY IT EXISTS
    The CLOUD engine — the paid one — cannot pass a CAPTCHA or authenticate on a user's site. The local engine
    can (it opens a real Chromium, the user signs in once, the session survives in a persistent profile), but
    inside a container there is no window to open and no user keyboard to reach, so the cloud agent hits the wall
    and stops. `widgets/navegador/owner.py` says it out loud: `_in_container()` → "I cannot do that from the
    cloud yet".

    The daemon runs where the window and the profile actually are. It gives the engine — local over loopback,
    cloud over the relay (P3) — two capabilities the container does not have:
      1. the user's FILES, under a per-folder permission circuit;
      2. a REAL BROWSER on the user's screen for auth and CAPTCHAs (P2).

WHAT IT IS NOT
    It is NOT a dependency. The engine keeps its own in-process browser and works exactly as it does today when
    the daemon is absent — the daemon is an ADDITIVE backend, never a required one (decision 5). Anybody who
    clones this repo and never starts the daemon has precisely today's product.

STANDALONE ON PURPOSE
    Nothing here imports the engine. The engine's venv is ~1.7 GB across ~394 packages (torch, mlx); a onefile
    installer built from that is not possible, so the daemon carries its OWN minimal dependency set — which for
    P0 is the empty set: standard library only. It resolves its own paths (see `paths.py`) with the same
    `ZAELAR_WORKSPACE` semantics as `nucleo/workspace.py` so that in-repo it lands in the same place, and falls
    back to an OS user-data directory when it is running as an installed binary with no repo around it.
"""
from __future__ import annotations

# Bumped by hand when the daemon's HTTP contract changes in a way the engine can observe. The engine compares it
# against what it expects and can say "your daemon is out of date" instead of failing on a missing route.
VERSION = "0.1.0"

# THE PORT. Fixed, so the engine and the wizard can both name it without discovery, and chosen deliberately:
#   · not in /etc/services (verified 2026-09-04) — no known service to collide with;
#   · below 49152, the ephemeral floor on macOS/Linux, so an outbound connection can never steal it while the
#     daemon is down and make the next start fail with EADDRINUSE;
#   · far from everything this project already binds — 43917/44317 (engine), 7880 (livekit), 9222/9200 (browser
#     debug) — and from 5570 (the MeshKore daemon this is not).
PORT = 45817

# Loopback ONLY, and this is load-bearing rather than a default. See `server.py`: the daemon hands out the user's
# documents, so binding anything else would put them on the network.
HOST = "127.0.0.1"

__all__ = ["VERSION", "PORT", "HOST"]
