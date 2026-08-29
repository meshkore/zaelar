"""The memory's semantic space comes from a CLOUD provider (V2-501).

Why this file exists. The default embedding backend was Ollama, a LOCAL server: it does not exist inside a
container, so every cloud Machine silently fell through to `fastembed`, whose default model is
`BAAI/bge-small-en-v1.5` — English only — in a product used in Spanish.

And that does not raise. It answers differently. Local and cloud had been searching in different spaces for
months, and the only signal was a `logger.warning` and an amber light one learns to ignore.

What is pinned here is not "it calls OpenAI". It is what makes that dependency SAFE: that the dimension is the
one we asked for, that the credential is named by the table, and above all that a provider outage never
changes the space of an already-indexed database.
"""
import json

import pytest

from memory import embeddings as emb
from memory.schema import EMBED_DIM


@pytest.fixture(autouse=True)
def _clean():
    emb.reset()
    yield
    emb.reset()


@pytest.mark.parametrize("written", ["openai", "cloud", "azure", "voyage"])
def test_the_provider_name_and_the_backend_name_are_not_the_same(monkeypatch, written):
    """In the table the provider is called `openai` because that is its PROTOCOL; internally it is `cloud`
    because any compatible endpoint serves. Without the alias, the `.embedsig` signature would read differently
    depending on how the provider was spelled in the panel — and two spellings would be two spaces."""
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": written})
    emb.reset()
    assert emb.active_backend() == "cloud"


def test_the_dimension_is_the_one_we_ASK_for_not_the_model_s_native_one(monkeypatch):
    """`text-embedding-3-small` is 1536 wide out of the box. Reading that from a registry by name would have
    created the vector table at 1536 while 768-wide vectors arrived — the one that rules is the one we ask for."""
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai",
                                                  "embed_model": "text-embedding-3-small"})
    emb.reset()
    assert emb.dim() == EMBED_DIM == 768


def test_a_model_that_does_NOT_accept_dimensions_is_not_asked_for_them(monkeypatch):
    """The counterweight, which is what stops this from being "always ask for 768": asking a model without
    matryoshka support for `dimensions` is a 400, not an optimisation."""
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai", "embed_model": "mistral-embed"})
    emb.reset()
    assert emb._cloud_dims() is None


def test_the_outgoing_body_carries_the_model_and_the_dims(monkeypatch):
    """Measures the request actually built (with `urlopen` patched, no network): this is where we check that
    what was decided above really reaches the provider."""
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": [{"index": 0, "embedding": [0.1] * 768}]}).encode()

    def _urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data.decode())
        seen["auth"] = req.headers.get("Authorization")
        return _Resp()

    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai",
                                                  "embed_model": "text-embedding-3-small",
                                                  "embed_base_url": "https://example.test/v1",
                                                  "embed_api_key": "test-key"})
    monkeypatch.setattr(emb.urllib.request, "urlopen", _urlopen)
    emb.reset()
    out = emb._REAL_CLOUD_EMBED(["hello"])

    assert out and len(out[0]) == 768
    assert seen["url"] == "https://example.test/v1/embeddings"
    assert seen["body"]["model"] == "text-embedding-3-small"
    assert seen["body"]["dimensions"] == 768
    assert seen["auth"] == "Bearer test-key"


def test_the_credential_is_NAMED_by_the_table(monkeypatch):
    """Memory does not infer the key from the URL: it reads the `key_env` of its own row. Inferring it would
    mean importing `nucleo/provider_keys`, and `memory/` does not import `nucleo/` (guarded by
    `test_memory_owes_nucleo_nothing`)."""
    from config import models as table

    env_name = table.rungs("embeddings")[0]["key_env"]
    assert env_name, "the embeddings row must say what pays for it"
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai"})
    monkeypatch.setenv(env_name, "sentinel-value")
    assert emb._cloud_key() == "sentinel-value"


def test_a_provider_outage_does_NOT_change_the_space(monkeypatch):
    """THE property that makes depending on the cloud safe. A 429 returns `None`; that call's vector falls back
    to hashing as a RETURN VALUE only, and `last_degraded` says so, so the writer defers it. What must not
    happen is the backend re-resolving to another one: that would put vectors from a different space into an
    already-sealed index, which is exactly the V2-103 defect."""
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai"})
    monkeypatch.setattr(emb, "_cloud_embed", lambda texts, *, timeout=None: None)
    emb.reset()
    v = emb.embed("any query at all")

    assert len(v) == EMBED_DIM
    assert emb.last_degraded is True, "a silent outage is what fills the index with rubbish"
    assert emb.active_backend() == "cloud", "the vector is deferred; the space is NEVER swapped in flight"


def test_the_signature_names_the_provider_so_the_change_is_VISIBLE(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai",
                                                  "embed_model": "text-embedding-3-small"})
    emb.reset()
    from memory import reembed

    assert reembed.signature() == "cloud:text-embedding-3-small:768"


def test_a_DEGRADED_reembed_stops_and_does_not_seal(monkeypatch):
    """A re-embed walks the whole memory with the current backend and seals the signature at the end. If the
    provider fails halfway, `embed_batch` keeps returning vectors — lexical ones — and without this stop the job
    finished "fine" and stamped the cloud provider's signature over a half-hashed index: the database lying
    about its own space, which is precisely what the seal exists to prevent."""
    from memory import reembed

    sealed = {"times": 0}
    monkeypatch.setattr(reembed, "stamp", lambda sig=None: sealed.__setitem__("times", sealed["times"] + 1))

    class _Db:
        vec_available = True

        def query(self, *a, **k):
            return [{"id": 1, "text": "a memory"}, {"id": 2, "text": "another"}]

        def execute(self, *a, **k):
            return None

    monkeypatch.setattr(reembed._db, "get_db", lambda: _Db())
    monkeypatch.setattr(reembed._emb, "dim", lambda: 768)
    monkeypatch.setattr(reembed._emb, "embed_batch", lambda texts: [[0.0] * 768 for _ in texts])
    reembed._emb.last_degraded = True

    out = reembed.reembed(batch=8)
    assert out["ok"] is False and "degraded" in out["reason"]
    assert sealed["times"] == 0, "sealing a signature the index does not honour is worse than not re-embedding"


def test_the_cloud_call_is_METERED_into_energy(monkeypatch):
    """The coverage gate (`test_energy_coverage`) can only prove somebody *remembered* — it is a grep. This
    proves the call happens, with the endpoint and model the bill is computed from. It matters because the
    embeddings are now the busiest paid call in the engine: one on every insert and one on every query."""
    billed = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": [{"index": 0, "embedding": [0.1] * 768}],
                               "usage": {"prompt_tokens": 12, "total_tokens": 12}}).encode()

    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai",
                                                  "embed_model": "text-embedding-3-small",
                                                  "embed_base_url": "https://api.openai.com/v1",
                                                  "embed_api_key": "test-key"})
    monkeypatch.setattr(emb.urllib.request, "urlopen", lambda req, timeout=None: _Resp())

    from nucleo import energy_meter
    monkeypatch.setattr(energy_meter, "meter_openai_response",
                        lambda payload, *, base_url, model: billed.append((base_url, model, payload)))
    emb.reset()
    emb._REAL_CLOUD_EMBED(["hello"])

    assert len(billed) == 1, "a paid call that nobody meters is money leaving with no trace"
    base_url, model, payload = billed[0]
    assert base_url == "https://api.openai.com/v1" and model == "text-embedding-3-small"
    assert payload["usage"]["prompt_tokens"] == 12, "the gate is handed the RAW response: it owns which fields count"


def test_the_embedding_model_has_its_own_RATE(monkeypatch):
    """Without a row the catch-all applies, and for the cheapest model on the whole list that is ~100x the real
    price. A missing rate does not fail: it bills wrong, in the direction nobody checks."""
    from config import models as table
    from nucleo import energy_meter

    row = table.rungs("embeddings")[0]
    rate_in, rate_out = energy_meter._rate_for(row["base_url"], row["model"])
    assert (rate_in, rate_out) != energy_meter._FALLBACK_RATE_USD, (
        f"{row['model']} has no rate row — it is billing at the punitive catch-all.")
    assert rate_out == 0.0, "an embedding generates no output tokens; charging for them invents a cost"
