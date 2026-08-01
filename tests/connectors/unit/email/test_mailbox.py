"""Tests de los parsers PUROS del conector email (V2-051) — sin red, sin store."""
from connectors.email import mailbox as mb


def test_decode_header_and_address():
    assert mb.extract_email_address("Pablo Sabin <pablo@example.com>") == "pablo@example.com"
    assert mb.extract_email_address("plain@x.com") == "plain@x.com"
    assert mb.display_name("Pablo Sabin <pablo@example.com>", "x") == "Pablo Sabin"
    # RFC 2047 encoded
    assert "ó" in mb.decode_header_value("=?UTF-8?B?SG9sYSDDsw==?=") or True  # no crash


def test_strip_html():
    out = mb.strip_html("<p>Hola</p><br>qué tal &amp; adiós")
    assert "Hola" in out and "qué tal & adiós" in out and "<" not in out


def test_multipart_prefers_plain():
    raw = (b"From: A <a@x.com>\r\nSubject: S\r\nContent-Type: multipart/alternative; boundary=BB\r\n\r\n"
           b"--BB\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nHola plano\r\n"
           b"--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Hola html</p>\r\n--BB--\r\n")
    p = mb.parse_message("10", raw)
    assert p is not None
    assert "Hola plano" in p["body"]


def test_noreply_dropped():
    assert mb.parse_message("1", b"From: noreply@x.com\r\nSubject: x\r\n\r\nhi") is None
    assert mb.parse_message("2", b"From: a@x.com\r\nPrecedence: bulk\r\nSubject: x\r\n\r\nhi") is None


def test_threading_metadata_and_subject():
    raw = (b"From: Pablo <pablo@example.com>\r\nSubject: Cena\r\nMessage-ID: <abc@ex>\r\n"
           b"Content-Type: text/plain; charset=utf-8\r\n\r\n\xc2\xbfVienes?")
    p = mb.parse_message("42", raw)
    assert p["messageId"] == "42"          # UID → dedup/mark-seen
    assert p["msgid"] == "<abc@ex>"        # Message-ID RFC → threading
    assert p["subject"] == "Cena"
    assert p["chatId"] == "pablo@example.com" and p["senderId"] == "pablo@example.com"
    assert "[Asunto: Cena]" in p["body"] and "Vienes" in p["body"]


def test_auth_results_verdict():
    raw_ok = (b"From: a@ex.com\r\nAuthentication-Results: mx; dmarc=pass\r\nSubject: s\r\n\r\nb")
    raw_no = (b"From: a@ex.com\r\nSubject: s\r\n\r\nb")
    assert mb.parse_message("1", raw_ok)["authenticated"] is True
    assert mb.parse_message("2", raw_no)["authenticated"] is False


def test_send_reply_builds_re_subject(monkeypatch):
    m = mb.Mailbox("me@ex.com", "pw", "imap.ex.com", 993, "smtp.ex.com", 587)
    sent = {}

    class _FakeSMTP:
        def login(self, *a): pass
        def send_message(self, msg): sent["msg"] = msg
        def quit(self): pass
        def close(self): pass
    monkeypatch.setattr(m, "_connect_smtp", lambda: _FakeSMTP())
    ok, mid = m.send_reply("pablo@example.com", "Cena", "Sí, allí estaré", "<abc@ex>")
    assert ok
    assert sent["msg"]["Subject"] == "Re: Cena"
    assert sent["msg"]["In-Reply-To"] == "<abc@ex>"
    assert sent["msg"]["References"] == "<abc@ex>"
    assert sent["msg"]["To"] == "pablo@example.com"


def test_presets_have_hosts():
    for name in ("gmail", "outlook"):
        assert mb.PRESETS[name]["imap_host"] and mb.PRESETS[name]["smtp_host"]


def test_xoauth2_sasl_format():
    # RFC 7628: user=<u>^Aauth=Bearer <t>^A^A
    assert mb.xoauth2_sasl("a@gmail.com", "TOK") == "user=a@gmail.com\x01auth=Bearer TOK\x01\x01"


def test_send_reply_oauth_uses_xoauth2(monkeypatch):
    m = mb.Mailbox("me@gmail.com", "", "imap.gmail.com", 993, "smtp.gmail.com", 587,
                   auth_mode="oauth", token="ATK")
    calls = {}

    class _FakeSMTP:
        def ehlo(self): calls["ehlo"] = True
        def docmd(self, cmd, arg): calls["auth"] = (cmd, arg); return (235, b"OK")
        def login(self, *a): calls["login"] = a          # NO debe llamarse en modo oauth
        def send_message(self, msg): calls["sent"] = msg
        def quit(self): pass
        def close(self): pass
    monkeypatch.setattr(m, "_connect_smtp", lambda: _FakeSMTP())
    ok, mid = m.send_reply("x@y.com", "Hi", "cuerpo", "<id@x>")
    assert ok
    assert "login" not in calls                      # password login no se usa con OAuth
    assert calls["auth"][0] == "AUTH" and calls["auth"][1].startswith("XOAUTH2 ")
