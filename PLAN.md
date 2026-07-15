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
- Updated DOCX export readiness reports to point users to the bulk duplicate resolver and added a common mixed-blocker regression scenario covering duplicate, stale, missing-requirement, and shallow-section remediation guidance.
- Fed the same requirement/blueprint depth thresholds used by DOCX export back into the drafting prompt as a section depth target, so generation is guided toward export-ready narrative depth before the final readiness gate.
- Tightened deterministic generated-text requirement coverage so superficial keyword mentions no longer count as coverage for operational requirements, while storing matched ratios for diagnostics and adding common-scenario regression coverage.
- Reduced generic Bulgarian procurement wording in proposal gap diagnostics so calibration reports focus on substantive missing technical terms instead of common words such as object, activities, order, work, and through.
- Added a per-requirement drafting coverage contract to the universal blueprint prompt so every checklist item asks for concrete action, responsible role, control point, evidence record, sequence link, and source-specific detail.
- Added a pre-export quality gate for incomplete operational response contracts, blocking long but one-sided generated sections that do not visibly cover action, responsible role, control point, evidence record, and sequence link.
- Surfaced incomplete operational response blockers in the Generations attention details with a human-readable label and typed readiness diagnostics.
- Connected incomplete operational response blockers to targeted quality regeneration guidance so remediation jobs ask for the missing response components explicitly.
- Added offline calibration-bundle inputs for archived selected/effective snapshots and readiness reports, including manifest-derived readiness blockers, so real-project gap calibration can run without a live DB/API stack.
- Added executable remediation command hints to calibration manifests so real-project diagnostics point directly to dry-run and execute/wait action commands.
- Hardened calibration action evidence so executed background generation actions without wait proof are marked unverified instead of being accepted as proof for the next bundle.
- Expanded the local proposal gap analysis script with universal topic coverage diagnostics for organization, schedule, quality, risk, environment, communication, safety, and documentation, with a runnable script-level regression test for calibration reports.
- Added actionable calibration recommendations to the proposal gap analysis report so missing or partial topic coverage points back to outline extraction, drafting blueprint grouping, grounding chunks, prompt specificity, and rerunning readiness plus gap analysis after regeneration.
- Updated generated engineering documentation to include script-level regression test inventory so calibration tooling tests are visible alongside backend coverage.
- Added a non-mutating selected-generations Markdown snapshot script for calibration runs, including duplicate selected, missing selected, stale evidence, and outside-outline warnings so gap analysis can run even before DOCX readiness is fully clear.
- Added a non-mutating calibration bundle script that exports the selected-generation Markdown snapshot, runs proposal gap analysis against a reference proposal, and writes a review manifest for repeatable real-project calibration.
- Extended the calibration bundle with the same DOCX readiness Markdown report used by the export flow, so calibration runs now connect reference-gap findings with duplicate, stale, missing-requirement, and shallow-section blockers in one repeatable package.
- Made drafting blueprints and export depth checks topic-aware inside each requirement category, so sections with one broad category but many distinct tender subtopics still require developed coverage and expose topic counts in readiness diagnostics.
- Tightened generated-text requirement coverage so scattered keyword mentions across a section no longer count as coverage unless enough requirement terms appear together in a coherent developed passage, with diagnostics and common-scenario regression coverage.
- Added calibration bundle gates to the manifest so real-project calibration runs now show snapshot warning counts, DOCX readiness status, blocker counts, and warn that gap findings are not final until duplicate/stale readiness blockers are resolved.
- Added an effective newest-selected-per-section calibration snapshot so gap analysis is no longer inflated by legacy duplicate selected variants, while still preserving the raw selected snapshot and readiness gates for forensic review.
- Added universal content-section filtering and Markdown subsection grouping to proposal gap analysis so calibration compares substantive work-program/methodology sections separately from formal front matter, declarations, signatures, forms, and internal generated-text subheadings.
- Added section-level gap diagnostics to proposal calibration reports, mapping weak sections to actionable calibration focus areas: outline mapping, drafting depth, or grounding/checklist coverage, while filtering formal greeting/participant sections out of content comparisons.
- Added calibration-focus rollups to the calibration manifest, summarizing how many gap-report sections point to outline mapping, drafting depth, grounding/checklist coverage, or monitor-only follow-up.
- Added a requirement response plan to drafting blueprints so every checklist item instructs the model to write a concrete action, responsible role, control/evidence record, and sequence or deliverable link when supported by sources.
- Tightened deterministic requirement coverage for operational categories so keyword-complete but undeveloped text no longer counts as covered unless the coherent passage includes operational evidence such as responsible role, control, record, monitoring, acceptance, escalation, or corrective action.
- Surfaced missing-requirement diagnostics in export readiness payloads and Markdown reports so blockers distinguish missing key terms, incoherent scattered coverage, and missing operational evidence.
- Surfaced missing-requirement diagnostic reasons in the Generations panel so users can see when a selected section needs operational evidence, a coherent passage, or key-term coverage before export.
- Added a non-mutating regeneration-priority shortlist to calibration manifests, combining DOCX readiness blockers with section gap diagnostics so reviewers can see which concrete sections to resolve or regenerate first on any project.
- Added a gap quality scorecard to calibration manifests and re-ran the Pernik non-mutating calibration bundle; the current effective generated proposal compares 22 content sections against 23 reference sections but only reaches a 0.15 generated/reference word-volume ratio, confirming that the remaining quality gap is primarily drafting depth and operational detail after readiness blockers are resolved.
- Raised adaptive drafting-depth targets for blueprint-heavy sections and added prompt guidance to distribute the required volume across every major group/topic, so complex technical proposal sections are pushed toward developed operational substance instead of short generic summaries.
- Strengthened common-scenario regressions and DOCX readiness reports for complex blueprint-heavy sections by exposing the suggested words-per-group/topic diagnostic, making shallow-section blockers easier to interpret and harder to regress.
- Surfaced the words-per-group/topic depth diagnostic in the web DOCX export warning so users can see the expected structural depth before opening the Markdown readiness report.
- Passed shallow-section depth details from DOCX export warnings into the Generations panel, so opening the remediation view shows each affected section's current/minimum words, developed sentence target, blueprint groups/topics, and words-per-group/topic guidance.
- Added a universal bulk quality/depth regeneration flow: DOCX readiness shallow-section blockers can now enqueue a targeted drafting job for only the selected sections that fail blueprint-aware depth checks, with backend and frontend regression coverage.
- Added a universal bulk missing-requirements regeneration flow: sections whose selected generation fails deterministic requirement coverage can now enqueue a targeted drafting job, so export blockers for uncovered tender requirements are actionable from the Generations panel.
- Updated calibration manifests to point each DOCX readiness blocker to the corresponding Generations bulk remediation action: duplicate resolver, stale `Regenerate`, missing-requirement `Regenerate coverage`, and shallow/depth `Regenerate detailed`.
- Added stable remediation `action_key` markers to calibration manifest readiness priorities so duplicate, stale, missing-requirement, and quality/depth blockers can be reviewed or automated consistently across projects.
- Re-ran the Pernik non-mutating calibration bundle through the API container after adding remediation action keys; the real manifest now includes `resolve_duplicate_selected` and `regenerate_stale` actions, while the current project remains blocked by 14 duplicate selected sections and 14 stale selected sections, with the generated/reference volume ratio still at 0.15.
- Added a structured `calibration_manifest.json` sidecar for non-mutating calibration bundles, exposing schema version, paths, readiness gates, gap scorecard, focus counts, readiness action keys, and gap priority rows for future UI/automation; verified it on the real Pernik bundle with `resolve_duplicate_selected` and `regenerate_stale` actions for 14 sections each.
- Added a backend bulk duplicate-selected resolver endpoint and connected the Generations panel duplicate action to it, making `resolve_duplicate_selected` an atomic API remediation path that keeps the newest selected generation per ambiguous section.
- Added a universal remediation action dispatcher endpoint and executable API paths in `calibration_manifest.json`, so readiness blocker action keys can be invoked consistently by UI or automation across projects.
- Added a safe calibration manifest action runner script with dry-run by default and explicit `--execute` selection, making manifest remediation paths usable in repeatable calibration workflows outside the web UI.
- Added a universal drafting quality-repair pass before saving generations: if the first draft misses checklist coverage or fails the same depth diagnostics used by export readiness, the drafting agent asks for one targeted rewrite and stores generation-depth diagnostics with the saved variant.
- Added a universal section structure plan to outline sections and drafting prompts, derived from checklist topics, subsections, source references, and writing instructions so generated text preserves tender-specific subtopics instead of collapsing them into generic paragraphs.
- Added common-scenario regression coverage proving that the section structure plan preserves explicit subsections and mapped checklist topics for a complex construction-organization section.
- Enriched calibration gap priority rows with executable remediation action metadata for drafting-depth and grounding/checklist gaps, while keeping outline-mapping gaps as manual review targets until a safe structural regeneration flow exists.
- Extended the calibration manifest action runner to include executable gap-priority actions in addition to readiness actions, deduplicating shared bulk remediation endpoints so dry-run and execute flows do not enqueue the same regeneration twice.
- Added a calibration manifest comparison script for before/after remediation review, reporting readiness blocker deltas, snapshot warning deltas, generated/reference volume-ratio movement, gap-focus changes, executable action changes, and the next universal review step.
- Connected before/after calibration comparison into the calibration bundle itself through an optional previous manifest input, so reruns can write a proof report alongside snapshots, readiness, gap analysis, and manifest outputs.
- Tightened blueprint-aware generation depth checks so long sections must visibly distribute coverage across real drafting blueprint groups/topics, preventing a lengthy but one-topic narrative from passing quality gates for multi-topic tender sections.
- Surfaced uneven blueprint distribution diagnostics through export readiness payloads, Markdown readiness reports, and the Generations remediation panel so users can see which groups/topics are missing before rerunning detailed regeneration.
- Fed missing blueprint group/topic labels into drafting quality-repair feedback so the targeted rewrite knows which tender subtopics to develop, not only that the section is underdistributed.
- Made calibration gap-priority actions executable for concrete sections: manifest rows now carry section-title hints, the action runner posts them as JSON, and the backend remediation dispatcher can queue targeted drafting jobs from those hints.
- Tightened calibration remediation targeting by writing `section_uid` metadata into selected/effective proposal snapshots and preferring exact `section_uids` in manifest action payloads, with title hints retained as a fallback.
- Hardened calibration remediation execution so requested `section_uids` are validated against the current outline before a targeted drafting job is queued, preventing stale manifests from creating empty no-op regeneration jobs.
- Added a repetition-aware generation-depth gate so long sections made from repeated sentence patterns are flagged before export or calibration remediation, forcing real distinct operational detail rather than padded volume.
- Surfaced generation-depth issue labels in DOCX readiness reports and the Generations panel so repetitive/padded text, missing blueprint topics, short sections, and weak sentence development are understandable remediation reasons.
- Made drafting quality repair iterative for up to two targeted passes, so a first weak rewrite that still misses checklist coverage or depth diagnostics is rechecked and repaired again before the generation is saved.
- Added wait/poll support to the calibration manifest action runner, allowing real-project remediation actions to execute and wait for queued generation jobs to finish before the next readiness or calibration rerun.
- Added JSON and Markdown execution reports to the calibration manifest action runner, preserving which remediation actions were planned/executed, their final job status, and any wait results for repeatable calibration evidence.
- Connected calibration action execution reports back into calibration bundles and manifests, so reruns can carry the exact remediation evidence alongside readiness gates, gap scorecards, and before/after comparisons.
- Extended before/after calibration manifest comparisons with remediation execution evidence, showing attached execution report counts, executed action counts, and final job status deltas alongside readiness and gap-score movement.
- Added a repeatable calibration remediation cycle script that runs selected manifest actions, writes action execution reports, and immediately builds the next calibration bundle with the previous manifest and action evidence attached.
- Made before/after calibration recommendations prioritize failed remediation job executions before interpreting readiness or gap-score movement, preventing misleading "improved" conclusions after partial action failure.
- Hardened the calibration remediation cycle script so real `--execute` runs require `--wait`, preventing a rerun bundle from being built before queued generation remediation jobs finish.
- Hardened the calibration remediation cycle script against project mix-ups by validating that the source manifest `project_id` matches the requested rerun `--project-id` before any actions or bundle generation start.
- Added an `--actions-only` mode to the calibration remediation cycle script so manifest remediation actions can be safely dry-run or reported without rebuilding a calibration bundle, avoiding DB/reference proposal dependencies during action validation.
- Made the calibration manifest action runner compatible with older manifests by synthesizing the standard remediation dispatcher API path from `action_key` when `api_path` is missing.
- Added explicit action-execution verdicts to calibration action reports (`ready_for_bundle`, failures, unexecuted actions, and recommendation) so a follow-up calibration bundle is only treated as evidenced after remediation actions are actually executed and completed.
- Propagated action-execution verdicts into calibration manifests and before/after comparisons, so attached dry-run or failed remediation reports block misleading calibration conclusions until actions are executed with `--execute --wait`.
- Added a strict `--require-action-ready` gate to the calibration remediation cycle, allowing proof-oriented reruns to stop before building a new bundle when the attached action report is only a dry-run or otherwise not `ready_for_bundle`.
- Tightened blueprint structure coverage so multi-word drafting topics/groups require enough matched anchor terms before they count as covered, preventing generic repeated wording from passing uneven-distribution quality gates.
- Exposed blueprint anchor match diagnostics in DOCX readiness reports, showing matched/required terms for missing groups or topics so underdistributed sections are easier to repair.
- Surfaced the same blueprint anchor match diagnostics in the Generations remediation panel so users can see partial topic matches directly before running detailed regeneration.
- Fed blueprint anchor match diagnostics into drafting quality-repair prompts, so targeted rewrites know which missing groups/topics have zero or partial term coverage.
- Enriched drafting quality-repair feedback for missing checklist coverage with required/matched term counts, coherent-passage counts, and operational-evidence signal counts so rewrites know exactly why a requirement failed deterministic coverage.
- Added a structured requirement-repair writing plan to drafting quality-repair prompts, turning checklist diagnostics into concrete universal rewrite instructions for missing concepts, coherent passages, and operational evidence.
- Added per-requirement remediation guidance to export readiness JSON and markdown reports, so pre-export blockers now explain how to repair missing concepts, weak coherent passages, and missing operational evidence.
- Surfaced per-requirement remediation guidance in the Generations panel, so users can see the exact repair instruction beside each missing checklist item before choosing regeneration or manual edits.
- Added a short remediation hint to the DOCX export warning for missing requirements, pulling the first actionable guidance items directly from the readiness payload.
- Connected missing-requirements remediation guidance into regeneration jobs and drafting prompts, so targeted reruns carry the exact missing checklist ids, reasons, and repair instructions from export readiness.
- Added a common proposal regression scenario proving missing requirement coverage flows through export readiness, targeted regeneration guidance, drafting prompt guidance, and back into a passing deterministic coverage assessment.
- Extended calibration action execution reports with target summaries from remediation request payloads, making dry-run and executed calibration reports show which section ids or title hints each action will affect.
- Added section target payloads to calibration readiness remediation actions for missing-requirement and shallow-section blockers, so generated manifests can queue targeted regeneration directly from DOCX readiness evidence.
- Preserved missing-requirement remediation guidance for targeted calibration actions by routing `regenerate_missing_requirements` section-specific requests through the readiness-aware requirements job builder.
- Surfaced readiness action target summaries in the Markdown calibration manifest, so reviewers can see the exact section ids and title hints that targeted remediation actions will use without opening the JSON.
- Extended before/after calibration manifest comparisons with executable action target deltas, so reviewers can see when the same remediation action now points to different section ids or title hints after reruns.
- Hardened strict calibration remediation cycles by requiring real `--execute --wait` evidence and explicit `--all` or `--action-key` selection before a proof-oriented rerun can proceed.
- Fixed calibration action deduplication so identical bulk remediation actions are still collapsed, but same-endpoint actions with different section target payloads are preserved and executed separately.
- Added backend regression coverage for multi-section targeted remediation, proving API action payloads preserve unique section targets and generation jobs regenerate exactly the requested sections.
- Added calibration manifest regression coverage for multi-section readiness targets, proving JSON action payloads and Markdown target summaries preserve all missing-requirement and quality/depth section targets.
- Made calibration action execution target summaries explicit when long target lists are truncated, so dry-run and execute reports show that additional section ids or title hints exist.
- Made Markdown calibration manifest target summaries explicit when long readiness-action target lists are truncated, matching the action execution and comparison reports.
- Hardened calibration action selection deduplication for readiness actions too, so identical target payloads are executed once while distinct same-endpoint targets are preserved.
- Kept overflow checklist requirements visible in drafting blueprints and prompts, so sections with many same-category requirements still expose every requirement id instead of only the first detailed response-plan items.
- Added blueprint requirement-id counts to generation depth targets and prompts, making large same-category sections visibly demanding even when they have few groups or topics.
- Surfaced blueprint requirement-id counts through export readiness JSON, Markdown readiness reports, export warnings, and the Generations remediation panel so shallow-section diagnostics show large same-category checklist load.
- Tightened requirement coverage for similar operational checklist items by requiring distinctive requirement details, and surfaced those diagnostics into export remediation guidance and drafting repair prompts.
- Validated the real Pernik calibration remediation dry-run in actions-only mode and improved legacy manifest action reports so planned targets remain visible even when older manifests only carry section summaries.
- Added explicit remediation action evidence levels (`planned`, `proof`, `failed`, etc.) to action reports, calibration manifests, and before/after comparisons so dry-run calibration evidence cannot be mistaken for completed remediation.
- Tightened the strict calibration remediation cycle gate so `--require-action-ready` now requires proof-level action evidence when available, while remaining compatible with older ready reports that predate evidence levels.
- Added common-scenario regression coverage for similar operational requirements, proving distinctive missing-requirement diagnostics flow from coverage assessment through export readiness and targeted drafting guidance into a repaired passing section.
- Preserved legacy section-summary targets in before/after calibration comparisons, so older manifests without explicit `request_json` still show which remediation sections changed.
- Preserved distinctive missing-requirement diagnostics in targeted regeneration job guidance, so reruns for similar operational requirements keep the exact distinguishing terms and required distinctive match counts.
- Surfaced structured missing-requirement diagnostics inside targeted drafting guidance prompts, including distinctive detail counts and distinguishing terms for similar operational requirements.
- Surfaced distinctive missing-requirement diagnostics in the Generations panel UI and frontend API types so users can see missing distinguishing details directly before triggering coverage regeneration.
- Added distinctive missing-requirement diagnostics to Markdown DOCX readiness reports, so calibration bundles show missing distinguishing terms and counts before regeneration.
- Added missing-requirement reason summaries to calibration manifest readiness actions, so review bundles show whether uncovered checklist items need distinctive detail, coherent coverage, operational evidence, or other universal repair types.
- Added multi-reason missing-requirement diagnostics across export readiness, Markdown reports, calibration manifests, targeted drafting guidance, and the Generations panel, so one uncovered checklist item can expose every repair cause instead of hiding secondary issues behind a single label.
- Surfaced compact missing-requirement reason summaries directly in the DOCX export warning, so users can see the blocker types before opening the full readiness report or Generations panel.
- Added structured missing-requirement reason counts to calibration manifest JSON actions and before/after comparison reports, so remediation cycles can track whether distinctive-detail, coherent-passage, operational-evidence, or key-term blockers actually decrease.
- Preserved missing-requirement reason counts in calibration action execution JSON and Markdown reports, so remediation evidence records why a missing-requirements action was planned or executed.
- Aggregated missing-requirement reason evidence from attached calibration action reports back into calibration bundle Markdown and JSON summaries, so follow-up bundles show which blocker types were actually targeted by remediation evidence.
- Made generated-text requirement coverage infer operational-detail expectations from uncategorized requirement text and topics, so legacy or fallback checklist items about risk, quality, communication, safety, environment, or documentation cannot pass with keyword-only wording.
- Tightened operational requirement coverage with an active execution-action check, so text that merely repeats terms such as protocol, record, evidence, or corrective action no longer passes unless it also says who performs/keeps/documents/monitors/applies the work; the diagnostic now flows through export readiness reports, targeted regeneration guidance, drafting repair prompts, and common-scenario regressions.
- Surfaced active execution-action diagnostics in the web UI, so DOCX export warnings and the Generations remediation panel show when a missing requirement needs concrete execution verbs in addition to operational evidence.
- Added script-level calibration regressions proving `needs execution action` reason counts are preserved through calibration manifests, Markdown summaries, and action execution reports.
- Added calibration-manifest comparison regression coverage for `needs execution action` before/after deltas, so remediation cycles can prove whether this specific blocker type decreases after regeneration.
- Added Bulgarian operational-coverage regression for active execution verbs such as assigning, executing, keeping records, and documenting corrective actions, so Bulgarian technical proposal text is not penalized by the stricter execution-action gate.
- Expanded the Bulgarian active-execution detector with common technical-proposal verbs such as performs, ensures, organizes, checks, controls, and prepares protocol documents, while keeping noun-only checklist wording from passing the execution-action gate.
- Added Bulgarian active-execution verb examples to export remediation guidance and drafting repair prompts, so regeneration instructions point the model toward natural Bulgarian operational phrasing instead of only English verbs.
- Localized missing-requirement reason labels in the DOCX export warning, so Bulgarian users see blocker causes such as operational evidence, execution action, coherent passage, and distinctive detail in Bulgarian.
- Localized the Generations panel missing-requirements remediation UI, including the coverage-regeneration action and per-requirement repair label, so export blocker resolution stays Bulgarian-first.
- Localized the remaining Generations panel remediation actions for stale selected sections and shallow/depth-blocked sections, keeping the export-blocker repair flow consistently Bulgarian-first.
- Fixed mojibake quality/depth issue labels in the Generations panel and added regression coverage for all exported depth-blocker reason labels, so remediation diagnostics remain readable in Bulgarian.
- Localized duplicate-selected remediation warnings, badges, and fallback errors in the Generations panel, so ambiguous selected variants are explained consistently in Bulgarian before DOCX export.
- Localized DOCX readiness Markdown diagnostics for missing-requirement reasons and quality/depth issue labels while preserving the original machine codes in backticks, making calibration reports readable for Bulgarian review without breaking automation.
- Localized calibration manifest remediation UI labels and Markdown action guidance for stale, missing-requirement, quality/depth, and outline-mapping actions while preserving stable action keys for automation.
- Preserved drafting blueprint overflow groups beyond the detailed group limit as compact additional groups, and made proposal-depth targets count those groups and requirement ids so complex tenders do not silently lose whole requirement categories.
- Preserved drafting blueprint metadata in saved generations even when future/custom blueprint limits produce compact additional groups without detailed groups, keeping calibration evidence traceable.
- Added export-readiness regression coverage proving compact additional blueprint groups are counted in DOCX pre-export depth diagnostics.
- Enriched calibration manifest quality/depth remediation labels with word targets, blueprint group/topic counts, checklist id counts, and suggested words per group/topic so reviewers can see structural depth pressure before running remediation.
- Preserved calibration remediation section labels in action execution JSON and Markdown reports, so dry-run and executed remediation evidence keeps the same structural depth diagnostics reviewers saw in the manifest.
- Preserved remediation section-label context in before/after calibration manifest target comparisons, making structural depth changes visible alongside action target deltas.
- Aggregated remediation section-label evidence back into calibration bundle manifests, so follow-up bundles show which structurally weak or depth-heavy sections were targeted by attached action reports.
- Added an end-to-end calibration regression proving action-execution section labels flow through the follow-up bundle manifest and into before/after comparison deltas.
- Added a universal weak-operational-detail depth gate, blocking long blueprint-aware sections that mention the right topics but lack concrete roles, controls, records, monitoring, acceptance evidence, sequence, or corrective actions, with backend report and web remediation labels.
- Fed weak-operational-detail diagnostics into drafting quality-repair prompts, including matched/required operational signal counts and concrete examples to add during regeneration.
- Passed quality/depth blocker diagnostics into targeted quality regeneration jobs, so reruns know the exact issue codes, word targets, missing blueprint topics, and weak-operational-detail examples before drafting starts.
- Added a common-scenario regression proving quality/depth remediation diagnostics flow from export readiness into targeted drafting guidance prompts, alongside the existing missing-requirement remediation scenario.
- Surfaced quality/depth issue codes such as `weak_operational_detail` inside calibration readiness action labels, so manifest shortlists and action reports show not only section depth numbers but also the blocker causes.
- Added operational-detail coverage diagnostics to proposal gap analysis, comparing reference and generated signals for roles, controls, records, monitoring, acceptance, sequence, escalation, and corrective actions.
- Propagated the operational-detail gap ratio/status into calibration manifest scorecards and before/after comparison deltas, so reruns can prove whether operational substance improved.
- Made before/after calibration recommendations treat weak or partial operational-detail coverage as a remaining quality blocker even when export readiness is clear and generated/reference volume improves.
- Preserved the exact missing operational-detail signals in calibration manifests and before/after comparison reports, so remediation can target concrete gaps such as records, monitoring, corrective actions, or responsible roles.
- Preserved missing operational-detail signals through calibration action execution reports and attached bundle summaries, so proof/dry-run evidence shows which concrete operational gaps a detailed regeneration action was meant to repair.
- Added before/after comparison deltas for operational-detail signals targeted by attached action execution evidence, so calibration reviews can see whether remediation focus shifted or cleared across reruns.
- Passed calibration gap reasons and missing operational-detail signals from gap-priority quality/depth actions into targeted drafting guidance, so reference-comparison findings become concrete regeneration instructions instead of report-only diagnostics.
- Surfaced calibration gap guidance in action execution JSON/Markdown reports, so dry-run and executed remediation evidence shows gap reasons plus reference/generated section context without requiring manual payload inspection.
- Structured calibration gap context now flows through targeted quality regeneration into the drafting prompt, including gap reasons, reference/generated section context, missing operational-detail signals, and expected regeneration outcomes for any calibrated project.
- Re-ran the Pernik calibration remediation cycle in non-mutating `--actions-only --all` dry-run mode against the stored manifest; it planned `resolve_duplicate_selected` and `regenerate_stale` for 14 sections each, produced planned-level action reports under `local_analysis/`, and correctly kept `ready_for_bundle=false` until real `--execute --wait` proof exists.
- Made calibration action execution reports self-contained by adding manifest path, project id, API base, execution mode, wait flag, and selected action keys to the JSON report and readable Markdown header.
- Added conservative legacy mojibake repair for human-facing calibration action report labels, so older manifests with mis-decoded Bulgarian section names remain reviewable without changing executable action payloads.
- Added ordered remediation execution-plan metadata to calibration action reports, making dry-run and proof reports show the exact action order, source, section counts, and target summaries before real execution.
- Corrected proposal-depth word counting to use the full Unicode Cyrillic range, with regression coverage for real Bulgarian text so quality gates do not undercount tender-specific Bulgarian narrative.
- Corrected requirement-coverage tokenization to use the full Unicode Cyrillic range, with regression coverage for Bulgarian checklist text so coverage diagnostics do not lose tender-specific Cyrillic terms.
- Corrected proposal gap analysis tokenization and heading heuristics to use the full Unicode Cyrillic range, so real Bulgarian reference/generated comparisons do not lose tender-specific terms or section cues.
- Reduced proposal gap analysis keyword noise by filtering generic Bulgarian procurement terms such as requirement, technical proposal, describe, participant, and execution, keeping calibration focus on substantive technical terms.
- Added common-scenario coverage across quality, risk, environment, safety, communication, and documentation requirements, proving keyword-only restatements stay blocked until the generated text includes active execution evidence.

## Active Goals

1. Turn the application into a reference-quality technical proposal generator that produces detailed, tender-specific Bulgarian proposals rather than short generic sections.
2. Use the winning Pernik technical proposal comparison as the first calibration baseline for outline granularity, grounding coverage, drafting depth, and export readiness.
3. Keep documentation as a reliable source of truth tied to the real repository state.
4. Add regression protection around generation quality so improvements do not silently regress.

## Next Recommended Steps

1. Use `scripts/run_calibration_remediation_cycle.py --execute --wait --require-action-ready` with explicit `--action-key resolve_duplicate_selected` or the Generations bulk duplicate resolver to clear Pernik's legacy duplicate selected generations; the latest dry-run already confirms the planned action path and target counts.
2. Use the calibration remediation cycle script with `--execute --wait --action-key regenerate_stale` or Generations panel bulk stale-regeneration action for Pernik after duplicate selections are resolved; then use the bulk missing-requirements and quality/depth regeneration actions for any remaining requirement-coverage or blueprint-aware shallow sections reported by export preflight or gap-priority diagnostics.
3. After resolving Pernik's duplicate selected variants and stale selected sections, regenerate affected sections so the section structure plan and iterative drafting quality-repair pass can improve subtopic coverage, checklist coverage, and depth before export readiness is checked again.
4. Re-run the Pernik calibration bundle after remediation with `--action-report` and compare the regenerated output against the winning proposal, focusing on the manifest word-volume scorecard, section-level drafting-depth diagnostics, executed remediation evidence, execution-status deltas, and action target deltas in the before/after calibration manifest comparison report.
5. Expand generated documentation with more precise backend endpoint and workflow coverage.
6. Continue broadening common tender regression coverage with more real-world noisy PDF extraction, DOCX readiness combinations, and operational-action coverage cases across quality, risk, environment, safety, communication, and documentation requirements.

## Notes

- `env.txt` is intentionally not tracked.
- This file is the shared working plan and should be updated as decisions and priorities change.
- Frontend stability is now a top priority because the UI has been breaking repeatedly.
- The goal is not only to fix current issues, but to create test coverage that gives confidence against regressions.
- Current stability baseline for the web app now includes lint, TypeScript, Vitest regression coverage, and Playwright smoke tests on the live local environment.
