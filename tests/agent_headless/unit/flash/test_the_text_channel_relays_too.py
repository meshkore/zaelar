"""The TEXT channel did not relay, leaving the harness unable to measure for eight hours (V2-252).

Measured by it on 2026-08-21, with the real chain seeded in a new sandbox
(`deepseek-directo → aimlapi-failover`). One turn:

    POST /api/flash/say → {"ok":false,"error":"modelo: 402 Insufficient Balance","spec":"deepseek/deepseek-v4-pro"}

and in the **same second**, in the same log:

    10:05:35  cerebro de voz: «deepseek-directo» SIN SALDO → relevo a «aimlapi-failover»
    10:05:34  memllm[i18n]: relevo a deepseek/deepseek-v4-pro @ aimlapi tras 402

**Voice relayed. i18n relayed. Text did not.** The policy was not missing; applying it was. `probe.py` captured
the error, recorded the cooldown and health… and returned, with a healthy tier waiting alongside it.

memoria-dev brought the precedent, which is what makes this structural: **this is the THIRD time it has bitten in
the same way**. `probe.py` is the PARALLEL implementation of the voice provider, and the harness runs through that
channel (`channel='probe'`). On 2026-08-18 (V2-118…121, `22f3674`) the symptom was different —the `[[cron.create]]`
tags were captured but not executed, so a scheduled notification was UNREACHABLE through that route— and on
2026-08-15 the relay on a hard failure was added to voice but not here.

That is why the fix is not just the retry: the DECISION moves to `nucleo/flash/provider_failure.py`, in one place,
and both channels use it. Two copies of a decision diverge silently, and the warning arrives when someone measures
something that goes wrong for a reason other than the one being measured.
"""
import inspect
import pathlib

import pytest

from nucleo.flash import provider_chain as pc
from nucleo.flash import provider_failure as pf

UNO = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm", "env": ["Z_AI_API_KEY"]}
DOS = {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "model": "", "env": ["AIMLAPI_KEY"]}
SIN_SALDO = "API Error: 402 Insufficient Balance"


@pytest.fixture
def cadena(monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(UNO), dict(DOS)])
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k")


# ── the decision, only once ──────────────────────────────────────────────────────────────────────────────────

def test_un_402_devuelve_EL_ESCALON_al_que_ir(cadena):
    v = pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)
    assert v["relay"] and v["relay"]["name"] == "aimlapi"
    assert v["dry"] is False


def test_y_deja_al_titular_en_COOLDOWN(cadena):
    pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)
    assert not pc._store.available("z.ai"), "sin cooldown, el turno siguiente vuelve al mismo sitio"


def test_un_ATASCO_no_es_un_fallo_duro(cadena):
    """V2-246: one isolated incident is noise and does not relay; two in a row do. The module makes the distinction, not the channel."""
    assert pf.handle("", role=pc.ROLE_VOICE, stalled=True)["relay"] is None
    assert pf.handle("", role=pc.ROLE_VOICE, stalled=True)["relay"]["name"] == "aimlapi"


def test_con_la_cadena_SECA_lo_dice(cadena, monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(UNO)])
    v = pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)
    assert v["relay"] is None and v["dry"] is True


def test_un_error_que_NO_es_del_proveedor_no_releva_a_nadie(cadena):
    """Sensitivity: relaying on one of our own failures would switch providers without cause and conceal the failure as well."""
    v = pf.handle("TypeError: 'NoneType' object is not subscriptable", role=pc.ROLE_VOICE)
    assert v["relay"] is None
    assert pc._store.available("z.ai"), "un error de código no puede poner a un proveedor sano en cooldown"


def test_no_añade_una_excepcion_a_la_que_ya_hubo(monkeypatch):
    """Runs INSIDE a turn's error handler: if it blows up, it takes down the turn as well as the diagnosis."""
    monkeypatch.setattr(pc, "note_failure", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")), raising=False)
    assert pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)["relay"] is None


# ── and have the TEXT channel apply it ───────────────────────────────────────────────────────────────────────
# WIRING GUARD (V2-199), and this is the heart of the matter: the policy already existed and the channel did not apply it.
# A test of the predicate would have passed three times while this was biting us.

def _probe_src() -> str:
    return pathlib.Path(inspect.getfile(pc)).parent.joinpath("probe.py").read_text(encoding="utf-8")


def test_el_canal_de_texto_REINTENTA_con_el_relevo():
    src = _probe_src()
    assert "_pfail.handle(" in src, "el canal de texto no usa la decisión compartida"
    assert "spec = _pchain_err.spec_for(_nxt)" in src, "apunta el cooldown y devuelve, sin reintentar"
    assert "continue" in src


def test_reintenta_UNA_vez_y_no_entra_en_bucle():
    """A broken provider cannot turn into a retry loop: one attempt, one relay, one retry."""
    src = _probe_src()
    assert "_relay_done = False" in src and "if _nxt and not _relay_done" in src


def test_NO_reintenta_si_el_turno_ya_habia_dicho_algo():
    """With a 402 the stream dies before the first delta, which is the real case. But if text or a
    tool had already been emitted, repeating the turn would say it TWICE — and that is worse than losing the turn."""
    src = _probe_src()
    assert "_virgen = not raw and not buf and not tool_calls" in src
    assert "and _virgen" in src


def test_cuando_ni_asi_se_puede_lo_DICE(cadena):
    """The response includes `sin_relevo` so whoever measures can distinguish «it broke» from «there was nobody to ask»."""
    src = _probe_src()
    assert '"sin_relevo": bool(_v.get("dry"))' in src


def test_los_DOS_canales_usan_la_MISMA_decision():
    """The structural fix, and what prevents a fourth time: the policy lives in one place and both read it."""
    voz = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    assert "provider_failure" in voz.read_text(encoding="utf-8")
    assert "provider_failure" in _probe_src()


# ── and the cooldown lands on the one that FAILED, not the one that would be next ───────────────────────────
# Second trap in the same area, measured by the harness on 2026-08-21: there are TWO sources for «who is primary».
# The turn builds its spec with `spec_from_config()` (which reads `fast.model` / `fast.base_url`) and the chain is
# ordered by `fast.providers`. The ladder was reordered and **nothing changed**, because the turn does not consult that list.
#
# This matters because `note_failure` without `tier` asks `pick()` — «the one that would be chosen NOW»—, which after a reorder
# may not be the one that just failed: the cooldown lands on a HEALTHY provider and the broken one remains selected. Punish
# the innocent and leave the guilty loose, silently.

class _Spec:
    def __init__(self, url):
        self._u = url

    def resolved_base_url(self):
        return self._u


def test_el_cooldown_cae_sobre_el_que_de_verdad_corrio(cadena):
    """The turn ran through the SECOND tier (the relay) and failed. Without the spec, the first would be punished."""
    v = pf.handle(SIN_SALDO, role=pc.ROLE_VOICE, spec=_Spec(DOS["base_url"]))
    assert not pc._store.available("aimlapi"), "el que falló tiene que quedar en cooldown"
    assert pc._store.available("z.ai"), "y el que NO corrió no puede pagarlo"
    assert v["relay"] and v["relay"]["name"] == "z.ai"


def test_una_barra_final_no_cambia_de_quien_hablamos(cadena):
    assert pf.tier_for(_Spec(DOS["base_url"] + "/"), pc.ROLE_VOICE)["name"] == "aimlapi"


def test_un_endpoint_DESCONOCIDO_no_castiga_a_nadie_por_error(cadena):
    """If the turn ran through a site that is not in the chain, guessing would be exactly the failure this
    closes. It falls back to the previous behavior —let `pick()` decide— and does not invent a culprit."""
    assert pf.tier_for(_Spec("https://otro.invalid/v1"), pc.ROLE_VOICE) is None


def test_sin_spec_se_comporta_como_antes(cadena):
    """Compatibility: callers that do not pass it continue to work the same way."""
    assert pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)["relay"]["name"] == "aimlapi"


def test_los_dos_canales_PASAN_el_spec():
    """WIRING GUARD: the predicate can be perfect while both channels still fail to say who ran."""
    voz = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    assert "spec=spec)" in voz.read_text(encoding="utf-8")
    assert "role=_pchain_err.ROLE_VOICE, spec=spec)" in _probe_src()


# ── V2-307: DOS escalones en el MISMO endpoint — el culpable se resuelve por (endpoint, MODELO) ──────────────
#
# Measured at 03:13-03:15 (2026-08-25): `deepseek-directo` (flash) failed for BALANCE, the relay went to
# `deepseek-directo-pro` —same account, same base_url—, whose retry's 402 marked FLASH again (already in
# cooldown) because `tier_for` returned «the first one matching by base_url», and pro never entered cooldown:
# the chain NEVER advanced to the broker. Four silent turns with a funded tier waiting alongside.

GEMELO_A = {"name": "ds-flash", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash",
            "env": ["DEEPSEEK_API_KEY"]}
GEMELO_B = {"name": "ds-pro", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-pro",
            "env": ["DEEPSEEK_API_KEY"]}


class _SpecMM:
    def __init__(self, model, url="https://api.deepseek.com"):
        self.model = model
        self._url = url

    def resolved_base_url(self):
        return self._url


def test_twin_tiers_on_one_endpoint_are_told_apart_by_model(monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(GEMELO_A), dict(GEMELO_B)])
    assert pf.tier_for(_SpecMM("deepseek-v4-pro"), pc.ROLE_VOICE)["name"] == "ds-pro", \
        "el 402 del reintento tiene que marcar al PRO, o la cadena nunca avanza al broker"
    assert pf.tier_for(_SpecMM("deepseek-v4-flash"), pc.ROLE_VOICE)["name"] == "ds-flash"


def test_a_pinned_model_outside_the_chain_still_matches_by_endpoint(monkeypatch):
    """The fallback is preserved: an operator's manual pin (a model not in the chain) is still
    resolved by endpoint — having no culprit would leave the failure entirely unrecorded."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(GEMELO_A), dict(GEMELO_B)])
    assert pf.tier_for(_SpecMM("deepseek-v5-experimental"), pc.ROLE_VOICE)["name"] == "ds-flash"


def test_the_turn_STARTS_on_a_healthy_tier_when_the_pinned_titular_is_cooling(cadena, monkeypatch):
    """The other half of V2-307: with the primary in cooldown, every turn burned a 402 before relaying. The
    guard lives in the probe (source without comments) and the seam is public (`tier_available`), not `_store`."""
    src = "\n".join(ln for ln in pathlib.Path("nucleo/flash/probe.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "tier_available(_t0)" in src, "el arranque del turno no consulta el cooldown del titular"
    assert "_pc0._store" not in src, "la costura tiene que ser pública, no el _store privado (V2-112)"
    # and the seam tells the truth:
    pc._store.set("z.ai", __import__("time").time() + 600, "health")
    assert pc.tier_available(UNO) is False
    assert pc.tier_available(DOS) is True
