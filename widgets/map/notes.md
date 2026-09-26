# map — notes

- 2026-09-26 · Built for the operator's demo script («Find me three things I might enjoy doing this weekend» →
  «Show them on a map»); before it the agent said «I don't have a map widget».
- Places arrive by name + address/city; data.py geocodes them (Photon, Nominatim as stand-in — OpenStreetMap,
  no key) inside the 8 s action budget and never accepts invented coordinates from the model as a requirement.
- Tiles are plain <img> (CARTO Voyager, attribution drawn on the map); no map library, no fetch from widget.js.
- The view fits every pin and re-fits on resize (one ResizeObserver per card). Pins and rows select through
  ctx.action("select").
