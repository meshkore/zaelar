# Per-install certificate for `local.zaelar.com`

`local.zaelar.com` resolves via a **bare, unproxied public DNS A record to `127.0.0.1`** — every user's own
browser resolves it to their own machine, never a shared server.

The certificate and key for it are **generated on each install** and never committed:

- `scripts/tls_cert.py` runs from the launchers (`./zaelar start`, `make run`, `make start` /
  `python scripts/zaelar.py start`, `.\zaelar.ps1`). If `fullchain.pem` + `privkey.pem` are missing (or expired)
  and [mkcert](https://github.com/FiloSottile/mkcert) is installed, it issues a certificate for
  `local.zaelar.com`, `localhost` and `127.0.0.1` into this folder, signed by mkcert's **local** CA.
- It never runs `mkcert -install` for you: that adds the local CA to your system and browser trust stores. Run it
  once yourself so the browser accepts the certificate without a warning.
- Without mkcert nothing is generated, the server skips the HTTPS listener (44317) and runs plain HTTP on 43917,
  and the launcher prints one line saying how to enable HTTPS. `http://localhost:43917` keeps the microphone.
- `*.pem` here is gitignored. The server reads the pair from `$ZAELAR_TLS_CERT_DIR` (default: this folder), so
  you can also drop in a certificate of your own.

Until 2026-10-10 every install shipped the SAME Let's Encrypt certificate with its private key committed to the
public repo. That key is retired; do not bring a shared key back.
