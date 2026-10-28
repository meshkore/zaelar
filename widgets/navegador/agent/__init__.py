#
# agent: browser AUTOMATOR — a goal-driven, DOM-first loop driving the owner's Chromium to a natural-language goal.
#   - DOM-first: each step gets a TEXT SNAPSHOT of the interactive elements (`[7] textbox "Search"`) and picks the
#     NEXT action by function-calling (click/type/scroll/navigate/press/done). Text tokens only.
#   - HUMAN behaviour lives in the Playwright layer (owner.py) at no token cost: mouse curve, delays, jittered typing.
#   - VISION on demand: `need_vision` attaches ONE screenshot to the next step, so the image is paid only there.
# Brain = a DEDICATED model (DeepSeek V4 Pro direct by default, env NAVEGADOR_AGENT_*), not the Hermes agent:
# governance already escalates the DECISION to automate; the loop is mechanical and must not hold the voice turn.
#
import json
import os
import re
from urllib.parse import urlsplit

from loguru import logger

# The model name TRAVELS WITH ITS ENDPOINT: the broker prefixes it (`deepseek/deepseek-v4-pro`), the native API does
# not — changing one without the other is a 400 on every step. Vision on this default is NOT verified: if a run
# stalls on `need_vision`, the escape hatch is `NAVEGADOR_AGENT_MODEL_STRONG` with a vision-capable id.
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"
_MAX_STEPS = int(os.environ.get("NAVEGADOR_AGENT_MAX_STEPS", "16"))

# LOGIN WALL: detected deterministically so credentials are never invented. On a login screen the loop types nothing
# and returns needs_login; the owner opens the REAL window for the operator (the session persists in the profile).
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
    """Model that judges the relevance of extracted listings, exact category included (off the hot path: judgement
    over latency). Default `deepseek-v4-flash` on the loop's endpoint — the DIRECT DeepSeek API, hence the UNPREFIXED
    name (`deepseek/` is the broker's catalog and 400s here). `NAVEGADOR_JUDGE_MODEL` overrides."""
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

# The loop lives in `run.py`, one model call (its client, lease and meter) in `step.py`; both read this module's names through it.
from widgets.navegador.agent.run import (  # noqa: E402,F401 — re-export
    run_task, _reread_the_goal, _ask_the_model)
from widgets.navegador.agent.step import (  # noqa: E402,F401 — re-export
    _c, _meter, _next_action, summarize_results, describe)
