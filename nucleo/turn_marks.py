"""Lo que un turno YA le puso delante al modelo — y por tanto no hay que volver a ponerle.

El prompt tiene varias caras que dicen «díselo LA PRIMERA VEZ» (la muerte de una tarea, la oferta de pararla)
y el modelo **no puede saber si es la primera**: eso es un hecho NUESTRO. V2-224 lo aprendió con el aviso de
muerte —la misma cláusula anti-repetición falló en las DOS direcciones opuestas en dos rondas del mismo
commit— y la conclusión fue que «¿ya se lo dije?» no se deduce de la ventana, se cuenta.

Vive aparte porque es un asunto propio y `dispatch` es un fichero-dios con techo: el trinquete pidió extraer
un módulo en vez de subirlo, y tenía razón. Se re-exporta desde `dispatch` para que los llamantes sigan
pidiéndoselo a la fachada de siempre.

**La regla que gobierna a todos sus inquilinos, y es de V2-224: callar la repetición NO es callar el estado.**
Lo que deja de darse es el AVISO; el hecho —sigue muerta, sigue sin avanzar, y desde cuándo— se queda.
"""
from __future__ import annotations

_STALL_OFFERED: dict[str, int] = {}


def mark_stall_offered(task_ids) -> None:
    """Un turno ya ha llevado delante la OFERTA DE PARAR esta tarea (V2-454).

    Hermano exacto de `mark_death_reported`, y por la misma razón: el bloque dice «dilo con esas letras **la
    primera vez** que salga a colación y ofrece pararla», y el modelo **no puede saber si es la primera** — eso
    es un hecho NUESTRO, no algo que se deduzca de la ventana. Sin contarlo, la oferta se renderiza en todos
    los turnos que la tarea siga atascada y el turno la repite: medido sobre las 334 rondas guardadas,
    **49 (14 %) repiten la oferta de parar dos o más veces**, y diez de las últimas quince del 2026-08-28.

    El daño no es la redundancia: el operador YA CONTESTÓ. En `search-buy-used-car` (10:57) dijo «párale y
    prueba de nuevo, o miramos por otro sitio, tú decides» y el turno siguiente volvió a plantear la misma
    disyuntiva — el juez lo puso de bloqueador [alta].

    Y la regla que gobierna la redacción es la que dejó V2-224: **callar la repetición no es callar el
    estado.** El HECHO (sigue sin avanzar, y desde cuándo) se queda; lo que deja de darse es la oferta.
    """
    for tid in (task_ids or []):
        t = str(tid)
        _STALL_OFFERED[t] = int(_STALL_OFFERED.get(t) or 0) + 1


def stall_offered(task_id) -> int:
    """Cuántos turnos han llevado ya la oferta de parar ESTA tarea."""
    return int(_STALL_OFFERED.get(str(task_id)) or 0)


