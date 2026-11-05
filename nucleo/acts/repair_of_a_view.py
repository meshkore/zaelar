"""The second pass when the model only VIEWED (re-opened what was on screen) or was about to COMMISSION a worker for
what the card the verdict names can do. Moved from `nucleo/flash/act_repair.py` (refactor2710-05 T-04). V2-851 F2
retired the promise repair that lived here (`call_for_promise_or_order` and the tails said after the words); these
two passes go with the second passes in F5."""
from __future__ import annotations

from nucleo.acts import card_pass as _cp


async def call_for_repeated_view(operator_text: str, widget_id: str, repeated: str, verdict: str, spec=None, *,
                                 window=None, _sys: str = "", brief=None) -> dict | None:
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
        if not wid or not verdict or not (operator_text or "").strip() or operator_text.lstrip().startswith("[SISTEMA]") or _cp.canvas_holds_the_turn(brief, operator_text, wid):
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _cp.widget_data_tool()
        if verdict not in declared or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_cp._CARD.format(wid=wid, digest=digest) if digest else "") + _cp.days()
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _cp.in_his_lang(_sys or _cp._SYS_REPEAT).format(wid=wid, repeated=repeated, verdict=verdict,
                                                                     actions=_cp.actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + _cp.conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if (name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid
                    and str(args.get("action") or "").strip() == verdict):
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": verdict, "payload": payload}
        _cp.note(wid, "el modelo no hizo la llamada del veredicto", action=verdict)
        return None
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
                out.append(f"\n\nWHAT «{other}» HOLDS, ALSO ON HIS SCREEN (the source of a fact the order names — a time, "
                           f"a date —, above what the commission says). It is the state NOW, with the changes he "
                           f"already asked for in the conversation ALREADY APPLIED: a time from here is the final "
                           f"one, nothing is added to or taken from it again:\n{digest}")
        return "".join(out)
    except Exception:  # noqa: BLE001
        return ""


def _ignored_the_verdict(got: list, wid: str, verdict_action: str, declared: dict) -> bool:
    """The pass called a DIFFERENT declared action on the card the verdict names an action of."""
    a = str(verdict_action or "").strip()
    if not a or a not in declared:
        return False
    calls = [str(x.get("action") or "").strip() for n, x in got
             if n == "widget_data" and str(x.get("widget_id") or "").strip().lower() == wid]
    return bool(calls) and a not in calls


def _verdict_hint(action: str, manifest: dict) -> str:
    """One line naming the action the engine's own reading of the order chose on this card, when it declares it.

    Demo passes 88/89 (2026-10-03), R3 «find a five-day period during her vacation when my calendar is clear»: the
    verdict read `agenda:find_free` (0.73-0.80) and this pass, not told, called `show_day` — a view of ONE day — and
    the answer was «I can't map out five days from just this». The verdict completes the pass; it never overrules a
    call that fits better."""
    a = str(action or "").strip()
    if not a or a not in (manifest.get("actions") or {}):
        return ""
    return (f"\nThe engine's reading of this order names the action «{a}» on this card — use it, with every value "
            f"the conversation already gave (dates, names), unless it clearly cannot do what he asked.")


async def call_or_read_for_commission(operator_text: str, commission: str, widget_id: str, spec=None, *,
                                      window=None, may_read: bool = True, verdict_action: str = "") -> dict | None:
    """A commission that names one of our cards, before it costs a worker (V2-773 final pass, C1): «Find me a
    free 45-minute slot tomorrow afternoon» was delegated to a Brain Worker (three minutes) when the agenda was
    the whole answer. One pass with the card in front decides: `{"kind": "call", widget_id, action, payload}`,
    `{"kind": "read", widget_id, question}`, or None — and None keeps today's path, the worker. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        if not wid or not (operator_text or "").strip() or _cp.canvas_holds_the_turn(None, operator_text, wid):
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        # The read option only for a card that can ANSWER (`widget_read.can_answer`): a messaging card gets the
        # call («message Rowan on Telegram» → send_to) and never a read it cannot serve.
        from nucleo.flash import widget_read as _wr0
        tools = [t for t in (_cp.tool_named("widget_data"),
                             _cp.tool_named("read_widget") if (may_read and _wr0.can_answer(wid)) else None) if t]
        from nucleo.flash import compose_rung as _compose
        if tools and _compose.prose_action(wid):
            tools.append(_compose.tool())   # a card that holds prose: its text may be WRITTEN now (2026-10-22)
        if not manifest or not tools:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_cp._CARD.format(wid=wid, digest=digest) if digest else "") + _other_open_cards(wid)
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        _msgs = [{"role": "system", "content": _cp.in_his_lang(_cp._SYS_COMMISSION).format(wid=wid, actions=_cp.actions_block(manifest), card=card)},
                 {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»\n"
                                             f"The commission that was going to a worker: «{(commission or '').strip()[:300]}»"
                                             + _verdict_hint(verdict_action, manifest)
                                             + _cp.conversation(window)}]
        await FastClient().complete(
            _msgs, spec=spec, max_tokens=300, tools=tools, no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        declared = manifest.get("actions") or {}
        if _ignored_the_verdict(got, wid, verdict_action, declared):
            # Demo pass 92, R3: hint agenda:find_free 0.75, the pass called show_day again. ONE more ask naming the
            # action; whatever it answers is taken (the verdict completes the pass, never runs blind).
            got.clear()
            await FastClient().complete(
                _msgs + [{"role": "user", "content": f"Call «{verdict_action}» on «{wid}» — that is the action this "
                                                     f"order needs; fill its payload from the operator's words and the "
                                                     f"conversation."}],
                spec=spec, max_tokens=300, tools=tools, no_thinking=True,
                on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if str(args.get("widget_id") or "").strip().lower() != wid:
                continue
            if (_c := _compose.decision(name, args, wid)):
                return _c
            if name == "read_widget":
                q = str(args.get("question") or "").strip() or operator_text.strip()
                return {"kind": "read", "widget_id": wid, "question": q[:300]}
            if name == "widget_data" and str(args.get("action") or "").strip() in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"kind": "call", "widget_id": wid, "action": str(args["action"]).strip(), "payload": payload}
        _cp.note(wid, "el encargo sigue su camino al worker" if not got else "la llamada no era de esta tarjeta")
        return None
    except Exception:  # noqa: BLE001 — never take down a live turn
        return None
