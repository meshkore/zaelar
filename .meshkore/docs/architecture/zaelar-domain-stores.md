# Domain stores — one canonical home per datum, and what memory is NOT for

**The rule (operator directive, 2026-09-09): every domain has exactly ONE canonical store. Central memory
holds only (a) distilled durable personal facts and (b) short-lived salience impressions. Widgets render
views. Nothing permanent lives twice.**

This is the guide for anyone adding or extending a widget/connector that holds data — music, video, books,
audiobooks, whatever comes. It exists because the question «where does this datum live?» kept being answered
ad hoc, and the one domain that answered it wrong (messages, fixed in V2-628) ended up writing every byte
twice and keeping neither copy.

## The three organs

| Organ | What lives there | Lifespan | Examples |
|---|---|---|---|
| **Domain store** (per widget/connector, under `widgets/_data/<id>/`) | The domain's own records and caches | Canonical — as long as the domain wants | photo index + thumbnails, file metadata, the contacts directory, playlists, the communications archive |
| **Central memory** (`memory/`, pills) | Distilled durable PERSONAL facts, and short-lived salience | Facts: durable, slot-governed. Salience: decays in days | «his daughter is called Abril», «he likes Madonna», a `msg` impression that fades |
| **Views** (widget UI state, prompt briefs, caches) | Whatever a surface needs to paint or a prompt needs to say | Expiring by design | the messaging inbox/threads, a lens criterion, `memory_cache` |

The test for each datum is one question: **who would re-derive it, and from where?** If the answer is «nobody
— this record IS the source», it belongs in a domain store. If the answer is «it is a fact about the PERSON
that any surface might need», it is a memory pill. If the answer is «it can be rebuilt from a canonical
store», it is a view and may expire freely.

## The map today

- **Photos** → `widgets/_data/fotos/` (index + cached thumbnails; canonical because Google's Picker URLs die
  in an hour — V2-564). Memory gets nothing per photo.
- **Files (cloud)** → `connectors/files/` facade; the providers are canonical, we cache metadata.
- **Contacts / favourites** → the unified directory (V2-541): a favourite IS a directory entry. This one
  legitimately lives in memory's slot machinery because it is personal-durable by nature.
- **Messages** → the **communications archive** (`connectors/messaging/archive.py`, V2-628): append-only,
  catalogued, cross-platform (platform is a column, not a silo), fed at the store's write seams including
  outbound. The inbox/threads are expiring views; the `kind='msg'` pills are decaying salience. **Neither is
  the record anymore.**
- **Music** → `widgets/_data/musica/` owns playlists, play counts / most-played, cover-art cache, followed
  artists. Memory gets the distilled preference («likes Madonna» — a `pref` pill), never the playlist rows.
  (Being settled with the music-widget work, 2026-09-09; this section is the contract to build against.)
- **Video** → same shape (V2-604 already ruled it: the widget OWNS its library and watch history — we record
  what WE play; a connector only extends).

## The rules that keep it clean

1. **No permanent datum in two places.** An expiring cache over a canonical store is fine (that is what a
   cache is); two expiring copies over nothing, or two permanent copies, are the two failure shapes.
2. **Memory never stores a domain's ROWS.** «His 40-song playlist» is domain data; «he loves this album» is a
   fact about him. The HEART distills the second from conversation — a widget must never bulk-write rows into
   memory pills. (The one sanctioned bridge: a short-lived salience impression, like `msg` pills, clearly
   decaying and never the record.)
3. **Promotion is the heart's job.** Important data arriving THROUGH a domain (a policy number in a chat
   message) becomes a personal fact via the distiller, with the secrets floor (V2-060) encrypting sensitive
   values. A widget does not decide what is biographical.
4. **A domain store is queryable, structured, and its OWN file** (SQLite when it needs search/joins, the
   widget `state.json` when it is small UI-shaped state). It never rides inside `zaelar.db`'s memory tables —
   personal memory stays small.
5. **Views may die at any moment** and the product must survive it: anything a view holds must be re-derivable
   from a canonical store. If losing it would lose information, it was not a view.
6. **When someone refers to domain data by voice** («that email from the school», «my most played songs»),
   the search channels to the DOMAIN store — never to memory recall. Memory recall answers questions about
   the person, not about the catalog.

## Checklist for a NEW widget with data (video, books, audiobooks…)

- [ ] Name the canonical records (library, history, favourites-of-the-domain, caches) → domain store.
- [ ] Name what is genuinely personal-durable («prefers dubbed audio») → memory, via the distiller, usually a
      `pref`/`fact` pill or a slot — never written in bulk by the widget.
- [ ] Every UI/prompt surface reads from the store; nothing it holds is the only copy.
- [ ] If people will ask time/name-scoped questions («last month», «from the school»), give the store real
      columns + FTS — do not lean on memory recall for catalog questions.
- [ ] Media caches (covers, thumbnails) live in the widget data dir, keyed, evictable.
