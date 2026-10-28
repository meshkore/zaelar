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
from . import row_named as _row_named   # a row he named is named by a word only it carries (2026-10-14)



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
    r"sin novedades|sigue en marcha|todavia no|aun no|quedamos así|me quedo a la espera|"
    # V2-475 — the same door in English. Without these, the stall backstop simply never fired for an
    # English operator: every gate in this family was written against Spanish wording only.
    r"i ?'?ll let you know|i will let you know|keep you posted|as soon as i|"
    r"still (working|looking|searching|running|on it|digging)|"
    r"working on it|i'?m on it|let me (nudge|check|keep)|"
    r"give me a (moment|second|minute)|hang on|one moment|bear with me|"
    r"nothing yet|no results yet|not yet|in the meantime)")


def _speaks_en() -> bool:
    """Is the operator being spoken to in English right now? (`langs.current_code()`, same reader the rest of
    the flash layer uses.) Guarded and false by default: this family must never lose a delivery to an import.
    """
    try:
        from voice.engine.core import langs as _langs
        return (_langs.current_code() or "").strip().lower() == "en"
    except Exception:  # noqa: BLE001
        return False


def sheet_delivery_backstop(reply: str, rows, said_before: str = "", errand: str = "", heard: str = "",
                            sheet=None) -> str:
    """La frase que se AÑADE a una respuesta de pura espera cuando la hoja ya tiene filas con nombre que la
    conversación no ha dicho. "" si no toca.

    Estrecho a propósito, por los dos lados: solo dispara sobre una respuesta CORTA que es una frase de espera
    (una respuesta larga ya está contando algo, y pisarla sería peor); y solo con filas cuyo contenido no haya
    aparecido en lo que zaelar YA dijo — re-anunciar lo entregado es el disco rayado de V2-189. La frase afirma
    solo HECHOS: las filas vienen de la hoja (escritas por `intake.push`), así que «en la hoja» es verdad — la
    frontera de V2-278 (nunca afirmar la pantalla EN VUELO) no aplica a una escritura que ya ocurrió.
    """
    r = _norm_txt(str(reply or ""))
    if not r:
        return ""
    # V2-478 — LA PUERTA TAMPOCO ERA LA LONGITUD.
    #
    # Aquí había un tope de 300 caracteres con este razonamiento: «una respuesta larga ya está contando algo,
    # y pisarla sería peor». Medido en `find-best-hotel-city__us` ronda 5 (2026-08-29), esa premisa es falsa:
    # el turno era largo —«I've got a partial shortlist up on screen, six central candidates for that
    # weekend»— y no nombró NI UN hotel ni UN precio. Contaba una NARRACIÓN, no un hecho; el operador se
    # quedó igual de sin nada que con un «te aviso», solo que más convencido de que ya tenía algo.
    #
    # Es la tercera vez que esta puerta se corrige mirando la propiedad equivocada: primero fue el
    # vocabulario de espera (V2-364), luego la pregunta (V2-371), ahora la longitud. La propiedad que
    # importa de verdad no es cómo suena el turno ni cuánto ocupa: es si NOMBRA lo que la hoja ya tiene. Y
    # eso ya se calcula abajo, fila a fila (`fresh`), así que la puerta correcta no hace falta inventarla —
    # basta con dejar de tapar el cálculo con una heurística de tamaño. Un turno que ya nombró sus filas no
    # recibe nada porque `fresh` sale vacío, que es la protección real contra pisar una entrega.
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
        # the prompt's markers are not speech (V2-781): a bare lead is no candidate, «SIN PRECIO» is just unsaid
        if not row or "PÁGINA WEB por mirar" in row:
            continue
        row = row.replace(" — SIN PRECIO", "")
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
        # V2-471, segunda puerta de la misma propiedad: lo entregable es «nombre — dato», no el nombre solo.
        # Ronda 12 del monitor: «Dell S2725QS» sonó en el turno 2, así que TODAS las filas Dell contaban como
        # dichas — mientras el $279.99 que la fila llevaba no sonó nunca, que era justo lo que el bucle de
        # «déjame confirmar el precio» le debía al operador. Una fila CON dato se da por dicha cuando su dato
        # ha sonado; el nombre solo salda las filas que no llevan dato.
        _dato = _norm_txt(row.split(" — ", 1)[1]) if " — " in row else ""
        _dato_toks = [w for w in _dato.split() if any(c.isdigit() for c in w)]
        if _row_named.by_him(heard, row, sheet or rows, errand):
            continue         # V2-781 T521: a row HE named (turned down, asked about) is never news to him
        if toks and not any(t in said for t in toks):
            fresh.append(row)
        elif _dato_toks and not any(t in said for t in _dato_toks):
            fresh.append(row)
        if len(fresh) >= 3:
            break
    if not fresh:
        return ""
    if _looks_like_an_unfiltered_feed(rows):
        return ""
    _filas = "; ".join(f"«{f}»" for f in fresh)
    # V2-475 — the sentence goes out in the language the operator is being spoken to. Until here this family
    # only knew Spanish, so an English turn got a Spanish paragraph glued to its reply: the guarantee itself
    # became the defect it was written to prevent.
    if _speaks_en():
        if _preguntando:
            return "And while you think about it, there are already candidates on the results sheet: " + _filas + "."
        return ("Actually, there are already candidates on the results sheet: "
                + _filas
                + ". Tell me if any of them works for you, or I keep narrowing it down.")
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
                             r"lleva \d+ min|se ha quedado|"
                             # English half of the same «it already says it» check (V2-475): without it the
                             # sentence would be appended behind a reply that had just said the same thing.
                             r"stuck|stalled|not moving|no progress|hasn'?t (moved|advanced|progressed)|"
                             r"frozen|been \d+ min)")


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
    if _speaks_en():
        _qe = "with no signal at all" if motivo == "callada" else "without completing a single step"
        return (f"Straight up, though: it has been {minutos} min {_qe}, so it may well be stuck. "
                "Do you want me to stop it and try another way, or give it a bit longer?")
    _q = "sin dar señal" if motivo == "callada" else "sin completar un paso"
    return (f"Aunque te lo digo claro: lleva {minutos} min {_q}, así que puede estar atascada. "
            "¿La paro y probamos por otro lado, o le doy un poco más de margen?")


#: A monetary amount as a reply writes one — same shape as `findings._AMOUNT_RE` (kept textually in sync;
#: importing the worker package from the flash layer for one regex would be a heavier coupling than the copy).
_REPLY_AMOUNT_RE = _re.compile(
    r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£]|€)|(?:USD|EUR|GBP|MXN)\s?\d[\d.,]*|\d[\d.,]*\s?(?:USD|EUR|GBP|MXN)"
    # the currency said as a WORD (2026-10-11: «1.079 euros», «830 dólares», «17 mil pesos» never matched)
    r"|\d[\d.,]*\s?(?:mil\s+)?(?:euros?|d[oó]lares|dollars?|bucks|pesos|libras|pounds)\b)",
    _re.I)
_BACKING_NUM_RE = _re.compile(r"\d[\d.,]*")


def _digits(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def strip_unbacked_amounts(reply: str, *, user_text: str = "", rows=None, active: bool = True, keep_whole: bool = True):
    """Cut the sentences of `reply` whose monetary amounts NO source of ours names. Returns (reply, dropped).

    V2-472 — the blocker class that dominates the US board, measured by the instrument as
    `market_claims_before_delivery`: mid-errand, with nothing to hand over yet, the model invents a market
    figure («under $400» over a $250 ceiling, «$200–300 sweet spot», «CUNPU at $136») and says it with the
    same confidence as a real one. The prompt already forbids it («o está en tu ESTADO o NO LO SABES») and
    loses one round in three — so the conduct is guaranteed by code, like every rule in this family.

    Conservative by the instrument's own asymmetry (a false cut removes a REAL delivery):
      · backing = the operator's own words this conversation + the errand sheet's rows — every legitimate
        way a figure can reach a reply, now that V2-471 lands snippet prices as sheet rows;
      · gate = a LIVE errand only (`active`): with nothing running, an amount is an answer, not a finding;
      · fail-open = a reply that would vanish entirely stays whole (a mute turn is the worse failure,
        V2-336) — the event still reports what was seen.
    """
    reply = str(reply or "")
    if not active or not reply or not _REPLY_AMOUNT_RE.search(reply):
        return reply, []
    from . import amount_gate as _ag
    backing = {_digits(t) for t in _BACKING_NUM_RE.findall(str(user_text or ""))}
    for row in [*(rows or []), _ag.search_backing()]:   # this turn's web results back a figure too (2026-10-11)
        backing |= {_digits(t) for t in _BACKING_NUM_RE.findall(str(row or ""))}
    kept, dropped = [], []
    for sent in _re.split(r"(?<=[.!?])\s+", reply):
        amounts = _REPLY_AMOUNT_RE.findall(sent)
        if amounts and any(not _ag.backed(_ag.amount_digits(a), backing) for a in amounts):
            dropped.append(sent.strip())
        else:
            kept.append(sent)
    out = " ".join(s for s in kept if s.strip()).strip()
    if not out and keep_whole:
        return reply, dropped                      # fail-open: never trade an invention for a mute turn
    return out, dropped                            # …unless the caller has a true sentence to say instead


#: errand goal → the rows the backstop already announced. The window prunes old replies; this does not, so a
#: batch he turned down is never re-offered as news (V2-781, search-buy-used-car).
_ANNOUNCED: dict[str, set] = {}


#: errands whose stall this backstop already OFFERED to stop. An offer is made once: in the EN round of
#: three-tasks-at-once (2026-10-10 20:00) he answered «stop it and try another way», the stop ran, and the next
#: reply asked the same question again with «4 min» for «3 min». The fact stays in the prompt; the offer does not.
_STALL_OFFERED: set = set()


def forget_announced() -> None:
    _ANNOUNCED.clear()
    _STALL_OFFERED.clear()
    from nucleo.turn.his_spec_to_sheet import forget as _forget_specs
    _forget_specs()


def _not_owed(heard_now: str, errand: str, rows, *, already: bool) -> str:
    """Why this errand's rows are NOT owed to his sentence ("" = they are). The rows answer a sentence ABOUT that
    errand, once — never a sentence about another one, and never as a tail that repeats.

    three-tasks-at-once (ES, 2026-10-11 02:04): with a report, a monitor hunt and a game live, «Bueno, de hecho ya
    hay candidatos en la hoja de resultados…» was glued to five replies in a row — three of them answers about the
    car REPORT («¿y el informe ese va bien?»), one right after he had picked «el Samsung de 50 €». Three readings,
    all of his sentence, none of a word list:
      · it names other errands and not this one → it is about them;
      · it names a row of this sheet → he is already choosing among what he was given;
      · it names no errand while several are known, and this errand's rows were already delivered once → the
        sentence is not about it, and a second delivery is the same tail again.
    With nothing heard (a caller that does not pass his words), the rule stays what it was."""
    if not heard_now or not errand:
        return ""
    if _about_another_errand(heard_now, errand):
        return "the turn is about another errand"
    # a bare number or the category is not a name: «al menos 27 pulgadas» is a criterion, not the «Samsung 27"» row
    if any(_row_named.by_him(heard_now, row, rows, errand) for row in rows or []):
        return "he named a row of this sheet"
    if already:
        try:
            from nucleo.turn import named_errand as _ne
            if not _ne.named(heard_now) and len(_ne.known()) > 1:
                return "already delivered, and his sentence is about no errand in particular"
        except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
            _emit("🤐 delivery backstop: errands unreadable", error=f"{type(e).__name__}: {e}"[:120])
    return ""


def _about_another_errand(heard_now: str, errand: str) -> bool:
    """Does his sentence name errands, none of them the one whose rows the backstop would deliver?

    three-tasks-at-once (ES, 2026-10-10 20:00): «del informe quítame los híbridos» → «dame un momento que lo miro»
    + three MONITOR candidates. The refinement was about the report; gluing the monitor sheet to the reply changed
    the subject under him, and he had to say it three more times. A sentence that names no errand keeps the
    backstop, as before."""
    if not heard_now or not errand:
        return False
    try:
        from nucleo.turn import named_errand as _ne
        # starting and just-finished errands are named too: «for the game make the jump higher» while the game's
        # session was still registering named nothing, and the monitor's rows answered it (EN 2026-10-11 11:34)
        return (bool(_ne.named(heard_now, _ne.known(with_finished=True)))
                and not _ne.named(heard_now, [{"request": errand}]))
    except Exception:  # noqa: BLE001
        return False


def _emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, role="system", extra=extra or {})
    except Exception:  # noqa: BLE001
        pass
