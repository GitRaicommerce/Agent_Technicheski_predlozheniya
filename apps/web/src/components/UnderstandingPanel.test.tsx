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
      contentPlan: {
        ...actual.api.contentPlan,
        get: vi.fn(),
      },
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
      scope: "proposal_content",
      target_section_hint: "График",
      proposal_path_json: ["Програма", "Линеен график"],
      acceptance_criteria_json: ["Включва всички дейности"],
      status: "extracted",
      origin: "map",
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
  proposal_focus: {
    roles: [
      { role: "Проектант по част „ВиК“", count: 1 },
      { role: "Технически ръководител", count: 1 },
    ],
  },
  acceptance: {
    machine_total: 1,
    all_requirement_count: 1,
    proposal_requirement_count: 1,
    accepted_machine: 1,
    noise_count: 0,
    manual_additions: 0,
    precision: 1,
    recall: 1,
    missed_rate: 0,
    review_complete: false,
    goal_missed_rate: 0.05,
    goal_met: false,
  },
};

const getMock = vi.mocked(api.understanding.get);
const getContentPlanMock = vi.mocked(api.contentPlan.get);
const startMock = vi.mocked(api.understanding.start);
const cancelJobMock = vi.mocked(api.understanding.cancelJob);
const resumeJobMock = vi.mocked(api.understanding.resumeJob);
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
    getContentPlanMock.mockResolvedValue({
      outline_id: "outline-1",
      version: 1,
      status_locked: false,
      source: "understanding_content_plan",
      understanding_status: {},
      items: [
        {
          id: "heading-1",
          project_id: "project-1",
          outline_id: "outline-1",
          parent_id: null,
          uid: "heading-uid-1",
          number: "1",
          title: "Концепция и подход",
          source_quotes_json: [{ requirement_id: "", source_file_id: "file-1", source_page: 8, source_quote: "1. Концепция и подход", source_kind: "mandatory_heading" }],
          acceptance_criteria_json: [{ id: "criterion-1", text: "Включва всички дейности", kind: "content", requirement_id: "req-1" }],
          content_kind: "specific",
          linked_wbs_ids: [],
          linked_fact_keys: [],
          order_index: 1,
          status: "draft",
          generation_uid: "generation-1",
        },
      ],
    });
    startMock.mockResolvedValue({
      id: "job-1",
      project_id: "project-1",
      status: "queued",
      total_batches: 0,
      completed_batches: 0,
      created_at: "2026-08-03T10:00:00Z",
      updated_at: "2026-08-03T10:00:00Z",
    });
    cancelJobMock.mockResolvedValue({
      id: "job-1",
      project_id: "project-1",
      status: "cancelled",
      total_batches: 18,
      completed_batches: 16,
      created_at: "2026-08-03T10:00:00Z",
      updated_at: "2026-08-03T11:00:00Z",
    });
    resumeJobMock.mockResolvedValue({
      id: "job-2",
      project_id: "project-1",
      status: "queued",
      total_batches: 0,
      completed_batches: 0,
      created_at: "2026-08-03T11:00:00Z",
      updated_at: "2026-08-03T11:00:00Z",
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

    await userEvent.click((await screen.findByTestId("requirement-group-1")).querySelector("summary")!);
    expect(await screen.findByText("стр. 8: „Участникът следва да представи график.“"))
      .toBeInTheDocument();
    expect(screen.getByTestId("understanding-acceptance")).toHaveTextContent("100.0%");
    expect(screen.getByTestId("proposal-focus")).toHaveTextContent("Задължително съдържание, извлечено от документацията");
    expect(screen.getByTestId("proposal-focus")).toHaveTextContent("Концепция и подход");
    expect(screen.getByTestId("proposal-focus")).toHaveTextContent("Проектант по част „ВиК“");
    await userEvent.click(screen.getByRole("tab", { name: "Дейности за ТП" }));
    expect(screen.getByDisplayValue("Изготвяне на график")).toBeInTheDocument();
    expect(screen.getByText("График: задача 12")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Данни за проекта" }));
    expect(screen.getByLabelText("Fact sheet JSON")).toHaveValue(
      '{\n  "subject": "Проектиране"\n}',
    );
  });

  it("uses the current tender hierarchy instead of fixed clause numbers", async () => {
    getContentPlanMock.mockResolvedValueOnce({
      outline_id: "outline-other",
      version: 1,
      status_locked: false,
      source: "understanding_content_plan",
      understanding_status: {},
      items: [{
        id: "heading-other",
        project_id: "project-1",
        outline_id: "outline-other",
        parent_id: null,
        uid: "heading-other-uid",
        number: "7.4",
        title: "Методика, етапи и график за услугата",
        source_quotes_json: [{ requirement_id: "", source_file_id: "file-1", source_page: 42, source_quote: "7.4 Методика, етапи и график за услугата", source_kind: "mandatory_heading" }],
        acceptance_criteria_json: [],
        content_kind: "specific",
        linked_wbs_ids: [],
        linked_fact_keys: [],
        order_index: 1,
        status: "draft",
        generation_uid: "generation-other",
      }],
    });

    render(<UnderstandingPanel projectId="project-1" />);

    const focus = await screen.findByTestId("proposal-focus");
    expect(focus).toHaveTextContent("7.4. Методика, етапи и график за услугата");
    expect(focus).toHaveTextContent("tender.pdf, стр. 42");
    expect(focus).not.toHaveTextContent("6.2");
    expect(focus).not.toHaveTextContent("4.5.3");
  });

  it("does not treat legacy example-proposal gaps as current requirements", async () => {
    getMock.mockResolvedValueOnce({
      ...workspace,
      probable_gaps: [
        {
          snippet_id: "legacy-example",
          file_id: "example-file",
          text: "Точка само от старото техническо предложение",
          best_match_score: 0.1,
        },
      ],
    } as UnderstandingWorkspace);

    render(<UnderstandingPanel projectId="project-1" />);

    expect(await screen.findByTestId("understanding-acceptance")).toBeInTheDocument();
    expect(screen.queryByText(/Вероятни пропуски/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Точка само от старото/)).not.toBeInTheDocument();
  });

  it("keeps qualification and execution requirements outside the TP work view", async () => {
    getMock.mockResolvedValueOnce({
      ...workspace,
      requirements: [
        ...workspace.requirements,
        {
          ...workspace.requirements[0],
          id: "req-execution",
          source_quote: "Изпълнителят извършва изпитване на уплътняването.",
          normalized_text: "Изпитване на уплътняването",
          scope: "execution_constraint",
          proposal_path_json: [],
          acceptance_criteria_json: [],
        },
      ],
      acceptance: {
        ...workspace.acceptance,
        all_requirement_count: 2,
        proposal_requirement_count: 1,
      },
    });
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click((await screen.findByTestId("requirement-group-1")).querySelector("summary")!);
    expect(await screen.findByDisplayValue("Представяне на график")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Изпитване на уплътняването")).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Всички изисквания/ })).not.toBeInTheDocument();
    expect(screen.getByTestId("proposal-focus")).toHaveTextContent(
      "Изискванията за опит, правоспособност и доказване в ЕЕДОП не са част от ТП",
    );
  });

  it("edits and saves an extracted requirement", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click((await screen.findByTestId("requirement-group-1")).querySelector("summary")!);
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

  it("allows cancelling an active job without disabling artifact tabs", async () => {
    getMock.mockResolvedValueOnce({
      ...workspace,
      latest_job: {
        id: "job-1",
        project_id: "project-1",
        status: "processing",
        total_batches: 18,
        completed_batches: 16,
        current_step: "Сливане и свързване",
        created_at: "2026-08-03T10:00:00Z",
        updated_at: "2026-08-03T10:30:00Z",
      },
    });
    render(<UnderstandingPanel projectId="project-1" />);

    expect(await screen.findByRole("tab", { name: "Дейности за ТП" })).toBeEnabled();
    await userEvent.click(screen.getByTestId("understanding-cancel"));

    await waitFor(() => {
      expect(cancelJobMock).toHaveBeenCalledWith("project-1", "job-1");
    });
  });

  it("resumes a timed-out job from its checkpoint", async () => {
    getMock.mockResolvedValueOnce({
      ...workspace,
      latest_job: {
        id: "job-1",
        project_id: "project-1",
        status: "timed_out",
        total_batches: 18,
        completed_batches: 16,
        error: "Анализът надвиши максималното време.",
        created_at: "2026-08-03T10:00:00Z",
        updated_at: "2026-08-03T11:00:00Z",
      },
    });
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click(await screen.findByTestId("understanding-resume"));

    await waitFor(() => {
      expect(resumeJobMock).toHaveBeenCalledWith("project-1", "job-1");
    });
  });

  it("adds and confirms WBS activities", async () => {
    render(<UnderstandingPanel projectId="project-1" />);

    await userEvent.click(await screen.findByRole("tab", { name: "Дейности за ТП" }));
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

    await userEvent.click((await screen.findByTestId("requirement-group-1")).querySelector("summary")!);
    await userEvent.click(await screen.findByRole("button", { name: "Изтрий изискване" }));
    expect(deleteRequirementMock).toHaveBeenCalledWith("project-1", "req-1");

    await userEvent.click(screen.getByRole("tab", { name: "Данни за проекта" }));
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
