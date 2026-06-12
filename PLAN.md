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
- Aligned the shared frontend API client with the real backend endpoints, response shapes, and error handling used by the project flows.
- Added a frontend unit test setup with Vitest and Testing Library for the first critical project flows.
- Expanded frontend regression tests to cover project details editing/deletion, chat interactions, generation pinning, rate limiting, and DOCX export behavior.
- Added browser-level smoke coverage with Playwright for real create/edit/delete project flows and file uploads against the live local stack.
- Expanded browser smoke coverage with deterministic seeded checks for outline visibility, generations panel opening, export readiness, and stale export conflicts.
- Added deterministic browser smoke coverage for chat-driven opening of outline and generations panels without relying on a live LLM response.
- Stabilized local startup by moving the Dockerized web dev server away from Turbopack on Windows mounts, adding a web healthcheck, and adding a startup script that waits for readiness before opening the app.
- Moved all-sections proposal generation to a persisted background job with progress polling in the Generations panel.
- Expanded deterministic browser smoke coverage for background generation progress, section regeneration reloads, and chat-driven variant pinning.
- Added project grounding context for drafting and verification so generated sections use tender scope excerpts and schedule tasks, not only example snippets.
- Made all-section background generation resilient to transient LLM connection failures by preserving successful sections and recording failed sections for retry.
- Added an explicit retry/continue action for failed all-section generation jobs so users can resume after network interruptions.
- Made drafting tolerant of temporary Lex.bg/legislation module failures by continuing generation without normative citations when the external source is unavailable.
- Reframed the legislation module as an automatic Lex.bg-backed normative base with visible status and manual refresh, while keeping uploads only for project-specific supplemental acts.
- Improved stale DOCX export handling with a visible regeneration path, section counts, and Playwright coverage for the real UI warning flow.
- Hardened the create/edit/delete browser smoke test against local Next.js dev navigation hangs by waiting for the actual delete response before verifying the project list.

## Active Goals

1. Keep documentation as a reliable source of truth tied to the real repository state.
2. Reduce drift between code, documentation, and workflows.
3. Continue stabilizing the codebase after the documentation foundation is in place.
4. Add real regression protection so fixing one area does not silently break another.

## Next Recommended Steps

1. Expand generated documentation with more precise backend endpoint and workflow coverage.
2. Re-test live proposal generation quality on a real tender project and tune grounding selection if specific project parts or schedule tasks are still missed.
3. Build broader regression coverage around the frontend so changes in one area are checked against breakage in other core flows.
4. Improve engineering docs for architecture, runbooks, and testing strategy.

## Notes

- `env.txt` is intentionally not tracked.
- This file is the shared working plan and should be updated as decisions and priorities change.
- Frontend stability is now a top priority because the UI has been breaking repeatedly.
- The goal is not only to fix current issues, but to create test coverage that gives confidence against regressions.
- Current stability baseline for the web app now includes lint, TypeScript, Vitest regression coverage, and Playwright smoke tests on the live local environment.
