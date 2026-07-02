import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RequirementChecklistPanel from "./RequirementChecklistPanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      agents: {
        ...actual.api.agents,
        getRequirementChecklist: vi.fn(),
      },
    },
  };
});

const getRequirementChecklistMock = vi.mocked(
  api.agents.getRequirementChecklist,
);

describe("RequirementChecklistPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    getRequirementChecklistMock.mockResolvedValue({
      project_id: "project-1",
      total: 2,
      importance_counts: { mandatory: 2 },
      category_counts: {
        "График и срокове": 1,
        "Качество и контрол": 1,
      },
      items: [
        {
          id: "req-1",
          text: "Да се представи линеен график.",
          category: "schedule",
          category_label: "График и срокове",
          topic: "график",
          importance: "mandatory",
          suggested_section: "Линеен график и организация във времето",
          coverage_question: "Покрит ли е линейният график?",
          source_chunk_id: "chunk-1",
          source_page: 25,
          source_section_path: "Методика",
          source_file: "Документация.pdf",
          source_excerpt: "Линеен график",
          evidence_cues: ["следва да"],
        },
        {
          id: "req-2",
          text: "Да се включат мерки за контрол на качеството.",
          category: "quality",
          category_label: "Качество и контрол",
          topic: "качество",
          importance: "mandatory",
          suggested_section: "Мерки за осигуряване на качеството",
          coverage_question: "Покрити ли са мерките за контрол?",
          source_chunk_id: "chunk-2",
          source_page: 30,
          source_section_path: "Методика",
          source_file: "Документация.pdf",
          source_excerpt: "Контрол на качеството",
          evidence_cues: ["следва да"],
        },
      ],
    });
  });

  it("renders summary, filters items, and stores checked requirements", async () => {
    render(<RequirementChecklistPanel projectId="project-1" />);

    expect(await screen.findByTestId("requirements-checklist-panel")).toBeInTheDocument();
    expect(screen.getByText("Да се представи линеен график.")).toBeInTheDocument();
    expect(
      screen.getByText("Да се включат мерки за контрол на качеството."),
    ).toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByLabelText("Филтър по категория"),
      "Качество и контрол",
    );

    expect(
      screen.queryByText("Да се представи линеен график."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Да се включат мерки за контрол на качеството."),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("checkbox"));

    await waitFor(() => {
      expect(window.localStorage.getItem("tp_requirement_checklist_checked_project-1"))
        .toContain("req-2");
    });
  });
});
