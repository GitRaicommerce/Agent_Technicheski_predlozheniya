# TP AI — implementation plan led by GPT-6 Sol

Date: 2026-09-25. Status: **PLANNED — IMPLEMENTATION NOT STARTED**.

Source: [Bulgarian audit and accepted architecture, revision 2](REPOSITORY_ANALYSIS_2026-09-25_BG.md). Audited application baseline: `7652435cbe6afc87ecb136a8773be87e92ed1e84`. Planning PR: [#2](https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya/pull/2).

This document is a technical handoff. The current user request authorizes updating documentation and the planning PR. It does not start this implementation, any workers, a deployment, or paid application model calls. Product direction is accepted; implementation completion and production acceptance are not claimed.

## 1. Objective and accepted decisions

Deliver a workflow in which every applicable client requirement remains traceable from source documentation through the approved plan, generation inputs, selected text, verification, and exported DOCX.

Priority order: **scope completeness → correct interpretation → traceability → text quality → time and cost**. Additional code, a dedicated auditor, and stronger models are justified when they close a demonstrated scope gap. Simplicity is a secondary implementation preference, never a reason to omit a required check.

Accepted design:

1. Strong models perform understanding, semantic planning, independent plan review, and final verification.
2. A separately instructed plan auditor makes its own source-based requirement inventory before comparing it with the author's plan. It must not depend only on the author's extracted registry.
3. Bulk drafting requires an accepted audit for the exact plan and input set. A missing, partial, failed, or stale audit is not acceptance.
4. Routine subpoints may use a lighter model when the task, evidence and criteria are explicit; complex technical methodologies use the stronger profile.
5. A job uses an immutable input set. Changes produce a new version or an explicit stale condition, not silent context replacement.
6. Human corrections and review decisions survive reanalysis when their underlying meaning is unchanged.
7. Verification evaluates the actual final content, including tables and assembled sections. Draft export remains available under existing restrictions; forbidden calendar dates remain a hard export block.
8. GPT-6 Sol leads the **development work**. This does not select Sol for every **runtime application agent**.

Scope includes all report cards К-01 through К-27. К-20 is conditional on shared/public deployment. Completing the broader historical Phase 6 illustration/table feature set, changing procurement policy, moving hosting, or introducing new commercial product features is outside this program.

## 2. Development orchestration and authority

### 2.1 Lead and helpers

- **Lead:** `gpt-6-sol`, reasoning `high` as the initial development setting. The user chose the model; the reasoning setting is this plan's starting recommendation. Use a higher supported setting only for a demonstrated difficult design/integration step. Do not silently replace the lead with Astra.
- **Lead responsibility:** inspect current ownership and code; sequence work; maintain contracts; perform or delegate bounded edits; review exact changes; integrate; run acceptance; update the user in Bulgarian and technical handoffs in English.
- **Optional helpers after implementation is separately started:** at most two simultaneously, each with a bounded file set and deliverable. Use Sol for code changes; a helper's presence does not make its report independent verification of unrun tests.
- **Core owner:** one executor at a time owns `core/models.py`, migrations, `content_plan.py`, `generation_jobs.py`, shared API contracts and final integration. The lead may own these directly.
- **Disjoint ownership:** parser/worker or export fixes may run alongside a core task only when files and contracts do not overlap. UI work begins against a published response contract.
- **Independent runtime auditor:** a product component implemented by WP-05. It is distinct from the development helpers; do not confuse a coding review with an audit of a tender plan.

No worker creates its own team. No shared file has two active writers. If a new finding requires another subsystem or changes an accepted business rule, the lead describes the concrete dependency before broadening the assignment.

### 2.2 Working state across long sessions

Use the existing `PLAN.md` implementation-status table as the single current ledger. Before each handoff or context restart, record:

- current work package, owner, branch/worktree and exact commit;
- completed acceptance cases and their evidence;
- unresolved cases and the exact next action;
- approved model policy and relevant schema/response contracts;
- execution authority: code/PR, merge, deployment and paid runs separately;
- approved paid cap and consumed amount, when applicable; otherwise `NOT APPROVED`.

Restart from this state and the current files, not from a reconstructed conversation. This document holds the intended sequence; the audit holds evidence; neither duplicates the live status ledger.

Implementation should start from freshly fetched `origin/main` in an isolated `codex/` branch after confirming ownership. If the planning PR is not yet merged, read these documents from its branch without treating that as authority to merge it. Dependent code packages may share an integration branch or explicitly based PRs; do not dispatch a package against main that lacks its prerequisites. Merge only with the authorization applicable at execution time.

## 3. Runtime model policy

### 3.1 Initial profiles

These are implementation targets for evaluation, not measured proof that a given model is sufficient for Bulgarian procurement work.

| Runtime role | Initial model | Effort | Existing/new call labels |
|---|---|---|---|
| Understand documentation and audit extracted requirements | `gpt-6-astra` | `xhigh` | `understanding_map`, `understanding_proposal_audit` |
| Semantic plan author | `gpt-6-astra` | `xhigh` | new `content_plan_author` |
| Independent source inventory and plan comparison | `gpt-6-astra` | `xhigh` | new `plan_audit_extract`, `plan_audit_compare` |
| Draft an explicit, routine subpoint | `gpt-6-sol` | `high` | `drafting`, with a recorded routine profile |
| Draft a complex methodology | `gpt-6-astra` | `xhigh` | `drafting`, with a recorded complex profile |
| Criterion verification and final consistency | `gpt-6-astra` | `xhigh` | `criteria_verifier`, `consistency_claims`, `consistency_conflicts`, applicable `verifier` path |
| Read potentially binding schedule/legislation statements | `gpt-6-astra` | `high` | `schedule`, `legislation` |
| Conversation routing and example selection | `gpt-6-sol` | `medium` | `orchestrator`, `examples` |
| Legacy plan generation, if still callable | `gpt-6-astra` | `xhigh` | `tender_struct`; preserve its supported mode boundaries |
| Calendar repair or another text repair | Inherit the writer's approved model class | Inherit or explicitly defined equivalent | `drafting_calendar_guard`, JSON/quality repair |
| Assembly | Existing deterministic code | N/A | normal `drafting_v2_assembly` model call removed from the standard finalization path |

If optional editorial assembly remains available, it uses an explicit author profile and produces unverified new text. It cannot inherit the previous text's accepted verdicts.

For genuinely difficult cases, `max` is an allowed escalation within the approved run budget. Do not apply it to every chunk automatically. Luna is not required for the first delivery; consider it later only for measured low-risk operations. Profile selection must be visible and persisted, not an accidental consequence of model naming.

### 3.2 Compatibility and fallbacks

Verified official sources: [Sol API](https://developers.openai.com/api/docs/models/gpt-6-sol), [Astra API](https://developers.openai.com/api/docs/models/gpt-6-astra), [GPT-6 migration](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#migration-quickstart), [Codex Ultra](https://learn.chatgpt.com/docs/models#know-when-to-use-max-or-ultra).

Astra API supports `low`, `medium`, `high`, `xhigh`, `max`; Sol additionally supports `none`. Ultra is a Codex multi-agent mode, not a runtime API effort string. API account access remains unverified.

The current app uses Chat Completions for JSON responses, not native model tool calls. Keep that transport if the required behavior is supported, adapting `reasoning_effort`, completion-token parameters and output parsing correctly. Do not send incompatible temperature/sampling parameters. The current `_uses_completion_token_limit` recognizes GPT-5 prefixes and must not misclassify GPT-6. If actual reasoning with native tools is introduced, use Responses and validate the boundary explicitly; do not rewrite the whole gateway merely for the model name change.

Record requested and actual provider/model/effort, role, prompt version, trace/job IDs, latency, and returned token usage. Unknown usage remains unknown; never invent zero cost. Check SDK compatibility before choosing a version update. Preserve existing JSON result fields consumed by agents.

Critical roles must not silently fall back to a weaker model. Persist an actionable failure if their configured model is unavailable. An explicitly configured quality-equivalent fallback is allowed only with recorded actual policy and authorized cost. JSON repair uses the provider that returned the malformed response, addressing К-22. Role changes must not trigger automatic paid regeneration of existing projects.

## 4. Contracts that must survive every stage

Agree and test these shapes before parallel UI/backend work. They are proposed implementation contracts, not fields already present. Reuse current models/JSON where they provide the required integrity; add Alembic migrations for actual schema changes.

### 4.1 Source manifest and requirement coverage

The source manifest identifies every included file/revision/hash, document role, source locations and extraction coverage. Appendices and clarification documents are part of the manifest. Uploaded example proposals may supply wording but never define new tender obligations.

Every applicable requirement has a stable ID, source quotation/location, category, human-review state and at least one explicit disposition: drafting target, global control, human-justified exclusion, or unresolved. Counts are derived from these records. A missing item cannot vanish from the denominator. Ambiguous applicability is not silently guessed.

### 4.2 Plan and immutable job inputs

The plan preserves mandatory headings and numbering. Added subpoints carry linked requirements, acceptance criteria, source quotations, content kind and sufficient drafting instructions. Parent requirements have explicit receivers. Global prohibitions remain rules, not decorative chapters.

A job fixes plan identity/content hash, source manifest, requirement/criterion IDs, project-brief version/content, facts and schedule versions/content, selected model-policy version, and accepted audit ID. An identifier alone is insufficient if its referenced JSON can be mutated in place. Store immutable revisions or the required content snapshot. Do not copy every document into every job if a stable immutable reference already suffices.

Resume uses the same input set and completed outputs. New inputs produce a new task version or explicit stale/error state. Reanalysis preserves unchanged human decisions, while changed meaning requires review. Old accepted outputs remain readable. Existing pre-audit jobs are labeled legacy/unverified and may not begin new paid drafting through an unexamined legacy shortcut.

### 4.3 Independent plan audit

Use a separate role and fresh context. The author and auditor may use the same model family, but never the same evolving author conversation as the auditor's sole evidence.

**Stage A — independent inventory:** read the full source manifest and extraction coverage, without the author's plan or justification. Persist source-derived obligations, prohibitions, evaluation rules and uncertainties with exact quotations. Source omissions or unreadable pages produce `PARTIAL`/unresolved coverage. The source inventory may be reused for the exact unchanged sources; it cannot be reused after a changed file/brief without validation.

**Stage B — bidirectional comparison:** compare that inventory with the plan. For each obligation, identify concrete plan targets or global controls and judge adequacy of intended detail. For each proposed plan obligation, identify its source or explicit user-approved rationale. Distinguish a contractor's justified method proposal from a claim that the client mandated it.

Suggested audit payload:

```text
input_fingerprint:
  source_manifest_hash, plan_id, plan_version, plan_content_hash,
  project_brief_version, relevant_fact_and_schedule_fingerprints
identity:
  audit_id, role, prompt_version, actual_model_profile
coverage:
  expected_sources, inspected_sources, missing_or_partial_locations
findings[]:
  source_requirement_id, quote, source_location, plan_item_ids,
  verdict, rationale, required_correction, resolution_reference
verdicts:
  covered | partial | missing | contradiction | unsupported_addition | ambiguous
overall:
  passed | changes_required | partial | error | stale
```

Exact enum names may be adapted once to current conventions; their meaning must remain distinct. An author correction creates another plan version and invalidates the old comparison. The auditor does not rewrite and approve its own repair. Human resolution records the interpretation and supporting reason; there is no generic green override for an unread source or a technical failure.

A shared server-side eligibility function applies to all new drafting entry points: chat, bulk API, per-section regeneration where new text is produced, retry/resume and internal job dispatch. It requires the same accepted input set, not merely the latest successful audit for the project. A job rechecks this immediately before paid dispatch. Reading history and permitted draft export remain available.

If a change to the current project sources/brief invalidates an active plan's acceptance, preserve completed units and stop new paid units at the next safe boundary. The fixed old snapshot remains available as evidence; the job must not switch to new inputs or treat old acceptance as a check of the changed assignment. Continuing an intentionally retained old scope requires an explicit scope decision.

Initial correction policy: at most two automated author-correction cycles after the first failed audit, within the approved run budget. Then retain the findings and ask for a specific human interpretation. This is an initial limit to validate, not a reason to label unresolved work complete. Missing/partial source coverage stops before another whole-plan paid retry.

### 4.4 Drafting and final verification

Each writer receives the exact approved criterion text/IDs, source quotations, applicable parent/global controls and fixed brief/facts. Criteria edited by the user must not be replaced with older `requirement_text`. Model assignment and the reason for a complex profile are stored with the generation.

Default assembly preserves full selected subpoint bodies and source-generation IDs without editorial rewriting. Final verification targets the exported text set and generated tables. Expected-versus-checked criteria and complete character/task coverage are explicit; unchecked/partial/stale are not verified. Contradiction results bind to the exact generation, schedule and fact inputs. A supported working draft may still be downloaded with its actual status and the existing hard restrictions.

## 5. Work packages, dependencies and acceptance

Keep each PR bounded. If a package is too large for one review, split its named substeps while retaining the same contract and acceptance cases. Do not mechanically assign one worker the entire package list.

### WP-00 — Current baseline and executable test foundation

**Cards:** К-01; the fast-CI part of К-18. **Owner:** Sol lead. **Dependencies:** none.

1. Fetch main, inspect open PRs/worktrees and identify current task owners. Confirm which audit findings still apply; do not redo the full audit if the relevant code is unchanged.
2. Establish an isolated supported Docker test stack and a non-production database. This planning host did not have Docker available; do not assume it has since appeared or install/change unrelated host services silently.
3. Fix the three content-plan test fixtures to select v2 explicitly; preserve a separate v1-disabled-feature test. Make UI handling preserve valid legacy generations when a v2-only feature is unavailable.
4. Add existing frontend unit and script tests to CI. Define the small deterministic source fixture used later, including parent/child obligations, a prohibition, evaluation rule, short line, last-page requirement, late-text violation and an unsupported proposed commitment.

**Files:** config/capability response only as needed; `tests/test_content_plan.py`; frontend API and affected panels/tests; `.github/workflows/ci.yml`; bounded fixtures.

**Acceptance:** report Т-01; backend tests exercise their intended behavior rather than fail at the mode check; a deliberate frontend/script regression fails CI; environment limitations remain explicitly recorded. **Stop:** do not switch all user projects to v2 or erase existing data. **Estimate:** 4–6 active hours.

### WP-01 — Apply the runtime role policy safely

**Cards:** К-24, К-22. **Owner:** one gateway/config owner. **Dependencies:** WP-00.

1. Inventory every actual `agent` call label; map it to the role table, including repairs, legacy `tender_struct`, schedule and legislation. Make unknown critical roles explicit errors.
2. Add validated model/effort/output settings; remove unsupported request arguments; adapt the GPT-6 completion limit path. Upgrade only the SDK surface shown to be incompatible.
3. Preserve JSON contracts and implement actual-provider repair. Persist policy and usage evidence. Define quality-equivalent fallback rules; never silently downgrade critical roles.
4. Add mocked request assertions for every profile and error/fallback combination. Do not make live calls merely to turn unit tests green.

**Files:** `core/config.py`, `core/llm_gateway.py`, `.env.example`, agent callers, gateway/config tests; one small policy module if useful.

**Acceptance:** Т-21, Т-23; correct model and effort for each role; no `ultra` API string; recorded actual profile; incompatible parameters absent; unchanged successful result shape. **Stop:** account-model access is an external preflight for a separately approved live run. **Estimate:** 6–10 active hours.

### WP-02 — Preserve source and schedule inputs

**Cards:** К-06, К-17, К-21. **Owner:** ingestion worker. **Dependencies:** WP-00; can run independently of WP-01 on disjoint files.

1. Preserve meaningful short paragraphs. Detect/recover or clearly mark page-level extraction gaps without replacing deterministic ingestion with a free-form model.
2. Commit file and related state before enqueue; record enqueue failure. Verify visibility using separate database sessions, not only an AsyncMock.
3. Keep the prior usable schedule active after fatal parsing failure. Parse supported duration units, dependencies and resource columns explicitly; mark unknown/missing fields accurately.
4. Add small real PDF/XLSX fixtures with no confidential production data. A real MPP fixture is required before claiming MPP support verified; otherwise record that acceptance case as blocked.

**Files:** ingestion parsers/worker, file routes, their tests/fixtures. **Acceptance:** Т-02, Т-19, Т-20; source manifest exposes incomplete coverage. **Stop:** do not rewrite the scheduling engine or invent units. **Estimate:** 8–12 active hours.

### WP-03 — Conserve requirements and build a model-assisted plan

**Cards:** К-02, К-03, К-26. **Owner:** core owner. **Dependencies:** WP-01 and WP-02's source contract.

1. Correct scope classification while preserving legitimate administrative exclusions. Add the certificate-in-proposal regression.
2. Account for all confirmed applicable requirements through mapping, global controls, explicit exclusions or unresolved findings. Define parent-to-child receiver semantics and stable criterion identities.
3. Build immutable mandatory heading/numbering constraints from the sources. Add the Astra planning step for justified subpoints, depth, criteria and mapping, using the existing plan model.
4. Validate the output before saving a new draft; reject missing/altered mandatory headings, foreign source IDs and silent missing criteria. Record suggested methodologies separately from sourced requirements. Do not autoapprove the model's plan.

**Files:** understanding/content-plan/generation-structure code, plan API, target tests; proposed author module if appropriate.

**Acceptance:** Т-03, Т-04, Т-24; retain original headings and every applicable requirement disposition. **Stop:** unresolved meaning remains visible; an invalid draft does not replace the last accepted plan. **Estimate:** 10–16 active hours.

### WP-04 — Freeze execution inputs and preserve human decisions

**Cards:** К-05, К-07, К-11. **Owner:** core owner. **Dependencies:** WP-03's identity and plan contract.

1. Load the plan recorded by the job, not the latest approved plan. Validate all requested unit IDs before dispatch.
2. Implement the immutable input contract for plan, brief, criteria, facts, schedule and source references. Version mutable facts/brief rather than relabeling changed content as the same version.
3. Preserve human review decisions on unchanged requirements during reanalysis. Changed or ambiguous matches are reviewed; old approved plan references remain resolvable.
4. Add the durable visible project brief and pass it to routing and writing. Do not automatically promote casual chat into an approved instruction.
5. Resume against the same inputs, preserve completed text, and expose stale downstream results after an upstream change. Inspect existing data shapes and design migrations against a copy before any production migration.

**Files:** models/migrations if needed, understanding routes/agent, context, generation jobs, project API/UI brief surface, target tests.

**Acceptance:** Т-06–Т-08, Т-13; a recorded version means immutable contents; restarting the coding agent also resumes from the PLAN ledger. **Stop:** no automatic paid restart or destructive reanalysis migration. **Estimate:** 12–18 active hours.

### WP-05 — Independent plan audit and enforced drafting eligibility

**Cards:** К-25. **Owner:** core owner plus a disjoint UI worker after the response contract is fixed. **Dependencies:** WP-01–WP-04.

1. Implement the two-stage auditor contract: independent source inventory, then plan comparison. Preserve source/page coverage and independent prompt identity.
2. Persist a dedicated audit result, preferably as a supported new job type using current job infrastructure. Add explicit dispatch; do not send every new job type through the drafting worker by accident.
3. Validate findings, source anchors and expected inventory. Bind audit to the immutable inputs. Handle missing sources, truncated batches, provider error and stale inputs as non-passing states.
4. Add correction and re-audit flow with bounded cycles. The writer cannot mutate the auditor's verdict. Preserve unresolved findings for a human decision.
5. Enforce shared eligibility in every server-side drafting entry point and before dispatch. Keep existing outputs accessible. UI shows precise missing coverage and links to affected plan points/sources, not just a green badge.

**Files:** proposed `agents/plan_audit.py`, corresponding route/job dispatcher, plan/generation routes, orchestration dispatch, shared models only as needed, API/UI and tests. Names are proposed, not pre-existing paths.

**Acceptance:** Т-25–Т-27; adversarial fixtures include a missing original-registry requirement, attractive heading with insufficient detail, invented obligation and unread final page. Direct API calls cannot bypass the gate. **Stop:** no passing result on missing evidence or unlimited author/auditor loop. **Estimate:** 12–18 active hours.

### WP-06 — Give the selected writer the exact accepted task

**Cards:** К-04, К-16; drafting profile integration from К-24. **Owner:** core/context owner. **Dependencies:** WP-03–WP-05.

1. Pass approved criteria IDs/text/kinds/quotes, global controls and durable brief to both bulk and single-section writing paths. Persist what the writer received.
2. Preserve direct evidence and allow keyword evidence to survive a full semantic result list. Choose bounded excerpts around the relevant content, not always the first characters.
3. Select routine Sol or complex Astra profile before dispatch. Record the reason. Do not route to a cheaper writer solely because the document is now in a later phase.

**Files:** context, drafting, generation jobs, orchestrator, tests. **Acceptance:** Т-05, Т-18, writer portions of Т-23; captured prompts match the accepted plan and model policy. **Stop:** no paid regeneration of historic text by migration. **Estimate:** 4–6 active hours.

### WP-07 — Preserve user edits and expose authoritative state

**Cards:** К-12, К-13, К-15. **Owner:** UI worker, with API changes serialized through core owner. **Dependencies:** WP-04/05 response contracts; verification display integration completes after WP-08.

1. Preserve dirty requirement/WBS/fact drafts across saving another item and background refresh. Save-and-confirm must confirm the actual displayed saved value.
2. Edit criteria as records with stable identity, not multiline strings rebuilt by position. Validate IDs and preserve source metadata.
3. Use authoritative selected-generation state in chat; refresh dependent checks after selection. Show only current results as current, with section and revision identity.
4. Expose regeneration, polling and selection failures without deleting visible content or automatically restarting paid work. Display calendar-only and combined blockers with affected sections.

**Files:** named report panels, `api.ts`, project page and component tests; small API contract adjustments only where specified.

**Acceptance:** Т-14, Т-15, Т-17 and calendar-blocker UI cases. A failed save preserves the edit and does not approve the old value. **Stop:** avoid unrelated UI redesign. **Estimate:** 8–12 active hours.

### WP-08 — Verify and export the exact final content

**Cards:** К-08, К-09, К-10, К-14, К-23. **Owner:** verification/export owner; serialize changes touching generation jobs. **Dependencies:** WP-04, WP-06; standalone deterministic assembly/date fixes may land earlier.

1. Use lossless deterministic assembly by default. Preserve revision/child links and invalidate assembly when a child changes.
2. Compare expected criteria with actual current-generation checks. Require valid text evidence for covered verdicts. Missing, partial and stale coverage are distinct from success; reconcile legacy verifier status explicitly.
3. Bind consistency to the exact exportable generation set and schedule/fact fingerprints. Avoid the subset-freshness bug without confusing child and assembled selections.
4. Make all verification limits visible first, then cover oversized text/tasks through bounded batches. No fully verified result when any required coverage is omitted.
5. Make final DOCX paragraphs and tables obey the calendar-date policy. Preserve usable durations/dependencies; clarify cover-date metadata separately without postponing the demonstrated schedule fix.
6. Run the final strong-model role against the actual final content and source-grounded criteria. It must also flag unsupported commitments; deterministic structural checks remain alongside semantic review.

**Files:** drafting_v2, criteria/consistency agents, export/readiness modules/routes, related API/UI types and tests.

**Acceptance:** Т-09–Т-12, Т-16; no child obligation lost at assembly; a report for g1 alone does not verify g1+g2; a late violation is inspected or marked incomplete; DOCX is reopened and checked. **Stop:** draft access does not become a way around hard calendar blockers or a claim of final readiness. **Estimate:** 10–16 active hours.

### WP-09 — Integration, migrations and truthful startup

**Cards:** remaining К-18, К-19. **Owner:** Sol lead. **Dependencies:** WP-00–WP-08 for final acceptance; individual script fixes may be prepared earlier.

1. Fail correctly on native command errors; apply migrations before announcing readiness; validate health dependencies rather than HTTP reachability alone.
2. Test an empty database and an upgrade from the old schema/data copy. Confirm old projects/text remain readable and new eligibility is explicit.
3. Add one deterministic full v2 browser/API journey using supported disposable services and a CI-available browser. Include the new independent audit, durable inputs, edit correction, drafting, final verification and DOCX.
4. Include frontend tests, script tests and targeted transaction/migration checks in CI. Document exactly which checks are live versus mocked.

**Files:** CI, existing startup scripts, health/Compose definitions, migrations and integration/browser tests.

**Acceptance:** Т-22 and the complete technical matrix Т-01–Т-27 on the integrated head. Deliberately remove a required item and confirm that the journey fails for that reason. **Stop:** do not run the historical destructive deployment commands or production migrations as part of testing. **Estimate:** 6–10 active hours.

### WP-10 — Measured comparison and human acceptance

**Cards:** К-27. **Owner:** Sol lead with the user's procurement expert. **Dependencies:** WP-09 and separately approved live-run inputs/access/budget.

1. Confirm a human-reviewed requirement set and frozen source/project snapshot. Use a representative real tender and small synthetic adversarial cases; do not present one tender as universal proof.
2. First validate the evaluation machinery with recorded/mock outputs. Then estimate the cost of the bounded real comparison, distinguish expected spend from the hard cap, and obtain the required spend authorization.
3. Compare the four model-policy/auditor combinations on the same corrected code, planning algorithm and inputs. Old-model availability is a preflight; unavailable cells remain unmeasured. An audit-disabled evaluation is isolated and cannot publish a production-ready artifact.
4. Record omissions, wrong interpretations, unsupported additions, unresolved cases, corrections required, elapsed time and actual usage/cost where known. Keep generated texts and evidence sufficient to review claims.
5. Have the expert inspect the actual final DOCX. Fix only demonstrated remaining defects through their owning package; a new requirement triggers an explicit scope decision.

**Files:** existing calibration tooling/tests, controlled fixtures and private run artifacts; no confidential tender artifacts committed to this public repository.

**Acceptance:** Т-28; zero unresolved known critical mandatory omissions/contradictions in the acceptance fixture, no misleading verified state, and explicit human acceptance. This is a release criterion for the tested example, not a statistical guarantee of zero future errors. **Stop:** a cap/credit failure preserves artifacts and reports partial completion; no automatic spend extension. **Estimate:** 8–12 active hours after prerequisites, excluding waiting for input or approval.

### WP-11 — Access boundary before shared/public deployment

**Cards:** К-20. **Owner:** Sol lead/assigned operator. **Dependencies:** actual deployment topology supplied; execute only if that deployment is requested.

Check the real network/authentication boundary and select the minimum sufficient protection for the intended users. Verify unauthorized clients cannot read/delete projects or trigger paid jobs. Do not infer exposure from Compose alone, or protection from CORS/APP_SECRET_KEY alone. No penetration testing of unrelated systems.

**Acceptance:** the report's К-20 cases, with current deployment evidence. **Estimate:** excluded from the core range until topology and requirements are known. A multi-user permissions product is not silently included.

## 6. Coverage, sequencing and stop conditions

### 6.1 Card-to-package mapping

| Report cards | Owning package |
|---|---|
| К-01 | WP-00 |
| К-02, К-03, К-26 | WP-03 |
| К-04, К-16 | WP-06 |
| К-05, К-07, К-11 | WP-04 |
| К-06, К-17, К-21 | WP-02 |
| К-08, К-09, К-10, К-14, К-23 | WP-08 |
| К-12, К-13, К-15 | WP-07 |
| К-18 | WP-00 fast tests; WP-09 integration, one shared owner |
| К-19 | WP-09 |
| К-20 | WP-11, conditional |
| К-22, К-24 | WP-01 |
| К-25 | WP-05 |
| К-27 | WP-10 |

Primary dependency chain: WP-00 → WP-01/WP-02 → WP-03 → WP-04 → WP-05 → WP-06 → WP-08 → WP-09 → WP-10. WP-07 can proceed against frozen contracts and joins final integration. WP-01 and WP-02 are candidates for useful parallel work. Do not multiply workers on the shared core files.

Milestones:

- **M1, independently checked plan:** WP-00–WP-05 accepted on controlled inputs. This is a plan-quality milestone, not a completed proposal.
- **M2, technically complete workflow:** WP-00–WP-09 accepted with deterministic model substitutes and the actual export artifact.
- **M3, measured real acceptance:** WP-10 accepted, within the approved budget. Production exposure still depends on applicable WP-11 and deployment authorization.

### 6.2 Acceptance and preserved behavior

Use all Т-01–Т-28 from the audit. Each package adds a regression for its known failure and runs the narrow relevant existing suite; run the integrated relevant suites at M2. Do not repeat broad tests without a change or unresolved failure that justifies them.

Do not restore obsolete historical rules by accident: WBS/fact review remains informative where currently intended, unless a specific required fact is necessary to resolve an actual tender obligation. Do not turn examples into requirements. Preserve the no-calendar-date policy, mandatory headings, human review, existing outputs and allowed draft export.

Known audit evidence, not new execution claims: local frontend 74/74 and script 95/95; baseline backend CI 311 passed/3 failed; migration chain structurally connected; no real full-stack acceptance. WP-00 must refresh results for its actual code head. Passing isolated tests does not replace M2/M3.

### 6.3 Stop conditions

- **Scope conflict:** two source obligations genuinely conflict or applicability changes a bidder commitment. Preserve evidence and request the specific interpretation; do not invent a resolution.
- **Incomplete inputs:** missing source pages, fixture, model access or required runtime dependency. Mark the affected acceptance `BLOCKED`/`NOT VERIFIED`; continue only independent authorized work.
- **Unowned concurrent change:** do not overwrite another executor's edits. Re-establish file ownership before integration.
- **Model/budget failure:** no silent downgrade, repeated paid replay or cap increase. Preserve completed artifacts.
- **Gate regression:** direct API, resume or single-section path bypasses accepted inputs/audit. Do not declare the package complete.
- **New deployment/data authority:** code and planning authorization do not imply production migration, merge or paid-run authorization.

## 7. Handoff prompt for the lead

Activate this prompt only when the user starts implementation. The planning task itself does not run it.

```text
You are the lead implementation orchestrator for TP AI. Use gpt-6-sol.
Start with high reasoning effort. Preserve Sol as the lead model.

Read AGENTS.md, Agent.md, PLAN.md, and:
- docs/REPOSITORY_ANALYSIS_2026-09-25_BG.md (revision 2)
- docs/IMPLEMENTATION_PLAN_GPT6_SOL.md

The user accepted coverage-first architecture, runtime model selection by role,
Astra-assisted planning, and an independent source-to-plan auditor.
Your development role is separate from the models called by the application.
Implement the authorized program through its work packages; do not treat this
document alone as authorization for paid calls, production deployment or merge.

First fetch current main, inspect worktree/PR ownership, compare relevant code
with the audit baseline 7652435cbe6afc87ecb136a8773be87e92ed1e84, and record the
current exact head and first package in PLAN.md. Read the planning PR branch
if these documents have not yet been merged. Do not merge it by assumption.

Use one owner for core contracts, models/migrations, content_plan.py and
generation_jobs.py. Use at most two helpers for truly disjoint bounded work
when the implementation assignment permits delegation. Give each helper one
package/substep, exact files, exclusions, prerequisites, acceptance and stop
conditions. Do not let helpers create further teams.

Work autonomously through authorized technical work. Reproduce each reported
defect, make the focused complete change and verify its acceptance. Completeness
has priority over minimizing code. Do not remove tests or weaken a gate to
obtain a passing status. Keep Bulgarian product labels and user updates;
use English for code, technical handoffs, commits and PR descriptions.

Never drop approved requirements, invent tender commitments, silently replace
job inputs with newer versions, or treat absent verification as success.
The plan auditor must form its own source-based inventory before comparing
the author's plan. Its passing result must bind to exactly the inputs used
for drafting. Preserve legacy text/history and allowed draft export.

After every package, update only the existing execution ledger with owner,
branch/head, acceptance evidence, gaps and exact next step. On context restart,
resume from that ledger. Create focused PRs under the execution assignment;
keep dependent changes on an explicit integration base until merge is allowed.

Before any real model run, confirm access, frozen input, expected spend and the
hard user-approved cap. Use model substitutes for technical tests. At a genuine
blocker, report the missing decision/evidence and retain completed work. Finish
by separating technical readiness, measured real-project acceptance, and actual
deployment status. Never label unfinished or unmeasured work complete.
```

## 8. Time estimate and assumptions

This is a planning estimate derived from the identified changes, shared-file dependencies and validation work. It is not a measured throughput benchmark for GPT-6 Sol, a guarantee, or a token/cost quotation.

| Package | Active implementation/integration/checking hours |
|---|---:|
| WP-00 | 4–6 |
| WP-01 | 6–10 |
| WP-02 | 8–12 |
| WP-03 | 10–16 |
| WP-04 | 12–18 |
| WP-05 | 12–18 |
| WP-06 | 4–6 |
| WP-07 | 8–12 |
| WP-08 | 10–16 |
| WP-09 | 6–10 |
| WP-10 | 8–12 |
| **Total WP-00–WP-10** | **88–136** |
| WP-11 | Estimate after deployment scope is known; excluded above |

At eight active hours per working day, the total is approximately **11–17 working days**, roughly **2–3.5 working weeks**. M1 accounts for about **52–80 active hours**, or **7–10 working days** before potential overlap. This is a conservative sequence estimate; useful parallelism may shorten elapsed time, but the plan does not subtract idealized speedups from every package.

Assumptions:

- a supported Docker-capable execution environment and test credentials/data become available at the beginning;
- the code is close to the audited baseline, with no concurrent large rewrite;
- one lead owns integration, with at most two disjoint helpers; context is maintained in the ledger;
- the user supplies one representative source package and access to a procurement expert for disputed requirements/final review;
- API access and a bounded budget are available before WP-10;
- existing data can be tested through a representative non-production copy;
- no hosting migration, new multi-user product, major document-layout redesign or unrelated feature work is added.

Expert review effort is not interchangeable with model execution time. Reserve approximately **6–10 hours of focused human review** across the requirement reference, disputed interpretations and final document; revise this for the actual tender size. Waiting for access, documents, approvals or expert availability is excluded from the active-time range and may lengthen the calendar schedule.

Re-estimate after WP-00 and the first model-policy/source package using observed implementation and test times. If major schema/data conflicts, unusable scans or materially changed main are found, report a revised range before widening work. Do not hide them inside unbounded retries. Paid token spending is separate from this time estimate; no monetary cap is set by this document.
