#
# System surfaces — BACKEND MIRROR of native frontend surfaces (V2-082).
#
# The SOURCE OF TRUTH is `frontend/app/core/system-surfaces.js` (`SYSTEM_SURFACES`): the front is "the body", its
# genetics are programmed. This module replicates ONLY the VOICE-ADDRESSABLE identity (id + name + FIXED aliases) of
# those surfaces, so the backend name resolver (`widgets/runtime.py::identify`) can unify USER WIDGETS (catalog,
# editable aliases) and SYSTEM SURFACES (hardcoded, NOT editable aliases) in one namespace. Thus "open chat" resolves
# to system and "open the messaging widget" to the catalog, and they are never confused.
#
# Only surfaces with non-null `name`+`aliases` in JS are listed (voice-addressable ones). Transitional/scaffolding
# surfaces (activity-strip, topbar, connstatus, alert, boot) do NOT enter — they are not opened by name.
#
# Synchronization INVARIANT: `test_system_surfaces_sync.py` compares this mirror against JS and FAILS if they diverge —
# adding/editing an addressable surface requires touching both places (or the test calls it out). System aliases are
# UNTOUCHABLE by the user (unlike widget aliases); there is no endpoint to edit them.
#
from __future__ import annotations

# id → {name, aliases}. EXACT replica of entries with name!=null from SYSTEM_SURFACES (frontend). Chat tab routing
# (Processes/Crons) does NOT live here: tool show_panel does it (router._canon_panel) — these chat aliases open the
# surface (default tab).
SYSTEM_SURFACES: dict[str, dict] = {
    "orb": {
        "name": "Orb",
        "aliases": ["orbe", "orb", "el ojo", "ojo", "controles", "subtitulos", "subtítulos",
                    "the eye", "eye", "controls", "subtitles"],
    },
    "chat": {
        "name": "Chat",
        "aliases": ["chat", "muro", "muro de texto", "muro de chat", "escribirte", "hablarte por texto",
                    "conversacion", "conversación", "el chat contigo", "wall", "text wall", "chat wall"],
    },
    "status": {
        "name": "Status",
        "aliases": ["estado", "estado del sistema", "status", "panel de estado", "salud del sistema",
                    "system status", "health"],
    },
    "config": {
        "name": "Settings",
        "aliases": ["config", "configuracion", "configuración", "ajustes", "preferencias", "settings", "opciones",
                    "preferences", "options"],
    },
    "benchmarks": {
        "name": "Benchmarks",
        "aliases": ["benchmarks", "por que estos modelos", "por qué estos modelos", "comparativa",
                    "why these models", "comparison"],
    },
    "debug": {
        "name": "Debug",
        "aliases": ["debug", "depuracion", "depuración", "logs", "logging", "trazas", "timeline", "observabilidad",
                    "traces", "observability"],
    },
    "memory-map": {
        "name": "Memory map",
        "aliases": ["memoria", "mapa de memoria", "mapa de la memoria", "tu memoria", "recuerdos",
                    "memory", "memory map", "memories"],
    },
    "wizard": {
        "name": "Setup wizard",
        "aliases": ["wizard", "asistente", "primer arranque", "configuracion inicial", "configuración inicial",
                    "setup", "setup wizard", "first run", "onboarding"],
    },
    "vault": {
        "name": "Vault",
        "aliases": ["boveda", "bóveda", "secretos", "vault", "contraseñas", "caja fuerte",
                    "secrets", "passwords", "safe"],
    },
}


def surfaces() -> list[dict]:
    """Lista de superficies de sistema dirigibles por voz, en la forma del registro unificado:
    `{id, name, aliases, surface: "system"}`. Consumida por `widgets/registry.py` y el resolver."""
    return [{"id": sid, "name": s["name"], "aliases": list(s["aliases"]), "surface": "system"}
            for sid, s in SYSTEM_SURFACES.items()]


def is_system_surface(sid: str) -> bool:
    return str(sid or "") in SYSTEM_SURFACES
