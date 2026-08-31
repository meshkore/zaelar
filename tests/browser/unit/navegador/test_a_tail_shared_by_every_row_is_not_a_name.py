"""A trailing phrase shared by ALL rows is not part of any name (V2-375).

The same rule as V2-346 —“data that names all of them names none of them”— applied to the other end of the string.

Measured in `weekend-plan-barcelona__es` (2026-08-27, 2/5). All SIXTEEN candidates in the sheet ended the same way:

    Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols) - Actividad relacionada
    Cremallera de Núria ida y vuelta en verano - Actividad relacionada
    Paseo a caballo por la Garrocha - Actividad relacionada
    Bautismo de escalada - Actividad relacionada
    …

In other words, the operator was reading the page module’s label sixteen times instead of sixteen plans, and
those same strings are the ones sent to the prompt and its sheet.

**The treatment is DIFFERENT from the prefix case, and that difference is what determines the fix.** With a shared
prefix, the row is left WITHOUT an identity —the nine dealer links from V2-346 differed only in the final
parenthesis— and are therefore degraded into the pile of those without a name. Here, the entire identity is
BEFORE the excess (“Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols)”), and what remains is the tail: it is
TRIMMED and the row remains. Degrading them would have discarded sixteen good findings.
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


# ── the detector ────────────────────────────────────────────────────────────────────────────────────────────

def test_la_coletilla_medida_se_detecta():
    assert "Actividad relacionada" in _boilerplate_suffix(MEDIDO)


def test_una_coletilla_CORTA_no_cuenta():
    """The same safeguard as for the prefix: “Kit” is shared by three legitimate cameras, and trimming it would
    remove genuine data from them."""
    assert _boilerplate_suffix(["Canon 4000D Kit", "Nikon D3500 Kit", "Sony A58 Kit"]) in ("", " Kit")


def test_tres_filas_sueltas_de_muchas_no_hacen_plantilla():
    """Half, never fewer than three: three “Ford Focus 1.5 TDCi” entries among seven cars are three cars."""
    ts = [f"Coche distinto {i}" for i in range(8)] + ["A - Actividad relacionada"] * 2
    assert not _boilerplate_suffix(ts).strip().endswith("Actividad relacionada")


def test_sin_nada_en_comun_no_hay_coletilla():
    assert _boilerplate_suffix(["Canon EOS 550D", "Nikon D3500", "Sony Alpha 58"]).strip() == ""


# ── the effect: it is TRIMMED and the row REMAINS ───────────────────────────────────────────────────────────────

def test_las_dieciseis_filas_SOBREVIVEN_recortadas():
    named, unnamed = by_identity(_filas(MEDIDO))
    assert len(named) == len(MEDIDO), "recortar no puede costar ni una fila"
    assert unnamed == []
    assert named[0]["title"] == "Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols)"
    assert not any("Actividad relacionada" in i["title"] for i in named)


def test_el_separador_colgante_tambien_se_va():
    """“Bautismo de escalada -” with the dangling hyphen reads like a title cut off halfway.

    ⚠️ The first version of this case used `MEDIDO`, where the separator is ALWAYS “ - ” and therefore falls
    within the detected trailing phrase (`' - Actividad relacionada'`): the cleanup had nothing to do and the
    teardown came out GREEN. A site that alternates separators leaves the trailing phrase as merely
    “ Actividad relacionada”, and that is where the hyphen remains dangling. It is measured where the defect can occur."""
    mezcla = ["Cala del Molí - Actividad relacionada", "Cremallera de Núria — Actividad relacionada",
              "Paseo por la Garrocha · Actividad relacionada", "Bautismo de escalada | Actividad relacionada"]
    named, _ = by_identity(_filas(mezcla))
    assert [i["title"] for i in named] == ["Cala del Molí", "Cremallera de Núria",
                                           "Paseo por la Garrocha", "Bautismo de escalada"]


def test_una_fila_que_SOLO_es_la_coletilla_no_se_vacia():
    """Trimming it entirely would leave it without a title and turn it into junk by our own hand: it is preferable
    to leave it as is and let whoever reviews the names judge it.

    ⚠️ Two previous versions of this case did NOT exercise the guard, and the teardown came out green both times. The
    reason is specific: the title is already compared after trimming (`.strip()`), so if the trailing phrase starts with
    a space —like the one from the measured run, `' - Actividad relacionada'`— NO trimmed title can be
    exactly equal to it, and equality is the only way to reach the guard. A trailing phrase WITHOUT a leading
    space is required. It is more artificial than the real run, but that is the situation: a guard that can only be
    checked with artificial data still has to be checked, or it is dead code that nobody knows is dead."""
    ts = ["AlfaActividadRelacionada", "BetaActividadRelacionada",
          "GammaActividadRelacionada", "DeltaActividadRelacionada"]
    cola = _boilerplate_suffix(ts)
    assert cola and not cola.startswith(" "), "premisa: la coletilla no puede empezar por espacio"
    named, _ = by_identity(_filas(ts + [cola]))
    assert all(i["title"].strip() for i in named), "ninguna fila puede quedarse sin título por nuestra mano"
    assert any(i["title"] == cola for i in named), "la que era solo coletilla se queda intacta"


def test_sin_coletilla_comun_los_titulos_NO_se_tocan():
    """Sensitivity on the other side, which is what matters: over-trimming eats real names."""
    ts = ["Canon EOS 550D", "Nikon D3500 Kit", "Sony Alpha 58", "Fujifilm X-T20", "Pentax K-70"]
    named, _ = by_identity(_filas(ts))
    assert [i["title"] for i in named] == ts


def test_el_PREFIJO_de_V2_346_sigue_DEGRADANDO_y_no_recortando():
    """The two rules coexist and intentionally do different things: without the distinctive part in front, the row
    has no identity and goes into the pile of those without a name."""
    ts = [f"+ Vehículos del profesional (FLEXICAR {c})" for c in "ABCDE"]
    named, unnamed = by_identity(_filas(ts))
    assert named == [] and len(unnamed) == 5


def test_una_sola_puerta_para_las_dos_reglas():
    """The trailing phrase reuses the prefix searcher by reversing the strings: a second algorithm
    doing the same thing from the other side would be a second place where the thresholds diverge."""
    from pathlib import Path
    src = Path("widgets/navegador/act_api.py").read_text()
    i = src.index("def _boilerplate_suffix")
    cuerpo = src[i:src.index("\ndef ", i + 10)]
    assert "_boilerplate_prefix(" in cuerpo
    assert act_api._TPL_MIN_CHARS and act_api._TPL_MIN_ROWS
