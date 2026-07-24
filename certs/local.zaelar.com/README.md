# Shared certificate for `local.zaelar.com`

`local.zaelar.com` resolves via a **bare, unproxied DNS A record to `127.0.0.1`** — every user's own
browser resolves it to their own machine, never a shared server (same trick that made the old plain-HTTP
redirect work, just now serving real HTTPS instead of bouncing to `http://localhost:PORT`).

For the browser to accept that HTTPS without warnings, the engine needs a certificate that's actually
valid for the hostname `local.zaelar.com`. Since there's no way to run a per-user domain-ownership
challenge against `127.0.0.1`, **every self-hosted install ships and presents the SAME certificate** —
the same trade-off Plex accepts with `*.plex.direct`.

**What this means, explicitly:**
- `privkey.pem` is a real private key, **intentionally committed** to this public repo (unlike every
  other credential file, which is gitignored). Anyone with the repo has it. That's fine — it protects
  against a passive eavesdropper on your own LAN, not against "another install of the same software",
  which isn't a meaningful threat model here (if someone has the software, they already have the key).
- It is issued for `local.zaelar.com` **only** — not a wildcard, not `my.zaelar.com` (that one goes
  through Cloudflare's own edge cert, unrelated to this).

**Renewal:** issued via Let's Encrypt (DNS-01, Cloudflare). Valid 90 days from issuance. Check
`openssl x509 -in fullchain.pem -noout -enddate`. Re-issuing (team-side, needs the Cloudflare account
token, not something an end user does):

```bash
certbot certonly --dns-cloudflare --dns-cloudflare-credentials cloudflare.ini \
  -d local.zaelar.com --non-interactive --agree-tos -m <team-email>
```

then replace `fullchain.pem`/`privkey.pem` here and cut a release — installs pick up the new cert on
next `./zaelar update` + restart. **No automated rotation pipeline exists yet** — this is a manual,
periodic task until one is built (a background check + fetch-latest-cert endpoint would close that gap).
