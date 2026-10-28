"""`TaskBrowser`'s actions (`_StepsMixin`): one step of the automator or the bridge, every route that reaches
the mouse or the keyboard behind the one gate, and the operator's OK for an irreversible click. The owner's state
and every name are read through the package (`_o.<name>`), so a patch on `owner` governs every call.
"""

import asyncio
import random

from nucleo.errors import brief as _brief
from widgets.navegador import click_gate as _click_gate
from widgets.navegador import click_reason as _click_reason

from widgets.navegador import owner as _o


class _StepsMixin:
    """`TaskBrowser`'s actions: one step of the automator or the bridge, behind the one gate."""

    async def agent_act(self, action: str, args: dict) -> tuple[bool, str]:
        page = await self.ensure()
        try:
            if action == "navigate":
                await self._goto(_o._normalize_url(str(args.get("url", ""))))
                # V2-152: reaching a page is a MILESTONE (what the task DID, not every click); in the worker-driven
                # path nothing else appends one, so `steps`/`last_event` would stay empty for «¿cómo va?».
                from widgets.navegador import tasks
                tasks.milestone(self.task_id, f"🌐 abrió {page.url[:120]}")
                return True, f"navegado a {page.url}"
            if action == "scroll":
                try:
                    await page.mouse.wheel(0, float(args.get("dy", 600)))
                    await asyncio.sleep(0.2)
                except Exception:
                    pass
                await self._capture()
                return True, "desplazado"
            if action == "press":
                # V2-711 T1 — Enter inside a form is a submit, the same consequence the click gate guards: gated
                # on the FOCUSED element, which is what Enter acts on.
                key = str(args.get("key", "Enter")) or "Enter"
                if key.lower() in ("enter", "numpadenter", "return"):
                    ok, why = await self._may_act(page, None)
                    if not ok:
                        return False, why
                try:
                    await page.keyboard.press(key)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                await self._capture()
                return True, "tecla pulsada"
            if action in ("click_at", "type_at"):
                return await self._act_by_vision(page, action, args)
            ref = int(args.get("ref", 0))
            h = self.refs.get(ref)
            if h is None:
                # V2-248 — an expired ref says how to RECOVER (look again), not only what happened. Deliberately NOT
                # retried with the new snapshot: numbers are ASSIGNED per look, so 26 there is a different element.
                return False, _o._stale_ref_reason(ref, self.refs, getattr(self, "refs_url", ""),
                                                getattr(page, "url", "") or "")
            if action == "click":
                # CONFIRM-GATE (safety): an IRREVERSIBLE-looking click STOPS for the operator's OK BEFORE clicking.
                # All four routes share `_may_act` (V2-711 T1), which reads the element's CONTEXT as well as its
                # words and fails CLOSED when it cannot be described.
                ok, why = await self._may_act(page, h)
                if not ok:
                    return False, why
                await _o._human_click_handle(page, h, self.mouse)
                await asyncio.sleep(0.7)
                await self._reap_popups()                     # TASK 3: absorb/close popups → no accumulated tabs
                await self._capture()
                return True, "clic hecho"
            if action == "type":
                # Typing is harmless; `--submit` presses Enter inside the helper, which is not (V2-711 T1).
                _submit = bool(args.get("submit"))
                if _submit:
                    ok, why = await self._may_act(page, h)
                    if not ok:
                        await _o._human_type_handle(page, h, str(args.get("text", "")), False, self.mouse)
                        await self._capture()
                        return True, "texto escrito; NO enviado: " + why
                await _o._human_type_handle(page, h, str(args.get("text", "")), _submit, self.mouse)
                await asyncio.sleep(0.6)
                await self._capture()
                return True, "texto escrito"
            if action == "select_option":
                # NATIVE <select>: cannot be filled with type/click_at (the native popup is not scrapeable).
                # Playwright `select_option` resolves it by LABEL (visible text), value, or index. Without this, a
                # required form dropdown (ITV cancellation reason, dates...) BLOCKS the worker → timeout.
                val = str(args.get("value") or args.get("text") or args.get("label") or "").strip()
                idx = args.get("index")
                try:
                    if idx is not None:
                        await h.select_option(index=int(idx))
                    else:
                        try:
                            await h.select_option(label=val)
                        except Exception:
                            await h.select_option(val)   # value or generic label (fallback)
                except Exception as e:  # noqa: BLE001
                    return False, f"no pude seleccionar «{val or idx}» en el desplegable: {_brief(e, 80)}"
                await asyncio.sleep(0.4)
                await self._capture()
                return True, f"opción «{val or idx}» seleccionada"
        except Exception as e:
            return False, f"{type(e).__name__}: {_brief(e, 120)}"
        return False, f"acción desconocida: {action}"

    async def _act_by_vision(self, page, action: str, args: dict) -> tuple[bool, str]:
        """`click_at`/`type_at`: act on a point of the screenshot (the VISION route), gated like every other route
        that reaches the mouse or the keyboard."""
        x, y = float(args.get("x", 0)), float(args.get("y", 0))
        # V2-711 T1 — the VISION route (the one `nav_cli` recommends for forms) is gated too: the element under
        # the pixel is resolved BEFORE the mouse moves.
        if action == "click_at":
            ok, why = await self._may_act(page, None, at=(x, y))
            if not ok:
                return False, why
        self._emit("vision_" + ("click" if action == "click_at" else "type"), f"{int(x)},{int(y)}")
        await _o._human_click_at(page, x, y, self.mouse)
        if action == "type_at":
            await page.keyboard.type(str(args.get("text", "")), delay=random.randint(40, 120))
            if bool(args.get("submit")):
                # `--submit` is an Enter, and an Enter in a form submits it. Same gate, same reason.
                ok, why = await self._may_act(page, None)
                if not ok:
                    return True, "texto escrito; NO enviado: " + why
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await page.keyboard.press("Enter")
        await asyncio.sleep(0.7)
        await self._reap_popups()
        await self._capture()
        return True, ("clic" if action == "click_at" else "texto") + " (visión) hecho"

    async def _may_act(self, page, handle, at: tuple[float, float] | None = None) -> tuple[bool, str]:
        """THE ONE GATE in front of an irreversible click (V2-711 T1). All four routes that reach the mouse
        or the keyboard consult it BEFORE moving anything; the decision itself lives in `click_gate`."""
        return await _click_gate.may_act(page, handle, at, confirm=self._confirm, task_id=self.task_id)

    async def _confirm(self, label: str) -> bool:
        """Ask the operator for OK on an irreversible action and WAIT for the response (by voice, routed to this task).
        Returns True if approved. `_CONFIRM_TIMEOUT` without an answer → do not execute (fail-safe). Cancellable."""
        from widgets.navegador import tasks
        tasks.ask(self.task_id, _click_reason.card_question(label))
        try:
            from voice import proactive
            await proactive.notify("navegador",
                                   _click_reason.needs_ok(self.task_id, label),
                                   kind="notify")
        except Exception:
            pass
        for _ in range(int(_o._CONFIRM_TIMEOUT / 0.5)):
            if tasks.is_cancelled(self.task_id):
                return False
            ans = tasks.take_answer(self.task_id)
            if ans:
                aff = any(w in ans.lower() for w in
                          ("sí", "si", "ok", "vale", "dale", "confirm", "adelante", "hazlo", "yes", "claro"))
                tasks.set_status(self.task_id, "working")
                tasks.add_event(self.task_id, "✅ confirmado" if aff else "🚫 no confirmado")
                return aff
            await asyncio.sleep(0.5)
        tasks.set_status(self.task_id, "working")
        tasks.add_event(self.task_id, "⏱ sin confirmación → no ejecuto la acción")
        return False
