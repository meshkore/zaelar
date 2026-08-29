#
# i18n bundle sanity (V2-089). The preset bundles (en = manifest, es = preset) must stay aligned: same key set,
# non-empty Spanish, and the SAME {placeholder} tokens per key (a drifted placeholder breaks interpolation at
# runtime). Guards the hand-maintained presets; generated languages are diffed at runtime by i18n.runtime.
#
import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
_BUNDLES = ENGINE / "i18n" / "bundles"


def _load(code: str) -> dict:
    return json.loads((_BUNDLES / f"{code}.json").read_text(encoding="utf-8"))


def _placeholders(s: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", s))


def test_en_es_same_keys():
    en, es = _load("en"), _load("es")
    assert set(en) == set(es), f"en/es key drift: en-only={sorted(set(en)-set(es))} es-only={sorted(set(es)-set(en))}"


def test_es_values_nonempty():
    es = _load("es")
    empty = [k for k, v in es.items() if not str(v).strip()]
    assert not empty, f"empty Spanish translations: {empty}"


def test_placeholders_match():
    en, es = _load("en"), _load("es")
    drift = {k: (_placeholders(en[k]), _placeholders(es[k])) for k in en
             if _placeholders(en[k]) != _placeholders(es.get(k, ""))}
    assert not drift, f"placeholder drift en↔es: {drift}"


def test_el_suelo_del_arranque_en_frio_dice_lo_MISMO_que_el_bundle_base():
    """V2-481 — el suelo compilado no puede ser un SEGUNDO vocabulario.

    En el arranque en frío de una Machine `/api/i18n/bundle` todavía no contesta, así que el primer pantallazo
    de quien acaba de instalar la PWA salía como `boot.encendiendo`. El suelo lo evita; lo que este test evita
    es lo siguiente: que se separe del bundle. Si el suelo dijera algo DISTINTO, la leyenda cambiaría de frase
    a mitad del arranque —peor que el defecto original— y si alguien renombra una clave, esto se pone rojo en
    vez de servir una cadena huérfana para siempre.
    """
    import json
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[4]
    js = (raiz / "frontend" / "app" / "core" / "i18n.js").read_text(encoding="utf-8")
    bloque = re.search(r"const BOOT_FLOOR = \{(.*?)\n\};", js, re.S)
    assert bloque, "BOOT_FLOOR desapareció de i18n.js"
    suelo = dict(re.findall(r'"([^"]+)":\s*"([^"]*)"', bloque.group(1)))
    assert suelo, "BOOT_FLOOR quedó vacío: el arranque en frío volvería a enseñar claves"

    base = json.loads((raiz / "i18n" / "bundles" / "en.json").read_text(encoding="utf-8"))
    for clave, texto in suelo.items():
        assert clave in base, f"{clave} está en el suelo y NO en el bundle base — cadena huérfana"
        assert texto == base[clave], (
            f"{clave}: el suelo dice {texto!r} y el bundle {base[clave]!r} — la leyenda cambiaría a mitad "
            f"del arranque")


def test_la_leyenda_del_arranque_se_resuelve_en_cada_pintado():
    """La otra mitad: el suelo no sirve de nada si la leyenda se congela al importar el módulo.

    `LABELS = {encendiendo: t("boot.encendiendo"), …}` corría `t()` UNA vez, al cargar el fichero — antes de
    que el bundle existiera — así que cuando el motor por fin contestaba la cadena buena llegaba y no la veía
    nadie. Es el defecto que V2-124 midió en el móvil, y no falla con ruido: falla enseñando una clave.
    """
    from pathlib import Path

    js = (Path(__file__).resolve().parents[4] / "frontend" / "app" / "components"
          / "BootOverlay.js").read_text(encoding="utf-8")
    assert "function labelFor(" in js, "la leyenda volvió a resolverse fuera del pintado"
    assert "encendiendo: t(" not in js, "t() vuelve a llamarse en un literal de módulo (congelado al importar)"
