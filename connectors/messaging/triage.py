#
# triage.py — SHARED classifier (promoted from connectors/whatsapp, INI-015). Given a batch of inbound messages from
# ANY platform (WhatsApp, Telegram, ...), returns for each one whether it DESERVES the operator's attention and
# whether it is ADDRESSED to them. DIRECT call to a model (LOCAL by default, Ollama) through an OpenAI-compatible
# endpoint — does NOT go through the Hermes agent (privacy + voice ACP invariant intact).
#
# It is platform-agnostic: receives dicts with {senderName, chatName?, isGroup, body} and returns the same list
# enriched with {importante, dirigido_a_mi, urgencia, motivo}. The connector adds platform/ids later.
#
# Output per message: {"i", "importante": bool, "dirigido_a_mi": bool, "urgencia": "alta|media|baja", "motivo"}.
# It is only a tunable prompt: if the local model does not classify well, change MSG_TRIAGE_MODEL (one variable).
#
import json
import time

import aiohttp
from loguru import logger

from connectors.messaging import config

# ── Prompt (editable; tuned on real messages) ───────────────────────────────
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
    """Classify a batch. Returns verdicts aligned by index (defensive against imperfect JSON). `operator_name` helps
    with "is it addressed to me?"; if None, falls back to the common name (config.operator_name())."""
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
        # ENERGY (2026-08-13). The default is LOCAL (Ollama) and `energy_meter` returns None for a local endpoint, so
        # the normal case still costs zero and makes no network call. Still reported because `MSG_TRIAGE_MODEL` may
        # point at a REMOTE endpoint — and there is no Ollama in the cloud: without this, moving that variable turns
        # triage into invisible spend, and triage runs for EVERY inbound message batch, not by operator request.
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

    # Align by index; anything the model did not return -> uncertain (do not silence it by mistake).
    out = []
    for i, m in enumerate(messages):
        v = verdicts.get(i, {})
        out.append({
            **m,
            "importante": bool(v.get("importante", True)),      # when unsure, show it (fail-open toward operator)
            "dirigido_a_mi": bool(v.get("dirigido_a_mi", False)),
            "urgencia": v.get("urgencia", "media"),
            "motivo": v.get("motivo", "(sin clasificar — el modelo no respondió)"),
        })
    return out


def _parse(content: str) -> dict[int, dict]:
    """Extract the JSON array even if surrounded by text/```json. Indexed by 'i'."""
    txt = content.strip()
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"sin array JSON en la respuesta: {txt[:120]}")
    arr = json.loads(txt[start:end + 1])
    return {int(o["i"]): o for o in arr if isinstance(o, dict) and "i" in o}
