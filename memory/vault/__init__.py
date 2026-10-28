"""memory/vault — the operator's SECRET VAULT (V2-060, end-to-end encrypted).

Stores the USER's secrets (a streaming password, an IBAN/card, a crypto private key) so they are NEVER in clear,
locally or in the cloud. Self-contained: depends only on `pynacl`, `memory.db` and `memory.writer`; never imports
`nucleo` nor touches the voice hot path.

Crypto model (detail in `zaelar-security.md`):
- Asymmetric (libsodium sealed box). The public key `PK` lives in clear in `vault_meta` (writing needs NO unlock);
  the private `SK` is only needed to READ.
- `SK` is stored WRAPPED by N unlock methods (key-wrapping): passphrase (`Argon2id` → `SecretBox`) and passkey
  (WebAuthn PRF). Adding a method = one new envelope; rotating the passphrase re-wraps only its envelope.
- Split storage: the VALUE is opaque in `vault_secrets`; the LABEL is a searchable pill in `memories`
  (`meta.vault=1`) — recall finds it but never sees the value.

Hard invariants: the passphrase and `SK` are NEVER persisted in clear, nor put in an LLM prompt, a worker, logs,
`state` or a pill. `SK` lives unwrapped only in RAM while unlocked (comfort mode) and is wiped on lock/expiry/strict
mode. `status()` is redacted: presence and state, never key material.

  keys.py      errors, KDF/envelopes, the vault row, lifecycle (create/unlock/lock), passphrase rotation, status
  sealed.py    seal / store / open / list the secrets themselves
  passkeys.py  the WebAuthn PRF unlock method
"""
from .keys import (  # noqa: F401
    VaultError, VaultLocked, WrongPassphrase, _msg, change_passphrase, create, exists, is_unlocked, lock, status,
    unlock,
)
from .passkeys import add_passkey, passkey_meta, remove_passkey, unlock_with_prf  # noqa: F401
from .sealed import is_sealed, list_secrets, open_secret, seal, store_secret  # noqa: F401
