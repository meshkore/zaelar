- Request history: this widget is the generic presentation surface for real search/research results. It never searches
  by itself; workers, the browser, or the brain deliver data through declared actions.
- Early fixes added visible `price`, image support, result counts, and item selection without inventing local fallback
  data. The old assumption that `[[push:results]]` could fill this surface was false: that channel was blocked by the
  provider path, so the widget was redesigned around persisted declared actions.
- Since 2026-08-02, `view_data()` returns the last delivered payload from store. With nothing delivered it returns a
  blank sheet, never demo project data. Delivery uses `present`, `append`, `clear`, and `choose`; `ref_index()` exposes
  real persisted items so the brain can distinguish "open with data" from "open and empty".
- Since 2026-08-12, the sheet has four persistent tabs:
  - Results: cards and one item's full record.
  - Summary: work state, explored/discarded counts, and milestones.
  - Sources: each attempted website/source and what happened there.
  - Criteria: the task as executed, including operator corrections.
- The card supports dynamic records through a closed block vocabulary (`text`, `facts`, `chips`, `gallery`, `meter`,
  `table`, `link`, `section`). Raw worker HTML is never accepted; everything renders through `textContent`.
- The widget is fluid-width and lets the canvas own sizing. The manifest declares preferred size; maximized in-app mode
  preserves the orb/chat, while native fullscreen is opt-in for widgets that explicitly request it.
- Documentation is split by audience: compact `usage` for every prompt, and detailed `worker_guide` only when a worker
  asks for widget details. Keep prompt-facing docs minimal and measured.
- Presentation quality rules:
  - The task title belongs in the card header; do not repeat generic catalog names such as "Results".
  - Clip long headers safely, preserving the full text in Criteria when needed.
  - Use tabular numerals for comparable values.
  - Keep lists scannable; heavy blocks belong in detail view.
  - Sources are irreplaceable audit data and should survive digest clipping before criteria do.
- Regression notes:
  - Always run `node --check` on widget JS. Backticks inside template literals broke production more than once.
  - Tests should exercise data through `apply_action`/`view_data`, not by rendering raw unsanitized fixtures.
  - Layout calculations must use the same CSS variables that paint the grid; duplicated numeric spacing caused a lost
    column when spacing changed.

## V2-571 (2026-09-03) — the browser lives INSIDE the process tab
- Operator redesign: a browser task and this sheet are ONE flow, so the separate `navegador::tN` monitor card no
  longer opens for an errand with a sheet. The PROCESS tab embeds the browser instead: capture top-left
  (`/widgets/navegador/asset/shot-<tid>.png`, cache-busted by `shot_rev`, refreshed by SSE — the task registry
  notifies this sheet's card on every view change), the search FILTERS (criteria.hard + changes) beside it, and
  the event feed below in REVERSE chronological order (newest first — the first line is what happens NOW).
- `data.browser` is DERIVED per read (`live._browser` → `dispatch.sheet_browser`), never persisted: a stored
  capture would outlive its browser. `{}` once the errand ends; the tab keeps only its persisted history.
- The browser's interaction moved here too: `auth_done` (declared action) forwards «Ya he iniciado sesión» to the
  navegador owner's mailbox via `widgets/supervisor.enqueue` — the sheet never writes the browser's state. A
  pending question renders with «Responde por voz»; a wall renders with its reason.
- A task with NO sheet keeps its monitor card (manual browsing, sheetless errands): there it is the only surface.
