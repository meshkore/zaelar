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

import pytest

from memory import embeddings as emb


@pytest.fixture(autouse=True)
def _clean():
    emb.reset()
    yield
    emb.reset()


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


def test_the_embedding_model_has_its_own_RATE(monkeypatch):
    """Without a row the catch-all applies, and for the cheapest model on the whole list that is ~100x the real
    price. A missing rate does not fail: it bills wrong, in the direction nobody checks."""
    from config import models as table
    from nucleo.energy import meter as energy_meter

    row = table.rungs("embeddings")[0]
    rate_in, rate_out = energy_meter._rate_for(row["base_url"], row["model"])
    assert (rate_in, rate_out) != energy_meter._FALLBACK_RATE_USD, (
        f"{row['model']} has no rate row — it is billing at the punitive catch-all.")
    assert rate_out == 0.0, "an embedding generates no output tokens; charging for them invents a cost"
