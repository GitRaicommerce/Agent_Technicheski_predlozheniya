# Agent Operating Guide

This file is the shared operating contract for every code executor working in this repository: Codex, Claude Code, GitHub Codespaces agents, local IDE assistants, or human maintainers.

The goal is simple: the same commands, the same safety rules, and the same code style should apply no matter who or what is editing the project.

## Project Purpose

TP AI is a monorepo for preparing Bulgarian technical proposals for public procurement. The app ingests tender documentation, example technical proposals, schedules, and legislation, then helps produce a structured technical proposal with traceable evidence.

Quality matters more than superficial output. Generated content must be grounded in the uploaded documentation and must preserve context from the original files.

## Repository Map

- `apps/web`: Next.js frontend.
- `services/api`: FastAPI backend, ingestion workers, agents, export logic, Alembic migrations.
- `docs`: generated and supporting engineering documentation.
- `scripts`: local automation scripts.
- `.githooks`: versioned Git hooks.
- `docker-compose.dev.yml`: local development stack.
- `PLAN.md`: shared work plan and current priorities.

`docs/ENGINEERING_OVERVIEW.md` is generated. Do not edit it manually.

## Required Startup Path

Use Docker for normal development. It is the only supported way to keep Postgres, Redis, MinIO, API, worker, and web aligned.

On Windows, prefer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

Manual startup:

```powershell
docker compose -f docker-compose.dev.yml up -d --wait
docker compose -f docker-compose.dev.yml exec -T api alembic upgrade head
```

Local URLs:

- Web: `http://localhost:3000`
- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

If Docker is running but commands fail with permission errors on Windows, rerun Docker commands with elevated permissions rather than changing project files.

## Required Checks

Run the narrowest useful checks while developing, then run the full relevant set before declaring work stable.

Backend targeted checks:

```powershell
docker compose -f docker-compose.dev.yml exec -T api pytest tests/test_parsers.py tests/test_worker.py -q
docker compose -f docker-compose.dev.yml exec -T api pytest tests/test_tender_struct.py tests/test_agents.py -q
```

Backend broader check:

```powershell
docker compose -f docker-compose.dev.yml exec -T api pytest tests/ -q
```

Frontend checks:

```powershell
cd apps/web
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run test:run
npm.cmd run test:e2e
```

On Windows PowerShell, prefer `npm.cmd` and `npx.cmd`.

If Playwright fails with `spawn EPERM`, rerun the same command with elevated permissions before treating it as an application failure.

## Database And Migrations

Schema changes must include an Alembic migration under `services/api/alembic/versions`.

After pulling or adding migrations, run:

```powershell
docker compose -f docker-compose.dev.yml exec -T api alembic upgrade head
```

Do not work around missing columns by changing application code. Apply the migration.

## PDF Ingestion Rules

PDF ingestion is critical for proposal quality.

Current preferred PDF path:

1. `opendataloader-pdf`
2. `markitdown`
3. page text audit through `pypdf`
4. OCR fallback through Poppler/Tesseract where needed

The container must provide Java 11 or newer. The Dockerfile currently uses `openjdk-21-jre-headless`.

Do not remove audit reporting from ingestion. `ProjectFile.ingest_report_json` and chunk `meta_json.parser_method` are required for debugging extraction quality.

When changing PDF parsing, verify with a real tender PDF when available. A good smoke result should include:

- `ingest_status=done`
- `ingest_quality_status=ok` or a clear warning
- `primary_method=opendataloader_pdf` for supported PDFs
- nonzero `page_count`, `chunk_count`, and `extracted_chars`
- no silent empty extraction

## Coding Style

Follow the existing style of the file being edited. Keep changes focused and avoid broad refactors during feature or bug-fix work.

Backend:

- Use FastAPI, SQLAlchemy async sessions, Pydantic models, and existing router patterns.
- Keep ingestion deterministic. Do not call LLMs from ingestion workers.
- Preserve clear fallbacks for file parsing and schedule parsing.
- Store diagnostic metadata when behavior depends on external tools.
- Add tests for parser choices, fallback behavior, migrations, and API response shape changes.

Frontend:

- Keep the app utilitarian and work-focused. This is an operational tool, not a marketing site.
- Reuse existing components and patterns before adding new abstractions.
- Keep API calls centralized in `apps/web/src/lib/api.ts`.
- Use stable `data-testid` hooks for browser smoke tests where user-facing selectors are fragile.
- Test critical project, upload, outline, generation, chat, and export flows.

LLM/agent code:

- Ground answers in uploaded documents and extracted chunks.
- Prefer explicit evidence and requirement matching over generic proposal boilerplate.
- Do not hide missing evidence. Surface gaps clearly.
- Keep prompts and outputs Bulgarian-first unless a user explicitly asks otherwise.

## Git Discipline

Worktrees may be dirty. Do not revert unrelated changes.

Before staging, inspect:

```powershell
git status --short
git diff --name-only
```

Stage only files related to the current task. Secrets and local files must never be committed:

- `.env`
- `env.txt`
- local test artifacts
- `.claude/` worktrees
- `apps/web/test-results/`

Commit messages should be short and conventional:

- `feat(api): ...`
- `fix(web): ...`
- `test(api): ...`
- `docs: ...`
- `chore: ...`

Before push, expect generated documentation hooks to run. If `docs/ENGINEERING_OVERVIEW.md` changes because of the hook, review and commit it separately when appropriate.

## Documentation Rules

Update `PLAN.md` when a task changes the project direction, completed work, or next recommended steps.

Regenerate engineering docs when dependency, test inventory, route, service, or repo structure facts change:

```powershell
py -3 scripts/generate_docs.py
```

Do not manually edit `docs/ENGINEERING_OVERVIEW.md`.

Validate the shared executor guide when editing `Agent.md`, `AGENTS.md`, `CLAUDE.md`, or CI documentation rules:

```powershell
py -3 scripts/check_agent_guides.py
```

## Stability Definition

Do not tell the user the app is stable until these are true for the area touched:

- The Docker stack is healthy.
- Required migrations are applied.
- Targeted backend/frontend tests pass.
- Browser smoke passes for user-facing flow changes.
- A real manual-path smoke has been run when the change affects upload, parsing, generation, export, or startup.

For PDF ingest work, a real upload through the API or UI is required before calling it stable.

## Safety Rules

Never commit secrets.

Never run destructive Git commands such as `git reset --hard` or `git checkout --` unless the user explicitly asks for them.

Never delete user files or unrelated generated artifacts just to make `git status` look clean.

Never silently swallow parser failures when they affect document understanding. Record warnings or errors in ingest reports.

Never replace a working deterministic path with an LLM-only path for parsing, extraction, or validation.

## Executor Notes

If you are an automated coding agent:

- Read this file before editing.
- Read the relevant code before proposing a fix.
- Prefer implementing and verifying over giving abstract plans.
- Keep the user informed when doing long-running work.
- Be explicit about checks that could not be run.
- Leave unrelated local changes alone.

