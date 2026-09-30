"""nucleo/flash/act_repair.py — the model PROMISED to act on a card and called nothing: ask it once more, for the call.

Measured on the operator's engine (V2-764, 2026-09-24), with a clean window per phrase: «Busca en torrent la serie
Sherlock» → *«Voy a por la serie Sherlock en torrent y te enseño el catálogo en cuanto lo tenga»* and NO tool;
«Hazme una lista de torrents de documentales de la NASA» → the same. The card was known (the turn's own verdict
names it — `build_decision.named_card`), the action existed (`archivos:torrent_search`, declared), and the model
even SAID which one it meant. What it did not produce was the call.

Sibling of `second_pass.promise_repair` (V2-717), which covers a promise to LOOK by reading the widget. This one
covers a promise to DO: one small non-streamed pass with the model that just failed, offered ONE tool
(`widget_data`) and the named card's own declared actions, told what it said. It extracts the payload itself — a
search query is free text no enumeration can fill, which is why the verdict alone (`direct_action.complete`) cannot
close this. The call it returns goes through the caller's `apply_widget_data`, the same `action_mode_now` gate
every model call goes through: nothing new is allowed to run, a declared action stops going unrun.

Bounded on purpose: only when the turn called NOTHING and promised; only a card the verdict names; only an action
that card declares; a model that still calls nothing leaves the turn exactly as it was. It costs one model call on
the turns that fail, and zero on every other turn.
"""
from __future__ import annotations

import json
import re

#: What the repair tells the model. Short on purpose: the ask is «make the call you promised», not a new turn.
_SYS = ("Eres el cerebro de un asistente de voz. En el turno anterior contestaste SIN llamar a ninguna herramienta. "
        "Lee lo que dijiste: si PROMETISTE hacer algo sobre la tarjeta «{wid}» o AFIRMASTE haberlo hecho (un "
        "borrador listo, una cita movida, algo abierto o cambiado), haz AHORA exactamente la llamada `widget_data` "
        "que lo cumple, con widget_id «{wid}», una de estas acciones declaradas y el payload sacado de las palabras "
        "del operador y de lo que hay en la tarjeta (una hora relativa —«media hora más tarde»— se calcula sobre la "
        "cita que hay). Si solo CONTESTASTE, PROPUSISTE o PREGUNTASTE — sin prometer ni afirmar un acto —, o si "
        "ninguna acción encaja, no llames a nada. OFRECER hacerlo («¿quieres que lo reserve?», «want me to put it "
        "there?») NO es hacerlo: espera su sí. Pero si AFIRMASTE un acto y además ofreces OTRO («movida a las 2:45; "
        "¿aviso a Rowan?»), haz la llamada del que afirmaste.\n\n"
        "Acciones de «{wid}»:\n{actions}{card}")
#: What the card holds, so a relative order («move it 30 minutes later») can be turned into a call. The
#: demo run (2026-09-26): the model computed «It's now at 2:00 PM, running until 2:45» in the turn — it had the
#: digest — and this pass, which had only his words, could not, and returned nothing in silence.
_CARD = "\n\nLO QUE HAY EN LA TARJETA «{wid}» AHORA:\n{digest}"


def conversation(window, n: int = 6) -> str:
    """The last turns, as the model that spoke them saw them — so a repair pass knows what «the new time», «that
    one» or «it» is (demo pass 2026-09-28, C5: «send rowan a telegram with the new time» reached a pass that saw
    only his sentence and the messaging card; the time lived two turns back, on the agenda)."""
    try:
        rows = [m for m in (window or []) if (m or {}).get("role") in ("user", "assistant")][-n:]
        lines = [f"{'Operador' if m['role'] == 'user' else 'Tú'}: {str(m.get('content') or '').strip()[:300]}"
                 for m in rows if str(m.get("content") or "").strip()]
        return ("\n\nLA CONVERSACIÓN HASTA AHORA (lo último abajo):\n" + "\n".join(lines)) if lines else ""
    except Exception:  # noqa: BLE001
        return ""


def _note(wid: str, why: str, **extra) -> None:
    """The pass ran and gave NO call — said on the timeline, because a silent None here was a turn that
    claimed an act nobody could find (V2-773 audit)."""
    try:
        from voice.observer import emit
        emit("brain", "🔁 la segunda pasada no dio llamada", text=f"{wid}: {why}", role="system",
             extra={"cat": "flash", "widget": wid, "why": why, **extra})
    except Exception:  # noqa: BLE001
        pass


def _actions_block(manifest: dict) -> str:
    rows = []
    for name, spec in (manifest.get("actions") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        pay = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
        rows.append(f"- {name}: {str(spec.get('desc') or '')[:200]}"
                    + (f" · payload {json.dumps(pay, ensure_ascii=False)[:220]}" if pay else ""))
    return "\n".join(rows)


def _widget_data_tool() -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == "widget_data"), None)
    except Exception:  # noqa: BLE001
        return None


# The words that DENY an act — the one case the repaired act has to be said after (see `after_the_repair`).
# English and Spanish, the two languages the demo and the operator's sessions are measured in.
_DENIED_RE = re.compile(
    r"\b(?:can'?t|cannot|can not|couldn'?t|unable to|not something i can|no way (?:to|i can)|there(?:'s| is) no|"
    r"there(?:'s| is)n'?t (?:a|any)|isn'?t (?:a|any|something)|"
    r"no puedo|no es algo que pueda|no hay (?:forma|manera|ning[uú]n)|no tengo (?:forma|manera)|no existe)\b", re.I)


def denies_the_act(spoken: str) -> bool:
    """Do the model's words say the act cannot be done? Deterministic and narrow: a can't/there's-no shape."""
    return bool(_DENIED_RE.search(spoken or ""))


def after_the_repair(spoken: str, promised: bool, widget_id: str = "", action: str = "") -> str:
    """What the VOICE adds once the second pass has carried out an order the model's words DENIED.

    Demo pass 31 (2026-09-28, E4): «leave that inworld one as unread» — the model called nothing and said «there's
    no unread toggle for a mail message»; the verdict's second pass then marked it unread. The action was done and
    the last thing heard was that it could not be. The text channel drops the model's words and lets the result
    speak; the voice cannot unsay what already streamed, so it says what happened after it — the same rule as a
    worker stopped by the backstop («never a silent kill»). Nothing is added when the words already promised the
    act, or when nothing was said (the ordinary data ack covers that)."""
    # One rule (demo passes 55-56, 2026-09-29): the words already carry the act unless they DENIED it. «Right… I
    # left the Inworld one unread — it's back to showing as new.» and «Yep — putting Madonna on.» both got a
    # «Done.» stapled on, because the promise table is Spanish and neither is a refusal. A claim or a promise in
    # any language needs nothing after it; a denial does, and a question gets «went ahead» (below).
    if promised or not (spoken or "").strip():
        return ""
    if "?" not in (spoken or "") and not denies_the_act(spoken):
        return ""
    try:
        # …and a repaired LOOK changes nothing to acknowledge (demo pass 42, C2: «…want me to put it on your calendar
        # at 4?» + a repaired `find_free` → «…at 4?Done.»). Its answer, if one is owed, comes from the op's data.
        from nucleo.flash import data_ops as _dops
        if widget_id and action and _dops.is_view_op(widget_id, action):
            return ""
    except Exception:  # noqa: BLE001
        pass
    try:
        from i18n import langs as _langs   # the voice.engine.core shim is this same module
        L = _langs.current_language()
        if "?" in (spoken or "") and str(getattr(L, "data_ack_went_ahead", "") or "").strip():
            return " " + L.data_ack_went_ahead.strip()
        return " " + (L.data_ack or "").strip()
    except Exception:  # noqa: BLE001
        return ""


async def call_for_promise(operator_text: str, reply: str, widget_id: str, spec=None, *,
                           window=None) -> dict | None:
    """`{widget_id, action, payload}` — the call the model should have made — or None. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        if not wid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if not declared or not tool:
            return None
        got: list[tuple[str, dict]] = []
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001 — without the card the pass still runs on his words
            digest = ""
        card = _CARD.format(wid=wid, digest=digest) if digest else ""
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS.format(wid=wid, actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operador: «{operator_text.strip()[:400]}»\n"
                                         f"Tu respuesta (sin llamada): «{(reply or '').strip()[:300]}»"
                                         + conversation(window)}],
            spec=spec, max_tokens=300, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if name != "widget_data":
                continue
            if str(args.get("widget_id") or "").strip().lower() != wid:
                _note(wid, "la llamada nombra otra tarjeta", other=str(args.get("widget_id") or "")[:40])
                continue
            action = str(args.get("action") or "").strip()
            if action not in declared:
                _note(wid, "acción no declarada", action=action[:40])
                continue
            payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            return {"widget_id": wid, "action": action, "payload": payload}
        if not got:
            _note(wid, "el modelo no llamó a nada")
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None


_SYS_REPEAT = (
    "Eres el cerebro de un asistente de voz. El operador dio una orden y tu única llamada fue `{repeated}` sobre la "
    "tarjeta «{wid}» — solo MIRÓ (una vista o una consulta que ya estaba o que no cambia nada): no cumplió nada. La orden, leída por separado, es "
    "`{verdict}` sobre «{wid}». Si sus palabras piden eso, haz AHORA exactamente la llamada `widget_data` con "
    "widget_id «{wid}» y action «{verdict}», con el payload sacado de sus palabras, de la conversación y de lo que hay "
    "en la tarjeta (una nota que él dicta se redacta tú; a una persona se la nombra como él la dijo). Si sus palabras "
    "NO piden eso, no llames a nada.\n\nAcciones de «{wid}»:\n{actions}{card}")


_SYS_REFUSED = (
    "Eres el cerebro de un asistente de voz. El operador dio una orden y no llamaste a nada: contestaste «{said}». "
    "La orden, leída por separado, es `{verdict}` sobre la tarjeta «{wid}» — una acción que esa tarjeta SÍ tiene, "
    "declarada abajo. Si sus palabras piden eso, haz AHORA exactamente la llamada `widget_data` con widget_id «{wid}» "
    "y action «{verdict}», con el payload sacado de sus palabras, de la conversación y de lo que hay en la tarjeta "
    "(una nota que él dicta se redacta tú; a una persona se la nombra como él la dijo). Si sus palabras NO piden "
    "eso, no llames a nada.\n\nAcciones de «{wid}»:\n{actions}{card}")


async def call_for_promise_or_order(operator_text: str, reply: str, widget_id: str, verdict: str = "", spec=None, *,
                                    window=None) -> dict | None:
    """`call_for_promise`, and when the words promised nothing — they REFUSED — the verdict's call.

    Demo pass 41 (2026-09-29, E3): «send the invoice to quinn…» over the open receipt → «I can't send it myself —
    sending mail isn't something I can do on my end», no call, the verdict reading `mensajeria:forward`. The promise
    pass asks «did you promise an act?», and a refusal did not, so it rightly called nothing — and the mail never
    went. A refusal of an action the card DECLARES, for an order the verdict names, is one more question to the
    model, with the action named. Bounded like the others: one card, its declared action, the caller's gate."""
    got = await call_for_promise(operator_text, reply, widget_id, spec, window=window)
    if got or not verdict:
        return got
    said = " ".join(str(reply or "").split())[:300]
    return await call_for_repeated_view(operator_text, widget_id, "", verdict, spec, window=window,
                                        _sys=_SYS_REFUSED.replace("{said}", said.replace("{", "(").replace("}", ")")))


async def call_for_repeated_view(operator_text: str, widget_id: str, repeated: str, verdict: str, spec=None, *,
                                 window=None, _sys: str = "") -> dict | None:
    """The model's only call RE-OPENED what was already on screen, and the verdict names an action on that card
    that needs a payload only a model can write — ask once, for that call. `{widget_id, action, payload}` or None.

    Demo pass 2026-09-28 (full20 E3): «send the invoice to quinn, tell him we're already trying inworld and he
    should book it» over the open Inworld invoice → the model called `open` (again), the verdict read
    `mensajeria:forward` at 0.61. The verdict alone cannot complete a forward — the note to Quinn has to be
    written — so the turn ended having done nothing. Bounded like `call_for_promise`: one card, its declared
    action, the caller's usual gate. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        verdict = str(verdict or "").strip()
        if not wid or not verdict or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if verdict not in declared or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = _CARD.format(wid=wid, digest=digest) if digest else ""
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": (_sys or _SYS_REPEAT).format(wid=wid, repeated=repeated, verdict=verdict,
                                                                     actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operador: «{operator_text.strip()[:400]}»" + conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if (name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid
                    and str(args.get("action") or "").strip() == verdict):
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": verdict, "payload": payload}
        _note(wid, "el modelo no hizo la llamada del veredicto", action=verdict)
        return None
    except Exception:  # noqa: BLE001
        return None


_SYS_AFTER_READ = (
    "Eres el cerebro de un asistente de voz. El operador dio una ORDEN sobre la tarjeta «{wid}». Para cumplirla leíste "
    "antes la tarjeta «{read}» — esto es lo que guarda:\n{block}\n\nAhora cumple la orden: haz la llamada "
    "`widget_data` con widget_id «{wid}», una de sus acciones declaradas y el payload sacado de sus palabras y de lo "
    "que acabas de leer (un mensaje lo redactas tú; a una persona se la nombra como él la dijo). Si su frase no pide "
    "hacer nada en «{wid}», no llames a nada.\n\nAcciones de «{wid}»:\n{actions}{card}")


async def call_after_read(operator_text: str, read_widget: str, widget_id: str, spec=None, *,
                          window=None) -> dict | None:
    """The turn READ one card to get what an order on ANOTHER card needed — and the read path ends the turn with
    words only. `{widget_id, action, payload}` for the order, or None. Never raises.

    Demo pass 2026-09-28 (full20 C5): «send rowan a telegram with the new time» — the model read the agenda for the
    new time (sensible), and the read's answer pass, which has no tools, said «I can't send a Telegram, I don't have
    any messaging tool available here». The order stood; this pass carries it out with what was read."""
    try:
        wid = str(widget_id or "").strip().lower()
        rid = str(read_widget or "").strip().lower()
        if not wid or not rid or wid == rid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if not declared or not tool:
            return None
        from nucleo.flash import widget_read as _wr
        block = str(_wr.read(rid) or "").strip()[:1500] or "(vacía)"
        digest = str(_wr.read(wid) or "").strip()[:800]
        card = _CARD.format(wid=wid, digest=digest) if digest else ""
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_AFTER_READ.format(wid=wid, read=rid, block=block,
                                                                  actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operador: «{operator_text.strip()[:400]}»" + conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            action = str(args.get("action") or "").strip()
            if name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid and action in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": action, "payload": payload}
        _note(wid, "tras leer, el modelo no hizo la llamada de la orden", read=rid)
        return None
    except Exception:  # noqa: BLE001
        return None


_SYS_COMMISSION = (
    "Eres el cerebro de un asistente de voz. El operador ha dado una ORDEN que nombra la tarjeta «{wid}», y el "
    "turno iba a mandarla a un proceso de fondo de VARIOS MINUTOS. Antes de gastarlos, decide con lo que hay en la "
    "tarjeta: (1) si una acción declarada de «{wid}» cumple la orden, llama a `widget_data` con ella; (2) si la "
    "RESPUESTA está en lo que la tarjeta guarda (sus citas y huecos libres, sus contactos, sus ficheros…), llama a "
    "`read_widget` con widget_id «{wid}» y la pregunta concreta que hay que resolver contra ella (con la fecha "
    "absoluta y la franja que él dijo) — solo si esa herramienta se te ofrece; (3) solo si hace falta el mundo "
    "exterior —la web, reservar en un sitio externo, buscar productos— no llames a nada. Un mensaje a un contacto "
    "es la acción de enviar de la tarjeta, con el texto redactado por ti a partir de lo que él quiere decir, y "
    "`contact` es el NOMBRE de la persona tal como él lo dijo («Rowan»), nunca su @usuario, teléfono o correo: "
    "la tarjeta lo resuelve en su directorio. Una orden de HACER algo (enviar, escribir, apuntar, mover) se cumple "
    "con su acción aunque dependa de un dato que la tarjeta guarda: la tarjeta lo comprueba al ejecutar y dice si "
    "falta — leer para comprobarlo antes no cumple la orden. Pero ENCONTRAR, buscar o decirle algo (un hueco libre, "
    "una fecha, un dato) es SABERLO: se lee, y no se apunta ni se envía nada que él no haya pedido — «búscame un "
    "hueco para hablar con Rowan» no es reservar ni escribirle a Rowan. El ENCARGO lo redactó otro paso y puede "
    "traer un dato mal copiado: una hora, una fecha o un nombre que una tarjeta de su pantalla guarda se toma de la "
    "TARJETA, no del encargo."
    "\n\nAcciones de «{wid}»:\n{actions}{card}")


def _tool_named(name: str) -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None


def _other_open_cards(wid: str, *, limit: int = 2, chars: int = 900) -> str:
    """What the OTHER cards on his screen hold — the facts a commission on this card usually refers to.

    Demo pass 43 (2026-09-29), C5: «send rowan a telegram with the new time» — the meeting had just been moved to
    4:30 on the open agenda (silently: no words in the window said so), the model's escalation said «17:00», and
    this pass, which saw only the messaging card and that brief, wrote Rowan «moved to 5:00 PM». The time was on
    the screen, in another card."""
    try:
        from memory import api as _memapi
        from nucleo.flash import widget_read as _wr
        ids = [str(x).split("::")[0].lower() for x in ((_memapi.state() or {}).get("open_widgets") or [])]
        out = []
        for other in dict.fromkeys(i for i in ids if i and i != wid):
            if len(out) >= limit:
                break
            if not _wr.can_answer(other):
                continue
            digest = str(_wr.read(other) or "").strip()[:chars]
            if digest:
                out.append(f"\n\nLO QUE HAY EN «{other}», TAMBIÉN EN SU PANTALLA (la fuente de un dato que la orden "
                           f"nombra — una hora, una fecha —, por encima de lo que diga el encargo). Es el estado de "
                           f"AHORA, con los cambios que él ya pidió en la conversación YA APLICADOS: una hora de aquí "
                           f"es la final, no se le vuelve a sumar ni restar nada:\n{digest}")
        return "".join(out)
    except Exception:  # noqa: BLE001
        return ""


async def call_or_read_for_commission(operator_text: str, commission: str, widget_id: str, spec=None, *,
                                      window=None, may_read: bool = True) -> dict | None:
    """A commission that names one of our cards, before it costs a worker (V2-773 final pass, C1): «Find me a
    free 45-minute slot tomorrow afternoon» was delegated to a Brain Worker (three minutes) when the agenda was
    the whole answer. One pass with the card in front decides: `{"kind": "call", widget_id, action, payload}`,
    `{"kind": "read", widget_id, question}`, or None — and None keeps today's path, the worker. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        if not wid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        # The read option only for a card that can ANSWER (`widget_read.can_answer`): a messaging card gets the
        # call («message Rowan on Telegram» → send_to) and never a read it cannot serve.
        from nucleo.flash import widget_read as _wr0
        tools = [t for t in (_tool_named("widget_data"),
                             _tool_named("read_widget") if (may_read and _wr0.can_answer(wid)) else None) if t]
        if not manifest or not tools:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _other_open_cards(wid)
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_COMMISSION.format(wid=wid, actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operador: «{operator_text.strip()[:400]}»\n"
                                         f"El encargo que iba a un worker: «{(commission or '').strip()[:300]}»"
                                         + conversation(window)}],
            spec=spec, max_tokens=300, tools=tools, no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        declared = manifest.get("actions") or {}
        for name, args in got:
            if str(args.get("widget_id") or "").strip().lower() != wid:
                continue
            if name == "read_widget":
                q = str(args.get("question") or "").strip() or operator_text.strip()
                return {"kind": "read", "widget_id": wid, "question": q[:300]}
            if name == "widget_data" and str(args.get("action") or "").strip() in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"kind": "call", "widget_id": wid, "action": str(args["action"]).strip(), "payload": payload}
        _note(wid, "el encargo sigue su camino al worker" if not got else "la llamada no era de esta tarjeta")
        return None
    except Exception:  # noqa: BLE001 — never take down a live turn
        return None


_SYS_REFUSAL = (
    "Eres el cerebro de un asistente de voz. Para cumplir lo que dijo el operador llamaste a `widget_data` con la "
    "acción «{action}» sobre la tarjeta «{wid}» y el payload {payload}, y la tarjeta la RECHAZÓ: «{why}». Corrige "
    "esa llamada: la MISMA acción sobre la MISMA tarjeta, con el dato que falta o que no encajaba sacado de sus "
    "palabras y de lo que hay en la tarjeta. Una referencia por cualidad («la mejor oferta», «el más barato», «la "
    "de mañana») se resuelve LEYENDO la tarjeta y pasando el título o el número de ese elemento; una hora relativa "
    "se calcula sobre lo que hay. Si con eso no se puede saber, no llames a nada."
    "\n\nAcciones de «{wid}»:\n{actions}{card}")


def _same_card(asked: str, wid: str) -> bool:
    a, w = (asked or "").strip().lower(), (wid or "").strip().lower()
    return bool(a) and (a == w or a.split("::")[0] == w.split("::")[0])


async def call_for_refusal(operator_text: str, widget_id: str, action: str, payload: dict, why: str,
                           spec=None, *, said: str = "") -> dict | None:
    """The corrected payload for a call the card REFUSED, or None. Never raises.

    Demo pass 2026-09-28: «open the one that's the best deal» reached `results:detail` with nothing the sheet
    could match (its badge says «Best value»), and «move it half an hour later» reached `move_meeting` with field
    names it did not read. Both refusals were true and both went to a note for the NEXT turn, so the operator got
    silence and then, one order later, an apology stapled to an unrelated answer. The refusal is exactly what the
    model needs to get it right, and it arrives while the turn is still his: one small pass, with the reason and
    the card in front, allowed to re-issue ONLY the same action on the same card — so it passes the same gate the
    refused call already passed, and it can change what the call says, never what it does."""
    try:
        wid = str(widget_id or "").strip().lower()
        action = str(action or "").strip()
        if not wid or not action or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid.split("::")[0]) or _rt.get(wid) or {}
        tool = _widget_data_tool()
        if action not in (manifest.get("actions") or {}) or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = _CARD.format(wid=wid, digest=digest) if digest else ""
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_REFUSAL.format(
                wid=wid, action=action, payload=json.dumps(payload or {}, ensure_ascii=False)[:300],
                why=str(why or "")[:300], actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operador: «{operator_text.strip()[:400]}»"
                                         + (f"\nLo que le acabas de decir: «{said.strip()[:300]}» — si ahí nombraste "
                                            f"cuál, la corrección es ESE." if (said or "").strip() else "")}],
            spec=spec, max_tokens=300, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if name != "widget_data" or not _same_card(str(args.get("widget_id") or ""), wid):
                continue
            if str(args.get("action") or "").strip() != action:
                _note(wid, "la corrección cambiaba de acción", action=str(args.get("action") or "")[:40])
                continue
            fixed = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            if fixed and fixed != (payload or {}):
                return {"widget_id": wid, "action": action, "payload": fixed}
        _note(wid, "el rechazo no tiene corrección", action=action)
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None


async def probe_call_for_promise(operator_text: str, reply: str, spec=None, *, wait_s: float = 3.0) -> dict | None:
    """The text channel's mirror: it has no brief in flight, so it fires one and waits for it (bounded) —
    only on the turn that already promised and called nothing. Same verdict, same repair, never raises."""
    try:
        import asyncio
        from nucleo import jev as _jev
        from nucleo.flash import build_decision as _bd, turn_brief as _tb
        handle = _tb.ask_for_turn(operator_text, last_reply="")
        if handle is None:
            return None
        waited = 0.0
        while not _jev._is_ready(handle) and waited < wait_s:
            await asyncio.sleep(0.05)
            waited += 0.05
        wid = _bd.named_card(handle)
        return await call_for_promise(operator_text, reply, wid, spec=spec) if wid else None
    except Exception:  # noqa: BLE001
        return None
