"""widgets/reset.py — DEJAR LAS SUPERFICIES EN BLANCO cuando el operador aprieta Reset.

Hasta hoy el reset cerraba las tarjetas pero NO tocaba sus datos, así que el contenido seguía ahí esperando: el
operador reseteó «para empezar de cero», pidió una búsqueda nueva y al abrirse la hoja de resultados le salió
ENTERA la búsqueda anterior (los ferrys a Ibiza del 10 de agosto) mientras el worker de la nueva todavía trabajaba.
Un widget que muestra el trabajo de antes como si fuera el de ahora es el mismo tipo de fallo que un agente caído
pintado en azul: no es feo, es que ENGAÑA.

**Qué se vacía y qué no.** El reset conserva credenciales y autenticación (es su contrato, y lo dice el diálogo),
así que aquí solo se toca `state.json` de cada widget — nunca su `data_dir`, donde viven las capturas y, sobre
todo, **el perfil de Chromium del navegador con las sesiones que el operador abrió a mano**. Borrar la carpeta
entera (lo que hace `store.delete`, pensado para cuando el widget MUERE) le costaría todos sus logins.

Y hay una frontera que el operador tiene que poder mover sin tocar código: **datos DERIVADOS vs REGISTRO del
operador**. Una hoja de resultados, un informe o una gráfica son la salida de un trabajo — reproducibles, y
vaciarlas no pierde nada. La agenda, en cambio, son sus proyectos, sus tareas y sus citas REALES: eso no es la
salida de nada y borrarlo sí es pérdida. Un widget lo declara en su manifest:

    "data": { "durable": true }     → el reset NO lo toca (es el registro del operador)

Sin declararlo, se vacía. Ese es el defecto que pidió el operador («todos los widgets de resultados, de
visualizaciones, etc. se tienen que inicializar en blanco»), y deja la excepción explícita, revisable y en el
propio widget en vez de en una lista escondida aquí.

**Cómo se vacía** (de más específico a más genérico, primero que gane):
  1. `data.py::blank()` — el widget decide qué es «en blanco» para él. Lo necesita mensajería: sus mensajes se van,
     pero el estado de CONEXIÓN de cada plataforma se queda (si no, un reset parecería desconectarte de WhatsApp).
  2. `data.py::_empty()` — la convención que ya existía en varios widgets para su estado semilla.
  3. borrar `state.json` — genérico y seguro: `store.load` cae al default que el propio widget pasa, o sea a su
     hoja vacía. Nunca toca el resto del `data_dir`.
"""
from __future__ import annotations

import inspect
import json
import os

from loguru import logger

from . import store
from .server_api import _data_module


def _manifest(widget_id: str) -> dict:
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), widget_id, "manifest.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def is_durable(widget_id: str) -> bool:
    """¿Su contenido es el REGISTRO del operador (agenda, contactos…) en vez de la salida de un trabajo?
    Solo True si el widget lo DECLARA. Ante la duda, se vacía: es lo que pidió el operador."""
    return bool((_manifest(widget_id).get("data") or {}).get("durable"))


def _has_state(widget_id: str) -> bool:
    return os.path.exists(os.path.join(store.data_dir(widget_id), "state.json"))


def _blank_one(widget_id: str) -> str:
    """Vacía UN widget. Devuelve cómo se hizo ('blank' | 'empty' | 'wiped' | 'error'). Nunca lanza."""
    mod = _data_module(widget_id)          # None si el widget no tiene data.py (o ya no existe su código)
    # (1) el widget sabe qué es «en blanco» para él (conserva lo que no es contenido: conexiones, ajustes…)
    for name in ("blank", "_empty"):
        fn = getattr(mod, name, None) if mod else None
        if not callable(fn):
            continue
        try:
            if inspect.signature(fn).parameters:      # `_empty(reason)` y compañía: no es un estado semilla vacío
                continue
            data = fn()
            if isinstance(data, dict):
                store.save(widget_id, data)                # ya anuncia el cambio al canvas (`widget/data`)
                # …pero un `data` a secas no dice que esto fue un RESET: la fila de auditoría la pone `_announce`.
                _announce(widget_id, "blank" if name == "blank" else "empty", refresh=False)
                return "blank" if name == "blank" else "empty"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"widgets.reset: {widget_id}.{name}() falló: {e}")
    # (2) genérico: fuera el estado, que el widget lo recomponga vacío. SOLO state.json.
    try:
        p = os.path.join(store.data_dir(widget_id), "state.json")
        if os.path.exists(p):
            os.remove(p)
        store.forget(widget_id)
        _announce(widget_id, "wiped")
        return "wiped"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widgets.reset: no se pudo vaciar {widget_id}: {e}")
        return "error"


def _announce(widget_id: str, how: str, refresh: bool = True) -> None:
    """Este camino MUTA los datos de un widget SIN pasar por `store.save()` — y `save()` es el único punto que
    anuncia «este widget ha cambiado». O sea que borrar el `state.json` era una mutación INVISIBLE: ni evento en el
    registro, ni señal al canvas, ni una línea que lo explique. Punto ciego encontrado en carne propia (2026-08-10):
    a otra sesión se le vació la hoja de resultados dos veces en mitad de una prueba y, sin rastro de reset, parecía
    un fallo de persistencia del widget — se fue un buen rato en buscar una avería que no existía.

    Se anuncia por la MISMA puerta y con dos propósitos distintos, y hacen falta los dos:
      · `blank` → la fila de AUDITORÍA: qué widget se vació, cómo y por orden de quién (`src`, provenance).
      · `data`  → la señal que el canvas escucha (`sse.js` → `desktop.refreshData`), para que la tarjeta abierta se
        repinte YA en vez de seguir mostrando datos que en disco ya no existen.
    Best-effort: vaciar un widget nunca puede fallar porque no se pudiera contar."""
    try:
        from voice.observer import emit
        from widgets.provenance import who
        src = who(widget_id)
        emit("widget", "blank", extra={"id": widget_id, "src": src, "how": how})
        if refresh:                                   # el camino que pasa por `save()` ya lo ha emitido él
            emit("widget", "data", extra={"id": widget_id, "src": src})
    except Exception:
        pass


def blank_all() -> dict:
    """Deja EN BLANCO el contenido de todos los widgets que no declaren que su dato es del operador.

    Devuelve `{"blanked": [...], "kept": [...]}` — para el resumen del reset y para que el operador pueda VER qué
    se respetó (una lista de lo conservado es la parte que evita la sorpresa)."""
    blanked, kept = [], []
    for wid in _widget_ids():
        if not _has_state(wid):
            continue                       # nada guardado → nada que vaciar (no crea ficheros por el camino)
        if is_durable(wid):
            kept.append(wid)
            continue
        how = _blank_one(wid)
        if how != "error":
            blanked.append(wid)
    if blanked or kept:
        logger.info(f"RESET widgets: en blanco {blanked or '—'} · conservados por declaración {kept or '—'}")
    return {"blanked": sorted(blanked), "kept": sorted(kept)}


def _widget_ids() -> list[str]:
    """Ids con datos guardados. Se recorre `widgets/_data/` y NO el catálogo: ahí quedan también los datos de
    widgets ya borrados, y son justo los que nadie volvería a limpiar nunca."""
    out = []
    try:
        base = store.DATA_DIR
        for name in sorted(os.listdir(base)):
            if name.startswith("_") or not os.path.isdir(os.path.join(base, name)):
                continue
            out.append(name)
    except Exception:
        pass
    return out
