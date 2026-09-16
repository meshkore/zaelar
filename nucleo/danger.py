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
    r"borrar cuenta|checkout|buy now|buy|pay|purchase|"
    r"place order|confirm order|complete purchase|publish|delete account)\b",
    re.I,
)

# ── BORRAR gates on its OBJECT, never on the bare verb (V2-707 F0) ──────────────────────────────────────────
# Every other verb in `_DANGER_RE` names something that is irreversible WHEREVER it happens: paying moves
# money, publishing is outward-facing. «Borrar» is the one that does not — it means one thing on the
# operator's bank account and another on a row of his own agenda, and until now the bare verb decided for
# both. Measured 2026-09-16 (session cb0ac5da, i=7917→7923): «I want you to delete that meeting and notify
# the other person» tripped `delete`, so `dispatch._run_session` PARKED the task before starting it and
# spoke «Before I go on I need your OK: this could be irreversible». The Brain Worker — which had
# `hbwidget read agenda`, the real row ids and `mensajeria.send_to`, i.e. everything the errand needed —
# never ran a single step. The order took five minutes and ended undone.
#
# A widget row is not ungoverned: every mutation passes `widgets/server_api._dispatch`, where the V2-705
# contract refuses a destructive action with an empty selector and `store.save` keeps a snapshot of what it
# overwrites. That is a rail on CONSEQUENCE and it is the one that works. This gate is for what has NO
# funnel — the open world the worker reaches through a browser — so it now asks the question that actually
# separates the two: **what is being deleted**. The object list is closed and every entry names something
# with no undo and no mirror of ours: an account, a profile, a subscription, a repository, a database, a
# backup. `[^.!?]{0,24}` lets a determiner through («borra MI cuenta de Spotify»), which the old adjacent
# `borrar cuenta` literal did not — so this is stricter than the bare verb and LOOSER than nothing on the
# case the tests already pin («borra la cuenta» must keep stopping).
_DESTROY_VERB = (r"borra|borrar|borre|borras|borrame|elimina|eliminar|elimine|eliminas|"
                 r"delete|remove|wipe|erase|destroy|drop")
_DESTROY_OBJECT = (r"cuenta|cuentas|perfil|usuario|suscripcion|suscripciones|repositorio|repo|"
                   r"base de datos|copia de seguridad|respaldo|historial|disco duro|"
                   r"account|accounts|profile|subscription|repository|database|backup|"
                   r"hard drive|everything|all my data|my data")
_DESTROY_OBJECT_RE = re.compile(
    rf"\b(?:{_DESTROY_VERB})\b[^.!?]{{0,24}}?\b(?:{_DESTROY_OBJECT})\b", re.I)


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

# ── A COMPLAINT ABOUT WHAT ALREADY HAPPENED IS NOT AN ORDER (V2-707 F6) ─────────────────────────────────────
# Measured in session 080b96a7 (2026-09-16). After two `clear_range` sweeps had run, he said, in this order:
#
#   i=10804  «No. You did delete all»                                        → task 2 opened
#   i=10829  «No. You did delete all day, and I just set three of them.»      → task 3 opened
#   i=10873  «Are you stupid? You just did delete.»                           → task 5 opened (deduped)
#   i=11064  «…items that you did delete without my permission.»              → merged into a live task
#
# Three escalations to a Brain Worker while he was asking for an explanation, each one going on to park at
# the irreversibles gate and be discarded. `is_dangerous` is the classifier that decides ALL of it — the
# voice backstop (`providers/nucleo.py`), the probe's mirror, and `dispatch._run_session`'s own gate — and
# it read «delete» in a sentence whose grammar says the act is already in the past and was not asked for.
#
# The fix is a SUBTRACTION of reach, not a new guard, and it uses the technique this module already relies
# on twice: strip the clause, THEN look for the verb. `_REMINDER_RE` does it so «recuérdame pagar…» is not
# an order to pay, and `_AMOUNT_QUESTION_RE` so «¿cuánto hay que pagar?» is not either. Same shape, third
# case: an accusation in the past tense, and a question about whether it happened.
#
# The clause ends at the next `. ! ? ; ,` — deliberately at the COMMA too, so a turn that complains AND then
# orders keeps its order: «you deleted my account without asking, now delete the other one» still stops.
# «you have to pay» is untouched (the frame demands a past participle or `did`), and so is «can you pay?».
_PAST_ACT_RE = re.compile(
    r"\b(?:why\s+|who\s+|when\s+|how\s+)?did\s+you\b[^.!?;,]*"
    r"|\byou\s+(?:just\s+|already\s+)?did\b[^.!?;,]*"
    r"|\byou(?:'ve|\s+have)\s+(?:just\s+|already\s+)?\w+ed\b[^.!?;,]*"
    r"|\byou\s+(?:just|already)\s+\w+ed\b[^.!?;,]*"
    r"|\bi\s+(?:never|didn'?t|did\s+not)\s+(?:ask|asked|tell|told|say|said)\b[^.!?;,]*"
    r"|\bpor\s+que\s+(?:me\s+|nos\s+|las?\s+|los?\s+)*(?:has|habeis|ha|han)\b[^.!?;,]*"
    r"|\b(?:ya\s+)?(?:me\s+|nos\s+|te\s+|se\s+|las?\s+|los?\s+)*(?:has|habias)\s+\w+d[oa]s?\b[^.!?;,]*"
    r"|\bacabas\s+de\s+\w+\b[^.!?;,]*"
    r"|\bno\s+te\s+(?:he|hemos)\s+(?:dicho|pedido)\b[^.!?;,]*"
    r"|\b(?:nunca|jamas)\s+te\s+(?:he|hemos)\s+(?:dicho|pedido)\b[^.!?;,]*",
    re.I)


def _drop_past_acts(order: str) -> str:
    """Remove the clauses that TALK ABOUT an act instead of ordering one, before any verb is looked for."""
    return _PAST_ACT_RE.sub(" ", order)


def about_a_past_act(text: str) -> bool:
    """True when the turn only DISCUSSES something already done — nothing left to gate once the accusation
    is removed. Public so the timeline can say why a turn did not escalate."""
    order = _strip_accents(_order_text(text))
    return bool(_PAST_ACT_RE.search(order)) and not is_dangerous(text)


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


# An AMOUNT QUESTION is not a payment (V2-645). Measured live (the La Mella session, 2026-09-09): the
# escalation «revisa el grupo… y averigua cuánto hay que pagar» tripped the money gate THREE times — the
# operator was asked to confirm a charge nobody proposed, over a task whose whole job was READING messages
# to find out a number. «cuánto hay que pagar» / «how much do we have to pay» asks ABOUT money and moves
# none. Unlike _PURCHASE_ADJUNCT_RE this drop is NOT gated on a lookup head: a composed worker request
# starts with «El operador…», so the ^-anchored head never matches there, and the interrogative itself is
# the evidence. Narrow on purpose: only «cuanto/how much» within a few words of a money verb is dropped —
# «paga lo que pida» and «averigua cuánto es y págalo» keep their imperative and still gate (tests).
_AMOUNT_QUESTION_RE = re.compile(
    r"\bcuant[oa]s?\b(?:\s+\w+){0,3}?\s+(?:pagar|abonar|pago|pagamos|pagas|debo|debemos|debe|deben|"
    r"cuesta|cuestan|costaria|vale|valen|transferir|aportar|poner)\w*"
    r"|\bhow\s+much\b(?:\s+\w+){0,4}?\s+(?:pay|owe|owed|cost|costs|transfer|chip\s+in)\w*", re.I)


def _drop_amount_questions(order: str) -> str:
    """A question about an amount is dropped BEFORE the danger/money regexes look for their verbs."""
    return _AMOUNT_QUESTION_RE.sub(" ", order)


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
    order = _drop_past_acts(
        _drop_amount_questions(_drop_lookup_adjuncts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))))
    return bool(_DANGER_RE.search(order) or _DANGER_CLITIC_RE.search(order)
                or _DANGER_ASK_CLITIC_RE.search(order) or _DANGER_PROCLITIC_RE.search(order)
                or _COMMITMENT_RE.search(order) or _DESTROY_OBJECT_RE.search(order))


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
    return bool(_COMMITMENT_RE.search(
        _drop_past_acts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))))


def moves_money(text: str) -> bool:
    """Documentation translated to English."""
    # translated implementation note
    # translated implementation note
    order = _drop_past_acts(
        _drop_amount_questions(_drop_lookup_adjuncts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))))
    if _MONEY_RE.search(order):
        return True
    # translated implementation note
    # translated implementation note
    # translated implementation note
    m = _DANGER_ASK_CLITIC_RE.search(order) or _DANGER_PROCLITIC_RE.search(order)
    return bool(m and _MONEY_VERB_RE.search(m.group(0)))


def confirm_question(text: str) -> str:
    """The sentence the operator HEARS before an irreversible or money-moving action.

    V2-682 — it used to be two Spanish literals right here, and he heard the money one verbatim in the
    middle of an English session (2026-09-12 20:45), fired by the STT rendering «pause» as «pay». A gate
    that stops the product doing something has to explain itself in HIS language or it reads as a fault."""
    t = (text or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    from i18n import langs as _lg
    sp = _lg.current_language()
    tpl = sp.spend_confirm if moves_money(t) else sp.irreversible_confirm
    return tpl.format(what=short)
