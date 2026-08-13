#
# triage.py — el clasificador COMPARTIDO (promovido de connectors/whatsapp, INI-015). Dado un lote de mensajes
# entrantes de CUALQUIER plataforma (WhatsApp, Telegram, …), devuelve para cada uno si MERECE la atención del
# operador y si va DIRIGIDO a él. Llamada DIRECTA a un modelo (por defecto LOCAL, Ollama) vía endpoint
# OpenAI-compatible — NO pasa por el agente Hermes (privacidad + invariante ACP de voz intactos).
#
# Es agnóstico de plataforma: recibe dicts con {senderName, chatName?, isGroup, body} y devuelve la misma lista
# enriquecida con {importante, dirigido_a_mi, urgencia, motivo}. El conector añade luego platform/ids.
#
# Salida por mensaje: {"i", "importante": bool, "dirigido_a_mi": bool, "urgencia": "alta|media|baja", "motivo"}.
# Es solo un prompt afinable: si el modelo local no clasifica bien, se cambia MSG_TRIAGE_MODEL (una variable).
#
import json
import time

import aiohttp
from loguru import logger

from connectors.messaging import config

# ── El prompt (editable; se afina sobre mensajes reales) ────────────────────
_SYSTEM = """Eres un triador de mensajes personales para un asistente de voz. Los mensajes llegan de varias apps
(WhatsApp, Telegram, …); trátalos igual. Para CADA mensaje decides:
- importante: ¿merece la atención del dueño AHORA? (algo que requiere respuesta, una cita, un tema personal o
  de trabajo real). NO son importantes: cadenas, promociones, "buenos días" de difusión, spam, bots, ruido de
  grupos/canales que no le mencionan.
- dirigido_a_mi: ¿el mensaje va dirigido personalmente al dueño? (un DM, o un grupo donde le mencionan/le
  responden). Un mensaje suelto en un grupo grande que no le nombra NO va dirigido a él.
- urgencia: "alta" (necesita acción hoy / algo urgente), "media" (importa pero puede esperar), "baja".
- motivo: máximo 12 palabras, en español, por qué.

Responde SOLO con un array JSON, un objeto por mensaje, en el MISMO orden, con la clave "i" (el índice dado).
Sin texto fuera del JSON. Ejemplo de formato:
[{"i":0,"importante":true,"dirigido_a_mi":true,"urgencia":"alta","motivo":"te pide confirmar la cena de hoy"}]"""

_FEWSHOT_USER = """Dueño: Ricart.
Mensajes:
[0] (DM de Mamá) "¿Vienes a comer el domingo? dime algo que compro"
[1] (grupo 'Ofertas Chollos', 47 personas) "🔥🔥 -70% en zapatillas, corre https://bit.ly/xy"
[2] (grupo 'Proyecto Zaelar') "@Ricart puedes revisar el PR antes de las 5?"
[3] (DM de Juan) "jajaja brutal el video"
[4] (grupo 'Familia', sin mención) "buenos días a todos ☀️" """

_FEWSHOT_ASSISTANT = """[{"i":0,"importante":true,"dirigido_a_mi":true,"urgencia":"media","motivo":"te pide confirmar comida del domingo"},
{"i":1,"importante":false,"dirigido_a_mi":false,"urgencia":"baja","motivo":"promoción de difusión, spam"},
{"i":2,"importante":true,"dirigido_a_mi":true,"urgencia":"alta","motivo":"te mencionan y piden revisar un PR hoy"},
{"i":3,"importante":false,"dirigido_a_mi":true,"urgencia":"baja","motivo":"charla informal sin acción"},
{"i":4,"importante":false,"dirigido_a_mi":false,"urgencia":"baja","motivo":"saludo de grupo sin mención"}]"""


def _render_batch(messages: list[dict], operator_name: str) -> str:
    who = operator_name or "el dueño"
    lines = [f"Dueño: {who}.", "Mensajes:"]
    for i, m in enumerate(messages):
        origin = ("grupo '%s'" % m.get("chatName", "?")) if m.get("isGroup") else \
                 ("DM de %s" % m.get("senderName", "?"))
        mention = " [te menciona]" if operator_name and \
            operator_name.lower() in (m.get("body", "").lower()) else ""
        body = (m.get("body") or "").replace("\n", " ")[:300]
        lines.append(f"[{i}] ({origin}){mention} \"{body}\"")
    return "\n".join(lines)


async def classify(messages: list[dict], operator_name: str | None = None) -> list[dict]:
    """Clasifica un lote. Devuelve la lista de veredictos alineada por índice (defensivo ante JSON imperfecto).
    `operator_name` ayuda al "¿va dirigido a mí?"; si es None cae al nombre común (config.operator_name())."""
    if not messages:
        return []
    who = config.operator_name() if operator_name is None else (operator_name or "").strip()
    payload = {
        "model": config.triage_model(),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _FEWSHOT_USER},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
            {"role": "user", "content": _render_batch(messages, who)},
        ],
    }
    to = aiohttp.ClientTimeout(total=120)
    t0 = time.time()
    url = config.triage_url()
    local = "11434" in url or "localhost" in url or "127.0.0.1" in url
    try:
        async with aiohttp.ClientSession(timeout=to) as s:
            async with s.post(url.rstrip("/") + "/chat/completions",
                              headers={"Authorization": f"Bearer {config.triage_key()}"},
                              json=payload) as r:
                data = await r.json()
        content = data["choices"][0]["message"]["content"]
        verdicts = _parse(content)
        # A ENERGY (2026-08-13). El default es LOCAL (Ollama) y `energy_meter` devuelve None para un
        # endpoint local, así que el caso normal sigue costando cero y no hace ni una llamada de red.
        # Se reporta igualmente porque `MSG_TRIAGE_MODEL` puede apuntar a un endpoint REMOTO —y en la
        # nube no hay Ollama—: sin esto, mover esa variable convierte el triaje en gasto invisible, y
        # el triaje corre por CADA lote de mensajes entrantes, no por petición del operador.
        try:
            from nucleo import energy_meter as _energy
            usage = (data.get("usage") or {}) if isinstance(data, dict) else {}
            _energy.report_llm_usage(base_url=url, model=config.triage_model(),
                                     prompt_tokens=usage.get("prompt_tokens"),
                                     completion_tokens=usage.get("completion_tokens"))
        except Exception:  # noqa: BLE001
            pass
        try:
            from voice.observer import emit
            emit("brain", f"📨 Triaje mensajería ({len(messages)})",
                 extra={"model": config.triage_model(), "engine": "local" if local else "remote",
                        "triage_ms": round((time.time() - t0) * 1000)})
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"triaje falló ({config.triage_model()}): {e} — marco todo como incierto")
        verdicts = {}

    # Alinear por índice; lo que el modelo no devolvió → incierto (no lo silenciamos por error).
    out = []
    for i, m in enumerate(messages):
        v = verdicts.get(i, {})
        out.append({
            **m,
            "importante": bool(v.get("importante", True)),      # ante duda, mostrar (fail-open hacia el operador)
            "dirigido_a_mi": bool(v.get("dirigido_a_mi", False)),
            "urgencia": v.get("urgencia", "media"),
            "motivo": v.get("motivo", "(sin clasificar — el modelo no respondió)"),
        })
    return out


def _parse(content: str) -> dict[int, dict]:
    """Extrae el array JSON aunque venga con texto/```json alrededor. Indexado por 'i'."""
    txt = content.strip()
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"sin array JSON en la respuesta: {txt[:120]}")
    arr = json.loads(txt[start:end + 1])
    return {int(o["i"]): o for o in arr if isinstance(o, dict) and "i" in o}
