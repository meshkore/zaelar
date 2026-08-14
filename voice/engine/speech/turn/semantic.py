"""Detector de fin de turno que también mira el SENTIDO, no solo el silencio (V2-095, 2026-08-14).

El límite del turno lo decidía LiveKit con silencio + energía (`min_delay`/`max_delay` de
`voice/endpointing.py`) y, si está activo, su modelo ONNX multilingüe. Ninguno de los dos mira si la frase del
operador **está acabada**. Consecuencia medida en la sesión b70a45d0: un operador dictando una petición larga
pausa para pensar, y cada pausa cerraba un turno que el fragmento siguiente cancelaba.

    465s → 626s (161 s):  22 prompts · 18 cancelados · 20 rellenos · CERO respuestas
    …sobre trozos como «del», «del software,», «a», «para que», «Un un superplanning»

Sobre las 89 transcripciones finales de esa sesión, la capa léxica de `nucleo/flash/segmenter.py` reconoce **43
como incompletas (48%)** con CERO falsos positivos sobre las órdenes cortas del operador («pon música», «para»,
«cancélalo», «sí, te autorizo»), que es lo que de verdad no se puede retener.

## Por qué AQUÍ y no en el proveedor

Porque LiveKit pone el techo por nosotros. Este detector no decide cuándo se cierra el turno: devuelve una
PROBABILIDAD de que haya acabado. Por debajo de `unlikely_threshold`, LiveKit espera `max_delay` en vez de
`min_delay` — y `max_delay` es un tope duro. Un veto semántico puede RETRASAR un turno; no puede perderlo.
Haciéndolo en el proveedor (descartando el fragmento) sí se perdería, si el operador se calla justo ahí.

## Composición, no sustitución

Si hay un detector previo configurado (el `MultilingualModel` de LiveKit), se conserva y este solo VETA: nos
quedamos con la probabilidad MÁS BAJA de las dos. Dos señales independientes de «aún no ha acabado» valen más que
una, y la nuestra no sabe de prosodia ni de idiomas — sabe de palabras colgadas.
"""
from __future__ import annotations

import os

from loguru import logger

from . import registry

# Probabilidad que devolvemos cuando la frase está claramente a medias. Tiene que quedar por DEBAJO del
# `unlikely_threshold` del detector para que LiveKit se espere: el del modelo local ronda 0.15-0.2.
_INCOMPLETE_P = 0.01
_COMPLETE_P = 0.99
_THRESHOLD = 0.5


class SemanticTurnDetector:
    """Implementa el `_TurnDetector` de LiveKit (`unlikely_threshold` · `supports_language` ·
    `predict_end_of_turn`) delegando en un detector interior si lo hay."""

    def __init__(self, inner=None):
        self._inner = inner

    @property
    def model(self) -> str:
        return "zaelar-semantic" + (f"+{getattr(self._inner, 'model', '?')}" if self._inner else "")

    @property
    def provider(self) -> str:
        return "zaelar"

    async def unlikely_threshold(self, language=None):
        # Si hay detector interior, respeta SU umbral (nuestras probabilidades son 0.01/0.99, así que caen del
        # lado correcto de cualquier umbral razonable). Sin él, uno propio.
        if self._inner is not None:
            try:
                v = await self._inner.unlikely_threshold(language)
                if v is not None:
                    return v
            except Exception:
                pass
        return _THRESHOLD

    async def supports_language(self, language=None) -> bool:
        # La capa léxica es es/en. Se declara soporte SIEMPRE: si el idioma no es de los nuestros, el análisis no
        # encuentra palabras colgadas y devuelve «completo» — o sea, el comportamiento de antes. Decir que no lo
        # soportamos apagaría también al detector interior.
        return True

    async def predict_end_of_turn(self, chat_ctx, *, timeout: float | None = None) -> float:
        text = _last_user_text(chat_ctx)
        ours = _COMPLETE_P
        try:
            from nucleo.flash import segmenter
            incomplete, why = segmenter.looks_incomplete(text)
            if incomplete:
                ours = _INCOMPLETE_P
                # VISIBLE: una retención equivocada tiene que poder verse y corregirse, no ser un turno que no
                # llega y nadie sabe por qué. Con el motivo concreto («acaba en «del»…»).
                try:
                    from voice.observer import emit
                    emit("vad", "⏸ turno RETENIDO — la frase no ha acabado", text=text[:160], role="system",
                         extra={"cat": "system", "why": why, "detector": "semantic"})
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"turno semántico: análisis fallido, dejo pasar ({e!r})")
            ours = _COMPLETE_P

        if self._inner is None:
            return ours
        try:
            inner = await self._inner.predict_end_of_turn(chat_ctx, timeout=timeout)
        except Exception:
            return ours
        # La MÁS BAJA: cualquiera de los dos que diga «aún no» manda. Retener de más cuesta hasta `max_delay`;
        # cortar a media frase cuesta un turno entero tirado y una respuesta a media pregunta.
        return min(ours, inner if isinstance(inner, (int, float)) else ours)


def _last_user_text(chat_ctx) -> str:
    """El último mensaje del OPERADOR del contexto que LiveKit pasa al detector. Tolerante con la forma: la API de
    `ChatContext` ha cambiado de shape entre versiones y esto no puede tumbar el turno por un atributo."""
    try:
        items = list(getattr(chat_ctx, "items", None) or getattr(chat_ctx, "messages", None) or [])
    except Exception:
        return ""
    for m in reversed(items):
        try:
            if str(getattr(m, "role", "")) != "user":
                continue
            c = getattr(m, "content", None) or getattr(m, "text_content", None)
            if callable(c):
                c = c()
            if isinstance(c, list):
                c = " ".join(str(x) for x in c if isinstance(x, str))
            if c:
                return str(c)
        except Exception:
            continue
    return ""


@registry.register("semantic")
def build():
    """`turn_provider=semantic` (DEFECTO desde 2026-08-14): la capa léxica, con el detector ONNX de LiveKit dentro
    solo si se pide explícitamente.

    El ONNX va **detrás de una env var y APAGADO por defecto** porque en esta arquitectura no puede funcionar, y eso
    está medido, no supuesto: el job corre en un HILO (`job_executor_type=THREAD`, INI-012) y `MultilingualModel()`
    exige registrar su `InferenceRunner` en el hilo PRINCIPAL — revienta con «InferenceRunner must be registered on
    the main thread». Intentarlo en cada sesión solo dejaba un error ruidoso en el log que parece una avería y no lo
    es. La capa léxica no necesita runner de inferencia ninguno, así que corre donde el modelo no puede.

    `ZAELAR_TURN_ONNX=1` lo reintenta, para el día que la inferencia se registre en el hilo principal antes de
    arrancar el worker (el follow-up de INI-012). Si falla, se degrada a la capa léxica sola — que sigue siendo
    infinitamente mejor que solo silencio.
    """
    inner = None
    if (os.getenv("ZAELAR_TURN_ONNX") or "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from livekit.plugins.turn_detector.multilingual import MultilingualModel
            inner = MultilingualModel()
        except Exception as e:  # noqa: BLE001
            logger.info(f"turno semántico: sin modelo ONNX interior ({e!r}) — capa léxica sola")
    return SemanticTurnDetector(inner)
