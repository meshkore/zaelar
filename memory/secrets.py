"""memory/secrets.py — detección FAIL-CLOSED de secretos del operador (V2-060).

Antes de que un turno se destile en píldoras, este módulo decide **si contiene un SECRETO** (contraseña, PIN,
IBAN, tarjeta, private key de wallet, seed phrase, API key, nº de cuenta) y, si lo hay, captura la **etiqueta**
(en claro, buscable) + el **valor** (a cifrar) y **redacta** el valor del texto para que el LLM destilador NUNCA
lo vea.

**FAIL-CLOSED (regla invertida frente al resto de la memoria):** un secreto que se cuele en claro = privacidad
rota. Por eso, ante la duda, esto marca secreto (un falso positivo —cifrar de más— es barato; un falso negativo
—dejar un secreto en claro— es inaceptable). La extracción NLP fina (label/valor de habla libre) es mejorable con
ayuda del LLM en el futuro; esta capa determinista es el suelo que siempre corre.

Es stdlib puro (sin deps, sin importar el core) → se puede usar desde cualquier capa.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

REDACTION = "«secreto guardado»"   # lo que ve el LLM en lugar del valor


@dataclass
class Detected:
    label: str          # etiqueta en claro y buscable ("contraseña de Netflix")
    value: str          # el secreto a cifrar
    slot: str           # clave canónica para supersede ("secret:netflix:password")
    sensitivity: str    # "high" | "critical"
    kind: str           # "password" | "pin" | "card" | "iban" | "key" | "seed" | "account" | "secret"
    span: tuple[int, int]   # (inicio, fin) del VALOR en el texto original (para redactar)


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
    # el valor termina en la frase: corta en un salto de línea o un cierre claro
    v = re.split(r"[\n\r]", v)[0].strip()
    return v


# ── patrón por MARCADOR explícito (contraseña/clave/pin/usuario de X es Y) ──────────────────────────────────
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

# marcador SIN servicio: "mi contraseña es X" / "guárdame esta clave: X" (servicio genérico)
_MARKER_NOSVC_RE = re.compile(
    r"\b(?:mi|la|una|el|est[ae]|es[ae])\s+(?P<type>contrase[nñ]a|password|clave|pin)\s*[,:]?\s*(?:es|:|=)\s+"
    r"(?P<val>.+)", re.IGNORECASE)

# marcador de servicio SIN conector "es" — «(guárdame) la contraseña del mail? CASAXX66gg12» / «la clave de la
# wifi, RouterCasa2024». Casa <tipo> de <servicio> y el VALOR se busca aparte con _CRED_TOKEN_RE.
_SVC_ONLY_RE = re.compile(
    r"\b(?P<type>contrase[nñ]as?|password|pass|clave privada|clave|pin|c[oó]digo|usuario y contrase[nñ]a|"
    r"credenciales)\s+(?:de la|de mi|del|de|para)\s+(?P<svc>[^,:=?!.\n]{1,40}?)(?=[\s,:?¿!.]|$)",
    re.IGNORECASE)
# token con PINTA de credencial: ≥6 chars con AL MENOS una letra Y un dígito (contraseña típica). Evita cazar
# palabras normales; solo se usa cuando YA hay un marcador de secreto en la frase (contexto), FAIL-CLOSED.
_CRED_TOKEN_RE = re.compile(r"(?<![\w@#$%._/+-])(?=[^\s]*[A-Za-z])(?=[^\s]*\d)[A-Za-z0-9@#$%._/+-]{6,}(?![\w])")


def _type_of(word: str) -> str:
    w = _strip_accents(word.lower())
    for k, v in _TYPE_WORDS.items():
        if _strip_accents(k) in w:
            return v
    return "password"


# ── detectores ESTRUCTURALES (el valor aparece crudo, sin marcador) ─────────────────────────────────────────
_EVM_KEY_RE = re.compile(r"\b0x[0-9a-fA-F]{64}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,30}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SEED_MARKER_RE = re.compile(
    r"\b(seed|frase semilla|frase de recuperaci[oó]n|recovery phrase|mnemonic|clave de recuperaci[oó]n)\b", re.I)
_APIKEY_RE = re.compile(r"\b(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b")


def detect(text: str) -> list[Detected]:
    """Devuelve la lista de secretos detectados en `text` (vacía si no hay). FAIL-CLOSED."""
    if not text or not text.strip():
        return []
    out: list[Detected] = []
    claimed: list[tuple[int, int]] = []   # spans ya reclamados (evita doble-detección)

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

    # 2b) marcador de servicio SIN conector "es" + un token con pinta de credencial en la frase
    #     («puedo guardarme la contraseña del mail? CASAXX66gg12»). Solo si el marcador con conector no lo cazó ya.
    if not any(d.kind in ("password", "pin") for d in out):
        for m in _SVC_ONLY_RE.finditer(text):
            if _overlaps(m.start(), m.end()):
                continue
            tok = None
            for tm in _CRED_TOKEN_RE.finditer(text):
                if _overlaps(tm.start(), tm.end()):
                    continue
                if m.start() <= tm.start() < m.end():        # el token está DENTRO del marcador (svc) → no
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

    # 3) estructurales — el valor crudo (fuera de un span ya reclamado)
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
        # seed phrase: 12/24 palabras — solo si hay marcador de 'seed' cerca (evita falsos positivos de frases)
        words = re.findall(r"\b[a-záéíóúñ]{3,}\b", text.lower())
        if len(words) >= 12:
            out.append(Detected(label="seed phrase (frase de recuperación)", value=text.strip(),
                                 slot="secret:wallet:seed", sensitivity="critical", kind="seed",
                                 span=(0, len(text))))

    return out


def redact(text: str) -> tuple[str, list[Detected]]:
    """Devuelve (texto_con_valores_redactados, detectados). El LLM ve `REDACTION` en lugar de cada secreto, así
    conserva el contexto ('mi contraseña de Netflix es «secreto guardado»') sin ver el valor."""
    found = detect(text)
    if not found:
        return text, []
    # redacta de derecha a izquierda para no descuadrar los offsets
    red = text
    for d in sorted(found, key=lambda x: x.span[0], reverse=True):
        s, e = d.span
        red = red[:s] + REDACTION + red[e:]
    return red, found
