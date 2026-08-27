"""Una coletilla que llevan TODAS las filas no es parte del nombre de ninguna (V2-375).

La misma regla de V2-346 —«un dato que nombra a todas no nombra a ninguna»— por el otro extremo de la cadena.

Medido en `weekend-plan-barcelona__es` (2026-08-27, 2/5). Los DIECISÉIS candidatos de la hoja acababan igual:

    Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols) - Actividad relacionada
    Cremallera de Núria ida y vuelta en verano - Actividad relacionada
    Paseo a caballo por la Garrocha - Actividad relacionada
    Bautismo de escalada - Actividad relacionada
    …

O sea que el operador leía dieciséis veces la etiqueta del módulo de la página en vez de dieciséis planes, y
esas mismas cadenas son las que viajan al prompt y a su hoja.

**El tratamiento es DISTINTO al del prefijo, y la diferencia es lo que decide el arreglo.** Con un prefijo
compartido la fila se queda SIN identidad —los nueve enlaces de concesionario de V2-346 solo se diferenciaban
en el paréntesis final— y por eso se degradan al montón de las que no tienen nombre. Aquí la identidad está
entera DELANTE («Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols)») y lo que sobra es el rabo: se
RECORTA y la fila se queda. Degradarlas habría tirado dieciséis hallazgos buenos.
"""
import pytest

from widgets.navegador import act_api
from widgets.navegador.act_api import _boilerplate_suffix, by_identity

MEDIDO = [
    "Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols) - Actividad relacionada",
    "Cremallera de Núria ida y vuelta en verano - Actividad relacionada",
    "Paseo a caballo por la Garrocha - Actividad relacionada",
    "Paseo a caballo por el Montseny - Actividad relacionada",
    "Bautismo de escalada - Actividad relacionada",
    "Descubre la magia de los volcanes en Espai Cràter - Actividad relacionada",
    "Trekking Acuático - Actividad relacionada",
    "Bautismo de escalada indoor - Actividad relacionada",
]


def _filas(titulos):
    return [{"title": t, "price": "40 €", "url": f"u{i}"} for i, t in enumerate(titulos)]


# ── el detector ────────────────────────────────────────────────────────────────────────────────────────────

def test_la_coletilla_medida_se_detecta():
    assert "Actividad relacionada" in _boilerplate_suffix(MEDIDO)


def test_una_coletilla_CORTA_no_cuenta():
    """El mismo freno que el prefijo: «Kit» lo comparten tres cámaras legítimas, y recortarlo les quitaría un
    dato de verdad."""
    assert _boilerplate_suffix(["Canon 4000D Kit", "Nikon D3500 Kit", "Sony A58 Kit"]) in ("", " Kit")


def test_tres_filas_sueltas_de_muchas_no_hacen_plantilla():
    """La mitad, nunca menos de tres: tres «Ford Focus 1.5 TDCi» entre siete coches son tres coches."""
    ts = [f"Coche distinto {i}" for i in range(8)] + ["A - Actividad relacionada"] * 2
    assert not _boilerplate_suffix(ts).strip().endswith("Actividad relacionada")


def test_sin_nada_en_comun_no_hay_coletilla():
    assert _boilerplate_suffix(["Canon EOS 550D", "Nikon D3500", "Sony Alpha 58"]).strip() == ""


# ── el efecto: se RECORTA y la fila SE QUEDA ───────────────────────────────────────────────────────────────

def test_las_dieciseis_filas_SOBREVIVEN_recortadas():
    named, unnamed = by_identity(_filas(MEDIDO))
    assert len(named) == len(MEDIDO), "recortar no puede costar ni una fila"
    assert unnamed == []
    assert named[0]["title"] == "Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols)"
    assert not any("Actividad relacionada" in i["title"] for i in named)


def test_el_separador_colgante_tambien_se_va():
    """«Bautismo de escalada -» con el guion suelto se lee como un título cortado a medias.

    ⚠️ La primera versión de este caso usaba `MEDIDO`, donde el separador es SIEMPRE « - » y por tanto entra
    dentro de la coletilla detectada (`' - Actividad relacionada'`): la limpieza no tenía nada que hacer y el
    desarme salió VERDE. Un sitio que alterne separadores deja la coletilla en « Actividad relacionada» a
    secas, y ahí es donde el guion se queda colgando. Se mide donde el defecto puede ocurrir."""
    mezcla = ["Cala del Molí - Actividad relacionada", "Cremallera de Núria — Actividad relacionada",
              "Paseo por la Garrocha · Actividad relacionada", "Bautismo de escalada | Actividad relacionada"]
    named, _ = by_identity(_filas(mezcla))
    assert [i["title"] for i in named] == ["Cala del Molí", "Cremallera de Núria",
                                           "Paseo por la Garrocha", "Bautismo de escalada"]


def test_una_fila_que_SOLO_es_la_coletilla_no_se_vacia():
    """Recortarla entera la dejaría sin título y la convertiría en cromo por nuestra mano: se prefiere dejarla
    como está y que la juzgue quien mira los nombres.

    ⚠️ Dos versiones anteriores de este caso NO tocaban el guarda y el desarme salía verde las dos veces. La
    razón es concreta: el título se compara ya recortado (`.strip()`), así que si la coletilla empieza por
    espacio —como la de la ronda medida, `' - Actividad relacionada'`— NINGÚN título recortado puede ser
    exactamente igual a ella, y la igualdad es la única forma de llegar al guarda. Hace falta una coletilla
    SIN espacio delante. Es más artificial que la ronda real y es lo que hay: un guarda que solo se puede
    comprobar con un dato artificial sigue teniendo que comprobarse, o es código muerto que nadie sabe que
    lo es."""
    ts = ["AlfaActividadRelacionada", "BetaActividadRelacionada",
          "GammaActividadRelacionada", "DeltaActividadRelacionada"]
    cola = _boilerplate_suffix(ts)
    assert cola and not cola.startswith(" "), "premisa: la coletilla no puede empezar por espacio"
    named, _ = by_identity(_filas(ts + [cola]))
    assert all(i["title"].strip() for i in named), "ninguna fila puede quedarse sin título por nuestra mano"
    assert any(i["title"] == cola for i in named), "la que era solo coletilla se queda intacta"


def test_sin_coletilla_comun_los_titulos_NO_se_tocan():
    """Sensibilidad por el otro lado, y es la que importa: recortar de más come nombres reales."""
    ts = ["Canon EOS 550D", "Nikon D3500 Kit", "Sony Alpha 58", "Fujifilm X-T20", "Pentax K-70"]
    named, _ = by_identity(_filas(ts))
    assert [i["title"] for i in named] == ts


def test_el_PREFIJO_de_V2_346_sigue_DEGRADANDO_y_no_recortando():
    """Las dos reglas conviven y hacen cosas distintas a propósito: sin la parte distintiva delante, la fila
    no tiene identidad y va al montón de las que no tienen nombre."""
    ts = [f"+ Vehículos del profesional (FLEXICAR {c})" for c in "ABCDE"]
    named, unnamed = by_identity(_filas(ts))
    assert named == [] and len(unnamed) == 5


def test_una_sola_puerta_para_las_dos_reglas():
    """La coletilla reutiliza el buscador del prefijo dándole la vuelta a las cadenas: un segundo algoritmo
    que haga lo mismo por el otro lado es un segundo sitio donde los umbrales se separan."""
    from pathlib import Path
    src = Path("widgets/navegador/act_api.py").read_text()
    i = src.index("def _boilerplate_suffix")
    cuerpo = src[i:src.index("\ndef ", i + 10)]
    assert "_boilerplate_prefix(" in cuerpo
    assert act_api._TPL_MIN_CHARS and act_api._TPL_MIN_ROWS
