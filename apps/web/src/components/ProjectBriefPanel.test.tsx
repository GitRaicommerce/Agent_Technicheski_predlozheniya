import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectBriefPanel from "./ProjectBriefPanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projects: { ...actual.api.projects, getBrief: vi.fn(), saveBrief: vi.fn() },
    },
  };
});

describe("ProjectBriefPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.projects.getBrief).mockResolvedValue({
      project_id: "p1",
      version: 1,
      content: "Не включвай част Електро.",
    });
  });

  it("saves an explicit new version", async () => {
    vi.mocked(api.projects.saveBrief).mockResolvedValue({
      project_id: "p1",
      version: 2,
      content: "Не включвай части Електро и ОВК.",
    });
    render(<ProjectBriefPanel projectId="p1" />);

    const input = await screen.findByTestId("project-brief-input");
    await waitFor(() => expect(input).toHaveValue("Не включвай част Електро."));
    await userEvent.clear(input);
    await userEvent.type(input, "Не включвай части Електро и ОВК.");
    await userEvent.click(screen.getByTestId("project-brief-save"));

    expect(api.projects.saveBrief).toHaveBeenCalledWith("p1", "Не включвай части Електро и ОВК.");
    expect(await screen.findByText(/Версия 2/)).toBeInTheDocument();
  });

  it("keeps the unsaved text when saving fails", async () => {
    vi.mocked(api.projects.saveBrief).mockRejectedValue(new Error("мрежова грешка"));
    render(<ProjectBriefPanel projectId="p1" />);

    const input = await screen.findByTestId("project-brief-input");
    await waitFor(() => expect(input).toHaveValue("Не включвай част Електро."));
    await userEvent.type(input, " Ново.");
    await userEvent.click(screen.getByTestId("project-brief-save"));

    expect(await screen.findByText("мрежова грешка")).toBeInTheDocument();
    expect(input).toHaveValue("Не включвай част Електро. Ново.");
  });
});
