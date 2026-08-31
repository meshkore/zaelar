"""The person MUST NOT know an ad's name: if they recite it, the assistant wrote the line (V2-285).

Measured in `search-buy-guitar__es` (2026-08-24 03:48), turn 18 — in the USER slot:

    «I have been looking and I have a couple of metal-string options that fit what you are asking for: the
     Yamaha F370BL for 100 € and the Fender CD-60 for 120 €.»

and zaelar's next turn replying as the user: «Perfect, I'll take the Yamaha F370 at 100 €… Send me
the link when you can». The driver's SIX faces did not see it: it does not contain the person's name,
offers nothing, and «I have been looking» is not «I have looked».

Widening the seventh regex is the treadmill — there are four now. This is not a wording rule: **«Yamaha
F370BL Negra» was produced by our worker reading a page and lives in OUR sheet.** Its appearance in a tester line
is a system fact, not a resemblance.

It runs in the POST-ROUND sweep and not in the driver's live guard, because the mechanism report with the titles
already exists there: the live guard cannot afford to read the sheet on every turn.
"""
from tests.use_cases.e2e.agent import verify as V

# The REAL titles from that round, exactly as returned by the sheet.
_KNOWN = ["Yamaha F370BL Negra", "Fender CD-60", "Yamaha F310P + funda", "Acústica con funda",
          "Greg Bennett Sunburst", "Clásica acústica nylon"]
_FLIP = ("He estado mirando y tengo un par de opciones de cuerdas de metal que encajan con lo que pides: "
         "la Yamaha F370BL por 100 € y la Fender CD-60 por 120 €.")


def test_la_linea_medida_se_reconoce():
    assert V.recites_our_candidates(_FLIP, _KNOWN), "la línea del turno 18 sigue pasando por línea de persona"


def test_y_ese_era_el_agujero_las_seis_caras_no_la_ven():
    """The sensitivity of the test above: without this signal, that line is indistinguishable from a user's."""
    from tests.use_cases.e2e.agent import driver as D
    assert D.looks_like_the_assistant(_FLIP, "Marc") is False


def test_lo_que_la_persona_SI_puede_decir_no_dispara():
    for linea in ("quiero una guitarra acústica de segunda mano por menos de 150€",
                  "prefiero cuerdas de metal, no clásica",
                  "vale, avísame cuando tengas algo",
                  "¿tienes alguna Yamaha?"):
        assert V.recites_our_candidates(linea, _KNOWN) == [], linea


def test_un_titulo_GENERICO_no_identifica_nada():
    """«Monitor 27» is what the person says when making the request: counting it as a recital would accuse the tester of existing."""
    assert V.recites_our_candidates("busco un monitor 27 barato", ["Monitor 27", "Monitor"]) == []
    assert V.recites_our_candidates("quiero una guitarra acústica", ["Guitarra acústica"]) == []


def test_la_cabecera_generica_del_titulo_se_descarta():
    """Real titles begin with the type of thing («Guitarra Acústica Yamaha F370BL»); the identity is what comes
    AFTERWARD. Without removing it, the title would match the user's own request."""
    assert V.recites_our_candidates("la Yamaha F370BL por 100 €",
                                    ["Guitarra Acústica Yamaha F370BL Negra"])


def test_se_casa_por_PREFIJO_porque_nadie_recita_el_anuncio_entero():
    assert V.recites_our_candidates("me quedo con la Fender CD-60",
                                    ["Fender CD-60 acústica con funda y púas, muy poco uso"])


def test_sin_titulos_conocidos_no_se_inventa_nada():
    assert V.recites_our_candidates(_FLIP, []) == []
    assert V.recites_our_candidates("", _KNOWN) == []


def test_el_barrido_de_la_ronda_LO_USA():
    """The wiring half: the predicate can get it right and still fail to reach the report (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = inspect.getsource(R)
    assert "recites_our_candidates(" in src, "el barrido de role-flip dejó de consultar la señal"
    i_known = src.find("_known = [str(t) for t in")
    i_use = src.find("verifymod.recites_our_candidates")
    assert 0 <= i_known < i_use, "los títulos se componen después de usarlos"
    # AND THAT THE REAL SWEEP MARKS THE OPENING (V2-427). The neighboring test reimplements the loop, so it
    # can remain green with broken `run.py`: measured while dismantling it on 2026-08-28 — I set `opening=False`
    # in the real sweep and all 25 checks kept passing against the restored defect.
    assert "opening=(i == 0)" in src, "el barrido real ya no distingue la primera línea del tester"


def test_un_CODIGO_DE_MODELO_identifica_aunque_sea_corto():
    """`fender cd60` is eleven characters long and is the most recognizable catalog entry: the length cutoff
    discarded it by ONE. Length is a proxy for identity; the model IS the identity."""
    assert V.recites_our_candidates("me quedo con la Fender CD-60", ["Fender CD-60 acústica con funda"])


def test_el_guion_va_DENTRO_del_modelo():
    """`CD-60` is one word to someone reading and saying it; splitting it left «fender cd», which is not identifying."""
    assert V._norm_title("Fender CD-60") == "fender cd60"
    assert V._norm_title("Yamaha F310P + funda") == "yamaha f310p funda"


def test_sin_modelo_y_corto_NO_identifica():
    """Sensitivity of the new rule: two standalone words without a code are not enough."""
    assert V.recites_our_candidates("una silla roja", ["Silla roja"]) == []


def test_medido_contra_TODAS_las_rondas_guardadas_no_hay_falsos_positivos():
    """The number that matters for a detector like this is not whether it catches the case, but how many innocents it accuses.

    Sweep over the TESTER lines in all of the night's reports: ONE marked, the one from turn 18. This is written
    down because when widening this, the temptation is to look only at whether the known case appears.
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
                # `heard`, just as in `run.py`: repeating ONE name that zaelar has just said is choosing, not
                # acting as the assistant. Measured 2026-08-24: 3 of the 4 marked lines were those echoes («that Fender one
                # sounds good», «the Casa Boutique rating»), and the only REAL one —turn 18 at 03:48,
                # reciting TWO titles with prices— is still caught, as required by the neighboring test.
                heard = " ".join((x.get("text") or "") for x in tr[:i] if x.get("who") == "zaelar")
                if t.get("who") == "tester" and V.recites_our_candidates(t.get("text") or "", known,
                                                                        heard=heard, opening=(i == 0)):
                    marcadas += 1
    # FOUR, and all four are REAL flips — the threshold rises when the corpus grows with another flip, never because the
    # detector was widened. The lines, so that a fourth one is visible:
    #   · guitar       03:48 (24-08) — «I have a couple of options … the Yamaha F370BL for 100 € and the Fender CD-60»
    #   · plumber US  01:42 (28-08) — «if Fast Response can't do today maybe check Magic Plumbing too». The
    #     FOURTH one raises the threshold for the right reason: zaelar never said «Magic Plumbing» —the
    #     tester introduces it in turn 12—, so the driver knew a name that could only come from our sheet.
    #     «Fast Response» is an echo (turn 1), and therefore is not what triggers it.
    #   · camera       04:41 (25-08) — «of the ones I have, the clearest is the Canon EOS 4000D: 2,019 shots and 205€»
    #   · things-todo 12:25 (25-08) — «I'll give you three concrete plans … 1. Jazz concert at Café Central … 15€»
    # ⚠️ The camera one was in a round that PASSED (4/3/5/3/3): the harness approved a contaminated measurement, which is
    # exactly what this detector exists to prevent. The third one WAS declared INFRA by V2-313.
    #
    # And there was a FOURTH one that was not (guitar, round 37, 15:51): «those don't work for me… as I told you… let's see if you
    # confirm the area and condition», the person rejecting by name what they had just heard. The POSTURE exception from
    # V2-319 removed it from here, not a higher threshold — see
    # `test_the_person_choosing_is_not_the_assistant.py`. This matters because the reflex on seeing this number
    # rise is to change the `<=`, and that fourth line was NOT supposed to count toward any threshold.
    #
    # What the pattern of the three real ones says: they all occur in CATALOG cases (choose among options with
    # prices). The driver has a list in front of it, and the reflex of a model with a list in front of it is to
    # present it. Widening the regex does not fix that; the place to fix it is its anchor (V2-315).
    assert marcadas <= 4, f"{marcadas} líneas del tester marcadas: el detector se ha vuelto ancho"


def test_una_ronda_con_flip_NO_puede_contarse_como_aprobada():
    """V2-313 — the sweep identified the lines and changed nothing: `search-buy-camera__es` (2026-08-25 04:41)
    came out overall 4 = PASS with the tester reciting our candidates, and raised the scoreboard with a measurement
    contaminated by its own harness. It is the SAME failure as `role_flips > 1`, seen by the sweep instead of
    the live guard, so it is handled the same way: INFRA, not a score."""
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
    """The other half: detecting it after the round only serves to discard the measurement. The THREE flips in the corpus
    are CATALOG cases —the driver has a list in front of it and presents it—, so the anchor now names the
    FACT («you have no list in front of you») instead of prohibiting another form.

    In BOTH languages, and that is the trap that already cost us once: until 2026-08-23 a Spanish anchor
    served the 60 US scenarios, whose users are written in English.
    """
    from tests.use_cases.e2e.agent import driver as D
    for ancla in (D._ANCHOR, D._ANCHOR_EN):
        low = ancla.lower()
        assert "lista" in low or "list" in low
        assert "zaelar" in low
    assert "NO TIENES NINGUNA LISTA DELANTE" in D._ANCHOR
    assert "YOU HAVE NO LIST IN FRONT OF YOU" in D._ANCHOR_EN


def test_el_ancla_VIAJA_al_prompt_de_la_ronda():
    """A correct anchor that does not reach the system prompt is a rule nobody reads (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import driver as D
    src = inspect.getsource(D.Driver.__init__)
    assert "_ANCHOR_EN" in src and "_ANCHOR" in src


def test_la_APERTURA_del_tester_no_puede_recitar_nada_nuestro():
    """`known_titles` is the sheet from the END of the round, and this is evaluated turn by turn: the first line
    was being compared against titles that did not exist at that point.

    Medido el 2026-08-28 en `search-buy-camera__us`, y el falso positivo fue **el encargo mismo** — «Find me a
    used DSLR camera with a low shutter count for under $400»— contra un anuncio titulado en inglés con esas
    same words. It did not occur in Spanish: the request and the ad look much more alike when both are
    in the site's language, so it was the US setting that exposed it.
    """
    titulos = ["Used DSLR Camera Canon EOS 4000D low shutter count 2019 shots"]
    linea = "Find me a used DSLR camera with a low shutter count for under $400."
    assert V.recites_our_candidates(linea, titulos, opening=True) == [], "la apertura no recita la hoja"


def test_y_con_zaelar_habiendo_hablado_se_sigue_cazando():
    """The sensitivity half: the temporal boundary cannot turn off the detector, only limit it."""
    titulos = ["Yamaha F370BL guitarra acústica negra"]
    linea = "tengo un par de opciones: la Yamaha F370BL por 100 €"
    assert V.recites_our_candidates(linea, titulos, heard="dame un momento que lo miro")


def test_es_la_APERTURA_y_no_el_silencio_lo_que_hace_inocente():
    """First failed attempt, and the neighboring test caught it: I set the boundary to «empty `heard`», and a line
    midway through a conversation naming a title zaelar NEVER said also arrives with `heard` without that title —
    and that is a flip, the strong case for the entire rule. What makes the opening innocent is not that nothing
    has been heard: it is that there is not yet anything of OURS that could have been read."""
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
