"""memory/kv_store.py — the generic KV (`sys_kv`): scoped, structured process state that is not the root STATE
(V2-778 F1, 2026-10-01: moved out of the facade, which had reached its size ceiling).

The functions are unchanged and `memory.api` re-exports them, so every caller still goes through the facade.
"""
from __future__ import annotations

from . import db as _db  # noqa: F401  (asegura import del paquete; get_db perezoso)


# ── KV genérico (sys_kv) — estado ESTRUCTURADO scopeado que no es el ESTADO raíz del operador ────────────────
# V2-069 «una sola mente»: la memoria-de-relación con cada agente (cápsula) necesita persistir un pequeño estado
# ESTRUCTURADO por (cluster,peer) — objetivo, fase, bucles abiertos — SIN inflar el `state()` raíz (que es la
# conciencia del operador) ni crear una tabla nueva. Reusa `sys_kv` (ya lo usan consolidator/rem). Es scope-partido:
# la clave lleva el scope (`capsule:<cluster>:<peer>`), así el estado de una conversación con un agente vive junto a
# todo lo demás pero AISLADO — nunca se mezcla con el estado del operador. Valor = JSON. µs, directo.
#
# ⚠️ FORMA CONSUMIDA DESDE FUERA (2026-08-24). `sys_kv` es `(key, value)` y el plató de los casos de uso lo
# lee y escribe con SQL DIRECTO sobre el fichero, no por aquí — legítimo, porque corre con el motor APAGADO
# (acarrea los cooldowns de proveedor a través de su `--fresh`, que si no se queman ~20 % del presupuesto de
# cada ronda redescubriendo un escalón ya muerto). Consecuencia para quien toque el schema: cambiar los
# nombres de esas dos columnas NO le falla con ruido — su lectura es fail-open y silenciosa, así que dejaría
# de acarrearlos y la única señal sería que sus tandas vuelven a ir lentas. Avisar antes de tocarlo.
def kv_get(key: str, default=None):
    """Lee un valor JSON de sys_kv por clave scopeada. Tolera BD vacía/JSON corrupto → default."""
    import json
    try:
        row = _db.get_db().query_one("SELECT value FROM sys_kv WHERE key=?", (key,))
    except Exception:
        return default
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def kv_set(key: str, value) -> None:
    """Escribe un valor JSON en sys_kv (upsert). Directo (no pasa por la cola: es estado de proceso, no una píldora)."""
    import json
    try:
        _db.get_db().execute(
            "INSERT INTO sys_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
    except Exception:
        pass


def kv_keys(prefix: str = "") -> list[str]:
    """Todas las claves de sys_kv que empiezan por `prefix` (vacío = todas). Para el barrido de mantenimiento
    (homeostasis) que evicta cápsulas muertas sin abrir la BD por su cuenta. El filtro por prefijo se hace en
    Python (sys_kv es pequeño y `LIKE` trataría `_` como comodín). Tolera BD vacía → []."""
    try:
        rows = _db.get_db().query("SELECT key FROM sys_kv ORDER BY key")
        return [r["key"] for r in rows if str(r["key"]).startswith(prefix)]
    except Exception:
        return []


def kv_del(key: str) -> None:
    """Borra una clave de sys_kv (idempotente). Usado por el mantenimiento para evictar estado muerto."""
    try:
        _db.get_db().execute("DELETE FROM sys_kv WHERE key=?", (key,))
    except Exception:
        pass
