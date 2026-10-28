# Where a NEW inbound message also goes, besides the inbox: the contact directory, the canonical archive and
# central memory. All three best-effort — none may break the UI store that called them.


def _to_directory(platform: str, items: list[dict]) -> None:
    """V2-683 — passive channel learning (V2-052's closed decision 3). Every inbound already carries an
    identity for its platform, so the contacts the operator really talks to build their own channel list and
    «escríbele a Iván» stops needing to ask which app. The whole decision — who this is, whether it is
    unambiguous, what may be written — lives in `widgets/directory.py`; this is only the fan-out, in the
    same place and with the same stance as `_to_memory`/`_to_archive`: best-effort, never breaks the store."""
    if not items:
        return
    try:
        from widgets import directory
        directory.note_many(platform, items)
    except Exception:  # noqa: BLE001
        pass


def _to_archive(items: list[dict], platform: str | None = None, chat_id=None, **kw) -> None:
    """V2-628 — the canonical communications log. This store and the `msg` pills both EXPIRE by design (replay
    cache and recall salience); the archive is the one permanent, catalogued copy, so «a message from a month
    ago» stays answerable. Same stance as `_to_memory`: best-effort, never breaks the UI store."""
    try:
        from connectors.messaging import archive
        if platform is None:
            archive.record_items(items)
        else:
            archive.record(platform, chat_id, items, **kw)
    except Exception:  # noqa: BLE001
        pass


def _to_memory(items: list[dict]) -> None:
    """Dump inbound messages into central memory as `kind='msg'` memories at `short` level (V2-003 · T57).
    Fire-and-forget through the memory queue; best-effort — a failure here does NOT affect the UI store or triage.
    The per-widget store remains for UI state; memory is for recall.

    Goes through `memory.ingest_message` (the unified TYPED path, multi-source 2026-07-10): indexes `source`
    (platform) + `entity` (sender) in `meta` -> the brain can query BY TYPE with `recent_by_source`, without the
    retriever. `trust='external'` = owner's personal connector."""
    if not items:
        return
    try:
        from memory import api as memapi
    except Exception:
        return
    for it in items:
        try:
            body = (it.get("body") or "").strip()
            if not body:
                continue
            memapi.ingest_message(it.get("platform") or "?", it.get("from") or "?", body,
                                  group=it.get("group"), directed=bool(it.get("dirigido_a_mi")),
                                  trust="external")
        except Exception:
            continue
