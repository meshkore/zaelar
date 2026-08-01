#
# One-shot migration (V2-082): dota a cada widget del catálogo de identidad canónica `name` + `aliases`.
#
# NO pliega los `keywords` a ciegas: los keywords viejos eran TEMÁTICOS (video, opciones, internet, "gol de
# maradona"…) y se pisaban entre widgets → justo la confusión que V2-082 elimina. En su lugar, un mapa CURADO y
# ÚNICO por widget = nombre + sinónimos de IDENTIDAD (no de tema). Cada alias pertenece a UNA sola pieza → certeza
# del enrutamiento. ADITIVO e idempotente: escribe `name`+`aliases`, MANTIENE `keywords` como legacy (Fase 1 no
# cambia comportamiento; el resolver de Fase 2 preferirá `aliases`). No toca `widget.js`/`data.py`.
#
# Uso: python -m widgets.migrate_aliases            (aplica)
#      python -m widgets.migrate_aliases --dry-run  (solo reporta)
#
from __future__ import annotations

import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# Mapa CURADO: id → {"name": nombre canónico, "aliases": [sinónimos de IDENTIDAD, únicos]}. El nombre se añade solo
# como alias implícito (no hace falta repetirlo). Colisiones resueltas a mano: el tema genérico va al widget que lo
# "posee" de verdad (internet/web/google→navegador; vídeo/clip→youtube; el gol del 86→su widget dedicado; whatsapp/
# x/twitter→mensajería; cuenta-atrás→timer; pomodoro-específico→pomodoro). Los términos de mando ("pon música") NO
# son alias de apertura: los enruta su rail/tool, no el nombre del widget.
CURATED: dict[str, dict] = {
    "agenda": {"name": "Agenda del día",
               "aliases": ["agenda", "agenda del día", "mi día", "plan del día", "planning"]},
    "clock": {"name": "Reloj",
              "aliases": ["reloj", "la hora", "qué hora es", "fecha"]},
    "cluster-registro": {"name": "Mesh for Cluster",
                         "aliases": ["cluster", "mesh", "meshkore", "registro del cluster", "peers"]},
    "futbol-champions": {"name": "Champions League",
                         "aliases": ["champions", "champions league", "liga de campeones", "uefa"]},
    "juego-serpiente-snake": {"name": "Serpiente",
                              "aliases": ["serpiente", "snake", "juego de la serpiente"]},
    "mensajeria": {"name": "Mensajería",
                   "aliases": ["mensajería", "mensajes", "mis mensajes", "chats", "whatsapp", "wasap", "telegram",
                               "x", "twitter", "email", "correo", "mail", "gmail", "outlook"]},
    "meteo-soria": {"name": "Meteo Soria",
                    "aliases": ["meteo soria", "tiempo en soria", "clima soria", "el tiempo de soria"]},
    "meteo-tarragona-grafico": {"name": "Meteo Tarragona",
                                "aliases": ["meteo tarragona", "tiempo en tarragona", "el tiempo de tarragona",
                                            "gráfico del tiempo", "tarragona 14 días"]},
    "musica": {"name": "Música",
               "aliases": ["música", "spotify", "reproductor de música", "mi música", "playlist",
                           "lista de reproducción"]},
    "navegador": {"name": "Navegador",
                  "aliases": ["navegador", "web", "internet", "google", "página web", "wallapop", "amazon"]},
    "personalizado-reproduzca-video": {"name": "Gol de la Mano de Dios",
                                       "aliases": ["gol de la mano de dios", "mano de dios", "gol de maradona",
                                                   "maradona 86", "argentina inglaterra 1986"]},
    "results": {"name": "Resultados",
                "aliases": ["resultados", "panel de resultados"]},
    "search": {"name": "Búsqueda",
               "aliases": ["búsqueda", "buscador", "panel de búsqueda"]},
    "temporizador-pomodoro-ayudar": {"name": "Pomodoro",
                                     "aliases": ["pomodoro", "técnica pomodoro", "sesión de trabajo", "25 minutos"]},
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
    for name in sorted(os.listdir(HERE)):
        mpath = os.path.join(HERE, name, "manifest.json")
        if not os.path.isfile(os.path.join(HERE, name, "widget.js")) or not os.path.isfile(mpath):
            continue
        try:
            man = json.load(open(mpath, encoding="utf-8"))
        except Exception as e:
            print(f"  ! {name}: manifest ilegible ({e})")
            continue
        wid = str(man.get("id") or name)
        spec = CURATED.get(wid)
        if not spec:
            skipped.append(wid)             # widget nuevo sin curar → lo cubre el generador/keywords legacy
            continue
        canon = spec["name"]
        aliases = _dedup([canon, *spec["aliases"]])
        for a in aliases:
            an = _norm(a)
            if an in sys_alias:
                collisions.append(f"[{wid}] alias '{a}' colisiona con la superficie de sistema '{sys_alias[an]}'")
            elif an in owner and owner[an] != wid:
                collisions.append(f"[{wid}] alias '{a}' ya pertenece al widget '{owner[an]}'")
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
    print(f"{'[DRY-RUN] ' if dry else ''}Widgets migrados ({len(res['changed'])}): {', '.join(res['changed']) or '—'}")
    if res["skipped"]:
        print(f"Sin curar (legacy keywords): {', '.join(res['skipped'])}")
    if res["collisions"]:
        print(f"\n⚠️  COLISIONES DE ALIAS ({len(res['collisions'])}) — resolver a mano:")
        for c in res["collisions"]:
            print(f"    {c}")
    else:
        print("Sin colisiones de alias. ✅  Cada alias pertenece a UNA sola pieza.")
