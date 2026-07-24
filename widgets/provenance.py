# ============================================================================
# provenance.py — WHO ordered a widget change (V2-039 · observabilidad del frontend).
#
# Cada evento de canvas del observador (`kind="widget"`) lleva un campo `src` que dice de dónde salió la orden:
#   "flash"        → el FlashBrain, en un turno de voz/chat (tag [[show/close/move/widget.data]] o tool)
#   "worker:<id>"  → un Brain Worker (nucleo/workers/) vía los puentes (hbweb/hbact/nav_cli / /api/worker/act)
#   "user"         → el operador tocando la UI (abrir/cerrar/mover/redimensionar/botón de un widget)
#   "system"       → ciclo de vida / background / reset / origen desconocido
#
# La mayoría de emits pasan `src` EXPLÍCITO (son llamadas directas a emit()). El ÚNICO punto ciego es el choke
# point de datos `widgets/store.py::save()` — le llega una mutación sin saber quién la pidió (código del widget,
# click de UI, [[widget.data]] del FlashBrain, un worker…). Para atribuirlo sin cambiar la firma de save() ni de
# apply_action (código del widget), el ORIGEN "anota" su intención justo antes de disparar la data-op y save() la
# lee. Registro global (GIL-safe, cross-loop/thread — no depende de contextvars que no propagan a los pools de
# ejecución de los widgets), con TTL corto: si nadie anotó en la ventana, es "system".
# ============================================================================
from __future__ import annotations

import time

_TTL_S = 15.0                          # una intención caduca rápido: atribuye la mutación inmediata, no la siguiente
_intent: dict[str, tuple[str, float]] = {}   # widget_id (base) → (src, ts)


def _base(widget_id: str) -> str:
    # normaliza el id de instancia (navegador::t3 → navegador) para que la anotación y la lectura casen
    return str(widget_id or "").split("::", 1)[0].strip().lower()


def note(widget_id: str, src: str) -> None:
    """El ORIGEN anota que ÉL va a cambiar los datos de este widget AHORA. Best-effort, nunca lanza."""
    try:
        _intent[_base(widget_id)] = (str(src or "system"), time.time())
    except Exception:
        pass


def who(widget_id: str) -> str:
    """Quién pidió el último cambio de este widget dentro del TTL; `system` si nadie anotó (o caducó)."""
    try:
        src, ts = _intent.get(_base(widget_id), ("", 0.0))
        if src and (time.time() - ts) <= _TTL_S:
            return src
    except Exception:
        pass
    return "system"
