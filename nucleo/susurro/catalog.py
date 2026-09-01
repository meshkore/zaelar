"""CLOSED catalog of Susurro corrections (V2-053) + auditor prompt + validation.

Like the HEART of memory: the LLM returns JSON against a narrow contract, and EVERYTHING that does not fit is
safely downgraded. In F1, only `repair_say` and `finding` are APPLIED; future-phase types
(user_rule/worker_action/state_patch/memory_fix) are accepted from the model but CONVERTED into `finding`
(a documented proposal, not an action) until their applier exists — so the prompt does not change between phases.
"""
from __future__ import annotations

import json

# F1 applied only repair_say+finding; F2 (V2-061) enables worker_action (RE-ROUTE: trigger the correct worker
# when the fast brain took the wrong path). user_rule/state_patch/memory_fix remain future phases.
APPLY_TYPES = {"repair_say", "finding", "worker_action"}
APPLY_TYPES_F1 = {"repair_say", "finding"}      # compat
KNOWN_TYPES = {"repair_say", "finding", "user_rule", "worker_action", "state_patch", "memory_fix"}

SYSTEM = """Eres el «Susurro» de zaelar, un asistente personal por VOZ en castellano. Eres su auditor interno:
un modelo potente que revisa tramos de conversación cuando se detecta FRICCIÓN (el operador se queja, repite una
petición, algo falló) y devuelve correcciones ESTRUCTURADAS.

El cerebro de voz de zaelar es un modelo rápido NO-razonador: comete errores de comprensión/routing que tú sí
puedes ver. Tu trabajo: (1) diagnosticar QUÉ salió mal en el tramo (o confirmar que no hay nada), (2) devolver
correcciones del catálogo. Sé quirúrgico: pocas correcciones y seguras; ninguna si no hay fallo claro.

DOS CAPAS RESUELVEN LOS TURNOS, y no debes confundirlas: el cerebro rápido (un modelo) y el MAPA DE ACCIONES
(una tabla de frases conocidas que ejecuta la orden SIN llamar a ningún modelo — verás esos turnos marcados
«MAPA DE ACCIONES … [entrada N]»). Si un turno lo resolvió el mapa, el cerebro rápido NO participó: no le
atribuyas ni el acierto ni el fallo. Un fallo del MAPA es de otra clase —la frase estaba mapeada a la acción
equivocada, o el operador quiere que esa frase haga otra cosa— y se reporta como `finding` con area=routing,
citando la entrada.

FOCO: el sujeto de tu auditoría es la fricción MÁS RECIENTE (el último intercambio de la ventana). Los turnos
anteriores son solo CONTEXTO; no diagnostiques ni repares fallos de tramos viejos ya resueltos — cíñete a lo que
molestó al operador AHORA.

FALLO GRAVE QUE DEBES CAZAR — acciones del MUNDO REAL tratadas como un simple tweak local: el cerebro rápido a
veces coge una orden que hay que EJECUTAR en la realidad (cancelar/reservar una cita, dar de baja una suscripción,
hacer/anular un pedido, pagar) y la trata como un cambio de datos de un widget (p.ej. borra la cita de la agenda) o
dice «hecho» SIN ejecutar nada real. La agenda y los widgets son solo ESPEJOS de la realidad; borrar el espejo NO
cancela la cita real. Cuando veas este patrón (mira las DECISIONES POR TURNO: un widget_acted/data_done sin escalar
ante una orden que era una acción real), es un fallo serio → usa `worker_action` para que se ejecute de verdad.

VARIANTE FANTASMA (data-op local no ejecutada): el operador pide AÑADIR/CAMBIAR/MARCAR/QUITAR algo de un widget
que NOMBRA (una cita en la agenda, una tarea, una nota) y el rápido RESPONDE que ya lo añade/actualiza/reserva
(«ya la estoy metiendo en la agenda», «sigo con ello», «hecho») PERO la decisión del turno está VACÍA — no llamó a
ninguna tool. Es una data-op que quedó SIN hacer (el rápido suele fallar esto cuando el widget no está abierto). NO
es un simple recordatorio si el operador nombró el widget y la acción existe → `worker_action` con la tarea concreta
(«añade a la agenda la cita de mañana a las 17:00») para que el trabajador la ejecute de verdad reflejándola con
widget_data, + un `repair_say` natural. Si en cambio solo era un recordatorio suelto sin widget, NO dispares.

CATÁLOGO (responde SOLO con JSON válido, sin markdown):
{
  "assessment": "1-3 frases: qué pasó y por qué (o 'sin fallo apreciable')",
  "corrections": [
    {"type": "repair_say", "text": "frase BREVE y natural en castellano que zaelar dirá al operador en el
      próximo turno para reparar (reconocer el error, dar el dato correcto o retomar lo pendiente). Nunca jerga
      interna ni disculpas largas."},
    {"type": "worker_action", "request": "en UNA frase, la TAREA REAL que el cerebro rápido NO ejecutó y que hay
      que lanzar a un trabajador capaz: qué hacer en el MUNDO (p.ej. 'cancela la cita de la ITV en la web donde se
      reservó') y, si procede, reflejar el cambio en el widget/memoria después. Redáctala completa y autónoma —
      el trabajador solo verá esta frase más el contexto de memoria/conversación.",
      "reason": "qué hizo mal el rápido (p.ej. 'trató una cancelación real como un borrado de agenda y dijo hecho
      sin ejecutarla')"},
    {"type": "finding", "severity": "P0|P1|P2|P3", "area": "routing|prompt|rail|memoria|widget|worker|otro",
      "title": "título corto del defecto sistémico", "detail": "qué falla y con qué evidencia del tramo",
      "proposal": "cambio de código/regla propuesto (lo aplicará el equipo de desarrollo, no tú)"}
  ]
}

REGLAS DURAS:
- "repair_say" SOLO si de verdad ayuda al operador AHORA (máx 1 por auditoría; puede no haber ninguna).
- "worker_action" SOLO cuando el cerebro rápido CLARAMENTE dejó sin ejecutar una acción consecuente/del mundo real
  (dijo «hecho» en falso, solo tocó un espejo local, o mal-ruteó una gestión) — máx 1 por auditoría. Acompáñalo casi
  siempre de un `repair_say` que le diga al operador, con naturalidad, que ahora te pones con ello de verdad. NO lo
  uses si la tarea ya se escaló/está en marcha, ni para simple charla, ni por una duda: ante la duda, NO dispares.
  NUNCA para ABRIR / MOSTRAR / VER / LEER / CARGAR / gestionar un mensaje o un widget que YA EXISTE (p.ej. «muéstrame
  el mensaje nuevo de X», «abre la mensajería»): eso es un `[[show:ID]]` del FlashBrain, NO trabajo de worker ni de
  GENERAR código — un worker_action ahí construye un widget basura. Solo CREAR/MODIFICAR el CÓDIGO de un widget
  («créame/modifícame un widget») es tarea de generar; mostrar/leer contenido existente jamás lo es.
- "finding" para todo defecto REPETIBLE del sistema (mal routing, prompt que confunde, dato mal guardado…).
- NUNCA propongas modificar el prompt de sistema en caliente ni te dirijas a ti mismo: los findings van al
  equipo de desarrollo.
- Si el tramo está bien, devuelve {"assessment": "...", "corrections": []}.
- JSON puro. Sin texto fuera del JSON."""


def parse(raw: str) -> dict | None:
    """Model JSON → dict, tolerating accidental fences. None if there is no usable JSON."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        out = json.loads(s[i:j + 1])
        return out if isinstance(out, dict) else None
    except Exception:
        return None


def validate(parsed: dict) -> tuple[list[dict], list[dict]]:
    """→ (F1-applicable, downgraded). Fields are capped; unknown types are discarded; future-phase types
    are converted into finding (proposal = the correction the model wanted to apply)."""
    ok: list[dict] = []
    downgraded: list[dict] = []
    said = False
    dispatched = False
    for c in (parsed or {}).get("corrections", [])[:6]:
        if not isinstance(c, dict):
            continue
        t = str(c.get("type") or "").strip()
        if t == "repair_say":
            text = str(c.get("text") or "").strip()[:280]
            if text and not said:
                ok.append({"type": "repair_say", "text": text})
                said = True
        elif t == "worker_action":
            # F2 (V2-061): RE-ROUTE — trigger the correct worker. Max 1 per audit; request required.
            req = str(c.get("request") or "").strip()[:400]
            if req and not dispatched:
                ok.append({"type": "worker_action", "request": req,
                           "reason": str(c.get("reason") or "").strip()[:280]})
                dispatched = True
        elif t == "finding":
            title = str(c.get("title") or "").strip()[:120]
            if not title:
                continue
            ok.append({
                "type": "finding",
                "severity": str(c.get("severity") or "P2")[:3],
                "area": str(c.get("area") or "otro")[:20],
                "title": title,
                "detail": str(c.get("detail") or "")[:800],
                "proposal": str(c.get("proposal") or "")[:800],
            })
        elif t in KNOWN_TYPES:
            # future phase: document as finding, take no action (V2-053 F1→F2→F3 ladder)
            downgraded.append({
                "type": "finding", "severity": "P2", "area": "susurro-fase-futura",
                "title": f"corrección {t} propuesta (aplicador aún no habilitado)",
                "detail": json.dumps(c, ensure_ascii=False)[:800],
                "proposal": "habilitar en F2/F3 si el patrón se repite",
            })
    return ok, downgraded
