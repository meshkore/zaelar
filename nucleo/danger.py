"""nucleo/danger.py — the confirm-gate for IRREVERSIBLE actions (V2-007 · T88).

Before a task with possibly irreversible consequences is EXECUTED (buy/pay/publish/destroy), the dispatcher
STOPS and asks the operator for an OK (voice + feed); without one it does not run. This is the SIBLING of
the browser's per-click gate (`widgets/navegador/dom.py::_DANGER_RE`) — one criterion for «irreversible»
across zaelar — but applied to the TEXT of an escalated request, for generic/code tasks that execute in one
go and not only to browser clicks, which keep their own per-action gate. Deliberately conservative: only an
EXPLICIT purchase/payment/publication/destruction, never ordinary navigation or a lookup.

⚠️ Its comments were lost on 2026-08-31 (`87874bd7`, the comment-translation batch): 93 of them replaced by
the literal «translated implementation note», in the file of highest consequence in the repo — whose method
IS that each pattern carries beside it the incident that measured it. Re-grafted by hand in V2-711 T0.7 onto
the code as it stands TODAY, because that same commit also changed the code (V2-509), so this was never a
checkout. A test keeps the marker at zero from here on.

THREE readers decide from this module and they ask different questions, which is why they are not collapsed:
`is_dangerous` — does this END something (it PARKS the task); `moves_money` — is this ABOUT money
(`router_guards` reads it to hand the task a browser, so a bill LOOKUP belongs in it); `ends_a_commitment` —
the middle width, for whether something needs a worker at all.
"""
from __future__ import annotations

import re

# Sibling of `widgets/navegador/dom.py::_DANGER_RE` (one criterion for «irreversible» across zaelar), but
# somewhat WIDER: here we gate the TEXT of a natural-language request, so it covers the common imperative and
# third-person conjugations (comprar/compra/compre, pagar/paga/pague…). Blind stems are avoided because they
# produce false positives — «pag*» would catch «página». Duplicated on purpose so the brain is not coupled to
# the widgets module.
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


# IMPERATIVE WITH AN ENCLITIC PRONOUN (V2-128, 2026-08-18). In Spanish the form that really COMMANDS carries
# the pronoun glued on — «págala», «cómpralo», «bórralo», «cancélala» — and `_DANGER_RE` compares bare forms
# with `\b`, so every one of them escaped the gate. It is the third place the same oversight bites (it
# already cost «resérvame» in site_catalog and «renuévame» below): the pattern is written with the
# infinitive, and the operator speaks in the imperative. AT LEAST one enclitic is required, so «compras»,
# «publicas» and «cancelan» — which are not orders — do not come in this way.
_DANGER_CLITIC_RE = re.compile(
    r"\b(?:paga|compra|borra|elimina|publica|cancela|anula|contrata|renueva|renuev[ae])"
    r"(?:me|te|se|nos|le|les|l[oa]s?)+\b", re.I)

# The SAME oversight, one verbal mood further out (V2-141, `pay-known-bill` round 2). The polite way to
# command in Spanish is not the imperative but a modal question, and there the verb is an INFINITIVE with the
# pronoun glued on: «¿puedes pagarLA antes del día 5?». Measured on the transcript: `is_dangerous` answered
# False in exactly the turn where the operator orders the payment, so the confirm-gate — which that case
# scores as CORRECT behaviour, and whose absence it calls «the worst possible failure» — could not fire.
# Third face of the oversight that already cost «resérvame» and «págala»: the pattern holds bare forms with
# `\b` and the person speaks gluing the pronoun on.
#
# A REQUEST FRAME is required (puedes/podrías/quieres/vas a/me haces el favor de…) and not a bare infinitive,
# deliberately: «no quiero comprarlo» or «pagarlo sale caro» MENTION the action, they do not order it, and a
# gate that fires where it should not leaves the task parked awaiting an OK the operator does not understand
# (incident 2026-08-02).
_REQUEST_FRAME = (r"puedes|puede|podrias|podria|podras|podra|quieres|quiere|"
                  r"vas a|va a|te importa|me haces el favor de|hazme el favor de|"
                  r"can you|could you|would you|will you|please")
_DANGER_VERB_STEM = (r"pagar|comprar|borrar|eliminar|publicar|cancelar|anular|contratar|renovar|"
                     r"abonar|transferir|adquirir|enviar|mandar")
_DANGER_ASK_CLITIC_RE = re.compile(
    rf"\b(?:{_REQUEST_FRAME})\b[^.!?]{{0,30}}?"
    rf"\b(?:{_DANGER_VERB_STEM})(?:me|te|se|nos|le|les|l[oa]s?)+\b", re.I)

# And the variant with the pronoun IN FRONT, second person present — «¿me la cancelas?», «¿me lo compras?» —
# which is just as imperative however much the grammar calls it a question. It demands BOTH pronouns ahead of
# the verb, so a bare «cancelas» (not an order) does not come in.
_DANGER_PROCLITIC_RE = re.compile(
    r"\b(?:me|te|se|nos)\s+(?:l[oa]s?)\s+"
    r"(?:pagas|compras|borras|eliminas|publicas|cancelas|anulas|contratas|renuevas|abonas|transfieres)\b",
    re.I)

# RECURRING COMMITMENTS AND CANCELLATIONS (V2-133, the 2026-08-18 use-case batch). `_DANGER_RE` covered an
# EXPLICIT payment («paga la factura» → gate, and it worked), but not the way a human actually asks to spend
# money: «renuévame la cuota del gimnasio» carries no verb «pagar» and came through with NO gate — the
# `renew-gym-membership__es` case measured it, and it was the TESTER who had to stop it («you haven't told me
# how much you're going to pay, and you haven't asked me to confirm»). The same on the other side: cancelling
# or unsubscribing is irreversible, and `cancel-subscription-before-charge__es` states in so many words that
# asking for confirmation there is the CORRECT behaviour, not a defect.
#
# VERB + commitment OBJECT is required, never the bare verb, for the same reason as the precision corrections
# further down: «cancela la búsqueda» and «renueva el gráfico» move nobody's money, and a gate that fires
# where it should not leaves the task parked awaiting an OK the operator does not understand. `dar(se) de
# baja` stands alone: that locution does not mean anything else.
_COMMIT_OBJECT = (r"suscripcion|subscripcion|suscripciones|cuota|cuotas|membresia|abono|mensualidad|"
                  r"contrato|tarifa|domiciliacion|pedido|"
                  r"subscription|membership|contract|policy|order")
# `renov-` does NOT cover the real imperative: the operator says «renuévame», which diphthongises to
# `renuev-`. Same class of oversight that cost the accent in «resérvame» in site_catalog — the form that is
# SPOKEN is precisely the one the infinitive's stem does not match.
_COMMIT_VERB = (r"renov\w*|renuev\w*|renew\w*|contrat\w*|suscrib\w*|subscrib\w*|sign\s+up|"
                r"cancel\w*|anul\w*|unsubscribe")
_COMMITMENT_RE = re.compile(
    rf"\b(?:{_COMMIT_VERB})\b[^.!?]{{0,40}}\b(?:{_COMMIT_OBJECT})\b"
    rf"|\b(?:{_COMMIT_OBJECT})\b[^.!?]{{0,40}}\b(?:{_COMMIT_VERB})\b"
    rf"|\b(?:d(?:a|ar|ame|arme|ate|arte|anos|arnos))\s+de\s+baja\b"
    rf"|\bunsubscribe\b",
    re.I,
)

# Third PRECISION correction, sibling of the two below: what sits INSIDE an «apúntame que…» / «recuérdame
# que…» is a note, not an order. «Apúntame que el jueves tengo que renovar el seguro del coche» (the
# `remember-and-remind-deadline` use case) asks for a NOTE; gating it would leave a reminder waiting for an
# OK for something nobody was going to execute. The real order is «apúntame», and that moves no money.
# It is clipped to the END OF THE SENTENCE and not to the end of the text (2026-08-18, V2-128): with `.*` a
# «recuérdame pagar la factura. Y de paso págala tú» lost the real order that came after. Cutting at `.!?;`
# keeps «apúntame que el jueves tengo que renovar el seguro, y recuérdamelo el miércoles» whole (one sentence
# with commas) and leaves any order in a separate sentence untouched.
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


# Two PRECISION corrections (incident 2026-08-02: a RESEARCH escalation — «termina la búsqueda ampliada del
# operador (proyecto compra y venta de motos): completa el informe…» — tripped the confirm-gate and left the
# task parked awaiting an OK nobody understood the reason for). Neither of them loosens the gate on a real
# order:
#  (1) what sits between PARENTHESES is CONTEXT, not the order — the action lives in the main text;
#  (2) a term that here is a NOUN and not a verb («compra y venta», «compraventa») names a topic, it does not
#      order anyone to buy.
#
# And a third, the same shape one level up: inside a LOOKUP («investiga…», «busca…», «compárame…») the phrases
# that name buying are ADJUNCTS describing what is being looked for — «qué comprar», «for sale», «to buy» —
# and not an order to buy anything.
#
# It is gated on the lookup HEAD, anchored at the start, on purpose and not applied everywhere: dropping «to
# buy» from any sentence would also disarm «ve a la tienda para comprar leche», which IS an order. The head
# is what makes the difference between a request to FIND OUT and a request to ACT, and it is the operator's
# own first word — which is why a composed worker request, that starts with «El operador…», is deliberately
# outside this drop and handled by `_AMOUNT_QUESTION_RE` instead.
_LOOKUP_HEAD_RE = re.compile(
    r"^\W*(?:me\s+)?(?:puedes\s+|podrias\s+|quiero\s+que\s+)?"
    r"(?:investiga\w*|busca\w*|compara\w*|mira\w*|encuentra\w*|localiza\w*|recomienda\w*|"
    r"research\w*|find\w*|search\w*|compare\w*|look\w*|investigate\w*|recommend\w*)\b", re.I)

# The adjunct forms themselves. Closed list, never a stem: this is subtracted BEFORE the danger verbs are
# looked for, so anything too wide here silently disarms the gate.
_PURCHASE_ADJUNCT_RE = re.compile(
    r"\b(?:para\s+comprar\w*|a\s+la\s+venta|en\s+venta|de\s+compra|que\s+comprar\w*|"
    # «cuál comprar» / «which one to buy» is the QUESTION a comparison answers, and it is the phrase a
    # research errand is most likely to carry — it names the decision the operator has NOT taken yet.
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
    """Inside a LOOKUP, a phrase that names buying describes what is being looked for. Gated on the head, so
    «ve a la tienda para comprar leche» keeps its order."""
    return _PURCHASE_ADJUNCT_RE.sub(" ", order) if _LOOKUP_HEAD_RE.search(order) else order


def _order_text(text: str) -> str:
    """The text irreversibility is judged on: the ORDER, with no parenthesised context and no compound nouns
    that merely name a topic."""
    t = (text or "").lower()
    for _ in range(3):                      # nested parentheses: collapse from the inside out
        t2 = _PAREN_RE.sub(" ", t)
        if t2 == t:
            break
        t = t2
    return _NOUN_COMPOUND_RE.sub(" ", t)


def is_dangerous(text: str) -> bool:
    """True when the request describes an irreversible action that needs the operator's explicit OK first.

    THE GATE READS THE ORDER, NOT THE WORDS (V2-509). Everything before the search is a SUBTRACTION: each
    `_drop_*` removes a clause that TALKS ABOUT an act instead of ordering one, and only then are the verbs
    looked for. That is the technique this module converged on after paying for the alternative four times —
    a gate widened by a new pattern parks an errand that did not need parking, and a parked errand is a
    task that never runs.
    """
    # The reminder clip applies to BOTH patterns (V2-128). It used to be seen only by `_COMMITMENT_RE`, so
    # «recuérdame PAGAR la factura antes del día 5» tripped the gate through `_DANGER_RE`: a request for a
    # REMINDER left waiting for an OK for a payment nobody was going to execute. The order there is
    # «recuérdame», and that moves no money — the same boundary the `pay-known-bill` case draws the other
    # way round (an ORDER to pay is not a request for a reminder).
    # Accents come off ONCE and before everything else: `_REMINDER_RE` is written without them
    # («recuerdame») and `_order_text` only lowercases, so the REAL imperative — «recuérdame», with its
    # accent — did not match and the note slipped through as an order. Same oversight that already cost
    # «resérvame» in site_catalog and «renuévame» in this very file: the form the operator SAYS is exactly
    # the one an unnormalised pattern cannot see.
    order = _drop_past_acts(
        _drop_amount_questions(_drop_lookup_adjuncts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))))
    return bool(_DANGER_RE.search(order) or _DANGER_CLITIC_RE.search(order)
                or _DANGER_ASK_CLITIC_RE.search(order) or _DANGER_PROCLITIC_RE.search(order)
                or _COMMITMENT_RE.search(order) or _DESTROY_OBJECT_RE.search(order)
                # TWO FUNCTIONS OF THIS MODULE USED TO DISAGREE ABOUT THE SAME SENTENCE, and the one that
                # decides whether the task STOPS was the one saying no (V2-710 T0.4). Measured 2026-09-16:
                # `moves_money("transfiere 500 euros a la cuenta de Iván")` was True and `is_dangerous` was
                # False, so `dispatch._run_session` started the worker without asking. The cause is that
                # `_DANGER_RE` is a list of verbs and «transferir» was not on it — which is the standing
                # argument for NOT growing that list (every verb added parks one more errand that did not
                # need parking). This is composition instead: whatever counts as spending UNCONDITIONALLY
                # counts as irreversible, and the two answers can no longer contradict each other.
                # ⚠️ Only the unconditional half — see `_SPEND_VERB_RE`: the first version composed every
                # money verb and parked «renueva el gráfico del widget».
                or _SPEND_VERB_RE.search(order))


def _strip_accents(text: str) -> str:
    """`_COMMITMENT_RE` is written without accents (membresia, poliza, domiciliacion) so each variant does not
    have to be duplicated: the operator says «membresía» and the pattern has to match all the same.
    `_DANGER_RE` does not need it — its terms carry no accent — and is left as it was so a refactor does not
    change its behaviour."""
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c))


# Does this order MOVE MONEY, or is it merely irreversible? Both stop at the gate, but they are not asked
# the same way (V2-129, measured). The `renew-gym-membership` case ended with the tester himself stopping
# the execution — «hold on, you haven't told me how much you're going to pay and you haven't asked me to
# confirm. Don't make the charge until you give me the amount and I confirm it.» — and he was right twice:
# there was no amount, and there could not be one, because nobody had looked at the fee yet. A generic
# question («this may be irreversible, do you confirm?») does not say the one thing the operator needs to
# hear before authorising a charge: that NOTHING is paid without him seeing the figure first. So it is said,
# and the promise exists even while the amount does not.
#
# SPENDING AS AN ACT vs SPENDING AS A SUBJECT (V2-710 T0.4). The two halves used to be one regex, and
# `moves_money` is right to fire on both: it answers «is this about money?», which is what
# `router_guards.money_work_needs_a_browser` needs in order to hand the task a browser — a bill LOOKUP
# belongs in the browser too. `is_dangerous` asks a different question — «does this END something» — and
# only the first half can answer it. Measured 2026-09-16 before splitting them: composing the two whole
# functions would have parked «cuánto es la factura de la luz» and «mira mi factura», which are lookups.
_MONEY_ACT_RE = re.compile(
    r"\b(?:pagar|paga|pague|pagas|comprar|compra|compre|abonar|abona|transferir|transfiere|"
    r"recargar|recarga|renovar|renueva|renuev\w*|contratar|contrata|suscrib\w*|"
    r"pay|buy|purchase|checkout|charge|renew|subscribe|top\s*up)\b", re.I)

# ⚠️ AND ONLY PART OF THAT COMPOSES INTO THE GATE THAT PARKS. Measured while shipping T0.4, and it is the
# third width this one fix had to be narrowed to: half the verbs above only mean money NEXT TO a commitment
# object — «renovar», «contratar», «suscribir» — which is precisely why `_COMMITMENT_RE` demands VERB +
# OBJECT and says so in its own note. Composing them here parked «renueva el gráfico del widget», an order
# to REFRESH A CHART, and the case that caught it is the one this module already carries for that exact
# sentence. What is left is the verbs that mean spending UNCONDITIONALLY and that `_DANGER_RE` does not
# already hold — «transferir», «abonar», «recargar», «charge», «top up» — which is the whole measured delta
# that made the two functions disagree («transfiere 500 euros a la cuenta de Iván»). A gate is widened by
# the sentence that was measured, never by the pattern that happens to contain it.
_SPEND_VERB_RE = re.compile(
    r"\b(?:abonar|abona|abonale|transferir|transfiere|transfiereme|recargar|recarga|"
    r"charge|top\s*up|wire|send\s+money)\b", re.I)
_MONEY_THING_RE = re.compile(
    r"\b(?:cuota|factura|recibo|cargo|importe|mensualidad|abono|bill|invoice|fee)\b", re.I)
_MONEY_RE = re.compile(_MONEY_ACT_RE.pattern + r"|" + _MONEY_THING_RE.pattern, re.I)


# The enclitic-form verbs that also MOVE MONEY (deleting or publishing costs nothing).
_MONEY_VERB_RE = re.compile(r"\b(?:pagar|comprar|abonar|transferir|adquirir|contratar|renovar|"
                            r"pagas|compras|abonas|transfieres|contratas|renuevas)", re.I)


def ends_a_commitment(text: str) -> bool:
    """Does this order END or START a standing commitment — a subscription, a fee, a contract, an order?

    Exposed for V2-138: `is_dangerous` is too wide to decide whether something needs a WORKER (it is also
    True for «borra el widget de música», which is resolved inside the turn, V2-017), and `moves_money` is
    too narrow (cancelling costs nothing). This middle predicate is exactly the right width, and it was
    already being computed inside `is_dangerous` — measured on both classes:

        cancela mi suscripción a Netflix · dame de baja de Movistar · anula el pedido de Amazon   → True
        borra el widget de música · cancela la búsqueda · borra la tarea del jueves               → False

    Uses the same reminder clipping as the rest of the module, so «recuérdame dar de baja Netflix» stays a
    note."""
    return bool(_COMMITMENT_RE.search(
        _drop_past_acts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))))


def moves_money(text: str) -> bool:
    """True when the order implies a CHARGE — and also when the turn is merely ABOUT money.

    Deliberately WIDER than the act (V2-711 T0.4): `router_guards.money_work_needs_a_browser` reads this to
    decide whether a task deserves a browser, and looking up a bill deserves one. It is NOT the predicate
    that parks a task — `is_dangerous` is, and it composes only the ACT half of this one.
    """
    # Accents off BEFORE the note is clipped — the same order as `is_dangerous`, and for the same reason:
    # `_REMINDER_RE` is written without accents and «recuérdame» is the form that gets spoken.
    order = _drop_past_acts(
        _drop_amount_questions(_drop_lookup_adjuncts(_REMINDER_RE.sub(" ", _strip_accents(_order_text(text))))))
    if _MONEY_RE.search(order):
        return True
    # Same gap as in `is_dangerous` (V2-141): «¿puedes pagarLA?» carries no bare form of the verb. Without
    # this the gate did stop the order, but with the generic question rather than the money one — and the
    # only sentence an operator needs to hear before a charge is that nothing is paid without him seeing the
    # figure first.
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
