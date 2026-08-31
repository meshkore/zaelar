#
# One-shot migration (V2-082): give each catalog widget a canonical identity through `name` + `aliases`.
#
# Do NOT blindly fold `keywords`: old keywords were THEMATIC (video, options, internet, a famous goal, etc.) and
# overlapped between widgets, which is exactly the confusion V2-082 removes. Instead, use a curated and UNIQUE map
# per widget: name + identity synonyms, not topic synonyms. Each alias belongs to exactly one piece, giving routing
# certainty. Additive and idempotent: writes `name`+`aliases`, keeps `keywords` as legacy (Phase 1 does not change
# behavior; the Phase 2 resolver will prefer `aliases`). Does not touch `widget.js`/`data.py`.
#
# Usage: python -m widgets.migrate_aliases            (apply)
#        python -m widgets.migrate_aliases --dry-run  (report only)
#
from __future__ import annotations

import json
import os
import sys
import unicodedata

from widgets import paths

HERE = paths.BUILTIN_ROOT

# CURATED map: id -> {"name": canonical name, "aliases": [unique IDENTITY synonyms]}. The name is added as an
# implicit alias, so it does not need to be repeated. Collisions resolved by hand: generic topics go to the widget
# that truly owns them (internet/web/google -> navegador; video/clip -> youtube; the 1986 goal -> its dedicated
# widget; whatsapp/x/twitter -> mensajeria; countdown -> timer; pomodoro-specific -> pomodoro). Command terms are
# NOT opening aliases; their rail/tool routes them, not the widget name.
CURATED: dict[str, dict] = {
    "agenda": {"name": "Agenda del día",
               "aliases": ["agenda", "agenda del día", "mi día", "plan del día", "planning"]},
    "clock": {"name": "Reloj",
              "aliases": ["reloj", "la hora", "qué hora es", "fecha"]},
    "mensajeria": {"name": "Mensajería",
                   "aliases": ["mensajería", "mensajes", "mis mensajes", "chats", "whatsapp", "wasap", "telegram",
                               "x", "twitter", "email", "correo", "mail", "gmail", "outlook"]},
    "musica": {"name": "Música",
               "aliases": ["música", "spotify", "reproductor de música", "mi música", "playlist",
                           "lista de reproducción"]},
    "navegador": {"name": "Navegador",
                  "aliases": ["navegador", "web", "internet", "google", "página web", "wallapop", "amazon"]},
    "results": {"name": "Resultados",
                "aliases": ["resultados", "panel de resultados"]},
    "search": {"name": "Búsqueda",
               "aliases": ["búsqueda", "buscador", "panel de búsqueda"]},
    "timer": {"name": "Temporizador",
              "aliases": ["temporizador", "cronómetro", "horno", "cuenta atrás", "countdown", "tiempo restante"]},
    "youtube": {"name": "YouTube",
                "aliases": ["youtube", "vídeo", "video", "clip", "reproductor de vídeo", "pon un vídeo",
                            "ver un vídeo"]},
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _dedup(seq) -> list[str]:
    out, seen = [], set()
    for a in seq:
        a = str(a or "").strip()
        k = _norm(a)
        if a and k not in seen:
            seen.add(k)
            out.append(a)
    return out


def _system_aliases() -> dict[str, str]:
    from . import system_surfaces
    out = {}
    for s in system_surfaces.surfaces():
        for a in [s["name"], *s["aliases"]]:
            out[_norm(a)] = s["id"]
    return out


def migrate(dry_run: bool = False) -> dict:
    sys_alias = _system_aliases()
    owner: dict[str, str] = {}
    collisions: list[str] = []
    changed: list[str] = []
    skipped: list[str] = []
    for name, folder in paths.iter_folders():
        mpath = os.path.join(folder, "manifest.json")
        if not os.path.isfile(os.path.join(folder, "widget.js")) or not os.path.isfile(mpath):
            continue
        try:
            man = json.load(open(mpath, encoding="utf-8"))
        except Exception as e:
            print(f"  ! {name}: unreadable manifest ({e})")
            continue
        wid = str(man.get("id") or name)
        spec = CURATED.get(wid)
        if not spec:
            skipped.append(wid)             # new uncurated widget -> covered by generator/legacy keywords
            continue
        canon = spec["name"]
        aliases = _dedup([canon, *spec["aliases"]])
        for a in aliases:
            an = _norm(a)
            if an in sys_alias:
                collisions.append(f"[{wid}] alias '{a}' collides with system surface '{sys_alias[an]}'")
            elif an in owner and owner[an] != wid:
                collisions.append(f"[{wid}] alias '{a}' already belongs to widget '{owner[an]}'")
            else:
                owner.setdefault(an, wid)
        if man.get("name") == canon and man.get("aliases") == aliases:
            continue
        man["name"] = canon
        man["aliases"] = aliases
        changed.append(wid)
        if not dry_run:
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(man, f, ensure_ascii=False, indent=2)
                f.write("\n")
    return {"changed": changed, "collisions": collisions, "skipped": skipped}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    res = migrate(dry_run=dry)
    print(f"{'[DRY-RUN] ' if dry else ''}Migrated widgets ({len(res['changed'])}): {', '.join(res['changed']) or '—'}")
    if res["skipped"]:
        print(f"Uncurated (legacy keywords): {', '.join(res['skipped'])}")
    if res["collisions"]:
        print(f"\nALIAS COLLISIONS ({len(res['collisions'])}) — resolve by hand:")
        for c in res["collisions"]:
            print(f"    {c}")
    else:
        print("No alias collisions. Each alias belongs to exactly one piece.")
