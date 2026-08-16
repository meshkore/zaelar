"""nucleo/flash/fast_client.py — cliente del modelo RÁPIDO no-razonador del FlashBrain (V2-004 · T60).

Puerto propio de `brains/duo/fast_client.py` (que muere con Hermes en V2-009), con la diferencia CLAVE del
cerebro v2:

  - **Modelo POR INVOCACIÓN** (regla dura del proyecto): el modelo/base_url/api_key/provider se pasan en CADA
    `stream()` dentro de un `ModelSpec`, NUNCA se leen de una env global de modelo — así dos sesiones concurrentes
    pueden usar modelos distintos sin pisarse. `spec_from_config()` compone el spec por defecto desde `config/v2`
    (que la UI gestiona), pero el llamador es libre de pasar otro.
  - **NO-razonador**: thinking siempre OFF. Un razonador no cierra el turno a tiempo → la voz se queda muda.
  - Interfaz OpenAI-compatible con **tool-calling real** (escalado y control van por function-calling, no por
    listas de palabras clave — agnóstico del idioma). Streaming de `delta.content` + acumulación de
    `delta.tool_calls`, con `on_tool_call(name, args)` disparado una vez por llamada completa.
  - **Degradación**: `stream()` propaga el error de transporte/proveedor; el provider de voz (`nucleo.py`) lo
    captura y responde una frase de reserva — NUNCA se queda mudo ni habla el error crudo.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from loguru import logger

# UA de navegador: AIMLAPI está tras Cloudflare y 403ea el User-Agent por defecto del SDK OpenAI (403/1010
# intermitente, visto en producción). Se falsea SOLO en el endpoint de AIMLAPI (sin efecto en Ollama/otros).
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_DEFAULT_MAX_TOKENS = 200

# Reintento en TRANSITORIOS (2026-07-25): AIMLAPI va tras Cloudflare y da `Connection error`/403/5xx intermitentes.
# Un blip PUNTUAL en la fase de conexión NO debe tirar el turno (síntoma real: el chat del operador quedaba sin
# respuesta o con "Uf, se me ha ido"). Reintentamos SOLO la fase de conexión (antes del primer token del stream) →
# seguro (no se re-emite nada ya enviado). Configurable `FAST_CONNECT_RETRIES` (def 2 reintentos).
_CONNECT_RETRIES = int(os.getenv("FAST_CONNECT_RETRIES", "2"))
_RETRY_BACKOFF_S = float(os.getenv("FAST_RETRY_BACKOFF_S", "0.4"))


def _is_transient(e: Exception) -> bool:
    """¿El error es un blip transitorio de red/proveedor (merece reintento) y NO un error de la petición (4xx de
    autenticación/cuota/entrada, que reintentar no arregla)?"""
    name = type(e).__name__.lower()
    if any(k in name for k in ("connection", "timeout", "apiconnection", "apitimeout", "internalserver")):
        return True
    s = str(e).lower()
    if any(k in s for k in ("connection error", "timed out", "timeout", "temporarily", "bad gateway",
                            "service unavailable", "502", "503", "504", "cloudflare", "reset by peer")):
        return True
    status = getattr(e, "status_code", None) or getattr(e, "status", None)
    return status in (408, 429, 500, 502, 503, 504)


async def _raise_with_body(resp) -> None:
    """`resp.raise_for_status()`, pero con el CUERPO de la respuesta metido en el mensaje de la excepción. Sin
    esto, un 429 de Z.AI llega como el mensaje genérico de httpx («429 Too Many Requests», sin más) y quien
    clasifica el fallo aguas abajo (`nucleo.flash.provider_chain.classify_failure`, y su hermano de
    `nucleo.workers.providers`) no puede distinguir «cuota SEMANAL agotada, reset el jueves» (hay que relevar) de
    un rate-limit pasajero (se reintenta solo) — los dos dan el MISMO 429 desnudo. No-op si la respuesta es OK.

    ES CORRUTINA: hay que llamarla con AWAIT. Sin await no lanza absolutamente nada —Python solo crea el objeto
    corrutina y lo tira— así que un 429/500 pasaba por bueno y el código seguía con `resp.json()` sobre un cuerpo de
    error, convirtiendo un fallo de proveedor claro en un error de parseo confuso más adelante. Pasó justo aquí, en
    `_complete_zai` (2026-08-09): solo se vio porque Python avisa («coroutine never awaited»)."""
    import httpx
    if resp.status_code < 400:
        return
    try:
        await resp.aread()          # no-op si ya está buffered (Response normal); imprescindible en streaming
        body = (resp.text or "")[:400]
    except Exception:
        body = ""
    err = httpx.HTTPStatusError(f"{resp.status_code} {resp.reason_phrase}" + (f" — {body}" if body else ""),
                                request=resp.request, response=resp)
    err.status_code = resp.status_code   # deja que `_is_transient` lo detecte también por status_code, no solo texto
    raise err


def _keepalive_expiry() -> float:
    """Segundos que el pool HTTP mantiene VIVA una conexión ociosa (FASE 1 cold-start). httpx por defecto la cierra
    a los ~5s → el prewarm no llega al 1er turno. La subimos mucho (def 30 min). Configurable `FAST_HTTP_KEEPALIVE_S`.
    La MISMA cifra alimenta la heurística `cold_estimate` (gap > keepalive ⇒ conexión probablemente fría)."""
    try:
        return float(os.getenv("FAST_HTTP_KEEPALIVE_S", "1800"))
    except Exception:
        return 1800.0


def _http_client():
    """Cliente httpx con keepalive LARGO + pool, para que la conexión TLS prewarmeada sobreviva al 1er turno y
    entre turnos (FASE 1). Best-effort: si httpx no admite la firma, devuelve None → AsyncOpenAI usa su default."""
    try:
        import httpx
        ka = _keepalive_expiry()
        limits = httpx.Limits(max_keepalive_connections=8, max_connections=16, keepalive_expiry=ka)
        return httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(60.0, connect=10.0))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"http_client keepalive setup skipped (usando default httpx): {e}")
        return None


@dataclass(frozen=True)
class ModelSpec:
    """Selección de modelo POR INVOCACIÓN. Nunca una env global de modelo."""
    model: str
    base_url: str | None = None
    api_key: str | None = None
    provider: str = "aimlapi"     # 'ollama' (local) | 'aimlapi' (nube) | …

    def is_local(self) -> bool:
        """True cuando apunta a un endpoint local (Ollama) — sin nube, sin coste por token."""
        if self.provider == "ollama":
            return True
        u = (self.base_url or "").lower()
        return "11434" in u or "localhost" in u or "127.0.0.1" in u

    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.is_local():
            return "http://localhost:11434/v1"
        return "https://api.aimlapi.com/v1"

    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.is_local():
            return "ollama"        # Ollama acepta cualquier no-vacío
        # Nube sin key explícita → credencial DESDE EL ENTORNO (fallback power-user). La KEY es una credencial,
        # no una selección de modelo, así que leerla del env NO viola "modelo por invocación". Contrato heredado:
        # FAST_API_KEY explícita → si no, resolución POR ENDPOINT (única, `nucleo/provider_keys.py`).
        import os
        fast = os.getenv("FAST_API_KEY")
        if fast:
            return fast
        from nucleo.provider_keys import key_for_endpoint
        return key_for_endpoint(self.resolved_base_url())

    def _is_aimlapi(self) -> bool:
        return "aimlapi" in self.resolved_base_url().lower()

    def _is_openai(self) -> bool:
        return "api.openai.com" in self.resolved_base_url().lower()

    def _is_mistral(self) -> bool:
        return "mistral.ai" in self.resolved_base_url().lower()

    def _is_xai(self) -> bool:
        return "x.ai" in self.resolved_base_url().lower()

    def _is_groq(self) -> bool:
        return "groq.com" in self.resolved_base_url().lower()

    def _is_gemini(self) -> bool:
        u = self.resolved_base_url().lower()
        return "googleapis" in u or "generativelanguage" in u

    def _is_zai(self) -> bool:
        return "api.z.ai" in self.resolved_base_url().lower()

    def _is_deepseek(self) -> bool:
        """DeepSeek DIRECTO (`api.deepseek.com`), distinto de DeepSeek servido por el broker AIMLAPI. La diferencia
        NO es cosmética: aquí el parámetro de no-razonar se OBEDECE, y por el broker no. Ver `reasoning_effort`."""
        return "api.deepseek.com" in self.resolved_base_url().lower()

    def reasoning_effort(self) -> str:
        """``reasoning_effort='none'`` apaga el thinking en GEMINI (su extensión) y también en DEEPSEEK DIRECTO.

        La versión anterior de esta docstring decía que «AIMLAPI/DeepSeek/Ollama lo RECHAZAN (400)» y era medio
        falsa: **AIMLAPI sí lo rechaza, DeepSeek directo NO** (medido 2026-08-14 con la key nueva: HTTP 200 y cero
        `reasoning_tokens`). La confusión venía de haber probado DeepSeek solo A TRAVÉS del broker.

        Aun así aquí se sigue devolviendo "" para DeepSeek, y a propósito: el camino que apaga el razonamiento es
        `thinking:{"type":"disabled"}` (ver `stream`), que funciona en los DOS endpoints, así que no hace falta un
        segundo mecanismo que mantener sincronizado. `reasoning_effort:"minimal"` NO sirve — medido, sigue razonando.
        """
        return "none" if self._is_gemini() else ""



# Fallback si `config/v2.json` no trae modelo (fresh install) o si leerlo revienta — auditoría 2026-07-26,
# hallazgo P3: hasta este fix era `x-ai/grok-4-fast-non-reasoning`, un modelo BANEADO en el FlashBrain (CLAUDE.md
# §fast: "grok mis-rutea memoria→widget_data, causa conversaciones absurdas") — justo el peor caso posible para un
# fallback de emergencia. El default de producción real es `anthropic/claude-haiku-4.5` vía aimlapi.
_FALLBACK_MODEL = "anthropic/claude-haiku-4.5"


def spec_from_config() -> ModelSpec:
    """Compone el `ModelSpec` por defecto desde `config/v2` (gestionado por la UI; env = fallback power-user).
    El llamador puede ignorarlo y pasar su propio spec (modelo por invocación)."""
    try:
        from config import v2 as _v2
        cfg = _v2.fast_model_spec()
        return ModelSpec(
            model=cfg.get("model") or _FALLBACK_MODEL,
            base_url=cfg.get("base_url") or None,
            api_key=cfg.get("api_key") or None,
            provider=cfg.get("provider") or "aimlapi",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fast spec_from_config fallback (usando defaults): {e}")
        return ModelSpec(model=_FALLBACK_MODEL, provider="aimlapi")


def available(spec: ModelSpec | None = None) -> bool:
    """True si hay credencial utilizable para este spec (local siempre; nube exige api_key)."""
    spec = spec or spec_from_config()
    return bool(spec.resolved_api_key())


# Chars por token. El 4.0 de siempre es la regla del pulgar del INGLÉS; medido contra el registro real (114 turnos
# con `usage` del proveedor Y los chars de sus dos bloques) nuestro input va a **3,36 chars/token** — castellano con
# tildes, más el JSON del catálogo de tools. El sesgo era sistemático, no ruido: el ratio estimado/real cabía entre
# 0,823 y 0,857 en las 114 muestras.
#
# Importa porque este estimado NO es solo observabilidad: es lo que FACTURA un turno cancelado, donde el `usage` del
# proveedor nunca llega (viaja en el último chunk). Con el 4.0 se cobraba **un 16% de menos** en el 70% de los turnos
# de una sesión real de dictado. Va contra la política fijada el 2026-08-13 al cerrar los cuatro agujeros de Energy:
# *«perder dinero por sub-cobrar es peor que sobre-cobrar un poco»*.
#
# Se deja en 3,3 y no en 3,36 a propósito: redondear hacia ABAJO el divisor estima de MÁS (~2%), que es el lado
# seguro y el mismo criterio que la tarifa de seguridad del medidor.
_CHARS_PER_TOKEN = 3.3


def est_tokens(chars: int) -> int:
    """Estimación barata de tokens desde nº de chars. Dos usos, y el segundo es el que fija la constante:

    1. **Observabilidad** — distinguir «prompt de 100 tokens» de «prompt de 50k», el eje que pide el operador para
       saber si la latencia es del MODELO o del TAMAÑO del prompt. Aquí el divisor casi da igual.
    2. **La factura de un turno CANCELADO** — el `usage` real del proveedor viaja en el ÚLTIMO chunk del stream, así
       que un turno cortado por barge-in no lo recibe nunca y este estimado es lo único que hay. Aquí el divisor es
       dinero (ver `_CHARS_PER_TOKEN`).

    Si el proveedor devuelve `usage`, ese manda siempre (ver `stream`).
    """
    return int(round((chars or 0) / _CHARS_PER_TOKEN))


class _AnthropicSSE:
    """Máquina de estados PURA para el stream SSE de Anthropic Messages (lo que habla Z.AI directo). Separada del
    transporte HTTP a propósito → testeable con objetos `data:` sintéticos (ver tests). `feed(obj)` recibe UN
    objeto JSON de una línea `data:` y devuelve una lista de eventos: `("text", str)` por cada `text_delta`, y
    `("tool", name, input_dict)` cuando un bloque `tool_use` se cierra (acumula `input_json_delta.partial_json`)."""

    def __init__(self) -> None:
        self._blocks: dict[int, dict] = {}   # index → {"type","name","json"}

    def feed(self, obj: dict) -> list[tuple]:
        out: list[tuple] = []
        t = obj.get("type")
        if t == "content_block_start":
            cb = obj.get("content_block") or {}
            self._blocks[obj.get("index")] = {"type": cb.get("type"), "name": cb.get("name", ""), "json": ""}
        elif t == "content_block_delta":
            d = obj.get("delta") or {}
            dt = d.get("type")
            if dt == "text_delta" and d.get("text"):
                out.append(("text", d["text"]))
            elif dt == "input_json_delta":
                b = self._blocks.get(obj.get("index"))
                if b is not None:
                    b["json"] += d.get("partial_json", "") or ""
        elif t == "content_block_stop":
            b = self._blocks.get(obj.get("index"))
            if b and b.get("type") == "tool_use" and b.get("name"):
                try:
                    inp = json.loads(b["json"] or "{}")
                except Exception:
                    inp = {}
                out.append(("tool", b["name"], inp))
        return out


class FastClient:
    """Cliente streaming del modelo rápido. STATELESS respecto al modelo: cada `stream()` recibe su `ModelSpec`.
    Los clientes AsyncOpenAI subyacentes se cachean por (base_url, api_key, ua) para reusar conexiones."""

    # timestamp de la ÚLTIMA llamada por client-key → heurística cold/warm (gap > keepalive ⇒ conexión probablemente
    # fría, se re-hace TLS). Observabilidad del cold-start (FASE 1). Class-level: compartido por todas las instancias.
    _last_call_at: dict[tuple, float] = {}

    _clients: dict[tuple, Any] = {}

    def _client_key(self, spec: ModelSpec) -> tuple:
        # EGRESS (T303). Donde el despliegue declara una salida mediada, el destino y la credencial los
        # decide `llm_egress`, no el spec: el spec sigue diciendo QUÉ modelo se quiere, y deja de decir
        # con qué llave se paga. Sin salida mediada esto devuelve exactamente lo de antes, así que el
        # camino de self-host no cambia ni un byte.
        from nucleo import llm_egress
        raw_base = spec.resolved_base_url()
        base, key, extra = llm_egress.route(raw_base, spec.resolved_api_key())
        if not key:
            raise RuntimeError(f"sin credencial para el modelo rápido ({spec.model} @ {base})")
        # El User-Agent de navegador es para Cloudflare delante de AIMLAPI. Con salida mediada quien
        # habla con AIMLAPI es el otro extremo, así que aquí ya no hace falta.
        ua = _BROWSER_UA if (spec._is_aimlapi() and not extra) else ""
        return (base, key, ua, tuple(sorted(extra.items())))

    def _client_for(self, spec: ModelSpec):
        # import perezoso: una key ausente no debe reventar el import del paquete/setup de sesión.
        from openai import AsyncOpenAI

        ck = self._client_key(spec)
        base, _key, ua, extra = ck
        cli = FastClient._clients.get(ck)
        if cli is None:
            headers = dict(extra)
            if ua:
                headers["User-Agent"] = ua
            headers = headers or None
            # FASE 1 (cold-start): el cliente HTTP mantiene la conexión TLS VIVA mucho más que el default de httpx
            # (~5s). Sin esto, el prewarm calienta la conexión al arrancar pero CADUCA antes del 1er turno → se
            # re-hace TLS+handshake = los ~3.8s del 1er turno frío. Con keepalive largo, la conexión prewarmeada
            # sobrevive hasta el 1er turno y ENTRE turnos → el modelo caliente (~1.2s) se percibe siempre.
            okw = dict(api_key=_key, base_url=base, default_headers=headers)
            _hc = _http_client()
            if _hc is not None:
                okw["http_client"] = _hc
            cli = AsyncOpenAI(**okw)
            FastClient._clients[ck] = cli
        return cli

    async def complete(
        self,
        messages: list[dict],
        *,
        spec: ModelSpec | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        on_tool_call=None,
    ) -> str:
        """Llamada NO-streaming (devuelve el texto entero). Mismo cliente/keys/spec que `stream()` — es el MISMO
        motor, solo sin trocear la salida. La usa el canal de cluster (V2-069): off-voz no necesita streaming, y un
        tier RAZONADOR (GLM-5.2 vía AIMLAPI) NO emite deltas hasta terminar de pensar → con `stream=True` la llamada
        parece colgarse (medido: >115s vs 3.4s sin stream). Lanza el error del proveedor igual que `stream`.

        Si se pasan `tools` (function-calling OpenAI-compatible, V2-076), se ofrecen con `tool_choice='auto'` y, al
        volver, `on_tool_call(name, args_dict)` se dispara una vez por llamada del modelo (best-effort: una con JSON
        inválido se salta, nunca lanza). Es el mismo mecanismo que `stream()` pero sin trocear — para que el turno de
        cluster (que DEBE ir no-streaming por el reasoner) pueda REUSAR el catálogo del FlashBrain. Sin `tools` el
        comportamiento es byte-idéntico a antes (cero regresión)."""
        spec = spec or spec_from_config()
        if spec._is_zai():
            return await self._complete_zai(messages, spec, max_tokens, tools=tools, on_tool_call=on_tool_call)
        extra_body: dict[str, Any] = {}
        r = spec.reasoning_effort()
        if r:
            extra_body["reasoning_effort"] = r
        if spec.is_local():
            extra_body["keep_alive"] = "30m"
        call_kwargs: dict[str, Any] = dict(
            model=spec.model,
            messages=messages,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            stream=False,
        )
        if extra_body:
            call_kwargs["extra_body"] = extra_body
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        # Reintento en transitorios (no-streaming → reintentar la llamada entera es seguro).
        _attempt = 0
        while True:
            try:
                resp = await self._client_for(spec).chat.completions.create(**call_kwargs)
                break
            except Exception as e:  # noqa: BLE001
                if _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise
                _attempt += 1
                logger.warning(f"fast_client.complete: blip transitorio ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
        try:
            msg = resp.choices[0].message
        except (IndexError, AttributeError):
            return ""
        if tools and on_tool_call:                       # function-calling no-streaming (V2-076)
            import json as _json
            for tc in (getattr(msg, "tool_calls", None) or []):
                try:
                    fn = tc.function
                    args = _json.loads(fn.arguments or "{}") if isinstance(fn.arguments, str) else (fn.arguments or {})
                    on_tool_call(fn.name, args if isinstance(args, dict) else {})
                except Exception:                        # una tool-call malformada se salta, nunca tira el turno
                    continue
        return (getattr(msg, "content", None) or "").strip()

    async def _complete_zai(self, messages: list[dict], spec: ModelSpec, max_tokens: int | None, *,
                            tools: list[dict] | None = None, on_tool_call=None) -> str:
        """Z.AI directo (V2-069 cost-fix, 2026-07-26): su endpoint Anthropic-compatible (`/v1/messages`, la cuenta
        'coding plan') habla un wire format DISTINTO del resto de `FastClient` (OpenAI chat/completions) — de ahí
        un método aparte en vez de forzarlo por `AsyncOpenAI`. Antes el canal de cluster pagaba GLM-5.2 vía AIMLAPI
        (proxy con margen) aunque el operador ya tenía cuenta Z.AI directa; el propio `/chat/completions`
        OpenAI-compatible de Z.AI usa OTRO saldo (pay-as-you-go, distinto del plan de coding) — probado en vivo:
        ese devuelve 429 sin fondos mientras `/v1/messages` sí responde. `tools` (OpenAI-compatible, V2-076) se
        traduce al formato de tool-use de Anthropic — necesario para evaluar de verdad la fiabilidad de
        tool-calling de un candidato (§v2077 A/B), no solo el canal de cluster que nunca las ofrece."""
        import httpx
        system = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")]
        if not turns:
            turns = [{"role": "user", "content": system}]
            system = ""
        payload: dict[str, Any] = {"model": spec.model, "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS, "messages": turns}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                for t in tools if t.get("type") == "function" and t.get("function", {}).get("name")
            ]
            payload["tool_choice"] = {"type": "auto"}
        headers = {"x-api-key": spec.resolved_api_key(), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = spec.resolved_base_url().rstrip("/") + "/v1/messages"
        _attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    await _raise_with_body(resp)      # sin await no lanza NADA: ver el aviso de abajo
                break
            except Exception as e:  # noqa: BLE001
                if _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise
                _attempt += 1
                logger.warning(f"fast_client._complete_zai: blip transitorio ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
        data = resp.json()
        parts = data.get("content") or []
        if tools and on_tool_call:
            for p in parts:
                if p.get("type") == "tool_use" and p.get("name"):
                    try:
                        on_tool_call(p["name"], p.get("input") or {})
                    except Exception:                    # una tool-call malformada se salta, nunca tira el turno
                        continue
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()

    async def _stream_zai(self, messages: list[dict], spec: ModelSpec, *, max_tokens: int | None = None,
                          tools: list[dict] | None = None, on_tool_call=None,
                          metrics: dict | None = None) -> AsyncIterator[str]:
        """STREAMING para Z.AI directo (V2-077 A/B, 2026-07-31): el endpoint Anthropic-compatible (`/v1/messages`
        con `stream:true`) emite SSE en el wire format de Anthropic Messages (`content_block_delta` con
        `text_delta`), DISTINTO del `chat/completions` de OpenAI que usa `stream()`. Hasta hoy Z.AI solo tenía
        `complete()` (no-streaming) → un GLM-4.5-Air como FlashBrain de VOZ no era evaluable (la voz necesita
        deltas para TTS incremental). Esto lo hace posible; queda LATENTE hasta configurar FAST=Z.AI (el path de
        voz vivo sigue en Haiku/AIMLAPI). El parser de SSE es `_AnthropicSSE` (puro, con test unitario). NOTA: sin
        verificar end-to-end contra un GLM-4.5-Air con fondos (pay-as-you-go da 429 sin saldo) — pendiente A/B."""
        import httpx
        system = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")]
        if not turns:
            turns = [{"role": "user", "content": system}]
            system = ""
        payload: dict[str, Any] = {"model": spec.model, "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
                                   "messages": turns, "stream": True}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                for t in tools if t.get("type") == "function" and t.get("function", {}).get("name")
            ]
            payload["tool_choice"] = {"type": "auto"}
        headers = {"x-api-key": spec.resolved_api_key(), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = spec.resolved_base_url().rstrip("/") + "/v1/messages"
        m = metrics if metrics is not None else {}
        m.update({"model": spec.model, "provider": spec.provider,
                  "prompt_chars": sum(len(str(x.get("content") or "")) for x in messages)})
        parser = _AnthropicSSE()
        _completion_chars = 0
        # Reintento SOLO de la fase de conexión (aún sin emitir tokens), como el path OpenAI de `stream()`.
        _attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        await _raise_with_body(resp)
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                obj = json.loads(raw)
                            except Exception:                # una línea SSE malformada no tira el turno
                                continue
                            for ev in parser.feed(obj):
                                if ev[0] == "text":
                                    _completion_chars += len(ev[1])
                                    yield ev[1]
                                elif ev[0] == "tool" and on_tool_call:
                                    try:
                                        on_tool_call(ev[1], ev[2])
                                    except Exception:        # tool-call malformada se salta, nunca tira el turno
                                        continue
                return
            except Exception as e:  # noqa: BLE001
                if _completion_chars or _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise                                    # ya emitimos, o no es transitorio → no reintentar
                _attempt += 1
                logger.warning(f"fast_client._stream_zai: blip transitorio al conectar ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
            finally:
                try:
                    m["completion_chars"] = _completion_chars
                    m["completion_tokens_est"] = est_tokens(_completion_chars)
                except Exception:
                    pass

    async def stream(
        self,
        messages: list[dict],
        *,
        spec: ModelSpec | None = None,
        tools: list[dict] | None = None,
        on_tool_call=None,
        max_tokens: int | None = None,
        metrics: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Thin wrapper over `_stream_inner()` that tracks "a real model request is in flight" for
        `nucleo.runstate`'s deferred stop (V2-092 addenda, 2026-08-15): the ⏻ switch must never cut a request
        mid network-call, but the wait is NOT a timer — it is this counter reaching zero, which only ever
        happens when a real stream actually ends (success, provider error, or cancellation). One choke point
        for both branches of `_stream_inner` (the Z.AI SSE path and the OpenAI-compatible path), since a
        `try/finally` around a delegating `async for` covers whatever the inner generator does, wherever inside
        it something raises. See `_stream_inner` for the unchanged streaming logic."""
        from nucleo import runstate

        runstate.enter_inflight()
        try:
            async for chunk in self._stream_inner(
                messages, spec=spec, tools=tools, on_tool_call=on_tool_call,
                max_tokens=max_tokens, metrics=metrics, **kwargs,
            ):
                yield chunk
        finally:
            await runstate.exit_inflight()

    async def _stream_inner(
        self,
        messages: list[dict],
        *,
        spec: ModelSpec | None = None,
        tools: list[dict] | None = None,
        on_tool_call=None,
        max_tokens: int | None = None,
        metrics: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Generador async: emite el texto de cada chunk según llega (para empujarlo a TTS al instante). Lanza
        ante error de transporte/proveedor (el llamador habla una reserva limpia — nunca el error crudo).

        Si se pasan `tools` (funciones OpenAI-compatible), se ofrecen con `tool_choice='auto'`; los
        `delta.tool_calls` se acumulan por índice y, al terminar el stream, `on_tool_call(name, args_dict)` se
        dispara una vez por llamada completa (best-effort: una con JSON inválido se salta, nunca lanza)."""
        spec = spec or spec_from_config()
        # Z.AI directo habla Anthropic Messages SSE (no OpenAI chat/completions) → ruta aparte (paridad con
        # `complete()`, que ya bifurca a `_complete_zai`). Latente hasta configurar FAST=Z.AI.
        if spec._is_zai():
            async for _t in self._stream_zai(messages, spec, max_tokens=max_tokens, tools=tools,
                                             on_tool_call=on_tool_call, metrics=metrics):
                yield _t
            return
        extra_body: dict[str, Any] = {}
        r = spec.reasoning_effort()
        if r:
            extra_body["reasoning_effort"] = r
        if "deepseek" in (spec.model or "").lower():
            # VOZ = NO-RAZONADOR (invariante duro). DeepSeek V4 Flash PIENSA por defecto → en el A/B (2026-07-31)
            # el modo thinking sobre-actuaba (abrió un widget en un turno de contradicción) y bajaba el routing
            # (4/5→3/5 intel); el non-thinking iguala a Haiku en inteligencia (5/5) con MENOS TTFT. Forzamos
            # non-thinking en el path rápido — campo `thinking` (api-docs.deepseek.com, OpenAI/Anthropic-compat).
            #
            # ⚠️ **Este parámetro se manda igual por los dos endpoints, pero solo UNO lo OBEDECE.** Medido el
            # 2026-08-14 con el prompt real de voz (13.488 chars, 23 tools), 6 turnos por brazo:
            #
            #   AIMLAPI `thinking:disabled` → TTFT p50 4,24 s · max 14,71 s · **2.138 tokens de razonamiento**
            #   DIRECTO `thinking:disabled` → TTFT p50 1,01 s · max  1,30 s · **0**
            #
            # O sea que el broker acepta el campo y razona de todas formas (ya se sospechaba el 2026-08-02 por el
            # tiempo: «lo reduce, no lo apaga»; ahora se LEE en `usage.completion_tokens_details.reasoning_tokens`,
            # que es la prueba que entonces no teníamos). El titular de voz es por eso `api.deepseek.com`.
            extra_body.setdefault("thinking", {"type": "disabled"})
        if spec.is_local():
            # Mantén el modelo local caliente durante toda la sesión (evita recargas de ~60s tras un hueco).
            extra_body["keep_alive"] = "30m"
        call_kwargs = dict(
            model=spec.model,
            messages=messages,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            stream=True,
        )
        if extra_body:
            call_kwargs["extra_body"] = extra_body
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        call_kwargs.update(kwargs)

        # ── TOTALIZADORES DE TAMAÑO (observabilidad, premisa del operador) ──────────────────────────────────
        # Chars EXACTOS del input (mensajes + esquemas de tools) + tokens ESTIMADOS. Distingue «lento por el
        # modelo» de «lento por prompt gigante». Todo en `metrics` (best-effort; nunca rompe el turno).
        m = metrics if metrics is not None else {}
        try:
            import json as _json
            prompt_chars = sum(len(str(msg.get("content") or "")) for msg in messages)
            sys_chars = sum(len(str(msg.get("content") or "")) for msg in messages if msg.get("role") == "system")
            tools_chars = len(_json.dumps(tools)) if tools else 0
            ck = self._client_key(spec)
            now = time.time()
            last = FastClient._last_call_at.get(ck)
            gap_s = (now - last) if last else None
            # keepalive del pool (FASE 1); si el gap lo supera, la conexión estaba probablemente FRÍA (TLS de nuevo).
            _ka = _keepalive_expiry()
            m.update({
                "model": spec.model, "provider": spec.provider,
                "prompt_chars": prompt_chars, "system_chars": sys_chars,
                "n_msgs": len(messages), "n_tools": len(tools) if tools else 0, "tools_chars": tools_chars,
                "prompt_tokens_est": est_tokens(prompt_chars + tools_chars),
                "gap_since_last_s": round(gap_s, 1) if gap_s is not None else None,
                "cold_estimate": (gap_s is None) or (gap_s > _ka),
            })
            FastClient._last_call_at[ck] = now
        except Exception:
            pass

        # Reintento SOLO de la fase de conexión (aún no se ha emitido ningún token) → seguro ante blips transitorios.
        _attempt = 0
        while True:
            try:
                stream = await self._client_for(spec).chat.completions.create(**call_kwargs)
                break
            except Exception as e:  # noqa: BLE001
                if _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise
                _attempt += 1
                logger.warning(f"fast_client: blip transitorio al conectar ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
        calls: dict[int, dict] = {}
        _completion_chars = 0
        _seen_output = False     # ¿ha contestado ya el proveedor? (→ retirar el fallo registrado, ver abajo)
        _usage = None
        _t_start = time.time()
        try:
            # try/finally (no "recorre y luego dispara"): el consumidor puede `return` desde DENTRO de su propio
            # `async for` (p. ej. deriva de idioma) → cierra este generador con GeneratorExit a mitad. Sin el
            # finally, una tool call ya acumulada se perdería en silencio (bug real corregido en duo 2026-07-08).
            async for chunk in stream:
                # `usage` REAL si el proveedor lo incluye en algún chunk (muchos lo mandan en el último). No lo
                # PEDIMOS con stream_options (riesgo de 400 en proxies que no lo soportan) — lo leemos si viene.
                _u = getattr(chunk, "usage", None)
                if _u is not None:
                    _usage = _u
                try:
                    delta = chunk.choices[0].delta
                except (IndexError, AttributeError):
                    continue
                # LATIDO DEL STREAM (2026-08-12) — el dato que faltaba, y costó turnos de verdad. Este generador solo
                # YIELDEA cuando el chunk trae TEXTO: los chunks de una tool-call (que llegan con `content` vacío y
                # los argumentos goteando en `tool_calls`) se consumen aquí dentro y no salen. Para quien nos
                # recorre, un turno cuya respuesta es una ACCIÓN —«muéstrame los resultados», «cierra eso»— es
                # indistinguible de un modelo colgado. El plazo de silencio del turno mataba esos turnos SANOS: el
                # 2026-08-12 a las 13:49/13:50 se cortaron tres seguidos justo cuando el operador pedía ver los
                # resultados, con `ttft=1.5s` (el modelo había contestado) y `spoken_chars=0`. Sellamos el avance
                # AQUÍ, en el sitio que sí ve cada chunk, y el plazo de arriba consulta esto antes de declarar nada.
                m["chunks"] = int(m.get("chunks") or 0) + 1
                m["last_chunk_ts"] = time.time()
                # SALUD: el proveedor ha CONTESTADO → se retira cualquier fallo anterior del modelo rápido. Va aquí,
                # en el único punto por el que pasan TODAS las llamadas del turno, y no al final del turno
                # conversacional, que es donde estaba (2026-08-12): esa función tiene una docena de `return`
                # tempranos —turno de solo-tool, `show_widget`, gate de atención, fragmento descartado— y cada uno
                # se saltaba el `clear`. Efecto medido: el ◉ enseñó «un turno se atascó» durante 40 MINUTOS
                # mientras el modelo respondía decenas de veces. Un panel que afirma el presente con evidencia
                # rancia es el mismo fallo que el agente caído pintado en azul.
                if not _seen_output:
                    _seen_output = True
                    try:
                        from voice import health_state
                        health_state.clear("llm")
                    except Exception:
                        pass
                text = getattr(delta, "content", None) or ""
                if text:
                    _completion_chars += len(text)
                    yield text
                for tc in (getattr(delta, "tool_calls", None) or []):
                    slot = calls.setdefault(getattr(tc, "index", 0), {"name": "", "arguments": ""})
                    fn = getattr(tc, "function", None)
                    if fn and getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if fn and getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments
        finally:
            # cierre de TOTALIZADORES: chars de salida + tokens (reales del proveedor si vinieron, si no estimados)
            # + tiempo total. El TTFT lo mide el llamador (primer yield). Best-effort.
            try:
                m["completion_chars"] = _completion_chars
                m["completion_tokens_est"] = est_tokens(_completion_chars)
                m["total_ms"] = round((time.time() - _t_start) * 1000, 1)
                if _usage is not None:
                    pt = getattr(_usage, "prompt_tokens", None)
                    ctk = getattr(_usage, "completion_tokens", None)
                    tt = getattr(_usage, "total_tokens", None)
                    # HIT DE CACHÉ (2026-08-14). DeepSeek directo reporta `prompt_cache_hit_tokens`, y aquí importa
                    # más que en cualquier otro sitio: el system prompt de voz son ~10k tokens CONSTANTES, así que
                    # en una conversación de verdad la mayor parte del input es un hit, y el input domina 14:1.
                    # Va DENTRO de `prompt_tokens` (verificado: pt = hit + miss), así que se DESCUENTA, no se suma
                    # — ver `energy_meter.llm_cost_to_energy`, donde los dos contadores son parámetros distintos
                    # precisamente para que nadie los confunda y cobre dos veces.
                    _hit = getattr(_usage, "prompt_cache_hit_tokens", None)
                    if _hit is None:
                        _det = getattr(_usage, "prompt_tokens_details", None)
                        _hit = getattr(_det, "cached_tokens", None) if _det is not None else None
                    if _hit is not None:
                        m["prompt_cache_hit_tokens"] = _hit
                    if pt is not None:
                        m["prompt_tokens"] = pt
                    if ctk is not None:
                        m["completion_tokens"] = ctk
                    if tt is not None:
                        m["total_tokens"] = tt
                    m["usage_source"] = "provider"
                else:
                    m["usage_source"] = "estimate"
            except Exception:
                pass
            # ENERGY METERING (INI-018, 2026-07-24) — no-op everywhere except a demo Machine (see
            # nucleo/energy_meter.py). Uses REAL provider usage when available, falls back to the
            # char-based estimate already computed above (m["*_tokens_est"]) otherwise — some real
            # signal beats none for a cost meter, even if provider usage never arrived this call.
            try:
                from nucleo import energy_meter as _energy
                _energy.report_llm_usage(
                    base_url=spec.resolved_base_url(),
                    model=spec.model,
                    prompt_tokens=m.get("prompt_tokens", m.get("prompt_tokens_est")),
                    completion_tokens=m.get("completion_tokens", m.get("completion_tokens_est")),
                    cache_hit_tokens=m.get("prompt_cache_hit_tokens"),
                )
            except Exception:
                pass
            if on_tool_call and calls:
                import json
                for call in calls.values():
                    if not call["name"]:
                        continue
                    try:
                        args = json.loads(call["arguments"] or "{}")
                    except Exception:
                        logger.warning(f"tool call {call['name']} con argumentos no parseables: {call['arguments']!r}")
                        continue
                    on_tool_call(call["name"], args if isinstance(args, dict) else {})

    def describe(self, spec: ModelSpec | None = None) -> str:
        spec = spec or spec_from_config()
        return f"{spec.model} @ {spec.resolved_base_url()} (reasoning={spec.reasoning_effort() or 'default'})"
