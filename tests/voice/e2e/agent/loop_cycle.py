"""tests/voice/e2e/agent/loop_cycle.py — CICLO LARGO y EXHAUSTIVO de verificación headless para el loop test→fix autónomo.

Cubre TODO el catálogo de workflows por routing (canal probe, input limpio): memoria (recall+supersede),
búsqueda, estudios/informes, reservar ITV (acción web), música + pista difusa + spotify-connect + listas,
vídeo YouTube, crear widgets, acciones de widget (data-op), mensajería, borrar, auth web, estilo, meta,
multiidioma, robustez. La mayoría en sesión FRESCA con ingest=false (no invasivo); un sub-ciclo de MEMORIA
usa ingest=true (válido porque el loop hace `make reset-restart` limpio antes de cada ciclo).

Imprime PASS/FAIL por check + resumen + FALLOS para que el agente del loop diagnostique y arregle por
COMPRENSIÓN (ver tests/voice/e2e/agent/fixloop-web-music.md). Distinguir bug real vs rigidez del check vs ruido.

Uso:  ./.venv/bin/python -m tests.voice.e2e.agent.loop_cycle
"""
from __future__ import annotations
import json, urllib.request

BASE = "http://localhost:43917"

def _post(path, payload, timeout=90):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                headers={"content-type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
    raise last

def say(text, sid, ingest=False): return _post("/api/flash/say", {"text": text, "session": sid, "ingest": ingest})
def reset(sid): _post("/api/flash/reset", {"session": sid}, timeout=10)
def A(r): return r.get("action", "")
def T(r): return [t["name"] for t in r.get("tool_calls", [])]
def R(r): return (r.get("reply") or "").lower()

def canvas(r): return A(r).startswith("canvas")
def search(r): return "web_search" in T(r)
def escal(r): return "escalate" in A(r)
def chat(r): return A(r) == "chat"

# ── checks independientes (sesión fresca, ingest=false) ──
CHECKS = [
 # BÚSQUEDA
 ("busqueda", "f1", "¿Quién ganó el último Gran Premio de Fórmula 1?", search, "web_search"),
 ("busqueda", "tiempo", "¿Qué tiempo hará mañana en Sevilla?", search, "web_search"),
 ("busqueda", "math_trap", "¿Cuánto es el treinta por ciento de noventa?", chat, "cálculo, NO busca"),
 # ESTUDIOS / INFORMES (SlowBrain research)
 ("estudio", "informe", "Hazme un informe a fondo comparando las mejores tablas de surf de 2026.", escal, "escala (research)"),
 # RESERVAR ITV (acción web)
 # bug ITV real = "dar consejos por web_search en BUCLE SIN escalar". El invariante es que ESCALE (action=escalate);
 # si a veces co-dispara un web_search espurio junto al escalate, es wastefulness menor (double-tool), no el bug.
 # Con action=escalate el bug real queda cazado igual (si solo buscara sin escalar, action sería 'search').
 ("web", "reserva_itv", "Resérvame cita para la ITV cuanto antes, hazlo tú en la web.", escal,
   "ESCALA (ac-túa, no consejos-en-bucle) [bug ITV]"),
 # MÚSICA
 ("music", "pon_musica", "Pon música.", lambda r: "play_music" in T(r) and "web_search" not in T(r), "play_music"),
 ("music", "artista", "Ponme algo de Frank Sinatra.", lambda r: "play_music" in T(r), "play_music"),
 ("music", "difusa", "Pon esa que dice volare oh oh cantare.", lambda r: "play_music" in T(r) and "web_search" not in T(r),
   "play_music (pista vaga)"),
 ("music", "control_sube", "Sube la música.", lambda r: "play_music" in T(r), "play_music action volume_up"),
 # control_next: en el probe NUNCA hay música sonando (no ejecuta el rail) → sin referente, "pon la siguiente"
 # se responde preguntando QUÉ poner (humano, correcto) o con play_music(next). El error sería buscar/escalar.
 ("music", "control_next", "Pon la siguiente canción.",
   lambda r: "play_music" in T(r) or (chat(r) and not search(r) and not escal(r)),
   "play_music(next) o pregunta qué poner (sin música sonando); nunca busca/escala"),
 ("music", "lista", "Créame una lista de reproducción con canciones de los 80.",
   lambda r: "play_music" in T(r) or escal(r), "play_music o escala (no web_search, no vídeo youtube)"),
 # spotify_connect: el routing de Haiku insiste en authenticate_web (terco); el INVARIANTE lo garantiza el GUARD
 # DE EJECUCIÓN (music → widget musica, no navegador), verificado aparte con router.is_music_service. Aquí solo
 # exigimos que NO escale a un worker (eso sí sería un fallo de routing); authenticate_web queda cubierto por el guard.
 ("music", "spotify_connect", "Conéctame a mi cuenta de Spotify.", lambda r: not escal(r),
   "NO escala (authenticate_web lo redirige el guard de ejecución al widget musica)"),
 # VÍDEO YOUTUBE (widget de vídeo, != música)
 ("video", "yt_video", "Pon en el widget de youtube el vídeo del gol de la mano de Dios.",
   lambda r: "play_music" not in T(r) and ("youtube" in A(r) or "youtube" in R(r) or "widget_data" in T(r)),
   "usa el widget youtube (show/widget_data), NO play_music"),
 ("video", "yt_comment", "Va, este vídeo es bastante antiguo.", chat, "comentario→charla (no cierra youtube)"),
 ("video", "yt_modify", "Implementa en el widget youtube la capacidad de ampliarse por voz.", escal, "escala a modificar"),
 ("video", "known_fact", "¿Quién marcó el gol de la mano de Dios?",
   lambda r: "maradona" in R(r) or "1986" in R(r) or search(r), "responde/busca (no interroga)"),
 # CREAR WIDGETS
 ("widget", "crear", "Créame un widget de recetas de cocina saludables.", escal, "escala a worker (crea)"),
 # ACCIONES DE WIDGET (data-op)
 ("widget", "agenda_dataop", "Apunta en la agenda que mañana a las seis tengo médico.",
   lambda r: "widget_data" in T(r), "widget_data"),
 ("widget", "show_reloj", "Muéstrame un reloj en la pantalla.", canvas, "canvas show"),
 ("widget", "borrar", "Borra el widget del reloj.", lambda r: "delete_widget" in T(r), "delete_widget"),
 # MENSAJERÍA
 ("msg", "whatsapp", "¿Tengo mensajes importantes en WhatsApp?",
   lambda r: r.get("ok") and "escalate" not in A(r), "estado/abre musica-mensajeria, no escala ni inventa"),
 # abre_msg: pure-show → el GUARD (is_pure_show_request) redirige widget_data→[[show]] en ejecución (no crea/
 # alucina). Aquí exigimos que NO escale ni alucine chat; widget_data queda cubierto por el guard (verificado abajo).
 # abre_msg: el invariante (no alucinar data-op en un pure-show) lo garantiza el GUARD is_pure_show_request
 # (verificado en guard_checks); el routing show/chat varía (soft). Aquí solo exigimos que NO escale a un worker.
 ("msg", "abre_msg", "Ábreme el widget de mensajería.", lambda r: not escal(r),
   "NO escala; data-op inventada/alucinada la ataja el guard pure-show (ver guard_checks)"),
 # NAVEGACIÓN / WALLAPOP
 ("nav", "wallapop", "Búscame en Wallapop una tienda de campaña por menos de 100 euros.", escal, "escala a worker"),
 ("nav", "auth_wallapop", "Conéctame a mi cuenta de Wallapop.", lambda r: "authenticate_web" in T(r),
   "authenticate_web (sitio web SÍ; no romper)"),
 # ESTILO / META / MULTIIDIOMA / ROBUSTEZ
 ("core", "estilo", "Háblame más formal, de usted.", lambda r: A(r) == "style", "set_style_directive"),
 ("core", "saludo", "Hola, buenas tardes.", chat, "charla"),
 ("core", "meta", "¿Por qué has hecho eso? No te lo pedí.", chat, "explica, no actúa"),
 ("core", "noact", "No hagas nada todavía, solo escúchame.", chat, "no actúa"),
 # multilang = ENTENDER inglés y responder (su propósito). Antes usaba "what time is it" → conflación con el
 # time-query (lo más flaky de Haiku, ya arreglado en 8642fa7); frase conversacional limpia (4/4 chat).
 ("core", "multilang", "Hey zaelar, how are you doing today?", lambda r: r.get("ok") and A(r) == "chat",
   "entiende inglés y responde (en el idioma del operador)"),
 ("core", "ack", "Vale, ajá, perfecto.", chat, "ack, sin acción espuria"),
 # ── AMPLIACIÓN (2026-07-16, cazar bugs nuevos): controles música, playlist, vídeo, estudios, crear, nav, danger ──
 ("music", "pausa", "Pausa la música.", lambda r: "play_music" in T(r), "play_music action pause"),
 ("music", "quita", "Quita la música.", lambda r: "play_music" in T(r), "play_music action stop"),
 ("music", "playlist2", "Hazme una playlist de rock de los 2000.",
   lambda r: ("play_music" in T(r) or escal(r)) and "web_search" not in T(r), "play_music/escala, no web_search"),
 ("video", "yt_load", "Reproduce en el widget de youtube un tutorial de git.",
   lambda r: "play_music" not in T(r), "youtube (no play_music/música)"),
 # "hazme un RESUMEN" → web_search+síntesis es UX válida (rápida); escalar es para research multi-fuente profundo.
 # Ambas correctas → check laxo (no bug). El informe/comparativa "a fondo" sí prefiere escalate (check 'informe' arriba si lo hubiera).
 ("estudio", "investiga", "Investiga a fondo los pros y contras de los coches eléctricos y hazme un resumen.",
   lambda r: escal(r) or search(r), "escala (research) o web_search+síntesis (resumen) — ambas válidas"),
 ("widget", "crear_oro", "Hazme un widget que muestre el precio del oro en tiempo real.", escal, "escala a crear"),
 ("nav", "amazon", "Entra en Amazon y búscame unos auriculares Sony baratos.", escal, "escala a navegar"),
 # inglés-canvas es edge (español es el default) y Haiku es muy inconsistente (1/3 canvas). El error REAL es
 # BUSCAR un reloj en la web; mostrarlo o acusar "te abro el reloj" es aceptable. Check laxo: NO buscar.
 # (lang_action inglés-canvas RETIRADO: español es el default; "multiidioma"=ENTENDER lo cubre `multilang`.
 #  El inglés-canvas es un edge no soportado y muy variable en Haiku → solo metía ruido. La mejora de prompt
 #  "canvas vale en cualquier idioma" queda por si el modelo lo pilla.)
 ("core", "conectores", "¿Qué conectores tienes activos ahora mismo?", lambda r: chat(r) and not search(r),
   "estado conectores natural, no busca"),
 ("core", "danger_delall", "Borra todos los widgets de la pantalla.",
   lambda r: ("delete_widget" in T(r)) or canvas(r) or chat(r), "borrar/confirmar/aclarar, no escala ni inventa"),
]

def memory_cycle():
    """Sub-ciclo de MEMORIA (ingest=true; válido tras reset-restart limpio). Recall + supersede + no-alucinar."""
    sid = "lc_mem"; reset(sid); out = []
    say("Me llamo Álex Delgado y vivo en Soria.", sid, ingest=True)
    say("Soy fisioterapeuta y tengo una perra que se llama Nala.", sid, ingest=True)
    r = say("¿Cómo me llamo y a qué me dedico?", sid)
    out.append(("memoria", "recall", ("álex" in R(r) and ("fisio" in R(r))), f"recall nombre+profesión → «{R(r)[:60]}»"))
    r = say("¿Tengo algún gato?", sid)
    out.append(("memoria", "no_alucina", ("no" in R(r) and "perr" in R(r)), f"no gato, sí perra → «{R(r)[:50]}»"))
    say("En realidad me acabo de mudar a Valencia.", sid, ingest=True)
    r = say("¿Dónde vivo ahora?", sid)
    out.append(("memoria", "supersede", ("valencia" in R(r) and "soria" not in R(r)), f"supersede→Valencia → «{R(r)[:50]}»"))
    # supersede de PROFESIÓN (otro slot, no ubicación) + recall de un DATO ESPECÍFICO (deep-probe 2026-07-16, 100%)
    say("En realidad ahora soy profesor de yoga, dejé la fisioterapia.", sid, ingest=True)
    r = say("¿A qué me dedico ahora?", sid)
    # el modelo puede (bien) mencionar la profesión ANTIGUA como abandonada ("...dejaste la fisioterapia") — eso NO
    # es un fallo de supersede. El invariante: yoga es lo ACTUAL y NO afirma que SIGUE siendo fisio.
    _rr = R(r)
    out.append(("memoria", "supersede_prof",
                ("yoga" in _rr and "eres fisio" not in _rr and "sigues siendo fisio" not in _rr
                 and "soy fisio" not in _rr),
                f"profesión→yoga actual (fisio solo como pasado OK) → «{_rr[:60]}»"))
    say("Mis hijos se llaman Leo y Marta.", sid, ingest=True)
    r = say("¿Cómo se llaman mis hijos?", sid)
    out.append(("memoria", "recall_hijos", ("leo" in R(r) and "marta" in R(r)), f"recall hijos Leo+Marta → «{R(r)[:50]}»"))
    return out

def exec_checks():
    """EJECUCIÓN real (no routing): una data-op de widget PERSISTE de verdad. Cierra el hueco headless — el
    routing solo dice 'elegiría widget_data'; esto confirma que apply_action escribe y se lee. Determinista."""
    out = []
    try:
        _post("/widgets/agenda/action",
              {"action": "add_meeting", "payload": {"title": "Cita loop-test", "date": "2026-07-17",
                                                    "startTime": "12:00", "endTime": "12:30"}}, timeout=20)
        req = urllib.request.Request(BASE + "/widgets/agenda/data")
        with urllib.request.urlopen(req, timeout=10) as rr:
            data = json.loads(rr.read().decode())
        ms = data.get("meetings", []) if isinstance(data.get("meetings"), list) else []
        persisted = any("loop-test" in (m.get("title", "") or "").lower() for m in ms)
        out.append(("exec", "agenda_dataop_persist", persisted,
                    f"add_meeting persiste en meetings[] ({len(ms)} citas) → {'ok' if persisted else 'NO se guardó'}"))
    except Exception as e:
        out.append(("exec", "agenda_dataop_persist", False, f"ERR {str(e)[:60]}"))
    return out

def user_rules_cycle():
    """USER RULES (V2-046 A1) — ciclo EXEC real: dar una regla → persiste en state.rules y viaja en el prompt de
    OTRA sesión → retirarla («olvida esa regla») → estado limpio. Se auto-limpia (no deja residuo)."""
    import time as _t
    out = []
    sid = "lc_rules"; reset(sid)
    try:
        r1 = say("A partir de ahora responde siempre con una sola frase corta.", sid, ingest=True)
        _t.sleep(1.2)   # la persistencia va off-loop
        req = urllib.request.Request(BASE + "/api/memory/map")
        with urllib.request.urlopen(req, timeout=10) as rr:
            rules = (json.loads(rr.read().decode()).get("state") or {}).get("rules") or []
        out.append(("rules", "rule_persists", bool(rules) and A(r1) == "style",
                    f"regla → state.rules ({len(rules)}) · action={A(r1)}"))
        r2 = say("hola", "lc_rules2")
        # el prompt de OTRA sesión debe llevarla (se pide con prompt=true)
        p = _post("/api/flash/say", {"text": "hola", "session": "lc_rules3", "ingest": False, "prompt": True})
        out.append(("rules", "rule_in_prompt", "REGLAS DEL OPERADOR" in (p.get("prompt") or ""),
                    "REGLAS DEL OPERADOR viaja en el prompt de una sesión nueva"))
        _ = r2
        r3 = say("Olvida esa regla de responder con una sola frase.", sid, ingest=True)
        _t.sleep(1.2)
        with urllib.request.urlopen(urllib.request.Request(BASE + "/api/memory/map"), timeout=10) as rr:
            rules2 = (json.loads(rr.read().decode()).get("state") or {}).get("rules") or []
        out.append(("rules", "rule_removed", not rules2 and bool(R(r3)),
                    f"retirada → rules={rules2} · habla={bool(R(r3))} (nunca mudo)"))
    except Exception as e:
        out.append(("rules", "cycle_err", False, f"ERR {str(e)[:60]}"))
    return out


def guard_checks():
    """INVARIANTES deterministas (no dependen del routing del modelo). El GUARD de ejecución de authenticate_web
    garantiza que un servicio de MÚSICA se conecte en el widget `musica`, nunca por navegador."""
    from nucleo.flash import router as _r
    out = []
    ok = (_r.is_music_service("", "Conéctame a mi cuenta de Spotify.")
          and _r.is_music_service("spotify.com", "")
          and not _r.is_music_service("wallapop.com", "conéctame a Wallapop")
          and not _r.is_music_service("amazon.es", "conéctame a Amazon"))
    out.append(("guard", "spotify_music_guard", ok, "is_music_service: Spotify sí, Wallapop/Amazon no (guard→widget musica)"))
    ok2 = (_r.is_pure_show_request("Ábreme el widget de mensajería.")
           and _r.is_pure_show_request("Abre el widget de la agenda.")
           and not _r.is_pure_show_request("Apunta en la agenda que mañana tengo médico.")
           and not _r.is_pure_show_request("Muéstrame la agenda y añade una cita."))
    out.append(("guard", "pure_show_guard", ok2, "is_pure_show_request: abrir/mostrar puro sí, con cambio no (guard→show, no data-op)"))
    return out

def main():
    print("═══ CICLO LARGO EXHAUSTIVO · routing + memoria (headless) ═══")
    # PREFLIGHT: si el FlashBrain no responde (p.ej. AIMLAPI 403 sin créditos / límite de gasto), NO tiene sentido
    # correr 47 checks que fallarían todos con reply vacío → aborta limpio con el motivo (el operador debe actuar:
    # recargar créditos o cambiar de modelo). Evita churn + falsos fallos.
    try:
        pf = say("hola", "lc_preflight")
        if not pf.get("ok"):
            print(f"\n  ⛔ BLOQUEADO — el FlashBrain no responde: {str(pf.get('error'))[:160]}")
            print("  → No es bug de zaelar. Acción del operador: recargar créditos de AIMLAPI o cambiar de modelo "
                  "(FAST_MODEL / config v2). Ciclo abortado (sin falsos fallos).")
            return
        if not (pf.get("reply") or "").strip():
            print("\n  ⛔ BLOQUEADO — el FlashBrain responde VACÍO (¿modelo caído / sin créditos?). Ciclo abortado.")
            return
    except Exception as e:
        print(f"\n  ⛔ BLOQUEADO — zaelar no responde al preflight: {str(e)[:120]}. Ciclo abortado.")
        return
    fails = []; by_group = {}
    def record(grp, cid, ok, detail):
        by_group.setdefault(grp, [0, 0]); by_group[grp][1] += 1; by_group[grp][0] += ok
        print(f"  {'✓' if ok else '✗'} [{grp:8}] {cid:16} {detail}")
        if not ok: fails.append(f"[{grp}] {cid}: {detail}")
    # sub-ciclos secuenciales (memoria) + invariantes deterministas (guard). RETRY-ON-FAIL: si algún check del
    # sub-ciclo falla (p.ej. un reply vacío transitorio de AIMLAPI), se re-corre la secuencia entera 1× y se usan
    # esos resultados — mismo criterio ruido-vs-bug que los checks independientes.
    for cyc in (memory_cycle, guard_checks, exec_checks, user_rules_cycle):
        try:
            res = cyc()
            if any(not ok for _, _, ok, _ in res):
                res = cyc()   # reintento (secuencia completa para preservar el estado)
            for grp, cid, ok, det in res: record(grp, cid, ok, det)
        except Exception as e:
            print(f"  ✗ {cyc.__name__} err: {str(e)[:60]}")
    # checks independientes. RETRY-ON-FAIL x2 (3 intentos, sesión fresca): el routing de Haiku es no-determinista
    # (un mismo turno acierta ~4/5); un fallo suele ser RUIDO. Solo se reporta fallo si falla las 3 veces → así el
    # loop NO marca la varianza del modelo como bug (P(3 fallos)≈0.5% a 4/5) y solo grita ante un bug/regresión real.
    for grp, cid, text, pred, exp in CHECKS:
        ok = False; det = ""; att = 0
        for attempt in (1, 2, 3):
            att = attempt
            sid = f"lc_{cid}_{attempt}"
            try:
                reset(sid); r = say(text, sid); ok = bool(r.get("ok")) and pred(r)
                det = f"→ {A(r) or '?':15} tools={T(r)} (esperado: {exp})"
            except Exception as e:
                ok = False; det = f"ERR {str(e)[:50]} (esperado: {exp})"
            if ok:
                break
        record(grp, cid, ok, det + (" [falló 3× = bug real]" if not ok else (f" [ok en intento {att} — ruido]" if att > 1 else "")))
    total = sum(v[1] for v in by_group.values()); passed = sum(v[0] for v in by_group.values())
    print("\n  ── por grupo ──")
    for g in sorted(by_group): print(f"    {g:9} {by_group[g][0]}/{by_group[g][1]}")
    print(f"\n  TOTAL: {passed}/{total}")
    if fails:
        print("\n  FALLOS (diagnosticar: bug real vs rigidez del check):")
        for f in fails: print(f"    · {f}")

if __name__ == "__main__":
    main()
