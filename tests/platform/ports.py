"""The three agents this machine runs, and the port each one answers on.

    43917   the operator's own engine      — `server/__main__.py`'s compiled-in default
    43921   the SPANISH sandbox            — `tests/use_cases/lab/` `es`, or a `--sandbox` batch of `__es` cases
    43922   the UNITED STATES sandbox      — the same, `us`

WHY A TABLE AND NOT A NUMBER AT EACH CALL SITE. The lab pinned 43921/43922 in `profiles.py` and said in its
README that the port never changes, while the unattended batch booted on `preferred_port(43918)`: ONE number
for both languages, and one that SLID to an ephemeral port whenever it was taken. So "the Spanish agent" had
two different addresses depending on which command had started it, and the sliding one had no address at all
— the operator opened the port they remembered and found nothing listening. Both halves read this table now,
so there is one Spanish agent, at one place, however the round was launched.

A BUSY PORT IS AN ERROR, NEVER A SLIDE. Already the lab's rule (see `lab/stage.py`), now the whole tree's. An
agent that quietly moves is an agent you cannot find, and the sliding bought less than it looked like it did:
a leftover engine on the old port killed every later round ANYWAY (`unit/test_run_persistence.py` — batches
that measured nothing while the tick read the previous verdict and acted on it), it just did it without
saying where to look. `busy_refusal()` refuses and names WHO is holding the port.
"""
from __future__ import annotations

import json
import socket
import subprocess
import urllib.request

OPERATOR = 43917
SANDBOX_ES = 43921
SANDBOX_US = 43922

#: key → port. The key is what the operator says out loud ("el sandbox ES"), and what `--lab` takes.
AGENTS: dict[str, int] = {"operator": OPERATOR, "es": SANDBOX_ES, "us": SANDBOX_US}

NAMES: dict[int, str] = {
    OPERATOR: "el motor del OPERADOR (su instalación de siempre)",
    SANDBOX_ES: "el sandbox ES (agente en español)",
    SANDBOX_US: "el sandbox US (agente en inglés)",
}


def sandbox_port(locale: str) -> int:
    """The fixed port of the sandbox that must drive a case of this locale.

    Takes what the catalog actually stores (`es` / `us`) and also what the engine calls it
    (`ZAELAR_LANGUAGE`: `es` / `en`), because the two travel together through this harness and a mapping
    that only understood one of them would send half the rounds to the other country's agent.
    """
    return SANDBOX_ES if str(locale or "").strip().lower().startswith("es") else SANDBOX_US


def is_free(port: int) -> bool:
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False


def _answers(port: int, timeout: float = 2.0) -> dict | None:
    """The `/api/status` of whoever is on the port, or None. Identifies a zaelar engine as such."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{int(port)}/api/status",
                                     headers={"User-Agent": "zaelar-ports"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def _listener(port: int) -> str:
    """`pid command` of whoever holds the port, best effort. Empty when we cannot tell (or on Windows)."""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=6).stdout
    except Exception:
        return ""
    for line in out.splitlines()[1:]:
        f = line.split()
        if len(f) >= 2:
            return f"pid {f[1]} ({f[0]})"
    return ""


def holder(port: int) -> str:
    """Who is on this port, in words the operator can act on — or "" when it is free.

    The version matters and is worth the extra field: the failure this whole registry exists to stop is
    measuring against an engine that is not the one you think, and "answers, but on 3.15+4abaf9c" is the
    line that catches it (the same trap `run.py`'s stamp check was written for).
    """
    if is_free(port):
        return ""
    st = _answers(port) or {}
    who = _listener(port)
    if st:
        ver = ""
        for it in (st.get("items") or []):
            if it.get("key") == "version":
                ver = str((it.get("extra") or {}).get("short") or it.get("detail") or "")
                break
        bits = ["un motor zaelar VIVO"] + ([f"build {ver}"] if ver else []) + ([who] if who else [])
        return " · ".join(bits)
    return f"algo que no es un motor zaelar{(' · ' + who) if who else ''}"


def busy_refusal(port: int, *, want: str) -> str:
    """"" when the port is ours to take, or the message that stops the round.

    `want` is what we were about to boot there, so the message reads as a collision between two named
    things rather than as a generic EADDRINUSE — the operator has three agents and needs to know WHICH two
    are fighting.
    """
    who = holder(port)
    if not who:
        return ""
    mine = NAMES.get(port, f"puerto {port}")
    hint = (f"   · si ya es el agente que querías, mídelo con `--lab {'es' if port == SANDBOX_ES else 'us'}` "
            f"en vez de levantar otro\n"
            f"   · si sobra, bájalo:  python -m tests.use_cases.lab down "
            f"{'es' if port == SANDBOX_ES else 'us'}   (o mata el proceso que lo tiene)\n")
    if port == OPERATOR:
        hint = "   · ese puerto es del motor del operador y no se le quita: usa el sandbox de su idioma\n"
    return (f"✗ el puerto {port} — {mine} — está OCUPADO, y aquí un puerto ocupado es un error, no una "
            f"razón para moverse.\n"
            f"   quería levantar: {want}\n"
            f"   lo tiene ahora:  {who}\n"
            f"{hint}"
            f"   (ver: `lsof -nP -iTCP:{port} -sTCP:LISTEN`)")
