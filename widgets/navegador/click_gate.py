"""widgets/navegador/click_gate.py — the ONE gate in front of an irreversible click (V2-711 T1).

## What was measured (2026-09-16)

This is the last rail before the engine presses a button on a real website in the operator's name, and it
had three holes at once.

**One of four routes was gated.** `owner.py::agent_act` reached the mouse and the keyboard by four paths and
only `click` (by `[ref]`) consulted `_DANGER_RE`:

    click       (by ref)              → gated
    click_at    (vision, by pixels)   → NOT gated
    press       ("Enter")             → NOT gated
    type/type_at --submit             → NOT gated (`keyboard.press("Enter")` inside the typing helper)

…and `nucleo/nav_cli.py`, the CLI a Brain Worker drives the browser with, RECOMMENDS the ungated one in its
own usage text: «VISION flow (robust for forms)». The recommended path was the unguarded path.

**It judged the LABEL, in one language.** Run against 30 real button labels, 21 walked through: «Reservar»,
«Confirmar reserva», «Firmar», «Send money», «Donate», «Donar», «Transferir», «Suscribirse», «Contratar»,
«Aceptar y continuar», «Book now», «Confirm booking», «Submit order», «Añadir al carrito», «Solicitar»…
The first example in this repo's own ⭐ operating rule is *«reservar un hotel o un restaurante»* — the
flagship case of the product was precisely the one the last gate did not cover.

**And it failed OPEN.** `owner.py`: if `_describe_el` raised, `_name = ""` and the click went ahead.

## What this module does instead

Gating a ROTULO cannot work: the set of words is the world's, in every language, and each one added is a
word the next site spells differently. So the label stays (it is right 9 times out of 30 and costs nothing)
and the CONTEXT of the element is added, which is ours to read and is language-independent:

  · a submit-ish control inside a `<form>` that carries PAYMENT or IDENTITY fields — a card number, a CVV,
    an IBAN, a password, a national id, a phone, an email, a postal address;
  · a target whose URL, or whose page's URL, is a checkout/booking/order path.

**It fails CLOSED**: signals that cannot be read at all mean ASK. That is the direction
`show_request_blocks_data_action` already chose in this codebase with the argument that settles it — a show
that does nothing is a smaller failure than a mutation nobody asked for — and here the mutation is on
somebody's real account.

`decide()` is a PURE function over a signal dict, deliberately: the page work is one `evaluate` and every
rule can then be measured without a browser. `shadow_reason()` is the third layer riding along without
arming — a form that would POST a document navigation is the signal that gates the CONSEQUENCE instead of
the appearance, and it earns its way in on the operator's own sessions before it can stop anything.
"""
from __future__ import annotations

import re

#: The paths a purchase, a booking or an order lives at. Matched on the TARGET url and on the page's own,
#: because a confirm button often posts back to the same address it is displayed at.
_CHECKOUT_URL_RE = re.compile(
    r"(?:^|[/.?&=_-])(?:checkout|payment|payments|pay|billing|order|orders|purchase|cart|basket|"
    r"booking|bookings|reserva|reservas|reservation|reservations|pedido|pedidos|compra|pago|pagos|"
    r"suscripcion|subscribe|subscription|donate|donacion|transfer|transferencia)(?:$|[/.?&=_-])", re.I)

#: A field whose presence means the form is about MONEY. `autocomplete` is the reliable half (the spec's own
#: token list), `name`/`id` the pragmatic one for sites that never filled it in.
_PAYMENT_FIELD_RE = re.compile(
    r"\b(?:cc-number|cc-exp|cc-csc|cc-name|cc-type|cc-exp-month|cc-exp-year)\b"
    r"|(?:card[_-]?number|cardnumber|creditcard|numero[_-]?tarjeta|tarjeta|iban|swift|bic|cvv|cvc|"
    r"security[_-]?code|codigo[_-]?seguridad|account[_-]?number|routing)", re.I)

#: A field whose presence means the form is about WHO YOU ARE. A booking form asks for these and no card.
_IDENTITY_FIELD_RE = re.compile(
    r"\b(?:email|tel|name|given-name|family-name|street-address|postal-code|address-line1|"
    r"address-line2|country|bday|sex)\b"
    r"|(?:\bdni\b|\bnif\b|\bnie\b|passport|pasaporte|id[_-]?number|documento|telefono|phone|mobile|movil|"
    r"correo|e-?mail|direccion|codigo[_-]?postal|zip)", re.I)

#: Read by the page. Returns the ONE dict `decide()` judges; never throws — an unreadable branch answers
#: null for its own field and the decision treats a null as «could not read», which asks.
JS_SIGNALS = r"""
(el) => {
  const out = {name: "", role: "", isSubmit: false, inForm: false, payment: false, identity: false,
               method: "", targetUrl: "", pageUrl: "", fields: 0};
  try { out.pageUrl = location.href || ""; } catch (e) {}
  if (!el || !el.tagName) return out;
  try {
    const tag = (el.tagName || "").toLowerCase();
    const type = ((el.getAttribute && el.getAttribute("type")) || "").toLowerCase();
    out.role = (el.getAttribute && el.getAttribute("role")) || tag;
    out.name = ((el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("title"))) ||
                el.value || el.innerText || el.textContent || "").trim().slice(0, 120);
    // A <button> with no type inside a form IS a submit button — the default the HTML spec sets, and the
    // shape most checkout pages actually use.
    out.isSubmit = (tag === "button" && (type === "submit" || type === "")) ||
                   (tag === "input" && (type === "submit" || type === "image"));
    const form = el.closest ? el.closest("form") : null;
    out.inForm = !!form;
    if (form) {
      out.method = (form.getAttribute("method") || "get").toLowerCase();
      out.targetUrl = form.getAttribute("action") || out.pageUrl;
      const fields = form.querySelectorAll("input, select, textarea");
      out.fields = fields.length;
      for (const f of fields) {
        const sig = [f.getAttribute("autocomplete"), f.getAttribute("name"), f.getAttribute("id"),
                     f.getAttribute("type"), f.getAttribute("placeholder")].filter(Boolean).join(" ");
        if ((f.getAttribute("type") || "").toLowerCase() === "password") out.payment = true;
        out.__sig = (out.__sig || "") + " " + sig;
      }
      out.signals = (out.__sig || "").slice(0, 4000);
      delete out.__sig;
    }
    if (!out.targetUrl) out.targetUrl = (el.getAttribute && el.getAttribute("href")) || "";
  } catch (e) {}
  return out;
}
"""

#: What the caller passes when the page could not be asked at all.
UNREADABLE = None


def _text(sig: dict, *keys: str) -> str:
    return " ".join(str(sig.get(k) or "") for k in keys)


def label_is_irreversible(name: str) -> bool:
    """The original rule, kept: it is right on 9 of 30 measured labels and costs nothing to keep asking."""
    from .dom import _DANGER_RE
    return bool(_DANGER_RE.search((name or "").lower()))


def decide(sig: dict | None) -> tuple[bool, str]:
    """(ask the operator?, why). `None` means the page could not be read — which ASKS, by design.

    Order matters only for the REASON reported, never for the answer: any one signal is enough.
    """
    if not isinstance(sig, dict):
        return True, "no se pudo leer el elemento"
    name = str(sig.get("name") or "")
    if label_is_irreversible(name):
        return True, f"el botón dice «{name[:40]}»"

    haystack = _text(sig, "signals")
    in_form = bool(sig.get("inForm"))
    submitish = bool(sig.get("isSubmit")) or in_form
    if submitish and sig.get("payment") is True:
        return True, "el formulario pide una contraseña o datos de pago"
    if submitish and _PAYMENT_FIELD_RE.search(haystack):
        return True, "el formulario pide datos de pago (tarjeta, IBAN, CVV)"
    # ⚠️ V2-712 — THE IDENTITY RULE NO LONGER ASKS FOR CONSENT, and the operator is right that it should not.
    # «Si te digo que reserves mesa en un restaurante, tú ya tienes que saber quién soy yo, cuál es mi
    # teléfono, cuál es mi email. Y si no lo sabes, obviamente preguntas. Pero una vez ya lo sepas y lo tengas
    # en el estado, no hace falta que preguntes otra vez.» A booking form asking for a name, a phone and an
    # email is the NORMAL shape of the order he just gave, so stopping on it was a rail on JUDGEMENT wearing
    # a safety hat — `principles.md` says to delete it and find the mechanism it stood in for.
    #
    # The mechanism it stood in for is `needs_facts()` below: the honest question is not «shall I proceed»
    # but «what is your phone», and it is only worth asking when the engine does not already have it.
    urls = _text(sig, "targetUrl", "pageUrl")
    if submitish and _CHECKOUT_URL_RE.search(urls):
        return True, "el destino es una página de compra, pedido o reserva"
    return False, ""


def needs_facts(sig: dict | None) -> list[str]:
    """Which of HIS OWN facts this form asks for and the engine does not have (V2-712).

    This is what the identity rule became. A form that wants an email and a phone is not a reason to ask
    permission — it is a reason to check we can fill it. When a datum is missing the caller asks for THAT
    datum, which is help; when every datum is on file the form is filled and the task keeps going, which is
    the whole complaint («no hace falta que preguntes otra vez»).

    Empty when the page could not be read: `decide()` already stops on that, and asking for a phone number
    over an unreadable form would be a question about nothing.
    """
    if not isinstance(sig, dict):
        return []
    haystack = _text(sig, "signals")
    if not (bool(sig.get("isSubmit")) or bool(sig.get("inForm"))):
        return []
    if not _IDENTITY_FIELD_RE.search(haystack):
        return []
    from nucleo import consent as _consent
    wants = ["operator.name", "operator.email", "operator.phone"]
    if re.search(r"\b(?:street-address|postal-code|address-line1|direccion|codigo[_-]?postal|zip)\b",
                 haystack, re.I):
        wants.append("operator.address")
    return _consent.missing_facts(wants)


def shadow_reason(sig: dict | None) -> str:
    """The THIRD layer, riding along without arming (V2-711 T1.3).

    A submit that causes a document navigation with method POST is a signal about the CONSEQUENCE rather
    than about the appearance, which is the only kind that generalises to a site nobody has seen. It is
    reported and counted first, on the operator's real sessions, and armed only once those verdicts show it
    costs no false stop — the same gate V2-653's arbiter is waiting behind. Empty when `decide` already
    asked: a second reason for a click that is already stopping measures nothing.
    """
    if not isinstance(sig, dict):
        return ""
    ask, _why = decide(sig)
    if ask:
        return ""
    if bool(sig.get("inForm")) and str(sig.get("method") or "").lower() == "post":
        return "un formulario que envía por POST"
    return ""


def _say_missing(missing: list[str]) -> str:
    """The sentence the operator hears when a form needs something about him we do not have. It names the
    DATUM, because that is the only thing he can usefully answer — and once he answers it, the fact lands in
    memory and no form of this shape ever asks again."""
    names = {"operator.name": "tu nombre", "operator.email": "tu email", "operator.phone": "tu teléfono",
             "operator.address": "tu dirección"}
    return "Para rellenar este formulario me falta " + ", ".join(names.get(m, m) for m in missing)


async def may_act(page, handle, at=None, *, confirm=None, task_id: str = "") -> tuple[bool, str]:
    """Resolve the element this action is about, judge it, and ask the operator when it must be asked.

    Lives HERE and not in `owner.py` because `owner.py` is a listed god file and the architecture ratchet
    is paid by EXTRACTING, never by raising a ceiling — and because the whole decision, including how the
    element is found, belongs to the gate rather than to the dispatch that calls it four times.

    `handle` is the element when we have one (`click`, `type --submit`); `at` its pixel for the vision
    route; NEITHER means «whatever has focus», which is what Enter acts on. `confirm` is the operator-facing
    ask, injected so this function needs no browser and no voice to be measured.
    """
    sig = None
    try:
        if handle is not None:
            sig = await handle.evaluate(JS_SIGNALS)
        elif at is not None:
            sig = await page.evaluate(
                "([x, y]) => { const el = document.elementFromPoint(x, y); return el ? ("
                + JS_SIGNALS + ")(el) : null; }", [at[0], at[1]])
        else:
            sig = await page.evaluate("() => { const el = document.activeElement; return el ? ("
                                      + JS_SIGNALS + ")(el) : null; }")
    except Exception:  # noqa: BLE001 — an unreadable page is exactly the case that must ASK
        sig = None
    ask, why = decide(sig)
    if not ask:
        # V2-712 — the only thing left to check before a form the operator ordered: can we FILL it. A missing
        # datum stops the click and asks for the datum by name; nothing missing means it goes through, which
        # is the difference between an agent that helps and one that keeps checking whether it may help.
        missing = needs_facts(sig)
        if missing and confirm is not None:
            await confirm(_say_missing(missing))
            return False, f"faltan datos del operador: {', '.join(missing)}"
        shadow = shadow_reason(sig)
        if shadow:
            try:
                from voice.observer import emit as _emit
                _emit("widget", "gate_shadow", text=shadow,
                      extra={"id": "navegador", "task": str(task_id), "rule": "post-form",
                             "url": str((sig or {}).get("pageUrl") or "")[:160]})
            except Exception:  # noqa: BLE001
                pass
        return True, ""
    label = str((sig or {}).get("name") or "").strip() or "esta acción"
    if confirm is not None and await confirm(f"{label} — {why}" if why else label):
        return True, ""
    return False, f"acción «{label[:40]}» NO confirmada por el operador ({why})"
