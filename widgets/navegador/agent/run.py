"""The automator's LOOP: one task driven step by step over the current page (DOM first, vision when stuck, a
stronger model on a hard bottleneck), and the Energy report of each call. Names are read through the package
(`_f.<name>`), so a patch on `agent` governs every call.
"""

import json

from loguru import logger

from widgets.navegador import agent as _f


async def run_task(goal: str, owner, plan: str = "", max_steps: int = _f._MAX_STEPS) -> dict:
    """Hybrid DOM+vision loop. `owner` is the owner.py module (snapshot/capture + action execution).
    `plan` = high-level guide prepared by Hermes (optional, best-effort). Drives the CURRENT page to complete the
    goal; when DOM is not enough, the model asks for `need_vision` and the next step acts on the SCREENSHOT.
    Returns {ok, success, summary, steps}. Never raises; degrades to {ok:False}."""
    if not _f.available():
        return {"ok": False, "summary": "El automatizador no tiene clave de modelo configurada (AIMLAPI_KEY)."}
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "summary": "objetivo vacío"}
    owner._emit("task_start", goal + (f" · plan: {plan[:80]}" if plan else ""))
    # Minimal history (short window): system + initial state. Re-inject fresh snapshot each turn.
    messages = [{"role": "system", "content": _f._SYSTEM}]
    if plan:
        messages.append({"role": "system", "content":
            "PLAN sugerido por el cerebro profundo (guíate por él, adáptalo a lo que veas en la página):\n" + plan})
    steps: list[str] = []
    pending_vision = False          # previous step requested VISION -> this step uses screenshot + coordinate tools
    last_fp = None                  # page fingerprint (url+title+elements) for detecting "nothing happened"
    no_progress = 0                 # consecutive steps WITHOUT page change -> loop is stuck
    last_sig = None                 # last action signature, to stop "same action over and over" loops
    same_sig = 0
    hard = 0                        # stuck count -> on the 2nd one, use ADVANCED model if configured (third rung)
    strong_mode = False
    _tid = getattr(owner, "task_id", "") or ""
    try:
        for i in range(max_steps):
            # CONTINUITY: reread the goal (the operator may clarify it mid-task) and go on in the SAME tab.
            if _tid:
                goal = _f._reread_the_goal(owner, _tid, goal)
            state = await owner.snapshot_for_agent()          # {"url","title","elements": "..."}
            # LOGIN WALL (deterministic, BEFORE the model acts): on a sign-in screen stop with needs_login — the loop
            # never invents credentials; the owner opens the real window and the task resumes after login.
            if _f._looks_like_login(state["url"], state["elements"]):
                site = _f._login_site(state["url"])
                owner._emit("task_need_login", f"login requerido en {site}")
                return {"ok": True, "success": False, "needs_login": True, "site": site,
                        "login_url": state["url"], "steps": steps,
                        "summary": f"«{site}» pide iniciar sesión; te abro la ventana para que entres con tu cuenta."}
            # ANTI-STUCK: the page did not change (no_progress) or the model REPEATS its action (same_sig) → force
            # VISION and act by coordinates (unsticks overlays, unfocused fields); give up only if vision can't advance.
            fp = hash((state["url"], state["title"], state["elements"]))
            if not pending_vision:
                no_progress = no_progress + 1 if (last_fp is not None and fp == last_fp) else 0
            last_fp = fp
            if no_progress >= 5:
                owner._emit("task_giveup", "sin progreso ni con visión")
                return {"ok": True, "success": False, "steps": steps,
                        "summary": "No conseguí avanzar en la página (no cambiaba tras cada intento, ni mirándola). "
                                   "Lo dejo en el último estado visible."}
            if not pending_vision and (no_progress >= 2 or same_sig >= 1):
                owner._emit("task_stuck", f"stuck (no_progress={no_progress}, repeat={same_sig}) -> VISION")
                pending_vision = True
                same_sig = 0                                  # give vision a clean chance
                hard += 1
                # THIRD RUNG: if still stuck and an ADVANCED model is configured, upgrade only on hard steps for
                # controlled cost. This unblocks bottlenecks the cheap model cannot pass.
                if hard >= 2 and not strong_mode and _f._model_strong():
                    strong_mode = True
                    owner._emit("task_upgrade", f"bottleneck -> advanced model ({_f._model_strong()})")
            action, args = await _f._ask_the_model(owner, messages, state, goal, pending_vision, strong_mode)
            pending_vision = False
            if action is None:
                # V2-253: if the step died because of unreadable arguments or the limit, that is what gets recorded — not
                # "emitted no action," which is something else and tells us to inspect the model when the limit is ours.
                steps.append(args.get("_error") or "(el modelo no emitió acción)")
                break
            if action == "need_vision":
                owner._emit("task_need_vision", args.get("why", ""))
                steps.append("need_vision")
                pending_vision = True
                # Does not consume a "real step"; next turn acts with the screenshot. Avoid infinite loop: if it
                # asks for vision twice in a row without acting, the for counter still advances and bounds it.
                continue
            if action == "need_login":
                # The model detected a login that deterministic checks missed (odd URL). Same outcome: stop without
                # typing credentials and return needs_login so the owner opens the real window.
                site = _f._login_site(state["url"])
                owner._emit("task_need_login", f"login requerido en {site}: {args.get('why', '')}"[:160])
                steps.append("need_login")
                return {"ok": True, "success": False, "needs_login": True, "site": site,
                        "login_url": state["url"], "steps": steps,
                        "summary": f"«{site}» pide iniciar sesión; te abro la ventana para que entres con tu cuenta."}
            sig = (action, json.dumps(args, sort_keys=True, ensure_ascii=False))
            same_sig = same_sig + 1 if sig == last_sig else 0
            last_sig = sig
            if same_sig >= 4:                                 # identical repeat even after vision -> cut off
                owner._emit("task_giveup", f"acción repetida sin efecto: {action}")
                return {"ok": True, "success": False, "steps": steps,
                        "summary": "Me quedé repitiendo la misma acción sin efecto; lo dejo en el estado actual."}
            owner._emit("task_step", f"{i+1}: {action} {json.dumps(args, ensure_ascii=False)[:120]}")
            steps.append(f"{action}({', '.join(f'{k}={v}' for k, v in args.items())})")
            if action == "done":
                owner._emit("task_done", args.get("summary", "")[:160])
                return {"ok": True, "success": bool(args.get("success")),
                        "summary": args.get("summary", "hecho"), "steps": steps}
            ok, note = await owner.agent_act(action, args)    # execute with human-like behavior
            messages.append({"role": "assistant", "content": f"[acción {action} → {note}]"})
            if not ok:
                messages.append({"role": "user", "content": f"La acción falló: {note}. Prueba otra cosa."})
        owner._emit("task_giveup", f"{max_steps} pasos sin done")
        return {"ok": True, "success": False, "steps": steps,
                "summary": f"No completé el objetivo en {max_steps} pasos. Último estado en pantalla."}
    except Exception as e:
        logger.warning(f"navegador agent: {e}")
        owner._emit("task_error", str(e)[:160])
        return {"ok": False, "summary": f"error del automatizador: {e}", "steps": steps}


def _reread_the_goal(owner, tid: str, goal: str) -> str:
    """CONTINUITY: the goal as the operator left it — he may have clarified it mid-task. The loop goes on in the SAME
    tab with what he really wants, without opening another."""
    try:
        from widgets.navegador import tasks as _tasks
        _cur = (_tasks.get(tid) or {}).get("goal") or ""
        if _cur.strip() and _cur.strip() != goal:
            goal = _cur.strip()
            owner._emit("task_refine", f"goal updated by operator: {goal[:100]}")
    except Exception:
        pass
    return goal


async def _ask_the_model(owner, messages: list[dict], state: dict, goal: str, vision: bool,
                         strong: bool) -> tuple[str | None, dict]:
    """One step's question to the model: the page as DOM refs, or — in vision mode — its screenshot with the
    coordinate tools (the image is paid only here)."""
    if vision:
        img = await owner.screenshot_b64()
        messages.append({"role": "user", "content": [
            {"type": "text", "text": (f"OBJETIVO: {goal}\nURL: {state['url']} · {state['title']}\n"
                                      f"{_f._VISION_SYSTEM}")},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
        ]})
        return await _f._next_action(messages, _f._VISION_TOOLS, strong=strong)
    user = (f"OBJETIVO: {goal}\n\nURL: {state['url']}\nTítulo: {state['title']}\n\n"
            f"ELEMENTOS INTERACTIVOS:\n{state['elements'] or '(ninguno visible)'}")
    messages.append({"role": "user", "content": user})
    return await _f._next_action(messages, _f._TOOLS, strong=strong)
