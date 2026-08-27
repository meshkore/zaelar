"""nucleo/flash/delivery.py — EL BACKSTOP DE ENTREGA: una espera con la hoja llena sale CON las filas.

Extraído de `router_guards.py` (V2-340) porque el trinquete de arquitectura lo pidió al crecer ese fichero —
y tenía razón por debajo del recuento: esto no es un guarda del router, es una decisión de ENTREGA con su
propia familia (cuándo una respuesta es pura espera, qué fila cuenta como ya dicha, y cuándo lo que hay en la
hoja es el feed de la página en vez de resultados). Vive junto a quien la llama, no dentro de un cajón de
guardas sin relación.

Historia condensada, porque cada regla de aquí costó una ronda medida:
  · V2-305  la espera con filas frescas sale con ellas (ronda 34: cinco turnos de «te aviso» con 27
            candidatos en la hoja, `delivery_lag_s` 98,9 s).
  · V2-305b la puerta de PERTENENCIA por encargo estaba adaptada a un dominio: un hotel se llama «La Banda
            Living Hostel» y un vuelo «Ryanair directo», así que 36 filas legítimas no dispararon nunca.
  · V2-339  y la señal que la sustituyó —«las filas comparten vocabulario»— silenciaba coches, hoteles y
            vuelos. Ahora un feed son DOS señales: ni se parecen entre sí NI sus precios están en la misma
            escala.
"""
from __future__ import annotations

import re as _re

from .router_guards import _norm_txt



# ── EL BACKSTOP DE ENTREGA (V2-305) ──────────────────────────────────────────────────────────────────────────
# Medido en la ronda 34 de `search-buy-guitar__es` (2026-08-25 01:56): la nota del navegador llegó como texto
# del turno, la cara del estado llevaba las filas, y el modelo contestó «Vale, te aviso en cuanto tenga
# novedades» — y así CINCO turnos, con delivery_lag_s = 98,9 s. El imperativo del prompt pierde contra el
# reflejo de espera una ronda de cada tres, y esa varianza es la diferencia entre pasar y fallar el caso.
# Misma familia que el nunca-mudo (V2-132) y el holding_line de arriba: cuando la conducta correcta es
# DETERMINISTA —hay filas con nombre delante y el turno solo dice «espera»— la garantiza el código, no la
# temperatura del modelo.
# V2-361 — el vocabulario salió de UNA tanda y por eso le faltaban formas reales. Medido en
# `best-rated-rental-car__es` (2026-08-27): con la tarea marcada SIN AVANZAR desde el segundo 188, los turnos
# siguientes dijeron «Te informo en cuanto SEPA algo» y «voy a reunir lo que llevo» — esperas de manual que
# esta lista no reconocía («sepa» no estaba entre los verbos), así que NINGÚN backstop llegó a mirarlas y el
# atasco se quedó sin contar pese a estar detectado. Lo alimenta a los DOS (entrega y atasco), así que cada
# forma que falta cuesta dos silencios.
#: ¿El turno le está PREGUNTANDO algo? Entonces no se le cuelga nada detrás: perdería la pregunta. Se mira el
#: cierre y las aperturas de interrogación del castellano, que es donde vive el signo cuando la frase sigue.
_PREGUNTA_RE = _re.compile(r"[¿?]\s*$|\?\s*[^.!?]{0,40}$|¿")

_WAITING_REPLY_RE = _re.compile(
    r"(te aviso|te informo|te lo digo|te lo cuento|te aviso en cuanto|"
    r"en cuanto (tenga|salga|encuentre|aparezca|sepa|lo tenga|este|la tenga)|"
    r"sigo con ello|sigo dandole|sigo en ello|sigo pendiente|sigo buscando|sigo trabajando|dame un momento|"
    r"dame un segundo|voy a reunir|lo miro y te digo|"
    r"sin novedades|sigue en marcha|todavia no|aun no|quedamos así|me quedo a la espera)")


def sheet_delivery_backstop(reply: str, rows, said_before: str = "", errand: str = "") -> str:
    """La frase que se AÑADE a una respuesta de pura espera cuando la hoja ya tiene filas con nombre que la
    conversación no ha dicho. "" si no toca.

    Estrecho a propósito, por los dos lados: solo dispara sobre una respuesta CORTA que es una frase de espera
    (una respuesta larga ya está contando algo, y pisarla sería peor); y solo con filas cuyo contenido no haya
    aparecido en lo que zaelar YA dijo — re-anunciar lo entregado es el disco rayado de V2-189. La frase afirma
    solo HECHOS: las filas vienen de la hoja (escritas por `intake.push`), así que «en la hoja» es verdad — la
    frontera de V2-278 (nunca afirmar la pantalla EN VUELO) no aplica a una escritura que ya ocurrió.
    """
    r = _norm_txt(str(reply or ""))
    if not r or len(str(reply or "")) > 300:
        return ""
    # V2-364 — LA PUERTA YA NO ES EL VOCABULARIO DE ESPERA, ES LA PREGUNTA.
    #
    # Hasta aquí esto exigía que la respuesta SONARA a espera (`_WAITING_REPLY_RE`), y esa lista se ha
    # ensanchado dos veces en un día persiguiendo formas nuevas — «te informo», «en cuanto sepa», «voy a
    # reunir»— sin dejar de perder turnos. Medido en `find-concert-tickets__es` (2026-08-27): las filas
    # existían en el segundo **72,2** y el turno no las nombró hasta el **137,3**, cuando por fin dijo algo que
    # la lista reconoció. Sesenta y cinco segundos de silencio con VEINTIDÓS candidatos escritos.
    #
    # Perseguir el idioma es una carrera que no se gana. Lo que este backstop existe para evitar no es «que la
    # respuesta suene a espera»: es que el operador se quede sin lo que ya está en su hoja. Las otras dos
    # guardas siguen haciendo el trabajo fino —una respuesta larga ya está contando algo (>300), y las filas ya
    # dichas no se re-anuncian—, así que lo único que hacía falta proteger de verdad es la PREGUNTA: si el
    # turno le está preguntando algo, colgarle las filas detrás le cambia el tema y se queda sin contestar.
    #
    # El backstop de ATASCO conserva la puerta vieja a propósito: contar un atasco es más intrusivo que
    # entregar lo que ya existe, y ahí sí conviene que la respuesta esté en modo espera.
    # V2-371 — la puerta de la PREGUNTA callaba, y callar era demasiado. Medido en `search-buy-motorcycle__es`
    # (2026-08-27) con ONCE candidatos con nombre y enlace en la hoja: la entrega se retuvo 87,4 s y, encima,
    # los turnos en que el modelo preguntaba «¿la paro o le doy margen?» pasaban de largo por aquí y caían en
    # el backstop de ATASCO, que le colgaba detrás NUESTRA propia pregunta de gestión. El operador acabó
    # recibiendo dos veces la misma pregunta —una ya contestada— y ni uno de los once candidatos.
    #
    # Lo que la puerta protege es real y sigue en pie: colgarle filas detrás a una pregunta puede dejarla sin
    # contestar. Pero eso NO es motivo para retener la entrega — es motivo para no ROBARLE el turno de palabra.
    # Con una pregunta abierta se entregan los HECHOS y se calla la nuestra, así que la única pregunta que
    # queda en el turno sigue siendo la suya.
    _preguntando = bool(r.rstrip().endswith("?") or _PREGUNTA_RE.search(r))
    said = _norm_txt(str(said_before or "")) + " " + r
    fresh: list[str] = []
    for row in rows or []:
        row = str(row or "").strip()
        if not row:
            continue
        # «Ya dicha» por TOKEN SIGNIFICATIVO, no por prefijo literal: zaelar dice «la Fender CD-60», nunca el
        # título entero del anuncio («Guitarra Acústica Fender CD-60»), y exigir el prefijo re-anunciaba lo
        # entregado (la misma identidad que el reloj de entrega pagó en la ronda 33). Significativo = trae
        # dígito (un código de modelo) o es una palabra distintiva de ≥5 letras — y NUNCA una palabra que ya
        # esté en el ENCARGO: la categoría («guitarra», «hotel», «monitor») está en la petición por
        # definición, así que suena en cada turno y marcaría TODAS las filas como dichas. Excluir los tokens
        # del encargo es agnóstico del dominio — una lista de genéricos por sector sería adaptarse al caso de
        # uso, que es justo lo que la doctrina prohíbe. Con UN token distintivo ya sonado, la fila cuenta
        # como dicha: el backstop dispara de menos, nunca de más.
        _errand_toks = set(_norm_txt(str(errand or "")).split())
        title = _norm_txt(row.split(" — ")[0])
        toks = [w for w in title.split()
                if (any(c.isdigit() for c in w) or len(w) >= 5) and w not in _errand_toks]
        if toks and not any(t in said for t in toks):
            fresh.append(row)
        if len(fresh) >= 3:
            break
    if not fresh:
        return ""
    if _looks_like_an_unfiltered_feed(rows):
        return ""
    _filas = "; ".join(f"«{f}»" for f in fresh)
    if _preguntando:
        # Los hechos y punto: la pregunta que cierra el turno tiene que seguir siendo la suya. Y la frase se
        # lee DETRÁS de esa pregunta, así que no puede empezar como si viniera delante.
        return "Y mientras lo piensas, ya hay candidatos en la hoja de resultados: " + _filas + "."
    return ("Bueno, de hecho ya hay candidatos en la hoja de resultados: "
            + _filas
            + ". Dime si alguno te encaja o sigo afinando.")


def _looks_like_an_unfiltered_feed(rows) -> bool:
    """¿Estas filas son el FEED de la página en vez de los resultados de la búsqueda? (V2-305, corregido)

    La ronda 35 (2026-08-25 02:20) llenó la hoja de Beyblades, cosmética, velas y un Ford Fiesta: el worker
    falló el tecleo, la página devolvió su portada sin filtrar, y anunciar eso como candidatos habría sido
    peor que la espera que corrige. La primera puerta que puse contra eso exigía compartir palabra con el
    ENCARGO — y eso está adaptado a UN dominio: en un marketplace el título repite la categoría («Guitarra
    Acústica Fender»), pero un hotel se llama «La Banda Living Hostel» y un vuelo «Ryanair directo». Medido en
    la tanda de las 10:04: con 36 filas legítimas de hoteles en la hoja, el backstop no disparó NI UNA vez y
    el juez volvió a fichar «retención de 202 s».

    La señal que sí separa los dos casos sin mirar el sector: la COHERENCIA ENTRE LAS FILAS. Unos resultados
    de búsqueda comparten algo entre sí («Guitarra» en todas, «Hostel» en tres de tres); un feed sin filtrar
    no comparte nada (Beyblade · Paula's Choice · Velas · Carta Nico Williams · Ford Fiesta). Con menos de
    tres filas no se juzga: dos cosas distintas no son un feed, y callar por ahí sería el error de ayer.

    Lado conservador asumido: un encargo legítimamente heterogéneo («cosas para el piso nuevo») se lee como
    feed y el backstop calla — se pierde una ayuda, no se dice una falsedad.
    """
    titles = [_norm_txt(str(r or "").split(" — ")[0]) for r in (rows or [])]
    titles = [t for t in titles if t]
    if len(titles) < 3:
        return False
    counts: dict[str, int] = {}
    for t in titles:
        for w in set(t.split()):
            if len(w) >= 4:
                counts[w] = counts.get(w, 0) + 1
    if any(n >= 2 for n in counts.values()):
        return False                      # comparten algo: son resultados de una búsqueda
    # V2-339 — Y ADEMÁS, ESCALAS DE PRECIO ABSURDAS. «No comparten vocabulario» a secas silenciaba justo los
    # dominios donde los resultados buenos NO se parecen entre sí: «Fiat Panda · Mercedes Clase A · Peugeot
    # 3008» son tres coches perfectos y esta guarda los llamaba feed. Medido con la instrumentación de V2-336
    # (2026-08-26 12:08 y 12:09): `rows=3` y el backstop CALLÓ las dos veces, en la ronda enfocada del coche.
    # Lo mismo explica los hoteles («La Banda Living Hostel» vs «Eurostars») y los vuelos («Ryanair directo»).
    #
    # Lo que de verdad delataba el feed de la ronda 35 no era el vocabulario, era la MEZCLA DE ESCALAS: una
    # vela y un Ford Fiesta no comparten ni precio ni orden de magnitud. Unos resultados de una misma búsqueda
    # sí — los tres coches iban de 6.900 a 9.500 (×1,4), las tres guitarras de 90 a 120 (×1,3).
    #
    # Se exigen las DOS señales para callar, así que la guarda es estrictamente más estrecha que antes: sigue
    # cubriendo el incidente que la creó (que tenía ambas) y devuelve el backstop a los dominios donde su
    # silencio costaba la entrega. Sin precios legibles no se juzga por aquí.
    precios = []
    for r in (rows or []):
        parte = str(r or "").split(" — ")
        if len(parte) < 2:
            continue
        d = _re.sub(r"[^\d]", "", parte[1].split(",")[0])
        if d and len(d) <= 7 and int(d) > 0:
            precios.append(int(d))
    if len(precios) < 3:
        return False
    return (max(precios) / max(1, min(precios))) >= 20


#: Lo que ya cuenta como haberlo dicho. Si la respuesta nombra el atasco con SUS palabras, el backstop calla:
#: añadir detrás sería el disco rayado que V2-189 existe para evitar.
_YA_LO_DICE_RE = _re.compile(r"(atasc|encallad|sin avanzar|no avanza|clavad|parad[ao]|bloquead|"
                             r"lleva \d+ min|se ha quedado)")


def stalled_task_backstop(reply: str, encargo: str, minutos: int, motivo: str) -> str:
    """Una espera que CALLA un atasco que el sistema ya conoce → la frase que lo dice, o "" (V2-359).

    Hermano de `sheet_delivery_backstop`, y por el mismo motivo. V2-354 puso el HECHO delante del modelo —«SIN
    AVANZAR: 5 min sin completar un paso»— y el imperativo le manda decirlo. Medido dos veces el mismo día,
    con el mismo código:

      · `weekend-adventure-sports-bilbao__es` — lo dijo, y bien: «La tarea lleva 5 minutos atascada sin
        completar ni un paso, así que te lo digo claro: va encallada, no te la estoy escondiendo».
      · `search-buy-used-car` — NO lo dijo: «la búsqueda sigue en marcha», con el aviso delante y el operador
        preguntando por el estado TRES veces.

    Una de cada dos. Es exactamente la variancia que V2-305 dejó escrita: cuando la conducta correcta es
    DETERMINISTA —hay un atasco medido, la respuesta es una espera— la garantiza el código, no la temperatura.

    Solo dispara sobre una ESPERA (`_WAITING_REPLY_RE`): una respuesta que ya está contando algo no se pisa. Y
    calla si la respuesta ya nombra el atasco con sus palabras, porque repetirlo detrás es el disco rayado.
    """
    r = (reply or "").strip()
    if not r or not encargo or minutos <= 0:
        return ""
    n = _norm_txt(r)
    if not _WAITING_REPLY_RE.search(n) or _YA_LO_DICE_RE.search(n):
        return ""
    _q = "sin dar señal" if motivo == "callada" else "sin completar un paso"
    return (f"Aunque te lo digo claro: lleva {minutos} min {_q}, así que puede estar atascada. "
            "¿La paro y probamos por otro lado, o le doy un poco más de margen?")


def apply_to_reply(spoken: str, window) -> str:
    """Aplica el backstop a la respuesta de un turno y devuelve la que sale. Nunca lanza.

    Vive aquí y no en `probe` (V2-340) porque el trinquete de arquitectura lo pidió al crecer aquel fichero, y
    porque la decisión y su cableado son la misma cosa: quien llama solo tiene que decir «pásale mi respuesta».

    La VOZ queda FUERA a propósito, como en V2-210: su stream ya se ha dicho cuando esto podría corregirlo, y
    añadir detrás es hablar dos veces — su arreglo es pre-generación, con su propia medición.
    """
    try:
        from . import live_blocks as _lb

        dicho = " ".join(str((m or {}).get("content") or "") for m in (window or [])
                         if (m or {}).get("role") == "assistant")
        encargo, filas = _lb.any_live_task_rows()
        extra = sheet_delivery_backstop(spoken or "", filas, dicho, errand=encargo)
        if extra:
            _emit("📬 backstop de entrega: la espera sale con las filas")
            return ((spoken.rstrip() + " ") if spoken else "") + extra
        # V2-359 — y si no hay filas que entregar, puede haber un ATASCO que callar. Va DESPUÉS y no antes:
        # con resultados delante la cara correcta es entregarlos, no hablar del atasco.
        _enc, _min, _mot = _lb.any_stalled_task()
        _stall = stalled_task_backstop(spoken or "", _enc, _min, _mot)
        if _stall:
            _emit("📬 backstop de atasco: la espera sale con el hecho", mins=_min, motivo=_mot)
            return ((spoken.rstrip() + " ") if spoken else "") + _stall
        # EL SILENCIO SE VE (V2-336). Todo esto vive bajo un `except` general, así que una avería interna
        # desaparece sin ruido — y un backstop que calla es indistinguible de uno que decidió callar. Fue
        # exactamente lo que pasó en la ronda limpia del coche (2026-08-26): tres esperas con la hoja llena y
        # cero disparos, mientras sus tests pasaban con esas mismas entradas. El evento deja las ENTRADAS de
        # la decisión donde el arnés las lee, y con ellas se cerró el misterio en la ronda siguiente: `rows=3`
        # y las filas YA dichas, o sea silencio correcto.
        # V2-371 — y el silencio se ve TAMBIÉN cuando el turno pregunta. Esta guarda seguía siendo el
        # vocabulario de espera, que V2-364 ya había dejado de usar para DECIDIR: desde entonces un turno
        # silenciado por ser una pregunta no dejaba ni una fila donde mirarlo. Reconstruir la ronda de la moto
        # costó cruzar el reloj de entrega con los eventos del atasco porque los turnos que importaban —los que
        # preguntaban— no habían emitido nada. Un guarda de observabilidad que no sigue a la decisión que
        # observa deja ciego justo el caso nuevo.
        _limpio = _norm_txt(spoken or "")
        _pregunta = bool(_limpio.rstrip().endswith("?") or _PREGUNTA_RE.search(_limpio))
        # Una pregunta SIN filas detrás es un turno normal, no una entrega retenida: emitir ahí convertiría el
        # evento en ruido de cada turno y lo dejaría inservible como señal. Con filas SÍ interesa, porque
        # entonces sí hubo algo que no se entregó y hace falta saber por qué.
        if _WAITING_REPLY_RE.search(_limpio) or (_pregunta and filas):
            _emit("🤐 backstop de entrega CALLÓ ante una espera",
                  rows=len(filas or []), goal=(encargo or "")[:80],
                  said_chars=len(dicho or ""), reply=(spoken or "")[:90])
    except Exception:  # noqa: BLE001
        pass
    return spoken


def _emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, role="system", extra=extra or {})
    except Exception:  # noqa: BLE001
        pass
