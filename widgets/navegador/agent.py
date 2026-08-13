#
# agent.py — el AUTOMATIZADOR del navegador (INI-016, Milestone 2): un bucle goal-driven DOM-first que conduce
# el Chromium del owner para cumplir un objetivo en lenguaje natural ("busca en Wallapop motos de menos de 5000€
# del 2020 en adelante"). Enfoque HÍBRIDO decidido con el operador 2026-07-08:
#
#   • DOM-primero (barato): cada paso le pasa al modelo un SNAPSHOT DE TEXTO de los elementos interactivos de la
#     página (árbol de accesibilidad → `[7] textbox "¿Qué buscas?"`), no una captura. El modelo elige la SIGUIENTE
#     acción por function-calling (click/type/scroll/navigate/press/done). Solo tokens de texto → céntimos/tarea.
#   • Comportamiento HUMANO en la capa Playwright (owner.py), GRATIS (sin tokens): curva de ratón + delays +
#     tecleo con jitter. Siempre activo — es lo que hace que las webs "vayan bien" sin pagar por ello.
#   • VISIÓN solo bajo demanda: si el modelo no puede resolver por DOM, pide `need_vision` y el paso adjunta UNA
#     captura (caro) — se paga la imagen solo en ese paso. (Fase de visión: stub en M2, se completa en M3.)
#
# Cerebro = MODELO BARATO DEDICADO por el MISMO enrutado que el duo (AIMLAPI, UA-spoof anti-Cloudflare), por
# defecto `anthropic/claude-haiku-4.5`. Configurable por env (NAVEGADOR_AGENT_*). NO usa el agente Hermes: la
# gobernanza ya escala a Hermes la DECISIÓN de automatizar (acción `automate` = safe:false); el bucle en sí es
# mecánico y barato, no debe ocupar el turno ACP de la voz.
#
import json
import os
import re
from urllib.parse import urlsplit

from loguru import logger
from openai import AsyncOpenAI

DEFAULT_BASE_URL = "https://api.aimlapi.com/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"   # en la lista de flash permitidos de AIMLAPI (CLAUDE.md routing)
_MAX_STEPS = int(os.environ.get("NAVEGADOR_AGENT_MAX_STEPS", "16"))

# MURO DE LOGIN: detección DETERMINISTA para NO inventar jamás credenciales (bug del 2026-07-10: ante el login de
# Google el bucle tecleó un correo falso y giró en círculos). Cuando la página ES una pantalla de inicio de sesión,
# el bucle NO teclea nada: para y devuelve needs_login → el owner abre la ventana REAL para que el operador entre a
# mano (la sesión queda en el perfil persistente). Patrones de URL de login conocidos + señal DOM (campo password).
_LOGIN_URL_RE = re.compile(
    r"(accounts\.google\.[^/]+/.*(signin|login)|/login(\b|[/?])|/signin(\b|[/?])|/sign-in(\b|[/?])|"
    r"/auth/(login|signin)|/sso/|/session/new|/uas/login|/checkpoint/|login\.(microsoftonline|yahoo|live)\.com|"
    r"appleid\.apple\.com|/oauth/authorize|wallapop\.[^/]+/login)", re.I)
_LOGIN_DOM_RE = re.compile(r'(type="password"|"password"|contrase[nñ]a|\biniciar sesi[oó]n\b|\bsign in\b|\blog ?in\b)',
                           re.I)


def _login_site(url: str) -> str:
    """Nombre legible del sitio de login (host sin www) para pedirle al operador que inicie sesión ahí."""
    try:
        host = (urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host or url
    except Exception:
        return url or "el sitio"


def _looks_like_login(url: str, elements: str) -> bool:
    """True si la página ACTUAL es un muro de inicio de sesión. URL conocida de login (fiable) O un campo de
    contraseña en el snapshot acompañado de la jerga de login. Un simple botón «Iniciar sesión» en una portada NO
    basta (no hay campo password) → no dispara falsos positivos en home de YouTube/Wallapop."""
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
    """Modelo que JUZGA la relevancia de los anuncios extraídos (¿este anuncio casa con lo pedido, categoría
    EXACTA incluida?). Off-hot-path → prioriza CRITERIO sobre latencia: un modelo capaz distingue enduro de trial/
    carretera. Default `deepseek/deepseek-v4-flash` (barato y buen razonador, vía AIMLAPI, mismo endpoint). Ajustable
    con `NAVEGADOR_JUDGE_MODEL`."""
    return os.getenv("NAVEGADOR_JUDGE_MODEL", "deepseek/deepseek-v4-flash").strip() or _model()


def _model_strong() -> str:
    """Modelo AVANZADO opcional — se usa SOLO para desatascar cuellos de botella que el barato no supera (tercer
    escalón: barato-DOM → visión → modelo avanzado). Configurable por el store (`navegador_agent_model_strong`,
    lo escribe la UI) o env `NAVEGADOR_AGENT_MODEL_STRONG`. Vacío = sin escalado (se sigue con el barato). Va por el
    MISMO endpoint/clave (`NAVEGADOR_AGENT_BASE_URL`/AIMLAPI) — pon un id que sirva ese proveedor (p.ej.
    `anthropic/claude-sonnet-4.5`). Coste controlado: solo se paga en los pasos difíciles."""
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
    # Igual que fast_client: una clave explícita gana; si no, la del proveedor según la base URL.
    if os.getenv("NAVEGADOR_AGENT_API_KEY"):
        return os.getenv("NAVEGADOR_AGENT_API_KEY")
    u = _base_url().lower()
    if "aimlapi" in u:
        return os.getenv("AIMLAPI_KEY", "")
    if "googleapis" in u or "generativelanguage" in u:
        return os.getenv("GEMINI_API_KEY", "")
    if "11434" in u or "localhost" in u or "127.0.0.1" in u:
        return "ollama"
    return os.getenv("AIMLAPI_KEY", "") or os.getenv("OPENAI_API_KEY", "")


def available() -> bool:
    return bool(_api_key())


_client: AsyncOpenAI | None = None


def _c() -> AsyncOpenAI:
    global _client
    if _client is None:
        key = _api_key()
        if not key:
            raise RuntimeError("no NAVEGADOR_AGENT_API_KEY/AIMLAPI_KEY para el automatizador del navegador")
        # EGRESS (T304). Este agente es el que más llamadas hace del sistema — una por paso de
        # navegación — así que es también el que más clave necesitaba tener a mano. Ya no.
        from nucleo import llm_egress
        base, key, extra = llm_egress.route(_base_url(), key)
        if not key:
            raise RuntimeError("sin credencial para el automatizador del navegador")
        headers = dict(extra)
        # El UA de navegador es para el Cloudflare que hay delante de AIMLAPI. Con salida mediada quien
        # habla con AIMLAPI es el otro extremo, así que aquí sobra.
        if not extra and "aimlapi" in base.lower():
            headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        _client = AsyncOpenAI(api_key=key, base_url=base, default_headers=headers or None)
    return _client


# Vocabulario de acciones que el modelo puede emitir (function-calling — fiable y agnóstico del idioma, igual que
# la escalada del duo). El backend resuelve la ref contra el snapshot del MISMO paso.
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

# VISIÓN (fallback del híbrido): cuando el DOM no basta, el modelo recibe la CAPTURA (viewport 1280×800) y actúa
# por COORDENADAS de píxel en vez de refs. Mismo modelo (multimodal); solo se paga la imagen en el paso que lo pida.
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

# Acciones del MODO VISIÓN — por coordenadas (no refs). El backend (owner.agent_act) las ejecuta con ratón humano.
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
    """Bucle HÍBRIDO DOM+visión. `owner` es el módulo owner.py (snapshot/captura + ejecución de acciones).
    `plan` = guía de alto nivel que Hermes preparó (opcional, best-effort). Conduce la página ACTUAL para cumplir
    el objetivo; cuando el DOM no basta, el modelo pide `need_vision` y el siguiente paso actúa sobre la CAPTURA.
    Devuelve {ok, success, summary, steps}. Nunca lanza — degrada a {ok:False}."""
    if not available():
        return {"ok": False, "summary": "El automatizador no tiene clave de modelo configurada (AIMLAPI_KEY)."}
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "summary": "objetivo vacío"}
    owner._emit("task_start", goal + (f" · plan: {plan[:80]}" if plan else ""))
    # Historial mínimo (ventana corta): system + estado inicial. Reinyectamos el snapshot fresco cada turno.
    messages = [{"role": "system", "content": _SYSTEM}]
    if plan:
        messages.append({"role": "system", "content":
            "PLAN sugerido por el cerebro profundo (guíate por él, adáptalo a lo que veas en la página):\n" + plan})
    steps: list[str] = []
    pending_vision = False          # el paso anterior pidió VISIÓN → este paso va con captura + tools de coordenadas
    last_fp = None                  # huella de la página (url+título+elementos) para detectar "no pasó nada"
    no_progress = 0                 # pasos seguidos SIN que la página cambie → el loop está atascado
    last_sig = None                 # firma de la última acción (para cortar el bucle "misma acción una y otra vez")
    same_sig = 0
    hard = 0                        # nº de atascos → al 2º, si hay modelo AVANZADO, se sube a él (3er escalón)
    strong_mode = False
    _tid = getattr(owner, "task_id", "") or ""
    try:
        for i in range(max_steps):
            # CONTINUIDAD (2026-07-12): re-lee el objetivo por si el operador lo ACLARÓ a mitad de la tarea
            # ("no, de enduro") → seguimos en la MISMA pestaña buscando lo que quiere de verdad, sin abrir otra.
            if _tid:
                try:
                    from . import tasks as _tasks
                    _cur = (_tasks.get(_tid) or {}).get("goal") or ""
                    if _cur.strip() and _cur.strip() != goal:
                        goal = _cur.strip()
                        owner._emit("task_refine", f"objetivo actualizado por el operador: {goal[:100]}")
                except Exception:
                    pass
            state = await owner.snapshot_for_agent()          # {"url","title","elements": "..."}
            # MURO DE LOGIN (determinista, ANTES de dejar que el modelo actúe): si la página ES una pantalla de
            # inicio de sesión, no la tecleamos NI escalamos a visión — paramos y devolvemos needs_login. Así el
            # bucle NUNCA inventa un correo/contraseña (bug 2026-07-10) y el owner abre la ventana real para el
            # operador. La sesión queda en el perfil persistente y la tarea se reanuda sola tras el login.
            if _looks_like_login(state["url"], state["elements"]):
                site = _login_site(state["url"])
                owner._emit("task_need_login", f"login requerido en {site}")
                return {"ok": True, "success": False, "needs_login": True, "site": site,
                        "login_url": state["url"], "steps": steps,
                        "summary": f"«{site}» pide iniciar sesión; te abro la ventana para que entres con tu cuenta."}
            # ANTI-ATASCO (visto en Wallapop: clics idénticos a ref 23 sin avanzar): dos señales de atasco →
            # (a) la página no cambia tras el paso (no_progress), (b) el modelo REPITE la misma acción (same_sig,
            # actualizado al final del paso anterior). Ante cualquiera de las dos, en vez de seguir con el DOM se
            # fuerza VISIÓN (mira la captura, actúa por coordenadas — desatasca overlays de cookies, campos que no
            # enfocan, el buscador que hay que TECLEAR y no clicar). Solo si incluso en visión sigue sin avanzar
            # se abandona honesto (no_progress alto o repetición terca).
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
                owner._emit("task_stuck", f"atasco (no_progress={no_progress}, repite={same_sig}) → VISIÓN")
                pending_vision = True
                same_sig = 0                                  # dale una oportunidad limpia a la visión
                hard += 1
                # TERCER ESCALÓN: si seguimos atascados y hay modelo AVANZADO configurado, súbete a él (solo en los
                # pasos difíciles → coste controlado). Desatasca cuellos que el barato no supera.
                if hard >= 2 and not strong_mode and _model_strong():
                    strong_mode = True
                    owner._emit("task_upgrade", f"cuello de botella → modelo avanzado ({_model_strong()})")
            if pending_vision:
                # MODO VISIÓN: adjunta la captura y ofrece acciones por coordenadas (se paga la imagen solo aquí).
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
                # no consume un "paso real"; el próximo turno actúa con la captura. Evita bucle infinito: si pide
                # visión dos veces seguidas sin actuar, el contador del for igual avanza (i sube), así que acota.
                continue
            if action == "need_login":
                # El modelo detectó un login que el chequeo determinista no cazó (URL rara). Mismo desenlace:
                # paramos, sin teclear credenciales, y devolvemos needs_login para que el owner abra la ventana real.
                site = _login_site(state["url"])
                owner._emit("task_need_login", f"login requerido en {site}: {args.get('why', '')}"[:160])
                steps.append("need_login")
                return {"ok": True, "success": False, "needs_login": True, "site": site,
                        "login_url": state["url"], "steps": steps,
                        "summary": f"«{site}» pide iniciar sesión; te abro la ventana para que entres con tu cuenta."}
            sig = (action, json.dumps(args, sort_keys=True, ensure_ascii=False))
            same_sig = same_sig + 1 if sig == last_sig else 0
            last_sig = sig
            if same_sig >= 4:                                 # repite idéntico incluso tras pasar a visión → corta
                owner._emit("task_giveup", f"acción repetida sin efecto: {action}")
                return {"ok": True, "success": False, "steps": steps,
                        "summary": "Me quedé repitiendo la misma acción sin efecto; lo dejo en el estado actual."}
            owner._emit("task_step", f"{i+1}: {action} {json.dumps(args, ensure_ascii=False)[:120]}")
            steps.append(f"{action}({', '.join(f'{k}={v}' for k, v in args.items())})")
            if action == "done":
                owner._emit("task_done", args.get("summary", "")[:160])
                return {"ok": True, "success": bool(args.get("success")),
                        "summary": args.get("summary", "hecho"), "steps": steps}
            ok, note = await owner.agent_act(action, args)    # ejecuta con comportamiento humano
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
    """Reporta a Energy lo que costó UNA llamada de este bucle. Este agente es el que más llamadas
    hace de todo el sistema —una por paso de navegación, y una tarea son decenas— y era el ÚNICO
    cliente de LLM que no reportaba nada: el navegador es gratis, el modelo que lo conduce no.
    Best-effort: medir jamás puede tumbar una tarea que ya está en marcha."""
    try:
        from nucleo import energy_meter as _energy
        u = getattr(resp, "usage", None)
        _energy.report_llm_usage(
            base_url=_base_url(), model=model,
            prompt_tokens=getattr(u, "prompt_tokens", None),
            completion_tokens=getattr(u, "completion_tokens", None),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"navegador agent: metering falló (no fatal): {e}")


async def _next_action(messages: list[dict], tools: list[dict], strong: bool = False) -> tuple[str | None, dict]:
    """Una llamada al modelo → una acción (function call). Ventana de mensajes acotada para no crecer.
    `tools` = _TOOLS (DOM, por refs) o _VISION_TOOLS (visión, por coordenadas). `strong`=True usa el modelo AVANZADO
    (tercer escalón anti-atasco) si está configurado; si el avanzado falla (id inválido/proveedor), cae al barato."""
    head = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    trimmed = head + rest[-10:]
    model = _model_strong() if (strong and _model_strong()) else _model()

    async def _call(mdl):
        r = await _c().chat.completions.create(
            model=mdl, messages=trimmed, tools=tools, tool_choice="required", max_tokens=400, temperature=0)
        _meter(r, mdl)                                      # el modelo REAL de esta llamada, no el pedido
        return r
    try:
        resp = await _call(model)
    except Exception as e:
        if model != _model():                              # el avanzado falló → degrada al barato ese paso
            logger.warning(f"modelo avanzado ({model}) falló: {e}; uso el barato")
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
    """FILTRA por relevancia + elige los mejores + conclusión. Un modelo CAPAZ (juez, def DeepSeek) revisa cada
    anuncio contra el objetivo y su CATEGORÍA EXACTA: DESCARTA los que no casan (p.ej. una moto de trial/carretera
    cuando se pidió ENDURO) con su razón, y solo entre los que SÍ casan elige los mejores. `items` =
    [{title,price,url,image}]. Devuelve {conclusion, items:[mejores que CASAN], discarded:[{title,reason}]} o None.
    Fail-open: sin modelo/errores → no filtra (devuelve los primeros), nunca revienta la tarea."""
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
