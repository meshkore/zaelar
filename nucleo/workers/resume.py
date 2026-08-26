"""nucleo/workers/resume.py — la CONTINUIDAD de una gestión web entre workers y entre procesos (V2-049).

Extraído de `dispatch.py` el 2026-08-26 al pagar el trinquete de arquitectura (V2-342 añadía `_leave_resume`
y el fichero cruzó su techo: la tabla pide extraer un concern, no subir el número). Es un concern COHESIVO:
un dict con espejo durable (`_WEB_RESUME` ⇄ `sys_kv`) y las cinco operaciones sobre él — persistir, restaurar,
la firma de una gestión (`_goal_key`), la entrada que deja al cerrar (`_resume_entry`/`_leave_resume`) y el
casado de una petición nueva con una gestión incompleta (`_find_resume`, con su `take=True` de V2-237).

`dispatch.py` conserva ALIAS con los nombres históricos (`dispatch._WEB_RESUME` es EL MISMO objeto): los
mutadores en sitio de fuera (`reset.py`, `test_rehydrate`) siguen funcionando sin tocarse. Lo que NO viaja
aquí es `_schedule_auto_resume`: dispara escaladas, y eso es del dispatcher.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def _content_words(text: str) -> set:
    from nucleo import matching
    return matching.content_words(text)


_WEB_RESUME: dict[str, dict] = {}
_RESUME_TTL = 1800.0
_RESUME_CAP = 3
# …y como el registro de sesiones, esto vivía SOLO en RAM: un reinicio en mitad de una gestión web se llevaba por
# delante la única forma de CONTINUARLA (el `native_sid` que hace que el worker retome su razonamiento en vez de
# empezar de cero). Espejo en `sys_kv` — estado de proceso, no del operador, igual que el ledger de workers. El TTL
# se aplica igual al cargar, así que una entrada rancia no revive nada.
_RESUME_KEY = "web_resume"


def _resume_persist() -> None:
    """Espeja `_WEB_RESUME` a `sys_kv`. Best-effort y fuera del hot-path (solo al cerrar una sesión web)."""
    try:
        from memory import api as _mem
        if _WEB_RESUME:
            _mem.kv_set(_RESUME_KEY, _WEB_RESUME)
        else:
            _mem.kv_del(_RESUME_KEY)
    except Exception:
        pass


def _resume_restore() -> int:
    """Recarga las entradas de continuidad web que no han caducado. Devuelve cuántas. La llama `start()`."""
    try:
        from memory import api as _mem
        raw = _mem.kv_get(_RESUME_KEY)
        if not isinstance(raw, dict):
            return 0
        now = time.time()
        n = 0
        for k, ent in raw.items():
            if isinstance(ent, dict) and (now - float(ent.get("ts") or 0)) <= _RESUME_TTL:
                _WEB_RESUME[str(k)] = ent
                n += 1
        if n:
            logger.info(f"dispatch: {n} gestión(es) web reanudables recuperadas del proceso anterior")
        return n
    except Exception:
        return 0


def _goal_key(req: str) -> str:
    """Firma estable de una gestión para casar reanudaciones (palabras de contenido, ordenadas)."""
    return " ".join(sorted(_content_words(req)))


def _resume_entry(rec, *, nav_tid: str, resume: dict | None, req: str, key: str,
                  brief: bool, prev_count: int) -> dict:
    """La entrada de reanudación que deja una gestión web INCOMPLETA. Fuera de `_run_session` para poder probarla.

    V2-239 — UN `native_sid` QUE MATÓ A UN WORKER NO SE VUELVE A ARMAR. Aquí había un
    `rec.native_sid or (resume or {}).get("native_sid")` que RECICLABA el id heredado cuando el worker no llegaba
    a tener el suyo. Y no llegar a tenerlo significa exactamente una cosa: el CLI nunca anunció su sesión
    (`rec.native_sid` lo pone el evento `spawned`, que nace del `system/init` de Claude Code — y ese init llega
    igual en un arranque limpio que en un `--resume`, así que una reanudación que PRENDE sí deja su id). O sea que
    el id volvía a la entrada, el siguiente worker se lo llevaba, y volvía a morir en el arranque.

    Medido por el arnés SOBRE el arreglo de V2-237 (05dd79f, worktree limpio, `n_dirty=0`): el `take=True`
    consumía bien y aun así la sesión `0364d544-505` se llevó por delante a los workers 3 y 4, muertos 2/2 a los
    380 y 420 ms. **Consumir la entrada no basta si el camino de la muerte la vuelve a armar con el mismo id.**

    `nav_task` SÍ conserva su respaldo: la pestaña del navegador es otro recurso, sobrevive al worker que la
    abrió y no es lo que estaba matando a nadie.
    """
    return {"nav_task": nav_tid or str((resume or {}).get("nav_task") or ""),
            "native_sid": rec.native_sid,
            "ts": time.time(), "count": int(prev_count) + 1, "goal": req[:200],
            # los criterios ya acordados viajan a la reanudación: recomponerlos a mitad de una búsqueda la
            # convertiría en otra búsqueda distinta sin avisar
            "brief_task": key if brief else str((resume or {}).get("brief_task") or "")}


def _leave_resume(rec, *, nav_tid: str, resume: dict | None, req: str, key: str,
                  brief: bool, prev_count: int) -> None:
    """El RASTRO reanudable que deja una gestión web al cerrar. Fuera de `_run_session` para poder probarlo.

    V2-342 — UNA GESTIÓN CANCELADA TAMBIÉN LO DEJA. Antes `status == "cancelled"` borraba la entrada («parada →
    nada que reanudar»), y esa línea es la que convertía cada «relanza desde cero» en empezar de cero de verdad.
    Medido en la sesión 7575e81a (2026-08-26, search-buy-used-car): 3 workers en 21,6 min, dos cancelados tras
    quejas del operador y relanzados sin heredar nada — 2/3 del tiempo en trabajo descartado, y el bucle se
    retroalimenta (va lento → queja → relanzar de cero → más lento). Parar borra el PROCESO (la pestaña se
    cierra, el auto-resume no dispara: `_resumable` sigue excluyendo `cancelled` — parar es parar, V2-092); lo
    que NO borra es lo andado: la sesión nativa del CLI conserva todo su razonamiento, y si el operador relanza
    el mismo encargo dentro del TTL, `_find_resume` se la entrega al worker nuevo en vez de tirarla. Si nunca lo
    relanza, el TTL la poda; `_RESUME_CAP` corta la cadena si algo está roto de verdad."""
    gk = _goal_key(req)
    if rec.ok:
        _WEB_RESUME.pop(gk, None)                       # completada → nada que reanudar
    elif nav_tid or rec.native_sid:
        _WEB_RESUME[gk] = _resume_entry(rec, nav_tid=nav_tid, resume=resume, req=req, key=key,
                                        brief=brief, prev_count=prev_count)
    _resume_persist()       # sobrevive al reinicio → la reanudación CONTINÚA en vez de empezar de cero


def _find_resume(req: str, *, take: bool = False) -> dict | None:
    """Entrada de reanudación reciente que casa esta petición ('' → None): solape de palabras ≥0.5 con una gestión
    web INCOMPLETA dentro del TTL. Poda de paso las caducadas.

    `take=True` la CONSUME, y eso es lo que impide que varios workers reanuden la misma sesión del CLI.

    Medido por el arnés el 2026-08-21 en `best-plumber-same-day` (1/5, cero filas extraídas), con la correlación
    perfecta: tres workers distintos arrancaron con «REANUDA sesión nativa c5ad1d9e-ad0…» —**la misma**— y los
    tres murieron a los 371, 401 y 374 ms; los dos que abrieron sesión propia sobrevivieron. **3 de 3 contra 0 de
    3.** Una sesión del CLI no se puede reanudar dos veces a la vez: el segundo `--resume` del mismo id muere en
    el arranque, antes de hacer nada. Y como esto se leía sin consumirse, cada escalada de la misma petición
    —incluidas las que dispara el auto-resume— se llevaba el MISMO `native_sid`.

    Consumirla es seguro porque el ciclo de vida ya la devuelve: al cerrar una gestión web incompleta,
    `_run_session` reescribe la entrada con el `native_sid` ACTUAL. Y si el worker muere antes de llegar ahí, la
    reanudación se pierde y el siguiente encargo empieza de cero — que es estrictamente mejor que morir en 400 ms.
    """
    now = time.time()
    req_w = _content_words(req)
    if not req_w:
        return None
    best, best_key, best_score = None, "", 0.0
    for key, ent in list(_WEB_RESUME.items()):
        if now - ent.get("ts", 0) > _RESUME_TTL:
            _WEB_RESUME.pop(key, None)
            continue
        o = set(key.split())
        # V2-342 — se puntúa contra el conjunto MENOR (con suelo de 3), no contra la unión. Medido en la sesión
        # 7575e81a (2026-08-26): el «Relanza desde cero la búsqueda de coches…» real trae 47 palabras de contenido
        # —instrucciones de ritmo, fuentes, avisos— y con Jaccard la gestión incompleta que RELANZA puntuaba 0,208:
        # la verbosidad de la orden ocultaba que la gestión entera está CONTENIDA en ella (11 de sus 17 palabras,
        # 0,647). Estrictamente más permisivo que Jaccard, así que nada que casaba deja de casar; el suelo de 3
        # impide que una petición de una palabra («busca») se lleve cualquier gestión pendiente.
        inter = len(req_w & o)
        denom = max(3, min(len(req_w), len(o)))
        score = inter / denom
        if score >= 0.5 and score > best_score:
            best, best_key, best_score = ent, key, score
    if best is not None and take:
        _WEB_RESUME.pop(best_key, None)
        _resume_persist()          # …y que el rastro durable no se la sirva otra vez tras un reinicio
    return best
