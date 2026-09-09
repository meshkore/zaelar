#
# digest.py — the per-chat digest over the archive (V2-628 F3): the 200-messages-unread promise.
#
# One LIVING state per chat — open actions (a booking to make, a payment owed, a gift to buy), deadlines,
# and a one-line position — distilled by the HEART's model machinery from the canonical archive, upserted
# (never accumulated: no new pill stream, no growth). It answers «do I need to do anything from <group>?»
# without the operator reading the thread, and beyond `peek`'s in-turn budget.
#
# Division of labour, per the domain-stores doctrine:
#   - this module OWNS the table and the distillation prompt (domain data, lives in archive.db);
#   - the LLM hook is INJECTED by the caller (nucleo/loop wires `memllm.chat_sync` in, the same
#     `synthesize_fn` pattern `memory/rem.py` lives by — connectors do not import brains);
#   - writing anything to the AGENDA from a digest is deliberately NOT here (F3b, needs the operator's
#     explicit OK: an agent creating reminders out of group chatter is his call, not a default).
#
# Cadence discipline (the caller checks `enabled()`, we gate per chat): a chat is digested only when the
# archive holds NEW messages since its last digest AND the conversation has settled (quiet for
# _SETTLE_S) — so an active back-and-forth is never distilled mid-flight and an idle chat costs zero.
# Kill-switch: ZAELAR_CHAT_DIGEST=0. Every public entry point is best-effort, like the archive's.
#
import json
import os
import time

from . import archive

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_digests(
  platform    TEXT NOT NULL,
  chat_id     TEXT NOT NULL,
  chat_name   TEXT NOT NULL DEFAULT '',
  updated_ts  REAL NOT NULL,
  last_msg_ts REAL NOT NULL,
  msg_count   INTEGER NOT NULL DEFAULT 0,
  digest_json TEXT NOT NULL,
  PRIMARY KEY (platform, chat_id)
);
"""

_WINDOW_DAYS = 7          # how far back a digest reads
_MIN_MSGS = 3             # fewer messages than this is not worth a model call
_SETTLE_S = 30 * 60       # a chat still moving is not digested yet
_MAX_MSGS = 200           # per-chat read budget (newest win)
_MAX_BODY = 300           # per-message body budget in the prompt

_SYSTEM = (
    "You distill ONE chat conversation into a small JSON state for a personal assistant. "
    "Return ONLY a JSON object: {\"summary\": one short sentence (the current position of the "
    "conversation), \"open_actions\": [{\"what\": short imperative, \"due\": \"YYYY-MM-DD\" or \"\"}], "
    "\"deadlines\": [\"short line with its date\"]}. "
    "open_actions holds ONLY things the OWNER of this assistant still has to do (a reply owed, a booking, "
    "a payment, a form, a gift) — never things already done, never other people's tasks. Empty lists are "
    "correct and common. Write the VALUES in the language of the conversation."
)


def enabled() -> bool:
    return os.getenv("ZAELAR_CHAT_DIGEST", "1").strip().lower() not in ("0", "false", "no", "off")


def _conn():
    conn = archive._conn()
    conn.executescript(_SCHEMA)
    return conn


def _due_chats(now: float, limit: int) -> list[dict]:
    """Chats whose archive moved past their digest and have settled. Newest movement first."""
    cut = now - _WINDOW_DAYS * 86400
    rows = _conn().execute(
        "SELECT m.platform, m.chat_id, MAX(m.chat_name) chat_name, MAX(m.ts) last_ts, COUNT(*) n "
        "FROM messages m WHERE m.ts >= ? GROUP BY m.platform, m.chat_id", (cut,)).fetchall()
    out = []
    for r in rows:
        if r["n"] < _MIN_MSGS or (now - r["last_ts"]) < _SETTLE_S:
            continue
        d = _conn().execute("SELECT last_msg_ts FROM chat_digests WHERE platform=? AND chat_id=?",
                            (r["platform"], r["chat_id"])).fetchone()
        if d is not None and r["last_ts"] <= d["last_msg_ts"]:
            continue
        out.append(dict(r))
    out.sort(key=lambda r: -r["last_ts"])
    return out[:limit]


def _chat_transcript(platform: str, chat_id: str, since: float) -> tuple[str, int, float]:
    rows = _conn().execute(
        "SELECT sender, direction, ts, body FROM messages WHERE platform=? AND chat_id=? AND ts>=? "
        "ORDER BY ts DESC LIMIT ?", (platform, chat_id, since, _MAX_MSGS)).fetchall()
    rows = list(reversed(rows))
    lines = []
    last_ts = 0.0
    for r in rows:
        who = "me" if r["direction"] == "out" else (r["sender"] or "?")
        day = time.strftime("%Y-%m-%d", time.localtime(r["ts"]))
        lines.append(f"[{day}] {who}: {(r['body'] or '')[:_MAX_BODY]}")
        last_ts = max(last_ts, float(r["ts"]))
    return "\n".join(lines), len(rows), last_ts


def _parse(content: str) -> dict | None:
    """The model's JSON, tolerantly: a fence or prose around the object is stripped, anything else is a miss."""
    s = (content or "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(s[a:b + 1])
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    return {"summary": str(d.get("summary") or "")[:300],
            "open_actions": [a for a in (d.get("open_actions") or []) if isinstance(a, dict)][:10],
            "deadlines": [str(x)[:200] for x in (d.get("deadlines") or []) if x][:10]}


def refresh_due(llm_fn, *, max_chats: int = 5, now: float | None = None) -> dict:
    """The idle HEART pass: digest every due chat, bounded. `llm_fn(system, user) -> str|None` is injected
    (fail-open per chat: a mute model leaves the previous digest standing, never a hole)."""
    now = float(now or time.time())
    report = {"considered": 0, "digested": 0, "failed": 0}
    if not enabled():
        return report
    try:
        due = _due_chats(now, max_chats)
    except Exception:  # noqa: BLE001
        return report
    for r in due:
        report["considered"] += 1
        try:
            text, n, last_ts = _chat_transcript(r["platform"], r["chat_id"], now - _WINDOW_DAYS * 86400)
            today = time.strftime("%Y-%m-%d", time.localtime(now))
            user = (f"Today is {today}. Chat: «{r['chat_name'] or r['chat_id']}» "
                    f"({r['platform']}).\n{text}")
            parsed = _parse(llm_fn(_SYSTEM, user) or "")
            if parsed is None:
                report["failed"] += 1
                continue
            _conn().execute(
                "INSERT INTO chat_digests(platform, chat_id, chat_name, updated_ts, last_msg_ts, "
                "msg_count, digest_json) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(platform, chat_id) DO UPDATE SET chat_name=excluded.chat_name, "
                "updated_ts=excluded.updated_ts, last_msg_ts=excluded.last_msg_ts, "
                "msg_count=excluded.msg_count, digest_json=excluded.digest_json",
                (r["platform"], r["chat_id"], r["chat_name"] or "", now, last_ts, n,
                 json.dumps(parsed, ensure_ascii=False)))
            _conn().commit()
            report["digested"] += 1
        except Exception:  # noqa: BLE001
            report["failed"] += 1
    return report


def get(platform: str, chat_id) -> dict | None:
    try:
        r = _conn().execute("SELECT * FROM chat_digests WHERE platform=? AND chat_id=?",
                            (str(platform), str(chat_id))).fetchone()
        return _row(r) if r else None
    except Exception:  # noqa: BLE001
        return None


def find(chat: str | None = None, *, only_open: bool = False, limit: int = 10) -> list[dict]:
    """Digests by chat-name substring (case-insensitive), or all of them; `only_open` keeps chats that
    still carry open actions — the shape of «¿tengo algo pendiente de mis grupos?»."""
    try:
        if chat and str(chat).strip():
            rows = _conn().execute(
                "SELECT * FROM chat_digests WHERE chat_name LIKE ? COLLATE NOCASE "
                "ORDER BY last_msg_ts DESC LIMIT ?", (f"%{chat}%", int(limit))).fetchall()
        else:
            rows = _conn().execute(
                "SELECT * FROM chat_digests ORDER BY last_msg_ts DESC LIMIT ?", (int(limit),)).fetchall()
        out = [_row(r) for r in rows]
        if only_open:
            out = [d for d in out if d["digest"].get("open_actions")]
        return out
    except Exception:  # noqa: BLE001
        return []


def _row(r) -> dict:
    try:
        digest = json.loads(r["digest_json"])
    except Exception:  # noqa: BLE001
        digest = {"summary": "", "open_actions": [], "deadlines": []}
    return {"platform": r["platform"], "chat_id": r["chat_id"], "chat_name": r["chat_name"],
            "updated_ts": r["updated_ts"], "last_msg_ts": r["last_msg_ts"],
            "msg_count": r["msg_count"], "digest": digest}
