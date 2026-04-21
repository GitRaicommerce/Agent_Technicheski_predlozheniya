import { expect, test } from "@playwright/test";

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
});
