#
# System surfaces — ESPEJO BACKEND de las superficies NATIVAS del frontend (V2-082).
#
# La FUENTE DE VERDAD es `frontend/app/core/system-surfaces.js` (`SYSTEM_SURFACES`): el front es "el cuerpo", su
# genética viene programada. Este módulo replica SOLO la identidad DIRIGIBLE POR VOZ (id + nombre + alias FIJOS) de
# esas superficies, para que el resolver de nombres del backend (`widgets/runtime.py::identify`) pueda unificar en un
# solo espacio de nombres los WIDGETS DE USUARIO (catálogo, alias editables) y las SUPERFICIES DE SISTEMA (alias
# hardcodeados, NO editables). Así "abre el chat" resuelve al sistema y "abre el widget de mensajería" al catálogo, y
# jamás se confunden.
#
# Solo se listan las superficies con `name`+`aliases` no nulos en el JS (las dirigibles por voz). Las transitorias /
# de andamiaje (activity-strip, topbar, connstatus, alert, boot) NO entran — no se abren por nombre.
#
# INVARIANTE de sincronía: `test_system_surfaces_sync.py` compara este espejo contra el JS y FALLA si divergen —
# añadir/editar una superficie dirigible obliga a tocar los dos sitios (o el test lo canta). Los alias de sistema son
# INTOCABLES por el usuario (a diferencia de los de widget); no hay endpoint que los edite.
#
from __future__ import annotations

# id → {name, aliases}. Réplica EXACTA de las entradas con name!=null de SYSTEM_SURFACES (frontend). El ruteo de las
# pestañas del chat (Procesos/Crons) NO vive aquí: lo hace la tool show_panel (router._canon_panel) — estos alias del
# chat abren la superficie (pestaña por defecto).
SYSTEM_SURFACES: dict[str, dict] = {
    "camera": {
        "name": "Cámara y micrófono",
        "aliases": ["camara", "cámara", "microfono", "micrófono", "mic", "webcam"],
    },
    "orb": {
        "name": "Orbe",
        "aliases": ["orbe", "orb", "el ojo", "ojo", "controles", "subtitulos", "subtítulos"],
    },
    "chat": {
        "name": "Chat",
        "aliases": ["chat", "muro", "muro de texto", "muro de chat", "escribirte", "hablarte por texto",
                    "conversacion", "conversación", "el chat contigo"],
    },
    "status": {
        "name": "Estado",
        "aliases": ["estado", "estado del sistema", "status", "panel de estado", "salud del sistema"],
    },
    "config": {
        "name": "Configuración",
        "aliases": ["config", "configuracion", "configuración", "ajustes", "preferencias", "settings", "opciones"],
    },
    "benchmarks": {
        "name": "Benchmarks",
        "aliases": ["benchmarks", "por que estos modelos", "por qué estos modelos", "comparativa"],
    },
    "debug": {
        "name": "Debug",
        "aliases": ["debug", "depuracion", "depuración", "logs", "logging", "trazas", "timeline", "observabilidad"],
    },
    "memory-map": {
        "name": "Mapa de la memoria",
        "aliases": ["memoria", "mapa de memoria", "mapa de la memoria", "tu memoria", "recuerdos"],
    },
    "wizard": {
        "name": "Asistente de configuración",
        "aliases": ["wizard", "asistente", "primer arranque", "configuracion inicial", "configuración inicial"],
    },
    "vault": {
        "name": "Bóveda",
        "aliases": ["boveda", "bóveda", "secretos", "vault", "contraseñas", "caja fuerte"],
    },
}


def surfaces() -> list[dict]:
    """Lista de superficies de sistema dirigibles por voz, en la forma del registro unificado:
    `{id, name, aliases, surface: "system"}`. Consumida por `widgets/registry.py` y el resolver."""
    return [{"id": sid, "name": s["name"], "aliases": list(s["aliases"]), "surface": "system"}
            for sid, s in SYSTEM_SURFACES.items()]


def is_system_surface(sid: str) -> bool:
    return str(sid or "") in SYSTEM_SURFACES
