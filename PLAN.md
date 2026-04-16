# Project Plan

## Working Agreements

- Codex works with high autonomy on tasks end-to-end.
- Every completed Codex change is committed to the Git repository.
- Codex may push completed commits to `origin/main`.
- Secrets, passwords, API keys, `.env` files, and similar sensitive files must never be committed.
- Existing unrelated local files must not be staged by accident.

## Current Setup Decisions

- Git remote is connected to `https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya`.
- Git commits are configured with:
  - `Недялко Даскалов`
  - `n.daskalov@raicommerce.bg`
- Local documentation automation uses `py -3` on Windows instead of `python`.
- Versioned git hooks are enabled through `core.hooksPath=.githooks`.

## Completed Work

- Reviewed the repository structure, architecture, toolchain, and documentation quality.
- Identified documentation drift between README claims and the real codebase.
- Reworked `README.md` into a stable entry point.
- Added generated engineering documentation in `docs/ENGINEERING_OVERVIEW.md`.
- Added `scripts/generate_docs.py` to build engineering documentation from repo facts.
- Added `.githooks/pre-commit`, `.githooks/pre-push`, and `.githooks/run-docs`.
- Added CI validation for generated docs.
- Added GitHub workflow `docs-sync.yml` to keep generated docs in sync after push.

## Active Goals

1. Keep documentation as a reliable source of truth tied to the real repository state.
2. Reduce drift between code, documentation, and workflows.
3. Continue stabilizing the codebase after the documentation foundation is in place.
4. Add real regression protection so fixing one area does not silently break another.

## Next Recommended Steps

1. Expand generated documentation with more precise backend endpoint and workflow coverage.
2. Fix contract mismatches between frontend and backend APIs.
3. Add real frontend and integration-style tests for the critical user flows, especially project creation, editing, listing, chat, file upload, generations, and export.
4. Build regression coverage around the frontend so changes in one area are checked against breakage in other core flows.
5. Improve engineering docs for architecture, runbooks, and testing strategy.

## Notes

- `env.txt` is intentionally not tracked.
- This file is the shared working plan and should be updated as decisions and priorities change.
- Frontend stability is now a top priority because the UI has been breaking repeatedly.
- The goal is not only to fix current issues, but to create test coverage that gives confidence against regressions.
