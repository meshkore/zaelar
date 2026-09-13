"""nucleo/errands/pack.py — an OPEN errand travels in the turn, and only while it is open (V2-683).

The context-pack registry (V2-675) was built for «a stretch of the relationship has its own instructions».
An errand with a third party is exactly that shape, and it is the mechanism's second consumer — which is
the argument for using it instead of adding another per-case branch to `prompt.py`:

  · re-judged EVERY turn from a cheap local read (`count_open()` is one indexed query),
  · archived for good when the errand closes — no phase text outliving its phase,
  · caught per pack, so a broken one cannot delete the introduction's contribution or anyone else's.

**What the block says, and what it must never let the model say.** The errand exists because he asked for
something that is not finished; the failure mode is the one V2-660 built a whole harness for — narrating it
as done. So the line is a FACT WITH ITS RULE (V2-453): what was asked, who it is with, where it stands,
when it expires, and the sentence that is forbidden until the objective really verifies.

**It is bounded twice**: three errands at most, each capped, and beyond that ONE line with the count. A
prompt cost that grows with how busy he is would make the system worse exactly when he needs it most.
"""
from __future__ import annotations

import time

MAX_SHOWN = 3
MAX_CHARS = 240

_LABEL = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "correo"}


def is_active() -> bool:
    """Cheap and local (rule 2 of the pack contract): one indexed count, no model, no network."""
    try:
        from . import count_open
        return count_open() > 0
    except Exception:
        return False


def _when(deadline: int, now: float) -> str:
    left = int(deadline or 0) - int(now)
    if left <= 0:
        return "fuera de plazo"
    if left < 3600:
        return f"quedan {max(1, left // 60)} min"
    if left < 86400:
        return f"quedan {left // 3600} h"
    return f"quedan {left // 86400} d"


def _who(row: dict) -> str:
    """Who this errand is with, READ FROM THE CONVERSATIONS IT OWNS and never from the objective's words —
    the name in a sentence is what the operator said, and the binding is who actually received the message.

    Returns a complete phrase («con Iván Musikin (por Telegram)», or just «por Telegram» when the other side
    is not in the directory), so the caller never glues two halves that do not fit."""
    try:
        from . import threads
        from widgets import directory
        named, bare = [], []
        for t in threads(row.get("id") or ""):
            c = directory.find_by_channel(t.get("platform"), t.get("chat_id"))
            label = _LABEL.get(str(t.get("platform")), str(t.get("platform") or ""))
            if c and c.get("name"):
                named.append(f"{c['name']} (por {label})")
            elif t.get("chat_id"):
                bare.append(f"por {label}")
        if named:
            return "con " + " · ".join(dict.fromkeys(named))
        return " · ".join(dict.fromkeys(bare))
    except Exception:
        return ""


def line(row: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    who = _who(row)
    state = {"gathering": "aún faltan datos", "contacting": "escrito, sin respuesta todavía",
             "negotiating": "hablando con él", "agreed": "hora acordada, falta cerrarlo"}.get(
        str(row.get("state") or ""), str(row.get("state") or ""))
    head = f"«{str(row.get('objective') or '')[:120]}»"
    if who:
        head += f" — {who}"
    out = f"{head} · {state} · {_when(int(row.get('deadline') or 0), now)}."
    return out[:MAX_CHARS]


def block() -> str:
    """The section that rides the turn while anything is open."""
    try:
        from . import live
    except Exception:
        return ""
    rows = live()
    if not rows:
        return ""
    now = time.time()
    lines = ["ENCARGOS ABIERTOS (gestiones TUYAS con terceros, en marcha ahora mismo):"]
    for r in rows[:MAX_SHOWN]:
        lines.append("· " + line(r, now))
    if len(rows) > MAX_SHOWN:
        lines.append(f"· … y {len(rows) - MAX_SHOWN} más.")
    # The RULE beside the facts. Without it the model reads «hay un encargo de reunión» and answers as if the
    # meeting existed — the V2-660 failure, which is the reason that harness was built at all.
    lines.append("REGLA: esto NO está hecho. No digas que la reunión/gestión está cerrada, ni des por "
                 "acordado nada que no esté ya en el widget que corresponda. Si te pregunta, cuéntale en qué "
                 "punto está y qué falta; si él cambia lo que quiere, dilo y sigue tú la gestión.")
    return "\n".join(lines)


def install() -> None:
    from ..context_packs import Pack, register
    # AFTER the introduction (order 10): meeting each other frames the conversation, an errand in flight is
    # news within it.
    register(Pack(id="errands", title="Encargos abiertos", order=20, active=is_active, block=block))
