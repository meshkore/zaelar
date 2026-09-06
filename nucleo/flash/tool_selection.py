"""PROGRESSIVE tool selection: the turn carries the direction it is heading in, not the entire catalog (V2-096 F2).

## The request

> “When someone says ‘hello, how are you?’ we are not going to send them every widget, every tool. The first thing we
> are going to tell them is: analyze this, here is the range of possibilities we can pursue… and start steering the
> direction.”

## Why this is NOT a second model call

Because that was already measured and lost (2026-08-02): splitting the turn into two requests reduces the prompt from
9,729 to 1,221 tokens but **increases the turn from 1,938 to 6,208 ms**, because each round trip costs 1.5–4.5 s. Two
trips on the critical path of the ordinary turn are ruled out.

The range is resolved without an extra trip, in three pieces of which **only the last would need a model**:

  1. Is the sentence finished? → lexicon, free (V2-096 F1, `accumulator`)
  2. Which tools do I load?   → **O(K) RETRIEVAL, free — this is this module**
  3. Is there a clear request? → yes, it needs a model, and that is the declared gap (`accumulator.set_predicate`)

## Retrieval is not understanding, which is why there is an escape hatch

V2-085 established a hard invariant: **a GATE looks at STATE, never at the words in the turn** — otherwise you would
hide a capability that does exist. This module is not a gate: it is RETRIEVAL, the same thing `widgets/selection.py`
already does to choose widgets with the `named` layer over the turn text. The difference between the two is what
justifies using words here: a gate DECIDES that something does not exist; retrieval PROPOSES candidates and must fail
gracefully when it fails.

The escape hatch is `need_capability`: a tiny tool that is added **only when something has been trimmed**, through which
the model requests the family it is missing. If it calls it, the caller retries with that family loaded. This turns the
retrieval error into **a measurable extra trip** instead of a capability silently denied — which is the failure that
actually breaks a conversation.

## The families that are NEVER trimmed, and why

`core` (scaling and setting style), `web` (`web_search`), and `memory` (`recall`) always remain. They are the ones a turn
may need **without any prior indication in the state or the words**: “how much does admission cost?” or “when is the
vehicle inspection appointment?” do not announce anything; they simply cannot be answered without the tool. Trimming
them to save tokens would trade cost for an incorrect answer, which is the wrong trade-off.
"""
from __future__ import annotations

import os
import re
import unicodedata

from nucleo.flash.router import FAMILIES

# Untouchable families (see the docstring). The rest are retrieved.
ALWAYS: frozenset[str] = frozenset({"core", "web", "memory"})

# Lexical hints by family. They are NOT an intent classifier: they are retrieval SEEDS, and `need_capability` absorbs
# their failure. Deliberately short — the long list of verbs that the operator rejected
# ([[feedback_no_hardcoded_understand]]) is what is NOT done here: we do not decide what the operator wants, only which
# schemas are worth putting in front of the model so that IT can decide.
_HINTS: dict[str, tuple[str, ...]] = {
    "widgets": ("widget", "tarjeta", "panel", "pantalla", "ventana", "abre", "abre", "cierra", "muestra",
                "muestrame", "ensename", "borra", "alias", "llama", "lista", "agenda", "card", "screen",
                "show", "close", "open", "delete",
                # V2-588: arrange_canvas — the tool-name words the family ratchet demands, plus the verbs
                # the operator actually says («ordena los widgets», «recoloca la pantalla»).
                "arrange", "canvas", "ordena", "recoloca", "organiza", "tidy"),
    # PHOTOS live in `media` too (`show_images`, V2-457 — music and video's third sibling), and this line had
    # only music and video words. Measured live on the operator's engine (2026-09-01, three turns): «Enséñame la
    # foto de un Ferrari F cuarenta» and «show me a ferrari f40 picture» retrieved `widgets` (from «enséñame» /
    # «show») and NOT `media`, so `show_images` — the only tool that puts a photo on screen — was trimmed away
    # from the very turns asking for one. Asking for MUSIC kept it; asking for a PHOTO did not.
    #
    # And the escape hatch could not absorb it, which is the part worth remembering: `need_capability` works when
    # the model can tell it is missing something, and here it kept `show_widget` and `widget_data` over the
    # `imagenes` card — tools that LOOK like they do the job. It used them, opened the viewer empty, and said
    # «Aquí lo tienes». A retrieval miss is invisible exactly when a plausible neighbour survives the trim.
    # V2-586: the PLURALS were missing — a LIST search is plural by definition («búscame vídeos de recetas de
    # paella», V2-402's own example, retrieved NO family and `play_video` was trimmed away), so every media
    # search escalated to a Brain Worker that took 9+ minutes to rediscover the widget's own `search` data-op.
    # Photos already carried both numbers because V2-548 paid this exact incident for them; music and video
    # had only the singular. Same rule as always: the SAME seeds in the other number, never a longer verb list.
    # V2-603: the ACCOUNT verbs. «conecta» was a seed of `cluster` (MeshKore peers) and of nothing else, so the
    # most natural Spanish word for linking an account retrieved peer-to-peer tools. Measured on «Vamos,
    # conecta.» while the operator was connecting YouTube: `named: ["cluster"]`, `omitted: ["media"]`. Families
    # are not exclusive, so `cluster` keeps its seed and this does not take anything from it.
    "media": ("musica", "cancion", "canciones", "suena", "spotify", "video", "videos", "youtube", "pon",
              "reproduce", "volumen", "podcast", "podcasts", "documental", "documentales",
              "play", "music", "song", "songs", "sube", "baja",
              "foto", "fotos", "fotografia", "fotografias", "imagen", "imagenes",
              "photo", "photos", "picture", "pictures", "pic", "image", "images",
              "conecta", "conectar", "conectame", "vincula", "vincular", "cuenta", "suscripciones",
              "connect", "link", "account", "subscriptions"),
    "workers": ("para", "paralo", "cancela", "cancelalo", "detente", "worker", "tarea", "proceso", "busqueda",
                "informe", "responde", "contesta", "stop", "task"),
    "cluster": ("cluster", "meshkore", "peer", "agente", "invitacion", "commons", "conecta"),
    # Spanish-only seeds until V2-548: `reply_message` was lost by «reply to the message from Claudia» and by
    # «show me my messages», while the Spanish forms worked. The operator writes in English often enough that
    # the very turn that exposed the photo gap was «show me a ferrari f40 picture» — the same night.
    # These are the SAME seeds in the other language, not a longer verb list: the list the operator rejected is
    # what this module deliberately does not build.
    "messaging": ("mensaje", "mensajes", "whatsapp", "telegram", "correo", "email", "responde", "contesta",
                  "mail", "message", "messages", "reply", "chat"),
}


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def _words(s: str) -> set[str]:
    return set(re.sub(r"[^\w\s]+", " ", _norm(s)).split())


NEED_CAPABILITY = {
    "type": "function",
    "function": {
        "name": "need_capability",
        "description": (
            "Use ONLY when this turn needs a capability whose tool you cannot see. Names the family; the turn is "
            "then retried with it loaded. Families: widgets (show/close/modify a card, change its data, aliases), "
            "media (music, video, volume), workers (stop/answer a running background task), cluster (talk to "
            "another agent), messaging (reply to a message). Do NOT use it for anything you can already do."),
        "parameters": {
            "type": "object",
            "properties": {"family": {"type": "string",
                                      "enum": ["widgets", "media", "workers", "cluster", "messaging"]}},
            "required": ["family"],
        },
    },
}

_family_of: dict[str, str] = {name: fam for fam, names in FAMILIES.items() for name in names}


def enabled() -> bool:
    """First-class kill switch. A change that affects ROUTING must be switchable off without deploying code:
    `ZAELAR_TOOL_SELECTION=0` restores the behavior of sending the entire catalog."""
    return (os.getenv("ZAELAR_TOOL_SELECTION", "1") or "").strip().lower() not in ("0", "false", "no", "off")


def select(tools: list[dict], *, turn_text: str = "", open_widgets=None,
           recent_families=None, force: set[str] | None = None) -> tuple[list[dict], dict]:
    """Trims `tools` (which have ALREADY been gated by state, `router.tools`) to what this turn may need.

    Returns `(trimmed_tools, report)`. The report travels to observability: without it, an incorrect trim means a model
    that "forgets" a capability and nobody knows why.

    Layers, from most to least entitled to be present (same ladder as `widgets/selection.py`):
      · `ALWAYS`   — never trimmed
      · `state`    — what the operator has IN FRONT OF THEM (open widgets → widgets family)
      · `forced`   — what the caller requires (e.g. after a `need_capability`)
      · `named`    — what the words in the turn suggest
      · `recent`   — families used in recent turns (MRU), so a conversation does not lose the thread
    """
    if not enabled() or not tools:
        return tools, {"selection": "off"}

    keep = set(ALWAYS)
    keep |= set(force or ())
    if open_widgets:
        keep.add("widgets")                      # what is in front of the operator takes precedence, without looking at words
    ws = _words(turn_text)
    named: set[str] = set()
    for fam, hints in _HINTS.items():
        if ws & set(hints):
            named.add(fam)
    keep |= named
    keep |= {f for f in (recent_families or ()) if f in FAMILIES}

    out, omitted = [], set()
    for t in tools:
        name = (t.get("function") or {}).get("name", "")
        fam = _family_of.get(name)
        if fam is None or fam in keep:
            out.append(t)
        else:
            omitted.add(fam)

    if omitted:
        out.append(NEED_CAPABILITY)              # the escape hatch, only if something is genuinely missing

    report = {"selection": "on", "kept": sorted(keep), "omitted": sorted(omitted),
              "n_before": len(tools), "n_after": len(out), "named": sorted(named)}
    return out, report


def families_used(names) -> set[str]:
    """Families to which called tools belong — to populate the `recent` layer of the next turn."""
    return {_family_of[n] for n in (names or ()) if n in _family_of}
