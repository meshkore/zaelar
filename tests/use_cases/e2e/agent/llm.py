"""Re-exports the voice tester's LLM client (tests/voice/e2e/agent/llm.py) — same DeepSeek/AIMLAPI +
GLM/Z.AI clients, same credentials, no reason to duplicate the HTTP/parsing code. This module exists only
so `from . import config, llm` reads the same way across every module in this package.

`call` gets one retry on top of the original: AIMLAPI sits behind Cloudflare and blips intermittently
(documented elsewhere in this codebase) — for an unattended run, one transient network error should not
waste the whole scenario's turns and cost so far. `glm_call`/`parse_json` are unchanged passthroughs.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from . import config
from tests.voice.e2e.agent.llm import call as _call
from tests.voice.e2e.agent.llm import glm_call, parse_json
from tests.voice.e2e.agent.llm import judge_call as _voice_judge_call


def _as_text(content) -> str:
    """Flatten a reply whose `content` came back as a LIST of parts instead of a string.

    Cost a real scenario (`buy-known-product__es`, 2026-08-18): the broker returned OpenAI's structured
    content form — `[{"type": "text", "text": "..."}]` — and `driver.py`'s `.strip()` on it raised
    `'list' object has no attribute 'strip'`, killing the scenario mid-run. Both shapes are legal in that API
    and which one arrives is the provider's choice, not ours, so the caller cannot be the place that knows.
    Non-text parts are dropped rather than stringified: a `str(dict)` of an image part inside the tester's next
    utterance would be worse than saying nothing.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text") or "" for part in content
            if isinstance(part, dict) and (part.get("type") in (None, "text") or "text" in part))
    return "" if content is None else str(content)


# ── Cadena de proveedores del DRIVE (norma del operador, 2026-08-19) ──────────────────────────────────────
# ORDEN: DeepSeek V4 DIRECTO → broker AIMLAPI → Z.AI/GLM. CERO modelos de OpenAI (norma del operador).
#
# Los dos escalones existen por hechos medidos, no por precaución: el 2026-08-19 a las 02:34 la cuenta de
# AIMLAPI devolvió 403 «You've run out of funds» (verificado contra el cuerpo de la respuesta, con la clave del
# arnés Y la del motor) y el DRIVE —el que hace de persona— murió con él: INFRA con 0 turnos, dos veces
# seguidas, sin un solo caso medible. Y el titular es el directo porque es ~30% más barato que el mismo modelo
# por el broker y porque el broker ACEPTA `thinking:disabled` y razona igual (TTFT p50 4,24 s vs 1,01 s).
#
# El escalón que sirvió se ESTAMPA en la medida (`drive_model` → ledger + ronda de la iniciativa). Un relevo
# cambia el INSTRUMENTO: la fila deja de ser comparable con las anteriores, y en el caso de Z.AI el DRIVE
# pasaría a compartir proveedor con el JUEZ, que existe en otro proveedor precisamente para ser independiente.
# Un relevo SILENCIOSO dejaría el tablero avanzando con dos instrumentos y sin saber qué fila usó cuál.
# ── Escalón de LICENCIA: el CLI de Claude Code con la licencia local ──────────────────────────────────────
# Es el ÚLTIMO escalón del tester, y existe por una razón que los otros dos no pueden dar: es de SUSCRIPCIÓN,
# así que no puede caerse por saldo ni por cuota. El 2026-08-21 se perdieron horas de paseo con los dos
# escalones de pago fuera a la vez (Z.AI sin cuota hasta el 25, y una caída de red que dejó al directo en
# `Connection error`), y una ronda sin escalón no es un fallo del producto: es una factura, y el arnés la
# apunta como INFRA. Con este escalón la corrida DEGRADA en vez de morir.
#
# Va el último y no el primero por dos motivos, ninguno de calidad del modelo: consume la licencia del
# operador (norma del 2026-08-02: forfait, nunca pago por token, y SOLO en local), y es más lento —medido,
# ~7 s para un turno trivial— porque levanta un proceso por llamada. Como cualquier relevo, SELLA la ronda:
# `drive_model()` devuelve `licencia-claude` y la fila deja de ser comparable con las de DeepSeek.
#
# Esto NO toca a los Brain Workers: el producto se mide con la cadena que el producto usa (DeepSeek/GLM, que
# es lo único que hay en la nube). Aquí solo se cambia QUIÉN hace de persona y QUIÉN puntúa — el instrumento.
def _claude_licence(messages: list[dict], max_tokens: int = 4000, model: str = "") -> str:
    """Un turno por el CLI de Claude Code, con la licencia con la que el operador ya está logueado.

    Tres cuidados, y los tres son trampas reales de este repo, no precaución:

    1. **El entorno se limpia.** `ANTHROPIC_BASE_URL`/`_AUTH_TOKEN`/`_API_KEY` son justo las variables con las
       que el motor redirige este mismo CLI a Z.AI o DeepSeek. Heredarlas aquí haría que el «escalón de
       Anthropic» fuese en realidad el escalón que se acaba de caer — el relevo se anunciaría en el sello y no
       habría relevado nada.
    2. **Se ejecuta desde un directorio NEUTRO.** El CLI carga el `CLAUDE.md` del cwd; desde `engine/` cada
       turno del conductor arrastraría el contexto del repo entero (V2-117 midió esa bomba: 167k → 25k tokens).
       Además de caro, un conductor que ha leído el código del motor deja de hacer de PERSONA.
    3. **Sin MCP y con nuestro system prompt.** `--strict-mcp-config` sin `--mcp-config` deja el proceso sin un
       solo servidor MCP, y `--system-prompt` sustituye al del agente de código: aquí no queremos un agente
       que edite ficheros, queremos un modelo que conteste una frase.
    """
    import subprocess
    import tempfile
    sys_parts = [m.get("content") or "" for m in messages if m.get("role") == "system"]
    convo = []
    for m in messages:
        if m.get("role") == "system":
            continue
        who = "ASISTENTE" if m.get("role") == "assistant" else "USUARIO"
        convo.append(f"{who}: {_as_text(m.get('content'))}")
    prompt = "\n\n".join(convo) or "(sin contenido)"
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
    model = model or (os.environ.get("USE_CASES_LICENCE_MODEL") or "").strip() or "sonnet"
    argv = ["claude", "-p", prompt, "--model", model,
            "--output-format", "text", "--strict-mcp-config"]
    if sys_parts:
        argv += ["--system-prompt", "\n\n".join(sys_parts)]
    with tempfile.TemporaryDirectory() as neutral:
        out = subprocess.run(argv, cwd=neutral, env=env, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"licencia-claude rc={out.returncode}: {(out.stderr or out.stdout)[:200]}")
    return out.stdout.strip()


_FUNDS = ("run out of funds", "top up your balance", "insufficient", "403")
_used_drive = ""


def drive_model() -> str:
    """Qué escalón condujo la ÚLTIMA llamada de DRIVE. Lo consume `run.py` para sellar la ronda."""
    return _used_drive


def _override() -> str:
    return (os.environ.get("ZAELAR_UC_DRIVE") or "").strip().lower()


def _nonempty(text: str, tier: str) -> str:
    """Una respuesta VACÍA es un fallo del escalón, no una respuesta.

    Sin esto la cadena da por bueno un `""` y el tester le dice NADA al agente: el escenario se degrada y el
    informe lo lee como que el agente se quedó mudo. Un turno vacío del que hace de persona no es medible.
    """
    if not (text or "").strip():
        raise RuntimeError(f"{tier} devolvió una respuesta VACÍA")
    return text


# El endpoint nativo RAZONA por defecto y el razonamiento se cobra contra `max_tokens`: medido, «Di solo OK»
# con `max_tokens=8` gasta los 8 pensando y devuelve `content=''` con `finish_reason=length` — una respuesta
# VACÍA sin ninguna excepción. Con el presupuesto de 200 del driver caben (24-38 tokens de razonamiento en las
# sondas) pero un turno de negociación difícil es justo donde el razonamiento se alarga, o sea que el fallo
# aparecería en el caso más complicado y se leería como que el agente no contestó. NO se apaga el razonamiento
# —es lo que hizo elegir este tier para el DRIVE— se le da techo aparte, que es gratis si no se usa.
_REASONING_RESERVE = 512


def _deepseek_direct(messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
    """DeepSeek nativo (OpenAI-compatible). Nombre de modelo SIN el prefijo del broker — ver `config`."""
    key = config.deepseek_key()
    if not key:
        raise RuntimeError("no DEEPSEEK_API_KEY")
    payload = {"model": config.native_model(model), "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens + _REASONING_RESERVE}
    req = urllib.request.Request(
        config.DEEPSEEK_BASE.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    return _as_text(((data.get("choices") or [{}])[0].get("message") or {}).get("content"))


def call(messages: list[dict], model: str | None = None, temperature: float = 0.0, max_tokens: int = 4000) -> str:
    global _used_drive
    want = _override()
    model = model or config.DRIVE_MODEL

    def _direct() -> str:
        return _deepseek_direct(messages, model, temperature, max_tokens)

    def _broker() -> str:
        return _as_text(_call(messages, model=model, temperature=temperature, max_tokens=max_tokens))

    def _zai() -> str:
        return _as_text(glm_call(messages, max_tokens=max_tokens))

    def _licence() -> str:
        return _claude_licence(messages, max_tokens=max_tokens)

    def _last() -> str:
        # Tercer escalón = Z.AI/GLM, NO un modelo de OpenAI (ver `config.LAST_RESORT_MODEL`). Si algún día se
        # fija un modelo ahí, va por el broker; vacío —el defecto— es Z.AI.
        if config.LAST_RESORT_MODEL:
            return _as_text(_call(messages, model=config.LAST_RESORT_MODEL, temperature=temperature,
                                  max_tokens=max_tokens))
        return _zai()

    # Escotilla manual: fijar UN escalón y no moverse de él (para medir un brazo concreto sin que un fallo
    # lo releve por detrás y contamine la comparación).
    forced = {"direct": ("deepseek-directo", _direct), "deepseek": ("deepseek-directo", _direct),
              "aimlapi": ("aimlapi", _broker), "broker": ("aimlapi", _broker),
              "zai": ("zai/glm", _zai), "glm": ("zai/glm", _zai),
              "claude": ("licencia-claude", _licence), "licencia": ("licencia-claude", _licence)}.get(want)
    if forced:
        _used_drive = forced[0]
        return _nonempty(forced[1](), forced[0])   # forzar un escalón no exime de que la respuesta exista

    chain = [("deepseek-directo", _direct), ("aimlapi", _broker),
             (f"último recurso · {config.LAST_RESORT_MODEL or 'zai/glm'}", _last),
             ("licencia-claude", _licence)]
    errs: list[str] = []
    for i, (name, fn) in enumerate(chain):
        try:
            out = _nonempty(fn(), name)
            _used_drive = name
            return out
        except Exception as e:
            errs.append(f"{name}: {e}")
            # Un reintento en el MISMO escalón antes de bajar: AIMLAPI va tras Cloudflare y blipea, y un blip
            # no debería cambiar el instrumento de medida de la corrida entera.
            if not any(x in str(e).lower() for x in _FUNDS):
                time.sleep(2.0)
                try:
                    out = fn()
                    _used_drive = name
                    return out
                except Exception as e2:
                    errs[-1] += f" | reintento: {e2}"
            if i == len(chain) - 1:
                raise RuntimeError("DRIVE sin escalón disponible → " + " ;; ".join(errs))
    raise RuntimeError("DRIVE sin escalón disponible")


def judge_call(messages: list[dict], max_tokens: int = 2000, out: dict | None = None) -> tuple[str, str]:
    """El JUEZ, con la licencia local debajo de todo.

    Perder al juez es perder la RONDA ENTERA: la conversación ya se pagó y ya ocurrió, y sin veredicto no
    entra en el marcador. La cadena del arnés de voz (GLM → DeepSeek directo → broker) ya reintenta lo
    transitorio; lo que no cubre es que los tres estén fuera a la vez, que es exactamente lo que pasó el
    2026-08-21 (Z.AI sin cuota hasta el 25 + caída de red del directo).

    Devuelve el modelo que puntuó, como antes, porque una ronda juzgada por otro instrumento tiene que poder
    distinguirse en el tablero: la licencia es un modelo distinto y sus notas no son comparables sin decirlo.
    """
    import sys
    try:
        return _voice_judge_call(messages, max_tokens=max_tokens, out=out)
    except Exception as e:
        print(f"[judge] cadena de pago sin escalón ({str(e)[:100]}) → licencia local de Claude Code",
              file=sys.stderr)
    txt = _claude_licence(messages, max_tokens=max_tokens)
    # La licencia local NO dice si cortó: se apunta «no lo sé» en vez de dejar la lectura de la pata que
    # acaba de fallar. Quien mire esto tiene que poder distinguir «cabía» de «no me consta».
    if out is not None:
        out["finish_reason"], out["cortada"] = "", False
    if not (txt or "").strip():
        raise RuntimeError("licencia-claude devolvió una respuesta VACÍA al JUEZ")
    return (txt, "licencia-claude")


__all__ = ["call", "glm_call", "judge_call", "parse_json", "drive_model"]
