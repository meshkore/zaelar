"""Play a video from a turn: shared execution (V2-383).

Exact sibling of `music_turn` (V2-380), and for the same reason. In this channel (`probe`, the one driven by
the use cases), `play_video` resolved to the «canvas:show:youtube» tag and ended there: zero data-ops, zero
`load`, the widget open and BARE. The voice provider does execute it — it shows the widget and dispatches
`load` with the query — and this channel is its PARALLEL implementation: «wire up BOTH».

Measured in `watch-a-video-not-listen-to-it` (2026-08-27 12:53, **1/5**): eight turns asking for the Dune
trailer, the same sentence four times —«I'll open it for you, although it's empty for now»— until the tester
wrote «you've already told me that three times». And the most painful part: the system DID find the trailers.
Six searches, real titles («Dune: Part Two | Official Trailer»), all on the results sheet. None in the player.
The sentence was not one of our canned lines: it was the model telling the truth about an empty box.

The search engine was not broken either — `_search_id('Dune tráiler oficial')` resolves today to `mSY_NbSmaUI`,
«Dune - Tráiler Oficial» by Warner Bros. España. It was UNREACHABLE from this channel, which is the fourth time
this family has appeared in `probe.py`: cron tags (V2-121), login handoff (V2-176), music (V2-380), and now video.
"""
from __future__ import annotations


def normalize_action(raw) -> str:
    """`play_video.action` → "play" | "list". ONE definition shared by BOTH channels (voice and probe): the
    V2-380/383 lesson is that anything decided per-channel ends up diverging per-channel. "list" is the V2-402
    half: a content search meant for CHOOSING ("find me videos about…") fills the player's list with several
    candidates without playing — a media search's destination is its dedicated widget, not the results sheet."""
    a = str(raw or "").strip().lower()
    return "list" if a in ("list", "lista", "search", "browse", "buscar", "varios") else "play"


def voice_dispatch(raw_action) -> "tuple[str, str]":
    """(data-op, observability label) for a play_video call — the voice provider's whole branch body, kept
    here so the search-vs-load decision cannot diverge from the probe channel's (V2-402)."""
    if normalize_action(raw_action) == "list":
        return "search", "🔎 vídeos → lista youtube"
    return "load", "▶️ vídeo → widget youtube"


def request_from(tool_calls: list) -> dict:
    """What `play_video` asked for, normalized: `{query, action}`."""
    pv = next((t for t in (tool_calls or []) if t.get("name") == "play_video"), None) or {}
    args = pv.get("args") or {}
    return {"query": str(args.get("query") or "").strip(),
            "action": normalize_action(args.get("action"))}


async def execute(query: str, action: str = "play") -> dict:
    """Loads the video and returns a report of what HAPPENED, so the mouth does not have to guess.

Same rail as voice (`brain_action` → the widget's `apply_action`), not a second way to play videos.
It calls `brain_action` rather than `dispatch_tag` deliberately: `dispatch_tag` swallows the result and
returns `None`, so with it there is no way to know whether it loaded — and not knowing is exactly how one
ends up saying «I'll open it for you» over an empty screen.

Entirely fail-soft: the turn has to complete even if the player is broken.
    """
    q = str(query or "").strip()
    try:
        from widgets.server_api import brain_action
        if normalize_action(action) == "list":
            # V2-402 — a media search goes to the PLAYER: several candidates into the list, nothing autoplays.
            res = await brain_action("youtube", "search", {"query": q} if q else {})
            res = res if isinstance(res, dict) else {}
            _show_card(bool(res.get("ok")))
            return {"executed": "play_video", "accion": "list", "ok": bool(res.get("ok")),
                    "query": q[:80], "added": [str(t)[:120] for t in (res.get("added") or [])],
                    "count": int(res.get("count") or 0),
                    "message": str(res.get("message") or res.get("error") or "")[:160]}
        res = await brain_action("youtube", "load", {"query": q} if q else {})
        res = res if isinstance(res, dict) else {}
        _show_card(bool(res.get("ok", res.get("videoId"))))
        return {"executed": "play_video", "ok": bool(res.get("ok", res.get("videoId"))),
                "query": q[:80], "videoId": str(res.get("videoId") or ""),
                "title": str(res.get("title") or "")[:120],
                "message": str(res.get("message") or res.get("error") or "")[:160]}
    except Exception as e:  # noqa: BLE001
        return {"executed": "play_video", "ok": False, "query": q[:80], "execute_error": str(e)[:200]}


def _show_card(loaded: bool) -> None:
    """The player CARD opens where the data lands (V2-463) - shared rail, so the probe channel gets it too.

    The voice provider emits its own early show for instant feedback (idempotent on the frontend); this one
    is the guarantee. Found via the imagenes sibling: a measured round filled the widget while the operator
    watched a canvas where no card ever appeared - and this player had the exact same hole on the probe side.
    """
    if not loaded:
        return
    try:
        from voice.observer import emit as _emit
        _emit("widget", "show", extra={"id": "youtube", "src": "flash"})
    except Exception:  # noqa: BLE001
        pass


def ensure_delivery_named(spoken: str, parte: dict) -> str:
    """Append a LIST search's outcome to whatever the model already said — a promise must not outlive
    its own delivery.

    V2-469, round 8 of `find-videos` (22:47): the model spoke «Voy a buscar vídeos reales…» while
    `execute()` had already put 5 titled hits in the list — the canned naming only fired when the model
    was MUTE (`if not spoken`), so the user had to ASK for the titles, and next turn the model DENIED
    having searched («ya estaban ahí en tu lista»): it never learns its own async-looking search landed.
    The failed branch rides along on purpose («no he podido buscarlos») — a promise standing alone over
    nothing is the same lie in the other direction. Voice cannot do this in-turn (its dispatch is async
    and the result does not exist before the reply streams), so this is the probe/text channel's half,
    not a diverged twin.
    """
    spoken = (spoken or "").strip()
    parte = parte if isinstance(parte, dict) else {}
    if parte.get("executed") != "play_video" or parte.get("accion") != "list":
        return spoken
    canned = spoken_for(parte, "")
    if not spoken:
        return canned
    if not canned or canned in spoken:
        return spoken
    return spoken.rstrip() + " " + canned


def spoken_for(parte: dict, ack: str) -> str:
    """What is SAID after attempting to play the video. `ack` is the language-specific canned response, only for the silent success case.

The loaded video is NAMED, not «done»: that lets the operator verify at a glance that it is the one they
asked for (V2-057), and it is the difference between delivering and claiming delivery. And if it did not
load, that is stated — the fifth time one of our sentences about an empty box is the one that lies
(V2-176, V2-209, V2-377, V2-380).
    """
    parte = parte if isinstance(parte, dict) else {}
    if parte.get("executed") != "play_video":
        return ack
    # THE ENGINE'S LANGUAGE, not Spanish (V2-464): same hole its imagenes sibling was caught with live on
    # the US agent — every canned line here was Spanish on an English-only engine. One read decides the set.
    en = _lang() == "en"
    if parte.get("accion") == "list":
        # A search is NAMED like the single video is: how many and which, verifiable at a glance (V2-057) —
        # and it invites a choice, because choosing is exactly what asking to SEARCH (vs to PLAY) means.
        if parte.get("ok"):
            added = [str(t) for t in (parte.get("added") or []) if str(t).strip()]
            if added:
                nombres = " · ".join(f"«{t}»" for t in added[:3])
                # The count must match what is shown (V2-469): «5 vídeos: a · b · c…» was answered with
                # «me has dicho 5 pero solo veo 3» — a bare ellipsis reads as lost items; «y N más» is a fact.
                resto = len(added) - 3
                if resto > 0:
                    nombres += (f" and {resto} more" if en else f" y {resto} más")
                return (f"I've queued {len(added)} videos: {nombres} — tell me which one to play."
                        if en else
                        f"Te he puesto {len(added)} vídeos en la lista: {nombres} — dime cuál pongo.")
            return ("They were all in the list already — tell me which one to play." if en
                    else "Ya estaban todos en la lista — dime cuál pongo.")
        msg = str(parte.get("message") or "").strip()
        if en:
            return "I couldn't search for them: " + (msg or "I found no videos of that.")
        return "No he podido buscarlos: " + (msg or "no encontré vídeos de eso.")
    if parte.get("ok"):
        t = str(parte.get("title") or "").strip()
        if not t:
            return ack
        return f"It's up on your screen: «{t}»." if en else f"Ya lo tienes en pantalla: «{t}»."
    msg = str(parte.get("message") or "").strip()
    if en:
        return "I couldn't play it: " + (msg or "I found no such video.")
    return "No he podido ponerlo: " + (msg or "no encontré ese vídeo.")


def _lang() -> str:
    """`en` or `es` — the engine's own language (monolingual per process, `voice/engine/core/langs`)."""
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
        return "en" if code.startswith("en") else "es"
    except Exception:  # noqa: BLE001
        return "es"
