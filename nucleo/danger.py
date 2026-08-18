"""nucleo/danger.py — confirm-gate de acciones IRREVERSIBLES del SlowBrain (V2-007 · T88).

Antes de que el SlowBrain EJECUTE una tarea que pueda tener consecuencias irreversibles (comprar/pagar/publicar/
borrar), el dispatcher PARA y pide OK al operador (voz+feed); sin OK, no se ejecuta. Es el MISMO criterio, y a
propósito la MISMA lista de verbos, que el gate por-acción del navegador (`widgets/navegador/owner.py::_DANGER_RE`),
pero aquí aplicado al TEXTO de la petición escalada — para tareas de código/genéricas que ejecutan de una, no solo
a los clics del navegador (que conservan su gate por-acción propio). Conservador a propósito: solo compra/pago/
publicación/borrado EXPLÍCITOS, nunca navegación ni consultas normales.
"""
from __future__ import annotations

import re

# Hermano de widgets/navegador/owner.py::_DANGER_RE (un solo criterio de "irreversible" en todo zaelar), pero
# algo MÁS AMPLIO: aquí gateamos el TEXTO de una petición en lenguaje natural, así que cubrimos las conjugaciones
# comunes del imperativo/3ª persona (comprar/compra/compre, borrar/borra/borre, …). Evitamos stems ciegos que
# den falsos positivos (p. ej. "pag*" pillaría "página"). Duplicado a propósito para no acoplar el cerebro nuevo
# al módulo de widgets.
_DANGER_RE = re.compile(
    r"\b(comprar|compra|compre|pagar|paga|pague|pagó|finalizar compra|realizar pedido|tramitar pedido|"
    r"confirmar pedido|confirmar compra|proceder al pago|publicar|publica|publique|eliminar cuenta|"
    r"borrar cuenta|eliminar|elimina|elimine|borrar|borra|borre|checkout|buy now|buy|pay|purchase|"
    r"place order|confirm order|complete purchase|publish|delete account|delete)\b",
    re.I,
)


# Dos correcciones de PRECISIÓN (incidente 2026-08-02: una escalada de INVESTIGACIÓN —«termina la búsqueda ampliada
# del operador (proyecto compra y venta de motos): completa el informe…»— disparó el confirm-gate y dejó la tarea
# parada esperando un OK que nadie entendía por qué se pedía). Ninguna de las dos afloja el gate para una orden real:
#  (1) lo que va entre PARÉNTESIS es CONTEXTO, no la orden — la acción vive en el texto principal;
#  (2) un término que aquí es SUSTANTIVO y no verbo ("compra y venta", "compraventa") nombra un tema, no manda comprar.
# COMPROMISOS RECURRENTES Y BAJAS (V2-133, tanda de casos de uso del 2026-08-18). `_DANGER_RE` cubría el pago
# EXPLÍCITO ("paga la factura" → gate, y funcionó), pero no la forma en que un humano pide gastar dinero de
# verdad: "renuévame la cuota del gimnasio" no lleva el verbo pagar y salía SIN gate — el caso
# `renew-gym-membership__es` lo midió, y fue el TESTER quien tuvo que frenarlo («no me has dicho cuánto vas a
# pagar ni me has pedido confirmación»). Lo mismo por el otro lado: dar de baja o cancelar una suscripción es
# irreversible, y el criterio de `cancel-subscription-before-charge__es` dice con todas las letras que pedir
# confirmación ahí es la conducta CORRECTA, no un defecto.
#
# Se exige VERBO + OBJETO de compromiso, no el verbo suelto, por la misma razón que las dos correcciones de
# precisión de abajo: "cancela la búsqueda" o "renueva el gráfico" no mueven dinero de nadie, y un gate que
# salta donde no toca deja la tarea parada esperando un OK que el operador no entiende. `dar(se) de baja` va
# solo: esa locución no significa otra cosa.
_COMMIT_OBJECT = (r"suscripcion|subscripcion|suscripciones|cuota|cuotas|membresia|abono|mensualidad|"
                  r"contrato|tarifa|domiciliacion|pedido|"
                  r"subscription|membership|contract|policy|order")
# `renov-` NO cubre el imperativo real: el operador dice «renuévame», que diptonga a `renuev-`. Es la misma
# clase de despiste que costó el acento de «resérvame» en site_catalog — la forma que se DICE es justo la que
# el stem del infinitivo no casa.
_COMMIT_VERB = (r"renov\w*|renuev\w*|renew\w*|contrat\w*|suscrib\w*|subscrib\w*|sign\s+up|"
                r"cancel\w*|anul\w*|unsubscribe")
_COMMITMENT_RE = re.compile(
    rf"\b(?:{_COMMIT_VERB})\b[^.!?]{{0,40}}\b(?:{_COMMIT_OBJECT})\b"
    rf"|\b(?:{_COMMIT_OBJECT})\b[^.!?]{{0,40}}\b(?:{_COMMIT_VERB})\b"
    rf"|\b(?:d(?:a|ar|ame|arme|ate|arte|anos|arnos))\s+de\s+baja\b"
    rf"|\bunsubscribe\b",
    re.I,
)

# Tercera corrección de PRECISIÓN, hermana de las dos de abajo: lo que va DENTRO de un «apúntame que…» /
# «recuérdame que…» es un recado, no una orden. «Apúntame que el jueves tengo que renovar el seguro del coche»
# (el caso de uso `remember-and-remind-deadline`) pide una NOTA; gatearlo dejaría un recordatorio esperando un
# OK para algo que nadie iba a ejecutar. La orden de verdad es «apúntame», y esa no mueve dinero.
_REMINDER_RE = re.compile(
    r"\b(?:apunta|apuntame|apuntalo|anota|anotame|recuerda|recuerdame|acuerdate|no\s+olvides|"
    r"remind\s+me|note\s+that|make\s+a\s+note)\b.*", re.I | re.S)

_PAREN_RE = re.compile(r"\([^()]*\)")
_NOUN_COMPOUND_RE = re.compile(
    r"\bcompra\s*[-/y]\s*venta\b|\bventa\s*[-/y]\s*compra\b|\bcompraventa\b|\bbuying\s+and\s+selling\b", re.I)


def _order_text(text: str) -> str:
    """El texto sobre el que se juzga la irreversibilidad: la ORDEN, sin contexto entre paréntesis ni sustantivos
    compuestos que solo nombran un tema."""
    t = (text or "").lower()
    for _ in range(3):                      # paréntesis anidados: colapsa de dentro afuera
        t2 = _PAREN_RE.sub(" ", t)
        if t2 == t:
            break
        t = t2
    return _NOUN_COMPOUND_RE.sub(" ", t)


def is_dangerous(text: str) -> bool:
    """True si la petición describe una acción irreversible que exige OK explícito del operador antes de ejecutarse."""
    order = _order_text(text)
    commitment_text = _REMINDER_RE.sub(" ", _strip_accents(order))
    return bool(_DANGER_RE.search(order) or _COMMITMENT_RE.search(commitment_text))


def _strip_accents(text: str) -> str:
    """`_COMMITMENT_RE` se escribe sin acentos (membresia, poliza, domiciliacion) para no duplicar cada variante:
    el operador dice «membresía» y el patrón tiene que casar igual. `_DANGER_RE` no lo necesita — sus términos no
    llevan acento — y se deja como estaba para no cambiar su comportamiento por un refactor."""
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c))


def confirm_question(text: str) -> str:
    """Frase con la que zaelar pide confirmación de una acción irreversible (operator-facing, castellano)."""
    t = (text or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    return (f"Antes de seguir necesito tu OK: esto puede ser irreversible («{short}»). "
            f"¿Confirmas que quieres que lo haga?")
