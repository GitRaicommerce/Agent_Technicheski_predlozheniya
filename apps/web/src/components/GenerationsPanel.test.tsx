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
        latestGenerationJob: vi.fn(),
        retryGenerationJob: vi.fn(),
        regenerateStaleGenerationJob: vi.fn(),
        regenerateSection: vi.fn(),
        selectGeneration: vi.fn(),
      },
    },
  };
});

const listGenerationsMock = vi.mocked(api.agents.listGenerations);
const latestGenerationJobMock = vi.mocked(api.agents.latestGenerationJob);
const retryGenerationJobMock = vi.mocked(api.agents.retryGenerationJob);
const regenerateStaleGenerationJobMock = vi.mocked(
  api.agents.regenerateStaleGenerationJob,
);
const regenerateSectionMock = vi.mocked(api.agents.regenerateSection);
const selectGenerationMock = vi.mocked(api.agents.selectGeneration);

describe("GenerationsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    latestGenerationJobMock.mockResolvedValue(null);
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

  it("shows requirement coverage for the selected generation", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-coverage",
        section_title: "Coverage Section",
        variants: [
          {
            id: "gen-coverage",
            section_uid: "sec-coverage",
            variant: 1,
            text: "Generated text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
            flags_json: {
              requirement_coverage: {
                total: 2,
                covered: 1,
                missing: 1,
                missing_ids: ["req-missing"],
                items: [
                  {
                    id: "req-covered",
                    text: "Covered requirement",
                    status: "covered",
                  },
                  {
                    id: "req-missing",
                    text: "Missing requirement",
                    status: "missing",
                  },
                ],
              },
            },
          },
        ],
      },
    ]);

    render(<GenerationsPanel projectId="project-1" />);

    expect(await screen.findByTestId("generation-requirement-coverage"))
      .toHaveTextContent("1/2");

    await userEvent.click(
      await screen.findByRole("button", { name: /Coverage Section/i }),
    );

    expect(
      await screen.findByTestId("generation-requirement-coverage-sec-coverage"),
    ).toHaveTextContent("1 липсват");
    expect(screen.getByText(/req-missing/)).toBeInTheDocument();
    expect(screen.getByText(/Missing requirement/)).toBeInTheDocument();
  });

  it("selects one variant to resolve duplicate selected generations", async () => {
    listGenerationsMock
      .mockResolvedValueOnce([
        {
          section_uid: "sec-duplicate",
          section_title: "Duplicate Section",
          variants: [
            {
              id: "gen-1",
              section_uid: "sec-duplicate",
              variant: 1,
              text: "First selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-20T10:00:00.000Z",
            },
            {
              id: "gen-2",
              section_uid: "sec-duplicate",
              variant: 2,
              text: "Second selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-21T10:00:00.000Z",
            },
          ],
        },
      ])
      .mockResolvedValueOnce([
        {
          section_uid: "sec-duplicate",
          section_title: "Duplicate Section",
          variants: [
            {
              id: "gen-2",
              section_uid: "sec-duplicate",
              variant: 2,
              text: "Second selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-21T10:00:00.000Z",
            },
            {
              id: "gen-1",
              section_uid: "sec-duplicate",
              variant: 1,
              text: "First selected text",
              evidence_status: "ok",
              selected: false,
              created_at: "2026-04-20T10:00:00.000Z",
            },
          ],
        },
      ]);
    selectGenerationMock.mockResolvedValue({
      status: "selected",
      generation_id: "gen-2",
    });

    render(<GenerationsPanel projectId="project-1" />);

    await userEvent.click(
      await screen.findByRole("button", { name: /Duplicate Section/i }),
    );

    expect(
      await screen.findByTestId(
        "generation-duplicate-selected-warning-sec-duplicate",
      ),
    ).toHaveTextContent("2 selected variants");

    await userEvent.click(await screen.findByTestId("generation-select-gen-2"));

    await waitFor(() => {
      expect(selectGenerationMock).toHaveBeenCalledWith("project-1", "gen-2");
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
    expect(
      screen.queryByTestId("generation-duplicate-selected-warning-sec-duplicate"),
    ).not.toBeInTheDocument();
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

  it("shows progress for an active all-sections generation job", async () => {
    listGenerationsMock.mockResolvedValue([]);
    latestGenerationJobMock.mockResolvedValue({
      id: "job-1",
      project_id: "project-1",
      job_type: "drafting_all",
      status: "processing",
      total_sections: 4,
      completed_sections: 1,
      skipped_sections: 1,
      current_section_uid: "sec-2",
      current_section_title: "Section 2",
      error: null,
      result_json: null,
      trace_id: "trace-1",
      created_at: "2026-04-20T10:00:00.000Z",
      updated_at: "2026-04-20T10:01:00.000Z",
      completed_at: null,
    });

    render(<GenerationsPanel projectId="project-1" />);

    expect(await screen.findByTestId("generation-job-progress")).toHaveTextContent(
      "2 / 4",
    );
    expect(screen.getByText("Section 2")).toBeInTheDocument();
  });

  it("retries a failed all-sections generation job", async () => {
    listGenerationsMock.mockResolvedValue([]);
    latestGenerationJobMock.mockResolvedValue({
      id: "job-1",
      project_id: "project-1",
      job_type: "drafting_all",
      status: "error",
      total_sections: 4,
      completed_sections: 2,
      skipped_sections: 1,
      current_section_uid: null,
      current_section_title: null,
      error: "Connection error.",
      result_json: {
        sections: [],
        failed_sections: [{ section_uid: "sec-4", title: "Section 4" }],
      },
      trace_id: "trace-1",
      created_at: "2026-04-20T10:00:00.000Z",
      updated_at: "2026-04-20T10:01:00.000Z",
      completed_at: "2026-04-20T10:01:00.000Z",
    });
    retryGenerationJobMock.mockResolvedValue({
      id: "job-2",
      project_id: "project-1",
      job_type: "drafting_all",
      status: "queued",
      total_sections: 0,
      completed_sections: 0,
      skipped_sections: 0,
      current_section_uid: null,
      current_section_title: null,
      error: null,
      result_json: null,
      trace_id: "trace-2",
      created_at: "2026-04-20T10:02:00.000Z",
      updated_at: "2026-04-20T10:02:00.000Z",
      completed_at: null,
    });

    render(<GenerationsPanel projectId="project-1" />);

    await userEvent.click(await screen.findByTestId("generation-job-retry-button"));

    await waitFor(() => {
      expect(retryGenerationJobMock).toHaveBeenCalledWith("project-1");
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
  });

  it("starts a stale selected sections generation job", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-stale",
        section_title: "Stale Section",
        variants: [
          {
            id: "gen-stale",
            section_uid: "sec-stale",
            variant: 1,
            text: "Stale text",
            evidence_status: "stale",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
          },
        ],
      },
    ]);
    regenerateStaleGenerationJobMock.mockResolvedValue({
      id: "job-stale",
      project_id: "project-1",
      job_type: "drafting_stale",
      status: "queued",
      total_sections: 1,
      completed_sections: 0,
      skipped_sections: 0,
      current_section_uid: null,
      current_section_title: null,
      error: null,
      result_json: {
        target_section_uids: ["sec-stale"],
        target_reason: "stale_selected",
      },
      trace_id: "trace-stale",
      created_at: "2026-04-20T10:02:00.000Z",
      updated_at: "2026-04-20T10:02:00.000Z",
      completed_at: null,
    });

    render(<GenerationsPanel projectId="project-1" />);

    expect(await screen.findByTestId("generation-stale-selected-action"))
      .toHaveTextContent("1 selected stale section");

    await userEvent.click(screen.getByTestId("generation-stale-regenerate-button"));

    await waitFor(() => {
      expect(regenerateStaleGenerationJobMock).toHaveBeenCalledWith("project-1");
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
  });
});
