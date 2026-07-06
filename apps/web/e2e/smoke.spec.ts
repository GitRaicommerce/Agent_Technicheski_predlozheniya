import { randomUUID } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";
import { Client } from "pg";

const minimalPdf = Buffer.from(
  `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Count 1 /Kids [3 0 R] >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 20 120 Td (Smoke PDF) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000010 00000 n 
0000000063 00000 n 
0000000122 00000 n 
0000000208 00000 n 
trailer
<< /Root 1 0 R /Size 5 >>
startxref
302
%%EOF`,
);

function createDbClient() {
  return new Client({
    host: process.env.PGHOST ?? "127.0.0.1",
    port: Number(process.env.PGPORT ?? 5432),
    user: process.env.POSTGRES_USER ?? "tpai",
    password: process.env.POSTGRES_PASSWORD ?? "tpai_dev",
    database: process.env.POSTGRES_DB ?? "tpai",
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("tp_disable_auto_lex_refresh", "1");
  });
});

function exportReadyText(opening: string) {
  const detailSentence =
    "The proposal explains the execution sequence, responsible roles, coordination rhythm, quality controls, reporting evidence, risk response, resource readiness, acceptance checks, and communication duties in enough operational detail for export validation.";

  return [opening, ...Array.from({ length: 12 }, () => detailSentence)].join(
    " ",
  );
}

async function seedProjectState(
  projectId: string,
  options?: {
    staleGeneration?: boolean;
    missingRequirementCoverage?: boolean;
    shallowRequirementCoverage?: boolean;
    duplicateSelectedGeneration?: boolean;
    outlineLocked?: boolean;
    includeAlternativeGeneration?: boolean;
    generationJob?: {
      status?: string;
      totalSections?: number;
      completedSections?: number;
      skippedSections?: number;
      currentSectionTitle?: string;
      error?: string | null;
    };
  },
) {
  const client = createDbClient();
  const sectionUid = randomUUID();
  const subsectionUid = randomUUID();
  const outlineId = randomUUID();
  const scheduleFileId = randomUUID();
  const snapshotId = randomUUID();
  const normalizedId = randomUUID();
  const generationId = randomUUID();
  const alternativeGenerationId = randomUUID();
  const generationJobId = randomUUID();

  const outlineJson = {
    sections: [
      {
        uid: sectionUid,
        title: "General Requirements",
        display_numbering: "1",
        required: true,
        requirements: ["Cover the general execution requirements."],
        requirement_ids: ["req-general-1", "req-general-2"],
        subsections: [
          {
            uid: subsectionUid,
            title: "Execution Plan",
            display_numbering: "1.1",
            required: true,
            subsections: [],
          },
        ],
      },
    ],
  };

  const scheduleJson = {
    tasks: [
      {
        uid: "task-1",
        wbs: "1",
        name: "Mobilization",
        duration_days: 5,
        start: "2026-05-01",
        finish: "2026-05-05",
      },
    ],
    resources: [{ id: "res-1", name: "Engineering Team" }],
  };
  const generationFlags = options?.missingRequirementCoverage
    ? {
        requirement_coverage: {
          total: 2,
          covered: 1,
          missing: 1,
          missing_ids: ["req-general-2"],
          items: [
            {
              id: "req-general-1",
              text: "Cover the general execution requirements.",
              status: "covered",
            },
            {
              id: "req-general-2",
              text: "Describe a specific missing tender requirement.",
              status: "missing",
              importance: "mandatory",
            },
          ],
        },
      }
    : options?.shallowRequirementCoverage
      ? {
          requirement_coverage: {
            total: 3,
            covered: 3,
            missing: 0,
            missing_ids: [],
            items: [
              {
                id: "req-general-1",
                text: "Cover the general execution requirements.",
                status: "covered",
              },
              {
                id: "req-general-2",
                text: "Describe sequence, controls, and responsibilities.",
                status: "covered",
              },
              {
                id: "req-general-3",
                text: "Describe acceptance and reporting for the work.",
                status: "covered",
              },
            ],
          },
        }
      : null;
  const generationText = options?.shallowRequirementCoverage
    ? "Short covered text."
    : exportReadyText("Seeded generated text for smoke export.");

  await client.connect();
  try {
    await client.query(
      `
        INSERT INTO tp_outlines (id, project_id, outline_json, status_locked, version)
        VALUES ($1, $2, $3::jsonb, $4, 1)
      `,
      [outlineId, projectId, JSON.stringify(outlineJson), options?.outlineLocked ?? false],
    );

    await client.query(
      `
        INSERT INTO project_files (
          id, project_id, module, filename, storage_key, file_hash, version, ingest_status
        )
        VALUES ($1, $2, 'schedule', 'schedule-seeded.pdf', $3, $4, 1, 'done')
      `,
      [scheduleFileId, projectId, `projects/${projectId}/schedule/${scheduleFileId}/schedule-seeded.pdf`, randomUUID().replaceAll("-", "")],
    );

    await client.query(
      `
        INSERT INTO schedule_snapshots (
          id, project_id, file_id, file_hash, parser_version
        )
        VALUES ($1, $2, $3, $4, 'playwright-smoke')
      `,
      [snapshotId, projectId, scheduleFileId, randomUUID().replaceAll("-", "")],
    );

    await client.query(
      `
        INSERT INTO schedule_normalized (
          id, project_id, schedule_snapshot_id, schedule_json, status_locked, version
        )
        VALUES ($1, $2, $3, $4::jsonb, true, 1)
      `,
      [normalizedId, projectId, snapshotId, JSON.stringify(scheduleJson)],
    );

    await client.query(
      `
        INSERT INTO generations (
          id, project_id, section_uid, variant, text, evidence_status, selected, trace_id, flags_json
        )
        VALUES ($1, $2, $3, '1', $4, $5, true, $6, $7::jsonb)
      `,
      [
        generationId,
        projectId,
        sectionUid,
        generationText,
        options?.staleGeneration ? "stale" : "ok",
        randomUUID(),
        JSON.stringify(generationFlags),
      ],
    );

    if (options?.includeAlternativeGeneration || options?.duplicateSelectedGeneration) {
      await client.query(
        `
          INSERT INTO generations (
            id, project_id, section_uid, variant, text, evidence_status, selected, trace_id
          )
          VALUES ($1, $2, $3, '2', $4, 'ok', $5, $6)
        `,
        [
          alternativeGenerationId,
          projectId,
          sectionUid,
          exportReadyText("Alternative smoke variant text."),
          options?.duplicateSelectedGeneration ?? false,
          randomUUID(),
        ],
      );
    }

    if (options?.generationJob) {
      await client.query(
        `
          INSERT INTO generation_jobs (
            id,
            project_id,
            job_type,
            status,
            total_sections,
            completed_sections,
            skipped_sections,
            current_section_uid,
            current_section_title,
            error,
            result_json,
            trace_id
          )
          VALUES ($1, $2, 'drafting_all', $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
        `,
        [
          generationJobId,
          projectId,
          options.generationJob.status ?? "processing",
          options.generationJob.totalSections ?? 3,
          options.generationJob.completedSections ?? 1,
          options.generationJob.skippedSections ?? 0,
          subsectionUid,
          options.generationJob.currentSectionTitle ?? "Execution Plan",
          options.generationJob.error ?? null,
          JSON.stringify({ source: "playwright-smoke" }),
          randomUUID(),
        ],
      );
    }
  } finally {
    await client.end();
  }

  return {
    sectionUid,
    generationId,
    alternativeGenerationId: options?.includeAlternativeGeneration || options?.duplicateSelectedGeneration
      ? alternativeGenerationId
      : null,
    generationJobId: options?.generationJob ? generationJobId : null,
  };
}

async function seedGenerationVariant(
  projectId: string,
  sectionUid: string,
  options: {
    variant: string;
    text: string;
    selected?: boolean;
    evidenceStatus?: string;
  },
) {
  const client = createDbClient();
  const generationId = randomUUID();

  await client.connect();
  try {
    if (options.selected) {
      await client.query(
        `
          UPDATE generations
          SET selected = false
          WHERE project_id = $1 AND section_uid = $2
        `,
        [projectId, sectionUid],
      );
    }

    await client.query(
      `
        INSERT INTO generations (
          id, project_id, section_uid, variant, text, evidence_status, selected, trace_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      `,
      [
        generationId,
        projectId,
        sectionUid,
        options.variant,
        options.text,
        options.evidenceStatus ?? "ok",
        options.selected ?? false,
        randomUUID(),
      ],
    );
  } finally {
    await client.end();
  }

  return generationId;
}

async function waitForProjectPage(page: Page, projectName: string) {
  await page.waitForLoadState("domcontentloaded");
  await expect(
    page.getByRole("heading", { level: 1, name: projectName }),
  ).toBeVisible({ timeout: 20_000 });
}

test.describe("smoke", () => {
  test("creates, edits, and deletes a project through the UI", async ({ page, request }) => {
    const projectName = `Smoke Project ${Date.now()}`;
    let projectId: string | null = null;

    try {
      await page.goto("/projects/new");

      await page.getByTestId("project-name-input").fill(projectName);
      await page.getByTestId("project-location-input").fill("Sofia");
      await page.getByTestId("project-description-input").fill("Playwright smoke coverage");
      await page.getByTestId("project-authority-input").fill("Smoke Authority");
      await page.getByTestId("create-project-submit").click();

      await page.waitForURL(/\/projects\/(?!new$)[^/]+$/);
      projectId = page.url().split("/").pop() ?? null;

      await waitForProjectPage(page, projectName);

      await page.getByTestId("project-edit-button").click();
      await page.getByTestId("project-edit-location-input").fill("Plovdiv");
      await page.getByTestId("project-edit-description-input").fill("Updated by smoke test");
      await page.getByTestId("project-save-button").click();

      await expect(page.getByText("Plovdiv")).toBeVisible();

      await page.getByTestId("project-delete-button").click();
      if (!projectId) throw new Error("Project id was not captured after creation.");
      const deleteResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "DELETE" &&
          response.url().includes(`/api/v1/projects/${projectId}`),
      );
      await page.getByTestId("project-delete-confirm").click();
      const deleteResponse = await deleteResponsePromise;
      expect(deleteResponse.status()).toBe(204);

      await page.goto("/projects");
      await expect(page.getByTestId("new-project-link")).toBeVisible();
      await expect(page.getByText(projectName)).toHaveCount(0);
      projectId = null;
    } finally {
      if (projectId) {
        await request.delete(`/api/v1/projects/${projectId}`);
      }
    }
  });

  test("uploads files in the examples and schedule flows", async ({ page, request }) => {
    const projectName = `Smoke Upload ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("module-toggle-examples").click();
      await page.getByTestId("file-upload-input-examples").setInputFiles({
        name: "example-smoke.pdf",
        mimeType: "application/pdf",
        buffer: minimalPdf,
      });
      await expect(page.getByText("example-smoke.pdf")).toBeVisible();

      await page.getByTestId("schedule-panel-toggle").click();
      await page.getByTestId("file-upload-input-schedule").setInputFiles({
        name: "schedule-smoke.pdf",
        mimeType: "application/pdf",
        buffer: minimalPdf,
      });
      await expect(page.getByText("schedule-smoke.pdf")).toBeVisible();

      await page.getByTestId("outline-panel-toggle").click();
      await expect(page.getByTestId("outline-panel-toggle")).toBeVisible();

      await page.getByTestId("generations-panel-toggle").click();
      await expect(page.getByTestId("generations-panel-toggle")).toBeVisible();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows seeded outline, opens generations, and has a ready export endpoint", async ({ page, request }) => {
    const projectName = `Smoke Export ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid } = await seedProjectState(projectId, { outlineLocked: true });

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("outline-panel-toggle").click();
      await expect(page.getByText("General Requirements")).toBeVisible();
      await expect(
        page.getByTestId(`outline-section-${sectionUid}-requirement-count`),
      ).toHaveText("2");

      await page.getByTestId("generations-panel-toggle").click();
      await expect(page.getByTestId("generations-panel-toggle")).toBeVisible();

      await expect(page.getByRole("button", { name: /\.docx/i })).toBeVisible();
      const exportResponse = await request.get(`/api/v1/export/${projectId}/docx`);

      expect(exportResponse.ok()).toBeTruthy();
      expect(exportResponse.headers()["content-disposition"]).toContain(".docx");
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows stale export warning for outdated seeded generations", async ({ page, request }) => {
    const projectName = `Smoke Stale ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid } = await seedProjectState(projectId, {
      staleGeneration: true,
      outlineLocked: true,
    });

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("export-docx-button").click();

      await expect(page.getByTestId("export-stale-warning")).toContainText(
        "1 секция",
      );
      await page.getByRole("button", { name: "Отвори Генерации" }).click();
      await expect(
        page.getByTestId(`generation-section-${sectionUid}`),
      ).toBeVisible();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows duplicate selected warning for ambiguous seeded generations", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Duplicate ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid, alternativeGenerationId } = await seedProjectState(projectId, {
      duplicateSelectedGeneration: true,
      outlineLocked: true,
    });
    expect(alternativeGenerationId).toBeTruthy();

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("export-docx-button").click();

      await expect(
        page.getByTestId("export-duplicate-selected-warning"),
      ).toContainText("1 секция");
      await page
        .getByTestId("export-duplicate-selected-warning")
        .getByRole("button")
        .click();
      await expect(page.getByTestId("generation-attention-summary")).toContainText(
        "1 секция изисква внимание",
      );
      await expect(page.getByTestId("generation-attention-summary")).toContainText(
        "дублиран избор: 1",
      );
      await page.getByTestId("generation-attention-filter-toggle").click();
      await expect(
        page.getByTestId(`generation-section-${sectionUid}`),
      ).toBeVisible();
      await page.getByTestId(`generation-section-${sectionUid}`).click();
      await expect(
        page.getByTestId(`generation-duplicate-selected-warning-${sectionUid}`),
      ).toContainText("2 selected variants");

      await page
        .getByTestId(`generation-select-${alternativeGenerationId}`)
        .click();

      await expect(
        page.getByTestId(`generation-duplicate-selected-warning-${sectionUid}`),
      ).toHaveCount(0);

      const exportResponse = await request.get(`/api/v1/export/${projectId}/docx`);
      expect(exportResponse.ok()).toBeTruthy();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows multiple pre-export warnings from one readiness check", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Readiness ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    await seedProjectState(projectId, {
      duplicateSelectedGeneration: true,
      staleGeneration: true,
      missingRequirementCoverage: true,
      outlineLocked: true,
    });

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("export-docx-button").click();

      await expect(
        page.getByTestId("export-duplicate-selected-warning"),
      ).toBeVisible();
      await expect(page.getByTestId("export-stale-warning")).toBeVisible();
      await expect(page.getByTestId("export-requirement-warning")).toBeVisible();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows requirement coverage warning for incomplete selected generations", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Requirements ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid } = await seedProjectState(projectId, {
      missingRequirementCoverage: true,
      outlineLocked: true,
    });

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("export-docx-button").click();

      await expect(page.getByTestId("export-requirement-warning")).toContainText(
        "1 изискване",
      );
      await page.getByTestId("export-requirement-warning").getByRole("button").click();
      await page.getByTestId(`generation-section-${sectionUid}`).click();
      await expect(
        page.getByTestId(`generation-requirement-coverage-${sectionUid}`),
      ).toContainText("1/2");
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows quality warning for shallow selected generations", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Quality ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid } = await seedProjectState(projectId, {
      shallowRequirementCoverage: true,
      outlineLocked: true,
    });

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("export-docx-button").click();

      await expect(page.getByTestId("export-quality-warning")).toContainText(
        "1 секция",
      );
      await page.getByTestId("export-quality-warning").getByRole("button").click();
      await expect(
        page.getByTestId(`generation-section-${sectionUid}`),
      ).toBeVisible();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("shows latest all-section background generation progress", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Progress ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    await seedProjectState(projectId, {
      outlineLocked: true,
      generationJob: {
        status: "processing",
        totalSections: 3,
        completedSections: 1,
        skippedSections: 1,
        currentSectionTitle: "Execution Plan",
      },
    });

    try {
      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("generations-panel-toggle").click();

      const progress = page.getByTestId("generation-job-progress");
      await expect(progress).toBeVisible();
      await expect(progress).toContainText("2 / 3");
      await expect(progress).toContainText("Execution Plan");
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("starts stale selected section regeneration from generations panel", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Stale Regen ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid } = await seedProjectState(projectId, {
      outlineLocked: true,
      staleGeneration: true,
    });
    const staleJobId = randomUUID();
    let staleJobStarted = false;
    const staleJob = {
      id: staleJobId,
      project_id: projectId,
      job_type: "drafting_stale",
      status: "queued",
      total_sections: 1,
      completed_sections: 0,
      skipped_sections: 0,
      current_section_uid: null,
      current_section_title: null,
      error: null,
      result_json: { target_reason: "stale_selected" },
      trace_id: randomUUID(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      completed_at: null,
    };

    try {
      await page.route(
        `**/api/v1/agents/${projectId}/generation-jobs/latest`,
        async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(staleJobStarted ? staleJob : null),
          });
        },
      );
      await page.route(
        `**/api/v1/agents/${projectId}/generation-jobs/stale`,
        async (route) => {
          staleJobStarted = true;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(staleJob),
          });
        },
      );

      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("generations-panel-toggle").click();
      await expect(
        page.getByTestId("generation-stale-selected-action"),
      ).toContainText("1 selected stale section");
      await expect(page.getByTestId("generation-attention-summary")).toContainText(
        "1 секция изисква внимание",
      );
      await expect(page.getByTestId("generation-attention-summary")).toContainText(
        "остарели избрани: 1",
      );
      await expect(
        page.getByTestId(`generation-stale-selected-badge-${sectionUid}`),
      ).toContainText("остаряла");

      await page.getByTestId("generation-stale-regenerate-button").click();

      await expect(page.getByTestId("generation-job-progress")).toContainText(
        "0 / 1",
      );
      expect(staleJobStarted).toBeTruthy();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("reloads a section after a deterministic regenerate action", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Regenerate ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid } = await seedProjectState(projectId, {
      outlineLocked: true,
    });
    let regeneratedGenerationId: string | null = null;

    try {
      await page.route(
        `**/api/v1/agents/${projectId}/sections/${sectionUid}/regenerate`,
        async (route) => {
          regeneratedGenerationId = await seedGenerationVariant(
            projectId,
            sectionUid,
            {
              variant: "2",
              text: "Regenerated smoke text for the section.",
              selected: true,
            },
          );
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              generation_ids: { variant_1: regeneratedGenerationId },
              trace_id: randomUUID(),
            }),
          });
        },
      );

      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByTestId("generations-panel-toggle").click();
      await page.getByTestId(`generation-section-${sectionUid}`).click();
      await expect(
        page.getByText("Seeded generated text for smoke export."),
      ).toBeVisible();

      await page.getByTestId(`generation-regenerate-${sectionUid}`).click();

      await expect(
        page.getByText("Regenerated smoke text for the section."),
      ).toBeVisible();
      expect(regeneratedGenerationId).not.toBeNull();
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });

  test("opens outline and generations panels from a deterministic chat flow", async ({
    page,
    request,
  }) => {
    const projectName = `Smoke Chat ${Date.now()}`;
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        name: projectName,
        location: "Sofia",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const project = (await createResponse.json()) as { id: string };
    const projectId = project.id;
    const { sectionUid, generationId, alternativeGenerationId } =
      await seedProjectState(projectId, {
      outlineLocked: true,
      includeAlternativeGeneration: true,
    });

    try {
      await page.route("**/api/v1/agents/chat", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            schema_version: "v1.3",
            status: "ok",
            trace_id: randomUUID(),
            assistant_message:
              "Генерирах текстовете и отворих панелите за преглед.",
            ui_actions: [
              {
                type: "show_outline",
                payload: {
                  message: "Outline е готов за преглед.",
                },
              },
            ],
            agent_called: "drafting_all",
            questions_to_user: [],
            agent_result: {
              variant_1: {
                text: "Chat smoke variant 1 text.",
              },
              variant_2: {
                text: "Chat smoke variant 2 text.",
              },
              generation_ids: {
                variant_1: generationId,
                variant_2: alternativeGenerationId,
              },
              verification: { verdict: "ok" },
            },
          }),
        });
      });

      await page.goto(`/projects/${projectId}`);
      await waitForProjectPage(page, projectName);

      await page.getByRole("textbox").fill("Генерирай текстовете по outline-а");
      await page.getByRole("button", { name: "Изпрати" }).click();

      await expect(
        page.getByText("Генерирах текстовете и отворих панелите за преглед."),
      ).toBeVisible();
      await expect(page.getByText("Outline е готов за преглед.")).toBeVisible();
      await expect(
        page.getByTestId(`outline-section-${sectionUid}`),
      ).toBeVisible();
      await expect(
        page.getByTestId(`generation-section-${sectionUid}`),
      ).toBeVisible();

      await page.getByTestId(`generation-section-${sectionUid}`).click();
      await expect(
        page.getByText("Seeded generated text for smoke export."),
      ).toBeVisible();

      expect(alternativeGenerationId).not.toBeNull();
      await page.getByTestId(`pin-generation-${alternativeGenerationId}`).click();

      await expect.poll(async () => {
        const response = await request.get(
          `/api/v1/agents/${projectId}/generations`,
        );
        const sections = (await response.json()) as Array<{
          variants: Array<{ id: string; selected: boolean }>;
        }>;
        return sections
          .flatMap((section) => section.variants)
          .find((variant) => variant.id === alternativeGenerationId)?.selected;
      }).toBe(true);
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });
});
