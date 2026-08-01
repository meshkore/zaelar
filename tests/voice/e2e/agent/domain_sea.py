#!/usr/bin/env python3
"""Mar de testing por DOMINIOS (INI-013) — parte del universo de simulación de conversación.
Mar de testing por dominios — simulación de conversación por el canal PROBE (rápido, alto volumen).
Genera N parafraseos NATURALES por semilla (vía AIMLAPI, como usuarios reales) → ejercita el MISMO FlashBrain,
router, rails, tools, memoria-estado y Susurro → auto-marca fallos de routing. Uso:
  ./.venv/bin/python .../sea.py <domains|all> <n_paraphrases>
"""
import os, sys, json, time, urllib.request, concurrent.futures as cf

BASE = "http://localhost:43917"
from tests.voice.e2e.agent import llm  # DRIVE vía AIMLAPI (UA-spoof incluido)

def post(path, body, t=45):
    r = urllib.request.Request(BASE+path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read().decode())

def probe(text, session):
    t0 = time.time()
    r = post("/api/flash/say", {"text": text, "session": session, "ingest": False})
    return {"action": r.get("action", ""), "reply": (r.get("reply") or ""), "ms": round((time.time()-t0)*1000)}

# ---- expectativas por dominio: (nombre, semilla, verificador(action)->ok, descripción) ----
def is_(x):   return lambda a: a == x
def pre(x):   return lambda a: a.startswith(x)
def notin(*xs): return lambda a: all(x not in a for x in xs)
def anyof(*xs): return lambda a: any(a == x or a.startswith(x) for x in xs)

SEEDS = [
    # dominio, semilla, verificador, por-qué
    ("mem",    "¿qué coche tengo?",                       notin("widget_data","escalate"), "pregunta de dato → responder, no actuar"),
    ("mem",    "¿cómo me llamo?",                          notin("widget_data","escalate"), "identidad → chat"),
    ("mem",    "dime cuándo es la cita de la ITV",         notin("widget_data"),            "recuperar dato ≠ widget_data/Hecho"),
    ("mem",    "¿qué tienes apuntado de mí?",              notin("widget_data"),            "recuperar ≠ Hecho"),
    ("web",    "¿quién ganó la última carrera de F1?",     is_("search"),                    "dato del mundo → web_search"),
    ("web",    "¿qué tiempo hará mañana en Soria?",        is_("search"),                    "tiempo → web_search"),
    ("math",   "¿cuánto es el 15% de 340?",                notin("search","widget_data","escalate"), "cálculo → él mismo"),
    ("math",   "¿cuántos días hay en tres semanas?",       notin("search","escalate"),      "cálculo simple → chat"),
    ("chat",   "cuéntame un chiste corto",                 is_("chat"),                      "charla"),
    ("chat",   "hola, ¿qué tal?",                          is_("chat"),                      "saludo"),
    # ---- WIDGETS: mostrar / cerrar / CREAR (código→escala) / MODIFICAR (código→escala) ----
    ("show",   "abre el reloj",                            pre("canvas:show"),               "mostrar widget existente"),
    ("show",   "muéstrame la agenda",                      anyof("canvas:show","escalate"),  "mostrar agenda"),
    ("show",   "pon el tiempo en pantalla",                anyof("canvas:show","search"),    "mostrar/dar el tiempo"),
    ("show",   "quiero ver mis tareas",                    anyof("canvas:show","escalate"),  "mostrar tareas"),
    ("close",  "cierra el reloj",                          anyof("canvas:close","chat"),     "cerrar widget nombrado (no escalar)"),
    ("close",  "quita el reloj de en medio",               anyof("canvas:close","chat"),     "quita = cerrar (no borrar)"),
    ("close",  "cierra el widget de música, has puesto un videoclip", anyof("canvas:close","chat"), "cerrar+queja NO escala a código"),
    ("create", "créame un widget para contar calorías",    is_("escalate"),                  "crear widget nuevo → escala"),
    ("create", "hazme un panel para seguir mis gastos del mes", is_("escalate"),             "crear panel → escala"),
    ("create", "necesito un widget que cuente los días hasta mi cumpleaños", is_("escalate"),"crear widget → escala"),
    ("modify", "cámbiale el color de fondo al widget del tiempo", is_("escalate"),           "modificar CÓDIGO de widget → escala"),
    ("modify", "añádele una columna de prioridad al widget de tareas", is_("escalate"),      "modificar código → escala"),
    ("music",  "pon música de Joaquín Sabina",             is_("music"),                     "música"),
    ("music",  "ponme algo de rock para concentrarme",     is_("music"),                     "música difusa"),
    ("style",  "sé más breve al responderme",              anyof("style","chat","canvas"),   "directiva de estilo"),
    ("video",  "pon el vídeo de Despacito",                 anyof("video","canvas:show"),     "vídeo → play_video/youtube"),
    # ---- V2-057: restricción TEMPORAL comprobable (el último / de hoy / actual) → ruta que la certifica ----
    ("latest", "reproduce el último vídeo de José Luis Cárpatos", anyof("video","canvas:show"), "último vídeo → youtube (orden por fecha, tarjeta con fecha)"),
    ("latest", "pon el vídeo más reciente de La Vecina Rubia",     anyof("video","canvas:show"), "más reciente → youtube por fecha"),
    ("latest", "¿qué tiempo hace hoy en Tarragona?",         is_("search"),                    "tiempo de HOY → web_search anclado a hoy"),
    ("latest", "dime la cotización actual del Ibex 35",       is_("search"),                    "dato vigente → web_search now-forward"),
    # ---- MARKETPLACES REALES: navegar un catálogo (no hay buscador que dé el dato) → escalate (navegador) ----
    ("market", "búscame pisos de alquiler en Idealista en Barcelona por menos de 1200 al mes", is_("escalate"), "idealista → navegador"),
    ("market", "mira en Idealista pisos en venta de 3 habitaciones en Valencia",               is_("escalate"), "idealista compra → navegador"),
    ("market", "busca en coches.net un Golf diésel de segunda mano por menos de 15.000",        is_("escalate"), "coches.net → navegador"),
    ("market", "en AutoScout enséñame un BMW Serie 3 familiar de 2019 en adelante",             is_("escalate"), "autoscout → navegador"),
    ("market", "búscame en Wallapop una bici de montaña de menos de 300 euros",                 is_("escalate"), "wallapop → navegador"),
    ("market", "busca motos de enduro en Wallapop cerca de Soria",                              is_("escalate"), "wallapop moto → navegador"),
    ("market", "en Milanuncios busca un sofá de segunda mano en Madrid",                        is_("escalate"), "milanuncios → navegador"),
    ("market", "búscame en Amazon unos auriculares con cancelación de ruido por menos de 100",  is_("escalate"), "amazon → navegador"),
    ("market", "encuéntrame un piso para comprar en Sevilla, dos habitaciones, con terraza",    is_("escalate"), "compra piso (sin nombrar web) → navegador"),
    # ---- investigación / informe A FONDO → escalate ----
    ("deep",   "hazme un informe comparando los tres coches eléctricos más vendidos este año",  is_("escalate"), "informe a fondo → escala"),
    ("deep",   "investiga a fondo qué barrio de Málaga es mejor para alquilar",                 is_("escalate"), "investigación → escala"),
    ("ml_en",  "what car do I have?",                       notin("widget_data","escalate"),  "EN memoria → chat"),
    ("ml_en",  "who won the last F1 race?",                 is_("search"),                    "EN mundo → search"),
    ("ml_en",  "open the clock",                            pre("canvas:show"),               "EN mostrar widget"),
    ("ml_en",  "find me a cheap flat to rent in Madrid on Idealista", is_("escalate"),         "EN marketplace → navegador"),
    ("ml_ca",  "quin cotxe tinc?",                          notin("widget_data","escalate"),  "CA memoria → chat"),
    ("ml_fr",  "quelle heure est-il a Madrid?",             notin("widget_data","escalate"),  "FR hora → chat/search"),
]

def paraphrases(seed, n):
    """N parafraseos NATURALES de la semilla, como los diría un humano distinto (registro variado)."""
    if n <= 1:
        return [seed]
    try:
        msgs = [{"role": "system", "content":
                 "Eres un generador de variantes. Devuelve SOLO un array JSON de N frases: parafraseos NATURALES y "
                 "VARIADOS de la frase dada, como los diría gente distinta (coloquial, formal, con muletillas, "
                 "elipsis, etc.), MANTENIENDO EXACTAMENTE LA MISMA INTENCIÓN/acción (no cambies pedir-cerrar por pedir-abrir, etc.). Español de España. Sin numerar, solo el array JSON."},
                {"role": "user", "content": f"N={n}. Frase: «{seed}»"}]
        out = llm.call(msgs, max_tokens=500, temperature=1.0)
        s = out[out.find("["): out.rfind("]")+1]
        arr = json.loads(s)
        arr = [str(x).strip() for x in arr if str(x).strip()]
        return ([seed] + arr)[:n] if arr else [seed]
    except Exception:
        return [seed]

def run(domains, n):
    seeds = [s for s in SEEDS if domains == "all" or s[0] in domains.split(",")]
    print(f"== MAR DE TESTING == dominios={domains} · semillas={len(seeds)} · parafraseos/semilla={n}")
    # pre-generar parafraseos en paralelo
    variants = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(paraphrases, s[1], n): i for i, s in enumerate(seeds)}
        for fut in cf.as_completed(futs):
            variants[futs[fut]] = fut.result()
    fails, total, lat = [], 0, []
    by_dom = {}
    for i, (dom, seed, check, why) in enumerate(seeds):
        for j, utt in enumerate(variants.get(i, [seed])):
            sess = f"sea-{dom}-{i}-{j}"
            post("/api/flash/reset", {"session": sess})
            try:
                r = probe(utt, sess)
            except Exception as e:
                r = {"action": f"ERR:{str(e)[:30]}", "reply": "", "ms": 0}
            total += 1; lat.append(r["ms"])
            ok = False
            try: ok = check(r["action"])
            except Exception: ok = False
            d = by_dom.setdefault(dom, [0, 0]); d[0] += 1; d[1] += 1 if ok else 0
            if not ok:
                fails.append((dom, utt, r["action"], r["reply"][:50], why))
    print(f"\n-- RESULTADO: {total} turnos · fallos {len(fails)} · lat p50 {sorted(lat)[len(lat)//2]}ms p90 {sorted(lat)[int(len(lat)*0.9)]}ms --")
    print("por dominio (ok/total):")
    for dom, (t, o) in sorted(by_dom.items()):
        flag = "" if o == t else "  <-- REVISAR"
        print(f"  {dom:8} {o}/{t}{flag}")
    if fails:
        print(f"\n-- FALLOS ({len(fails)}) --")
        for dom, utt, act, rep, why in fails:
            print(f"  [{dom}] «{utt[:52]}» → {act}  | {rep}  [esperado: {why}]")
    return fails

if __name__ == "__main__":
    dom = sys.argv[1] if len(sys.argv) > 1 else "all"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    run(dom, n)
