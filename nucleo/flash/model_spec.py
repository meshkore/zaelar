"""nucleo/flash/model_spec.py — the "which model, from where" selection type (split out of fast_client.py,
2026-08-17 modularization pass). `ModelSpec` and its two composers (`spec_from_config`, `available`) are pure
provider-detection/URL/key resolution with zero I/O and zero coupling to the streaming client itself — the
audit that led to this split found them a genuinely separable concern from `fast_client.py`'s actual HTTP/SSE
transport code. Re-exported from `fast_client.py` (imported there by name across many callers: `nucleo/research.py`,
`nucleo/flash/provider_chain.py`, `voice/engine/pipeline/agent.py`, etc. — none of them needed to change).

Regla dura del proyecto (se conserva de la docstring original): modelo POR INVOCACIÓN, nunca una env global de
modelo — dos sesiones concurrentes pueden usar modelos distintos sin pisarse."""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

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
        # Explicit FAST_API_KEY wins; otherwise resolve BY ENDPOINT (single resolver, `nucleo/provider_keys.py`).
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
        """The coding-plan (Anthropic-compatible) endpoint ONLY. Z.ai's pay-per-use credits live at
        `/api/paas/v4`, which is OpenAI-compatible: matching it here would force it down `_complete_zai`'s
        `/v1/messages` path and buy a 404 that looks exactly like an outage. Same host, two protocols —
        the URL segment is what tells them apart (V2-462)."""
        u = self.resolved_base_url().lower()
        return "api.z.ai" in u and "/paas/" not in u

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
# hallazgo P3: hasta ese fix era `x-ai/grok-4-fast-non-reasoning`, un modelo BANEADO en el FlashBrain (CLAUDE.md
# §fast: "grok mis-rutea memoria→widget_data, causa conversaciones absurdas") — justo el peor caso posible para un
# fallback de emergencia.
#
# 2026-08-19: es **DeepSeek V4 Pro DIRECTO**, el mismo titular que fija `config/v2.json`, por norma del operador.
# Un fallback que apunta a otro modelo distinto del titular es un cambio de cerebro SILENCIOSO justo en el
# momento en que la config no se puede leer: se nota en la calidad de las respuestas y en la factura, nunca en un
# error. `_FALLBACK_BASE` va pegado al nombre porque el catálogo del broker y el de la API nativa NO coinciden
# (el broker prefija `deepseek/`, la nativa no) — separarlos deja un 400 esperando.
_FALLBACK_MODEL = "deepseek-v4-pro"
_FALLBACK_BASE = "https://api.deepseek.com"


def spec_from_config() -> ModelSpec:
    """Compone el `ModelSpec` por defecto desde `config/v2` (gestionado por la UI; env = fallback power-user).
    El llamador puede ignorarlo y pasar su propio spec (modelo por invocación)."""
    try:
        from config import v2 as _v2
        cfg = _v2.fast_model_spec()
        model = cfg.get("model") or _FALLBACK_MODEL
        base = cfg.get("base_url") or None
        # The fallback model TRAVELS WITH ITS ENDPOINT. Falling back on the name alone would send
        # `deepseek-v4-pro` to `resolved_base_url()`'s default (the broker), whose catalog prefixes it as
        # `deepseek/deepseek-v4-pro` — the exact naming trap that shipped the workers' DeepSeek rung broken
        # (400 on every request, invisible because a relay rung only runs once the titular is already down).
        if model == _FALLBACK_MODEL and not base:
            base = _FALLBACK_BASE
        return ModelSpec(
            model=model,
            base_url=base,
            api_key=cfg.get("api_key") or None,
            provider=cfg.get("provider") or ("deepseek" if base == _FALLBACK_BASE else "aimlapi"),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fast spec_from_config fallback (usando defaults): {e}")
        return ModelSpec(model=_FALLBACK_MODEL, base_url=_FALLBACK_BASE, provider="deepseek")


def available(spec: ModelSpec | None = None) -> bool:
    """True si hay credencial utilizable para este spec (local siempre; nube exige api_key)."""
    spec = spec or spec_from_config()
    return bool(spec.resolved_api_key())
