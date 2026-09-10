# torrent — Descargas (V2-637, redesigned as a manager)

Backed by `connectors/torrent/` (libtorrent, pure-Python wheel — nothing installed on the host). The search
is a MeshKore network agent, not this widget; here we download the magnet and manage it.

**Operator's redesign brief** (this pass): it has to look like a real torrent client. Two lists — files that
are SEEDS (finished, still sharing back) on one side, files still DOWNLOADING (or finished but not yet
reannounced as seeding) on the other. Per-row: play, save, remove-torrent-and-file, like any client. One
download alone should NOT take the whole screen as a fixed layout — the single-download "hero" card (kept
from the original, he liked it) is fine for exactly one; several downloads switch to a compact row list.
A playable video row gets a ▶ that streams it for real THROUGH THE VIDEO WIDGET (`youtube`), not inline here.

- **This widget never plays anything itself anymore** — no `<video>`/`<audio>` element. `open {id}` hands
  video rows to `youtube` (`play_torrent` with an `id`, adopting the SAME session handle — no re-search,
  no re-download) and finished-playable audio rows to `musica` (`play_local`, after filing). The hand-off
  goes through `nucleo/torrent_router.py`, never a direct import of the sibling widget from here —
  `widgets/AGENTS.md`'s isolation rule ("widgets are dumb and never talk to each other") is real; a widget's
  own `apply_action` must not reach into another widget's store.
- **The list is `connectors.torrent.service.active()`, live, every render** — NO private bookkeeping of
  "my" downloads. The client is a SYSTEM tool (V2-638): a magnet started here, from `youtube`'s own
  `play_torrent`, or by voice, all show on the same shelf. The store only remembers a title per id, as a
  display nicety before metadata resolves, pruned against the live set on every write.
- **Actions ARE the skills** (V2-544): `search {query,keep}`, `add_magnet {magnet,keep}` (was `play`),
  `open {id}` (route to the player), `save {id}` (file a FINISHED download onto its shelf, for a format
  the browser can't play or just to keep it — `ref:"id"`), `remove {id}` (cancel + delete, `confirm:true`,
  `ref:"id"`), `poll`. Driven via the generic `widget_data` tool.
- `data.py` reaches `connectors.torrent.service` (deferred import; in `validator._STDLIB_EXEMPT`).
- `service.file_it()` now RETIRES the torrent handle after a successful move (`delete_files=False` — the
  file is already gone from the sandbox): a handle whose file just moved out from under it would otherwise
  linger in `active()` pointing at a dead path.
- `widget.js` rebuilds only the row list on each render; the shell (header + collapsible "+ Magnet" quick-add
  box) is built once, so the magnet input never loses what the operator is mid-typing.
- Row delete asks a real "¿Eliminar y borrar el fichero? Sí / Cancelar" inline (`agenda`'s own
  `confirmDel` two-step click pattern) — a raw UI click bypasses the brain's `confirm` gate entirely, so a
  destructive button needs its OWN confirm step in the widget.

Full mechanism: `.meshkore/docs/modules/zaelar-torrent-addon.md`. Tests: connectors/unit/torrent (sections
4-6), browser/unit/youtube (source id-adoption), phone-render fixture (`torrent` in
`tests/browser/e2e/mobile/render_widgets_on_a_phone.py`). Node 5.22.

**Known, deliberate limitation**: there is no generic "open the folder" gesture — this is a web app, not a
filesystem browser, and no such widget exists yet. `save {id}` puts a finished file onto its shelf
(`library/video|audio|documents/`) via `library.index.file_into_place`, but neither `youtube` nor `musica`
has a "browse everything filed" tab today — `youtube`'s tabs are Inicio/Reproductor/Cola/Suscripciones/
Listas, `musica` only shows a played local track in Recientes/Top. So "ir a la carpeta" only really lands
somewhere once the operator PLAYS the saved file (`open`, if it's a playable video/audio); a filed but
unplayable file (a document, an archive) is on disk with a `download_url` but genuinely has no place to
browse to yet — would need a generic library-browser widget, out of scope here. Checked, not assumed.
