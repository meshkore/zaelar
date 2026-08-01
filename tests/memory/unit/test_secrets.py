#
# test_secrets.py — detección FAIL-CLOSED de secretos (V2-060). Sin red, stdlib puro.
# Ejecutar: .venv/bin/pytest tests/unit/memory/test_secrets.py
#
from memory import secrets


def _one(text):
    d = secrets.detect(text)
    assert len(d) == 1, f"esperaba 1 detección en {text!r}, hubo {len(d)}: {d}"
    return d[0]


# ── marcador con servicio ─────────────────────────────────────────────────────────────────────────────────
def test_password_with_service():
    d = _one("guárdame la contraseña de Netflix, es Perrito123")
    assert d.value == "Perrito123"
    assert "netflix" in d.slot
    assert d.kind == "password"
    assert "Netflix" in d.label


def test_password_es_esta_filler():
    d = _one("mi contraseña de Spotify es esta: Zorro_2024")
    assert d.value == "Zorro_2024"      # 'es esta:' se limpia


def test_pin_service():
    d = _one("el pin de la tarjeta es 4321")
    assert d.value == "4321"
    assert d.kind == "pin"


def test_marker_without_service():
    d = _one("guárdame esta clave: correochapa88")
    assert d.value == "correochapa88"


# ── marcador de servicio SIN conector "es" + token credencial (bug del operador 2026-07-21) ────────────────
def test_service_no_connector_password_after_question():
    d = _one("puedo guardarme la contraseña del mail? CASAXX66gg12")
    assert d.value == "CASAXX66gg12"
    assert d.kind == "password" and "mail" in d.slot


def test_service_no_connector_comma():
    d = _one("guárdame la contraseña del mail, CASAXX66gg12")
    assert d.value == "CASAXX66gg12"


def test_service_no_connector_de_la_picks_service():
    d = _one("la clave de la wifi RouterCasa2024")
    assert d.value == "RouterCasa2024" and "wifi" in d.slot


def test_read_request_not_a_save():
    # pedir un secreto (sin valor) NO es guardar → no se detecta nada que cifrar
    assert secrets.detect("dame la contraseña del mail") == []
    assert secrets.detect("¿cuál es mi contraseña de Netflix?") == []


# ── estructurales ─────────────────────────────────────────────────────────────────────────────────────────
def test_evm_private_key_critical():
    key = "0x" + "a1b2" * 16
    d = _one(f"apunta la private key {key}")
    assert d.kind == "key" and d.sensitivity == "critical"
    assert key in d.value


def test_iban():
    d = _one("mi IBAN es ES9121000418450200051332")
    # el marcador "cuenta/IBAN" no aplica; lo pilla el detector estructural de IBAN
    assert d.kind == "iban"
    assert "ES9121000418450200051332" in d.value.replace(" ", "")


def test_card_luhn():
    d = _one("guarda mi tarjeta 4111 1111 1111 1111")
    assert d.kind == "card"


def test_card_invalid_luhn_not_detected():
    assert secrets.detect("el pedido número 1234 5678 9012 3456 llega mañana") == []


def test_api_key():
    d = _one("la key es sk-abcdef0123456789ABCDEF")
    assert d.kind == "key" and d.sensitivity == "critical"


# ── redacción (el LLM nunca ve el valor) ──────────────────────────────────────────────────────────────────
def test_redact_removes_value_keeps_context():
    red, found = secrets.redact("mi contraseña de Netflix es Perrito123")
    assert "Perrito123" not in red
    assert secrets.REDACTION in red
    assert "contraseña de Netflix" in red
    assert len(found) == 1


def test_redact_noop_on_plain_text():
    txt = "recuérdame que mañana tengo dentista a las cinco"
    red, found = secrets.redact(txt)
    assert red == txt and found == []


def test_plain_sentence_not_a_secret():
    assert secrets.detect("hoy hace un día estupendo para pasear por el parque") == []
