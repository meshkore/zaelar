"""V2-645 — a group message carries the group's SUBJECT, never its bare numeric id.

Measured live (2026-09-09): every WhatsApp group event shipped chatName = the id digits, so «el grupo del
viaje a La Mella» was unfindable BY NAME in the thread store and the communications archive — the whole
name-addressed design downstream was paper over a number. The bridge is vendored JS with no harness of its
own, so this pins the SEAM in source, comment-stripped (the V2-573 lesson): the event construction must
resolve the subject through the cached groupMetadata door, with the digits only as a last resort.
"""
import pathlib
import re

BRIDGE = pathlib.Path("connectors/whatsapp/bridge/bridge.js")


def _stripped() -> str:
    src = BRIDGE.read_text(encoding="utf-8")
    return re.sub(r"//[^\n]*", "", src)


def test_the_event_resolves_the_group_subject_not_the_id():
    src = _stripped()
    assert "async function groupSubject" in src, "the cached subject resolver is gone"
    assert "groupMetadata" in src
    m = re.search(r"chatName:\s*isGroup\s*\?\s*\(\(await groupSubject\(chatId\)\)", src)
    assert m, "the message event no longer walks through the subject resolver"


def test_a_failed_lookup_is_not_cached_so_the_next_message_retries():
    src = _stripped()
    fn = src.split("async function groupSubject", 1)[1].split("}\n", 3)
    body = "async function groupSubject" + "}\n".join(fn[:3])
    assert "if (subject) groupSubjects.set" in body, \
        "caching an empty subject would freeze the id-digits fallback forever"
