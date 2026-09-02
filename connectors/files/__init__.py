"""Cloud file connectors (Google Drive, OneDrive) — V2-557.

The public seam is `service.py`; `providers.py` is the registry, `oauth.py` the shared PKCE flow, and
`gdrive.py`/`onedrive.py` the per-provider HTTP clients.
"""
