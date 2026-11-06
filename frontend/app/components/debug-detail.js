// Capture gaps (2026-11-06) — what the viewer adds to a row of the new kinds, from structured fields only: a connector's
// sender, subject, result and cause (`connector`), where a voice metric ran (`provider`), the pulse's period numbers
// (`pulse · beat`), and what a Brain Worker's model call was HANDED beside what it answered (`model_call`).
export const detailMeta = (d) => [
  d.platform && d.op && `${d.platform}:${d.op}`, d.from && `from ${d.from}`, d.subject && `«${d.subject}»`,
  d.attachments && `📎${d.attachments}`, d.files && `📎${d.files}`, d.ok === false && d.error && `⚠ ${d.error}`,
  d.provider && !d.model && d.provider, d.kind === "pulse" && d.ticks && `${d.ticks} ticks · avg ${d.avg_ms}ms · max ${d.max_ms}ms · ${d.slow} slow`,
  d.kind === "model_call" && d.tools && d.tools.length && `tools ${d.tools.join(",")}`,
].filter(Boolean);
export const detailText = (d, text) => (d.kind === "model_call" && d.input ? `⇐ ${d.input}  ⇒ ${text}` : text);
