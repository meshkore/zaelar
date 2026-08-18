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


# IMPERATIVO CON CLÍTICO (V2-128, 2026-08-18). En castellano la forma en que de verdad se manda algo lleva el
# pronombre pegado —«págala», «cómpralo», «bórralo», «cancélala»— y `_DANGER_RE` compara formas desnudas con
# `\b`, así que TODAS ellas escapaban del gate. Es el tercer sitio donde muerde el mismo despiste (ya pasó con
# «resérvame» en site_catalog y con «renuévame» aquí arriba): el patrón está escrito con el infinitivo, y el
# operador habla en imperativo. Se exige AL MENOS un clítico, de modo que ni «compras» ni «publicas» ni
# «cancelan» —que no son órdenes— entren por aquí.
_DANGER_CLITIC_RE = re.compile(
    r"\b(?:paga|compra|borra|elimina|publica|cancela|anula|contrata|renueva|renuev[ae])"
    r"(?:me|te|se|nos|le|les|l[oa]s?)+\b", re.I)

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
# Se recorta hasta el FIN DE LA FRASE, no hasta el final del texto (2026-08-18, V2-128): con `.*` un
# «recuérdame pagar la factura. Y de paso págala tú» perdía la orden real que venía detrás. El corte por
# `.!?;` conserva «apúntame que el jueves tengo que renovar el seguro, y recuérdamelo el miércoles» entero
# (una sola frase con comas) y deja intacta cualquier orden que vaya en frase aparte.
_REMINDER_RE = re.compile(
    r"\b(?:apunta|apuntame|apuntalo|anota|anotame|recuerda|recuerdame|acuerdate|no\s+olvides|"
    r"remind\s+me|note\s+that|make\s+a\s+note)\b[^.!?;]*", re.I)

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
    # El recorte del recado se aplica a LOS DOS patrones (V2-128). Antes solo lo veía `_COMMITMENT_RE`, así que
    # «recuérdame PAGAR la factura antes del día 5» disparaba el gate por `_DANGER_RE`: una petición de
    # recordatorio quedaba esperando un OK para un pago que nadie iba a ejecutar. La orden ahí es «recuérdame»,
    # y esa no mueve dinero — es la misma frontera que el propio caso `pay-known-bill` marca al revés (una ORDEN
    # de pagar NO es pedir un recordatorio).
    # Los acentos se quitan UNA vez y antes de todo: `_REMINDER_RE` está escrito sin ellos («recuerdame») y
    # `_order_text` solo minusculiza, así que el imperativo REAL —«recuérdame», con tilde— no casaba y el recado
    # se colaba como orden. Es el mismo despiste que ya costó «resérvame» en site_catalog y «renuévame» aquí
    # mismo: la forma que el operador DICE es justo la que el patrón sin normalizar no ve.
    order = _REMINDER_RE.sub(" ", _strip_accents(_order_text(text)))
    return bool(_DANGER_RE.search(order) or _DANGER_CLITIC_RE.search(order)
                or _COMMITMENT_RE.search(order))


def _strip_accents(text: str) -> str:
    """`_COMMITMENT_RE` se escribe sin acentos (membresia, poliza, domiciliacion) para no duplicar cada variante:
    el operador dice «membresía» y el patrón tiene que casar igual. `_DANGER_RE` no lo necesita — sus términos no
    llevan acento — y se deja como estaba para no cambiar su comportamiento por un refactor."""
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c))


# ¿Esta orden MUEVE DINERO, o solo es irreversible? Los dos paran en el gate, pero no se preguntan igual
# (V2-129, medido). El caso `renew-gym-membership` acabó con el propio tester frenando la ejecución:
#
#   «un momento, no me has dicho cuánto vas a pagar ni me has pedido confirmación.
#    No hagas el cargo hasta que me pases el importe y te confirme.»
#
# Y tenía razón dos veces: no había importe, y no podía haberlo — nadie había mirado la cuota todavía. Una
# pregunta genérica («esto puede ser irreversible, ¿confirmas?») no dice lo único que el operador necesita oír
# antes de autorizar un cargo: que NADA se paga sin que él vea la cifra primero. Se dice, y así la promesa
# existe aunque el importe aún no.
_MONEY_RE = re.compile(
    r"\b(?:pagar|paga|pague|pagas|comprar|compra|compre|abonar|abona|transferir|transfiere|"
    r"recargar|recarga|renovar|renueva|renuev\w*|contratar|contrata|suscrib\w*|"
    r"pay|buy|purchase|checkout|charge|renew|subscribe|top\s*up)\b"
    r"|\b(?:cuota|factura|recibo|cargo|importe|mensualidad|abono|bill|invoice|fee)\b", re.I)


def moves_money(text: str) -> bool:
    """True si la orden implica un CARGO. Subconjunto de `is_dangerous`: todo lo que mueve dinero es
    irreversible, pero borrar un widget o publicar un anuncio no cuesta nada."""
    # Acentos fuera ANTES de recortar el recado — el mismo orden que `is_dangerous`, y por el mismo motivo:
    # `_REMINDER_RE` está escrito sin tildes y «recuérdame» es la forma que se dice.
    return bool(_MONEY_RE.search(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text)))))


def confirm_question(text: str) -> str:
    """Frase con la que zaelar pide confirmación de una acción irreversible (operator-facing, castellano)."""
    t = (text or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    if moves_money(t):
        return (f"Esto mueve dinero («{short}») y no hago ningún cargo sin tu OK. Primero miro el importe "
                f"exacto y te lo digo; cuando me lo confirmes, lo hago. ¿Sigo?")
    return (f"Antes de seguir necesito tu OK: esto puede ser irreversible («{short}»). "
            f"¿Confirmas que quieres que lo haga?")
