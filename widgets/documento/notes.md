# documento — notes

- **Created 2026-09-02 (V2-549)** on the operator's request: «a widget that is like a blank sheet, a generic
  one, to show other things — a PDF, an HTML, a recipe, a report we make — basically the square, and we fill it
  with the content». Explicit asks: it must be IN the widget list, and the code + its tools must stay LIGHT,
  «without overloading the prompts with skills, tools or other things».
- **Three kinds, closed on purpose**: `markdown` (default), `html`, `pdf`. A fourth kind means a fourth
  renderer inside a widget whose whole value is being small. Photos → `imagenes`. A live page → `navegador`.
  Several options to compare → `results`. Those borders are written into `whenToUse`; do not blur them.
- **The frontier with `results` is WHAT the answer is, not what it contains**: `results` = a set you compare
  (cards, sources, criteria); `documento` = ONE thing you read. The operator's own example: «I asked for a
  recipe and it brought a list of recipes — I only ordered one, and I trust its criteria».
- **No new tool, no new skill.** Three declared actions (`show`, `append`, `clear`) and nothing else; the
  brain drives it with the generic `widget_data`. That was a stated constraint, not an implementation detail.
- **`show` and `append` are `view: true`** (V2-547): `show` is the action that IS this widget's purpose, and an
  unflagged one turns «enséñame la receta» into an empty card.
- **An empty `show` never blanks the sheet** — it returns an error instead (the `imagenes` rule). Leaving the
  operator staring at a blank card is worse than saying nothing arrived.
- **No `innerHTML` anywhere.** The html kind is parsed inert (DOMParser), then whitelisted; `class` and `style`
  are stripped on the way in so a foreign fragment lands in THIS sheet's typography and follows the live theme.
  If you ever need to keep an attribute, add it to the narrow per-tag list, never a blanket pass-through.
- **`prompt_digest` is the reason this beats a screenshot**: with the sheet open, «how much flour?» is a
  question about text we already hold. A PDF says outright that its inside is not readable from here rather
  than letting the model invent it.
- **`live_title: true`** — the card header shows the document's own title, so the body does not repeat it.
