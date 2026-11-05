"""A LOOPBACK messaging account inside a battery sandbox (V2-851 F0) — test-only, never shipped.

Loaded by the interpreter (`sitecustomize`) because the battery puts this folder on the sandbox's PYTHONPATH and sets
`ZAELAR_TEST_LOOPBACK=1`. It does nothing in any other process: it waits until the process is the engine
(`python -m server`) and its bus exists, then plays the part of a linked messaging connector for the platforms in
`ZAELAR_TEST_LOOPBACK_PLATFORMS` (default `telegram,email`):

  1. publishes `connector.status = connected` for each of them (again every few seconds: the messaging card's owner
     may subscribe late, and a reset blanks the card);
  2. consumes every `msg.send` / `msg.reply` order for those platforms — appended to `<workspace>/loopback/sent.jsonl`
     — and publishes the echo a real connector publishes once the message left (`connector.msg_out` with the order's
     `ref`, the shape of `connectors/telegram/service/outbound.py` and `connectors/email/service/orders.py`);
  3. polls `<workspace>/loopback/inbox/*.json` and publishes each file as an inbound `connector.msg` (a message or a
     mail, in the normalised shape of `connectors/email/mailbox/parse.py`), then renames it `*.done`.

Why the real platform names and not a `loopback` platform: the outbound door accepts only the platforms it declares
(`widgets/mensajeria/outbound/targets.PLATFORMS`, `widgets/directory.PLATFORMS`), and adding one is product code. The
sandbox runs with every real connector OFF (`TG_ENABLED=0`, `EMAIL_ENABLED=0`, its own session dirs, an empty
connector store), so nothing else in the process consumes these orders and nothing can reach a real account: this
module is the only reader of `msg.send` there.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path


def _chain_shadowed() -> None:
    """Run the `sitecustomize` this one shadows (Homebrew's Python ships one), so the sandbox's interpreter keeps
    whatever it set up."""
    here = Path(__file__).resolve().parent
    for entry in sys.path:
        try:
            cand = Path(entry or ".").resolve() / "sitecustomize.py"
        except OSError:
            continue
        if cand.parent == here or not cand.is_file():
            continue
        try:
            code = compile(cand.read_text(encoding="utf-8"), str(cand), "exec")
            exec(code, {"__name__": "_shadowed_sitecustomize", "__file__": str(cand)})
        except Exception:  # noqa: BLE001 — a broken host hook must not stop the sandbox
            pass
        return


_chain_shadowed()

_PLATFORMS = tuple(p.strip() for p in os.getenv("ZAELAR_TEST_LOOPBACK_PLATFORMS", "telegram,email").split(",")
                   if p.strip())
_ORDER_TOPICS = ("msg.send", "msg.reply")
_STATUS_EVERY_S = 5.0
_INBOX_EVERY_S = 1.0


def _is_engine() -> bool:
    argv0 = str((sys.argv or [""])[0])
    return argv0.replace("\\", "/").endswith("server/__main__.py")


def _root() -> Path:
    return Path(os.environ["ZAELAR_WORKSPACE"]) / "loopback"


class _Loopback:
    def __init__(self):
        import queue
        self.orders: "queue.Queue[tuple[str, dict]]" = queue.Queue()
        self.seq = 0
        root = _root()
        (root / "inbox").mkdir(parents=True, exist_ok=True)
        self.sent = root / "sent.jsonl"

    def sink(self, rec: dict) -> None:
        """A bus sink runs on the publisher's thread: only enqueue here, never publish."""
        try:
            topic = str(rec.get("topic") or "")
            pay = rec.get("payload")
            if topic in _ORDER_TOPICS and isinstance(pay, dict) and pay.get("platform") in _PLATFORMS:
                self.orders.put((topic, dict(pay)))
        except Exception:  # noqa: BLE001
            pass

    def deliver(self, topic: str, order: dict) -> None:
        from connectors.messaging import ingest
        self.seq += 1
        now = time.time()
        line = {"topic": topic, "at": now, **{k: v for k, v in order.items() if k != "attachments"}}
        with self.sent.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        plat = str(order.get("platform"))
        chat = str(order.get("chatId") or order.get("to") or "")
        echo = {"chatId": chat, "messageId": f"loopback:{self.seq}:{int(now)}", "ref": order.get("ref") or "",
                "from": "", "body": str(order.get("text") or ""), "timestamp": now,
                "contactId": order.get("contactId") or "", "chatName": order.get("name") or ""}
        ingest.publish_msg_out(plat, echo)

    def status(self) -> None:
        from connectors.messaging import ingest
        for p in _PLATFORMS:
            ingest.publish_status(p, "connected", None, "loopback")

    def inbox(self) -> None:
        from connectors.messaging import ingest
        for f in sorted((_root() / "inbox").glob("*.json")):
            try:
                msg = json.loads(f.read_text(encoding="utf-8"))
                plat = str(msg.pop("platform", "email"))
                ingest.publish_msg(plat, msg)
            except Exception as e:  # noqa: BLE001
                msg = {"error": repr(e)}
            f.rename(f.with_suffix(".done"))

    def run(self) -> None:
        import bus
        import queue
        last_status = 0.0
        last_inbox = 0.0
        while True:
            bus.add_sink(self.sink)          # idempotent; a bus reset clears sinks
            now = time.time()
            if now - last_status >= _STATUS_EVERY_S:
                last_status = now
                try:
                    self.status()
                except Exception:  # noqa: BLE001
                    pass
            if now - last_inbox >= _INBOX_EVERY_S:
                last_inbox = now
                try:
                    self.inbox()
                except Exception:  # noqa: BLE001
                    pass
            try:
                topic, order = self.orders.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.deliver(topic, order)
            except Exception:  # noqa: BLE001
                pass


def _start() -> None:
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(0.5)
        if not _is_engine():
            if sys.argv and sys.argv[0] not in ("", "-m", "-c"):
                return               # another program (a worker's CLI, a child script): not ours
            continue
        if "bus" in sys.modules and "server" in sys.modules:
            break
    else:
        return
    time.sleep(2.0)
    try:
        _Loopback().run()
    except Exception:  # noqa: BLE001
        pass


if os.getenv("ZAELAR_TEST_LOOPBACK") == "1" and os.getenv("ZAELAR_WORKSPACE"):
    threading.Thread(target=_start, name="battery-loopback", daemon=True).start()
