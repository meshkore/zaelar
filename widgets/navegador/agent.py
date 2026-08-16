#
# agent.py: browser AUTOMATOR (INI-016, Milestone 2): a goal-driven, DOM-first loop that drives the owner's
# Chromium to complete a natural-language goal. HYBRID approach decided with the operator on 2026-07-08:
#
#   - DOM-first (cheap): each step passes the model a TEXT SNAPSHOT of the page's interactive elements
#     (accessibility tree -> `[7] textbox "Search"`), not a screenshot. The model chooses the NEXT action through
#     function-calling (click/type/scroll/navigate/press/done). Text tokens only -> cents per task.
#   - HUMAN behavior in the Playwright layer (owner.py), free of token cost: mouse curve + delays + jittered typing.
#     Always active; this is what makes websites behave well without paying model cost for it.
#   - VISION only on demand: if the model cannot solve through DOM, it asks for `need_vision` and the step attaches
#     ONE screenshot (expensive), so the image is paid only on that step. Vision phase: stub in M2, completed in M3.
#
# Brain = DEDICATED CHEAP MODEL through the same routing as duo (AIMLAPI, UA-spoof anti-Cloudflare), defaulting to
# `anthropic/claude-haiku-4.5`. Configurable by env (NAVEGADOR_AGENT_*). Does NOT use the Hermes agent: governance
# already escalates the DECISION to automate to Hermes (`automate` action = safe:false); the loop itself is
# mechanical and cheap, and should not occupy the voice ACP turn.
#
import json
import os
import re
from urllib.parse import urlsplit

from loguru import logger
from openai import AsyncOpenAI

DEFAULT_BASE_URL = "https://api.aimlapi.com/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"   # in AIMLAPI's allowed flash list (CLAUDE.md routing)
_MAX_STEPS = int(os.environ.get("NAVEGADOR_AGENT_MAX_STEPS", "16"))

# LOGIN WALL: deterministic detection so credentials are never invented (2026-07-10 bug: on Google login, the loop
# typed a fake email and spun). When the page IS a login screen, the loop types nothing: it stops and returns
# needs_login, so the owner opens the REAL window for the operator to log in manually. The session remains in the
# persistent profile. Known login URL patterns + DOM signal (password field).
_LOGIN_URL_RE = re.compile(
    r"(accounts\.google\.[^/]+/.*(signin|login)|/login(\b|[/?])|/signin(\b|[/?])|/sign-in(\b|[/?])|"
    r"/auth/(login|signin)|/sso/|/session/new|/uas/login|/checkpoint/|login\.(microsoftonline|yahoo|live)\.com|"
    r"appleid\.apple\.com|/oauth/authorize|wallapop\.[^/]+/login)", re.I)
_LOGIN_DOM_RE = re.compile(r'(type="password"|"password"|contrase[nñ]a|\biniciar sesi[oó]n\b|\bsign in\b|\blog ?in\b)',
                           re.I)


def _login_site(url: str) -> str:
    """Readable login site name (host without www) for asking the operator to sign in there."""
    try:
        host = (urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host or url
    except Exception:
        return url or "el sitio"


def _looks_like_login(url: str, elements: str) -> bool:
    """True if the CURRENT page is a login wall. Known login URL (reliable) OR a password field in the snapshot with
    login wording. A simple sign-in button on a landing page is NOT enough because there is no password field, which
    avoids false positives on YouTube/Wallapop home pages."""
    u = (url or "").lower()
    if _LOGIN_URL_RE.search(u):
        return True
    el = (elements or "")
    return ('password' in el.lower() or 'contrase' in el.lower()) and bool(_LOGIN_DOM_RE.search(el))


def _base_url() -> str:
    return os.getenv("NAVEGADOR_AGENT_BASE_URL", DEFAULT_BASE_URL)


def _model() -> str:
    return os.getenv("NAVEGADOR_AGENT_MODEL", DEFAULT_MODEL)


def _judge_model() -> str:
    """Model that judges relevance of extracted listings, including exact-category fit. Off-hot-path, so prioritize
    judgment over latency: a capable model distinguishes enduro from trial/road. Default `deepseek/deepseek-v4-flash`
    (cheap and good at reasoning, through AIMLAPI on the same endpoint). Adjustable with `NAVEGADOR_JUDGE_MODEL`."""
    return os.getenv("NAVEGADOR_JUDGE_MODEL", "deepseek/deepseek-v4-flash").strip() or _model()


def _model_strong() -> str:
    """Optional ADVANCED model, used ONLY to unblock bottlenecks the cheap model cannot pass (third rung:
    cheap-DOM -> vision -> advanced model). Configurable through the store (`navegador_agent_model_strong`, written
    by the UI) or env `NAVEGADOR_AGENT_MODEL_STRONG`. Empty = no escalation; keep using the cheap model. Uses the
    SAME endpoint/key (`NAVEGADOR_AGENT_BASE_URL`/AIMLAPI), so set an id served by that provider, e.g.
    `anthropic/claude-sonnet-4.5`. Cost is controlled: paid only on hard steps."""
    v = os.getenv("NAVEGADOR_AGENT_MODEL_STRONG", "").strip()
    if v:
        return v
    try:
        import json as _json
        from config.settings import SETTINGS_FILE
        if SETTINGS_FILE.is_file():
            return str((_json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {})
                       .get("navegador_agent_model_strong") or "").strip()
    except Exception:
        pass
    return ""


def _api_key() -> str:
    # Explicit key wins; otherwise the single shared endpoint→key resolver (nucleo/provider_keys.py, V2-098).
    if os.getenv("NAVEGADOR_AGENT_API_KEY"):
        return os.getenv("NAVEGADOR_AGENT_API_KEY")
    u = _base_url().lower()
    if "11434" in u or "localhost" in u or "127.0.0.1" in u:
        return "ollama"
    from nucleo.provider_keys import key_for_endpoint
    return key_for_endpoint(u) or os.getenv("AIMLAPI_KEY", "") or os.getenv("OPENAI_API_KEY", "")


def available() -> bool:
    return bool(_api_key())


_client: AsyncOpenAI | None = None


def _c() -> AsyncOpenAI:
    global _client
    if _client is None:
        key = _api_key()
        if not key:
            raise RuntimeError("no NAVEGADOR_AGENT_API_KEY/AIMLAPI_KEY para el automatizador del navegador")
        # EGRESS (T304). This agent makes the most calls in the system, one per navigation step, so it most needed
        # mediated key handling. Not anymore.
        from nucleo import llm_egress
        base, key, extra = llm_egress.route(_base_url(), key)
        if not key:
            raise RuntimeError("sin credencial para el automatizador del navegador")
        headers = dict(extra)
        # Browser UA is for Cloudflare in front of AIMLAPI. With mediated egress, the far end talks to AIMLAPI, so
        # it is unnecessary here.
        if not extra and "aimlapi" in base.lower():
            headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        _client = AsyncOpenAI(api_key=key, base_url=base, default_headers=headers or None)
    return _client


# Action vocabulary the model can emit through function-calling: reliable and language-agnostic, like duo
# escalation. The backend resolves refs against the snapshot from the SAME step.
_TOOLS = [
    {"type": "function", "function": {"name": "click", "description": "Haz clic en el elemento con esa ref del snapshot",
        "parameters": {"type": "object", "properties": {"ref": {"type": "integer"}}, "required": ["ref"]}}},
    {"type": "function", "function": {"name": "type", "description": "Escribe texto en el campo con esa ref (lo enfoca antes)",
        "parameters": {"type": "object", "properties": {"ref": {"type": "integer"}, "text": {"type": "string"},
            "submit": {"type": "boolean", "description": "pulsar Enter al terminar"}}, "required": ["ref", "text"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Desplaza la página (dy>0 baja)",
        "parameters": {"type": "object", "properties": {"dy": {"type": "integer"}}, "required": ["dy"]}}},
    {"type": "function", "function": {"name": "navigate", "description": "Ve a una URL o dominio directamente",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "press", "description": "Pulsa una tecla (Enter, Escape, Tab…)",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "done", "description": "El objetivo está cumplido (o es imposible); resume qué se ve",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"},
            "success": {"type": "boolean"}}, "required": ["summary", "success"]}}},
    {"type": "function", "function": {"name": "need_vision", "description": "No puedes resolver por el texto de la página; pide una captura",
        "parameters": {"type": "object", "properties": {"why": {"type": "string"}}, "required": ["why"]}}},
    {"type": "function", "function": {"name": "need_login", "description": "La página exige INICIAR SESIÓN con la cuenta del usuario y el objetivo la necesita. NO inventes credenciales: pide que el operador inicie sesión.",
        "parameters": {"type": "object", "properties": {"why": {"type": "string"}}, "required": ["why"]}}},
]

_SYSTEM = (
    "Eres un piloto de navegador web. Cumples un OBJETIVO del usuario conduciendo una página real paso a paso.\n"
    "En cada turno recibes: el objetivo, la URL y título actuales, y un SNAPSHOT de los elementos interactivos "
    "visibles, cada uno con una ref numérica entre corchetes, p.ej.:\n"
    "  [3] link \"Motos\"\n  [7] textbox \"¿Qué buscas?\"\n  [12] button \"Buscar\"\n"
    "Elige UNA acción llamando a UNA función. Reglas:\n"
    "- HONRA LA CATEGORÍA EXACTA del objetivo en CADA paso: las categorías son EXCLUYENTES. Si el objetivo pide una "
    "moto de ENDURO, NO abras ni filtres por trial, cross ni carretera; si pide un piso, no un local. Antes de "
    "teclear o clicar un filtro/categoría, comprueba que sigue el objetivo — y si te das cuenta de que la página "
    "muestra la categoría equivocada, corrige el término/filtro en vez de seguir. No generalices ni cambies de "
    "categoría por tu cuenta.\n"
    "- BANNERS DE COOKIES: al llegar a una web, si ves un cartel de cookies/consentimiento (botón \"Aceptar\"/"
    "\"Aceptar todo\" o similar) que TAPA la página, tu PRIMERA acción es aceptarlo. NO llames a done mientras un "
    "banner de cookies tape la página.\n"
    "- YA ESTÁS EN UNA PÁGINA (mira la URL). Si el objetivo es sobre el sitio en el que ya estás, USA SU buscador "
    "y sus filtros — NO navegues a un buscador externo (Bing/Google) ni te vayas del sitio. Solo usa navigate si "
    "el objetivo pide EXPLÍCITAMENTE otra web distinta.\n"
    "- Usa las refs EXACTAS del snapshot de ESTE turno (cambian cada paso).\n"
    "- Para buscar: escribe en el campo de texto con submit=true; no busques un botón si hay campo.\n"
    "- Aplica filtros (precio, año…) con los controles que veas; si no hay, refleja lo que se pueda.\n"
    "- MANTÉN EL FOCO: cuando estés en la página de RESULTADOS (la rejilla con VARIOS anuncios/miniaturas), NO "
    "entres en fichas individuales una por una — el sistema extrae la LISTA por ti. Aplica los filtros que pidan "
    "(precio, año…) SOBRE la rejilla y, en cuanto la rejilla muestre resultados que cumplen lo pedido, llama a "
    "done. NUNCA abras el mismo anuncio repetidamente. NO te vayas a otras secciones no relacionadas.\n"
    "- Cuando el objetivo esté cumplido —o sea claramente imposible— llama a done con un resumen HONESTO de lo "
    "que se ve en pantalla (no inventes resultados) y success true/false.\n"
    "- Si algo NO se puede resolver por el texto del snapshot (control visual sin nombre, mapa/canvas, un elemento "
    "que no aparece, o un banner que no puedes cerrar por DOM), llama a need_vision: el siguiente turno recibirás "
    "una CAPTURA y actuarás por coordenadas. Úsalo cuando de verdad haga falta ver.\n"
    "- INICIO DE SESIÓN: si la página pide iniciar sesión (login) con la cuenta del usuario y el objetivo la "
    "necesita, llama a need_login. NUNCA inventes ni teclees un correo, usuario o contraseña — no los conoces. El "
    "operador iniciará sesión a mano en una ventana real y la tarea se reanudará sola.\n"
    "Sé directo y eficiente: menos pasos es mejor."
)

# VISION (hybrid fallback): when DOM is not enough, the model receives the SCREENSHOT (1280x800 viewport) and acts
# by pixel COORDINATES instead of refs. Same multimodal model; the image is paid only on the step that asks for it.
_VISION_SYSTEM = (
    "Estás en MODO VISIÓN. Recibes una CAPTURA del viewport (1280 de ancho × 800 de alto; origen 0,0 arriba-"
    "izquierda). Mira la imagen y elige UNA acción por COORDENADAS de píxel:\n"
    "- click_at(x, y): clic en ese punto (centro del elemento que quieras pulsar).\n"
    "- type_at(x, y, text, submit): clic en el campo de (x,y), escribe `text`, y pulsa Enter si submit=true.\n"
    "- scroll(dy), navigate(url), press(key), done(summary, success) igual que antes.\n"
    "- need_login: si la pantalla pide iniciar sesión y el objetivo lo requiere. NUNCA teclees credenciales "
    "inventadas — el operador entrará a mano.\n"
    "Da coordenadas dentro de 0..1280 / 0..800. Sé preciso: apunta al centro del elemento."
)

# VISION MODE actions: coordinates, not refs. The backend (owner.agent_act) executes them with human-like mouse.
_VISION_TOOLS = [
    {"type": "function", "function": {"name": "click_at", "description": "Clic en las coordenadas (x,y) de la captura",
        "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "type_at", "description": "Clic en (x,y), escribe texto y opcionalmente Enter",
        "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
            "text": {"type": "string"}, "submit": {"type": "boolean"}}, "required": ["x", "y", "text"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Desplaza la página (dy>0 baja)",
        "parameters": {"type": "object", "properties": {"dy": {"type": "integer"}}, "required": ["dy"]}}},
    {"type": "function", "function": {"name": "navigate", "description": "Ve a una URL o dominio directamente",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "press", "description": "Pulsa una tecla (Enter, Escape, Tab…)",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "done", "description": "Objetivo cumplido o imposible; resume qué se ve",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"},
            "success": {"type": "boolean"}}, "required": ["summary", "success"]}}},
    {"type": "function", "function": {"name": "need_login", "description": "La página exige INICIAR SESIÓN con la cuenta del usuario. NO inventes credenciales: pide que el operador inicie sesión.",
        "parameters": {"type": "object", "properties": {"why": {"type": "string"}}, "required": ["why"]}}},
]


async def run_task(goal: str, owner, plan: str = "", max_steps: int = _MAX_STEPS) -> dict:
    """Hybrid DOM+vision loop. `owner` is the owner.py module (snapshot/capture + action execution).
    `plan` = high-level guide prepared by Hermes (optional, best-effort). Drives the CURRENT page to complete the
    goal; when DOM is not enough, the model asks for `need_vision` and the next step acts on the SCREENSHOT.
    Returns {ok, success, summary, steps}. Never raises; degrades to {ok:False}."""
    if not available():
        return {"ok": False, "summary": "El automatizador no tiene clave de modelo configurada (AIMLAPI_KEY)."}
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "summary": "objetivo vacío"}
    owner._emit("task_start", goal + (f" · plan: {plan[:80]}" if plan else ""))
    # Minimal history (short window): system + initial state. Re-inject fresh snapshot each turn.
    messages = [{"role": "system", "content": _SYSTEM}]
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
            # CONTINUITY (2026-07-12): reread the goal in case the operator clarified it mid-task. Continue in the
            # SAME tab searching for what they really want, without opening another.
            if _tid:
                try:
                    from . import tasks as _tasks
                    _cur = (_tasks.get(_tid) or {}).get("goal") or ""
                    if _cur.strip() and _cur.strip() != goal:
                        goal = _cur.strip()
                        owner._emit("task_refine", f"goal updated by operator: {goal[:100]}")
                except Exception:
                    pass
            state = await owner.snapshot_for_agent()          # {"url","title","elements": "..."}
            # LOGIN WALL (deterministic, BEFORE letting the model act): if the page IS a sign-in screen, do not type
            # and do not escalate to vision. Stop and return needs_login, so the loop NEVER invents email/password
            # (2026-07-10 bug) and the owner opens the real window for the operator. The session stays in the
            # persistent profile and the task resumes automatically after login.
            if _looks_like_login(state["url"], state["elements"]):
                site = _login_site(state["url"])
                owner._emit("task_need_login", f"login requerido en {site}")
                return {"ok": True, "success": False, "needs_login": True, "site": site,
                        "login_url": state["url"], "steps": steps,
                        "summary": f"«{site}» pide iniciar sesión; te abro la ventana para que entres con tu cuenta."}
            # ANTI-STUCK (seen in Wallapop: identical clicks on ref 23 without progress). Two stuck signals:
            # (a) page does not change after the step (no_progress), (b) model REPEATS the same action (same_sig,
            # updated at the end of the previous step). On either signal, force VISION instead of continuing with
            # DOM: look at the screenshot and act by coordinates, which unsticks cookie overlays, unfocused fields,
            # and search boxes that must be typed into rather than clicked. Only give up honestly if even vision
            # keeps failing to advance.
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
                if hard >= 2 and not strong_mode and _model_strong():
                    strong_mode = True
                    owner._emit("task_upgrade", f"bottleneck -> advanced model ({_model_strong()})")
            if pending_vision:
                # VISION MODE: attach screenshot and offer coordinate actions; image is paid only here.
                img = await owner.screenshot_b64()
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": (f"OBJETIVO: {goal}\nURL: {state['url']} · {state['title']}\n"
                                              f"{_VISION_SYSTEM}")},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
                ]})
                action, args = await _next_action(messages, _VISION_TOOLS, strong=strong_mode)
                pending_vision = False
            else:
                user = (f"OBJETIVO: {goal}\n\nURL: {state['url']}\nTítulo: {state['title']}\n\n"
                        f"ELEMENTOS INTERACTIVOS:\n{state['elements'] or '(ninguno visible)'}")
                messages.append({"role": "user", "content": user})
                action, args = await _next_action(messages, _TOOLS, strong=strong_mode)
            if action is None:
                steps.append("(el modelo no emitió acción)")
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
                site = _login_site(state["url"])
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


def _meter(resp, model: str) -> None:
    """Report to Energy the cost of one call in this loop. This agent makes the most calls in the whole system: one
    per navigation step, and one task can take dozens. It was the only LLM client that reported nothing: the browser
    is free, the model driving it is not. Best-effort: metering must never bring down a running task."""
    try:
        from nucleo import energy_meter as _energy
        u = getattr(resp, "usage", None)
        _energy.report_llm_usage(
            base_url=_base_url(), model=model,
            prompt_tokens=getattr(u, "prompt_tokens", None),
            completion_tokens=getattr(u, "completion_tokens", None),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"navegador agent: metering failed (non-fatal): {e}")


async def _next_action(messages: list[dict], tools: list[dict], strong: bool = False) -> tuple[str | None, dict]:
    """One model call -> one action (function call). Bounded message window to avoid growth.
    `tools` = _TOOLS (DOM, by refs) or _VISION_TOOLS (vision, by coordinates). `strong`=True uses the ADVANCED model
    (third anti-stuck rung) if configured; if the advanced model fails (invalid id/provider), fall back to cheap."""
    head = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    trimmed = head + rest[-10:]
    model = _model_strong() if (strong and _model_strong()) else _model()

    async def _call(mdl):
        r = await _c().chat.completions.create(
            model=mdl, messages=trimmed, tools=tools, tool_choice="required", max_tokens=400, temperature=0)
        _meter(r, mdl)                                      # actual model for this call, not the requested one
        return r
    try:
        resp = await _call(model)
    except Exception as e:
        if model != _model():                              # advanced failed -> degrade to cheap for this step
            logger.warning(f"advanced model ({model}) failed: {e}; using cheap model")
            resp = await _call(_model())
        else:
            raise
    choice = resp.choices[0].message
    for tc in (choice.tool_calls or []):
        try:
            return tc.function.name, json.loads(tc.function.arguments or "{}")
        except Exception:
            return tc.function.name, {}
    return None, {}


async def summarize_results(goal: str, items: list) -> dict | None:
    """Filter by relevance + choose best items + conclusion. A capable judge model (default DeepSeek) reviews each
    listing against the goal and its EXACT CATEGORY: discard non-matches with a reason, and only among matching
    items choose the best. `items` = [{title,price,url,image}]. Returns {conclusion, items:[best matches],
    discarded:[{title,reason}]} or None. Fail-open: no model/errors -> do not filter, return first items, never
    break the task."""
    items = [it for it in (items or []) if it.get("title") or it.get("price")]
    if not items:
        return None
    if not available():
        return {"conclusion": f"{len(items)} resultados encontrados.", "items": items[:3], "discarded": []}
    lst = "\n".join(f"{i}. {it.get('title', '')[:80]} — {it.get('price', '') or '¿precio?'}"
                    for i, it in enumerate(items[:24]))
    prompt = (
        f"OBJETIVO DEL USUARIO (respétalo al pie de la letra): {goal}\n\n"
        f"ANUNCIOS ENCONTRADOS (índice. título — precio):\n{lst}\n\n"
        "Tarea EN DOS PASOS:\n"
        "1) FILTRA por RELEVANCIA. Para CADA anuncio decide si CASA con el objetivo, mirando su CATEGORÍA EXACTA: "
        "las categorías son EXCLUYENTES (una moto de ENDURO no es de trial, ni de cross, ni de carretera/naked; un "
        "piso no es un local; etc.) y también deben cumplir precio/zona/estado si se pidieron. DESCARTA sin piedad "
        "lo que no casa, aunque el buscador lo devolviera.\n"
        "2) Entre los que SÍ casan, elige los MEJORES (máx 3) por relación calidad/precio y encaje.\n"
        "Responde SOLO JSON: {\"keep\":[índices que CASAN], \"best\":[índices de los mejores, subconjunto de keep, "
        "en orden], \"discarded\":[{\"i\":índice, \"reason\":\"por qué no casa, muy breve\"}], "
        "\"conclusion\":\"1-2 frases para el usuario sobre lo que SÍ encaja\"}")
    try:
        resp = await _c().chat.completions.create(
            model=_judge_model(), messages=[{"role": "user", "content": prompt}], max_tokens=600, temperature=0)
        _meter(resp, _judge_model())
        txt = (resp.choices[0].message.content or "").strip()
        txt = txt[txt.find("{"):txt.rfind("}") + 1] if "{" in txt else txt
        data = json.loads(txt)
        keep = [i for i in (data.get("keep") or []) if isinstance(i, int) and 0 <= i < len(items)]
        best = [i for i in (data.get("best") or []) if isinstance(i, int) and i in keep][:5]
        chosen = [items[i] for i in best] or ([items[i] for i in keep[:3]] if keep else items[:3])
        discarded = []
        for d in (data.get("discarded") or []):
            try:
                di = d.get("i")
                if isinstance(di, int) and 0 <= di < len(items):
                    discarded.append({"title": (items[di].get("title") or "")[:70],
                                      "reason": str(d.get("reason") or "")[:80]})
            except Exception:
                continue
        return {"conclusion": str(data.get("conclusion") or "").strip() or f"{len(chosen)} resultados que encajan.",
                "items": chosen, "discarded": discarded}
    except Exception as e:
        logger.warning(f"summarize_results: {e}")
        return {"conclusion": f"{len(items)} resultados encontrados.", "items": items[:3], "discarded": []}


def describe() -> str:
    return f"{_model()} @ {_base_url()}"
