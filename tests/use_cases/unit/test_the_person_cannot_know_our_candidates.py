"""La persona NO PUEDE saber cómo se llama un anuncio: si lo recita, la línea la escribió el asistente (V2-285).

Medido en `search-buy-guitar__es` (2026-08-24 03:48), turno 18 — en el slot del USUARIO:

    «He estado mirando y tengo un par de opciones de cuerdas de metal que encajan con lo que pides: la
     Yamaha F370BL por 100 € y la Fender CD-60 por 120 €.»

y el turno siguiente de zaelar contestando como usuario: «Perfecto, me quedo con la Yamaha F370 a 100 €… Me
pasas el enlace cuando puedas». Las SEIS caras del conductor no la vieron: no lleva el nombre de la persona,
no ofrece nada, y «he estado mirando» no es «he mirado».

Ensanchar la séptima regex es la cinta de correr — van cuatro. Esto no es una regla de redacción: **«Yamaha
F370BL Negra» lo produjo nuestro worker leyendo una página y vive en NUESTRA hoja.** Que aparezca en una línea
del tester es un hecho del sistema, no un parecido.

Corre en el barrido POSTERIOR a la ronda y no en el guarda vivo del conductor, porque ahí ya está el informe
de mecanismo con los títulos: el guarda vivo no puede pagar una lectura de la hoja en cada turno.
"""
from tests.use_cases.e2e.agent import verify as V

# Los títulos REALES de esa ronda, tal como los devolvió la hoja.
_KNOWN = ["Yamaha F370BL Negra", "Fender CD-60", "Yamaha F310P + funda", "Acústica con funda",
          "Greg Bennett Sunburst", "Clásica acústica nylon"]
_FLIP = ("He estado mirando y tengo un par de opciones de cuerdas de metal que encajan con lo que pides: "
         "la Yamaha F370BL por 100 € y la Fender CD-60 por 120 €.")


def test_la_linea_medida_se_reconoce():
    assert V.recites_our_candidates(_FLIP, _KNOWN), "la línea del turno 18 sigue pasando por línea de persona"


def test_y_ese_era_el_agujero_las_seis_caras_no_la_ven():
    """La sensibilidad del de arriba: sin esta señal, esa línea es indistinguible de una del usuario."""
    from tests.use_cases.e2e.agent import driver as D
    assert D.looks_like_the_assistant(_FLIP, "Marc") is False


def test_lo_que_la_persona_SI_puede_decir_no_dispara():
    for linea in ("quiero una guitarra acústica de segunda mano por menos de 150€",
                  "prefiero cuerdas de metal, no clásica",
                  "vale, avísame cuando tengas algo",
                  "¿tienes alguna Yamaha?"):
        assert V.recites_our_candidates(linea, _KNOWN) == [], linea


def test_un_titulo_GENERICO_no_identifica_nada():
    """«Monitor 27» es lo que la persona dice al pedir: contarlo como recital acusaría al tester de existir."""
    assert V.recites_our_candidates("busco un monitor 27 barato", ["Monitor 27", "Monitor"]) == []
    assert V.recites_our_candidates("quiero una guitarra acústica", ["Guitarra acústica"]) == []


def test_la_cabecera_generica_del_titulo_se_descarta():
    """Los títulos reales empiezan por el tipo de cosa («Guitarra Acústica Yamaha F370BL»); la identidad es lo
    que viene DESPUÉS. Sin quitarla, el título casaría con la propia petición del usuario."""
    assert V.recites_our_candidates("la Yamaha F370BL por 100 €",
                                    ["Guitarra Acústica Yamaha F370BL Negra"])


def test_se_casa_por_PREFIJO_porque_nadie_recita_el_anuncio_entero():
    assert V.recites_our_candidates("me quedo con la Fender CD-60",
                                    ["Fender CD-60 acústica con funda y púas, muy poco uso"])


def test_sin_titulos_conocidos_no_se_inventa_nada():
    assert V.recites_our_candidates(_FLIP, []) == []
    assert V.recites_our_candidates("", _KNOWN) == []


def test_el_barrido_de_la_ronda_LO_USA():
    """La mitad de cableado: el predicado puede acertar y no llegar al informe (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = inspect.getsource(R)
    assert "recites_our_candidates(" in src, "el barrido de role-flip dejó de consultar la señal"
    i_known = src.find("_known = [str(t) for t in")
    i_use = src.find("verifymod.recites_our_candidates")
    assert 0 <= i_known < i_use, "los títulos se componen después de usarlos"
    # Y QUE EL BARRIDO REAL MARQUE LA APERTURA (V2-427). El test de al lado reimplementa el bucle, así que
    # puede seguir verde con `run.py` roto: medido al desarmarlo el 2026-08-28 — puse `opening=False` en el
    # barrido de verdad y las 25 comprobaciones siguieron pasando sobre el defecto restaurado.
    assert "opening=(i == 0)" in src, "el barrido real ya no distingue la primera línea del tester"


def test_un_CODIGO_DE_MODELO_identifica_aunque_sea_corto():
    """`fender cd60` mide once caracteres y es lo más reconocible del catálogo: el corte por longitud lo tiraba
    por UNO. La longitud es un proxy de identidad; el modelo ES la identidad."""
    assert V.recites_our_candidates("me quedo con la Fender CD-60", ["Fender CD-60 acústica con funda"])


def test_el_guion_va_DENTRO_del_modelo():
    """`CD-60` es una palabra para quien la lee y la dice; partirla dejaba «fender cd», que no identifica."""
    assert V._norm_title("Fender CD-60") == "fender cd60"
    assert V._norm_title("Yamaha F310P + funda") == "yamaha f310p funda"


def test_sin_modelo_y_corto_NO_identifica():
    """Sensibilidad de la regla nueva: dos palabras sueltas sin código no bastan."""
    assert V.recites_our_candidates("una silla roja", ["Silla roja"]) == []


def test_medido_contra_TODAS_las_rondas_guardadas_no_hay_falsos_positivos():
    """El número que importa de un detector así no es que cace el caso, es a cuántos inocentes acusa.

    Barrido sobre las líneas del TESTER de todos los informes de la noche: UNA marcada, la del turno 18. Se
    deja escrito porque la tentación al ensanchar esto es mirar solo si el caso conocido sale.
    """
    import glob
    import json
    marcadas = 0
    for f in glob.glob("tests/runs/use_cases/report_2026082*.json"):
        try:
            rondas = json.load(open(f))["results"]
        except Exception:
            continue
        for r in rondas:
            m = r.get("run", {}).get("mechanism_report", {}) or {}
            known = [str(t) for t in ((m.get("results_sheet") or {}).get("titles") or [])]
            known += [str(t) for t in ((m.get("offered") or {}).get("named") or [])]
            tr = r.get("run", {}).get("transcript", []) or []
            for i, t in enumerate(tr):
                # `heard` igual que en `run.py`: repetir UN nombre que zaelar acaba de decir es elegir, no
                # hacer de asistente. Medido 2026-08-24: 3 de las 4 marcadas eran esos ecos («la Fender esa
                # suena bien», «la valoración de la Casa Boutique»), y la única REAL —el turno 18 del 03:48,
                # que recita DOS títulos con precios— sigue cazada, como exige el test de al lado.
                heard = " ".join((x.get("text") or "") for x in tr[:i] if x.get("who") == "zaelar")
                if t.get("who") == "tester" and V.recites_our_candidates(t.get("text") or "", known,
                                                                        heard=heard, opening=(i == 0)):
                    marcadas += 1
    # CUATRO, y las cuatro son flips REALES — el umbral sube cuando el corpus crece con otro flip, nunca porque el
    # detector se haya ensanchado. Las líneas, para que una cuarta se vea:
    #   · guitarra    03:48 (24-08) — «tengo un par de opciones … la Yamaha F370BL por 100 € y la Fender CD-60»
    #   · plumber US  01:42 (28-08) — «if Fast Response can't do today maybe check Magic Plumbing too». La
    #     CUARTA, y sube el umbral por la razón buena: zaelar nunca dijo «Magic Plumbing» —lo introduce el
    #     tester en el turno 12—, así que el conductor conocía un nombre que solo puede salir de nuestra hoja.
    #     «Fast Response» sí es eco (turno 1), y por eso no es lo que dispara.
    #   · cámara      04:41 (25-08) — «de las que tengo, la más clara es la Canon EOS 4000D: 2.019 disparos y 205€»
    #   · things-todo 12:25 (25-08) — «te saco tres planes concretos … 1. Concierto de jazz en Café Central … 15€»
    # ⚠️ La de la cámara vivía en una ronda que PASÓ (4/3/5/3/3): el arnés aprobó una medida contaminada, que es
    # exactamente lo que este detector existe para impedir. La tercera SÍ salió declarada INFRA por V2-313.
    #
    # Y hubo una CUARTA que no lo era (guitarra, ronda 37, 15:51): «esas no me valen… como te dije… a ver si me
    # confirmas zona y estado», la persona rechazando por nombre lo que acababa de oír. La sacó de aquí el
    # eximente de POSTURA de V2-319, no un umbral más alto — ver
    # `test_the_person_choosing_is_not_the_assistant.py`. Anotarlo importa porque el reflejo al ver este número
    # subir es tocar el `<=`, y esa cuarta línea NO debía contarse a ningún umbral.
    #
    # Lo que dice el patrón de las tres reales: todas llegan en casos de CATÁLOGO (elige entre opciones con
    # precio). El conductor tiene una lista delante y la reflex de un modelo con una lista delante es
    # presentarla. Ensanchar la regex no arregla eso; el sitio donde se arregla es su ancla (V2-315).
    assert marcadas <= 4, f"{marcadas} líneas del tester marcadas: el detector se ha vuelto ancho"


def test_una_ronda_con_flip_NO_puede_contarse_como_aprobada():
    """V2-313 — el barrido nombraba las líneas y no cambiaba nada: `search-buy-camera__es` (2026-08-25 04:41)
    salió overall 4 = PASS con el tester recitando nuestros candidatos, y subió el tablero con una medida
    contaminada por su propio arnés. Es la MISMA avería que `role_flips > 1`, vista por el barrido en vez de
    por el guard vivo, así que se trata igual: INFRA, no nota."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = "\n".join(ln for ln in inspect.getsource(R._run_scenario).splitlines()
                    if not ln.strip().startswith("#"))
    i_flip = src.find('mech["role_flip_lines"] = flipped')
    assert i_flip > 0
    cola = src[i_flip:i_flip + 900]
    assert "crashed" in cola, "el barrido marca las líneas y la ronda se puntúa igual"
    assert "if not crashed:" in cola, "no puede pisar una avería ya declarada (role_flips > 1)"


def test_y_el_ANCLA_del_conductor_se_lo_dice_EN_SUS_DOS_IDIOMAS():
    """La otra mitad: detectarlo después de la ronda solo sirve para tirar la medida. Los TRES flips del corpus
    son casos de CATÁLOGO —el conductor tiene una lista delante y la presenta—, así que el ancla ahora nombra el
    HECHO («no tienes ninguna lista delante») en vez de prohibir otra forma más.

    En los DOS idiomas, y esa es la trampa que ya costó una vez: hasta el 2026-08-23 un ancla en castellano
    servía a los 60 escenarios US, cuyas personas están escritas en inglés.
    """
    from tests.use_cases.e2e.agent import driver as D
    for ancla in (D._ANCHOR, D._ANCHOR_EN):
        low = ancla.lower()
        assert "lista" in low or "list" in low
        assert "zaelar" in low
    assert "NO TIENES NINGUNA LISTA DELANTE" in D._ANCHOR
    assert "YOU HAVE NO LIST IN FRONT OF YOU" in D._ANCHOR_EN


def test_el_ancla_VIAJA_al_prompt_de_la_ronda():
    """Un ancla correcta que no llega al system prompt es una regla que nadie lee (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import driver as D
    src = inspect.getsource(D.Driver.__init__)
    assert "_ANCHOR_EN" in src and "_ANCHOR" in src


def test_la_APERTURA_del_tester_no_puede_recitar_nada_nuestro():
    """`known_titles` es la hoja del FINAL de la ronda y esto se evalúa turno a turno: contra la primera línea
    se estaba comparando con títulos que en ese momento no existían.

    Medido el 2026-08-28 en `search-buy-camera__us`, y el falso positivo fue **el encargo mismo** — «Find me a
    used DSLR camera with a low shutter count for under $400»— contra un anuncio titulado en inglés con esas
    mismas palabras. En castellano no salía: el encargo y el anuncio se parecen mucho más cuando los dos están
    en el idioma del sitio, así que fue el plató US lo que lo destapó.
    """
    titulos = ["Used DSLR Camera Canon EOS 4000D low shutter count 2019 shots"]
    linea = "Find me a used DSLR camera with a low shutter count for under $400."
    assert V.recites_our_candidates(linea, titulos, opening=True) == [], "la apertura no recita la hoja"


def test_y_con_zaelar_habiendo_hablado_se_sigue_cazando():
    """La mitad de sensibilidad: la frontera temporal no puede apagar el detector, solo acotarlo."""
    titulos = ["Yamaha F370BL guitarra acústica negra"]
    linea = "tengo un par de opciones: la Yamaha F370BL por 100 €"
    assert V.recites_our_candidates(linea, titulos, heard="dame un momento que lo miro")


def test_es_la_APERTURA_y_no_el_silencio_lo_que_hace_inocente():
    """Primer intento fallido, y lo cazó el test de al lado: puse la frontera en «`heard` vacío», y una línea
    a media conversación que nombra un título que zaelar NUNCA dijo también llega con `heard` sin ese título —
    y ésa sí es un flip, el caso fuerte de la regla entera. Lo que hace inocente a la apertura no es que no se
    haya oído nada: es que todavía no hay nada NUESTRO que se pueda haber leído."""
    titulos = ["Epiphone DR-100 Nat"]
    linea = "no me vale la Epiphone DR-100, porfa busca otra"
    assert V.recites_our_candidates(linea, titulos, heard="") != [], "a media conversación SÍ delata"
    assert V.recites_our_candidates(linea, titulos, opening=True) == [], "en la apertura, no"


def test_a_measurement_is_not_a_model_code():
    """`27inch`/`4k`/`144hz` are SPECS, not identity: a number+unit token is exactly what the person says
    on their own when stating requirements, so it must never satisfy the model-code check.

    Measured 2026-08-29 in `cheapest-monitor__us` (00:28 round, judged 4/5): a worker prose note titled
    «## 27-inch 4K monitors mentioned **Note:** …» reached `known_titles`, its head normalized to
    `27inch 4k`, the digits-and-letters heuristic read `27inch` as a model code, and the tester's own
    requirements line — «I need a 27-inch **4K** monitor» — was filed as a role flip. Third clean round
    archived INFRA over the same phrase; the guard was killing the rounds it exists to protect.
    """
    prose_note = '## 27-inch 4K monitors mentioned **Note:** The article states "Prices are pulled live"'
    linea = "Hmm, you dropped the 4K part — I need a 27-inch **4K** monitor, not just any budget one."
    assert V.recites_our_candidates(linea, [prose_note], heard="let me search for budget monitors") == [], \
        "a spec phrase the person can say alone must not read as reciting our sheet"
    # …and a real model code keeps its teeth: digits+letters that are NOT a unit still identify.
    assert V.recites_our_candidates("tengo la Yamaha F370BL apuntada", ["Yamaha F370BL guitarra negra"],
                                    heard="") != [], "a true model code still flags"
