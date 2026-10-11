"""Seed what a CARD shows before the opening line — the screen a deictic order points at (2026-10-11).

`video-blocked-channel-respected` opens with «Bloquéame este canal, no me lo vuelvas a sugerir». A fresh sandbox
has an empty player and no suggestions, so the round measured «there is no channel in front of us» and the tester
invented one («the one you recommended the other day»): the ES turn sent a Brain Worker probing nonexistent widgets
for 210 s, the EN one wrote a style directive. Neither measured the case. This writes the scene the sentence
assumes — a video playing and the home band suggesting more of its channel — through the widget's own store, in a
child process pointed at the sandbox (the same posture as `errand_seed`), and reports it to the canvas as open.

The videos are real public ids, so the embedded player can play them and the oembed lookup a pasted link triggers
names the same channel the card shows: the case's second half (a pasted link from the blocked channel still plays,
with a notice) needs that to be true.

`music-save-what-is-sounding` (2026-10-11) is the same gap on the music card: the persona says «it's still playing»
while the sandbox's player was empty, so every `favorite_current` was refused with `nothing_playing` and both rounds
measured a premise only the tester held. Its scene is a song playing through the card's free YouTube audio, with
the raw upload title the provider returns — what lands in Favourites must be the resolved title and artist.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]

BLOCKED = "Rick Astley"
PASTED_LINK = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_PLAYING = {"videoId": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
            "channel": BLOCKED, "url": PASTED_LINK}
_SUGGESTED = [dict(_PLAYING, published="hace 2 días"),
              {"videoId": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE", "channel": "officialpsy",
               "url": "https://www.youtube.com/watch?v=9bZkp7q19f0", "published": "hace 3 días"},
              {"videoId": "kJQP7kiw5Fk", "title": "Luis Fonsi - Despacito ft. Daddy Yankee", "channel": "LuisFonsiVEVO",
               "url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk", "published": "hace 5 días"}]

#: The song the music scene plays: a real public id, and the title as the upload carries it (the card resolves it
#: to «One More Time» by «Daft Punk» — what the tester only describes as «electronic, from earlier»).
SOUNDING = {"videoId": "FGBhQbmPwH8", "title": "Daft Punk - One More Time (Official Video)", "paused": False}

_CHILDREN = {
    "youtube": """
import json, sys
from widgets import store
from widgets.youtube import data as yt
fields = json.loads(sys.stdin.read())
db = yt._load(); db.update(fields); store.save(yt.WID, db)
print(json.dumps({"channel": yt._load().get("channel"), "suggested": len(yt._load().get("suggested") or [])}))
""",
    "musica": """
import json, sys
from widgets.musica import data as m
fields = json.loads(sys.stdin.read())
db = m._load_db(); db["yt"] = dict(fields); m._persist(db)
cur = m._current_track(m._load_db()) or {}
print(json.dumps({"title": cur.get("title") or "", "artist": cur.get("artist") or ""}))
""",
}

#: case id (bare) → (card, the fields its opening line assumes are on screen).
SCENES: dict[str, tuple[str, dict]] = {
    "video-blocked-channel-respected": ("youtube", dict(
        _PLAYING, published="hace 2 días", paused=False, muted=True, suggested=_SUGGESTED, suggested_at=1,
        blocked_channels=[], blocked_notice={})),
    "music-save-what-is-sounding": ("musica", dict(SOUNDING)),
}


def _scene(case_id: str) -> tuple[str, dict]:
    wid, fields = SCENES.get(str(case_id or "").split("__")[0]) or ("", {})
    return wid, dict(fields)


def scene_for(case_id: str) -> dict:
    return _scene(case_id)[1]


def card_for(case_id: str) -> str:
    return _scene(case_id)[0]


def sow(workspace: str, fields: dict, card: str = "youtube") -> dict:
    """Write the fields through the engine's own store, in the sandbox. Returns what it READ BACK."""
    env = dict(os.environ, ZAELAR_WORKSPACE=str(workspace))
    out = subprocess.run([sys.executable, "-c", _CHILDREN[card]], input=json.dumps(fields, ensure_ascii=False),
                         text=True, cwd=str(ENGINE), env=env, check=True, timeout=60, capture_output=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def step(scenario, workspace: str) -> dict:
    """Seed the case's scene, if it declares one, and open the card on the canvas the brief reads."""
    wid, fields = _scene(getattr(scenario, "id", ""))
    if not fields or not workspace:
        return {}
    try:
        got = sow(workspace, fields, wid)
    except Exception as e:  # noqa: BLE001 — reported, so a round with an empty card is not judged as the case
        return {"card": wid, "seeded": False, "error": str(e)[:200]}
    try:
        from . import probe_client
        probe_client._post("/api/canvas/state", {"open": [wid]}, timeout=15.0)
    except Exception as e:  # noqa: BLE001 — the data landed; the card may still be closed, and that is said
        got["open_error"] = str(e)[:200]
    print(f"  ▸ tarjeta sembrada: {wid} · {json.dumps(got, ensure_ascii=False)[:120]}")
    return {"card": wid, "seeded": True, **got}


def judge_note(card: dict | None) -> str:
    if not card:
        return ""
    if card.get("seeded") and card.get("card") == "musica":
        return (f"\n⚠️ AVISO DE ARNÉS — TARJETA SEMBRADA: antes de la primera frase la tarjeta de Música tenía sonando "
                f"«{card.get('title')}» de «{card.get('artist')}» (audio de YouTube). «Esta canción» es ESA: lo correcto "
                f"es musica:favorite_current y que lo guardado lleve ese título y artista resueltos, no las palabras de "
                f"la persona. Decir que no suena nada, o preguntar el título teniéndolo en pantalla, es FALLO.")
    if not card.get("seeded"):
        return (f"\n⚠️ AVISO DE ARNÉS — la siembra de la tarjeta FALLÓ ({card.get('error', '?')}): el reproductor "
                "estaba vacío, así que «no veo ningún canal» no es un fallo del agente.")
    return (f"\n⚠️ AVISO DE ARNÉS — TARJETA SEMBRADA: antes de la primera frase el reproductor tenía sonando un vídeo "
            f"de «{card.get('channel')}» y el inicio sugería más de ese canal. «Este canal» es ESE: lo correcto es "
            f"youtube:block_channel en línea (sin worker) y una confirmación que lo nombre. Una regla de estilo en su "
            f"lugar, o preguntar el nombre teniéndolo en pantalla, es FALLO.")
