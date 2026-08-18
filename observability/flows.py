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
    operador esperó. `families`/`spans` responden «¿por dónde pasó?» sin abrir el detalle.

    `origin` es el ARGUMENTO con el que nació el flujo (`voice/trace.py::begin(origin=...)`: `turno`/`kickoff`
    para lo que dice el operador, `ui`/`cron`/`proactivo`/`cluster`/`probe` para lo que NO es una petición
    suya, `pulso` para el latido/evaluador del cluster comprobando una conversación INACTIVA por su cuenta —
    distinto de `cluster`, que es un peer diciendo algo de verdad) — hay como mucho UNA fila `kind='trace'` por
    `corr_id` (el evento raíz), así que `MAX(CASE...)` la
    aísla sin un JOIN. `title` es el texto de ESE mismo evento raíz (lo que disparó el flujo): deja que quien
    lo muestra (el tablero del master) rotule la columna sin adivinar de qué iba mirando el resto de eventos."""
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
               MAX(ts_ms)                         AS last_ms,
               MAX(ts_ms) - MIN(ts_ms)            AS t_ms,
               COUNT(*)                           AS events,
               COUNT(DISTINCT cat)                AS families_n,
               GROUP_CONCAT(DISTINCT cat)         AS families,
               GROUP_CONCAT(DISTINCT span)        AS spans,
               SUM(COALESCE(tokens_in, 0))        AS tokens_in,
               SUM(COALESCE(tokens_out, 0))       AS tokens_out,
               SUM(CASE WHEN kind IN ('error', 'alert') THEN 1 ELSE 0 END) AS errors,
               SUM(CASE WHEN kind = 'flow' AND label = 'end' THEN 1 ELSE 0 END) AS ended_events,
               -- The merge marker is EXCLUDED from origin/title: it records that this flow was ABSORBED, not why it
               -- was born. Today MAX() prefers 'turno' over 'merge' alphabetically, which is luck rather than a
               -- contract, and a flow whose origin read 'merge' would carry the wrong tag wherever it is shown.
               MAX(CASE WHEN kind = 'trace' AND label != 'merge' THEN label END) AS origin,
               MAX(CASE WHEN kind = 'trace' AND label != 'merge'
                        THEN json_extract(payload, '$.text') END) AS title,
               -- WHICH flow this one was merged into, if any (`voice/trace.py::merge`). A reader needs it to show a
               -- merged pair as ONE thread instead of two: the merge machinery has existed since V2-105 but this
               -- projection never exposed the relation, so every consumer kept treating the absorbed trace as a
               -- flow of its own. Kept in sync with `cloud/backoffice/src/flyQuery.js`, which mirrors this SQL for
               -- the cloud path — the two-surfaces rule: a column added on one side only fails by coming out EMPTY.
               MAX(CASE WHEN kind = 'trace' AND label = 'merge'
                        THEN json_extract(payload, '$.merge_into') END) AS merge_into,
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
    # `topic` va en la proyección a propósito: un flujo NO es solo observabilidad. Otras señales del bus
    # (`turn.completed`, `memory.updated`…) viajan con el mismo correlation id, y son parte legítima de la
    # historia del flujo — pero no traen `kind`/`label`, así que sin el topic salían como filas VACÍAS y
    # misteriosas en el visor. Un renglón que no se sabe qué es hace desconfiar de toda la tabla.
    return _rows(
        """
        SELECT id, ts_ms, topic, cat, kind, label, span, ms, model, tokens_in, tokens_out, ver, payload
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


def session(session_id: str) -> dict:
    """UNA sesión con su forma, para abrirla y auditarla: cuándo empezó, cuánto lleva/duró, cuántos flujos y
    eventos, tokens, errores. Devuelve `{}` si no existe — el que pregunta decide qué hacer con eso, aquí no se
    inventa una sesión vacía que parezca real."""
    r = _rows(
        """
        SELECT session_id,
               MAX(user_id)                       AS user_id,
               MIN(ts_ms)                         AS started_ms,
               MAX(ts_ms)                         AS last_ms,
               MAX(ts_ms) - MIN(ts_ms)            AS t_ms,
               COUNT(*)                           AS events,
               COUNT(DISTINCT corr_id)            AS flows,
               SUM(COALESCE(tokens_in, 0))        AS tokens_in,
               SUM(COALESCE(tokens_out, 0))       AS tokens_out,
               SUM(CASE WHEN kind IN ('error', 'alert') THEN 1 ELSE 0 END) AS errors,
               GROUP_CONCAT(DISTINCT cat)         AS families,
               MAX(ver)                           AS ver
        FROM events WHERE session_id = ?
        """,
        (str(session_id),),
    )
    row = r[0] if r else {}
    return row if row and row.get("events") else {}


def events(session_id: str = "", corr_id: str = "", since_id: int = 0, limit: int = 500) -> list[dict]:
    """Los eventos EN CRUDO y en orden, con su payload completo — el material de la auditoría (2026-08-10).

    `since_id` es lo que hace posible **seguir una sesión viva sin repetirse**: el que lee guarda el último `id`
    que vio y pide lo que haya después. Es un cursor sobre una clave monótona (`AUTOINCREMENT`), no una ventana
    de tiempo: ni pierde eventos que lleguen con el mismo milisegundo ni los cuenta dos veces.

    El `payload` va TAL CUAL (JSON crudo, sin tocar): ahí viven la evidencia y los campos que el resto de la
    proyección no sube a columnas. Quien audita necesita el original, no un resumen nuestro."""
    where, args = ["topic = 'observer'"], []
    if session_id:
        where.append("session_id = ?")
        args.append(str(session_id))
    if corr_id:
        where.append("corr_id = ?")
        args.append(str(corr_id))
    if since_id:
        where.append("id > ?")
        args.append(int(since_id))
    args.append(int(limit))
    return _rows(
        f"""
        SELECT id, ts_ms, topic, corr_id, session_id, user_id, cat, kind, label, span, ms, model,
               tokens_in, tokens_out, ver, payload
        FROM events WHERE {' AND '.join(where)} ORDER BY id ASC LIMIT ?
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
