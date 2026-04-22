import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";
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

async function seedProjectState(
  projectId: string,
  options?: { staleGeneration?: boolean; outlineLocked?: boolean },
) {
  const client = createDbClient();
  const sectionUid = randomUUID();
  const subsectionUid = randomUUID();
  const outlineId = randomUUID();
  const scheduleFileId = randomUUID();
  const snapshotId = randomUUID();
  const normalizedId = randomUUID();
  const generationId = randomUUID();

  const outlineJson = {
    sections: [
      {
        uid: sectionUid,
        title: "General Requirements",
        display_numbering: "1",
        required: true,
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
          id, project_id, section_uid, variant, text, evidence_status, selected, trace_id
        )
        VALUES ($1, $2, $3, '1', $4, $5, true, $6)
      `,
      [
        generationId,
        projectId,
        sectionUid,
        "Seeded generated text for smoke export.",
        options?.staleGeneration ? "stale" : "ok",
        randomUUID(),
      ],
    );
  } finally {
    await client.end();
  }

  return { sectionUid };
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

      await page.waitForURL(/\/projects\/[^/]+$/);
      projectId = page.url().split("/").pop() ?? null;

      await expect(page.getByRole("heading", { level: 1, name: projectName })).toBeVisible();

      await page.getByTestId("project-edit-button").click();
      await page.getByTestId("project-edit-location-input").fill("Plovdiv");
      await page.getByTestId("project-edit-description-input").fill("Updated by smoke test");
      await page.getByTestId("project-save-button").click();

      await expect(page.getByText("Plovdiv")).toBeVisible();

      await page.getByTestId("project-delete-button").click();
      await page.getByTestId("project-delete-confirm").click();
      await page.waitForURL("**/projects");

      await expect(page.getByTestId("new-project-link")).toBeVisible();
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
      await expect(page.getByRole("heading", { level: 1, name: projectName })).toBeVisible();

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
    await seedProjectState(projectId, { outlineLocked: true });

    try {
      await page.goto(`/projects/${projectId}`);
      await expect(page.getByRole("heading", { level: 1, name: projectName })).toBeVisible();

      await page.getByTestId("outline-panel-toggle").click();
      await expect(page.getByText("General Requirements")).toBeVisible();

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

  test("returns a stale export conflict for outdated seeded generations", async ({ page, request }) => {
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
    await seedProjectState(projectId, { staleGeneration: true, outlineLocked: true });

    try {
      await page.goto(`/projects/${projectId}`);
      await expect(page.getByRole("heading", { level: 1, name: projectName })).toBeVisible();

      await expect(page.getByRole("button", { name: /\.docx/i })).toBeVisible();
      const exportResponse = await request.get(`/api/v1/export/${projectId}/docx`);
      expect(exportResponse.status()).toBe(409);
    } finally {
      await request.delete(`/api/v1/projects/${projectId}`);
    }
  });
});
