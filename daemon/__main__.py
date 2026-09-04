"""`python -m daemon` — start the Zaelar Local Daemon.

Sub-commands exist for the two things somebody needs from a terminal that the HTTP surface cannot give them:
seeing the token (to point an engine on the same machine at it) and seeing what has been granted.

    python -m daemon              start it in the foreground
    python -m daemon status       is it running, on what port, with which folders
    python -m daemon token        print the API token (the engine reads it from daemon.json itself)
    python -m daemon allow PATH   grant a folder from the terminal
    python -m daemon deny PATH    revoke one
"""
from __future__ import annotations

import json
import sys

from . import PORT, VERSION, config, permissions, server
from .paths import config_file, state_dir
from .permissions import Refusal

USAGE = __doc__


def main(argv: list[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "").strip().lower()
    arg = argv[2] if len(argv) > 2 else ""

    if cmd in ("", "serve", "start", "run"):
        return server.serve()

    if cmd == "status":
        cfg = config.load()
        port = int(cfg.get("port") or PORT)
        print(json.dumps({
            "version": VERSION,
            "running": server.is_running(port),
            "port": port,
            "configured": bool(cfg.get("configured")),
            "roots": permissions.roots(),
            "state_dir": str(state_dir()),
            "config": str(config_file()),
        }, indent=1, ensure_ascii=False))
        return 0

    if cmd == "token":
        print(config.token())
        return 0

    if cmd in ("allow", "deny"):
        if not arg:
            print(f"usage: python -m daemon {cmd} /path/to/folder", file=sys.stderr)
            return 2
        try:
            roots = permissions.grant(arg) if cmd == "allow" else permissions.revoke(arg)
        except Refusal as r:
            print(r.message, file=sys.stderr)
            return 1
        # The change lands in daemon.json, which a RUNNING daemon has already cached in memory — say so rather
        # than let the user watch a granted folder stay invisible and conclude the permission system is broken.
        print("folders: " + (", ".join(roots) if roots else "(none)"))
        if server.is_running():
            print("the daemon is running: restart it for this to take effect.")
        return 0

    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
