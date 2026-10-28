"""Tariffs: the rates Energy is computed from (nucleo/energy/tariffs.py).

THE RATCHET LIVES HERE. The defect these tests exist for was never a wrong number — it was that
nothing tied a number to the provider actually running, so the STT was metered at Deepgram's rate while
Voxtral ran and no test, log or alarm noticed. Fixing the number alone would leave the
mechanism that produced it completely intact.
"""
import json
import re
from pathlib import Path

import pytest

from nucleo.energy import tariffs as energy_tariffs

# A deployment repo checked out alongside the engine may declare the same provider keys; when it does,
# its config is read as TEXT (it is JavaScript) rather than kept as a hand copy here. Skipped when absent.
# parents: [0]=core [1]=unit [2]=infrastructure [3]=tests [4]=engine [5]=the parent folder
_MACHINE_CONFIG = Path(__file__).resolve().parents[5] / "cloud" / "provisioner" / "src" / "machineConfig.js"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Blank cache AND ISOLATED `sys_kv`.

    Clearing only the process cache is not enough, as was discovered in the worst possible way:
    `update()` PERSISTS, so the first tests wrote to the operator's real `zaelar.db` and the next one
    read it back — two failures that were not caused by the code but by the test contaminating itself…
    and, incidentally, dirtying a real install's memory. A test cannot depend on or write to a shared store.
    """
    store: dict[str, str] = {}
    from memory import api as memory
    monkeypatch.setattr(memory, "kv_get", lambda k: store.get(k))
    monkeypatch.setattr(memory, "kv_set", lambda k, v: store.__setitem__(k, v))
    energy_tariffs._reset_for_tests()
    yield
    energy_tariffs._reset_for_tests()


def _deployed_provider(var: str) -> str | None:
    """The value BASE_PROVIDER_ENV assigns to `var` in the deployment config, read as text."""
    if not _MACHINE_CONFIG.exists():
        return None
    for line in _MACHINE_CONFIG.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{var}:"):
            # The VALUE is the first quoted literal after the colon. A trailing `// comment` (V2-774 put one
            # on ZAELAR_TTS) used to be read as part of it, so the ratchet reported a provider that has a
            # rate as one that does not — red for the wrong reason, which trains people to ignore it.
            m = re.match(r"""\s*(['"])(.*?)\1""", stripped.split(":", 1)[1])
            return m.group(2) if m else stripped.split(":", 1)[1].split("//", 1)[0].strip().strip(",")
    return None


@pytest.mark.parametrize("var,family", [("ZAELAR_STT", "stt"), ("ZAELAR_TTS", "tts")])
def test_every_provider_a_deployment_runs_has_its_own_rate(var, family):
    """THE RATCHET. Changing the voice provider in a deployment config without giving it a rate breaks
    here, at the moment of the change — not later, while looking at numbers that do not add up.

    Without this, a new provider falls into the catch-all: it is metered, but at a price that is not its
    own, and the only symptom is a plausible number."""
    provider = _deployed_provider(var)
    if provider is None:
        pytest.skip(f"{_MACHINE_CONFIG.name} is not available (no deployment repo alongside)")
    table = {"stt": energy_tariffs.DEFAULT_STT_USD_PER_MIN,
             "tts": energy_tariffs.DEFAULT_TTS_USD_PER_1K_CHARS}[family]
    assert provider in table, (
        f"The deployment runs {var}={provider!r} and energy_tariffs.py has no rate for it. "
        f"Add it to DEFAULT_{family.upper()}_* — otherwise it is metered at the catch-all rate."
    )


def test_an_unknown_provider_is_never_free():
    """Under-metering is silent; over-metering a rare provider is visible and can be corrected. The
    default failure mode goes toward the visible side."""
    rate = energy_tariffs.rate_for("stt", "un-proveedor-que-no-existe")
    assert rate > 0
    assert rate == max(energy_tariffs.DEFAULT_STT_USD_PER_MIN.values())


def test_local_backends_are_absent_from_the_tables_on_purpose():
    """Free is a PROPERTY of the provider, not a zero rate. A `whisper_local: 0.0` row would be
    indistinguishable from a price that someone forgot to fill in."""
    assert "whisper_local" not in energy_tariffs.DEFAULT_STT_USD_PER_MIN
    assert "kokoro_local" not in energy_tariffs.DEFAULT_TTS_USD_PER_1K_CHARS


def test_central_rates_win_over_the_bundled_defaults():
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.rate_for("stt", "voxtral") == pytest.approx(0.010)


def test_a_partial_central_table_does_not_erase_what_it_does_not_mention():
    """The operator edits only what they want to change, so the central table arrives incomplete by
    design. A provider it does not mention is not unknown to US — it still has its default, and must
    not fall into the catch-all (which would assign it the most expensive price for no reason)."""
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.rate_for("stt", "deepgram") == pytest.approx(
        energy_tariffs.DEFAULT_STT_USD_PER_MIN["deepgram"])


def test_an_empty_payload_is_refused_instead_of_wiping_the_rates():
    """A half-migrated, misconfigured, or buggy control plane may return `{}`. Adopting it would leave
    the engine metering EVERYTHING at the catch-all rate. Absence is not an instruction."""
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.update({}) is False
    assert energy_tariffs.update(None) is False
    assert energy_tariffs.rate_for("stt", "voxtral") == pytest.approx(0.010)


def test_zero_is_a_legitimate_rate_not_a_missing_one():
    """A provider within its included quota (LiveKit includes 5,000 WebRTC minutes per month) has a
    marginal cost that is genuinely zero, and charging for it would invent an expense. It must be
    possible to specify 0."""
    energy_tariffs.update({"transport": {"livekit": 0.0}})
    assert energy_tariffs.rate_for("transport", "livekit") == 0.0


def test_a_negative_rate_is_dropped():
    """A negative rate would GIVE Energy away with every call. The endpoint already validates this;
    this is the second lock because the payload travels over the network."""
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    energy_tariffs.update({"stt": {"voxtral": -5.0}})
    assert energy_tariffs.rate_for("stt", "voxtral") == pytest.approx(0.010)


def test_snapshot_says_where_the_rates_came_from():
    assert energy_tariffs.snapshot()["source"] == "bundled_defaults"
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.snapshot()["source"] == "central"


def test_the_lease_carries_the_tariffs(monkeypatch):
    """The coupling that holds everything together: the rates arrive piggybacked on the lease, the only
    periodic call the engine already makes. If someone stops reading them there, the central prices stop
    arriving and nobody notices — the engine keeps metering with stale ones."""
    import nucleo.energy.lease as lease
    src = Path(lease.__file__).read_text(encoding="utf-8")
    assert "energy_tariffs.update(" in src, (
        "energy_lease ya no adopta las tarifas de la respuesta del arriendo — el canal central está roto"
    )
