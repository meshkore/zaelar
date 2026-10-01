"""The voice turn's TOOL SET: which tools this turn is offered, narrowed to the turn's direction, and the
observability of that budget (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no behaviour change. Every name the block
read from the provider module is read through it (`_p.<name>`), so a patch on the provider still governs it.
`choose_the_tools` takes the turn's locals it read as keyword arguments and returns the ones the rest of
`_run_inner` reads, only when bound.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p


async def choose_the_tools(*, _router, brain, emit, first_turn, had_pending_confirm, llm_metrics, self, text) -> dict:
    try:
        from widgets.navegador import tasks as _nt
        _auth_pending = bool(_nt.login_waiting_id())
    except Exception:
        _auth_pending = False
    # V2-038: ofrece send/stop_worker solo si hay Brain Workers vivos, y answer_worker solo si alguno espera.
    try:
        from nucleo import dispatch as _dispatch, worker_api as _wapi
        _has_workers = _dispatch.has_active()
        _ask_pending = _wapi.has_pending_ask()
    except Exception:
        _has_workers = _ask_pending = False
    # V2-086: las tools de cluster YA NO dependen de tener un widget delante. El gate de V2-064
    # (`cluster-registro` abierto) hacía la capacidad INDESCUBRIBLE — para conectar un cluster NUEVO había que
    # saber de antemano que primero tocaba abrir un widget concreto (pez que se muerde la cola: comprobado en
    # el turno 766 del 2026-08-01, donde `connect_cluster` simplemente no estaba en el set ofrecido y el
    # modelo no pudo hacer nada). La protección real contra el disparo espurio no era ese gate sino la
    # CONFIRMACIÓN Sí/No determinista con el cluster_id a la vista, que sigue intacta.
    _cluster_open = True
    # `cluster_send` sí es situacional, pero por ESTADO REAL: sin cluster conectado no hay a quién escribir.
    try:
        from connectors import meshkore as _mk0
        _cluster_conn = any(c.get("connected") for c in _mk0.get_manager().clusters())
    except Exception:
        _cluster_conn = False
    # V2-085 — tres CAPACIDADES reales más (nunca palabras del turno: hechos del sistema). Todas fail-OPEN:
    # si el sondeo peta, la tool se ofrece igual y no le quitamos nada al operador.
    try:
        from connectors.whatsapp import service as _wa1
        _msg_on = _wa1.enabled()
    except Exception:
        _msg_on = False
    if not _msg_on:
        try:
            from connectors.telegram import service as _tg1
            _msg_on = _tg1.enabled()
        except Exception:
            _msg_on = True                  # no se pudo sondear ninguno → fail-open
    try:
        from memory import vault as _vault1
        _has_vault1 = _vault1.exists()
    except Exception:
        _has_vault1 = True
    try:
        from widgets import runtime as _rt_cap
        _has_video1 = _rt_cap.get("youtube") is not None
    except Exception:
        _has_video1 = True
    _tool_ctx = _router.tool_context(confirm_pending=had_pending_confirm, auth_pending=_auth_pending,
                                     has_workers=_has_workers, ask_pending=_ask_pending,
                                     cluster_widget_open=_cluster_open, messaging_on=_msg_on,
                                     has_vault=_has_vault1, has_video_widget=_has_video1,
                                     cluster_connected=_cluster_conn)
    _turn_tools = _router.tools(_tool_ctx)
    # KICKOFF = saludo PURO, sin tools (fix 2026-07-19): el texto del kickoff ("Salúdame en 1-2 frases, cálido y
    # breve…") lo interpretaba el modelo como `set_style_directive` → guardaba una regla y respondía "Hecho." en
    # vez de saludar. El saludo no necesita ninguna tool → no las ofrecemos y no hay nada que mis-rutear.
    if first_turn:
        _turn_tools = []
    # SELECCIÓN PROGRESIVA (V2-096 F2): el turno lleva la DIRECCIÓN hacia la que va, no el catálogo entero.
    # «Cuando alguien dice "hola, ¿qué tal?" no le vamos a mandar todos los widgets, todas las tools.»
    # Va DESPUÉS del gate por estado (que decide qué capacidades EXISTEN) porque son cosas distintas: el gate
    # niega, esto solo recupera candidatos — y por eso puede mirar las palabras del turno sin romper el
    # invariante de V2-085. Medido sobre los 14 casos del nodo 2.13: **−51,4% de chars de catálogo** y CERO
    # casos que se queden sin ninguna tool aceptable.
    _tool_report: dict = {}
    # V2-726 A5: no Jev verdict enters here any more. The force set is the caller's own
    # (`_force_families`, set by `need_capability`), and `select_for_turn` is off by default
    # since F0a — a full stable catalog caches its ~6.000 tokens from the second turn on.
    if not first_turn:
        try:
            from nucleo.flash import tool_selection as _tsel
            _force_fams = set(getattr(self, "_force_families", None) or ())
            _turn_tools, _tool_report = _tsel.select_for_turn(
                _turn_tools, turn_text=text, window=getattr(brain, "_window", None),
                recent_families=getattr(brain, "_recent_tool_families", None),
                force=_force_fams or None)
            if _tool_report.get("omitted"):
                emit("brain", "🎯 tools recortadas al rumbo del turno", role="system",
                     extra={"cat": "flash", **_tool_report})
        except Exception as e:  # noqa: BLE001
            emit("brain", "⚠️ selección de tools falló — catálogo completo", role="system",
                 extra={"cat": "flash", "err": repr(e)[:120]})
    # OBSERVABILIDAD del presupuesto de tools (V2-085): no solo cuántas — cuánto ocupan, qué familias entraron
    # y cuáles se podaron. Junto a los `sz_*`/`widgets_*` del prompt cierra el desglose completo del turno.
    try:
        llm_metrics.update(_router.tools_report(_turn_tools))
    except Exception:
        llm_metrics["n_tools_offered"] = len(_turn_tools)
    _out = locals()
    return {k: _out[k] for k in ('_auth_pending', '_has_workers', '_tool_ctx', '_turn_tools', ) if k in _out}
