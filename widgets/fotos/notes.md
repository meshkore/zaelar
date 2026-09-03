# fotos — decision log

## V2-564 (2026-09-03) — first build

- Google Photos only, via the Picker API. Google shut off third-party read access to a user's *existing*
  library in March 2025 — there is no "browse the whole library" scope left for a third-party app. Apple
  Photos and Amazon Photos are catalog-only (`connectors/catalog/apple-photos.json`,
  `connectors/catalog/amazon-photos.json`, both `state: "not-possible"`) — no connector code for either.
- Everything this widget shows comes from `connectors/photos/store.py`, our own local index of what has been
  picked. Google is never a live source of truth for browsing/searching — only for the one-time import.
- Voice search v1 = date-range (past-oriented, `connectors/photos/service.py::_parse_date_hint`, NOT
  `nucleo/scheduler.py::parse_when`, which is future-only) + a trip label the operator gave a batch, or a
  filename. No visual content recognition. Stated in the manifest so the FlashBrain never claims it.
- The grid virtualizes real DOM nodes (windowed by scroll position, not just `loading="lazy"`) — the
  operator's own worry about a thousand photos on screen eating memory.
- NOT built this pass: a multi-provider picker screen inside the widget (only one real provider exists);
  visual content search; voice-reachability beyond what the manifest's declared actions already give.
