# The catalogued LOOKUPS over the archive: a structured search, how common a word is here, and the ranked answer
# to a free-text question.


def search(q: str | None = None, *, sender: str | None = None, chat: str | None = None,
           platform: str | None = None, since: float | None = None, until: float | None = None,
           direction: str | None = None, limit: int = 20) -> list[dict]:
    """The catalogued lookup the platforms never gave us. `q` walks the FTS index; every other argument is a
    structured filter (sender/chat match by substring, case-insensitive — the operator says «the school», not
    an exact display name). Newest first."""
    try:
        conn = _svc._conn()
        where, args = [], []
        if q and str(q).strip():
            fts = " ".join('"' + t.replace('"', "") + '"' for t in str(q).split())
            where.append("m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
            args.append(fts)
        for field, val in (("sender", sender), ("chat_name", chat)):
            if val and str(val).strip():
                where.append(f"m.{field} LIKE ? COLLATE NOCASE")
                args.append(f"%{val}%")
        if platform:
            where.append("m.platform = ?"); args.append(str(platform))
        if direction in ("in", "out"):
            where.append("m.direction = ?"); args.append(direction)
        if since is not None:
            where.append("m.ts >= ?"); args.append(float(since))
        if until is not None:
            where.append("m.ts <= ?"); args.append(float(until))
        sql = "SELECT m.* FROM messages m"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY m.ts DESC LIMIT ?"
        args.append(max(1, min(int(limit or 20), 200)))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _fts_term(t: str) -> str:
    return '"' + str(t).replace('"', "") + '"'


def doc_count(term: str) -> int:
    """How many archived messages contain `term` (FTS) — how COMMON a word is here. 0 on any failure."""
    try:
        conn = _svc._conn()
        return int(conn.execute("SELECT count(*) FROM messages_fts WHERE messages_fts MATCH ?",
                                (_fts_term(term),)).fetchone()[0])
    except Exception:  # noqa: BLE001
        return 0


def ranked(terms: list[str], *, platform: str | None = None, limit: int = 8) -> list[dict]:
    """Messages matching ANY of `terms`, best first by BM25 — the free-text question's lookup.

    `search()` ANDs every word, which is right for a structured `q` and wrong for a sentence: «has inworld sent
    any email recently» matches nothing, because no message holds all seven words. BM25 over an OR weighs each
    word by how rare it is here, so the one that names the sender outranks «email» and «any» without anybody
    having to list which words are filler — in any language."""
    terms = [t for t in (str(x).strip() for x in (terms or [])) if t][:12]
    if not terms:
        return []
    try:
        conn = _svc._conn()
        named = _svc._naming_terms(conn, terms)
        if named:
            return _ranked_by_name(conn, named, platform=platform, limit=limit)
        sql = ("SELECT m.*, bm25(messages_fts) AS score FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid"
               " WHERE messages_fts MATCH ?")
        args: list = [" OR ".join(_fts_term(t) for t in terms)]
        if platform:
            sql += " AND m.platform = ?"
            args.append(str(platform))
        sql += " ORDER BY score LIMIT ?"
        args.append(max(1, min(int(limit or 8), 50)))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _naming_terms(conn, terms: list[str]) -> list[str]:
    """The words of a question that NAME a sender or a chat: they appear in the sender/chat_name column, and they
    are among the less common words of the question here (a group called «The …» must not make «the» a name).

    Demo pass 35 (2026-09-29, E1): «Is there any email from Inworld (inworld.ai) in the inbox? What is it about and
    when did it arrive?» ranked four long Telegram posts first — BM25 over the OR of thirteen words adds up the
    filler, and a trading channel holds a lot of it. No list of filler words, in any language: the column says
    who is a sender, and the counts say which words are common."""
    df = {t: doc_count(t) for t in terms}
    seen = sorted(n for n in df.values() if n > 0)
    if not seen:
        return []
    median = seen[len(seen) // 2]
    # …or rare in the ARCHIVE as a whole (demo pass 46, 2026-09-29): «inworld» had grown to 21 messages — every
    # earlier forward of the receipt mentions it — past the question's median word (10), and stopped being read
    # as a sender. A word in under 2% of everything we hold is not filler whatever the question around it.
    try:
        total = int(conn.execute("SELECT count(*) FROM messages").fetchone()[0])
    except Exception:  # noqa: BLE001
        total = 0
    out = []
    for t in terms:
        if not df[t] or (df[t] > median and not (total and df[t] <= 0.02 * total)):
            continue
        hit = conn.execute("SELECT count(*) FROM messages_fts WHERE messages_fts MATCH ?",
                           ("{sender chat_name}: " + _fts_term(t),)).fetchone()[0]
        if hit:
            out.append(t)
    return out


def _ranked_by_name(conn, named: list[str], *, platform: str | None, limit: int) -> list[dict]:
    """Rows from the named sender/chat first, then rows that only mention the name — each group by BM25 over the
    naming words alone, so filler never weighs in."""
    q = " OR ".join(_fts_term(t) for t in named)
    lim = max(1, min(int(limit or 8), 50))
    base = ("SELECT m.*, bm25(messages_fts) AS score FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid"
            " WHERE messages_fts MATCH ?")
    tail = (" AND m.platform = ?" if platform else "") + " ORDER BY score LIMIT ?"
    out, ids = [], set()
    for match in ("{sender chat_name}: (" + q + ")", q):
        args: list = [match] + ([str(platform)] if platform else []) + [lim]
        for r in conn.execute(base + tail, args).fetchall():
            if r["id"] not in ids and len(out) < lim:
                ids.add(r["id"])
                out.append(dict(r))
    return out


# Read back through the facade (V2-778 F1): tests patch `_db_path`/`_conn`/`_naming_terms` there.
from connectors.messaging import archive as _svc  # noqa: E402
