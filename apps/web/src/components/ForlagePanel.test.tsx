import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ForlagePanel from "./ForlagePanel";
import { api, type ForlageWorkspace } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      forlage: {
        get: vi.fn(),
        analyze: vi.fn(),
        confirm: vi.fn(),
        updateLink: vi.fn(),
      },
    },
  };
});

const emptyWorkspace: ForlageWorkspace = {
  project_id: "project-1",
  outline_id: "outline-12",
  outline_version: 12,
  analyzed: false,
  section_count: 0,
  mapped_count: 0,
  review_confirmed: false,
  sections: [],
  mappings: [],
};

const analyzedWorkspace: ForlageWorkspace = {
  ...emptyWorkspace,
  analyzed: true,
  section_count: 1,
  mapped_count: 1,
  sections: [{
    id: "section-quality",
    file_id: "file-1",
    filename: "example.docx",
    number: "7",
    title: "Контрол на качеството",
    path: ["Работна програма", "Контрол на качеството"],
    order_index: 1,
    page_start: 8,
    page_end: 10,
    text_preview: "Проверки, протоколи и записи за качество.",
  }],
  mappings: [{
    item_id: "item-quality",
    item_number: "7",
    item_title: "Мерки за осигуряване на качеството",
    selected_section_id: "section-quality",
    candidates: [{
      section_id: "section-quality",
      score: 0.82,
      reason: "Общи понятия: качество, контрол",
    }],
  }],
};

describe("ForlagePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.forlage.get).mockResolvedValue(emptyWorkspace);
  });

  it("analyzes hierarchy and allows excluding an unsuitable match", async () => {
    vi.mocked(api.forlage.analyze).mockResolvedValue(analyzedWorkspace);
    vi.mocked(api.forlage.updateLink).mockResolvedValue({
      ...analyzedWorkspace,
      mapped_count: 0,
      mappings: [{ ...analyzedWorkspace.mappings[0], selected_section_id: null }],
    });
    vi.mocked(api.forlage.confirm).mockResolvedValue({
      ...analyzedWorkspace,
      mapped_count: 0,
      review_confirmed: true,
      mappings: [{ ...analyzedWorkspace.mappings[0], selected_section_id: null }],
    });

    render(<ForlagePanel projectId="project-1" />);

    await userEvent.click(await screen.findByTestId("forlage-analyze-button"));
    expect(await screen.findByTestId("forlage-summary")).toHaveTextContent("1 йерархични раздела");
    expect(screen.getByText("Мерки за осигуряване на качеството")).toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByLabelText("Форлаге за 7 Мерки за осигуряване на качеството"),
      "",
    );

    await waitFor(() => {
      expect(api.forlage.updateLink).toHaveBeenCalledWith(
        "project-1",
        "item-quality",
        null,
      );
    });
    await userEvent.click(screen.getByTestId("forlage-confirm-button"));
    await waitFor(() => expect(api.forlage.confirm).toHaveBeenCalledWith("project-1"));
  });
});
