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
- Added a local proposal gap analysis script to compare a winning/reference technical proposal against the app-generated proposal by section coverage, volume, missing key terms, and tender-source snippets.
- Ran the first real reference comparison for the Pernik ODL PDF live-ingest project against a submitted winning technical proposal; the generated selected proposal was only about 14% of the reference volume and missed important work-program topics such as stakeholders, construction organization, communication/control/subordination, risk, fire safety, environmental measures, waste, dust, soil protection, and quality controls.
- Updated all-section background generation so sections with only stale evidence are regenerated instead of being skipped as already complete.
- Increased drafting depth expectations and default project grounding context so generation receives more tender excerpts and schedule tasks per section.
- Expanded deterministic tender outline extraction to preserve detailed work-program subtopics when present in the tender documentation: stakeholders, internal communication/coordination/control/subordination, communication with the contracting authority/supervision/institutions, fire safety, concrete risk controls, environmental dust/soil/waste measures, and quality control/documentation.
- Added a universal requirement-checklist extractor that converts tender documentation chunks into atomic requirements with category, importance, source reference, suggested proposal section, and coverage question; the checklist is now included in tender outline extraction prompts and can be rendered as Markdown for diagnostics.
- Exposed the requirement checklist in the application through a backend API endpoint and a project sidebar panel with summary counts, category/importance filters, source references, and local check-off state.
- Added a universal fallback for tender-specific requirements that do not fit predefined categories, and connected requirement checklist items to outline sections through `requirement_ids`, missing-section creation, and outline coverage summaries.
- Added requirement-aware drafting and verification: outline sections now preserve structured checklist items, drafting prompts include a per-section checklist, generated variants store deterministic requirement coverage metadata, and verifier marks missing checklist items as review gaps.
- Surfaced generated-text requirement coverage in the Generations panel and added a DOCX pre-export check that blocks export when selected sections still miss tender checklist requirements.
- Improved logical reconstruction of requirement text extracted from noisy PDFs so wrapped list items and scored sentences are kept as complete checklist requirements, with regression coverage for no-outline risk/quality/environment/specific tender scenarios.
- Re-ran the Pernik requirement-checklist calibration after wrapped-line reconstruction; extracted requirements increased from 92 to 97 and obviously truncated candidate requirements dropped from 50 to 15 in the local diagnostic check.
- Added a conservative procurement-only noise filter for requirement extraction and re-ran Pernik calibration; the checklist settled at 85 requirements with the tracked administrative residuals reduced from 8 to 0.
- Added a deterministic proposal-depth quality gate before DOCX export: selected sections with mapped checklist requirements now need enough developed text for their requirement count, with backend, frontend, and browser smoke coverage for shallow generated sections.
- Hardened generation selection and export readiness: drafting now unselects older section generations before saving a new selected variant, DOCX export blocks ambiguous sections with multiple selected variants, and legacy sections without coverage metadata can still be depth-checked from outline requirements.
- Re-ran the Pernik export readiness check after the duplicate-selected guard; the real project is now correctly blocked before export with 14 ambiguous selected sections that must be resolved before a fresh gap analysis.
- Added a universal duplicate-selected remediation flow in the Generations panel: users can now see all variants for a section, identify sections with multiple selected variants, choose exactly one variant through the existing select endpoint, and re-run export readiness without a database repair.
- Added an explicit DOCX export readiness preflight endpoint and connected the Export button to it so duplicate selections, stale evidence, missing requirement coverage, and shallow selected sections are reported together before download instead of one blocker at a time.
- Re-ran the aggregated readiness preflight against the real Pernik project without mutating data; it currently reports 14 sections with duplicate selected variants and 14 selected sections with stale evidence, with no missing-requirement or shallow-section blockers visible yet.
- Added a targeted stale-selected regeneration flow: the backend can enqueue a drafting job for exactly the selected stale sections, and the Generations panel now shows a bulk regenerate action when stale selected sections are present.
- Added a universal drafting blueprint layer: section checklist items are now grouped by category/topic into structural guidance for the drafting prompt, and the generated blueprint is saved with generation metadata for later diagnostics.
- Made the DOCX export proposal-depth gate blueprint-aware, so selected sections with many requirement structure groups need a developed narrative even when the raw checklist count is modest.
- Surfaced blueprint-aware depth details in the DOCX export warning so users can see when a shallow section is blocked because it has many requirement structure groups.
- Added deterministic common-scenario regression tests that cover no-outline fallback, explicit outline preservation, requirement checklist attachment, drafting blueprint grouping, and blueprint-aware proposal-depth gating.
- Added a non-mutating Markdown DOCX export readiness report endpoint for calibration runs, summarizing duplicate selected variants, stale evidence, missing requirements, shallow/blueprint-heavy sections, and recommended next actions.
- Enriched export readiness diagnostics with outline section titles so calibration reports are readable by humans instead of listing only section UUIDs.
- Exposed the Markdown export readiness report in the web export flow so blocked users can download a calibration/debug report directly from the UI.
- Added a Generations panel attention summary and filter, with frontend unit and browser smoke coverage, that counts duplicate selected variants, stale selected sections, and missing requirement coverage so export blockers are easier to locate and resolve on any project.
- Connected blueprint-aware quality/depth readiness blockers back into the Generations panel attention filter so shallow selected sections flagged by export preflight are visible next to duplicate, stale, and missing-requirement issues.
- Made export warning remediation open the Generations panel already focused on attention/problem sections, reducing manual filtering when resolving readiness blockers on any project.
- Reduced requirement-checklist noise from broad catch-all compliance clauses and PDF scoring-table joins, while preserving concrete compliance requirements and adding a common-scenario regression so noisy rows do not inflate drafting blueprint groups.
- Added a bulk duplicate-selected remediation action in the Generations attention panel that keeps the newest selected variant per ambiguous section through the existing selection endpoint, with frontend and browser coverage.

## Active Goals

1. Turn the application into a reference-quality technical proposal generator that produces detailed, tender-specific Bulgarian proposals rather than short generic sections.
2. Use the winning Pernik technical proposal comparison as the first calibration baseline for outline granularity, grounding coverage, drafting depth, and export readiness.
3. Keep documentation as a reliable source of truth tied to the real repository state.
4. Add regression protection around generation quality so improvements do not silently regress.

## Next Recommended Steps

1. Use the export warning remediation button and the Generations bulk duplicate resolver to clear Pernik's legacy duplicate selected generations, then re-run the aggregated export readiness check.
2. Use the Generations panel bulk stale-regeneration action for Pernik after duplicate selections are resolved; the same attention filter will also surface any blueprint-aware shallow/depth sections reported by the next export preflight.
3. Re-run export readiness and the proposal gap analysis against the winning technical proposal, then calibrate the drafting blueprint and blueprint-aware depth thresholds against the regenerated Pernik output.
4. Expand generated documentation with more precise backend endpoint and workflow coverage.
5. Continue broadening common tender regression coverage with more real-world noisy PDF extraction and DOCX readiness combinations.
6. Use the readiness Markdown report during the next Pernik calibration, then compare the regenerated output against the winning proposal after duplicate selected variants and stale generations are resolved.

## Notes

- `env.txt` is intentionally not tracked.
- This file is the shared working plan and should be updated as decisions and priorities change.
- Frontend stability is now a top priority because the UI has been breaking repeatedly.
- The goal is not only to fix current issues, but to create test coverage that gives confidence against regressions.
- Current stability baseline for the web app now includes lint, TypeScript, Vitest regression coverage, and Playwright smoke tests on the live local environment.
