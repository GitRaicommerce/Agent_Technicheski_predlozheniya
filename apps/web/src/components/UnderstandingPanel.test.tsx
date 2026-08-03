import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import UnderstandingPanel from "./UnderstandingPanel";
import { api, type UnderstandingWorkspace } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      understanding: Object.fromEntries(
        Object.keys(actual.api.understanding).map((key) => [key, vi.fn()]),
      ),
    },
  };
});

const workspace: UnderstandingWorkspace = {
  enabled: true,
  sources: [{ id: "file-1", filename: "tender.pdf" }],
  requirements: [
    {
      id: "req-1",
      project_id: "project-1",
      source_file_id: "file-1",
      source_page: 8,
      source_quote: "Участникът следва да представи график.",
      normalized_text: "Представяне на график",
      kind: "obligation",
      target_section_hint: "График",
      status: "extracted",
      created_at: "2026-08-03T10:00:00Z",
    },
  ],
  wbs_items: [
    {
      id: "wbs-1",
      project_id: "project-1",
      parent_id: null,
      level: 0,
      kind: "activity",
      title: "Изготвяне на график",
      description: null,
      source_refs_json: [],
      schedule_task_uid: "12",
      order_index: 0,
      status: "extracted",
    },
  ],
  fact_sheet: {
    id: "fact-1",
    project_id: "project-1",
    version: 1,
    facts_json: { subject: "Проектиране" },
    status: "draft",
  },
  latest_job: null,
};

const getMock = vi.mocked(api.understanding.get);
const startMock = vi.mocked(api.understanding.start);
const updateRequirementMock = vi.mocked(api.understanding.updateRequirement);
const deleteRequirementMock = vi.mocked(api.understanding.deleteRequirement);
const confirmRequirementsMock = vi.mocked(api.understanding.confirmRequirements);
const createWbsItemMock = vi.mocked(api.understanding.createWbsItem);
const confirmWbsMock = vi.mocked(api.understanding.confirmWbs);
const saveFactSheetMock = vi.mocked(api.understanding.saveFactSheet);

describe("UnderstandingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMock.mockResolvedValue(workspace);
    startMock.mockResolvedValue({
      id: "job-1",
      project_id: "project-1",
      status: "queued",
      total_batches: 0,
      completed_batches: 0,
      created_at: "2026-08-03T10:00:00Z",
      updated_at: "2026-08-03T10:00:00Z",
    });
    updateRequirementMock.mockResolvedValue(workspace.requirements[0]);
    deleteRequirementMock.mockResolvedValue();
    confirmRequirementsMock.mockResolvedValue({ status: "confirmed", updated: 1 });
    createWbsItemMock.mockResolvedValue(workspace.wbs_items[0]);
    confirmWbsMock.mockResolvedValue({ status: "confirmed", updated: 1 });
    saveFactSheetMock.mockResolvedValue(workspace.fact_sheet!);
  });

  it("shows the three Bulgarian review panels and their source links", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    expect(await screen.findByText("стр. 8: „Участникът следва да представи график.“"))
      .toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Дейности" }));
    expect(screen.getByDisplayValue("Изготвяне на график")).toBeInTheDocument();
    expect(screen.getByText("График: задача 12")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Fact sheet" }));
    expect(screen.getByLabelText("Fact sheet JSON")).toHaveValue(
      '{\n  "subject": "Проектиране"\n}',
    );
  });

  it("edits and saves an extracted requirement", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    const input = await screen.findByLabelText("Нормализирано изискване");
    await userEvent.clear(input);
    await userEvent.type(input, "Подробен график");
    await userEvent.click(screen.getByRole("button", { name: "Запази" }));

    await waitFor(() => {
      expect(updateRequirementMock).toHaveBeenCalledWith(
        "project-1",
        "req-1",
        expect.objectContaining({ normalized_text: "Подробен график" }),
      );
    });
  });

  it("starts the full understanding job", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click(await screen.findByTestId("understanding-start"));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith("project-1");
    });
  });

  it("adds and confirms WBS activities", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click(await screen.findByRole("tab", { name: "Дейности" }));
    await userEvent.type(screen.getByPlaceholderText("Нова дейност"), "Контрол");
    await userEvent.click(screen.getByRole("button", { name: "Добави" }));

    await waitFor(() => {
      expect(createWbsItemMock).toHaveBeenCalledWith(
        "project-1",
        expect.objectContaining({ title: "Контрол", kind: "activity" }),
      );
    });
    await userEvent.click(screen.getByRole("button", { name: "Потвърди WBS" }));
    expect(confirmWbsMock).toHaveBeenCalledWith("project-1");
  });

  it("deletes requirements and saves edited fact sheet data", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click(await screen.findByRole("button", { name: "Изтрий изискване" }));
    expect(deleteRequirementMock).toHaveBeenCalledWith("project-1", "req-1");

    await userEvent.click(screen.getByRole("tab", { name: "Fact sheet" }));
    const editor = screen.getByLabelText("Fact sheet JSON");
    fireEvent.change(editor, { target: { value: '{"subject":"Нов предмет"}' } });
    await userEvent.click(screen.getByRole("button", { name: "Запази" }));

    await waitFor(() => {
      expect(saveFactSheetMock).toHaveBeenCalledWith(
        "project-1",
        { subject: "Нов предмет" },
      );
    });
  });
});
