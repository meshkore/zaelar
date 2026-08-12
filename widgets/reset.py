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
                store.save(widget_id, data)
                return "blank" if name == "blank" else "empty"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"widgets.reset: {widget_id}.{name}() falló: {e}")
    # (2) genérico: fuera el estado, que el widget lo recomponga vacío. SOLO state.json.
    try:
        p = os.path.join(store.data_dir(widget_id), "state.json")
        if os.path.exists(p):
            os.remove(p)
        store.forget(widget_id)
        return "wiped"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widgets.reset: no se pudo vaciar {widget_id}: {e}")
        return "error"


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
