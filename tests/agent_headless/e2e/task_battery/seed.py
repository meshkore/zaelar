"""What a battery sandbox holds before the first line (V2-851 F0): the people, the rules, the inbound mail.

Every write runs in a CHILD process pointed at the sandbox (`ZAELAR_WORKSPACE`, `ZAELAR_DB`, `ZAELAR_LOG_DIR`) and goes
through the engine's own store — the posture of `tests/use_cases/e2e/agent/errand_seed.py`: the test process never
imports a store against its own environment, which is how a script once wrote into the operator's real data.

The channels are the LOOPBACK account's (`loopback/sitecustomize.py`): a send to any of these people is appended to
`<workspace>/loopback/sent.jsonl` and echoed, and never leaves the machine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
LOOPBACK_DIR = Path(__file__).resolve().parent / "loopback"


def _tg(handle: str, chat: str) -> dict:
    return {"platform": "telegram", "handle": handle, "chatId": chat, "source": "operator", "last_seen": 0.0,
            "volume": 0}


#: The people of each language. Two who share a first name (the C1 ambiguity), a second pair (C3's other task), one
#: unambiguous person reachable by Telegram (preferred) and by mail (the channel variant), and one with no channel at
#: all (C6's refusal).
PEOPLE = {
    "es": {
        "ambiguous": "Raquel", "ambiguous2": "Pablo", "single": "Lucía", "unreachable": "Tomás",
        "contacts": [
            {"name": "Raquel Gómez", "channels": [_tg("@raquel_gomez_lb", "700001")]},
            {"name": "Raquel Martín", "channels": [_tg("@raquel_martin_lb", "700002")]},
            {"name": "Pablo Ruiz", "channels": [_tg("@pablo_ruiz_lb", "700003")]},
            {"name": "Pablo Vidal", "channels": [_tg("@pablo_vidal_lb", "700004")]},
            {"name": "Lucía Ferrer", "channels": [_tg("@lucia_ferrer_lb", "700005")],
             "email": "lucia.ferrer@loopback.example", "preferred": "telegram"},
            {"name": "Tomás Rey", "channels": []},
        ],
    },
    "en": {
        "ambiguous": "Rachel", "ambiguous2": "Paul", "single": "Lucy", "unreachable": "Tom",
        "contacts": [
            {"name": "Rachel Green", "channels": [_tg("@rachel_green_lb", "710001")]},
            {"name": "Rachel Brooks", "channels": [_tg("@rachel_brooks_lb", "710002")]},
            {"name": "Paul Hunt", "channels": [_tg("@paul_hunt_lb", "710003")]},
            {"name": "Paul Ward", "channels": [_tg("@paul_ward_lb", "710004")]},
            {"name": "Lucy Fox", "channels": [_tg("@lucy_fox_lb", "710005")],
             "email": "lucy.fox@loopback.example", "preferred": "telegram"},
            {"name": "Tom Reed", "channels": []},
        ],
    },
}

#: The sender of C9's inbound mail.
MAIL_FROM = {"es": ("Facturas ACME", "facturas@acme-loopback.example"),
             "en": ("ACME Billing", "billing@acme-loopback.example")}


def loopback_env(extra: dict | None = None) -> dict:
    """The environment that turns the loopback account on in a sandbox (`spawn_engine(extra_env=...)`)."""
    path = os.pathsep.join(p for p in (str(LOOPBACK_DIR), os.environ.get("PYTHONPATH", "")) if p)
    return {"PYTHONPATH": path, "ZAELAR_TEST_LOOPBACK": "1", **(extra or {})}


def _child_env(workspace: Path) -> dict:
    env = os.environ.copy()
    env.update({"ZAELAR_WORKSPACE": str(workspace), "ZAELAR_DB": str(workspace / "memory" / "_data" / "sandbox.db"),
                "ZAELAR_LOG_DIR": str(workspace / "logs")})
    env.pop("ZAELAR_TEST_LOOPBACK", None)
    return env


def _run(workspace: Path, code: str, data) -> dict:
    (workspace / "memory" / "_data").mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    out = subprocess.run([sys.executable, "-c", code], input=json.dumps(data), cwd=str(ENGINE),
                         env=_child_env(workspace), capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"seed child failed: {out.stderr[-800:]}")
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
    return json.loads(lines[-1]) if lines else {}


_CONTACTS = """
import json, sys, time
from widgets import store
from widgets.contactos import data as cd, model
people = json.loads(sys.stdin.read())
db = cd.load_db()
have = {model.norm(c.get("name")) for c in db.get("contacts") or []}
for p in people:
    if model.norm(p["name"]) in have:
        continue
    c = {"id": f"c{db.get('next_id', 1)}", "kind": "person", "groups": [], "updated": time.strftime("%Y-%m-%d"),
         **p}
    model.normalize(c)
    db.setdefault("contacts", []).append(c)
    db["next_id"] = int(db.get("next_id", 1)) + 1
store.save(cd.WIDGET_ID, db)
print(json.dumps({"contacts": [c["name"] for c in cd.load_db().get("contacts") or []]}))
"""


def seed_people(workspace: Path, lang: str) -> list[str]:
    """Write the language's people into the sandbox's directory. Returns the names READ BACK."""
    return list(_run(Path(workspace), _CONTACTS, PEOPLE[lang]["contacts"]).get("contacts") or [])


_RULE = """
import json, sys
import rules
r = json.loads(sys.stdin.read())
row = rules.add(r["scope"], "pref", "note", r["text"], text=r["text"])
print(json.dumps({"id": row["id"]}))
"""


def seed_rule(workspace: Path, text: str, *, scope: str = "widget:mensajeria") -> str:
    """A standing rule in his words, as the rules table keeps a note (`rules.add(scope, "pref", "note", …)`)."""
    return str(_run(Path(workspace), _RULE, {"scope": scope, "text": text}).get("id") or "")


def drop_rules(workspace: Path, ids: list[str]) -> None:
    _run(Path(workspace), "import json,sys,rules\n[rules.remove(i) for i in json.loads(sys.stdin.read())]\n"
                          "print('{}')", list(ids))


def inbound_mail(workspace: Path, lang: str, subject: str, body: str) -> str:
    """Drop one inbound mail into the loopback inbox; the sandbox publishes it as `connector.msg` within a second."""
    name, addr = MAIL_FROM[lang]
    mid = f"lb-{uuid.uuid4().hex[:8]}"
    msg = {"platform": "email", "senderName": name, "isGroup": False, "chatName": None,
           "body": f"[Asunto: {subject}]\n{body}", "messageId": mid, "chatId": addr, "senderId": addr,
           "subject": subject, "msgid": f"<{mid}@acme-loopback.example>", "authenticated": True, "auth_reason": "",
           "recipients": [], "timestamp": time.time()}
    inbox = Path(workspace) / "loopback" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    tmp = inbox / f"{mid}.tmp"
    tmp.write_text(json.dumps(msg, ensure_ascii=False), encoding="utf-8")
    tmp.rename(inbox / f"{mid}.json")
    return mid


def sent(workspace: Path) -> list[dict]:
    """Every order the loopback account received, oldest first."""
    f = Path(workspace) / "loopback" / "sent.jsonl"
    if not f.exists():
        return []
    out = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out
