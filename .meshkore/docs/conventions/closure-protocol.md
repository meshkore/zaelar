# Closure protocol — how a batch of work is closed in this repo

The MeshKore preamble points here. The standard's own text is at
<https://meshkore.com/standard#91-commit-attribution--agent--model--meshkore-trailers-v12-revised-v21>.

What this repo adds on top of it (the operator's rules win over the preamble):

1. **The test and its node.** A new test is seen RED under a disarm first, then mapped in `tests/run_testmap.py`.
   A test outside the map does not exist for «is everything green?».
2. **The why** goes in `.meshkore/docs/decisions.md`; a line in `.meshkore/docs/criteria.md` only if a rule changed.
3. **The module log** under `.meshkore/modules/<module>/logs/<YYYY-MM>/` (gitignored on purpose).
4. **Commit with a pathspec** (`git commit -- <paths>`) after checking `git diff --cached --name-only` is empty,
   with the three MeshKore trailers **plus** `Co-Authored-By:` (operator override of §9.1, 2026-09-19), then push.

The full eight-step closure for changes that also touch the website lives in the private workspace root.
