"""nucleo/workers/generator_session.py — backend `GeneratorBackend` (V2-038, §v3·Q4).

Unifica la CREACIÓN/MODIFICACIÓN de widgets bajo el sustrato de Brain Workers **conservando el CONTRATO**: reutiliza
`widgets/generator.py` ÍNTEGRO (su `_CONTRACT`, la validación de acciones/background/CSS, el journal `_jobs`,
rollback) — solo se sustituye la EJECUCIÓN por una sesión matable/observable. Así "crea un widget del clima" es un
Brain Worker como cualquier otro (matable con stop_worker, visible en /api/tasks) sin duplicar el sustrato de
subproceso ni perder la validación (que era el valor real del generador).

Emite WorkerEvent: phase (creando/modificando) → result (id creado / error) → done. `stop()` mata el subproceso del
generador por token (= task_id). La inyección (↓) a una generación en curso no aplica (un build atómico no reabre
turno) → se ignora con gracia; el operador refina re-generando o modificando después.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from .base import WorkerBackend, WorkerEvent, WorkerSpec


class GeneratorBackend(WorkerBackend):
    name = "widget_generator"

    def __init__(self):
        self._q: asyncio.Queue[WorkerEvent] = asyncio.Queue()
        self._task_id = ""
        self._done = False
        self._run_task: asyncio.Task | None = None

    async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
        self._task_id = spec.task_id or ""
        req = (spec.env or {}).get("ZAELAR_TASK_REQUEST") or prompt or ""
        self._run_task = asyncio.create_task(self._drive(req))

    async def _drive(self, req: str) -> None:
        try:
            from widgets import generator
            from nucleo.agentes import code as _code   # helpers de detección (módulo estable, reutilizado)
            # DECISIÓN crear/modificar/borrar por la FUENTE ÚNICA `code.widget_action` (§sesión 2026-07-15):
            # antes el generador exigía un verbo de modificar y "implementar en el widget X …" caía a CREATE →
            # widget basura. Ahora: existente + sin verbo de crear = MODIFY; borrado explícito = DELETE.
            action, existing = _code.widget_action(req)
            if action == "delete":
                # Un borrado que llegó hasta aquí (debería resolverlo el FlashBrain, V2-017) NUNCA debe acabar
                # creando/modificando un widget: se borra de verdad y se reporta.
                await self._emit("phase", label=f"borrando el widget «{existing}»…")
                from widgets import lifecycle
                res = await lifecycle.delete_widget(existing, f"worker:{self._task_id or 'code'}")
                summary = (f"He borrado el widget «{existing}»." if res.get("ok")
                           else f"No pude borrar el widget «{existing}».")
                await self._emit("result", summary=summary, ok=bool(res.get("ok")),
                                 data={"widget": existing, "deleted": bool(res.get("ok"))})
                return
            if action == "modify":
                await self._emit("phase", label=f"modificando el widget «{existing}»…")
                res = await asyncio.to_thread(generator.modify_widget, existing, req, self._task_id)
            else:
                await self._emit("phase", label="creando un widget…")
                res = await asyncio.to_thread(generator.generate_widget, req, "", "", self._task_id)
            if res.get("ok"):
                wid = res.get("id") or ""
                verb = "actualizado" if action == "modify" else "creado"
                if res.get("existed"):
                    summary = f"El widget «{wid}» ya existía, te lo muestro."
                else:
                    summary = f"He {verb} el widget «{wid}»."
                await self._emit("result", summary=summary, ok=True, data={"widget": wid})
            else:
                # Sesión 23:15 2026-07-16: el fallo decía «No pude CREAR el widget» en un MODIFY (confunde: parece
                # que se intentó crear otro) y la RAZÓN REAL no salía de este dict → indiagnosticable a posteriori.
                # Copy por acción + razón al timeline (evento task/generator_fail).
                err = str(res.get("error") or "")[:300]
                verb = (f"modificar el widget «{existing}»" if action == "modify" and existing
                        else "crear el widget")
                try:
                    from voice.observer import emit as _obs_emit
                    _obs_emit("task", "generator_fail", text=err or "(sin detalle del generador)", role="system",
                              extra={"id": self._task_id, "action": action, "widget": existing or ""})
                except Exception:
                    pass
                await self._emit("result", summary=f"No pude {verb}.", ok=False, data={"error": err})
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"generator worker[{self._task_id}] falló: {e}")
            try:
                from voice.observer import emit as _obs_emit
                _obs_emit("task", "generator_fail", text=str(e)[:300], role="system", extra={"id": self._task_id})
            except Exception:
                pass
            await self._emit("result", summary="No pude completar el trabajo del widget.", ok=False)
        finally:
            await self._emit("done")
            self._done = True

    async def send(self, text: str) -> None:
        return                                   # un build atómico no acepta inyección mid-turno

    async def events(self):
        while True:
            ev = await self._q.get()
            yield ev
            if ev.type == "done":
                return

    async def stop(self, *, grace: float = 3.0) -> None:
        self._done = True
        try:
            from widgets import generator
            generator.kill(self._task_id)        # mata el subproceso `claude` del generador (to_thread no cancelable)
        except Exception:
            pass
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()

    @property
    def alive(self) -> bool:
        return not self._done

    async def _emit(self, etype: str, **data) -> None:
        await self._q.put(WorkerEvent(task_id=self._task_id, type=etype, data=data, backend=self.name))
