# Investments: design notes

## Origin (2026-08-10)
- The operator asked to improve an investments/tokens dashboard with a disk/donut plus small text boxes.
  **No investments widget existed in the system** (verified in `widgets/`, `results`, `navegador`, and memory).
  It was built from scratch with the requested improvements already included.
- **Example** data (sample=true): BTC/ETH/SOL/ADA. Pending: the operator must provide real positions through
  action `set_holdings`.

## Design Decisions (what the operator asked for; do not regress)
- **Large disk with balanced margins:** the donut panel has `padding-left` == `padding-bottom` (26==26). The donut
  is generous (r=80, stroke 34, about 212px). Do not return to a small donut or asymmetric margins.
- **Text shifted right inside the boxes:** each card has a color bar on the left plus wide `padding-left` (20px).
  Content starts separated from the left edge.
- **4 data items as 2 rows x 2, NOT 4 columns:** each position is its own card (background + border), in a 2x2 grid
  with generous `gap` (13px). Inside the card, name+value are grouped as one unit; between cards, separation is
  clear, making it impossible to confuse one token's value with the next token's name.
- **Graphic resources:** ticker glyphs (BTC/ETH/SOL/ADA-style glyphs), color bar = donut segment, monospaced
  typography for figures, green/red up/down variation, circular swatch icon.

## Structure
- `view_data()` reads from `store` and seeds the example if empty. `apply_action("set_holdings")` replaces the
  whole portfolio with real data. Passive, foreground-only.
- Colors: `COLORS` = accent / accent2 / violet #8B5CF6 / amber #F59E0B (+ extras). Readable in light and dark themes.
