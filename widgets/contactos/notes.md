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
