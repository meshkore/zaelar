"""Names that are NEVER served, at any depth, even inside a folder the user explicitly granted.

THE RULE THIS ENCODES: "the user allowed their home directory" must not mean "the agent may read the SSH key".
Granting a folder is a statement about DOCUMENTS, and every list below is a thing that is not a document — a key,
a session cookie, a shell history with a pasted token in it. None of it is overridable in v1, on purpose: an
override switch is the first thing a confused user flips and the first thing a prompt-injected agent asks for.

FIVE SHAPES, because secrets are named in five different ways and a single list would miss four of them:

  SEGMENTS  an exact path component at any depth (`.ssh`, `credentials`) — this also covers FILE names, since a
            path's last component is one of its parts.
  NAMES     an exact filename (`.netrc`, `id_rsa`).
  PREFIXES  a filename that STARTS with one of these (`.env` also means `.env.local`, `.env.production`).
  SUFFIXES  an extension that is a private key or a key store (`.pem`, `.kdbx`).
  WINDOWS   syntax that is not a name at all but a way to reach past one — see `windows_reason`.

MATCHING IS NORMALIZED, and both halves of that matter. Case: the filesystems this runs on are usually
case-insensitive, so `.SSH` would otherwise walk straight through. Unicode: macOS stores names decomposed
(NFD), so a caller passing the composed (NFC) form of the same name would compare unequal against a literal
written in this file — the two are the SAME FILE to the operating system and must be the same name here.

WHY THE LIST IS LONG. Every entry is a place a real credential lives on a real machine, and the cost of a false
positive is one refused file with a reason attached, while the cost of a miss is a session cookie for every site
the user is logged into. When those are the two mistakes available, this is the cheap one.
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path

# ── exact path components, at any depth ───────────────────────────────────────────────────────────────────

_DENIED_SEGMENTS = frozenset({
    # SSH, GPG and the shape of a key store
    ".ssh", ".gnupg", ".gpg", "keychains", ".keychain", "keyrings", ".password-store", ".pki",
    # cloud provider credentials
    ".aws", ".azure", ".kube", ".docker", ".gcloud", "gcloud", ".oci", ".config/gcloud", ".chef",
    ".terraform.d", ".vagrant.d", ".ansible",
    # package registries — these hold publish tokens, not packages
    ".gem", ".cargo", ".npm", ".yarn", ".composer", ".nuget", ".m2", ".gradle", ".bundle", ".pip",
    # things whose NAME announces what they are. `private` on its own is deliberately NOT here: it is an
    # ordinary English word and `Documents/private/` is a folder a real person really has, so refusing it as
    # "sensitive" inside a folder they granted would be the broken-product-with-a-good-excuse failure.
    "credentials", ".credentials", "secrets", ".secrets", "private_keys",
    # version control: a repo's own config can carry a token inside a remote URL. Only `.git/**` is refused,
    # so the code in a granted project folder is still perfectly readable.
    ".git", ".svn", ".hg",
    # browser state. Cookies are session tokens for every site the user is signed into, which makes this the
    # single highest-value target on the disk after the SSH key.
    "cookies", ".mozilla", ".thunderbird", "chromium", "bravesoftware",
    # the daemon's own neighbourhood
    ".meshkore",
})

# ── exact filenames ───────────────────────────────────────────────────────────────────────────────────────

_DENIED_NAMES = frozenset({
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".htpasswd", ".pgpass", ".my.cnf",
    ".dockercfg", ".boto", ".s3cfg", ".rclone.conf", ".flyctl", ".databrickscfg",
    "credentials.json", "client_secret.json", "service-account.json", "serviceaccount.json", "token.json",
    "authorized_keys", "known_hosts", "secring.gpg", "pubring.gpg", "trustdb.gpg",
    "zaelar.env", "wallet.dat", "keystore.json",
    # browser credential and cookie stores, by their real on-disk names
    "logins.json", "key3.db", "key4.db", "signons.sqlite", "cookies.sqlite", "login data", "web data",
    # shell and REPL history: people paste tokens into terminals
    ".bash_history", ".zsh_history", ".sh_history", ".python_history", ".psql_history", ".mysql_history",
    ".node_repl_history", ".irb_history", ".lesshst", ".viminfo",
})

# ── filename prefixes ─────────────────────────────────────────────────────────────────────────────────────

# `.env` is never one file. A project has `.env`, `.env.local`, `.env.production`, and an exact-name list
# would refuse the first and hand over the other two.
_DENIED_PREFIXES = (
    ".env",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
)

# ── extensions that ARE a key ─────────────────────────────────────────────────────────────────────────────

# `.key` occasionally means something innocent (a translation key file, a Keynote export). Refusing it and
# saying why is the cheaper of the two available mistakes.
_DENIED_SUFFIXES = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".p8", ".der", ".keystore", ".jks", ".jceks", ".asc", ".gpg", ".pgp",
    ".kdbx", ".kdb", ".agilekeychain", ".opvault", ".ovpn", ".ppk", ".mobileconfig", ".pkcs12",
})


def _norm(text: str) -> str:
    """Case-folded and Unicode-normalized, so the comparison is about the FILE and not about how its name was
    spelled on the way in. NFKC first, then casefold — casefold is the aggressive sibling of `.lower()` and is
    what makes a Turkish dotted capital compare equal to its ASCII form."""
    return unicodedata.normalize("NFKC", text).casefold()


def windows_reason(raw: str) -> str | None:
    """Windows path syntax that reaches past a name rather than being one. Returns the offending shape or None.

    Checked on the RAW string, before any resolution, because that is the only place these are still visible:

      ALTERNATE DATA STREAMS (`notes.txt:hidden`) are a second file living inside the first. `Path.resolve()`
      keeps the suffix, every name check sees `notes.txt`, and the read returns the stream instead of the file.

      UNC PATHS (`\\\\server\\share\\x`) are not on this machine at all. A daemon whose entire promise is "the
      user's own files, under permissions the user granted" has no business opening a network share, and the
      allowlist cannot meaningfully contain one.

      DEVICE NAMES (`CON`, `NUL`, `COM1`, `LPT1`) are not files. Opening one can block forever or talk to
      hardware; either way it is not a document.

    Returns None on POSIX for everything but the device names, which are harmless there and worth refusing
    anyway so that behaviour does not change with the platform underneath a shared allowlist."""
    text = raw.strip()

    if os.name == "nt":
        if text.startswith("\\\\") or text.startswith("//"):
            return "a network share"
        # `C:` is a drive, not a stream. Anything AFTER the drive letter's colon is one.
        without_drive = text[2:] if len(text) > 1 and text[1] == ":" else text
        if ":" in without_drive:
            return "an alternate data stream"

    # The last component, split on BOTH separators rather than by `Path`. On POSIX a backslash is an ordinary
    # character, so `Path("C:\\Docs\\NUL").name` is the whole string and the device check silently never fires —
    # a rule that only works on the platform it was written for is a rule that fails on the shared allowlist a
    # user carries between two machines.
    last = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    stem = _norm(last.split(".", 1)[0])
    if stem in {"con", "prn", "aux", "nul"} or (
        len(stem) == 4 and stem[:3] in {"com", "lpt"} and stem[3].isdigit()
    ):
        return f"the device name '{stem}'"
    return None


def reason_for(resolved: Path) -> str | None:
    """Does this ALREADY-RESOLVED path cross the never-served list? Returns the offending token, or None.

    Takes a resolved path on purpose: the whole reason the caller resolves first is that `~/Documents/../.ssh`
    and a symlink into `~/.ssh` both look innocent until you do."""
    for segment in resolved.parts:
        if _norm(segment) in _DENIED_SEGMENTS:
            return segment

    name = _norm(resolved.name)
    if name in _DENIED_NAMES:
        return resolved.name
    for prefix in _DENIED_PREFIXES:
        if name.startswith(prefix):
            return f"{prefix}*"
    if _norm(resolved.suffix) in _DENIED_SUFFIXES:
        return f"*{resolved.suffix.lower()}"
    return None
