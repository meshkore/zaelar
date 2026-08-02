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
