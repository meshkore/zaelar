#
# agent.py: browser AUTOMATOR (Milestone 2): a goal-driven, DOM-first loop that drives the owner's
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
# Brain = DEDICATED model, DeepSeek V4 Pro DIRECT by default (operator's norm, 2026-08-19: DeepSeek V4 Pro and
# nothing else). Configurable by env (NAVEGADOR_AGENT_*). Does NOT use the Hermes agent: governance
# already escalates the DECISION to automate to Hermes (`automate` action = safe:false); the loop itself is
# mechanical and cheap, and should not occupy the voice ACP turn.
#
import json
import os
import re
from urllib.parse import urlsplit

from loguru import logger
from openai import AsyncOpenAI

# ⚠️ 2026-08-19 — operator's norm: DeepSeek V4 Pro DIRECT, no other provider. The model name TRAVELS WITH ITS
# ENDPOINT: the broker prefixes it (`deepseek/deepseek-v4-pro`) and the native API does not, so changing one
# without the other buys a 400 on every step.
#
# KNOWN, WRITTEN LIMIT rather than a silent regression: the loop is DOM-FIRST (text snapshots of the
# accessibility tree), which is what almost every step uses and is plain text — that path is unaffected. The
# `need_vision` step attaches a screenshot as an `image_url` content part, and VISION on this default is NOT
# verified. If a run stalls asking for vision, that is where to look; the escape hatch is
# `NAVEGADOR_AGENT_MODEL_STRONG` with a vision-capable id on the same endpoint, which is exactly the third rung
# this loop already has for "the cheap model cannot pass this".
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"
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
    judgment over latency: a capable model distinguishes enduro from trial/road. Default `deepseek-v4-flash`
    (cheap and good at reasoning) on the SAME endpoint as the loop, which since 2026-08-19 is the DIRECT DeepSeek
    API — hence the UNPREFIXED name; the `deepseek/` prefix is the broker's catalog and 400s here. Adjustable with
    `NAVEGADOR_JUDGE_MODEL`."""
    return os.getenv("NAVEGADOR_JUDGE_MODEL", "deepseek-v4-flash").strip() or _model()


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
    # Asked on EVERY step, not only when the client is built: the client is cached for the life of the process,
    # so the egress gate in `llm_egress.route` below would otherwise see the first call and none of the rest.
    from nucleo import energy_lease, llm_egress
    if not llm_egress.is_local_endpoint(_base_url()):
        energy_lease.admit("llm")
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

# refactor2710-12 — the loop lives in `run.py`, one model call in `step.py`; both read this module's names through it.
from widgets.navegador.agent.run import (  # noqa: E402,F401 — re-export
    run_task,
    _reread_the_goal,
    _ask_the_model,
    _meter,
)
from widgets.navegador.agent.step import (  # noqa: E402,F401 — re-export
    _next_action,
    summarize_results,
    describe,
)
