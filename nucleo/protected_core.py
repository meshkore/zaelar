"""protected_core.py — EL NÚCLEO NO SE MODIFICA. Por voz, por chat, ni por ninguna interfaz del agente.

Directriz del operador, 2026-09-10, verbatim: *«De momento quiero una protección en el que el núcleo y el
motor del sistema no se puede modificar. El sistema a través de la voz o el chat o cualquier interfaz que
tenga permisos solo permite modificar widgets.»*

LO QUE PASÓ (sesión 85eec898). El operador pegó en el chat del agente un mensaje escrito para un agente de
DESARROLLO —«revisa que los rails o canalizaciones de esas acciones vayan a parar aquí»— y el agente lo tomó
como una orden para sí mismo: en el MISMO segundo en que el modelo preguntaba «¿Me pongo a revisar y dejar
eso cableado?», el encargo ya existía, con destino a un worker que escribe ficheros. Lo único que lo frenó
fue la puerta del GASTO — y `nucleo/danger.py` es vocabulario de dinero y comercio: no contiene ni una
palabra sobre tocar el motor. **Fue una coincidencia, no un control.**

Y la protección que parecía existir era accidental: `errand_kind` solo devuelve `code` si la frase nombra un
widget, y solo `code` recibe `Write`/`Edit`. Pero la rama `architect` también devuelve `code` sin ser una
tarea de widget, y esa NO pasa por el generador confinado: es un worker de CLI con `Write`+`Edit` y **el
repositorio entero como directorio de trabajo**. Una frase distinta y el freno desaparecía.

LAS DOS CAPAS, porque la intención y el mecanismo fallan distinto:

  · **MECANISMO** (`writes_are_confined`) — lo que de verdad protege. Un encargo que no sea el generador de
    widgets ni el worker de desarrollo del cluster no recibe permiso de escritura ni el repositorio: aunque
    el modelo se convenza de que debe recablear el motor, no tiene con qué. Falla CERRADO: lo que no se
    reconozca como una de esas dos cosas, no escribe.
  · **INTENCIÓN** (`touches_the_engine`) — para que la negativa sea LEGIBLE. Sin esto el operador vería un
    worker dando vueltas y entregando nada, que es indistinguible de una avería. Con esto se le dice qué se
    ha entendido y cuál es la frontera.

LA FRONTERA, dicha una vez: **el agente puede crear y modificar WIDGETS. Nada más.** El canal de desarrollo
(`kind="dev"`, que solo nace del camino de cluster con `ctx["dev"] and ctx["repo"]`) queda fuera de esta
regla a propósito: es nuestra herramienta de trabajo, no una interfaz del agente, y ya lleva su propio jail
que falla cerrado (`nucleo/dev_worker_guard.py`).
"""
from __future__ import annotations

import re
import unicodedata

# El vocabulario que el propio mensaje del operador usaba, más el resto de nombres con los que se le puede
# pedir a un agente que se toque a sí mismo. NO es una lista de temas prohibidos: es la lista de cosas que
# este agente no puede modificar por ninguna vía, y por eso están sus SINÓNIMOS de producto (rails,
# canalizaciones, cableado) junto a los de implementación (dispatcher, prompt, repositorio).
_ENGINE_NOUN = (r"(?:motor|nucleo|kernel|engine|core|dispatcher|despachador|prompt|rail|rails|"
                r"canalizacion\w*|cablead\w*|flujo\s+prioritario|pipeline|codigo(?:\s+fuente)?|"
                r"repositorio|repo|backend|servidor|arquitectura)")
# ⚠️ El SUBJUNTIVO se escapa si el prefijo llega hasta la consonante que cambia: `modific\w*` NO casa
# «modifiques» (modifi-QUE-s), ni `toca\w*` «toques», ni `revisa\w*` «revises». Medido al escribir esto:
# «quiero que modifiques el motor de voz» pasaba limpio. Los prefijos se cortan ANTES de la alternancia.
_CHANGE_VERB = (r"(?:modifi\w*|cambi\w*|reconfigur\w*|configur\w*|recable\w*|cable\w*|reescrib\w*|escrib\w*|"
                r"refactoriz\w*|arregl\w*|corrij\w*|corrig\w*|edit\w*|toc\w*|toqu\w*|ajust\w*|revis\w*|"
                r"repar\w*|implement\w*|parche\w*|reprogram\w*|program\w*|"
                r"modify|change|rewrite|refactor|fix|patch|rewire|reconfigure)")

# El verbo y el sustantivo tienen que ir CERCA. Sin la ventana, «arregla la cita y de paso mira el motor del
# coche» sería una orden de tocar el motor — y el coste de un falso positivo aquí es negarse a un encargo
# legítimo del operador, que es exactamente el fallo que no queremos importar del otro lado.
_TOUCH_RE = re.compile(_CHANGE_VERB + r"\b[^.!?]{0,60}\b" + _ENGINE_NOUN, re.I)
_TOUCH_REV_RE = re.compile(_ENGINE_NOUN + r"\b[^.!?]{0,40}\b" + _CHANGE_VERB, re.I)

# EL CONTRAPESO, y es la mitad que decide si esto sirve o estorba: un WIDGET sí se puede modificar.
#
# ⚠️ Y la primera versión de esto era un COLADERO, encontrado EN VIVO contra el mensaje real del operador:
# eximía cualquier frase que nombrara un widget EN CUALQUIER PARTE, y la suya acababa en «…para que las
# acciones vayan al widget correcto». O sea que el mensaje exacto que provocó toda esta iniciativa pasaba
# limpio. El test unitario no lo vio porque usaba una versión recortada, sin esa palabra — midió un caso
# cómodo en vez del suyo.
#
# La regla correcta: nombrar un widget exime cuando el widget es lo que se CAMBIA, no cuando se cambia el
# MOTOR para que algo acabe en un widget. Gramaticalmente: el widget tiene que ser el objeto del verbo —
# cerca, y sin una pieza del motor por medio. Misma idea de ventana corta que `errand_kind._MODIFY_CODE_RE`.
_WIDGET_NOUN = r"(?:widget|tarjeta|panel|card)\w*"
_WIDGET_OBJECT_RE = re.compile(_CHANGE_VERB + r"\b((?:(?!" + _ENGINE_NOUN + r"\b)[^.!?]){0,45}?)\b" + _WIDGET_NOUN,
                               re.I)


def _norm(text: str) -> str:
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c))


def touches_the_engine(request: str) -> bool:
    """¿Esta petición pide modificar a ZAELAR mismo? Gramática, nunca intención (la doctrina de V2-095 y
    V2-635): un verbo de cambio junto a una pieza del motor. Un widget nombrado en la frase la exime — eso es
    justo lo que sí se permite."""
    t = _norm(request or "")
    if not t.strip():
        return False
    if not (_TOUCH_RE.search(t) or _TOUCH_REV_RE.search(t)):
        return False
    # Nombrar un widget exime solo si el widget es LO QUE SE CAMBIA — ver la nota sobre el coladero.
    return not _WIDGET_OBJECT_RE.search(t)


def refusal(request: str) -> str:
    """La negativa que se le DICE al operador. Nombra lo que se ha entendido y dónde está la frontera —
    negarse sin decir qué se puede hacer se lee como una avería (la lección de V2-507)."""
    short = (request or "").strip()
    short = (short[:90] + "…") if len(short) > 90 else short
    return (f"Eso me pide cambiarme a mí por dentro («{short}»), y no puedo: mi núcleo y mi motor no se "
            f"tocan desde la voz ni desde el chat. Lo que sí puedo es crear o modificar un widget — dime "
            f"cuál y qué quieres que haga.")


def writes_are_confined(kind: str, request: str) -> bool:
    """¿Puede este encargo escribir código, y dónde? True = SÍ, y confinado por quien lo ejecuta.

    Solo dos cosas escriben: el GENERADOR de widgets (`kind="code"` sobre una petición de widget — corre
    dentro de `GeneratorBackend`, con `ZAELAR_DEV_WORKER_ROOT` apuntando a la carpeta de ESE widget y el
    jail de `dev_worker_guard`, que falla cerrado) y el WORKER DE DESARROLLO del cluster (`kind="dev"`, que
    construye su propio cwd aislado).

    Todo lo demás recibe False, incluida la rama `architect` de `kind="code"`: esa NO pasa por el generador
    y era un worker de CLI con `Write`+`Edit` y el repositorio como cwd. Falla CERRADO — si no se puede
    determinar que es una de las dos, no escribe."""
    k = (kind or "").strip()
    if k == "dev":
        return True
    if k != "code":
        return False
    try:
        from nucleo.agentes import code as _code
        return bool(_code.is_widget_request(request or "") or _code._DELETE_RE.search(request or "")) \
            and not _code.is_architect_request(request or "")
    except Exception:      # noqa: BLE001 — sin los ayudantes no se puede afirmar que sea un widget
        return False
