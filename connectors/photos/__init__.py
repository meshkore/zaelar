"""Photo-library connectors (Google Photos) — V2-564.

The public seam is `service.py`; `providers.py` is the registry, `oauth.py` the PKCE flow, `google_photos.py`
the HTTP client, and `store.py` OUR OWN local index of what has been picked (Google's Picker API never hands
us a standing feed of "the whole library" — see `providers.py` for why).
"""
