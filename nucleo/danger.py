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
    return bool(_DANGER_RE.search(_order_text(text)))


def confirm_question(text: str) -> str:
    """Frase con la que zaelar pide confirmación de una acción irreversible (operator-facing, castellano)."""
    t = (text or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    return (f"Antes de seguir necesito tu OK: esto puede ser irreversible («{short}»). "
            f"¿Confirmas que quieres que lo haga?")
