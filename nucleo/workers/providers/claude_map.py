"""How the Claude Code stream is READ: one stream-json line to the normalised WorkerEvent vocabulary, its steps
and its result text. Part of providers.claude; module names are read through _c."""
from __future__ import annotations

from nucleo.workers.providers import claude as _c


def _map(self, obj: dict):
    """Traduce UN objeto stream-json de Claude a 0..N WorkerEvent. Conservador: lo que no encaja, se ignora."""
    t = obj.get("type")
    if t == "system" and obj.get("subtype") == "init":
        self._native_sid = obj.get("session_id") or ""
        self._model = self._model or obj.get("model") or ""   # init trae el modelo RESUELTO (si spec venía vacío)
        yield self._ev("spawned", native_session_id=self._native_sid, model=self._model)
        return
    if t == "assistant":
        # Derivación de PROGRESO (§v2·E·Q3): cada tool_use → una fase coarse (rec.phase, para el prompt) Y un
        # `step` RICO para la observabilidad (V2-048): DÓNDE trabaja (web/memoria/navegador/código/archivo/zaelar)
        # + QUÉ usa (la tool + su objetivo concreto: URL, query, slot, fichero, ref del navegador). El texto
        # assistant sigue SIN convertirse en say (monólogo interno).
        msg = obj.get("message") or {}
        # REAL MODEL (incident 2026-08-18). Every `assistant` message states which model produced it, and it
        # need NOT be the one we asked for: the run we recorded as `claude-opus-4-8[1m]` was actually performed
        # by `glm-4.7` (the gateway accepts the Claude alias and serves its own). The panel lied about the model
        # and the cost was priced at the alias's rate. `<synthetic>` is discarded: that is the label the CLI puts
        # on messages IT fabricates (the error notice, for one), not a model.
        # `getattr`/`setattr`-safe like the `_tier` reads elsewhere in this file: several call sites build a
        # session with `object.__new__` (no `__init__`) to exercise `_map` in isolation, and a mapper that only
        # works on a fully constructed object is a mapper that cannot be tested — which is how this attribute
        # first shipped broken (caught by the suite, 2026-08-18).
        _m = str(msg.get("model") or "").strip()
        if _m and _m != "<synthetic>":
            self._real_model = _m
        elif not hasattr(self, "_real_model"):
            self._real_model = ""
        # CONSUMO PARCIAL (2026-08-13): cada mensaje `assistant` trae SU `usage`, y el del `result` final es solo
        # la suma (verificado sondeando: 61.969+127 = 62.096). Se emite por mensaje para que un worker que NO
        # llega a su `result` —el caso NORMAL cuando el supervisor lo mata por presupuesto— siga habiendo
        # declarado lo que gastó. Antes, matar a un worker era metrar CERO: una corrida medida quemó 704 s, 256
        # pasos y ~$0,20 de tokens reales y se facturó a €0. La factura no puede depender de que el proceso
        # tenga la cortesía de despedirse.
        if isinstance(msg.get("usage"), dict):
            # CURRENT CONTEXT SIZE (incident 2026-08-18) — different from the accumulated spend above, and
            # conflating the two is exactly what left us blind: spend is SUMMED message by message, but the
            # context is the TOTAL OF THE LAST message (fresh + cache read + cache written). Summing it would
            # give a number that grows without meaning anything; the one that predicts death is this.
            self._ctx_tokens = _c._ctx_size(msg["usage"])
            yield self._ev("usage", usage=msg["usage"], model=self._model,
                           real_model=getattr(self, "_real_model", ""),
                           ctx_tokens=getattr(self, "_ctx_tokens", 0),
                           base_url=(getattr(self, "_tier", None) or {}).get("base_url", ""))
        for block in (msg.get("content") or []):
            if not isinstance(block, dict):
                continue
            # NARRACIÓN del worker (2026-08-02). Hasta hoy solo se traducían los `tool_use`, así que entre que
            # nacía y tocaba su primera herramienta el operador veía un hueco NEGRO (medido: 21 s hasta el primer
            # paso y 2m21s sin una sola fila en una tarea de 5 min). El worker SÍ está hablando todo ese rato —
            # dice qué va a hacer, qué ha encontrado, por qué cambia de plan — y eso es justo lo que hay que ver.
            # Sigue SIN convertirse en `say` (no se habla por voz, §v2·E): es observabilidad pura.
            if block.get("type") == "text":
                txt = " ".join(str(block.get("text") or "").split())
                if txt:
                    yield self._ev("note", text=txt, model=self._model)
                continue
            if block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            tin = block.get("input") or {}
            step = self._tool_step(name, tin)
            lbl = self._tool_phase(name, tin)
            if lbl:                          # "" = no pisar la fase (p.ej. hbnote la fija él mismo, más rica)
                # quiet=True cuando hay `step`: el step ES la fila del panel → no duplicar con la fase coarse,
                # pero rec.phase (el prompt "PROCESOS DE FONDO") SÍ se actualiza con la coarse.
                yield self._ev("phase", label=lbl, quiet=bool(step))
            # EVERY tool_use is remembered by its id, not only the ones that paint a row (2026-09-28, demo
            # pass 30): an `agent_report plan "…under $400…"` has no step, so its rejection fell back to
            # `_last_step` and the log blamed the previous `nav_cli scroll down`, which had succeeded.
            self._steps().setdefault(str(block.get("id") or ""), {
                "tool": name, "where": (step or {}).get("where", ""),
                "cmd": str((tin or {}).get("command") or "")[:220]})
            if step:
                # Se recuerda el ÚLTIMO paso para poder atribuirle su respuesta: el `tool_result` llega en el
                # mensaje siguiente (rol `user`) y NO dice de qué tool era más que por `tool_use_id`.
                # LA ENTRADA, no solo la herramienta. Cuando la puerta de permisos rechaza un comando, el
                # `tool_result` trae el motivo («Contains simple_expansion») y NADA de lo que se intentó —
                # así que desde fuera no se puede distinguir un worker que escribió algo raro de un prompt
                # NUESTRO que se lo enseñó. Cuatro veces la noche del 2026-08-28 hubo que adivinarlo, y dos
                # de esas veces la culpa era nuestra (V2-424 el `&`, V2-426 el `cd`). Solo se guarda, y
                # solo se emite cuando el paso FALLA: ver `session._emit_step_result`.
                _meta = {"tool": name, "where": step.get("where", ""),
                         "cmd": str((tin or {}).get("command") or "")[:220]}
                self._last_step = dict(_meta)
                yield self._ev("step", tool=name, model=self._model, **step)
        return
    if t == "user":
        # LA EVIDENCIA DEL PASO (2026-08-10). Esto se descartaba entero como «ruido interno», y con ello lo
        # único que permite auditar a un worker: qué le CONTESTARON. Se veía «busca en la web: ferry Dénia
        # Ibiza» y «abre esta URL», pero no si volvió el horario correcto o una página de error — un worker que
        # trae basura dejaba el mismo rastro que uno que acierta.
        msg = obj.get("message") or {}
        for block in (msg.get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            meta = self._steps().pop(str(block.get("tool_use_id") or ""), None) \
                or getattr(self, "_last_step", None) or {}
            yield self._ev("step_result", text=self._result_text(block.get("content")),
                           tool=meta.get("tool", ""), where=meta.get("where", ""),
                           cmd=meta.get("cmd", ""),
                           is_error=bool(block.get("is_error")),
                           # el escalón con el que corre ESTA sesión: si sus tools se agotan, hay que culpar al
                           # que las sirve, no al que esté primero en la cadena ahora mismo (tras un relevo son
                           # distintos, y atribuirlo mal manda al operador a mirar el proveedor equivocado)
                           provider=(getattr(self, "_tier", None) or {}).get("name", ""))
        return
    if t == "result":
        summary = obj.get("result") or ""
        ok = obj.get("subtype") == "success" and not obj.get("is_error")
        usage = obj.get("usage") or {}
        # ¿murió por el PROVEEDOR (plan/cuota agotada) y no por la tarea? Hasta hoy ese «API Error … Weekly
        # Limit Exhausted» se le entregaba al operador como si fuera el RESULTADO de su búsqueda, sin alerta
        # ni relevo. Marcar aquí pone el escalón en cooldown, dispara la alerta del panel y deja elegido el
        # siguiente proveedor para el próximo spawn.
        if not ok:
            try:
                from nucleo.workers import providers as _prov
                # BLOWN CONTEXT first (incident 2026-08-18): it is not the provider, it is the size of the
                # context. It takes its own lane — compact and continue — and NEVER `note_failure`, which would
                # put a healthy tier on cooldown and migrate the fault to the next one.
                if _prov.is_context_overflow(str(summary)):
                    yield self._ev("context_full", text=str(summary)[:300],
                                   tokens=int(getattr(self, "_ctx_tokens", 0) or 0))
                else:
                    # V2-713 R4 — ONE classification, carried. This read `if nxt is not None or
                    # classify_failure(summary)`, which had to guess what the layer above already knew —
                    # and guessed wrong for `broken` (recognised by `is_broken_request`, not by
                    # `classify_failure`): a rejected request with no relay put the tier on cooldown and
                    # emitted NOTHING. `note_failure` now answers with the cause, so a cause is a chip.
                    cause = _prov.note_failure(str(summary), self._tier)
                    if cause:
                        yield self._ev("provider_down", text=str(summary)[:300],
                                       provider=cause.get("provider", ""),
                                       kind=cause.get("kind", ""),
                                       next=cause.get("next", ""))
            except Exception:
                pass
        yield self._ev("result", summary=str(summary), ok=bool(ok), usage=usage,
                       cost=obj.get("total_cost_usd"), model=self._model,
                       real_model=getattr(self, "_real_model", ""),
                       base_url=(getattr(self, "_tier", None) or {}).get("base_url", ""))
        yield self._ev("done")
        self._done = True
        return


def _steps(self) -> dict:
    """`tool_use_id` → el paso que lo pidió, para casar cada `tool_result` con SU herramienta.

    Se resuelve PEREZOSAMENTE en vez de confiar en `__init__`: `_map` es el bombeo de eventos del worker y un
    `AttributeError` ahí mata el stream entero de una sesión viva. (Y el test del mapper construye la sesión
    con `object.__new__` a propósito, para probar la traducción pura sin montar colas ni procesos.)"""
    d = getattr(self, "_steps_by_id", None)
    if d is None:
        d = {}
        self._steps_by_id = d
    return d


def _result_text(content) -> str:
    """El cuerpo de un `tool_result`, que llega en dos formas según la tool: un string pelado, o una lista de
    bloques `{type:"text"|"image", ...}`. De las imágenes solo se anota que había una (una captura en base64 no
    cabe en un evento y no se audita leyéndola en el log). Recortado con el presupuesto de `evidence`."""
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(str(b.get("text") or ""))
                elif b.get("type") == "image":
                    parts.append("[imagen]")
    else:
        parts = [str(content or "")]
    try:
        from observability import evidence as _evd
        return _evd.body(" ".join(p for p in parts if p))
    except Exception:
        return " ".join(p for p in parts if p)[:1500]
