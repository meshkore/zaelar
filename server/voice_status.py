# The ⓘ panel's SYSTEM STATUS, in two halves: the brain, the voice and its providers; then memory, the workers,
# connectors and the health log, and the overall light (V2-778 F1, 2026-10-01).
#
# Moved out of `server/voice_api.py::status` (335 lines) with no behaviour change. Every name the halves read from
# `voice_api` is read through it (`_va.<name>`), so a patch on `voice_api` still governs them.
from __future__ import annotations

from server import voice_api as _va


async def brain_and_voice(*, SETTINGS, active, has, health_state) -> dict:
    items = []

    # ── Server (FastAPI) ──────────────────────────────────────────────────────────────────────────────────────
    # If this responds at all the server is up — but the operator asked to SEE it listed, so we surface it plainly.
    items.append({"key": "server", "label": "Servidor · FastAPI",
                  "state": "ok", "detail": f"en línea · puerto {_va.os.getenv('PORT', '43917')}"})

    # ── Version (V2-074) — which code runs on THIS instance (certainty that restart loaded the new code) ──────
    try:
        import version as _ver
        _vi = _ver.info()
        _up = _vi["uptime_s"]
        _up_s = f"{_up // 3600}h {(_up % 3600) // 60}m" if _up >= 3600 else f"{_up // 60}m {_up % 60}s"
        items.append({"key": "version", "label": "Versión", "state": "ok",
                      "detail": f"{_vi['short']} · activa {_up_s}", "extra": _vi})
    except Exception as e:  # noqa: BLE001
        items.append({"key": "version", "label": "Versión", "state": "warn", "detail": f"desconocida ({e})"})

    # ── «Colmena» brain ───────────────────────────────────────────────────────────────────────────────────────
    from config.v2 import active_brain
    brain = active_brain()
    _brain_detail = {"nucleo": "«Colmena» · FlashBrain + brain workers + memoria propia"}.get(brain, f"modo {brain}")
    items.append({"key": "brain", "label": "Cerebro", "state": "ok", "detail": _brain_detail})

    # ── Voice session ─────────────────────────────────────────────────────────────────────────────────────────
    try:
        live = active.count() > 0
    except Exception:
        live = False
    # Voice ALWAYS ON (2026-07-07): there is no longer an "Activate" button — the session starts when the web opens.
    # A recorded session DEATH outranks everything here (2026-09-10): an unrecoverable error closed the
    # AgentSession while the room stayed connected, and this panel kept saying green — the operator's exact
    # complaint («no es normal que el sistema pueda estar arriba» while nothing answers). The client merge
    # (StatusPanel.js) deliberately does NOT overwrite an error state on this row.
    vdead = health_state.get("voice")
    if vdead:
        items.append({"key": "voice", "label": "Sistema de voz", "state": "error",
                      "detail": "la sesión MURIÓ — reciclando el motor; recarga la página si no vuelve"})
    else:
        items.append({"key": "voice", "label": "Sistema de voz",
                      "state": "ok" if live else "off",
                      "detail": "sesión activa" if live else "en espera · se activa al abrir la web"})

    # ── LLM provider (the fast-layer model driving the conversation) ─────────────────────────────────────────
    # With BRAIN=nucleo, the fast-layer model is PER INVOCATION (config/v2 `fast`, UI-managed); here we show the
    # configured default.
    llm_err = health_state.get("llm")
    # REAL provider + key from the fast-layer ModelSpec (provider-agnostic: xAI / Groq / AIMLAPI / Gemini /
    # Ollama-local) — do not hardcode "AIMLAPI" (invariant: status reflects the provider in use).
    prov_label = "nube"; llm_key = True; model_name = SETTINGS.llm_model or _va.os.getenv("LLM_MODEL", "?")
    if brain == "nucleo":
        try:
            from nucleo.flash.fast_client import spec_from_config
            _spec = spec_from_config()
            model_name = _spec.model or model_name
            _url = _spec.resolved_base_url().lower()
            prov_label = ("Ollama·local" if _spec.is_local() else "DeepSeek" if "deepseek" in _url
                          else "xAI" if "x.ai" in _url
                          else "Groq" if "groq" in _url else "Gemini" if "googleapis" in _url or "generativelanguage" in _url
                          else "nube")
            llm_key = _spec.is_local() or bool(_spec.resolved_api_key())
        except Exception:
            prov_label = "nube"
    else:
        llm_key = has("AIMLAPI_KEY", "LLM_API_KEY")
    llm_detail = f"{model_name} · {prov_label}"
    if llm_err and llm_err.get("kind") == "slow":
        # ONE STUCK TURN ≠ PROVIDER NOT RESPONDING (2026-08-12). The turn silence deadline recorded the cut as if
        # the model were down → the ◉ stayed RED with "not responding" while the model answered perfectly before
        # and after. This is a WARNING with the concrete fact, not an outage diagnosis.
        state = "warn"; llm_detail += " · " + (llm_err.get("text") or "un turno se atascó")
    elif llm_err:
        state = "error"
        llm_detail += " · " + {"credit": "SIN SALDO/cuota", "auth": "credencial inválida"}.get(llm_err["kind"], "no responde")
    elif not llm_key:
        state = "warn"; llm_detail += " · falta API key"
    else:
        state = "ok"; llm_detail += " · key ✓"
    # V2-750 — AMBER IS NOT RED, AND THE BOX SAYS WHO IS ANSWERING. Operator, 2026-09-22: «más que ponerse en
    # rojo, me pondría por ejemplo en amarillo y diría: ahora mismo el modelo principal está caído y está
    # actuando el segundo modelo. Y sacaría en esa cajita dos líneas — este no responde, en rojo, y debajo en
    # verde: ahora estás funcionando a través de este otro modelo».
    #
    # The distinction is real and the old row could not make it: a titular down WITH a stand-in answering is a
    # degraded system that works, and a titular down WITHOUT one is an agent that cannot think. Painting both
    # red taught him to read red as «probably still fine», which is how a light stops being a light.
    #
    # The two lines travel as DATA (`extra.titular` / `extra.serving`), not as a composed sentence: the panel
    # writes them in the operator's own language from the i18n table, which is where a sentence he reads
    # belongs (the V2-676 lesson — this row's own `detail` is still a Spanish literal, older debt, untouched).
    # V2-758 — THE LADDER IS READ ON EVERY POLL, NOT ONLY WHEN THE LIGHT IS ALREADY ON. Operator, 2026-09-23:
    # «tiene que haber una cajita solo para el flash brain que se muestre que estamos llamando al v4 flash como
    # principal, y también tiene que haber el modelo failover… cuando falla el primero pones el segundo y ya me
    # marcas el amarillo».
    #
    # The old version only looked inside `if state in ("error","warn")`, and that hid the case he cares about
    # MOST: once the stand-in answers, `fast_client` clears the model light on the first chunk (a provider DID
    # reply), so a successfully relayed turn painted the row GREEN — the engine running on the substitute and
    # the panel saying everything was fine. WHO IS ANSWERING is a fact about the ladder, not about whether an
    # error is still fresh, so it is read from the ladder every time.
    llm_extra = None
    try:
        from nucleo.flash import provider_chain as _pc
        _ch = _pc.chain(_pc.ROLE_VOICE)
        _serving = _pc.pick(_pc.ROLE_VOICE)
        if _ch and _serving and _serving.get("name") != _ch[0].get("name"):
            # A stand-in is answering: degraded, and that is AMBER, never red. A titular down WITH a stand-in
            # answering is a system that works; painting it red teaches him to read red as «probably fine».
            state = "warn"
            llm_extra = {"titular": {"model": _ch[0].get("model"), "provider": _ch[0].get("provider")},
                         "serving": {"model": _serving.get("model"), "provider": _serving.get("provider")}}
        elif _ch:
            # Healthy, or down with nobody behind: name the primary, and the stand-in when there is one, so he
            # can see the ladder EXISTS before the day it has to work.
            llm_extra = {"titular": {"model": _ch[0].get("model"), "provider": _ch[0].get("provider")},
                         "titular_ok": bool(_serving and _serving.get("name") == _ch[0].get("name"))}
            # «Relevo listo» is a PROMISE, so it is only made about a rung that could actually take over. With
            # both tiers in cooldown `pick()` returns None, the titular line goes red, and offering a stand-in
            # that is equally down would be the panel telling him he is covered when he is not — «si fallaran
            # los dos, entonces sí que habría que marcarlo en rojo».
            if len(_ch) > 1 and _pc.tier_available(_ch[1]):
                llm_extra["standby"] = {"model": _ch[1].get("model"), "provider": _ch[1].get("provider")}
    except Exception:  # noqa: BLE001 — a status row must never be the thing that breaks
        llm_extra = None
    _llm_item = {"key": "llm", "label": "Cerebro rápido · FlashBrain", "state": state, "detail": llm_detail}
    if llm_extra:
        _llm_item["extra"] = llm_extra
    items.append(_llm_item)

    # ── A BUG OF OURS GETS ITS OWN ROW (V2-758) ─────────────────────────────────────────────────────────────
    # It only exists when there IS one: a permanently green «engine: fine» row is noise, and noise is how a
    # panel stops being read. When it appears it NAMES the exception, because that is the whole difference
    # between «tengo que saber qué pasa» and the five days this defect went unnoticed under a provider's name.
    _eng = health_state.get("engine")
    if _eng:
        items.append({"key": "engine", "label": "Motor · fallo interno", "state": "error",
                      "detail": (_eng.get("text") or "un turno falló dentro del motor")[:160]})
    _out = locals()
    return {k: _out[k] for k in ('brain', 'items', ) if k in _out}


async def the_rest_and_the_light(*, SETTINGS, brain, has, health_state, items) -> dict:
    try:
        from nucleo import mem_processor
        _mp = mem_processor.status()
        mem_err = health_state.get("memory")
        # ONE LIGHT, FOURTEEN WRITERS (2026-09-10). `health_state["memory"]` is a key SHARED by the heart, REM,
        # the retriever, the embedding backend and the turn's recall budget — facts with nothing in common. This
        # row used to render EVERY one of them as the heart's canned outage line, which stated something FALSE:
        # measured live on the operator's engine, it read «gpt-4.1-mini · 0 fallos — escribiendo por heurística»
        # while the heart was distilling pills normally and the real fact was a recall that missed its 0.8 s
        # budget (0.6 % of turns, and each one held the light red for the full 600 s TTL — which is why the panel
        # looked broken one time in two). «0 fallos» inside an outage headline is the tell that the two halves of
        # the sentence came from different places.
        #
        # So the row is built from WHO recorded the fact, not from the fact merely existing:
        #   · the heart's own outage keeps the red AND the narrative — there it is true;
        #   · any other `outage` is red too, but IN ITS OWN WORDS (e.g. «rem: sin proveedor …»);
        #   · a `degraded` record is AMBER — a relay, a slow recall or a degraded vector space is a warning, not
        #     an outage, and painting warnings red is how a light stops being read at all.
        _mem_says = (mem_err or {}).get("text") or ""
        if _mp.get("degraded"):
            mem_state = "error"
            mem_detail = f"{_mp['model']} · {_mp['fail_streak']} fallos — escribiendo por heurística"
        elif mem_err and mem_err.get("kind") == "outage":
            mem_state = "error"
            mem_detail = f"{_mp['model']} · {_mem_says or 'sin proveedor'}"[:160]
        elif _mp.get("fail_streak"):
            mem_state, mem_detail = "warn", f"{_mp['model']} · {_mp['fail_streak']} fallo(s) recientes"
        elif mem_err:
            # V2-762 — NOT prefixed with the heart's model: a slow recall (remote embeddings), a degraded vector
            # space or REM is not the distiller, and «deepseek-flash · el recall no cerró» blamed it by position.
            mem_state = "warn"
            mem_detail = (_mem_says or "degradada")[:160]
        else:
            mem_state, mem_detail = "ok", f"{_mp['model']}"
        # Whether the heart's TITULAR is answering is the heart's own fact — never the row's colour. Derived from
        # the row, an amber recall read «deepseek no responde» all afternoon (2026-09-24) over a heart that was
        # writing every pill normally.
        _heart_ok = not (_mp.get("degraded") or _mp.get("fail_streak")
                         or (mem_err and mem_err.get("kind") == "outage"))
        # V2-758 — THE MEMORY BOX SAYS WHO IS WRITING, exactly like the FlashBrain one, and it travels as DATA
        # so the panel writes the two lines in his language. The heart has failed over since 2026-08-19 and the
        # panel could not show it: whoever answered, the row read «deepseek-flash». And amber, never red, while
        # a stand-in is writing — «si fallaran los dos, entonces sí que habría que marcarlo en rojo».
        mem_extra = None
        try:
            from config import models as _mtbl
            _rungs = _mtbl.rungs("memory_writer") or []
            _tit = {"model": _mp.get("model"), "provider": (_rungs[0].get("provider") if _rungs else "")}
            if _mp.get("relayed"):
                if mem_state != "error":
                    mem_state = "warn"          # a stand-in that WRITES is degraded, not down
                mem_extra = {"titular": _tit,
                             "serving": {"model": _mp.get("serving_model"),
                                         "provider": (_rungs[1].get("provider") if len(_rungs) > 1 else "")}}
            else:
                mem_extra = {"titular": _tit, "titular_ok": _heart_ok}
                if len(_rungs) > 1:
                    mem_extra["standby"] = {"model": _rungs[1].get("model"),
                                            "provider": _rungs[1].get("provider")}
        except Exception:  # noqa: BLE001 — a status row must never be the thing that breaks
            mem_extra = None
        _mem_item = {"key": "memory", "label": "Memoria · CORAZÓN", "state": mem_state, "detail": mem_detail}
        if mem_extra:
            _mem_item["extra"] = mem_extra
        items.append(_mem_item)
    except Exception:
        items.append({"key": "memory", "label": "Memoria · CORAZÓN", "state": "warn", "detail": "no disponible"})

    # ── STT / TTS (from the LiveKit engine SETTINGS) ─────────────────────────────────────────────────────────
    stt_prov = SETTINGS.stt_provider
    stt_err = health_state.get("stt")
    stt_needs = {"voxtral": "MISTRAL_API_KEY", "deepgram": "DEEPGRAM_API_KEY"}.get(stt_prov)
    if stt_err:
        stt_state, stt_detail = "error", f"{stt_prov} · {stt_err['kind']}"
    elif stt_needs and not has(stt_needs):
        stt_state, stt_detail = "warn", f"{stt_prov} · falta {stt_needs}"
    else:
        stt_state, stt_detail = "ok", f"{stt_prov}" + (" · key ✓" if stt_needs else " · local/gratis")
    items.append({"key": "stt", "label": "STT · voz→texto", "state": stt_state, "detail": stt_detail})

    try:
        from voice.engine.speech.voices import tts_provider, voices_for
        prov = tts_provider()   # catalog key (kokoro_local → kokoro)
        vs = voices_for(prov)
        cur = vs[int(_va.S.STATE.get("voice", 0)) % len(vs)]["label"]
    except Exception:
        prov, cur = SETTINGS.tts_provider, "?"
    tts_err = health_state.get("tts")
    # elevenlabs was MISSING from this map (2026-09-10): with no key at all — or a revoked one — the row said
    # «ok · Voz ElevenLabs» while every synthesis would 401. Presence here; validity comes from the balance
    # probe recording health_state («auth») when the provider answers 401.
    needs_key = {"cartesia": "CARTESIA_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY",
                 "inworld": "INWORLD_API_KEY"}.get(prov)
    if tts_err:
        tts_state, tts_detail = "error", f"{prov} · {tts_err['kind']}"
    elif needs_key and not has(needs_key):
        tts_state, tts_detail = "warn", f"{prov} · falta {needs_key}"
    else:
        tts_state, tts_detail = "ok", f"{prov} · {cur}"
    items.append({"key": "tts", "label": "TTS · texto→voz", "state": tts_state, "detail": tts_detail})

    # ── OS audio output (operator request 2026-09-10: the monitor must catch «volume at zero») ──────────────
    try:
        from . import system_audio
        _sys_audio = system_audio.status_item()
        if _sys_audio is not None:
            items.append(_sys_audio)
    except Exception:
        pass

    # ── Crons (proactivity · OWN orchestrator loop, nucleo/) ─────────────────────────────────────────────────
    if brain == "nucleo":
        try:
            from nucleo import loop as nucleo_loop
            from nucleo import scheduler
            running = nucleo_loop.is_running()
            n = len(scheduler.list_jobs(active_only=True))
            cron_detail = (f"loop activo · {n} tarea{'s' if n != 1 else ''} programada{'s' if n != 1 else ''}"
                           if running else "loop detenido")
            items.append({"key": "cron", "label": "Crons · proactividad",
                          "state": "ok" if running else "warn", "detail": cron_detail})
        except Exception:
            items.append({"key": "cron", "label": "Crons · proactividad", "state": "warn", "detail": "no disponible"})

    # ── Widgets (full-stack service) ─────────────────────────────────────────────────────────────────────────
    try:
        from widgets import runtime as widgets_runtime
        wcount = len(widgets_runtime.catalog())
        items.append({"key": "widgets", "label": "Widgets",
                      "state": "ok", "detail": f"{wcount} disponible" + ("s" if wcount != 1 else "")})
    except Exception:
        items.append({"key": "widgets", "label": "Widgets", "state": "off", "detail": "sin catálogo"})

    # ── MeshKore cluster ─────────────────────────────────────────────────────────────────────────────────────
    try:
        from connectors import meshkore
        clusters = meshkore.get_manager().clusters()
    except Exception:
        clusters = []
    if clusters:
        conn = [c for c in clusters if c.get("connected")]
        cl_detail = ", ".join(f"{c['name']}·{'/'.join(c.get('online') or []) or 'sin peers'}" for c in conn) or "sin conexión"
        items.append({"key": "cluster", "label": "Cluster MeshKore",
                      "state": "ok" if conn else "off", "detail": cl_detail})
    else:
        items.append({"key": "cluster", "label": "Cluster MeshKore", "state": "off", "detail": "sin clusters"})

    # ── Registro (V2-711 T0.5) — what the instrument could not keep ──────────────────────────────────────
    # The durable log and the timeline writer are both BEST-EFFORT by design: bounded queues, dropped
    # before voice is ever slowed. That trade is right and it was invisible — the bus counted its own
    # saturation drops in `stats()` and NOBODY read them, while a failed INSERT and a full observer queue
    # counted nothing at all. A silent loss is a fault that does not exist until an audit needs the rows,
    # so the three numbers are here, in the panel the operator already opens when something feels wrong.
    # WARN and never ERROR: losing log lines degrades the forensics, it does not break the product.
    try:
        from bus import log as _blog
        from voice import observer as _obs
        _ls = _blog.stats()
        _ws = _obs.writer_stats()
        _lost = int(_ls.get("dropped") or 0) + int(_ls.get("insert_failed") or 0) \
            + int(_ws.get("queue_full") or 0) + int(_ws.get("write_failed") or 0)
        _detail = f"{_ls.get('rows', 0)} eventos"
        if _ls.get("suppressed"):
            _detail += f" · {_ls['suppressed']} repeticiones de estado plegadas"
        if _lost:
            _detail += f" · ⚠️ {_lost} perdidos (cola llena o escritura fallida)"
        items.append({"key": "eventlog", "label": "Registro · observabilidad",
                      "state": "warn" if _lost else "ok", "detail": _detail,
                      "extra": {"log": _ls, "timeline": _ws}})
    except Exception as e:  # noqa: BLE001
        items.append({"key": "eventlog", "label": "Registro · observabilidad",
                      "state": "warn", "detail": f"no medido ({e})"})

    # Group items so the panel can show the CORE (what you boot from the terminal — must be up for zaelar to work)
    # above the fold, and SECONDARY features (proactivity, widgets, cluster) below in a quieter section.
    CORE = {"server", "brain", "voice", "llm", "memory", "stt", "tts", "sysaudio"}
    for it in items:
        it["group"] = "core" if it["key"] in CORE else "extra"

    rank = {"error": 3, "warn": 2, "off": 0, "ok": 1}
    worst = max((it["state"] for it in items), key=lambda s: rank.get(s, 0))
    overall = "error" if worst == "error" else "warn" if worst == "warn" else "ok"
    _out = locals()
    return {k: _out[k] for k in ('overall', ) if k in _out}
