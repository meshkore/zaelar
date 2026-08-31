"""Documentation translated to English."""
from __future__ import annotations

import re

# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_DANGER_RE = re.compile(
    r"\b(comprar|compra|compre|pagar|paga|pague|pagó|finalizar compra|realizar pedido|tramitar pedido|"
    r"confirmar pedido|confirmar compra|proceder al pago|publicar|publica|publique|eliminar cuenta|"
    r"borrar cuenta|eliminar|elimina|elimine|borrar|borra|borre|checkout|buy now|buy|pay|purchase|"
    r"place order|confirm order|complete purchase|publish|delete account|delete)\b",
    re.I,
)


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_DANGER_CLITIC_RE = re.compile(
    r"\b(?:paga|compra|borra|elimina|publica|cancela|anula|contrata|renueva|renuev[ae])"
    r"(?:me|te|se|nos|le|les|l[oa]s?)+\b", re.I)

# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# pronombre.
#
# translated implementation note
# translated implementation note
# translated implementation note
_REQUEST_FRAME = (r"puedes|puede|podrias|podria|podras|podra|quieres|quiere|"
                  r"vas a|va a|te importa|me haces el favor de|hazme el favor de|"
                  r"can you|could you|would you|will you|please")
_DANGER_VERB_STEM = (r"pagar|comprar|borrar|eliminar|publicar|cancelar|anular|contratar|renovar|"
                     r"abonar|transferir|adquirir|enviar|mandar")
_DANGER_ASK_CLITIC_RE = re.compile(
    rf"\b(?:{_REQUEST_FRAME})\b[^.!?]{{0,30}}?"
    rf"\b(?:{_DANGER_VERB_STEM})(?:me|te|se|nos|le|les|l[oa]s?)+\b", re.I)

# translated implementation note
# translated implementation note
# translated implementation note
_DANGER_PROCLITIC_RE = re.compile(
    r"\b(?:me|te|se|nos)\s+(?:l[oa]s?)\s+"
    r"(?:pagas|compras|borras|eliminas|publicas|cancelas|anulas|contratas|renuevas|abonas|transfieres)\b",
    re.I)

# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_COMMIT_OBJECT = (r"suscripcion|subscripcion|suscripciones|cuota|cuotas|membresia|abono|mensualidad|"
                  r"contrato|tarifa|domiciliacion|pedido|"
                  r"subscription|membership|contract|policy|order")
# translated implementation note
# translated implementation note
# translated implementation note
_COMMIT_VERB = (r"renov\w*|renuev\w*|renew\w*|contrat\w*|suscrib\w*|subscrib\w*|sign\s+up|"
                r"cancel\w*|anul\w*|unsubscribe")
_COMMITMENT_RE = re.compile(
    rf"\b(?:{_COMMIT_VERB})\b[^.!?]{{0,40}}\b(?:{_COMMIT_OBJECT})\b"
    rf"|\b(?:{_COMMIT_OBJECT})\b[^.!?]{{0,40}}\b(?:{_COMMIT_VERB})\b"
    rf"|\b(?:d(?:a|ar|ame|arme|ate|arte|anos|arnos))\s+de\s+baja\b"
    rf"|\bunsubscribe\b",
    re.I,
)

# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_REMINDER_RE = re.compile(
    r"\b(?:apunta|apuntame|apuntalo|anota|anotame|recuerda|recuerdame|acuerdate|no\s+olvides|"
    r"remind\s+me|note\s+that|make\s+a\s+note)\b[^.!?;]*", re.I)

_PAREN_RE = re.compile(r"\([^()]*\)")
_NOUN_COMPOUND_RE = re.compile(
    r"\bcompra\s*[-/y]\s*venta\b|\bventa\s*[-/y]\s*compra\b|\bcompraventa\b|\bbuying\s+and\s+selling\b", re.I)


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_LOOKUP_HEAD_RE = re.compile(
    r"^\W*(?:me\s+)?(?:puedes\s+|podrias\s+|quiero\s+que\s+)?"
    r"(?:investiga\w*|busca\w*|compara\w*|mira\w*|encuentra\w*|localiza\w*|recomienda\w*|"
    r"research\w*|find\w*|search\w*|compare\w*|look\w*|investigate\w*|recommend\w*)\b", re.I)

# translated implementation note
_PURCHASE_ADJUNCT_RE = re.compile(
    r"\b(?:para\s+comprar\w*|a\s+la\s+venta|en\s+venta|de\s+compra|que\s+comprar\w*|"
    # translated implementation note
    # translated implementation note
    # translated implementation note
    r"(?:cual|cuales|que)\s+comprar\w*|which\s+(?:one\s+)?to\s+buy|what\s+to\s+buy|"
    r"available\s+for\s+purchase|for\s+purchase|for\s+sale|to\s+buy|worth\s+buying)\b", re.I)


def _drop_lookup_adjuncts(order: str) -> str:
    """Documentation translated to English."""
    return _PURCHASE_ADJUNCT_RE.sub(" ", order) if _LOOKUP_HEAD_RE.search(order) else order


def _order_text(text: str) -> str:
    """Documentation translated to English."""
    t = (text or "").lower()
    for _ in range(3):                      # translated implementation note
        t2 = _PAREN_RE.sub(" ", t)
        if t2 == t:
            break
        t = t2
    return _NOUN_COMPOUND_RE.sub(" ", t)


def is_dangerous(text: str) -> bool:
    """Documentation translated to English."""
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    order = _drop_lookup_adjuncts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))
    return bool(_DANGER_RE.search(order) or _DANGER_CLITIC_RE.search(order)
                or _DANGER_ASK_CLITIC_RE.search(order) or _DANGER_PROCLITIC_RE.search(order)
                or _COMMITMENT_RE.search(order))


def _strip_accents(text: str) -> str:
    """Documentation translated to English."""
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c))


# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_MONEY_RE = re.compile(
    r"\b(?:pagar|paga|pague|pagas|comprar|compra|compre|abonar|abona|transferir|transfiere|"
    r"recargar|recarga|renovar|renueva|renuev\w*|contratar|contrata|suscrib\w*|"
    r"pay|buy|purchase|checkout|charge|renew|subscribe|top\s*up)\b"
    r"|\b(?:cuota|factura|recibo|cargo|importe|mensualidad|abono|bill|invoice|fee)\b", re.I)


# translated implementation note
_MONEY_VERB_RE = re.compile(r"\b(?:pagar|comprar|abonar|transferir|adquirir|contratar|renovar|"
                            r"pagas|compras|abonas|transfieres|contratas|renuevas)", re.I)


def ends_a_commitment(text: str) -> bool:
    """Documentation translated to English."""
    return bool(_COMMITMENT_RE.search(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text)))))


def moves_money(text: str) -> bool:
    """Documentation translated to English."""
    # translated implementation note
    # translated implementation note
    order = _drop_lookup_adjuncts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))
    if _MONEY_RE.search(order):
        return True
    # translated implementation note
    # translated implementation note
    # translated implementation note
    m = _DANGER_ASK_CLITIC_RE.search(order) or _DANGER_PROCLITIC_RE.search(order)
    return bool(m and _MONEY_VERB_RE.search(m.group(0)))


def confirm_question(text: str) -> str:
    """Documentation translated to English."""
    t = (text or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    if moves_money(t):
        return (f"Esto mueve dinero («{short}») y no hago ningún cargo sin tu OK. Primero miro el importe "
                f"exacto y te lo digo; cuando me lo confirmes, lo hago. ¿Sigo?")
    return (f"Antes de seguir necesito tu OK: esto puede ser irreversible («{short}»). "
            f"¿Confirmas que quieres que lo haga?")
