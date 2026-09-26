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

#: What the repair tells the model. Short on purpose: the ask is «make the call you promised», not a new turn.
_SYS = ("Eres el cerebro de un asistente de voz. En el turno anterior PROMETISTE (o AFIRMASTE haber hecho) algo "
        "sobre la tarjeta «{wid}» y NO llamaste a ninguna herramienta. Haz AHORA exactamente la llamada "
        "`widget_data` que cumple lo que dijiste, con widget_id «{wid}», una de estas acciones declaradas y el "
        "payload sacado de las palabras del operador y de lo que hay en la tarjeta (una hora relativa —«media "
        "hora más tarde»— se calcula sobre la cita que hay). Si ninguna encaja, no llames a nada.\n\n"
        "Acciones de «{wid}»:\n{actions}{card}")
#: What the card holds, so a relative order («move it 30 minutes later») can be turned into a call. The
#: demo run (2026-09-26): the model computed «It's now at 2:00 PM, running until 2:45» in the turn — it had the
#: digest — and this pass, which had only his words, could not, and returned nothing in silence.
_CARD = "\n\nLO QUE HAY EN LA TARJETA «{wid}» AHORA:\n{digest}"


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


async def call_for_promise(operator_text: str, reply: str, widget_id: str, spec=None) -> dict | None:
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
                                         f"Tu respuesta (sin llamada): «{(reply or '').strip()[:300]}»"}],
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
