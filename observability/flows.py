"""
observability.flows — leer la observabilidad por FLUJOS, no por líneas sueltas.

Un flujo es todo lo que un estímulo desencadena: «enséñame el tiempo en Soria» → transcripción → decisión del
FlashBrain → búsqueda web → apertura del widget → entrega en pantalla. Todos esos eventos comparten
**correlation id** (`corr_id`, el `trace` que nace en `voice/trace.py`), así que la pregunta que de verdad
importa —«¿este flujo acabó bien, cuánto tardó, qué piezas tocó, cuánto costó?»— es una consulta, no una
arqueología a mano por el `.jsonl`.

Solo LECTURA. La escritura la hace `bus/log.py` como sink del bus (un solo escritor, ver `zaelar-memory.md`);
aquí no se abre nunca una conexión de escritura ni se toca el esquema.
"""
from __future__ import annotations

from bus import log as _log


def _rows(sql: str, args: tuple) -> list[dict]:
    with _log._lock:                      # misma conexión y cerrojo que el escritor: no abrimos una 2ª al fichero
        conn = _log._connect()
        cur = conn.execute(sql, args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def flows(limit: int = 50, session_id: str = "", user_id: str = "") -> list[dict]:
    """Los últimos flujos, uno por `corr_id`, con su resumen: cuándo empezó, cuánto duró de punta a punta, cuántos
    eventos, qué FAMILIAS tocó, qué actores trabajaron, tokens gastados y si hubo errores.

    `t_ms` es la duración REAL del flujo (último evento − primero), no la suma de latencias: es lo que el
    operador esperó. `families`/`spans` responden «¿por dónde pasó?» sin abrir el detalle."""
    where = ["corr_id IS NOT NULL", "corr_id != ''"]
    args: list = []
    if session_id:
        where.append("session_id = ?")
        args.append(session_id)
    if user_id:
        where.append("user_id = ?")
        args.append(user_id)
    args.append(int(limit))
    return _rows(
        f"""
        SELECT corr_id,
               MIN(ts_ms)                         AS started_ms,
               MAX(ts_ms) - MIN(ts_ms)            AS t_ms,
               COUNT(*)                           AS events,
               COUNT(DISTINCT cat)                AS families_n,
               GROUP_CONCAT(DISTINCT cat)         AS families,
               GROUP_CONCAT(DISTINCT span)        AS spans,
               SUM(COALESCE(tokens_in, 0))        AS tokens_in,
               SUM(COALESCE(tokens_out, 0))       AS tokens_out,
               SUM(CASE WHEN kind IN ('error', 'alert') THEN 1 ELSE 0 END) AS errors,
               MAX(session_id)                    AS session_id,
               MAX(user_id)                       AS user_id
        FROM events
        WHERE {' AND '.join(where)}
        GROUP BY corr_id
        ORDER BY started_ms DESC
        LIMIT ?
        """,
        tuple(args),
    )


def flow(corr_id: str, limit: int = 500) -> list[dict]:
    """El flujo COMPLETO en orden cronológico — la secuencia exacta de qué pasó y cuándo, que es lo que permite
    ver dónde se torció (p. ej. que se abrió el widget equivocado, y de qué frase salió)."""
    return _rows(
        """
        SELECT id, ts_ms, cat, kind, label, span, ms, model, tokens_in, tokens_out, ver, payload
        FROM events WHERE corr_id = ? ORDER BY id ASC LIMIT ?
        """,
        (str(corr_id), int(limit)),
    )


def sessions(limit: int = 30, user_id: str = "") -> list[dict]:
    """Las últimas sesiones de trabajo con su forma: cuándo, cuánto duraron, cuántos flujos y eventos, tokens y
    errores. Es la vista que después permitirá comparar «cómo le fue a esta persona hoy» contra ayer."""
    where = ["session_id IS NOT NULL", "session_id != ''"]
    args: list = []
    if user_id:
        where.append("user_id = ?")
        args.append(user_id)
    args.append(int(limit))
    return _rows(
        f"""
        SELECT session_id,
               MAX(user_id)                       AS user_id,
               MIN(ts_ms)                         AS started_ms,
               MAX(ts_ms) - MIN(ts_ms)            AS t_ms,
               COUNT(*)                           AS events,
               COUNT(DISTINCT corr_id)            AS flows,
               SUM(COALESCE(tokens_in, 0))        AS tokens_in,
               SUM(COALESCE(tokens_out, 0))       AS tokens_out,
               SUM(CASE WHEN kind IN ('error', 'alert') THEN 1 ELSE 0 END) AS errors
        FROM events
        WHERE {' AND '.join(where)}
        GROUP BY session_id
        ORDER BY started_ms DESC
        LIMIT ?
        """,
        tuple(args),
    )


def stats() -> dict:
    """Cobertura del propio sistema: cuántos eventos llevan ya cada eje. Sirve para detectar un hueco (una pieza
    que emite sin correlation id) en vez de descubrirlo cuando falte el dato al analizar.

    Acotado a `topic='observer'`: la tabla guarda TODO el bus, y las señales internas (`memory.updated`,
    `connector.status`) no son eventos de observabilidad — no llevan familia, ni sesión, ni flujo, y contarlas
    hundía la cobertura con un problema inexistente. `with_corr` bajo SÍ es normal: solo tienen flujo los eventos
    que nacen de un estímulo; los de arranque y los de fondo no vienen de ninguno."""
    r = _rows(
        """
        SELECT COUNT(*)                                                        AS events,
               SUM(CASE WHEN corr_id    IS NOT NULL AND corr_id    != '' THEN 1 ELSE 0 END) AS with_corr,
               SUM(CASE WHEN session_id IS NOT NULL AND session_id != '' THEN 1 ELSE 0 END) AS with_session,
               SUM(CASE WHEN user_id    IS NOT NULL AND user_id    != '' THEN 1 ELSE 0 END) AS with_user,
               COUNT(DISTINCT corr_id)                                         AS flows,
               COUNT(DISTINCT session_id)                                      AS sessions
        FROM events WHERE topic = 'observer'
        """,
        (),
    )
    return r[0] if r else {}
