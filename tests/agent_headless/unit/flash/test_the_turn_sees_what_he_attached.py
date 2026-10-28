"""V2-809 — the turn sees the file he just attached to the chat, and only while it is his latest attachment.

«¿qué pone en esta foto?» / «resume este PDF» act on THAT file because the reference rides the turn as STATE
(`files/attachments.current()` → one line of the live block) carrying the reading made at upload — not because a
word in the question is recognised. So the cases here are about the state, never about phrasings:

  · an attachment puts its line (name, kind, size, reading) in the live block; none puts NOTHING there;
  · a removed chip or an expired attachment leaves the turn; many attachments share one budget;
  · a file that could not be read says so, so the model does not invent its contents;
  · the image is read by the `image_reader` model with the image ITSELF as a content part, downscaled, metered;
  · the readers are bounded: a PDF stops at its page cap, an image over the pixel cap is not decoded.
"""
from __future__ import annotations

import base64
import io
import time

import pytest

from files import attachments as att


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from memory import db as memdb
    memdb.reset_db()
    att._reset_for_tests()
    att.limits()
    yield
    att._reset_for_tests()
    memdb.reset_db()


def _attach(eid, name, kind, reading="", why=""):
    att.save_reading(eid, reading)
    att.attach({"episode_id": eid, "name": name, "kind": kind, "mime": "", "bytes": 2048, "why_not": why})


def test_no_attachment_adds_nothing_to_the_turn():
    from nucleo.flash.prompt import live_state
    assert att.prompt_lines() == []
    assert "ADJUNTO" not in live_state()


def test_the_attachment_rides_the_turn_with_its_reading():
    from nucleo.flash.prompt import live_state
    _attach(41, "ticket.jpg", "image", "Receipt from Bar Pepe. Total 23,40 EUR")
    live = live_state()
    assert "«ticket.jpg» · image · 2 KB" in live and "Total 23,40 EUR" in live


def test_a_removed_or_expired_attachment_leaves_the_turn():
    _attach(1, "a.pdf", "pdf", "first")
    _attach(2, "b.txt", "text", "second")
    assert [r["episode_id"] for r in att.current()] == [2, 1], "newest first"
    att.detach(2)
    assert [r["episode_id"] for r in att.current()] == [1]
    assert att.prompt_lines(now=time.time() + att.TTL_S + 1) == []


def test_many_attachments_share_one_budget(monkeypatch):
    monkeypatch.setitem(att._limits_cache, "turn_chars_per_file", 1000)
    monkeypatch.setitem(att._limits_cache, "turn_chars_total", 1500)
    for i in range(4):
        _attach(10 + i, f"f{i}.txt", "text", "z" * 5000)
    lines = att.prompt_lines()
    assert len(lines) == 4
    assert sum(ln.count("z") for ln in lines) == 1500
    assert "sin presupuesto" in lines[-1]


def test_a_file_that_could_not_be_read_says_so():
    _attach(5, "scan.pdf", "pdf", "", "the PDF has no text layer (a scan)")
    (line,) = att.prompt_lines()
    assert "NO se pudo leer (the PDF has no text layer (a scan))" in line


# ── the readers ──────────────────────────────────────────────────────────────────────────────────────────────
def _jpeg(w, h) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


def test_the_image_travels_to_a_model_that_receives_it(monkeypatch, tmp_path):
    from nucleo.energy import meter as energy_meter
    from nucleo.memory_agent.processor import llm
    # The titular is read from the declared table, so a measured change of reader does not break this test; what
    # it pins is that the image travels to THAT model, downscaled, as an image part, and is metered there.
    titular = att._image_rungs()[0]
    monkeypatch.setenv(titular["key_env"], "placeholder-key")
    sent, metered = [], []
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, **kw: sent.append((url, payload)) or
                        {"choices": [{"message": {"content": "A blue square."}}], "usage": {"prompt_tokens": 1}})
    monkeypatch.setattr(energy_meter, "meter_openai_response", lambda out, **kw: metered.append(kw))
    p = tmp_path / "big.jpg"
    p.write_bytes(_jpeg(4000, 3000))
    assert att._read_image(p) == ("A blue square.", "")
    url, payload = sent[0]
    from urllib.parse import urlparse
    assert urlparse(titular["base_url"]).netloc in url and payload["model"] == titular["model"]
    part = payload["messages"][0]["content"][1]
    assert part["type"] == "image_url" and part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    from PIL import Image
    shown = Image.open(io.BytesIO(base64.b64decode(part["image_url"]["url"].split(",", 1)[1])))
    assert max(shown.size) <= att.limits()["reader_image_side"], "downscaled before it travels"
    assert metered and metered[0]["model"] == titular["model"]


def test_every_rung_of_the_image_reader_receives_images():
    from config import models
    rungs = models.rungs("image_reader")
    assert len(rungs) == 2 and all(r.get("vision") is True for r in rungs)
    assert rungs[0]["provider"] != rungs[1]["provider"]


def test_without_a_key_the_image_is_unread_and_says_why(monkeypatch, tmp_path):
    # Every rung's key, read from the table: a hard-coded list missed the titular when it changed and this test
    # made a real model call.
    for env in {r["key_env"] for r in att._image_rungs()}:
        monkeypatch.delenv(env, raising=False)
    p = tmp_path / "a.jpg"
    p.write_bytes(_jpeg(50, 50))
    reading, why = att._read_image(p)
    assert reading == "" and why.startswith("no key")


def test_an_image_over_the_pixel_cap_is_not_decoded(monkeypatch, tmp_path):
    monkeypatch.setitem(att._limits_cache, "max_image_pixels", 100 * 100)
    p = tmp_path / "huge.jpg"
    p.write_bytes(_jpeg(200, 200))
    reading, why = att._read_image(p)
    assert reading == "" and "pixel cap" in why
    assert att.make_thumb(p, tmp_path / "t.jpg") is False


def _pdf(pages: int) -> bytes:
    """A real text PDF, written by hand (no PDF writer is a dependency): one line of text per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for i in range(pages):
        stream = f"BT /F1 18 Tf 72 720 Td (Page number {i}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        content_id = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>"
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for n, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def test_a_pdf_is_read_up_to_its_page_cap(monkeypatch, tmp_path):
    monkeypatch.setitem(att._limits_cache, "max_pdf_pages", 5)
    p = tmp_path / "long.pdf"
    p.write_bytes(_pdf(40))
    reading, why = att.read(p, "pdf")
    assert why == "" and reading.startswith("[40 page(s)]")
    assert "Page number 4" in reading and "Page number 5" not in reading


def test_a_text_file_is_read_up_to_its_byte_cap(monkeypatch, tmp_path):
    monkeypatch.setitem(att._limits_cache, "max_text_read_bytes", 1000)
    p = tmp_path / "big.txt"
    p.write_bytes(b"y" * 50_000)
    reading, _ = att.read(p, "text")
    assert len(reading) == 1000
