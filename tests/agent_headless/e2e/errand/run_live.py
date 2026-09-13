"""A REAL errand against a REAL person — the live node of V2-684.

Everything about the errand is deterministic except the only thing that matters: whether a stranger, on
their own phone, in their own time, can be talked to. This runner is the human-in-the-loop half, and the
operator gave it a counterpart to talk to — a second Telegram account he controls, `@cryptonite_fund`,
installed on his own machine. He answers it himself while watching.

    ./.venv/bin/python -m tests.agent_headless.e2e.errand.run_live --yes
    ./.venv/bin/python -m tests.agent_headless.e2e.errand.run_live --yes --to @otro --wait 3600

## Read this before running it

This is the one test in the house that WRITES TO A PERSON. It:

  · **arms the errand out of SHADOW** for the duration of the run, by writing `config/playbooks.json` —
    which the live engine re-reads on mtime. The flag is global, so the run REFUSES to start while any
    other errand is open, and restores the file (or deletes it) in a `finally`;
  · sends a real Telegram message from the operator's own account;
  · writes a contact and, if the conversation gets that far, a meeting in his real agenda.

Nothing here is undone afterwards except the arming. That is deliberate: the point is to leave the same
traces a real errand leaves, so he can look at them.

## What it proves that nothing else can

Node 3.43 drives the whole arc with a fake at the transport, which means it proves the ENGINE. It cannot
prove that Telegram accepted the message, that the echo carried a usable chat id, that the reply arrived
as an inbound event, that the thread store held it in time for the dossier, or that a person reading it
understood what they were being asked. Those are the five things this runs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ENGINE = "http://127.0.0.1:43917"
DEFAULT_TO = "@cryptonite_fund"
PLATFORM = "telegram"


# ── talking to the live engine ──────────────────────────────────────────────────────────────────────────
def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(f"{ENGINE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _get(path: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(f"{ENGINE}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _action(wid: str, action: str, payload: dict) -> dict:
    return _post(f"/widgets/{wid}/action", {"action": action, "payload": payload})


def say(*parts) -> None:
    print(*parts, flush=True)


# ── the preconditions, each one a reason to stop ────────────────────────────────────────────────────────
def _engine_is_up() -> bool:
    try:
        _get("/widgets", timeout=5)
        return True
    except Exception as e:  # noqa: BLE001
        say(f"✘ the engine does not answer on {ENGINE} ({e!r}).\n"
            f"  → start it with `make run` and try again.")
        return False


def _telegram_is_connected() -> bool:
    from config import connectors as cfg
    if not cfg.enabled(PLATFORM):
        say("✘ the Telegram connector is OFF.\n"
            "  → open the mensajería widget → Conectores → Telegram, and link the account (QR).")
        return False
    return True


def _nothing_else_is_open() -> bool:
    """The arming is GLOBAL, so this is a precondition and not a nicety: arming with another errand live
    would hand it the same authority, and nobody asked for that one to be sent."""
    from nucleo import errands
    n = errands.count_open()
    if n:
        say(f"✘ {n} errand(s) are already open, and arming is global — this run would arm those too.\n"
            f"  → close them (or wait for them to expire) and try again.")
        for row in errands.live():
            say(f"    · {row['id']} · {row['state']} · {row['objective'][:70]}")
        return False
    return True


# ── arming, and putting it back ─────────────────────────────────────────────────────────────────────────
class Armed:
    """Take the live engine out of shadow for the length of the run, and put it back whatever happens."""

    def __enter__(self):
        from nucleo import workspace
        self.path = workspace.root() / "config" / "playbooks.json"
        self.existed = self.path.exists()
        self.before = self.path.read_text(encoding="utf-8") if self.existed else ""
        data = json.loads(self.before or "{}")
        data.setdefault("errands", {})["shadow"] = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        say("⚠️  ARMED — the errand will really send. The engine re-reads this file by mtime, so it is live now.")
        return self

    def __exit__(self, *exc):
        if self.existed:
            self.path.write_text(self.before, encoding="utf-8")
        else:
            try:
                self.path.unlink()
            except Exception:
                pass
        say("🔒 back in SHADOW.")
        return False


# ── reading what happened, from the engine's own stores ─────────────────────────────────────────────────
def _thread(chat_id: str) -> list[dict]:
    from connectors.messaging import store as msgstore
    from widgets.mensajeria import thread as _thread_mod
    db = msgstore.load()
    th = (db.get("threads") or {}).get(_thread_mod.key(PLATFORM, chat_id)) or {}
    return list(th.get("msgs") or [])


def _transcript(msgs: list[dict]) -> str:
    out = []
    for m in msgs:
        who = "→ zaelar" if str(m.get("direction") or m.get("dir") or "") == "out" else "← ellos  "
        out.append(f"    {who}  {str(m.get('body') or '')[:160]}")
    return "\n".join(out) or "    (nothing yet)"


def _wait_for(what: str, predicate, *, timeout: float, poll: float = 3.0):
    """Poll until it happens, saying what it is waiting for. Returns the value, or None on timeout."""
    say(f"⏳ waiting for {what} (up to {int(timeout // 60)} min) — you can answer whenever you like.")
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        got = predicate()
        if got:
            return got
        left = int(deadline - time.time())
        line = f"   … {left // 60:02d}:{left % 60:02d} left"
        if line != last:
            print(line, end="\r", flush=True)
            last = line
        time.sleep(poll)
    say(f"\n✘ timed out waiting for {what}.")
    return None


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Drive a REAL errand against a real person.")
    ap.add_argument("--yes", action="store_true", help="required: this sends a real message to a real person")
    ap.add_argument("--to", default=DEFAULT_TO, help=f"Telegram handle of the other party (default {DEFAULT_TO})")
    ap.add_argument("--name", default="Pruebas Zaelar", help="how the contact is named in the directory")
    ap.add_argument("--objective", default="organizar una reunión de prueba en las próximas 4 horas")
    ap.add_argument("--text", default=None, help="the opening message (default: introduces itself)")
    ap.add_argument("--wait", type=float, default=1800, help="seconds to wait for each of his replies")
    ap.add_argument("--resume", action="store_true",
                    help="attach to the errand already open instead of sending a NEW opening message")
    args = ap.parse_args()

    if not args.yes:
        say(__doc__)
        say("Refusing to run without --yes: this sends a REAL message to a REAL person.")
        return 2
    if not _engine_is_up() or not _telegram_is_connected():
        return 1
    if not args.resume and not _nothing_else_is_open():
        return 1

    opener = args.text or (
        "Hola, soy Zaelar, el asistente personal de Ricard. Me ha pedido que organice una reunión con "
        "vosotros esta tarde, en las próximas cuatro horas. ¿Te viene bien alguna hora? Si no, mañana lunes "
        "a cualquier hora también nos sirve.")

    from nucleo import errands as _e
    if args.resume:
        # Picking up a conversation already in flight. The point of the run is what happens when somebody
        # ANSWERS, and sending a third identical opener to a real person to get there is not a test, it is
        # a nuisance. Also the honest shape of the thing: an errand outlives the process that opened it.
        row = _newest_errand(_e)
        if not row or row.get("state") in ("closed", "abandoned", "blocked"):
            say("✘ --resume, but there is no open errand to resume.")
            return 1
        with Armed():
            return _follow(_e, row, args)

    say("── 1 · the contact ─────────────────────────────────────────────────────────────")
    res = _action("contactos", "add_contact", {
        "name": args.name, "kind": "person",
        "channels": [{"platform": PLATFORM, "handle": args.to}], "preferred": PLATFORM})
    say(f"   {args.name} · {args.to} · {res.get('ok') and 'ok' or res}")

    from nucleo import errands
    with Armed():
        say("── 2 · the order ───────────────────────────────────────────────────────────────")
        say(f"   → {args.to}: «{opener[:120]}…»")
        res = _action("mensajeria", "send_to", {
            "contact": args.name, "channel": PLATFORM, "text": opener, "objective": args.objective})
        if not res.get("ok"):
            say(f"✘ the engine refused the order: {res.get('error') or res}")
            return 1
        ref = ((res.get("result") or {}).get("ref")) or ""
        say(f"   queued · ref {ref}")

        say("── 3 · the echo, which is what BIRTHS the errand ───────────────────────────────")
        row = _wait_for("Telegram to confirm the message went out", lambda: _newest_errand(errands),
                        timeout=120, poll=2)
        if not row:
            say("  → check the engine log: a send that never echoes means the connector could not resolve the "
                "handle, and no errand is opened on purpose.")
            return 1
        if row.get("state") in ("closed", "abandoned", "blocked"):
            say(f"✘ the errand was born and ENDED immediately: {row['state']} · {row.get('outcome') or '—'}")
            say("  → that is a product defect, not a transport one: the message DID go out. Read the "
                "outcome above before running again.")
            return 1
        say(f"   errand {row['id']} · kind {row['kind']}")
        say(f"   deadline {time.strftime('%H:%M', time.localtime(row['deadline']))} · "
            f"expires {time.strftime('%a %H:%M', time.localtime(row['expires_at']))}")

        return _follow(errands, row, args)
    return 0


def _follow(errands, row: dict, args) -> int:
    """Wait for the other person, one reply at a time, and report how it ended."""
    threads = errands.threads(row["id"])
    chat = str(threads[0]["chat_id"]) if threads else ""
    say("── 4 · the conversation ────────────────────────────────────────────────────────")
    say(f"   errand {row['id']} · {row.get('state')} · owns {PLATFORM}:{chat}")
    say(f"   ANSWER NOW from {args.to}. Every reply wakes the errand; it answers on its own.")
    seen = len(_thread(chat))
    for turn in range(1, 9):
        got = _wait_for(f"reply #{turn}", lambda: _grew(chat, seen), timeout=args.wait)
        if not got:
            break
        seen = len(got)
        say(f"\n   transcript after reply #{turn}:")
        say(_transcript(got[-8:]))
        state = (errands.get(row["id"]) or {}).get("state") or "closed"
        say(f"   errand state: {state}")
        if state in ("closed", "abandoned", "blocked"):
            break

    say("── 5 · how it ended ────────────────────────────────────────────────────────────")
    final = errands.get(row["id"]) or {}
    say(f"   state {final.get('state')} · outcome {final.get('outcome') or '—'} · "
        f"wakes {final.get('wake_count')}")
    if final.get("state") == "agreed":
        say("   ⚠️ it agreed a time and the errand is still open — that is CORRECT today: nothing in the "
            "engine writes the agreed meeting into the agenda yet (V2-683 row 6, blocked on "
            "connectors/calendar/). Put it in by hand and the next beat should close the errand.")
    say("\n   full transcript:")
    say(_transcript(_thread(chat)))
    return 0


def _newest_errand(errands):
    """The errand this run opened — whatever STATE it is in.

    ⚠️ It used to ask `errands.live()`, and the first live run showed why that is the wrong question: the
    errand was born and CLOSED itself in the same second (a verifier defect), so `live()` answered empty
    and the runner reported «Telegram never confirmed the message went out» — over a message Telegram had
    confirmed one second earlier. An instrument that can only see the happy path describes every other
    outcome as the one failure it knows.
    """
    from memory import errands_store as store
    rows = store.errands_where(("contacting", "gathering", "negotiating", "agreed",
                                "closed", "abandoned", "blocked"), limit=50)
    return dict(rows[-1]) if rows else None


def _grew(chat: str, seen: int):
    msgs = _thread(chat)
    return msgs if len(msgs) > seen else None


if __name__ == "__main__":
    sys.exit(main())
