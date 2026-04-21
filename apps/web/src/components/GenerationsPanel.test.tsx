import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import GenerationsPanel from "./GenerationsPanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      agents: {
        ...actual.api.agents,
        listGenerations: vi.fn(),
        regenerateSection: vi.fn(),
      },
    },
  };
});

const listGenerationsMock = vi.mocked(api.agents.listGenerations);
const regenerateSectionMock = vi.mocked(api.agents.regenerateSection);

describe("GenerationsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when there are no generations", async () => {
    listGenerationsMock.mockResolvedValue([]);

    render(<GenerationsPanel projectId="project-1" />);

    expect(await screen.findByRole("button")).toBeInTheDocument();
    expect(screen.queryByText("Section 1")).not.toBeInTheDocument();
  });

  it("renders a section and expands its selected text", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-1",
        section_title: "Section 1",
        variants: [
          {
            id: "gen-1",
            section_uid: "sec-1",
            variant: 1,
            text: "Selected generation text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
          },
        ],
      },
    ]);

    render(<GenerationsPanel projectId="project-1" />);

    const sectionButton = await screen.findByRole("button", { name: /Section 1/i });
    await userEvent.click(sectionButton);

    expect(await screen.findByText("Selected generation text")).toBeInTheDocument();
  });

  it("regenerates a section and reloads the list", async () => {
    listGenerationsMock
      .mockResolvedValueOnce([
        {
          section_uid: "sec-1",
          section_title: "Section 1",
          variants: [
            {
              id: "gen-1",
              section_uid: "sec-1",
              variant: 1,
              text: "Old text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-20T10:00:00.000Z",
            },
          ],
        },
      ])
      .mockResolvedValueOnce([
        {
          section_uid: "sec-1",
          section_title: "Section 1",
          variants: [
            {
              id: "gen-2",
              section_uid: "sec-1",
              variant: 2,
              text: "New text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-21T10:00:00.000Z",
            },
          ],
        },
      ]);
    regenerateSectionMock.mockResolvedValue({
      generation_ids: { variant_1: "gen-2" },
      trace_id: "trace-1",
    });

    const { container } = render(<GenerationsPanel projectId="project-1" />);

    await screen.findByText("Section 1");
    const titledButtons = container.querySelectorAll("button[title]");
    const regenerateButton = titledButtons[1];
    await userEvent.click(regenerateButton!);

    await waitFor(() => {
      expect(regenerateSectionMock).toHaveBeenCalledWith("project-1", "sec-1");
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
  });
});
