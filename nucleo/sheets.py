"""nucleo/sheets.py — la HOJA de resultados como superficie de UN encargo (V2-276).

Extraído de `nucleo/dispatch.py` el 2026-08-24 para pagar el trinquete de arquitectura, que llevaba rojo
desde la noche anterior por MIS commits: `dispatch.py` estaba 22 líneas por encima de su techo y la regla de
esa tabla es explícita — un fichero que crece pide EXTRAER, y su único precedente de subida exige poder
decir qué duplicación se retiró. No retiré ninguna, así que se extrae.

Se eligió esta sección porque la frontera ya estaba dibujada: llevaba su propio banner desde V2-227, y
`widgets/results/data.py` y `widgets/navegador/act_api.py` ya importaban de aquí a través de `dispatch` —
una capa de widgets pidiéndole a un gestor de sesiones cómo se llama su caja.

MÓDULO HOJA a propósito: no importa `dispatch`. Las tres funciones que necesitan recorrer el registro vivo
reciben las sesiones como argumento (`sessions=`), y `dispatch` las envuelve pasándole las suyas. Hacerlo al
revés —importar `_SESSIONS` desde aquí— es el ciclo que V2-112 ya pagó (`research.py` cogiendo un nombre
privado de `dispatch`, y solo la suite ENTERA lo cazó, en runtime).

Todo se re-exporta desde `dispatch`: es una mudanza, no un cambio de interfaz.
"""
from __future__ import annotations

import time

from nucleo import surfaces
from nucleo.runtime_ids import boot_id as _boot_id

#: El anillo de fases: lo que cabe en una pestaña sin convertirse en un log. Vive aquí porque es la longitud
#: de lo que la HOJA pinta; `dispatch.record_phase` lo re-importa para recortar el registro con la misma cifra.
PHASES_KEPT = 40

# ── la HOJA de resultados como superficie del progreso (V2-227 ámbito C) ──────────────────────────────────────
# El registro vivo es el ÚNICO dueño de «qué está pasando». La hoja no lo guarda: lo LEE en cada `view_data`,
# igual que `counts`. Guardarlo sería reproducir el estado en dos sitios y quedarse con la copia rancia en
# pantalla — que es exactamente el fallo que este ámbito existe para quitar.
def sheet_sessions(sessions, live_states) -> list:
    """Las sesiones VIVAS cuya superficie es la hoja (`lista`/`item`). El resto de encargos no pintan aquí.

    Recibe el registro en vez de importarlo: ver la nota de módulo HOJA en la cabecera.
    """
    return [r for r in list(sessions)
            if r.status in live_states and surfaces.opens_sheet(getattr(r, "surface", ""))]


def _phrases(rec) -> list:
    """Las fases de un registro, ya legibles y en orden, sin el andamio `{t, s}`."""
    out = []
    for p in list(getattr(rec, "phases", None) or []):
        s = str((p.get("s") if isinstance(p, dict) else p) or "").strip()
        if s:
            out.append(s)
    return out


#: Sello de ESTE proceso. `escalate._seq` vuelve a 0 en cada arranque, así que un `task_id` no identifica un
#: encargo más allá de la vida del motor; un id de hoja SÍ tiene que hacerlo, porque la hoja se guarda en disco y
#: sobrevive al reinicio (V2-233). Aleatorio y corto: no hace falta que sea legible, hace falta que no choque.
def sheet_id_for(task_id) -> str:
    """El id de la HOJA de un encargo. UNA definición: la usan el sellado del record y cualquiera que necesite
    reconstruirlo, para que no haya dos formas de nombrar la misma caja."""
    return f"{_boot_id()}-{str(task_id or '').strip()}"


def sheet_of(rec) -> str:
    """La hoja de un encargo, sellada UNA vez (mismo criterio que `surfaces.set_once`: cambiarla a mitad mueve lo
    que el operador ya está mirando). Devuelve "" si este encargo no tiene hoja — entonces se escribe la de
    siempre, que es lo correcto para un navegador sin encargo detrás."""
    return str(getattr(rec, "sheet", "") or "")


def sheet_for_nav_task(nav_task: str, sessions=()) -> str:
    """La hoja del ENCARGO al que pertenece esta tarea de navegador ("" si no cuelga de ninguno).

    V2-259 — el navegador encuentra cosas y las entrega a la hoja (V2-257), pero la hoja es del ENCARGO y la tarea
    del navegador tiene su propio id: dos navegadores de la misma búsqueda entregan en la MISMA hoja. `_prepare_web`
    ya guarda `rec.nav_task`, así que la vuelta existe; lo que faltaba era pedirla. Sin encargo detrás —el operador
    conduciendo el navegador a mano— devuelve "", que es la hoja de siempre y es lo correcto.
    """
    tid = str(nav_task or "").strip()
    if not tid:
        return ""
    for r in list(sessions):
        if str(getattr(r, "nav_task", "") or "") == tid:
            return sheet_of(r)
    return ""


def sheet_progress(sheet: str = "", sessions=(), live_states=()) -> dict:
    """`{alive, phases}` — lo que la pestaña de PROCESO de la hoja tiene que pintar AHORA MISMO.

    `alive` es «hay un encargo en marcha», no «ha dicho algo»: la hoja se abre antes de la primera fase, y ese
    hueco de unos segundos es justo cuando el operador está mirando la pantalla en blanco que pidió quitar.

    `sheet` acota a UN encargo (V2-259: una hoja por encargo, y su clave es el `task_id`). Sin él se mantiene el
    comportamiento viejo —las fases de todos los encargos vivos, entrelazadas EN ORDEN DE TIEMPO—, que era la
    respuesta honesta cuando la hoja era única: quedarse con un encargo escondía en silencio que había otro
    trabajando. Con hojas separadas eso deja de hacer falta, pero la hoja SIN instancia sigue existiendo y sigue
    mereciendo el relato completo.
    """
    rows = sheet_sessions(sessions, live_states)
    # V2-259 — con UNA hoja por encargo, el relato de una caja es el de SU encargo. El entrelazado de abajo era
    # la respuesta honesta mientras la hoja era única (quedarse con un encargo escondía que había otro); ahora
    # cada uno tiene dónde contarse, y mezclarlos sería contar dos veces lo mismo en dos sitios.
    want = str(sheet or "").strip()
    if want:
        rows = [r for r in rows if sheet_of(r) == want]
    if not rows:
        return {"alive": False, "phases": []}
    seq = []
    for r in rows:
        for p in list(getattr(r, "phases", None) or []):
            s = str((p.get("s") if isinstance(p, dict) else p) or "").strip()
            if s:
                seq.append((float(p.get("t") or 0.0) if isinstance(p, dict) else 0.0, s))
    seq.sort(key=lambda x: x[0])
    return {"alive": True, "phases": [s for _, s in seq][-PHASES_KEPT:]}


def _sheet_open(rec) -> None:
    """ABRIR la hoja al ENCARGAR, que es el gesto entero del ámbito C: sin esto el operador no ve nada hasta que
    hay respuesta, y el contrato de pantalla se queda cumplido en un test y ausente en el producto.

    UNA HOJA POR ENCARGO (V2-259), y su clave es el `task_id`. Antes era única, así que había que elegir entre
    estrenarla —borrándole lo entregado a otro encargo que siguiera escribiendo— y reutilizarla, que enseñaba los
    resultados de la búsqueda anterior como si fueran los de ésta. Ninguna de las dos era buena, y la primera es
    literalmente el «error de borrar búsquedas» que el operador pidió quitar. Con una clave por encargo la
    disyuntiva desaparece: cada uno estrena la suya y nadie pisa a nadie.

    Todo fail-soft: un fallo aquí no puede tumbar una escalada.
    """
    # El SELLO, una vez y antes de nada: todo lo que escriba en esta hoja tiene que nombrarla igual.
    #
    # A RELAY IS NOT A NEW ERRAND (measured 2026-08-23, `cheapest-monitor`). When the provider runs out of
    # quota, `session._finish` relaunches the SAME goal on the next tier — and that relaunch minted a fresh
    # `task_id`, so it minted a fresh SHEET: the operator ended up with `results::…-1` empty and `results::…-2`
    # holding the 13 findings, two boxes for one errand, and the turn saying "they are in your results widget"
    # about the wrong one. Same for the context-overflow handoff (V2-117). If the escalation arrives carrying
    # its predecessor's sheet, it is INHERITED — this is the continuation of the same thing, not another one.
    # INHERITED is asked by comparing against MY OWN, never by checking whether the field is filled. The first
    # version read "already has a sheet ⇒ it came from someone else" and turned a V2-259 test red — rightly: an
    # errand can arrive with ITS OWN sheet already sealed, and that does not make it a relay. A relay's sheet is
    # its PREDECESSOR's, so it does not derive from this `task_id`.
    _mine = ""
    try:
        _mine = sheet_id_for(rec.task_id)
    except Exception:  # noqa: BLE001
        pass
    _inherited = bool(getattr(rec, "sheet", "")) and str(rec.sheet) != _mine
    if not getattr(rec, "sheet", ""):
        rec.sheet = _mine
    _sid = sheet_of(rec)
    try:
        from widgets.results import data as _sheet
        # V2-259 — SU hoja. `fresh` deja de ser una decisión difícil: una hoja nueva es una CLAVE nueva, así que
        # estrenar ya no puede borrarle a nadie lo suyo (que es literalmente lo que el operador pidió evitar).
        #
        # …except when the sheet is INHERITED, where `fresh` is precisely the damage: `present` REPLACES the
        # items, so starting the predecessor's sheet fresh wipes whatever it had already delivered before running
        # out of quota. Inheriting without this turns "two boxes" into "one empty box", which is worse.
        _sheet.begin_task((rec.goal or "").strip(), fresh=not _inherited, sheet=_sid)
        _sheet.prune_sheets()          # la hoja persiste a propósito; N instancias no pueden crecer sin techo
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice.observer import emit
        from widgets.results import data as _sheet2
        emit("widget", "show",
             extra={"id": _sheet2.instance_id(_sid), "src": f"worker:{rec.task_id}"})
    except Exception:
        pass


def _sheet_close(rec) -> None:
    """El encargo ACABÓ: se para el loader y la historia se queda con el informe.

    Dos cosas que solo se pueden hacer aquí. (1) Nadie más avisa del final: el emisor de fases solo dispara al
    CAMBIAR una fase, así que sin esta escritura la tarjeta seguiría diciendo «Trabajando…» sobre un worker que
    ya no existe. (2) El registro vivo se tira al terminar, y con él las frases; la hoja SÍ es persistente —un
    informe que sobrevive a un reinicio con la explicación de cómo se llegó a él borrada cuenta la mitad.
    """
    try:
        from widgets.results import data as _sheet
        _sheet.end_task(_phrases(rec), sheet=sheet_of(rec))
    except Exception:  # noqa: BLE001
        pass


def record_phase(rec, phase: str, phases_kept: int = 0) -> bool:
    """Apunta UNA línea en el diario que lee la pestaña de PROCESO. Devuelve si entró.

    MÓDULO HOJA (V2-281): recibe el REGISTRO, no lo busca — quien lo tiene es `dispatch`, que lo envuelve.

    Es la ÚNICA casa de esa regla, y lo es porque tiene DOS puertas que no se parecen: lo que el worker narra de
    su parte (`hbnote`, vía `session_phase`) y lo que hacemos nosotros al traducir sus pasos de herramienta a una
    frase (`nucleo/workers/progress.phrase`, vía el stream del backend). Hasta el 2026-08-21 la segunda no pasaba
    por aquí, y el efecto no era una línea peor: era que **no había línea**. La sesión `ed9df756` del operador es
    la prueba — el worker abrió Google Maps, cerró el overlay, hizo captura, snapshot y dos clics, extrajo la
    ruta con tráfico, y la pestaña dijo «trabajando» durante dos minutos y medio porque las únicas dos entradas
    que llegaron a este anillo fueron las que el propio worker se molestó en narrar, y llegaron al final.

    Se DEDUPLICA contra la última: tres `scroll` seguidos producen tres veces «recorriendo la página», y tres
    líneas idénticas no informan de nada — parecen progreso sin serlo. El anillo es corto a propósito: esto es lo
    que el operador MIRA, no la auditoría (que ya vive en observabilidad, entera y con su evidencia).
    """
    r, _p = rec, (phase or "").strip()
    if r is None or not _p:
        return False
    if r.phases and r.phases[-1].get("s") == _p:
        return False
    r.phases.append({"t": time.time(), "s": _p})
    del r.phases[:-(phases_kept or PHASES_KEPT)]
    # …y que la tarjeta abierta se entere. `widgets/store.py` emite esto al GUARDAR, y aquí no hay nada
    # que guardar: el proceso es una vista del registro vivo, no un dato de la hoja. Sin este aviso la
    # pestaña se quedaría quieta hasta el siguiente cambio de datos — un panel de progreso que no avanza.
    if surfaces.opens_sheet(getattr(r, "surface", "")):
        try:
            from voice.observer import emit as _emit_w
            from widgets.results import data as _sheet3
            _emit_w("widget", "data",
                    extra={"id": _sheet3.instance_id(sheet_of(r)), "src": "worker"})
        except Exception:
            pass
    return True
