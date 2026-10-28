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
        # PROGRESS (§v2·E·Q3): each tool_use → a coarse `rec.phase` AND a rich `step` (V2-048): WHERE + WHAT
        # (tool and its target). Assistant text never becomes a say (inner monologue).
        msg = obj.get("message") or {}
        # REAL MODEL (incident 2026-08-18): each `assistant` message names its model — the run recorded as
        # `claude-opus-4-8[1m]` was `glm-4.7`, mispriced. `<synthetic>` (CLI-made messages) is discarded.
        # `getattr`/`setattr`-safe: tests build sessions via `object.__new__` (caught by the suite, 2026-08-18).
        _m = str(msg.get("model") or "").strip()
        if _m and _m != "<synthetic>":
            self._real_model = _m
        elif not hasattr(self, "_real_model"):
            self._real_model = ""
        # PARTIAL SPEND (2026-08-13): each `assistant` message carries its own `usage` (`result` is the sum,
        # 61.969+127 = 62.096), emitted per message so a worker killed by budget still declared its spend —
        # before, a run of 704 s, 256 steps and ~$0.20 was billed €0.
        if isinstance(msg.get("usage"), dict):
            # CURRENT CONTEXT SIZE (incident 2026-08-18) ≠ accumulated spend: context is the TOTAL of the LAST
            # message (fresh + cache read + cache written), never a sum — this is the number that predicts death.
            self._ctx_tokens = _c._ctx_size(msg["usage"])
            yield self._ev("usage", usage=msg["usage"], model=self._model,
                           real_model=getattr(self, "_real_model", ""),
                           ctx_tokens=getattr(self, "_ctx_tokens", 0),
                           base_url=(getattr(self, "_tier", None) or {}).get("base_url", ""))
        for block in (msg.get("content") or []):
            if not isinstance(block, dict):
                continue
            # Worker NARRATION (2026-08-02): only `tool_use` was translated, leaving a black gap (21 s to the
            # first step, 2m21s without a row in a 5-min task). Observability only, never a voice `say` (§v2·E).
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
            # pass 30): an `cli.report plan "…under $400…"` has no step, so its rejection fell back to
            # `_last_step` and the log blamed the previous `cli.nav scroll down`, which had succeeded.
            self._steps().setdefault(str(block.get("id") or ""), {
                "tool": name, "where": (step or {}).get("where", ""),
                "cmd": str((tin or {}).get("command") or "")[:220]})
            if step:
                # The LAST step is kept so its `tool_result` (next `user` message, linked by `tool_use_id`)
                # can be attributed. The INPUT is kept too, emitted only on FAILURE (`session._emit_step_result`):
                # a permission rejection carries the reason but not the command — on 2026-08-28 the culprit
                # was guessed four times, twice our own prompt (V2-424 `&`, V2-426 `cd`).
                _meta = {"tool": name, "where": step.get("where", ""),
                         "cmd": str((tin or {}).get("command") or "")[:220]}
                self._last_step = dict(_meta)
                yield self._ev("step", tool=name, model=self._model, **step)
        return
    if t == "user":
        # STEP EVIDENCE (2026-08-10): what the worker was ANSWERED was discarded as noise, so a worker bringing
        # back an error page left the same trace as one that got it right.
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
                           # the tier THIS session runs on, not the chain head (they differ after a relay)
                           provider=(getattr(self, "_tier", None) or {}).get("name", ""))
        return
    if t == "result":
        summary = obj.get("result") or ""
        ok = obj.get("subtype") == "success" and not obj.get("is_error")
        usage = obj.get("usage") or {}
        # Died of the PROVIDER (plan/quota exhausted), not the task? «Weekly Limit Exhausted» used to reach the
        # operator as the RESULT. Marking puts the tier on cooldown, alerts the panel and picks the next provider.
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
                    # V2-713 R4 — ONE classification, carried: `classify_failure(summary)` guessed wrong for
                    # `broken` (cooldown, nothing emitted). `note_failure` now answers with the cause → a chip.
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
