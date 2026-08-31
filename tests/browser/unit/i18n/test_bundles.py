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
    """V2-481 — the compiled fallback cannot be a SECOND vocabulary.

    During the cold start of a Machine, `/api/i18n/bundle` still does not respond, so the first screen shown
    to someone who has just installed the PWA appeared as `boot.encendiendo`. The fallback prevents that; what
    this test prevents is the following: the fallback drifting away from the bundle. If the fallback said
    something DIFFERENT, the label would change wording halfway through startup —worse than the original bug—
    and if someone renames a key, this turns red instead of serving an orphaned string forever.
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
    """The other half: the fallback is useless if the label is frozen when the module is imported.

    `LABELS = {encendiendo: t("boot.encendiendo"), …}` ran `t()` ONCE, when loading the file — before the
    bundle existed — so when the engine finally responded, the correct string arrived but nobody saw it. This
    is the bug that V2-124 measured on mobile, and it does not fail noisily: it fails by displaying a key.
    """
    from pathlib import Path

    js = (Path(__file__).resolve().parents[4] / "frontend" / "app" / "components"
          / "BootOverlay.js").read_text(encoding="utf-8")
    assert "function labelFor(" in js, "la leyenda volvió a resolverse fuera del pintado"
    assert "encendiendo: t(" not in js, "t() vuelve a llamarse en un literal de módulo (congelado al importar)"
