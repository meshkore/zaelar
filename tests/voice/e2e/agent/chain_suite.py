"""tests/voice/e2e/agent/chain_suite.py — ITERACIÓN 2 del testing del FlashBrain: HUMANO, FLEXIBLE, ENCADENADO + TRAZAS.

Sube el listón sobre `tests/voice/e2e/agent/loop_cycle.py`: en vez de UNA frase precisa por intención, prueba VARIAS frases
humanas y difusas por intención (como hablaría el operador), verifica que el FlashBrain (la CABEZA del iceberg)
elige la PRIMERA acción correcta que lanza la cadena, INSPECCIONA las INSTRUCCIONES del handoff (el `request` que
recibe el worker / el `query` de la música) y comprueba la TRAZABILIDAD (V2-044): que la frase nace con un trace id
y su decisión queda sellada con él en el timeline.

Filosofía (operador 2026-07-16): el FlashBrain conduce desde arriba; las acciones complejas y el plan encadenado
los ejecutan los workers Claude Code por detrás. Aquí se prueba que:
  1. una frase HUMANA cae en el DOMINIO correcto (música/vídeo/widget/búsqueda/estudio/marketplace/memoria/…);
  2. la PRIMERA acción es la que ARRANCA la cadena adecuada (no charla muda, no navegador para música, no
     alucinar una data-op en un "ábreme X");
  3. cuando ESCALA, el `request` lleva las INSTRUCCIONES del plan (no un escalado vacío);
  4. el estímulo queda TRAZADO (root event + decisión con el mismo trace id).

Lo que el probe NO puede (no ejecuta workers/rails) queda DOCUMENTADO como cadena IDEAL en cada caso — la
verificación de la cadena COMPLETA (worker→web→widget) vive en la observabilidad del camino real (vista Trazas).

Uso:
    ./.venv/bin/python -m tests.voice.e2e.agent.chain_suite                  # sweep completo
    ./.venv/bin/python -m tests.voice.e2e.agent.chain_suite --domains music,chain
    ./.venv/bin/python -m tests.voice.e2e.agent.chain_suite --sample 2       # 2 frases por caso (rotación rápida)
    ./.venv/bin/python -m tests.voice.e2e.agent.chain_suite --trace CHAIN-01 # dump del árbol de traza de un caso
    ./.venv/bin/python -m tests.voice.e2e.agent.chain_suite --json           # resumen máquina (para el cron)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = "http://localhost:43917"
TIMELINE = os.path.join(os.path.dirname(__file__), "..", ".meshkore", "logs", "timeline-latest.jsonl")


# ── canal probe ──────────────────────────────────────────────────────────────────────────────────────────
def _post(path, payload, timeout=90):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def say(text, sid, ingest=False):
    return _post("/api/flash/say", {"text": text, "session": sid, "ingest": ingest})


def reset(sid):
    try:
        _post("/api/flash/reset", {"session": sid}, timeout=10)
    except Exception:
        pass


# ── accesores de resultado ───────────────────────────────────────────────────────────────────────────────
def A(r):
    return r.get("action", "") or ""


def T(r):
    return [t["name"] for t in r.get("tool_calls", [])]


def R(r):
    return (r.get("reply") or "").lower()


def args_of(r, name):
    for t in r.get("tool_calls", []):
        if t["name"] == name:
            return t.get("args", {}) or {}
    return {}


def tool(r, name):
    return name in T(r)


def escal(r):
    return "escalate" in A(r) or tool(r, "escalate_to_slowbrain")


def search(r):
    return tool(r, "web_search")


def chat(r):
    return A(r) == "chat"


def canvas(r):
    return A(r).startswith("canvas")


def video(r):
    """¿el turno mandó el vídeo al widget youtube? (V2-045 tool play_video, o show/data-op de youtube)."""
    return tool(r, "play_video") or "youtube" in A(r) or "youtube" in R(r)


def tags_have(r, action):
    """¿el turno emitió una tag de canvas con esta acción? (show/close/move) — para comandos COMPUESTOS donde el
    `action` derivado se lo lleva una tool (p.ej. play_music) pero además hubo una tag de show/close."""
    return any((t.get("action") or "") == action for t in r.get("tags", []))


def kw(r, *words):
    """¿el `request` del escalado O el `query` de música/búsqueda menciona alguna de estas palabras clave?
    (verifica que las INSTRUCCIONES del handoff describen el plan, no un escalado vacío)."""
    blob = " ".join([
        (args_of(r, "escalate_to_slowbrain").get("request") or ""),
        (args_of(r, "play_music").get("query") or ""),
        (args_of(r, "web_search").get("query") or ""),
        R(r),
    ]).lower()
    return any(w.lower() in blob for w in words)


# ── trazabilidad (V2-044) ────────────────────────────────────────────────────────────────────────────────
def trace_events(tid):
    """Eventos del timeline sellados con este trace id (root + memoria + decisión). Confirma que el estímulo
    nace trazado y su decisión queda encadenada (la cadena COMPLETA worker→web→widget vive en el camino real)."""
    if not tid:
        return []
    out = []
    try:
        with open(TIMELINE, encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("trace") == tid:
                    out.append(ev)
    except Exception:
        pass
    return out


def trace_ok(r):
    """El estímulo nació trazado (hay un trace id) y hay al menos el evento raíz sellado con él."""
    tid = r.get("trace")
    if not tid:
        return False
    evs = trace_events(tid)
    return any(e.get("kind") == "trace" and e.get("extra", {}).get("root") for e in evs) or bool(evs)


# ══ CATÁLOGO ═══════════════════════════════════════════════════════════════════════════════════════════════
# Cada caso: id, domain, intent, phrasings[], head(pred sobre el resultado del probe), chain(cadena IDEAL en
# lenguaje humano — para el informe/roadmap), note(qué invariante caza). head = la PRIMERA acción correcta que
# ARRANCA la cadena. Predicados LAXOS a propósito (varias primeras-acciones válidas): el objetivo es cazar el
# ERROR claro (charla muda, navegador para música, alucinar data-op), no imponer una única ruta.
CATALOG = [
    # ── MÚSICA — reproducir / control ──
    {"id": "MUS-01", "domain": "music", "intent": "reproducir por artista",
     "phrasings": ["Ponme algo de Frank Sinatra.", "Quiero escuchar a Sinatra.", "Échame música de Sinatra, porfa."],
     "head": lambda r: tool(r, "play_music"),
     "chain": "play_music(query≈sinatra) → rail música: control(play) directo o resolver→web→play → widget musica",
     "note": "artista claro → play_music (NO web_search, NO navegador)"},
    {"id": "MUS-02", "domain": "music", "intent": "reproducir difuso por letra",
     "phrasings": ["Pon esa que dice 'volare oh oh cantare'.", "Ponme la que hace 'vuela conmigo', creo que es de Sinatra.",
                   "Esa canción del anuncio que dice 'because you're worth it', ponla."],
     "head": lambda r: tool(r, "play_music") and not search(r),
     "chain": "play_music(query=pista) → rail música resuelve la pista difusa (web) → play",
     "note": "pista difusa → play_music; el rail resuelve, NO web_search en el turno"},
    {"id": "MUS-03", "domain": "music", "intent": "controles de reproducción",
     "phrasings": ["Sube la música.", "Pon la siguiente.", "Pausa la canción.", "Quita la música."],
     "head": lambda r: tool(r, "play_music"),
     "chain": "play_music(action=volume_up/next/pause/stop) → rail música",
     "note": "controles → play_music con action"},
    {"id": "MUS-04", "domain": "music", "intent": "parar del todo",
     "phrasings": ["Para la música ya.", "Basta de música.", "Apaga la música."],
     "head": lambda r: tool(r, "play_music") or canvas(r) or chat(r),
     "chain": "play_music(action=stop) → rail música para a la primera",
     "note": "parar → play_music stop (o hard-interrupt); NUNCA escala ni busca"},

    # ── MÚSICA — listas/favoritos (HUECO conocido: no implementado) ──
    {"id": "LIST-01", "domain": "playlist", "intent": "crear playlist", "gap": True,
     "phrasings": ["Créame una lista con canciones de los 80.", "Hazme una playlist de rock de los 2000.",
                   "Prepárame una lista para correr por la mañana."],
     "head": lambda r: (tool(r, "play_music") or escal(r)) and not search(r),
     "chain": "IDEAL: worker crea/gestiona la playlist en el conector (Spotify) — HOY no implementado",
     "note": "listas → play_music o escala; HUECO de producto (play_music no gestiona listas → posible falso 'Hecho')"},
    {"id": "LIST-02", "domain": "playlist", "intent": "gestionar favoritos", "gap": True,
     "phrasings": ["Guarda esta canción en mis favoritos.", "Añade esto a mi lista de me gusta.",
                   "Empieza a preparar mi lista de canales favoritos."],
     "head": lambda r: (tool(r, "play_music") or escal(r)),
     "chain": "IDEAL: worker gestiona favoritos en el conector — HOY no implementado",
     "note": "favoritos → HUECO de producto; verificar que NO finge 'Hecho' mudo"},

    # ── VÍDEO — YouTube (≠ música) ──
    # V2-045: VÍDEO ya es tool de 1ª clase (play_video) → estos casos vuelven a ACTIVO (fin del defer). Invariante:
    # el vídeo va al widget youtube (play_video / show:youtube / widget_data), NUNCA a play_music.
    {"id": "VID-01", "domain": "video", "intent": "reproducir vídeo por descripción",
     "phrasings": ["Pon el vídeo del gol de la mano de Dios.", "Enséñame el vídeo del aterrizaje del Falcon 9.",
                   "Ponme el tráiler de la última de Dune."],
     "head": lambda r: not tool(r, "play_music") and (video(r) or tool(r, "widget_data") or escal(r) or canvas(r)),
     "chain": "play_video(query) → widget youtube busca+carga+reproduce el vídeo real",
     "note": "vídeo → play_video/widget youtube, NUNCA play_music (música)"},
    {"id": "VID-02", "domain": "video", "intent": "tutorial/contenido youtube",
     "phrasings": ["Reproduce un tutorial de git en el widget de youtube.", "Ponme un vídeo para aprender a hacer pan.",
                   "Busca en youtube un directo de lofi para estudiar y ponlo."],
     "head": lambda r: not tool(r, "play_music") and (video(r) or tool(r, "widget_data") or canvas(r)),
     "chain": "play_video(query) → widget youtube (buscar+cargar) — no música",
     "note": "youtube/play_video, no play_music"},
    {"id": "VID-03", "domain": "video", "intent": "comentario sobre el vídeo (charla)",
     "phrasings": ["Va, este vídeo es bastante antiguo.", "Qué gol más bueno, ¿eh?", "Me encanta esta canción del vídeo."],
     "head": lambda r: chat(r),
     "chain": "charla — NO cierra ni recarga el widget",
     "note": "comentario → charla, sin acción espuria"},
    {"id": "VID-04", "domain": "video", "intent": "cerrar el vídeo (close, no borrar)",
     "phrasings": ["Cierra el widget de youtube.", "Ya no quiero ver esto, ciérralo.", "Quita el vídeo de la pantalla."],
     "head": lambda r: canvas(r) or not (escal(r) or tool(r, "delete_widget")),
     "chain": "[[close]] — cerrar ≠ borrar; no escala",
     "note": "cerrar vídeo → close; NUNCA escala ni borra (delete es permanente)"},

    # ── CADENAS (centro de esta iteración): plan multi-paso desde frase difusa ──
    {"id": "CHAIN-01", "domain": "chain", "intent": "mejor canción de un artista → reproducirla",
     "phrasings": ["Me encanta Frank Sinatra, ¿cuál es su mejor canción? Quiero escucharla.",
                   "¿Cuál es la canción más famosa de Queen? Ponla.",
                   "Dime la mejor canción de los Beatles y reprodúcela, anda."],
     "head": lambda r: tool(r, "play_music") or escal(r) or search(r),
     "chain": "identificar la mejor canción (conocimiento/web) → reproducir en widget musica/youtube",
     "note": "CADENA identificar→reproducir: head válido = play_music (rail resuelve) / escalate (worker) / web_search; "
             "MAL = charla muda o navegador de música"},
    {"id": "CHAIN-02", "domain": "chain", "intent": "peli/vídeo famoso → reproducir en youtube",
     # V2-045: con play_video de 1ª clase, 'ponme una peli/vídeo/algo entretenido' debe ir al widget youtube (VER),
     # no a play_music (OÍR). Válido también buscar/escalar (candidatos). MAL = play_music o charla muda.
     "phrasings": ["Ponme una película divertida y famosa para esta noche.",
                   "Quiero ver un vídeo gracioso y viral.",
                   "Enséñame algo entretenido para desconectar un rato."],
     "head": lambda r: not tool(r, "play_music") and (video(r) or escal(r) or search(r)
                                                       or tool(r, "widget_data") or canvas(r)),
     "chain": "play_video / buscar candidatos → reproducir en widget youtube (VER, no play_music)",
     "note": "peli/vídeo → play_video/youtube o buscar; NUNCA play_music ni charla muda"},
    {"id": "CHAIN-03", "domain": "chain", "intent": "dato del mundo → acción sobre widget",
     "phrasings": ["Mira qué tiempo hará mañana y apúntame en la agenda 'llevar paraguas' si va a llover.",
                   "Busca a qué hora juega el Madrid y créame un recordatorio.",
                   "Averigua el cumple de mi hermana... bueno, apunta en la agenda que la llame el sábado."],
     "head": lambda r: escal(r) or search(r) or tool(r, "widget_data"),
     "chain": "web_search/escala (dato) → widget_data (agenda) — cadena dato→acción",
     "note": "CADENA dato→acción: da un paso real, no charla"},
    {"id": "CHAIN-04", "domain": "chain", "intent": "buscar producto con criterios (marketplace)",
     "phrasings": ["Estoy en Malibú y quiero una tabla de surf de segunda mano por menos de 300 dólares, mírame opciones.",
                   "Búscame una moto de enduro KTM de menos de 5000 euros y dime las mejores.",
                   "Necesito una tabla de windsurf barata en Wallapop, échame un ojo."],
     "head": lambda r: escal(r),
     "chain": "worker navega el marketplace (Wallapop/Craigslist) → extrae anuncios reales → top-3",
     "note": "CADENA marketplace: ESCALA a worker de navegación; verifica request con criterios (precio/producto/zona)",
     "handoff": lambda r: kw(r, "surf", "moto", "enduro", "windsurf", "tabla", "ktm", "wallapop", "malib", "300", "5000")},

    {"id": "CHAIN-05", "domain": "chain", "intent": "música por ánimo/gusto (estado/memoria → reproducir)",
     "phrasings": ["Pon algo que me anime.", "Ponme música para concentrarme.",
                   "Pon lo que suelo escuchar por las mañanas."],
     "head": lambda r: tool(r, "play_music"),
     "chain": "play_music(query≈ánimo/gusto) → rail música; la memoria de gustos (recent_by_source music) afina",
     "note": "música por ánimo/gusto → play_music (NO web_search, NO charla muda)"},

    {"id": "CHAIN-06", "domain": "chain", "intent": "comando COMPUESTO (dos acciones en un turno)",
     "defer": "POR DISEÑO, no bug: el prompt del FlashBrain dice 'UNA cosa por turno' (anti-proliferación, sesión "
              "2026-07-15). Ante 'abre el reloj Y pon jazz' hace una y descarta la otra. La visión de cadenas del "
              "operador (objetivo→pasos: buscar→reproducir, dato→acción) SÍ funciona (CHAIN-01/02/03/04). Soportar "
              "comandos compuestos = RELAJAR ese invariante → decisión de diseño del operador/developer, no del loop.",
     "phrasings": ["Abre el reloj y ponme algo de jazz.", "Pon música relajante y enséñame la agenda.",
                   "Muéstrame un cronómetro y sube el volumen de la música."],
     # invariante: NO ignora una de las dos partes → o hace música + una tag/canvas de show, o al menos ambas señales.
     "head": lambda r: tool(r, "play_music") and (tags_have(r, "show") or canvas(r) or tool(r, "widget_data")),
     "chain": "play_music + [[show:ID]] en el MISMO turno — dos acciones, no una",
     "note": "comando compuesto → ejecuta AMBAS partes (música + show); no ignora una"},
    {"id": "CHAIN-07", "domain": "chain", "intent": "compuesto cerrar + acción",
     "defer": "POR DISEÑO (como CHAIN-06, 'una cosa por turno') + interacción con hard_interrupt: 'cierra todo Y pon "
              "música' → en la voz real attention.hard_interrupt captaría 'cierra todo' → [[close]] y descartaría la "
              "música. Relajar el multi-acción es decisión de diseño del operador/developer, no del loop.",
     "phrasings": ["Cierra todo y pon música tranquila.", "Quita los widgets y ponme rock."],
     "head": lambda r: tool(r, "play_music") and (tags_have(r, "close") or "close" in A(r)),
     "chain": "[[close]] + play_music — limpia el canvas y arranca música",
     "note": "compuesto cerrar+música → close + play_music"},

    # ── BÚSQUEDA directa (dato + síntesis en el turno) ──
    {"id": "SRCH-01", "domain": "search", "intent": "dato factual actual",
     "phrasings": ["¿Quién ganó el último Gran Premio de F1?", "¿Qué tiempo hará mañana en Sevilla?",
                   "¿A cuánto está el euro respecto al dólar hoy?"],
     "head": lambda r: search(r),
     "chain": "web_search → síntesis en el turno (~1-2s, sin tarjeta)",
     "note": "dato del mundo → web_search"},
    {"id": "SRCH-02", "domain": "search", "intent": "cálculo (NO buscar)",
     "phrasings": ["¿Cuánto es el treinta por ciento de noventa?", "Divide 144 entre 12.", "¿Cuántos días hay en tres semanas?"],
     "head": lambda r: chat(r),
     "chain": "cálculo mental en el turno — NO web_search",
     "note": "cálculo → charla, no busca"},
    {"id": "SRCH-03", "domain": "search", "intent": "noticias / actualidad",
     "phrasings": ["¿Qué ha pasado hoy en las noticias?", "Dame las últimas novedades de tecnología.",
                   "¿Hay alguna noticia importante sobre el clima esta semana?"],
     "head": lambda r: search(r),
     "chain": "web_search → síntesis en el turno",
     "note": "noticias/actualidad → web_search"},

    # ── ESTUDIO / INFORME (research profundo → SlowBrain) ──
    {"id": "STUDY-01", "domain": "study", "intent": "informe comparativo a fondo",
     "defer": "El modelo responde INLINE (charla) un informe/comparativa 'a fondo' en vez de escalar a un worker "
              "de research (riesgo de datos obsoletos, cutoff). La descripción de escalate YA cubre 'informe/estudio "
              "a fondo'; forzarlo más sin hardcodear verbos (feedback operador) es criterio del modelo → developer.",
     "phrasings": ["Hazme un informe a fondo comparando las mejores tablas de surf de 2026.",
                   "Prepárame un estudio detallado de los coches eléctricos con más autonomía.",
                   "Investiga a fondo el mercado de las motos de enduro y hazme un dossier."],
     "head": lambda r: escal(r),
     "chain": "worker research: WebSearch/WebFetch múltiples → informe multi-fuente",
     "note": "informe/estudio a fondo → escala; request describe el tema",
     "handoff": lambda r: kw(r, "informe", "estudio", "compar", "surf", "coche", "moto", "enduro", "dossier", "eléctric", "autonom")},

    # ── RESERVAR / ACTUAR EN WEB (ITV) ──
    {"id": "ACT-01", "domain": "webact", "intent": "reservar cita ITV (actuar, no aconsejar)",
     "phrasings": ["Resérvame cita para la ITV cuanto antes, hazlo tú en la web.",
                   "Sácame una cita en la ITV para el coche esta semana.",
                   "Gestióname la cita de la ITV, entra tú a la web y hazlo."],
     # invariante REAL (bug ITV documentado): NO caer en el bucle de consejos por web_search sin escalar. Escalar es
     # lo ideal; una charla que pide datos (qué centro/fecha) también es aceptable ante un 'sácame cita' escueto.
     "head": lambda r: escal(r) or (chat(r) and not search(r)),
     "chain": "worker navega la web de la ITV → rellena → confirma (con gate de irreversibilidad)",
     "note": "reservar ITV → ESCALA (actúa) o pide datos; NUNCA consejos en bucle por web_search"},

    # ── CREAR / MODIFICAR WIDGET (código → SlowBrain) ──
    {"id": "WNEW-01", "domain": "widget_create", "intent": "crear widget nuevo",
     "phrasings": ["Créame un widget de recetas de cocina saludables.", "Hazme un widget con el precio del oro en tiempo real.",
                   "Quiero un widget que me muestre las mareas de la costa."],
     "head": lambda r: escal(r),
     "chain": "worker generador (claude -p) escribe data.py+widget.js → valida → catálogo",
     "note": "crear widget → escala; request describe el widget",
     "handoff": lambda r: kw(r, "widget", "receta", "oro", "marea", "precio")},
    {"id": "WMOD-01", "domain": "widget_modify", "intent": "modificar código de widget",
     "phrasings": ["Implementa en el widget de youtube la capacidad de ampliarse por voz.",
                   "Añádele al widget de la agenda un botón para exportar a PDF.",
                   "Cambia el widget del reloj para que muestre también los segundos."],
     "head": lambda r: escal(r),
     "chain": "worker generador modifica el código del widget (rollback si falla)",
     "note": "modificar CÓDIGO → escala (no data-op)"},

    # ── ACCIONES DE WIDGET (data-op — FlashBrain al instante) ──
    {"id": "WACT-01", "domain": "widget_action", "intent": "añadir cita a la agenda (data-op)",
     # NOTA: "recuérdame que…" NO es agenda (V2-029: auto-ingest lo guarda, sin tool) → no se usa como frase aquí;
     # las frases son ALTAS explícitas de EVENTO con fecha/hora (apunta/añade una cita/reunión).
     "phrasings": ["Apunta en la agenda que mañana a las seis tengo médico.",
                   "Añádeme una reunión el viernes a las diez con el equipo.",
                   "Métele una cita el jueves a las cinco para recoger a los niños."],
     "head": lambda r: tool(r, "widget_data"),
     "chain": "widget_data(add_meeting) → apply_action persiste en state.json (FAST, no escala)",
     "note": "data-op agenda → widget_data (NUNCA escala; es dato, no código)"},
    {"id": "WACT-02", "domain": "widget_action", "intent": "marcar hecho / descartar item (data-op, no código)",
     "phrasings": ["Marca como hecha la tarea del informe.", "Tacha lo del médico de la agenda.",
                   "Descarta ese proyecto para siempre."],
     "head": lambda r: not escal(r),
     "chain": "widget_data(done/drop/drop_project) con refs.py resolviendo el item — FAST, sin confirmación",
     "note": "marcar/descartar item → widget_data; 'para siempre' es ÉNFASIS, NO trabajo de código → NUNCA escala"},
    {"id": "WSHOW-01", "domain": "widget_show", "intent": "mostrar/abrir widget (show puro)",
     "phrasings": ["Muéstrame un reloj en la pantalla.", "Ábreme el widget de la agenda.", "Sácame la calculadora."],
     "head": lambda r: canvas(r) or (not escal(r) and not tool(r, "widget_data")),
     "chain": "[[show:ID]] — abre el widget; NUNCA alucina una data-op",
     "note": "show puro → canvas show; el guard is_pure_show_request impide alucinar data-op"},
    {"id": "WDEL-01", "domain": "widget_delete", "intent": "borrar widget",
     "phrasings": ["Borra el widget del reloj.", "Elimina la tarjeta de la agenda.", "Quítame de en medio el widget del tiempo."],
     "head": lambda r: tool(r, "delete_widget") or canvas(r),
     "chain": "delete_widget → confirmación → lifecycle.delete (FlashBrain, no escala)",
     "note": "borrar widget → delete_widget (determinista, no escala)"},

    # ── MENSAJERÍA ──
    {"id": "MSG-01", "domain": "messaging", "intent": "consultar mensajes (del conector, no buscar)",
     "phrasings": ["¿Tengo mensajes importantes en WhatsApp?", "¿Me ha escrito alguien por Telegram?",
                   "¿Hay algo urgente en mis mensajes?"],
     "head": lambda r: r.get("ok") and not escal(r) and not search(r),
     "chain": "responde del estado del conector (ya triado) o abre el widget mensajeria",
     "note": "mensajería → estado/abre widget; NO escala NI busca en web"},
    # REWRITTEN 2026-08-31 (V2-521): until then this scenario asserted the OPPOSITE of today's contract.
    # Messaging was read-only, so the honest reply was "I can only read" and the head check FAILED any
    # `widget_data` — correct then. Since V2-521 all three connectors send (email threads over SMTP, the
    # WhatsApp bridge's POST /send, Telethon), and the correct chain for a dictated reply IS a `reply`
    # data-op with its confirm gate reading the draft before anything leaves. Keeping the old check would
    # have graded the fixed product as broken. What is STILL not built: resolving a person to a chat when
    # they are not in the widget's live items ("mi madre" with no such chat) — there the honest move is to
    # ask, never to invent a recipient (V2-523, the contacts agenda).
    {"id": "MSG-03", "domain": "messaging", "intent": "dictar una respuesta (envío real con confirmación)",
     "phrasings": ["Responde a mi madre que llego tarde.", "Contéstale a Juan que vale.",
                   "Mándale un mensaje a Ana diciéndole que sí."],
     # El invariante nuevo: la respuesta va por la data-op `reply` (confirm-gate delante) — NUNCA se escala
     # a un worker a "enviar", y NUNCA se afirma enviado sin la data-op. Si el destinatario no resuelve
     # contra los chats vivos del widget, preguntar es conducta correcta (sin tool también vale).
     "head": lambda r: not escal(r),
     "chain": "reply data-op sobre el chat resuelto + confirmación leyendo el borrador; destinatario no "
              "resoluble → pregunta, jamás inventa",
     "note": "dictar respuesta → data-op reply con confirm (V2-521); no escalar a worker; no fingir envío"},
    {"id": "MSG-02", "domain": "messaging", "intent": "abrir mensajería (show puro)",
     "defer": "Referencias INDIRECTAS al widget de mensajería ('enséñame los mensajes' → escala; 'abre WhatsApp' → "
              "widget_data) no mapean a [[show:mensajeria]]: runtime.identify no resuelve 'WhatsApp'/'los mensajes' "
              "al id 'mensajeria', así que el guard pure-show no dispara. 'Ábreme el widget de mensajería' (directo) "
              "sí funciona. Fix limpio = enseñar el mapeo en el brief o alias de identify → developer (no hardcodear).",
     "phrasings": ["Ábreme el widget de mensajería.", "Enséñame los mensajes.", "Abre WhatsApp."],
     "head": lambda r: not escal(r) and not tool(r, "widget_data"),
     "chain": "[[show:mensajeria]] — guard pure-show impide alucinar data-op",
     "note": "abrir mensajería → show; NO escala NI alucina data-op"},

    # ── CONECTAR CUENTAS (auth) — música al widget, web al navegador ──
    {"id": "AUTH-01", "domain": "auth", "intent": "conectar servicio de música (→ widget musica)",
     "phrasings": ["Conéctame a mi cuenta de Spotify.", "Vincula mi Spotify.", "Enlaza mi cuenta de Apple Music."],
     "head": lambda r: not escal(r),
     "chain": "guard is_music_service → widget musica (NUNCA navegador)",
     "note": "auth música → NO escala; el guard de ejecución lo lleva al widget musica"},
    {"id": "AUTH-02", "domain": "auth", "intent": "conectar sitio web (→ navegador)",
     "phrasings": ["Conéctame a mi cuenta de Wallapop.", "Inicia sesión en mi LinkedIn.", "Entra en mi cuenta de Amazon."],
     "head": lambda r: tool(r, "authenticate_web"),
     "chain": "authenticate_web → navegador abre login real en perfil persistente",
     "note": "auth web → authenticate_web (sitio web sí)"},

    # ── ROBUSTEZ — ruido de STT, autocorrección, ambigüedad ──
    {"id": "ROBUST-01", "domain": "robust", "intent": "input GARBLEADO de STT (titubeos, repeticiones)",
     "phrasings": ["Eee ponme po-ponme algo de de Sinatra porfa.", "Va, pon pon música, jazz, eso, jazz.",
                   "Súbe-súbeme un poco la la música anda."],
     "head": lambda r: tool(r, "play_music"),
     "chain": "el ruido de STT no debe romper el routing → play_music igual",
     "note": "STT garbleado → misma acción; robustez a titubeos/repeticiones"},
    {"id": "ROBUST-02", "domain": "robust", "intent": "autocorrección en la MISMA frase (intención FINAL)",
     # todas retractan MÚSICA → invariante único y limpio: NO ejecuta la música retractada (obedece lo FINAL).
     "phrasings": ["Pon música... espera no, mejor enséñame la agenda.",
                   "Ponme algo de jazz... uy no, ¿qué tiempo hace en Sevilla?",
                   "Pon música, bah, mejor cierra todo."],
     "head": lambda r: not tool(r, "play_music"),
     "chain": "toma la intención FINAL tras la autocorrección, no la música retractada",
     "note": "autocorrección → intención final (agenda/tiempo/cerrar), NUNCA la música retractada"},
    {"id": "ROBUST-03", "domain": "robust", "intent": "referencia AMBIGUA sin contexto",
     "phrasings": ["Ponme eso de antes.", "Haz lo de siempre.", "Ya sabes, lo otro."],
     "head": lambda r: chat(r),
     "chain": "sin contexto → pregunta/aclara, NO actúa a ciegas",
     "note": "referencia ambigua sin contexto → charla que aclara, no acción espuria"},

    # ── USER RULES (V2-046 A1) — routing: dar/retirar una regla → set_style_directive (persistencia en loop_cycle) ──
    {"id": "RULE-01", "domain": "rules", "intent": "dar una regla de comportamiento",
     "phrasings": ["A partir de ahora responde solo sí o no.", "Sé mucho más breve cuando me hables.",
                   "Cuando te pida una acción, hazla sin responderme nada.", "Trátame siempre de usted."],
     "head": lambda r: A(r) == "style",
     "chain": "set_style_directive → aplica YA (directiva) + persiste como user rule (state.rules) → REGLAS DEL OPERADOR en cada prompt",
     "note": "regla de comportamiento → set_style_directive (nunca escala, nunca charla-sin-guardar)"},
    {"id": "RULE-02", "domain": "rules", "intent": "retirar una regla",
     "phrasings": ["Olvida esa regla de ser tan breve.", "Quita la regla de responder solo sí o no.",
                   "Ya no hace falta que me trates de usted."],
     "head": lambda r: A(r) == "style" or chat(r),
     "chain": "set_style_directive + guard looks_like_rule_removal → remove_user_rule (match difuso)",
     "note": "retirar regla → style (el guard decide el sentido); chat aceptable si no había regla"},
    {"id": "RULE-03", "domain": "rules", "intent": "orden puntual NO es regla",
     "phrasings": ["Ponme algo de música ya.", "Ábreme la agenda ahora mismo.", "Dime qué hora es."],
     "head": lambda r: A(r) != "style",
     "chain": "una orden puntual ejecuta su acción; NO se convierte en user rule",
     "note": "orden puntual → su acción normal, NUNCA set_style_directive (no polucionar rules)"},

    # ── CORE — estilo / meta / multiidioma / robustez ──
    {"id": "CORE-01", "domain": "core", "intent": "directiva de estilo",
     "phrasings": ["Háblame más formal, de usted.", "A partir de ahora sé más breve.", "Trátame de tú y con más humor."],
     "head": lambda r: A(r) == "style", "chain": "set_style_directive → directiva persiste en la sesión",
     "note": "estilo → set_style_directive"},
    {"id": "CORE-02", "domain": "core", "intent": "multiidioma (entender inglés)",
     "phrasings": ["Hey zaelar, how are you doing today?", "Can you help me with something?", "What's up, zaelar?"],
     "head": lambda r: r.get("ok") and chat(r),
     "chain": "entiende inglés, responde en el idioma del operador — sin acción espuria",
     "note": "inglés conversacional → charla"},
    {"id": "CORE-03", "domain": "core", "intent": "no actuar / ack",
     "phrasings": ["No hagas nada todavía, solo escúchame.", "Vale, ajá, perfecto.", "Espera, déjame pensar."],
     "head": lambda r: chat(r), "chain": "charla — sin acción espuria", "note": "ack/pausa → charla"},
    {"id": "CORE-04", "domain": "core", "intent": "consultar conectores (del estado, no buscar)",
     "phrasings": ["¿Qué conectores tienes activos ahora mismo?", "¿A qué tienes acceso?", "¿Qué apps tienes conectadas?"],
     "head": lambda r: chat(r) and not search(r),
     "chain": "responde del estado (brief de conectores) — no busca en web",
     "note": "conectores → charla del estado, no web_search"},
]


# ── ejecución de un caso ─────────────────────────────────────────────────────────────────────────────────
def run_case(case, sample=None, verbose=True):
    """Corre todas (o `sample`) las frases del caso. Cada frase: probe + retry×3 (varianza del titular de entonces) + traza.
    Devuelve dict con estado GREEN/YELLOW/RED + detalle por frase."""
    phr = case["phrasings"][:sample] if sample else case["phrasings"]
    per = []
    for i, text in enumerate(phr):
        ok = False
        att = 0
        last = None
        for attempt in (1, 2, 3):
            att = attempt
            sid = f"cs_{case['id']}_{i}_{attempt}"
            reset(sid)
            try:
                r = say(text, sid)
                last = r
                ok = bool(r.get("ok")) and bool(case["head"](r))
            except Exception as e:  # noqa: BLE001
                last = {"ok": False, "error": str(e)[:80]}
                ok = False
            if ok:
                break
        handoff = None
        if case.get("handoff") and last and last.get("ok"):
            try:
                handoff = bool(case["handoff"](last))
            except Exception:
                handoff = None
        tr = trace_ok(last) if last and last.get("ok") else False
        per.append({"text": text, "ok": ok, "attempts": att, "action": A(last or {}),
                    "tools": T(last or {}), "handoff": handoff, "trace": tr,
                    "reply": (last or {}).get("reply", "")[:70] if last else ""})
    n_ok = sum(1 for p in per if p["ok"])
    n_flaky = sum(1 for p in per if p["ok"] and p["attempts"] > 1)
    if n_ok < len(per):
        status = "RED"
    elif n_flaky:
        status = "YELLOW"
    else:
        status = "GREEN"
    # handoff fallido degrada a YELLOW (instrucciones pobres) aunque el head acierte
    if any(p["handoff"] is False for p in per) and status == "GREEN":
        status = "YELLOW"
    # clasificación reportada: HUECO (producto no implementado) / DEFER (esperando developer) / activo (RED=actúa YA)
    kind = "gap" if case.get("gap") else ("defer" if case.get("defer") else "active")
    if verbose:
        icon = {"GREEN": "✓", "YELLOW": "~", "RED": "✗"}[status]
        tag = {"gap": " ⌂HUECO", "defer": " ⇢DEFER", "active": ""}[kind]
        print(f"  {icon} [{case['domain']:14}] {case['id']:9} {n_ok}/{len(per)} frases  ({case['intent']}){tag}")
        for p in per:
            if not p["ok"] or p["attempts"] > 1 or p["handoff"] is False:
                flag = "✗" if not p["ok"] else ("H!" if p["handoff"] is False else f"~{p['attempts']}")
                print(f"       {flag} «{p['text'][:58]}» → {p['action'] or '?'} {p['tools']}"
                      + (f"  handoff={p['handoff']}" if p['handoff'] is not None else ""))
    return {"id": case["id"], "domain": case["domain"], "status": status, "intent": case["intent"],
            "chain": case["chain"], "note": case["note"], "n_ok": n_ok, "n": len(per), "per": per,
            "kind": kind, "defer": case.get("defer", "")}


def dump_trace(case_id):
    """Dump del árbol de traza de la 1ª frase de un caso (para VER la trazabilidad, petición del operador)."""
    case = next((c for c in CATALOG if c["id"] == case_id), None)
    if not case:
        print(f"caso {case_id} no existe"); return
    text = case["phrasings"][0]
    sid = f"cs_trace_{case_id}"
    reset(sid)
    r = say(text, sid, ingest=True)   # ingest=True → se ven también las escrituras de memoria trazadas
    tid = r.get("trace")
    print(f"\n═══ TRAZA de {case_id} ═══\n  frase: «{text}»\n  trace: {tid}  ·  action: {A(r)}  ·  tools: {T(r)}")
    print(f"  reply: «{(r.get('reply') or '')[:100]}»")
    time.sleep(0.8)   # deja que la ingesta async selle sus eventos
    evs = trace_events(tid)
    print(f"\n  eventos sellados con {tid} ({len(evs)}):")
    for e in evs:
        sp = e.get("span") or "—"
        print(f"    · [{e.get('kind'):8}] span={sp:10} {(e.get('label') or '')[:70]}")
    print("\n  (el probe NO ejecuta workers/rails → la cadena worker→web→widget completa se ve en el camino REAL,")
    print("   vista Trazas ◷⛓ del /debug. Aquí se confirma que el estímulo NACE trazado y su decisión queda sellada.)")


# ── main ─────────────────────────────────────────────────────────────────────────────────────────────────
def preflight():
    try:
        pf = say("hola", "cs_preflight")
        if not pf.get("ok"):
            print(f"⛔ BLOQUEADO — FlashBrain no responde: {str(pf.get('error'))[:160]}")
            return False
        if not (pf.get("reply") or "").strip():
            print("⛔ BLOQUEADO — FlashBrain responde VACÍO (¿modelo caído/sin créditos?).")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"⛔ BLOQUEADO — zaelar no responde: {str(e)[:120]}")
        return False


def main():
    argv = sys.argv[1:]
    domains = None
    sample = None
    as_json = "--json" in argv
    for i, a in enumerate(argv):
        if a == "--domains" and i + 1 < len(argv):
            domains = set(argv[i + 1].split(","))
        if a == "--sample" and i + 1 < len(argv):
            sample = int(argv[i + 1])
        if a == "--trace" and i + 1 < len(argv):
            if not preflight():
                return
            dump_trace(argv[i + 1])
            return
    if not preflight():
        return
    cases = [c for c in CATALOG if not domains or c["domain"] in domains]
    if not as_json:
        print(f"═══ CHAIN SUITE · {len(cases)} casos · frases humanas + cadenas + trazas ═══")
    results = []
    for c in cases:
        results.append(run_case(c, sample=sample, verbose=not as_json))
    # activos = los que cuentan como PASS/FAIL a actuar; gap/defer se reportan aparte (no son acción del loop).
    active = [r for r in results if r["kind"] == "active"]
    gaps = [r for r in results if r["kind"] == "gap"]
    defers = [r for r in results if r["kind"] == "defer"]
    by_status = {"GREEN": 0, "YELLOW": 0, "RED": 0}
    for r in active:
        by_status[r["status"]] += 1
    reds = [r for r in active if r["status"] == "RED"]
    yellows = [r for r in active if r["status"] == "YELLOW"]
    trace_pass = sum(1 for r in results for p in r["per"] if p["trace"])
    trace_tot = sum(len(r["per"]) for r in results)
    if as_json:
        print(json.dumps({"green": by_status["GREEN"], "yellow": by_status["YELLOW"], "red": by_status["RED"],
                          "reds": [r["id"] for r in reds], "yellows": [r["id"] for r in yellows],
                          "gaps": [r["id"] for r in gaps], "defers": [r["id"] for r in defers],
                          "trace_pass": trace_pass, "trace_tot": trace_tot}))
        return
    print(f"\n  ── resumen (activos) ──  GREEN {by_status['GREEN']}  ·  YELLOW {by_status['YELLOW']}  ·  "
          f"RED {by_status['RED']}   (trazas selladas {trace_pass}/{trace_tot})")
    print(f"      aparte: {len(gaps)} HUECO(s) de producto · {len(defers)} DEFER (esperando developer)")
    if reds:
        print("\n  🔴 RED (falla ≥1 frase las 3 veces — bug real o rigidez del check → ACTÚA):")
        for r in reds:
            print(f"    · {r['id']} [{r['domain']}] {r['intent']}")
            for p in r["per"]:
                if not p["ok"]:
                    print(f"        ✗ «{p['text'][:56]}» → {p['action'] or '?'} {p['tools']}  (ideal: {r['note']})")
    if yellows:
        print("\n  🟡 YELLOW (varianza del titular de entonces o handoff pobre — vigilar, no necesariamente bug):")
        for r in yellows:
            print(f"    · {r['id']} [{r['domain']}] {r['intent']}")
    if defers:
        print("\n  ⇢ DEFER (esperando fix del developer — cuando se cierre, quita el flag y re-testea):")
        for r in defers:
            print(f"    · {r['id']} [{r['domain']}] {r['intent']} — {r['status']}")
    if gaps:
        print("\n  ⌂ HUECO (funcionalidad no implementada — decisión de producto):")
        for r in gaps:
            print(f"    · {r['id']} [{r['domain']}] {r['intent']}")


if __name__ == "__main__":
    main()
