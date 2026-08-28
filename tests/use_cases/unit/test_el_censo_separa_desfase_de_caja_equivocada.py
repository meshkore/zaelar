"""V2-440 · el censo del INSTANTE separa las dos causas que se veían idénticas.

La cara dice «ya ha encontrado algo» y la hoja no da ni una fila. Eso tiene DOS causas que piden arreglos
opuestos: **desfase** (el worker aún no ha entregado — el aviso es correcto y no hay nada que tocar) y
**caja equivocada** (las filas están en otra hoja — ahí sí hay defecto). Desde fuera se ven igual.

El 2026-08-28 se intentó separarlas comparando con el estado FINAL de la ronda y salió un FALSO POSITIVO:
`search-buy-bicycle__es` marcó `e84138-2` como equivocada y esa caja acabó con 35 filas. El estado final no
puede contestar una pregunta sobre un instante — para entonces la caja que se miró ya tenía lo que le
faltaba cuando se miró.
"""
from tests.use_cases.e2e.agent.verify import _censo_dice, unresolved_errand_sheets

_AVISO = "🧾 la cara dice que hay filas y la hoja no las da"


def _ev(cajas, censo):
    return {"kind": "perf", "label": _AVISO, "payload": {"cajas": cajas, "censo": censo}}


def test_ninguna_hoja_con_filas_es_DESFASE_y_no_un_defecto():
    """El caso sano: el aviso salió antes de que el worker entregara. Contarlo como defecto manda a alguien a
    arreglar algo que nunca pasó — el error que una herramienta de medida no puede permitirse."""
    assert _censo_dice("e84138-1:0 e84138-2:0", "e84138-2") == ("desfase", "")


def test_otra_hoja_CON_filas_se_reporta_como_HECHO_y_dice_CUAL():
    """Y NO como «caja equivocada»: el censo lista todo el almacén, y la hoja de un encargo anterior tiene
    filas con todo el derecho. Llamarlo defecto convierte una ronda sana en un hallazgo en cuanto hay dos
    encargos — el mismo error que este nodo existe para no repetir. Nombrar cuál es lo que evita deducirlo a
    mano, que es lo que costó horas esa noche."""
    v, donde = _censo_dice("e84138-1:12 e84138-2:0", "e84138-2")
    assert v == "otras_con_filas" and donde == "e84138-1:12"


def test_mirar_donde_estan_las_filas_no_es_ninguna_de_las_dos():
    """La hoja tenía filas y las miramos: si esto marcara algo, el instrumento acusaría al motor de un fallo
    que no cometió justo cuando acierta."""
    assert _censo_dice("e84138-2:12", "e84138-2") == ("", "")


def test_un_censo_ILEGIBLE_es_un_HUECO_y_nunca_un_hallazgo():
    """«No pude mirar» no es «no había nada». Confundirlos publica una causa inventada con la misma
    seguridad que una medida."""
    assert _censo_dice("?", "e84138-2") == ("", "")
    assert _censo_dice("", "e84138-2") == ("", "")


def test_las_filas_en_la_hoja_DESNUDA_son_su_propia_categoria():
    """La caja FANTASMA no es un desfase, y meterla ahí sería lo cómodo: en un desfase no hay nada escrito y
    aquí las filas existen, a un palmo de la hoja del encargo. `_sheet_of_tab` lo documenta — sin hoja
    resuelta los hallazgos caen en `results` desnuda, «la que no es de nadie». El arreglo es OTRO: el motor
    miró bien y entregó mal el escritor. Medido en `search-buy-bicycle__es`, cuyo `written_ids` trae las dos.
    """
    assert _censo_dice("(base):9 e84138-2:0", "e84138-2") == ("fantasma", "(base)")


def test_la_hoja_DESNUDA_no_se_confunde_con_una_caja_de_encargo_equivocada():
    """Si se contara como caja equivocada, el informe mandaría a arreglar la RESOLUCIÓN cuando lo roto es la
    ENTREGA — y el que lo lea perderá el tiempo en el sitio que no es."""
    v, _ = _censo_dice("(base):9 e84138-1:0", "e84138-1")
    assert v == "fantasma"


def test_el_informe_PUBLICA_el_veredicto_y_no_solo_las_cajas():
    """La mitad del cableado: emitir la señal y no traerla al informe deja el dato donde nadie lo mira."""
    out = unresolved_errand_sheets([_ev("e84138-2", "e84138-1:12 e84138-2:0"),
                                    _ev("e84138-2", "e84138-1:0 e84138-2:0")])
    assert out["n_face_without_rows"] == 2
    assert out["n_with_other_sheets"] == 1 and out["other_sheets"] == ["e84138-1:12"]
    assert out["n_lag"] == 1


def test_el_MOTOR_emite_el_censo_y_no_solo_las_cajas(monkeypatch, tmp_path):
    """La otra mitad, y sin ella los cinco de arriba pasan con el emisor MUDO — comprobado desarmándolo.

    Un lector que sabe interpretar un campo que nadie escribe no mide nada: publica ceros que se leen como
    «no pasó», que es la respuesta tranquilizadora. La guarda recorre el camino real (`aviso_sin_filas`) y
    exige que el evento lleve el censo dentro.
    """
    monkeypatch.setenv("ZAELAR_HOME", str(tmp_path))
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    from nucleo.flash import errand_sheet
    from widgets import store
    from widgets.results import data as sheet, intake
    # ALMACÉN PROPIO. El censo lista TODAS las hojas y va acotado, así que dentro de la suite completa las que
    # dejan otros casos empujan a la nuestra fuera del corte y la guarda falla por el motivo equivocado —
    # medido. Lo que se prueba aquí es el CABLEADO, no cuántas hojas quepan.
    _wd = tmp_path / "wdata"
    _wd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "DATA_DIR", str(_wd), raising=False)

    sheet.begin_task("bicis", fresh=True, sheet="cen-1")
    intake.push([{"title": "Rockrider ST 100", "price": "150€", "url": "http://x/1"}], sheet="cen-1")

    visto = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda *a, **k: visto.append(k.get("extra") or {}), raising=False)
    errand_sheet.aviso_sin_filas("7", ["cen-2"])

    assert visto, "el motor no emitió nada"
    censo = str(visto[-1].get("censo") or "")
    assert censo and censo != "?", f"el aviso salió sin censo: {visto[-1]!r}"
    # Y el censo tiene que ser LEGIBLE por el mismo parser que lo consume, o el cableado sigue roto.
    v, _ = _censo_dice(censo, "cen-2")
    assert v == "otras_con_filas"
    # Lo que prueba el CABLEADO es que nuestra hoja esté en el censo CRUDO con su recuento: el resumen del
    # informe va acotado a propósito, así que dentro de la suite completa —con las hojas que dejan otros
    # tests— la nuestra puede caer fuera del corte sin que nada esté roto. Comprobado: falla solo ahí.
    assert "cen-1:1" in censo, censo


def test_al_juez_se_le_da_la_causa_del_CENSO_y_no_la_del_estado_final():
    """`n_wrong_box` compara con el estado FINAL de la ronda y por eso marcó los ONCE avisos de
    `find-theatre-tickets__us` (2026-08-28) como caja equivocada, cuando el censo dice que los once eran
    DESFASE: nadie tenía filas en ese instante. Decirle al juez una causa falsa once veces es peor que no
    darle ninguna — se la creerá y bajará la nota de mecanismo por una avería inexistente."""
    from tests.use_cases.e2e.agent import judge
    mech = {"sheet_hidden_from_the_prompt": {"n": 2, "turns": [{"turn": 5}]},
            "unresolved_errand_sheets": {"n_wrong_box": 11, "wrong_boxes": {"86f804-2": 11},
                                         "n_lag": 11, "n_ghost": 0, "n_with_other_sheets": 0}}
    txt = judge.mechanism_facts(mech)
    assert "caja que NO era" not in txt and "86f804-2" not in txt


def test_y_si_el_CENSO_dice_que_habia_filas_en_otra_hoja_SI_se_le_dice():
    """La mitad que impide que el arreglo sea silencio: cuando el censo sí encuentra filas fuera, esa es la
    pista buena y tiene que llegar — con el aviso de que una hoja anterior las tiene con todo el derecho."""
    from tests.use_cases.e2e.agent import judge
    mech = {"sheet_hidden_from_the_prompt": {"n": 2, "turns": [{"turn": 5}]},
            "unresolved_errand_sheets": {"n_lag": 0, "n_ghost": 0,
                                         "n_with_other_sheets": 3, "other_sheets": ["e84138-1:12"]}}
    txt = judge.mechanism_facts(mech)
    assert "e84138-1:12" in txt and "encargo ANTERIOR" in txt
