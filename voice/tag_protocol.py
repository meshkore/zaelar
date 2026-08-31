#
# voice/tag_protocol.py — zaelar brain-canvas silent tag protocol
#
# Parses the tags that ANY brain emits in its reply to drive the widget canvas.
# Brain-agnostic: imported by hermes_llm.py and any future brain adapter
# (gemini_llm.py, direct_llm.py, ...) so the logic is never duplicated.
#
# Tag vocabulary:
#   [[show:ID]]                       — show a widget (loads its own data)
#   [[close:ID]] / [[close]]          — hide a widget / hide all widgets
#   [[fullscreen:ID]]                 — toggle TRUE OS-level fullscreen for a widget's card (native Fullscreen
#       API; Escape exits it natively). Real bug 2026-07-23: there was NO path for "put it in fullscreen" — the
#       model fabricated success without touching anything. Self-closing counterpart of show/close (same TAG_RE).
#   [[push:ID]]{json}[[/push]]        — hand data from the brain to a widget
#   [[create:ID]]<spec>[[/create]]    — build a new widget on demand
#   [[modify:ID]]<change>[[/modify]]  — edit an existing widget live
#   [[delete:ID]]                     — remove a widget FOR GOOD (folder + its private store)
#   [[widget.data:ID]]{"action":..,"payload":{..}}[[/widget.data]] — mutate a widget's OWN stored data (same
#       contract as that widget's apply_action) — e.g. add/remove an agenda item. HERMES-ONLY: the fast/duo layer
#       must never emit this directly (enforced in voice/engine/llm/providers/duo.py, not just prompted) — any
#       widget data change goes through Hermes via [[deep]] first. See widgets/__init__.py:dispatch_tag.
#
# MeshKore cluster channel (connectors/meshkore/) — talk to OTHER agents, never spoken:
#   [[cluster.connect]]{json}[[/cluster.connect]]     — join a cluster ({name,cluster_id,token,handle})
#   [[cluster.send:NAME]]{json}[[/cluster.send]]      — send to a cluster ({to:"handle|*", text})
#   [[cluster.done:NAME]]                             — the joint task is concluded (stops the heartbeat)
#   [[cluster.disconnect:NAME]]                       — leave a cluster
#
# Native Hermes cron channel (brains/hermes/cron.py) — schedule proactive tasks/reminders, never spoken:
#   [[cron.create]]{json}[[/cron.create]]   — schedule a job ({schedule:"30m"|"every 2h"|"0 9 * * *", prompt, name, repeat})
#   [[cron.cancel:NAME]]                     — cancel a job by name/id
#
# Two-speed escalation (brains/duo/) — the fast orchestrator hands a turn to the deep brain (Hermes), never spoken:
#   [[deep]]<request for the deep brain>[[/deep]]  — run this in the background on Hermes (memory/tools/reasoning);
#                                                    the fast brain speaks a holding line FIRST, then emits this.
#
# Architect provider (connectors/architect/) — delegate project/code work to the MeshKore daemon, never spoken:
#   [[architect.ask:PROJECT]]<natural-language intent>[[/architect.ask]] — async ask to the project's manager
#   [[architect.new]]{json}[[/architect.new]]                            — create a project ({name, parent?})
#
# Unified messaging (connectors/messaging/) — control the triaged inbox (WhatsApp+Telegram+…), never spoken:
#   [[msg.open:N]] / [[msg.close]]        — open chat N (grouped list) / go back to the chat list
#   [[msg.readchat:N]]                    — mark an entire chat N as read without opening it
#   [[msg.read:N]] / [[msg.dismiss:N]]    — mark read / hide a single message N — only meaningful with a chat open
#   [[msg.clear]]                         — mark everything (all chats) read
#
import json
import re

TAG_RE    = re.compile(r"\[\[\s*(show|close|delete|fullscreen)\s*(?::\s*([a-zA-Z0-9_-]+))?\s*\]\]", re.I)
# [[move:ID:where]] — reposition a widget on the canvas (pure UI, like show/close). where ∈ left|right|center|
# top|bottom (+ combinations such as top-left) or their Spanish synonyms (izquierda/derecha/centro/arriba/abajo).
MOVE_RE   = re.compile(r"\[\[\s*move\s*:\s*([a-zA-Z0-9_-]+)\s*:\s*([a-zA-Záéíóúñ -]+?)\s*\]\]", re.I)
# [[resize:ID]]{"width":200,"height":340}[[/resize]] — resize a widget (width/height in pixels). The body
# is JSON with optional width and/or height. HERMES-ONLY (not safe). Emitted in a separate fragment (never spoken).
RESIZE_RE = re.compile(r"\[\[\s*resize\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/?\s*resize\s*\]\]", re.S | re.I)
PUSH_RE   = re.compile(r"\[\[\s*push\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/\s*push\s*\]\]", re.S | re.I)
CREATE_RE = re.compile(r"\[\[\s*create\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/\s*create\s*\]\]", re.S | re.I)
MODIFY_RE = re.compile(r"\[\[\s*modify\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/\s*modify\s*\]\]", re.S | re.I)
WIDGET_DATA_RE = re.compile(r"\[\[\s*widget\.data\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/\s*widget\.data\s*\]\]", re.S | re.I)
# MeshKore: block tags carry a JSON body; control tags are self-closing (optional :NAME).
CX_CONNECT_RE = re.compile(r"\[\[\s*cluster\.connect\s*\]\](.*?)\[\[\s*/\s*cluster\.connect\s*\]\]", re.S | re.I)
CX_SEND_RE    = re.compile(r"\[\[\s*cluster\.send\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/\s*cluster\.send\s*\]\]", re.S | re.I)
CX_PACT_RE    = re.compile(r"\[\[\s*cluster\.pact\s*:\s*([a-zA-Z0-9_-]+)\s*\]\](.*?)\[\[\s*/\s*cluster\.pact\s*\]\]", re.S | re.I)
CX_CTRL_RE    = re.compile(r"\[\[\s*cluster\.(done|disconnect)\s*(?::\s*([a-zA-Z0-9_-]+))?\s*\]\]", re.I)
# Native cron: create carries a JSON body; cancel is self-closing with an optional :NAME.
CRON_CREATE_RE = re.compile(r"\[\[\s*cron\.create\s*\]\](.*?)\[\[\s*/\s*cron\.create\s*\]\]", re.S | re.I)
CRON_CANCEL_RE = re.compile(r"\[\[\s*cron\.cancel\s*(?::\s*([a-zA-Z0-9_-]+))?\s*\]\]", re.I)
# Two-speed: the fast brain escalates a turn to Hermes. Block form only (always carries the request body); the
# body may be empty (the duo processor then falls back to the raw user utterance). Never spoken.
DEEP_RE = re.compile(r"\[\[\s*deep\s*\]\](.*?)\[\[\s*/\s*deep\s*\]\]", re.S | re.I)
# Safety net: a fast/non-reasoning brain can answer a data question with raw JSON(-ish) prose instead of wrapping
# it in a proper tag (seen live: BRAIN=duo describing the widget catalog as spoken JSON — INI-008 follow-up
# 2026-07-05; a botched tool-call attempt writing `{q: "..."}` with an UNQUOTED key — INI-013 2026-07-08 early morning,
# deep-dive wave A). Never speak that. Matches the OPENING of an object with a key (quoted `{"title":` or
# a bare identifier `{q:`) — a pattern that's essentially never legitimate prose in any of our target languages.
JSON_LEAK_RE = re.compile(r'\{\s*(?:"[^"{}]{1,60}"|[A-Za-z_][A-Za-z0-9_]{0,30})\s*:')
# Same idea for our OWN bracket-tag syntax: a model can invent a tag name that doesn't exist in the vocabulary
# above (seen live: `[[search]]{q: "..."}` — "search" is a widget id, not a real tag; the vocabulary only has
# [[show:ID]]) and it's the wrong side of the same bug (mimicking OUR OWN protocol instead of really following
# it). By the point this runs, every REAL *self-closing* tag has already been stripped by the loops above —
# anything still `[[...]]`-shaped is either genuinely unrecognized, or the OPENER of a real BLOCK tag
# (push/create/modify/widget.data/cluster.connect/cluster.send/cron.create/architect.ask/architect.new/deep)
# whose body+closer just hasn't streamed in yet. Those two cases look byte-for-byte identical to a regex looking
# only at what's landed so far — `[[push:x]]` alone is indistinguishable from an invented self-closing tag. The
# negative lookahead excludes every known block-tag prefix so this pass NEVER deletes a real opener: the
# existing hold-back logic below (the `for marker, closer in (...)` loop) keeps protecting it until its closer
# arrives, exactly like before this safety net existed. A REAL bug fixed 2026-07-08 (INI-013 code review):
# without the exclusion, `[[widget.data:agenda]]` streamed as its own chunk got deleted as "unknown" before its
# `[[/widget.data]]` closer ever arrived — silently breaking every widget mutation, cluster/cron/architect
# dispatch, and duo's own escalation under normal token-by-token streaming (verified with a live repro).
UNKNOWN_BRACKET_RE = re.compile(
    r"\[\[(?!\s*(?:push|create|modify|resize|widget\.data|cluster\.connect|cluster\.send|cluster\.pact|cron\.create|"
    r"architect\.ask|architect\.new|deep)\b).*?\]\]",
    re.S | re.I,
)
# Architect provider: ask carries a plain-text intent (project ids may have dots/hyphens); new carries JSON.
ARCH_ASK_RE = re.compile(r"\[\[\s*architect\.ask\s*:\s*([a-zA-Z0-9_.-]+)\s*\]\](.*?)\[\[\s*/\s*architect\.ask\s*\]\]", re.S | re.I)
ARCH_NEW_RE = re.compile(r"\[\[\s*architect\.new\s*\]\](.*?)\[\[\s*/\s*architect\.new\s*\]\]", re.S | re.I)
# Unified messaging (connectors/messaging/, INI-015): operator-only, self-closing. read/dismiss carry the item
# number (the numbered COMBINED list — WhatsApp+Telegram+… — the brain sees in the messaging brief); clear marks
# everything shown as read. The action routes to the right connector by the item's platform. Never spoken.
MSG_RE = re.compile(r"\[\[\s*msg\.(read|dismiss|clear|open|close|readchat)\s*(?::\s*(\d+))?\s*\]\]", re.I)


def parse_json(raw: str):
    """Decode JSON from a string that may be fenced (```json ... ```) or plain, or have trailing prose after
    the object closes (a leaked tool-call blob captured by JSON_LEAK_RE can carry text after the `}` — only the
    leading object is ours to parse). Returns None on failure."""
    raw = (raw or "").strip()
    for candidate in (raw, raw.strip("`"), re.sub(r"^json\s*", "", raw.strip("`").strip(), flags=re.I)):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw)
        return obj
    except Exception:
        return None


def strip_tags(buf: str, emit_fn, final: bool):
    """
    Extract and emit widget tags from *buf*. Return ``(spoken, new_buf)``.

    spoken  — text safe to speak now (all complete tags stripped).
    new_buf — partial/incomplete tag(s) held back for the next chunk.

    emit_fn(action: str, extra: dict) is called once per complete tag found.
    It is NEVER called with partial tag text — the hold logic below ensures
    a tag that splits across two streamed chunks is caught whole.

    Set final=True on the last chunk of a turn to flush any held remainder.
    """
    # Remove complete push blocks (data → widget; never spoken).
    while True:
        m = PUSH_RE.search(buf)
        if not m:
            break
        emit_fn("show", {"id": m.group(1).lower(), "data": parse_json(m.group(2))})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete create blocks (spec → new widget; never spoken).
    while True:
        m = CREATE_RE.search(buf)
        if not m:
            break
        emit_fn("create", {"id": m.group(1).lower(), "spec": (m.group(2) or "").strip()})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete modify blocks (change → existing widget; never spoken).
    while True:
        m = MODIFY_RE.search(buf)
        if not m:
            break
        emit_fn("modify", {"id": m.group(1).lower(), "change": (m.group(2) or "").strip()})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete widget.data blocks (mutate a widget's OWN store; HERMES-ONLY, never spoken).
    while True:
        m = WIDGET_DATA_RE.search(buf)
        if not m:
            break
        emit_fn("widget.data", {"id": m.group(1).lower(), "data": parse_json(m.group(2))})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete cluster.connect / cluster.send blocks (JSON body → the MeshKore bridge; never spoken).
    while True:
        m = CX_CONNECT_RE.search(buf)
        if not m:
            break
        emit_fn("cluster.connect", {"data": parse_json(m.group(1))})
        buf = buf[:m.start()] + buf[m.end():]
    while True:
        m = CX_SEND_RE.search(buf)
        if not m:
            break
        emit_fn("cluster.send", {"name": m.group(1).lower(), "data": parse_json(m.group(2)), "raw": (m.group(2) or "").strip()})
        buf = buf[:m.start()] + buf[m.end():]
    # cluster.pact (V2-072): NEGOTIATED rules for this agent-to-agent conversation ({to?,cadence_s?,medium?,scope?,note?}).
    while True:
        m = CX_PACT_RE.search(buf)
        if not m:
            break
        emit_fn("cluster.pact", {"name": m.group(1).lower(), "data": parse_json(m.group(2))})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete cron.create blocks (JSON body → native Hermes cron; never spoken).
    while True:
        m = CRON_CREATE_RE.search(buf)
        if not m:
            break
        emit_fn("cron.create", {"data": parse_json(m.group(1))})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete architect blocks (delegation to the MeshKore daemon's project managers; never spoken).
    while True:
        m = ARCH_ASK_RE.search(buf)
        if not m:
            break
        emit_fn("architect.ask", {"project": m.group(1).lower(), "request": (m.group(2) or "").strip()})
        buf = buf[:m.start()] + buf[m.end():]
    while True:
        m = ARCH_NEW_RE.search(buf)
        if not m:
            break
        emit_fn("architect.new", {"data": parse_json(m.group(1))})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove unified messaging control tags (self-closing; operator-only; never spoken).
    while True:
        m = MSG_RE.search(buf)
        if not m:
            break
        extra = {}
        if m.group(2):
            extra["n"] = int(m.group(2))
        emit_fn("msg." + m.group(1).lower(), extra)
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete deep blocks (fast→Hermes escalation; never spoken). The body is the request for the deep brain.
    while True:
        m = DEEP_RE.search(buf)
        if not m:
            break
        emit_fn("deep", {"request": (m.group(1) or "").strip()})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete move tags (reposition a widget on the canvas; pure UI, never spoken).
    while True:
        m = MOVE_RE.search(buf)
        if not m:
            break
        emit_fn("move", {"id": m.group(1).lower(), "where": (m.group(2) or "").strip().lower()})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete resize blocks (HERMES-ONLY resize; JSON body with width/height; never spoken).
    while True:
        m = RESIZE_RE.search(buf)
        if not m:
            break
        emit_fn("resize", {"id": m.group(1).lower(), "data": parse_json(m.group(2))})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove complete show / close tags.
    while True:
        m = TAG_RE.search(buf)
        if not m:
            break
        emit_fn(m.group(1).lower(), {"id": (m.group(2) or "").lower()})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove self-closing cluster control tags (done / disconnect).
    while True:
        m = CX_CTRL_RE.search(buf)
        if not m:
            break
        emit_fn("cluster." + m.group(1).lower(), {"name": (m.group(2) or "").lower()})
        buf = buf[:m.start()] + buf[m.end():]

    # Remove self-closing cron.cancel tags.
    while True:
        m = CRON_CANCEL_RE.search(buf)
        if not m:
            break
        emit_fn("cron.cancel", {"name": (m.group(1) or "").lower()})
        buf = buf[:m.start()] + buf[m.end():]

    # Every REAL tag is gone by now — any COMPLETE `[[...]]` still standing is an invented/malformed one.
    # Drop it (never speak raw bracket syntax) instead of leaking it as literal text.
    while True:
        m = UNKNOWN_BRACKET_RE.search(buf)
        if not m:
            break
        emit_fn("unknown_tag_dropped", {"text": buf[m.start():m.end()][:4000]})
        buf = buf[:m.start()] + buf[m.end():]

    if final:
        # Last-resort net: if a JSON-looking blob slipped through OUTSIDE any recognized tag (a brain answered a
        # data question with raw JSON prose instead of a proper [[push]]), cut it and everything after it — never
        # speak it. This is a bug in the CALLER's tag usage, not something to silently "fix" by guessing intent.
        m = JSON_LEAK_RE.search(buf)
        if m:
            # Untruncated: a caller (duo.py, 2026-07-08) parses this as JSON to recover a botched tool call —
            # a fast layer that meant to call escalate_to_hermes/set_style_directive but wrote the JSON body as
            # plain content instead. 4000 chars comfortably covers any realistic turn (max_tokens caps it lower).
            emit_fn("json_leak_dropped", {"text": buf[m.start():m.start() + 4000]})
            buf = buf[:m.start()]
        return buf, ""

    # Hold back anything that could be the opening of an unclosed tag so we
    # never speak a partial tag and never miss one that spans two chunks.
    # CRITICAL: hold from the start of "[["  — never from a lone trailing "["
    # (that would leak "[" into speech AND the tag would never match again).
    hold = len(buf)
    lo = buf.lower()

    jm = JSON_LEAK_RE.search(buf)
    if jm:
        hold = min(hold, jm.start())   # hold from the "{" onward — never leak it token by token while streaming

    # JSON_LEAK_RE only matches once the WHOLE `{"key":` shape is visible — under real token-by-token streaming
    # (seen live 2026-07-08: a fast model botching a tool call wrote `{"request": "..."}` as plain content) the
    # opening `{` and several chars after it get spoken in an EARLIER chunk, before the pattern ever completes.
    # Same idea as the `[[` marker below: hold from ANY unclosed brace immediately, don't wait to recognize the
    # full shape — false positives (a stray "{" that never becomes JSON) just sit in the hold buffer one extra
    # chunk, they still get spoken once "}" closes and it turns out not to match on the final pass.
    # find() (not rfind()) deliberately: if the buffer ever has TWO separate unclosed "{" (e.g. two botched
    # attempts in one completion), we must hold from the EARLIER one — anchoring on the later one would let
    # everything up to and including the first "{" leak through (2026-07-08 code review).
    c = buf.find("{")
    if c != -1 and "}" not in buf[c:]:
        hold = min(hold, c)

    for marker, closer in (("[[push", "[[/push]]"), ("[[create", "[[/create]]"), ("[[modify", "[[/modify]]"),
                           ("[[widget.data", "[[/widget.data]]"),
                           ("[[cluster.connect", "[[/cluster.connect]]"), ("[[cluster.send", "[[/cluster.send]]"),
                           ("[[cluster.pact", "[[/cluster.pact]]"),
                           ("[[cron.create", "[[/cron.create]]"), ("[[deep", "[[/deep]]"),
                           ("[[resize", "[[/resize]]"),
                           ("[[architect.ask", "[[/architect.ask]]"), ("[[architect.new", "[[/architect.new]]")):
        p = lo.rfind(marker)
        if p != -1 and closer not in lo[p:]:
            hold = min(hold, p)

    b = buf.rfind("[[")
    if b != -1 and "]]" not in buf[b:]:
        hold = min(hold, b)

    if buf.endswith("[") and not buf.endswith("[["):
        hold = min(hold, len(buf) - 1)

    return buf[:hold], buf[hold:]
