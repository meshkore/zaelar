"""files/attachments.py — a file added to the CHAT (V2-809).

The chat's 📎 (and a paste/drop onto its composer) sends each file through the one upload door,
`POST /api/files/upload` with `source=chat`. This module is what that door does for the chat on top of what it
already did (bytes + an episodic memory row):

  · **its limits live in ONE declared place**, `config/attachments.default.json` (size per file, files and bytes
    per message, the disk's free-space headroom, every reader's bound). The door, the turn and the composer
    (`GET /api/files/limits`) read the same numbers;
  · **decides the kind from the bytes**, never from the name or the browser's mime: image, PDF or plain text.
    Anything else is refused at the door, whatever the client claimed;
  · **reads it once, after upload, with bounded work**: text up to a byte cap, a PDF's text layer up to a page
    cap (`pypdf`), and an image DOWNSCALED and sent to a model that really RECEIVES the image (the
    `image_reader` service of `config/models.default.json`) — the voice brain cannot see, which is why an image
    is read here. The reading and a thumbnail are kept by episode id beside the episodic bytes, and the head of
    the reading becomes the episode's searchable summary;
  · **holds what he just attached** as the turn's state: the recent attachments, for a short window, until he
    removes the chip or attaches newer ones. `prompt_lines()` gives the turn one line per attachment and NOTHING
    when there is none, so a turn without a file pays zero characters for this.

A reading that could not be made (no key, a scan with no text layer, a provider down, a timeout) is said as such
in the turn's line, so the model says it could not read the file instead of inventing what it holds.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import threading
import time
from pathlib import Path

from loguru import logger

_LIMITS_FILE = Path(__file__).resolve().parent.parent / "config" / "attachments.default.json"
_limits_cache: dict = {}

#: How long an attachment stays «what he just attached» in the turn's state.
TTL_S = 30 * 60
#: The head of a reading kept as the episode's searchable summary.
SUMMARY_CHARS = 600

# Magic numbers of the image formats a browser shows and the reader models accept.
_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

_lock = threading.Lock()
_recent: list[dict] = []
#: ONE file is read at a time. The composer uploads a message's files in parallel, and the worst bounded read
#: (a PNG at the pixel cap) costs ~250 MB of RSS (measured): ten of them at once would not fit a small machine.
_work = threading.BoundedSemaphore(1)


def limits() -> dict:
    """The declared limits (`config/attachments.default.json`), read once. Fails LOUDLY if the file is missing:
    a door with no limits is not a door."""
    if not _limits_cache:
        data = json.loads(_LIMITS_FILE.read_text(encoding="utf-8"))
        _limits_cache.update({k: v for k, v in data.items() if not k.startswith("_") and k != "why"})
    return dict(_limits_cache)


def public_limits() -> dict:
    """What the composer needs to refuse before uploading (the server refuses again)."""
    lim = limits()
    return {k: lim[k] for k in ("max_file_bytes", "max_files_per_message", "max_message_bytes", "upload_stall_s",
                                     "process_timeout_s")}


def free_bytes_needed(total_bytes: int) -> int:
    """The free space an upload must LEAVE on the volume: max(min_free_bytes, min_free_ratio of the volume)."""
    lim = limits()
    return max(int(lim["min_free_bytes"]), int(float(lim["min_free_ratio"]) * int(total_bytes)))


# Bytes that uploads in flight have announced and not written yet. The free space of the volume only shows what
# is already on disk, so without this several uploads at once were each measured as if alone — and together could
# land the volume under its headroom.
_reservations: dict[int, int] = {}
_res_lock = threading.Lock()


class Reservation:
    """The bytes one upload still owes the disk: announced at the start, shrinking as they are written."""

    def __init__(self, announced: int):
        self._key = id(self)
        self.update(announced)

    def update(self, left: int) -> None:
        with _res_lock:
            _reservations[self._key] = max(0, int(left))

    def release(self) -> None:
        with _res_lock:
            _reservations.pop(self._key, None)


def reserved_bytes() -> int:
    with _res_lock:
        return sum(_reservations.values())


def disk_allows(directory: Path, incoming: int = 0) -> bool:
    """False when writing `incoming` more bytes — on top of what every upload in flight still owes — would leave
    the volume under its headroom."""
    du = shutil.disk_usage(directory)
    return du.free - max(0, int(incoming)) - reserved_bytes() >= free_bytes_needed(du.total)


# ── kind ─────────────────────────────────────────────────────────────────────────────────────────────────────
def sniff(head: bytes, filename: str) -> tuple[str, str] | None:
    """`(kind, mime)` decided from the first bytes — `image`, `pdf` or `text` — or None when the chat does not
    take it. Text is the one kind with no signature, so it needs both a text extension AND bytes that decode as
    UTF-8 with no NUL: a renamed binary fails the second, a script named `.py` fails the first."""
    for magic, mime in _IMAGE_MAGIC:
        if head.startswith(magic):
            return "image", mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp"
    if head.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    low = (filename or "").lower()
    if low.endswith(tuple(limits()["text_extensions"])) and b"\x00" not in head:
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as e:
            if e.start < len(head) - 4:     # a multi-byte char cut by the window is not a binary
                return None
        mime = "text/csv" if low.endswith(".csv") else (
            "text/markdown" if low.endswith((".md", ".markdown")) else "text/plain")
        return "text", mime
    return None


# ── reading (bounded: none of these loads more than its cap, whatever the file weighs) ───────────────────────
def _read_text(path: Path) -> tuple[str, str]:
    with open(path, "rb") as fh:
        raw = fh.read(int(limits()["max_text_read_bytes"]))
    text = raw.decode("utf-8", errors="replace").strip()
    return (text, "") if text else ("", "the file is empty")


def _read_pdf(path: Path) -> tuple[str, str]:
    lim = limits()
    budget = int(lim["turn_chars_per_file"]) * 4
    try:
        from pypdf import PdfReader
        # An open FILE, never the path: given a path, pypdf reads the whole file into memory first (measured:
        # +239 MB of RSS for a 198 MB PDF); given a file it seeks to the objects it needs.
        with open(path, "rb") as fh:
            reader = PdfReader(fh)
            n_pages = len(reader.pages)
            parts, total = [], 0
            for i, page in enumerate(reader.pages):
                if i >= int(lim["max_pdf_pages"]) or total > budget:
                    break
                txt = (page.extract_text() or "").strip()
                if txt:
                    parts.append(txt)
                    total += len(txt)
        if not parts:
            return "", "the PDF has no text layer (a scan)"
        return f"[{n_pages} page(s)]\n" + "\n".join(parts), ""
    except Exception as e:  # noqa: BLE001
        return "", f"the PDF could not be opened ({str(e)[:80]})"


def _open_image(path: Path, side: int):
    """The image decoded at no more than about `side` px: JPEG uses the decoder's reduced scale, and anything
    over the pixel cap is refused BEFORE decoding (the header carries the size)."""
    from PIL import Image
    im = Image.open(str(path))
    w, h = im.size
    if w * h > int(limits()["max_image_pixels"]):
        im.close()
        raise ValueError(f"{w}x{h} is over the {limits()['max_image_pixels']} pixel cap")
    if im.format == "JPEG":
        im.draft("RGB", (side, side))
    # Resampled in its own mode and converted only once small: converting first doubles the full-size copy.
    im.thumbnail((side, side), reducing_gap=2.0)
    return im.convert("RGB")


def make_thumb(path: Path, dest: Path) -> bool:
    try:
        im = _open_image(path, int(limits()["thumb_side"]))
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=78)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"attachments: no thumbnail for {path.name}: {str(e)[:120]}")
        return False


_IMAGE_PROMPT = (
    "Transcribe every piece of visible text in this image verbatim, in its original language, then describe "
    "what the image shows in a few sentences: what it is, the people/objects/places, numbers and anything a "
    "person might ask about it. Plain text, no preamble.")


def _image_rungs() -> list[dict]:
    from config import models as _table
    return [r for r in _table.rungs("image_reader") if r.get("vision") is not False]


def _read_image(path: Path) -> tuple[str, str]:
    """One request per rung of `image_reader`, the DOWNSCALED image as an `image_url` content part (it travels to
    the model, it is not described to it). Metered like every paid call; a rung without a key is skipped."""
    try:
        im = _open_image(path, int(limits()["reader_image_side"]))
    except Exception as e:  # noqa: BLE001
        return "", f"the image could not be decoded ({str(e)[:80]})"
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    url_img = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    from nucleo import energy_meter, llm_egress
    from nucleo.memory_agent.processor import llm
    from nucleo.provider_keys import key_for_endpoint
    why = "no image-reading model is configured"
    for rung in _image_rungs():
        base, model = rung.get("base_url") or "", rung.get("model") or ""
        key = key_for_endpoint(base)
        if not key and not llm_egress.mediated():
            why = f"no key for {rung.get('provider')}"
            continue
        payload = {"model": model, "max_tokens": 1200, "temperature": 0.1,
                   "messages": [{"role": "user", "content": [
                       {"type": "text", "text": _IMAGE_PROMPT},
                       {"type": "image_url", "image_url": {"url": url_img}}]}]}
        try:
            r_url, r_key, extra = llm_egress.route(base, key)
            out = llm._post_json(r_url.rstrip("/") + "/chat/completions", payload,
                                    headers={"Authorization": f"Bearer {r_key}", "Content-Type": "application/json",
                                             **(extra or {})}, timeout=float(limits()["process_timeout_s"]))
            energy_meter.meter_openai_response(out, base_url=base, model=model)
            text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            if text.strip():
                return text.strip(), ""
            why = f"{model} returned nothing"
        except Exception as e:  # noqa: BLE001
            why = f"{model}: {str(e)[:100]}"
            logger.warning(f"attachments: image reading failed on {model}: {str(e)[:160]}")
    return "", why


def process(path: Path, kind: str, thumb_dest: Path) -> tuple[str, str, bool]:
    """`(reading, why_not, has_thumb)` — the whole bounded work on one file, one file at a time (`_work`)."""
    with _work:
        reading, why = read(path, kind)
        has_thumb = kind == "image" and make_thumb(path, thumb_dest)
    return reading, why, has_thumb


def read(path: Path, kind: str) -> tuple[str, str]:
    """`(reading, why_not)` — what the file says, or why it could not be read. Never raises."""
    try:
        if kind == "text":
            return _read_text(path)
        if kind == "pdf":
            return _read_pdf(path)
        if kind == "image":
            return _read_image(path)
    except Exception as e:  # noqa: BLE001
        return "", f"reading failed ({str(e)[:80]})"
    return "", "unsupported kind"


def summary_of(name: str, kind: str, reading: str) -> str:
    """The episode's searchable summary: what it is plus the head of what it says."""
    head = f"Archivo adjuntado al chat: {name} ({kind})"
    body = " ".join((reading or "").split())[:SUMMARY_CHARS]
    return f"{head}. {body}" if body else head


# ── side files, by episode id (so the thumbnail of a restored history is one lookup) ─────────────────────────
def _side_dir(sub: str) -> Path:
    from memory import api as memapi
    d = Path(memapi.episode_inbox()).parent / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def thumb_path(episode_id: int) -> Path:
    return _side_dir(".thumbs") / f"{int(episode_id)}.jpg"


def reading_path(episode_id: int) -> Path:
    return _side_dir(".readings") / f"{int(episode_id)}.txt"


def save_reading(episode_id: int, reading: str) -> None:
    if reading:
        reading_path(episode_id).write_text(reading, encoding="utf-8")


# ── the turn's state ─────────────────────────────────────────────────────────────────────────────────────────
def attach(ref: dict) -> None:
    """He has just attached this file: it becomes the newest entry of the turn's state."""
    item = {k: ref.get(k) for k in ("episode_id", "name", "kind", "mime", "bytes", "why_not")}
    item["at"] = time.time()
    with _lock:
        _recent[:] = [r for r in _recent if r.get("episode_id") != item["episode_id"]]
        _recent.insert(0, item)
        del _recent[int(limits()["max_files_per_message"]):]


def detach(episode_id: int) -> bool:
    """He removed the chip before sending: the file stays stored, the turn stops seeing it."""
    with _lock:
        n = len(_recent)
        _recent[:] = [r for r in _recent if r.get("episode_id") != int(episode_id)]
        return len(_recent) != n


def current(now: float | None = None) -> list[dict]:
    """What he attached in the last `TTL_S` seconds, newest first."""
    t = time.time() if now is None else now
    with _lock:
        _recent[:] = [r for r in _recent if t - float(r.get("at") or 0) <= TTL_S]
        return [dict(r) for r in _recent]


def _size(n) -> str:
    n = int(n or 0)
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


def prompt_lines(now: float | None = None) -> list[str]:
    """One line per attachment the turn should see; an empty list when there is none (a turn without a file
    pays nothing). Each carries the reading made at upload, within the per-file and per-turn budgets, or the
    reason there is none."""
    lim = limits()
    per_file, left = int(lim["turn_chars_per_file"]), int(lim["turn_chars_total"])
    out = []
    t = time.time() if now is None else now
    for r in current(t):
        ago = max(0, int((t - float(r.get("at") or t)) // 60))
        head = (f"ADJUNTO en el chat (hace {ago} min): «{r.get('name')}» · {r.get('kind')} · {_size(r.get('bytes'))}"
                f" — «esta foto/este archivo/esto» se refiere a él.")
        reading = ""
        try:
            p = reading_path(r["episode_id"])
            if p.is_file():
                with open(p, encoding="utf-8", errors="replace") as fh:
                    reading = fh.read(per_file + 1).strip()
        except (OSError, KeyError, TypeError):
            reading = ""
        if reading and left > 0:
            cap = min(per_file, left)
            more = " […]" if len(reading) > cap else ""
            out.append(f"{head} Contenido:\n{reading[:cap]}{more}")
            left -= cap
        elif reading:
            out.append(f"{head} (contenido omitido: sin presupuesto en este turno)")
        else:
            out.append(f"{head} NO se pudo leer ({r.get('why_not') or 'sin lectura'}): dilo, no lo supongas.")
    return out


def _reset_for_tests() -> None:
    with _res_lock:
        _reservations.clear()
    with _lock:
        _recent.clear()
