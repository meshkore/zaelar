"""Documentation translated to English."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

REDACTION = "«secreto guardado»"   # translated implementation note


@dataclass
class Detected:
    label: str          # translated implementation note
    value: str          # translated implementation note
    slot: str           # translated implementation note
    sensitivity: str    # "high" | "critical"
    kind: str           # "password" | "pin" | "card" | "iban" | "key" | "seed" | "account" | "secret"
    span: tuple[int, int]   # translated implementation note


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _slug(s: str) -> str:
    s = _strip_accents(s.lower()).strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "generico"


def _luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in digits if c.isdigit()]
    if not (13 <= len(ds) <= 19):
        return False
    total, alt = 0, False
    for d in reversed(ds):
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _clean_value(raw: str) -> str:
    """Quita muletillas iniciales ('es esta:', 'la siguiente:', comillas) del valor capturado."""
    v = raw.strip()
    v = re.sub(r'^(?:es\s+|son\s+)?(?:est[ae]|esto|la siguiente|el siguiente)\b[\s:,-]*', "", v, flags=re.I)
    v = v.strip().strip('"“”\'').strip()
    # translated implementation note
    v = re.split(r"[\n\r]", v)[0].strip()
    return v


# translated implementation note
_TYPE_WORDS = {
    "contraseña": "password", "contrasena": "password", "password": "password", "pass": "password",
    "clave": "password", "contraseñas": "password", "pin": "pin", "código": "pin", "codigo": "pin",
    "usuario y contraseña": "password", "credenciales": "password",
    "número de cuenta": "account", "numero de cuenta": "account", "cuenta": "account",
    "private key": "key", "clave privada": "key", "seed": "seed", "frase semilla": "seed",
    "frase de recuperación": "seed", "recovery phrase": "seed", "mnemonic": "seed",
}
# marcador: <tipo> (de|del|para) <servicio> [,]? (es|son|:|=) <valor>
_MARKER_RE = re.compile(
    r"\b(?P<type>contrase[nñ]as?|password|pass|clave privada|clave|pin|c[oó]digo|usuario y contrase[nñ]a|"
    r"credenciales|n[uú]mero de cuenta|private key|seed|frase semilla|frase de recuperaci[oó]n|recovery phrase|"
    r"mnemonic)\s+(?:de|del|para|de la|de mi)\s+(?P<svc>[^,:=\n]{1,40}?)\s*[,:]?\s*(?:es|son|:|=)\s+(?P<val>.+)",
    re.IGNORECASE)

# translated implementation note
_MARKER_NOSVC_RE = re.compile(
    r"\b(?:mi|la|una|el|est[ae]|es[ae])\s+(?P<type>contrase[nñ]a|password|clave|pin)\s*[,:]?\s*(?:es|:|=)\s+"
    r"(?P<val>.+)", re.IGNORECASE)

# translated implementation note
# translated implementation note
_SVC_ONLY_RE = re.compile(
    r"\b(?P<type>contrase[nñ]as?|password|pass|clave privada|clave|pin|c[oó]digo|usuario y contrase[nñ]a|"
    r"credenciales)\s+(?:de la|de mi|del|de|para)\s+(?P<svc>[^,:=?!.\n]{1,40}?)(?=[\s,:?¿!.]|$)",
    re.IGNORECASE)
# translated implementation note
# translated implementation note
_CRED_TOKEN_RE = re.compile(r"(?<![\w@#$%._/+-])(?=[^\s]*[A-Za-z])(?=[^\s]*\d)[A-Za-z0-9@#$%._/+-]{6,}(?![\w])")


def _type_of(word: str) -> str:
    w = _strip_accents(word.lower())
    for k, v in _TYPE_WORDS.items():
        if _strip_accents(k) in w:
            return v
    return "password"


# translated implementation note
_EVM_KEY_RE = re.compile(r"\b0x[0-9a-fA-F]{64}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,30}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SEED_MARKER_RE = re.compile(
    r"\b(seed|frase semilla|frase de recuperaci[oó]n|recovery phrase|mnemonic|clave de recuperaci[oó]n)\b", re.I)
_APIKEY_RE = re.compile(r"\b(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b")


def detect(text: str) -> list[Detected]:
    """Documentation translated to English."""
    if not text or not text.strip():
        return []
    out: list[Detected] = []
    claimed: list[tuple[int, int]] = []   # translated implementation note

    def _overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in claimed)

    # 1) marcador con servicio
    for m in _MARKER_RE.finditer(text):
        val = _clean_value(m.group("val"))
        if not val:
            continue
        svc = m.group("svc").strip(" .,")
        typ = _type_of(m.group("type"))
        vstart = m.start("val") + (len(m.group("val")) - len(m.group("val").lstrip()))
        out.append(Detected(
            label=f"{m.group('type').strip().lower()} de {svc}",
            value=val, slot=f"secret:{_slug(svc)}:{typ}",
            sensitivity="critical" if typ in ("key", "seed", "account") else "high",
            kind=typ, span=(vstart, m.end("val"))))
        claimed.append((m.start(), m.end()))

    # 2) marcador sin servicio
    for m in _MARKER_NOSVC_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        val = _clean_value(m.group("val"))
        if not val:
            continue
        typ = _type_of(m.group("type"))
        out.append(Detected(
            label=f"{m.group('type').strip().lower()} (sin servicio)", value=val,
            slot=f"secret:generico:{typ}", sensitivity="high", kind=typ,
            span=(m.start("val"), m.end("val"))))
        claimed.append((m.start(), m.end()))

    # translated implementation note
    # translated implementation note
    if not any(d.kind in ("password", "pin") for d in out):
        for m in _SVC_ONLY_RE.finditer(text):
            if _overlaps(m.start(), m.end()):
                continue
            tok = None
            for tm in _CRED_TOKEN_RE.finditer(text):
                if _overlaps(tm.start(), tm.end()):
                    continue
                if m.start() <= tm.start() < m.end():        # translated implementation note
                    continue
                tok = tm
                break
            if not tok:
                continue
            svc = m.group("svc").strip(" .,")
            typ = _type_of(m.group("type"))
            out.append(Detected(
                label=f"{m.group('type').strip().lower()} de {svc}", value=tok.group(0),
                slot=f"secret:{_slug(svc)}:{typ}", sensitivity="high", kind=typ,
                span=(tok.start(), tok.end())))
            claimed.append((m.start(), m.end()))
            claimed.append((tok.start(), tok.end()))
            break

    # translated implementation note
    def _struct(rx, kind, label, sens, guard=None):
        for m in rx.finditer(text):
            if _overlaps(m.start(), m.end()):
                continue
            raw = m.group(0)
            if guard and not guard(raw):
                continue
            out.append(Detected(label=label, value=raw.strip(), slot=f"secret:{kind}:{_slug(raw[-6:])}",
                                 sensitivity=sens, kind=kind, span=(m.start(), m.end())))
            claimed.append((m.start(), m.end()))

    _struct(_EVM_KEY_RE, "key", "private key de wallet", "critical")
    _struct(_IBAN_RE, "iban", "IBAN", "high")
    _struct(_APIKEY_RE, "key", "API key", "critical")
    _struct(_CARD_RE, "card", "número de tarjeta", "high", guard=_luhn_ok)
    if _SEED_MARKER_RE.search(text):
        # translated implementation note
        words = re.findall(r"\b[a-záéíóúñ]{3,}\b", text.lower())
        if len(words) >= 12:
            out.append(Detected(label="seed phrase (frase de recuperación)", value=text.strip(),
                                 slot="secret:wallet:seed", sensitivity="critical", kind="seed",
                                 span=(0, len(text))))

    return out


def redact(text: str) -> tuple[str, list[Detected]]:
    """Documentation translated to English."""
    found = detect(text)
    if not found:
        return text, []
    # translated implementation note
    red = text
    for d in sorted(found, key=lambda x: x.span[0], reverse=True):
        s, e = d.span
        red = red[:s] + REDACTION + red[e:]
    return red, found
