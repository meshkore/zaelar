"""The terminal side of the daemon.

Sub-commands exist for the things somebody needs from a terminal that the HTTP surface cannot give them: seeing
the token (to point an engine on the same machine at it), seeing what has been granted, changing it without a
UI, and replacing the token if it leaked.

    zaelar-daemon                 start it in the foreground
    zaelar-daemon status          is it running, on what port, with which folders
    zaelar-daemon token           print the API token
    zaelar-daemon rotate-token    mint a new one (the running daemon keeps the old until it restarts)
    zaelar-daemon allow PATH      grant a folder
    zaelar-daemon deny PATH       revoke one
    zaelar-daemon version         print the version and exit

(`python -m daemon <command>` is the same thing when running from a source tree.)
"""
from __future__ import annotations

import json
import sys

from . import PORT, VERSION, config, permissions, server
from .paths import audit_file, config_file, state_dir
from .permissions import Refusal

USAGE = __doc__


def _status() -> int:
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
        "audit": str(audit_file()),
    }, indent=1, ensure_ascii=False))
    return 0


def _allow_or_deny(command: str, argument: str) -> int:
    if not argument:
        print(f"usage: zaelar-daemon {command} /path/to/folder", file=sys.stderr)
        return 2
    try:
        roots = permissions.grant(argument) if command == "allow" else permissions.revoke(argument)
    except Refusal as refusal:
        print(refusal.message, file=sys.stderr)
        return 1
    # The change lands in daemon.json, which a RUNNING daemon has already cached in memory — say so rather than
    # let the user watch a granted folder stay invisible and conclude the permission system is broken.
    print("folders: " + (", ".join(roots) if roots else "(none)"))
    if server.is_running():
        print("the daemon is running: restart it for this to take effect.")
    return 0


def main(argv: list[str]) -> int:
    command = (argv[1] if len(argv) > 1 else "").strip().lower()
    argument = argv[2] if len(argv) > 2 else ""

    if command in ("", "serve", "start", "run"):
        return server.serve()

    if command == "status":
        return _status()

    if command == "version":
        print(VERSION)
        return 0

    if command == "token":
        print(config.token())
        return 0

    if command in ("rotate-token", "rotate_token"):
        fresh = config.rotate_token()
        print(fresh)
        if server.is_running():
            print("the daemon is running: restart it so it starts accepting the new token.", file=sys.stderr)
        return 0

    if command in ("allow", "deny"):
        return _allow_or_deny(command, argument)

    print(USAGE, file=sys.stderr)
    return 2
