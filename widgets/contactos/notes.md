# contactos — decision log

Read before editing; append after.

- 2026-09-01 · V2-541 · Born. ONE directory for every identity (person/place/company) — the operator's direct
  order: a favourite restaurant IS an entry here with `favorite` as a flag, never a per-kind list (the generated
  `restaurantes-favoritos-operador` widget was deleted the same day so only this one exists). Record shape
  follows the V2-523 plan (kind, parentId nesting, freeform group labels) so the eventual memory/state
  integration is a projection, not a rewrite.
- 2026-09-01 · The VIEW is an action from birth (`show_view`/`show_contact`, witness counter + `_VIEW_TTL_S`
  server-side) — the agenda's V2-540 lesson applied before the incident instead of after. `show_view` also
  RETURNS the matches (`result.matches`) so «¿cuál es mi restaurante favorito en Barcelona?» is one call.
- 2026-09-01 · `add_contact` dedups by normalized name+city (update, never duplicate — the V2-208 family);
  a nameless add is an ERROR that teaches the retry shape (V2-473: the write does not invent).
- 2026-09-01 · Group matching is containment over accent-stripped forms, both directions
  («fontanero» ↔ «fontaneros») — never a synonym table (no-hardcoded-understanding rule).

## 2026-09-04 — prompt_digest (V2-576)
The card publishes its contents to the turn prompt while open (refs.prompt_digest seam): counts,
view filter, rows. Born from the favourites session where the voice answered from stale memory
against the visible list and confabulated a view explanation. See CLAUDE.md decision V2-576.

## 2026-09-17 — V2-715 · the directory ORGANISES ITSELF, and a platform is a FILTER

His redesign order, with the card open on 2 688 contacts. Four things, and the first three are one idea:

1. **Two bars, counting the window.** «La barra del sistema parece un espacio desaprovechado… me vuelves a
   repetir un icono de contactos, el nombre de contactos.» The brand disc and the content title came off
   (the canvas header already says «Contactos»), the kind tab strip came off with them, and what is left is
   ONE bar: search · provider icons · plug. The house standard was amended, not broken — see
   `.meshkore/docs/conventions/zaelar-widget-header-standard.md` §AMENDMENT.
2. **The rail is DERIVED.** «Un contacto nunca va a ser un lugar, con lo cual eso no tiene ningún sentido
   ahí… en la barra lateral es donde vayamos a desarrollar de forma dinámica todo lo que tenemos.» Kinds,
   labels, cities and the hidden shelf are TALLIED from the rows on screen; a section with nothing in it is
   not drawn, and a single kind is not a classification. The count lives on its row — «Todos (2 688)».
3. **A source icon FILTERS.** His own correction of the V2-699 shape he had asked for. Belonging is both
   halves — where the row came from AND where he can reach the person (`model.source_matches`) — so somebody
   typed here and later matched to a Telegram account IS a Telegram contact. An unlinked source keeps
   opening the connectors screen: there is nothing to filter and «conéctalo» is the only useful answer.
4. **The record grew.** `phones` / `emails`, several per entry, each with a free label; `phone`/`email` stay
   as the PRIMARY and `model.normalize` keeps the two in step in both directions, because four modules
   outside this widget read the scalar. Schema v1 → v2, migrated lazily and ROW BY ROW inside its own `try`
   (a raising migration degrades to the seed, which here is an empty address book).

Also: the LIST is capped at 120 rows with «ver más» (his directory is 2 688 and every row used to become a
DOM node on every keystroke); the hidden shelf became reachable and undoable; `link_contact` got a control
(it had existed with no button since V2-541); and `show_connectors` was added so the plug has a voice.

⚠️ **`show_view` had carried `kind` and `source` since V2-714 and `widget.js` read NEITHER** — the spoken
answer filtered and the card did not, which is the two-surfaces-disagreeing failure `prompt_digest` exists
to prevent. Found by a test, not by reading.

⚠️ **A click and a sentence are not the same filter.** A rail click means «show me THIS» and replaces the
whole selection; «mi restaurante favorito en Barcelona» is group + city + favourites at once. The first cut
of the rail was single-axis and broke exactly that case — the card holds all of them now, and only a click
clears the others.
