# Standard evolution — catching up with the MeshKore standard

The MeshKore preamble points here. This repo **consumes** the standard and does not publish it, so the
four-file bump (`standard.json` / `standard.md` / `CHANGELOG.md` / `version`) does not apply here.

To catch up:

1. Compare `.meshkore/STANDARD_VERSION` with <https://meshkore.com/standard/version>.
2. Read the changelog entries in between (<https://meshkore.com/standard>).
3. Apply what touches this repo's layout or conventions, then bump `.meshkore/STANDARD_VERSION` in the same commit.
4. The rendered `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` come from `.meshkore/public/AGENT_INSTRUCTIONS.md`: edit the
   operator block in all of them, never only one.
