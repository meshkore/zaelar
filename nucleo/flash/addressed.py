"""nucleo/flash/addressed.py — does this turn NAME somebody in the directory? (V2-705, Nivel 2)

The one STATE fact that a request «write to X / organise something with X» always carries is X: a name
that resolves in the operator's own directory. Words come and go («write», «contact», «text him», «ping»,
«escríbele», and whatever the next session brings); the name is there every time. V2-682 patched the same
failure three days earlier with seeds and a carried window, and 2026-09-15 it recurred with other words —
«write to my contact Kryptonite… organise a meeting» named no seed, and the tool selector trimmed the
messaging family off the very turn that needed it. Retrieval by dictionary words was the single point that
sent that order to the wrong path.

So this reads STATE, the way the selector's `open_widgets` layer does: the directory, through the same
`directory.resolve` the send door uses — so what forces the messaging tools into the box is exactly what
`send_to` will accept. `contact_in(text)` answers with the resolved contact's name, or "". Adding a family
costs tokens, never a capability, so a false positive is cheap and this reader over-includes on purpose.
(There is deliberately no «does this ask to WRITE to them» reader here: telling «write TO X» from «what did
X send me» is understanding we do not do, and the errand that verifies a sent message already lives in
`nucleo/errands/` — this module only decides which TOOLS the turn may reach.)

Cost: one directory load per call (a JSON read, µs to low ms) and a handful of string comparisons — only
on spans that look like a name (quoted, or a capitalised run), never on every word. Fail-soft: an
unreadable directory answers "".
"""
from __future__ import annotations

import re

_MIN_SPAN = 3


def _spans(text: str) -> list[str]:
    """Quoted spans and capitalised runs — the pieces that could be a name. Same shape as
    `widgets/contactos/lookup._spans`, without its «every remaining word» tail: this runs on every turn."""
    q = str(text or "")
    out: list[str] = []
    out += [m.strip() for m in re.findall(r"[\"'«]([^\"'»]{2,60})[\"'»]", q)]
    out += [m.strip() for m in re.findall(
        r"\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'-]+(?:\s+(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'-]+|\d+))*)", q)]
    seen, keep = set(), []
    for s in out:
        s = s.strip(" .,;:¿?¡!")
        k = s.lower()
        if len(s) < _MIN_SPAN or k in seen:
            continue
        seen.add(k)
        keep.append(s)
    return keep[:8]


def contact_in(text: str) -> str:
    """The name of the directory contact this text names, or "". A span that resolves to SEVERAL contacts is
    still a hit (the family is what matters here, not which of them); the first resolved name is returned."""
    try:
        from widgets import directory
    except Exception:  # noqa: BLE001
        return ""
    for span in _spans(text):
        # A capitalised run may be a sentence start («Remove the appointment…»): try the run, then its
        # individual words, so «my contact Kryptonite» and «Kryptonite, which is…» both resolve.
        candidates = [span] + ([w for w in span.split() if len(w) >= _MIN_SPAN] if " " in span else [])
        for cand in candidates:
            try:
                hits = directory.resolve(cand)
            except Exception:  # noqa: BLE001
                hits = []
            if hits:
                return str(hits[0].get("name") or cand).strip()
    return ""
