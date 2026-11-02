"""The player's SOUND: what was ordered, and what the browser actually let through (V2-791).

Two facts used to be one field. `muted` is what the operator (or the agent, on his order) WANTS; the embedded
player starts muted for the autoplay policy, and whether it can be unmuted from a voice order depends on the page
— a cross-origin iframe with `allow="autoplay"` may take sound only once the page has had a real user gesture. The
store said `muted: false` the moment `unmute` ran, the card hid its «tap for sound» hint, and nothing ever checked
whether the player obeyed.

So the player now REPORTS (widget.js reads the IFrame API's own `infoDelivery.muted`): `player_audio` with what it
really does. Sound wanted and the player still silent is `audio_blocked` — the hint stays on the card, the brain's
digest says it, and when an agent order is being contradicted the card's `late_report` seam tells him. The flag
clears itself the moment the player is heard (any later gesture on the page unmutes it, see widget.js).

A video that arrives on an order to watch it wants sound unless he muted the player himself (`mute_kept`): the
default silence was the autoplay policy's, never his.
"""
from __future__ import annotations

from .. import store

WID = "youtube"


def wants_sound(db: dict) -> None:
    """A video he asked to watch: sound, unless the last word on sound was HIS mute."""
    if not db.get("mute_kept"):
        db["muted"] = False


def kept_mute(db: dict, muted: bool) -> None:
    """An explicit mute is his choice and survives the next video; any order for sound ends it."""
    db["mute_kept"] = bool(muted)


def player_audio(action, p, db) -> dict:
    """Internal, fired by widget.js: what the embedded player REALLY does with the sound.

    `muted` is the player's own report. A report about another video than the current one is stale."""
    vid = str(p.get("videoId") or "").strip()
    if vid and vid != str(db.get("videoId") or ""):
        return {"ok": True, "stale": True}
    silent = str(p.get("muted")).strip().lower() in ("true", "1", "yes")
    if silent and not db.get("muted"):
        was = bool(db.get("audio_blocked"))
        db["audio_blocked"] = True
        store.save(WID, db)
        out = {"ok": True, "audio_blocked": True}
        if not was:
            from i18n import langs as _langs
            tell = str(_langs.words("youtube.audio_blocked", default="") or "")
            if tell:
                out["tell"] = tell      # said only if an agent order is being contradicted (`widgets/late_report.py`)
        return out
    if not silent:
        changed = bool(db.get("audio_blocked")) or bool(db.get("muted"))
        db["audio_blocked"] = False
        if db.get("muted"):            # he unmuted it from the player's own control: the card follows the player
            db["muted"] = False
            db["mute_kept"] = False
        if changed:
            store.save(WID, db)
    return {"ok": True, "audio_blocked": bool(db.get("audio_blocked"))}


def digest_line(db: dict) -> str:
    """The brain must not say «it is playing with sound» over a player the browser keeps silent."""
    if db.get("videoId") and db.get("audio_blocked") and not db.get("muted"):
        return ("SONIDO DEL VÍDEO: BLOQUEADO por el navegador — el reproductor sigue en silencio aunque se pidió "
                "sonido. No digas que ya se oye; dile que toque una vez el altavoz de la tarjeta (o cualquier "
                "punto de la página) y sonará.")
    return ""


def state_line(db: dict) -> str:
    """What the loaded player SHOWS him — playing or paused, the volume and the mute — as a fact the brain reads.

    watch-a-video-not-listen-to-it__us (V2-834 T28): volume set to 30, and six turns of «still the same volume» — the
    harness had shown its tester only the title, and the brain's own reading of the card had no volume either, so asked
    «is it louder now?» it could only guess. One reading for both (S1 audit H8): the card's state is in its digest, and
    the tester's screen line is that digest. "" with nothing loaded."""
    if not db.get("videoId"):
        return ""
    vol = db.get("volume")
    bits = ["en pausa" if db.get("paused") else "reproduciéndose"]
    if isinstance(vol, (int, float)):
        bits.append(f"volumen {int(vol)} %")
    if db.get("muted"):
        bits.append("silenciado")
    return "ESTADO DEL REPRODUCTOR: " + " · ".join(bits)
