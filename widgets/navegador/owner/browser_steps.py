"""`TaskBrowser`'s actions (`_StepsMixin`): one step of the automator or the bridge, every route that reaches
the mouse or the keyboard behind the one gate, and the operator's OK for an irreversible click.
Moved out of `owner.py`; the owner's state and every module name are read through the package (`_o.<name>`), so a
patch on `owner` still governs every call.
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
                # V2-152: reaching a page is a MILESTONE by this module's own definition (what the task DID, not
                # every click), and nothing in the worker-driven path ever appended one — `_automate` pushes the
                # milestones and that is the built-in loop, not the path a Brain Worker drives. So `steps` was
                # structurally 0 and `last_event` empty for the whole life of a worker task, and the brain had a
                # step COUNT of zero to answer «¿cómo va?» with. `_goto` already captures the view on success, so
                # `url` is not the gap here; the FEED is.
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
                # V2-711 T1 — this pressed Enter with NO gate of any kind, and Enter inside a form is a
                # submit: the same consequence as the click the gate next door was guarding. Gated on the
                # FOCUSED element, which is what Enter acts on.
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
                # V2-248 — AN EXPIRED REF SAID WHAT WAS HAPPENING BUT NOT HOW TO RECOVER. Same contract as node 4.20
                # and V2-203: the bridge SAYS what it knows, and an error also says how to recover. Measured by the
                # harness on 2026-08-21 (`ref 26 does not exist`, the V2-212 form): it is one of the three causes
                # that made a worker die on its own, while the recovery —look again— was one command away.
                #
                # It is deliberately NOT retried using only the new snapshot: numbers are ASSIGNED during a look,
                # so 26 in the new look is a different element. Retrying would click something else.
                return False, _o._stale_ref_reason(ref, self.refs, getattr(self, "refs_url", ""),
                                                getattr(page, "url", "") or "")
            if action == "click":
                # CONFIRM-GATE (safety): if the click looks IRREVERSIBLE, STOP and ask the operator for OK
                # BEFORE clicking. The automator never buys/publishes/deletes/books blindly.
                # V2-711 T1: this used to be the ONLY gated route and it judged the LABEL alone — 21 of 30
                # real button labels walked through it, «Reservar» and «Confirmar reserva» among them — and
                # it failed OPEN when the element could not be described. All four routes share `_may_act`
                # now, which reads the element's CONTEXT as well as its words and fails CLOSED.
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
        # V2-711 T1 — the VISION route, which `nucleo/nav_cli.py` RECOMMENDS to the worker («VISION
        # flow (robust for forms)»), reached the mouse with no gate at all: the recommended path was
        # the unguarded one. The element under the pixel is resolved BEFORE the mouse moves.
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
        Returns True if approved. Timeout ~60s → do not execute (fail-safe). Cancellable."""
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
