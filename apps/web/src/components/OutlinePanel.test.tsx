import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OutlinePanel from "./OutlinePanel";
import { api, type ContentPlan } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      agents: { ...actual.api.agents, getOutline: vi.fn() },
      contentPlan: {
        get: vi.fn(),
        build: vi.fn(),
        updateItem: vi.fn(),
        approve: vi.fn(),
        unlock: vi.fn(),
      },
    },
  };
});

const plan: ContentPlan = {
  outline_id: "outline-v2",
  version: 3,
  status_locked: false,
  source: "understanding_content_plan",
  understanding_status: {
    requirements_confirmed: true,
    wbs_confirmed: true,
    fact_sheet_confirmed: true,
  },
  items: [
    {
      id: "item-1",
      project_id: "project-1",
      outline_id: "outline-v2",
      parent_id: null,
      uid: "plan-uid-1",
      number: "1",
      title: "Управление на риска",
      source_quotes_json: [{
        requirement_id: "req-1",
        source_file_id: "file-1",
        source_page: 29,
        source_quote: "Участникът следва да разработи мерки за риска.",
      }],
      acceptance_criteria_json: [{
        id: "criterion-1",
        text: "За всеки риск е посочена превантивна мярка.",
        kind: "content",
        requirement_id: "req-1",
        requirement_text: "Да се разработят мерки за риска.",
      }],
      content_kind: "specific",
      linked_wbs_ids: ["wbs-1"],
      linked_fact_keys: ["stages"],
      forlage_section_id: null,
      order_index: 1,
      status: "draft",
      generation_uid: "generation-uid-1",
    },
  ],
};

describe("OutlinePanel Phase 2", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.agents.getOutline).mockResolvedValue(null);
    vi.mocked(api.contentPlan.get).mockResolvedValue(null);
  });

  it("offers a deterministic build when no content plan exists", async () => {
    vi.mocked(api.contentPlan.build).mockResolvedValue(plan);
    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByText(/не използва API кредити/i)).toBeInTheDocument();
    await userEvent.click(await screen.findByTestId("content-plan-build-button"));

    await waitFor(() => expect(api.contentPlan.build).toHaveBeenCalledWith("project-1"));
    expect(await screen.findByTestId("content-plan-editor")).toBeInTheDocument();
  });

  it("warns that a legacy outline is not the Understanding plan", async () => {
    vi.mocked(api.agents.getOutline).mockResolvedValue({
      id: "legacy",
      outline_json: { sections: [] },
      status_locked: true,
      version: 2,
    });
    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByTestId("legacy-outline-warning")).toHaveTextContent("стар план v2");
  });

  it("renders criteria and approves the detailed plan", async () => {
    vi.mocked(api.contentPlan.get).mockResolvedValue(plan);
    vi.mocked(api.contentPlan.approve).mockResolvedValue({ ...plan, status_locked: true });
    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByText("Управление на риска")).toBeInTheDocument();
    expect(screen.getByText("За всеки риск е посочена превантивна мярка.")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("content-plan-approve-button"));

    await waitFor(() => expect(api.contentPlan.approve).toHaveBeenCalledWith("project-1"));
    expect(await screen.findByText("✓ Планът е одобрен")).toBeInTheDocument();
  });

  it("keeps approval disabled until WBS and fact sheet are confirmed", async () => {
    vi.mocked(api.contentPlan.get).mockResolvedValue({
      ...plan,
      understanding_status: {
        requirements_confirmed: true,
        wbs_confirmed: false,
        fact_sheet_confirmed: false,
      },
    });
    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByTestId("content-plan-understanding-warning")).toBeInTheDocument();
    expect(screen.getByTestId("content-plan-approve-button")).toBeDisabled();
  });

  it("keeps tender-mandated headings visibly locked", async () => {
    vi.mocked(api.contentPlan.get).mockResolvedValue({
      ...plan,
      items: [{
        ...plan.items[0],
        source_quotes_json: [{
          ...plan.items[0].source_quotes_json[0],
          source_kind: "mandatory_heading",
        }],
      }],
    });
    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByText("задължително")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "редакция" }));
    expect(screen.getByLabelText("Заглавие на точката")).toBeDisabled();
  });

  it("edits a point title, classification, and acceptance criteria", async () => {
    vi.mocked(api.contentPlan.get).mockResolvedValue(plan);
    vi.mocked(api.contentPlan.updateItem).mockResolvedValue({
      ...plan.items[0],
      title: "Рискове и мерки",
      content_kind: "mixed",
      acceptance_criteria_json: [{ ...plan.items[0].acceptance_criteria_json[0], text: "Има собственик на риска." }],
    });
    render(<OutlinePanel projectId="project-1" />);

    await userEvent.click(await screen.findByRole("button", { name: "редакция" }));
    await userEvent.clear(screen.getByLabelText("Заглавие на точката"));
    await userEvent.type(screen.getByLabelText("Заглавие на точката"), "Рискове и мерки");
    await userEvent.selectOptions(screen.getByLabelText("Вид съдържание"), "mixed");
    await userEvent.clear(screen.getByLabelText("Критерии за приемане"));
    await userEvent.type(screen.getByLabelText("Критерии за приемане"), "Има собственик на риска.");
    await userEvent.click(screen.getByRole("button", { name: "Запази" }));

    await waitFor(() => expect(api.contentPlan.updateItem).toHaveBeenCalled());
    expect(await screen.findByText("Рискове и мерки")).toBeInTheDocument();
  });
});
