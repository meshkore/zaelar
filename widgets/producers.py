"""widgets/producers.py — widgets que PRODUCEN algo (V2-092): cómo se paran todos a la vez y quién tiene el altavoz.

`actions.py` responde «¿CÓMO se ejecuta esta acción?» (directa / con confirmación / escala). Este módulo responde
otras dos preguntas, ortogonales a esa y hasta ahora sin dueño:

    1. ¿Este widget está PRODUCIENDO algo ahora mismo (sonando, grabando, procesando)?
    2. Si lo está, ¿cómo se le dice que PARE — y puede haber dos a la vez en el mismo canal?

## Por qué hace falta un contrato y no un `if` por widget

El bug que lo destapó (operador, 2026-08-13): con el agente PARADO seguía sonando un vídeo de YouTube, y encima
sonaba a la vez que el reproductor de música. Se podía arreglar con dos casos especiales cableados —«si el widget
es youtube, llama a pause»—, pero eso no escala a un catálogo donde los widgets los GENERA el agente: el widget de
podcast de la semana que viene volvería a sonar sobre el agente parado, y nadie se acordaría de añadir su `if`.

Así que la producción se **DECLARA** en el manifest, igual que ya se declaran las acciones, el tamaño o si su
pantalla completa es la nativa. Una elección declarada no se enruta mal:

    "runtime": {
      "output": "audio",                                    // canal EXCLUSIVO que ocupa (omitir = no compite)
      "produce": ["load", "play", "restart", "unmute"],      // acciones que lo PONEN a producir
      "suspend": "pause",                                    // la acción que lo hace parar
      "active_when": {"videoId": true, "paused": false}      // cómo se lee «está produciendo» de view_data()
    }

`active_when` admite una LISTA de condiciones cuando un widget puede producir por más de una vía — la música suena
por Spotify (dispositivo remoto) o por YouTube-audio (iframe oculto), y son dos estados distintos:

    "active_when": [{"yt.videoId": true, "yt.paused": false}, {"now_playing.playing": true}]

Dentro de una condición todo debe cumplirse (Y); entre condiciones basta una (O).

Con eso, tres capacidades salen gratis para CUALQUIER widget presente o futuro:

  - **Parada global** (`suspend_all`): el ⏻ del operador suspende a todo el que esté produciendo, sin conocer a
    nadie por su nombre.
  - **Exclusividad de canal** (`enforce_exclusive`): poner música apaga el vídeo y al revés. Dos cosas sonando a
    la vez no es una función, es un fallo — y el altavoz es uno.
  - **Puerta con el agente parado** (`gate`): un agente parado no arranca reproducciones. Ni por voz, ni por un
    cron, ni por un botón de la tarjeta.

## Invariantes

  - **`active_when` se evalúa contra `view_data()`**, que es la verdad del widget (no una copia nuestra de su
    estado). Admite rutas con punto (`yt.paused`) porque un widget puede tener su reproducción en un sub-bloque.
  - **Suspender NO pasa por la puerta.** Va por el camino crudo (`server_api.dispatch_raw`): si el `suspend`
    pasara por el mismo embudo que gatea las acciones, parar con el agente parado se rechazaría a sí mismo.
  - **Nunca lanza.** Un widget que revienta al ser consultado se considera «no produce» y se deja constancia. Una
    parada global no puede caerse por un widget roto: el operador cree que paró y algo sigue sonando.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from . import runtime

# Canal por defecto de un widget que declara `runtime` sin decir en qué canal produce. `""` = no compite con nadie
# (produce, pero no en un recurso exclusivo: un proceso, una grabación en disco…). Solo un canal con NOMBRE se
# disputa; así declarar producción no impone exclusividad por accidente.
_NO_CHANNEL = ""


def spec(w: dict | str) -> dict | None:
    """Contrato de producción de un widget, normalizado, o `None` si no declara ninguno.

    Acepta el manifest completo o un id (lo busca en el catálogo). Un `runtime` sin `suspend` es inútil —no habría
    forma de pararlo— y se descarta con aviso: preferimos un widget que no participa a uno que participa a medias
    y deja al operador con algo sonando que el sistema cree apagado."""
    man = runtime.get(w) if isinstance(w, str) else w
    if not isinstance(man, dict):
        return None
    rt = man.get("runtime")
    if not isinstance(rt, dict):
        return None
    wid = str(man.get("id") or "")
    susp = str(rt.get("suspend") or "").strip()
    if not susp:
        logger.warning(f"producers[{wid}]: declara 'runtime' SIN 'suspend' — se ignora (no habría cómo pararlo)")
        return None
    produce = rt.get("produce") or []
    if isinstance(produce, str):
        produce = [produce]
    return {
        "id": wid,
        "output": str(rt.get("output") or _NO_CHANNEL).strip(),
        "produce": {str(a).strip() for a in produce if str(a).strip()},
        "suspend": susp,
        "active_when": _clauses(rt.get("active_when")),
    }


def _clauses(aw) -> list[dict]:
    """Normaliza `active_when` a una LISTA de condiciones (O de Y). Un dict suelto es una lista de uno.

    Las condiciones VACÍAS se tiran: un `{}` se cumpliría siempre (un «para todo» sobre cero campos es cierto), o
    sea que un widget que se olvidara de decir cómo se le mira constaría como «produciendo» PARA SIEMPRE y la
    parada global le mandaría un comando en cada pasada."""
    if isinstance(aw, dict):
        return [aw] if aw else []
    if isinstance(aw, (list, tuple)):
        return [c for c in aw if isinstance(c, dict) and c]
    return []


def all_specs() -> dict[str, dict]:
    """`{id: spec}` de todo widget del catálogo que declare producción."""
    out = {}
    for w in runtime.catalog():
        sp = spec(w)
        if sp and sp["id"]:
            out[sp["id"]] = sp
    return out


def _dig(data: dict, path: str):
    """Lee `a.b.c` de un dict anidado. `None` si el camino no existe (un campo ausente NO es «produciendo»)."""
    cur = data
    for part in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def is_producing(data: dict, sp: dict) -> bool:
    """¿Dicen los datos del widget que está produciendo AHORA? PURA (sin I/O) para poder probarla sola.

    Basta que se cumpla UNA condición de `active_when`, y dentro de ella TODOS sus campos. `true`/`false` comparan
    por VERDAD (no por identidad): `{"paused": false}` = «el campo paused es falsy», que es lo que un widget escribe
    de verdad (`0`, `""`, ausente). Cualquier otro valor compara por igualdad de texto, para que
    `{"mode": "youtube"}` funcione tal cual.

    Sin `active_when` no se puede saber → `False`. Un widget que quiere participar en la parada global tiene que
    decir cómo se le mira; adivinarlo sería suspender cosas que no estaban sonando. Un `view_data()` degradado
    (`{"error": …}`) tampoco produce: no vamos a mandar comandos a un widget que no sabe ni leerse."""
    clauses = sp.get("active_when") or []
    if not isinstance(data, dict) or not clauses or data.get("error"):
        return False
    return any(_clause_holds(data, c) for c in clauses)


def _clause_holds(data: dict, cond: dict) -> bool:
    for path, want in cond.items():
        got = _dig(data, path)
        if want is True:
            if not got:
                return False
        elif want is False:
            if got:
                return False
        elif str(got) != str(want):
            return False
    return True


async def _view_data(wid: str) -> dict:
    """`view_data()` del widget con el MISMO aislamiento que la API HTTP (pool acotado + timeout duro)."""
    from . import server_api
    def call(view_data):
        try:
            return view_data(q="")
        except TypeError:                       # widgets antiguos no aceptan query
            return view_data()
    res = await server_api.run_widget_hook(wid, "view_data", call)
    return res if isinstance(res, dict) and res is not server_api.MISSING else {}


async def producing(*, channel: str | None = None) -> list[str]:
    """Ids de los widgets que están produciendo ahora mismo (opcionalmente solo los de un canal).

    Consulta los `view_data()` en PARALELO: en una parada global el operador no puede esperar N timeouts en serie."""
    specs = all_specs()
    if channel is not None:
        specs = {k: v for k, v in specs.items() if v["output"] == channel}
    if not specs:
        return []
    ids = list(specs.keys())
    datas = await asyncio.gather(*[_view_data(w) for w in ids], return_exceptions=True)
    out = []
    for wid, data in zip(ids, datas):
        if isinstance(data, BaseException):
            logger.warning(f"producers[{wid}]: no pude leer su estado ({data!r}) — lo doy por parado")
            continue
        try:
            if is_producing(data, specs[wid]):
                out.append(wid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"producers[{wid}]: active_when malformado ({e!r}) — lo doy por parado")
    return out


async def suspend(wid: str, sp: dict | None = None, *, reason: str = "") -> bool:
    """Manda a UN widget su acción declarada de suspensión. Camino CRUDO (sin puerta, sin exclusividad) para que
    parar nunca se rechace a sí mismo. `True` si el widget la aceptó."""
    sp = sp or spec(wid)
    if not sp:
        return False
    from . import server_api
    try:
        res = await server_api.dispatch_raw(wid, sp["suspend"], {"reason": reason})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"producers[{wid}]: falló la suspensión ({sp['suspend']}): {e!r}")
        return False
    if isinstance(res, dict) and (res.get("error") or res.get("ok") is False):
        logger.warning(f"producers[{wid}]: la suspensión ({sp['suspend']}) no se aplicó: {res}")
        return False
    return True


async def suspend_all(*, reason: str = "", channel: str | None = None, keep: str = "") -> list[str]:
    """Suspende a TODOS los que estén produciendo (o solo los de `channel`), menos `keep`. Devuelve los ids que
    de verdad se suspendieron — es lo que se enseña en el log del operador, así que no puede ser una lista de
    intenciones."""
    specs = all_specs()
    todo = [w for w in await producing(channel=channel) if w != keep]
    if not todo:
        return []
    oks = await asyncio.gather(*[suspend(w, specs.get(w), reason=reason) for w in todo],
                              return_exceptions=True)
    return [w for w, ok in zip(todo, oks) if ok is True]


def starts_production(wid: str, action: str) -> bool:
    """¿Esta acción PONE A PRODUCIR a este widget? Declarado (`runtime.produce`), no deducido."""
    sp = spec(wid)
    return bool(sp and str(action or "").strip() in sp["produce"])


def gate(wid: str, action: str) -> dict | None:
    """Puerta previa a una acción de widget: `None` = adelante; un dict = RECHAZADA, y ese dict es la respuesta.

    Regla única: **con el agente parado, nada empieza a producir.** Palabras del operador: «si el agente está
    parado, ningún widget puede estar funcionando; pueden estar visibles o abiertos, pero no pueden estar
    reproduciendo nada ni haciendo nada». Todo lo demás (navegar la tarjeta, crear una lista, cambiar de vista)
    sigue permitido: parar el agente no es congelar la interfaz."""
    if not starts_production(wid, action):
        return None
    try:
        from nucleo import runstate
        if not runstate.stopped():
            return None
    except Exception:                            # sin runstate no hay motivo para bloquear a nadie
        return None
    return {"ok": False, "error": "agent_stopped", "id": wid, "action": action,
            "message": "El agente está parado. Enciéndelo (⏻) para volver a reproducir."}


async def enforce_exclusive(wid: str, action: str) -> list[str]:
    """Tras una acción que pone a producir: si el widget ocupa un canal EXCLUSIVO, calla a los demás de ese canal.

    Se llama DESPUÉS de aplicar la acción (no antes): quién ocupa el canal se lee del estado real, no de lo que
    creemos que la acción iba a hacer. Devuelve a quién se calló."""
    if not starts_production(wid, action):
        return []
    sp = spec(wid)
    channel = (sp or {}).get("output") or _NO_CHANNEL
    if not channel:
        return []
    others = await suspend_all(reason=f"exclusive:{channel}", channel=channel, keep=wid)
    if others:
        logger.info(f"producers[{wid}]: toma el canal «{channel}» → suspendidos {others}")
        try:
            from voice.observer import emit
            emit("widget", "exclusive", text=f"{wid} toma «{channel}» → calla {', '.join(others)}",
                 extra={"id": wid, "channel": channel, "suspended": others})
        except Exception:
            pass
    return others
