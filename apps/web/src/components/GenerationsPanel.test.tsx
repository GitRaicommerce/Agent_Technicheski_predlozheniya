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
        regenerateQualityGenerationJob: vi.fn(),
        regenerateMissingRequirementsGenerationJob: vi.fn(),
        regenerateSection: vi.fn(),
        resolveDuplicateSelectedGenerations: vi.fn(),
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
const regenerateQualityGenerationJobMock = vi.mocked(
  api.agents.regenerateQualityGenerationJob,
);
const regenerateMissingRequirementsGenerationJobMock = vi.mocked(
  api.agents.regenerateMissingRequirementsGenerationJob,
);
const regenerateSectionMock = vi.mocked(api.agents.regenerateSection);
const resolveDuplicateSelectedGenerationsMock = vi.mocked(
  api.agents.resolveDuplicateSelectedGenerations,
);
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
                    reason: "missing distinctive requirement detail",
                    reasons: [
                      "missing distinctive requirement detail",
                      "needs execution action",
                      "needs coherent passage",
                    ],
                    matched_ratio: 0.8,
                    coherent_matched_ratio: 0.75,
                    operational_signals: ["record"],
                    operational_execution_signals: [],
                    required_operational_signal_count: 2,
                    required_operational_execution_signal_count: 1,
                    distinctive_terms: ["final", "acceptance", "handover"],
                    distinctive_matches: [],
                    required_distinctive_count: 1,
                    remediation_guidance:
                      "Regenerate or edit this section with final acceptance and handover details.",
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
    expect(screen.getByText("липсва отличителен детайл"))
      .toBeInTheDocument();
    expect(screen.getByText("липсва изпълнителско действие"))
      .toBeInTheDocument();
    expect(
      screen.getByText(
        "термини 80% · свързаност 75% · оперативни сигнали 1/2 · изпълнителски действия 0/1 · отличителни детайли 0/1 · отличаващи: final, acceptance, handover",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Поправка: Regenerate or edit this section with final acceptance and handover details.",
      ),
    ).toBeInTheDocument();
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

  it("resolves duplicate selected generations by keeping the newest selected variants", async () => {
    listGenerationsMock
      .mockResolvedValueOnce([
        {
          section_uid: "sec-duplicate-a",
          section_title: "Duplicate Section A",
          variants: [
            {
              id: "gen-a-old",
              section_uid: "sec-duplicate-a",
              variant: 1,
              text: "Older selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-20T10:00:00.000Z",
            },
            {
              id: "gen-a-new",
              section_uid: "sec-duplicate-a",
              variant: 2,
              text: "Newer selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-21T10:00:00.000Z",
            },
          ],
        },
        {
          section_uid: "sec-duplicate-b",
          section_title: "Duplicate Section B",
          variants: [
            {
              id: "gen-b-v1",
              section_uid: "sec-duplicate-b",
              variant: 1,
              text: "Variant one selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-22T10:00:00.000Z",
            },
            {
              id: "gen-b-v3",
              section_uid: "sec-duplicate-b",
              variant: 3,
              text: "Variant three selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-22T10:00:00.000Z",
            },
          ],
        },
      ])
      .mockResolvedValueOnce([
        {
          section_uid: "sec-duplicate-a",
          section_title: "Duplicate Section A",
          variants: [
            {
              id: "gen-a-new",
              section_uid: "sec-duplicate-a",
              variant: 2,
              text: "Newer selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-21T10:00:00.000Z",
            },
          ],
        },
        {
          section_uid: "sec-duplicate-b",
          section_title: "Duplicate Section B",
          variants: [
            {
              id: "gen-b-v3",
              section_uid: "sec-duplicate-b",
              variant: 3,
              text: "Variant three selected text",
              evidence_status: "ok",
              selected: true,
              created_at: "2026-04-22T10:00:00.000Z",
            },
          ],
        },
      ]);
    resolveDuplicateSelectedGenerationsMock.mockResolvedValue({
      status: "resolved",
      resolved_count: 2,
      sections: [
        {
          section_uid: "sec-duplicate-a",
          generation_id: "gen-a-new",
          previous_selected_count: 2,
        },
        {
          section_uid: "sec-duplicate-b",
          generation_id: "gen-b-v3",
          previous_selected_count: 2,
        },
      ],
    });

    render(<GenerationsPanel projectId="project-1" />);

    expect(await screen.findByTestId("generation-attention-summary"))
      .toHaveTextContent("дублиран избор: 2");

    await userEvent.click(
      screen.getByTestId("generation-resolve-duplicates-latest-button"),
    );

    await waitFor(() => {
      expect(resolveDuplicateSelectedGenerationsMock).toHaveBeenCalledWith(
        "project-1",
      );
    });
    expect(selectGenerationMock).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
    expect(
      screen.queryByTestId("generation-resolve-duplicates-latest-button"),
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

  it("summarizes and filters sections that need generation attention", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-clean",
        section_title: "Clean Section",
        variants: [
          {
            id: "gen-clean",
            section_uid: "sec-clean",
            variant: 1,
            text: "Clean text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
            flags_json: {
              requirement_coverage: {
                total: 1,
                covered: 1,
                missing: 0,
                items: [
                  {
                    id: "req-clean",
                    text: "Clean requirement",
                    status: "covered",
                  },
                ],
              },
            },
          },
        ],
      },
      {
        section_uid: "sec-quality",
        section_title: "Quality Review Section",
        variants: [
          {
            id: "gen-quality",
            section_uid: "sec-quality",
            variant: 1,
            text: "Short but otherwise clean text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
            flags_json: {
              requirement_coverage: {
                total: 1,
                covered: 1,
                missing: 0,
                items: [
                  {
                    id: "req-quality",
                    text: "Quality requirement",
                    status: "covered",
                  },
                ],
              },
            },
          },
        ],
      },
      {
        section_uid: "sec-duplicate",
        section_title: "Duplicate Section",
        variants: [
          {
            id: "gen-duplicate-1",
            section_uid: "sec-duplicate",
            variant: 1,
            text: "First duplicate text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
          },
          {
            id: "gen-duplicate-2",
            section_uid: "sec-duplicate",
            variant: 2,
            text: "Second duplicate text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-21T10:00:00.000Z",
          },
        ],
      },
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
      {
        section_uid: "sec-missing",
        section_title: "Missing Requirement Section",
        variants: [
          {
            id: "gen-missing",
            section_uid: "sec-missing",
            variant: 1,
            text: "Text without one requirement",
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

    render(
      <GenerationsPanel
        projectId="project-1"
        qualityAttentionSectionUids={["sec-quality"]}
        qualityAttentionSections={[
          {
            section_uid: "sec-quality",
            word_count: 180,
            min_words: 1400,
            sentence_count: 3,
            min_sentences: 10,
            blueprint_group_count: 5,
            blueprint_topic_count: 6,
            blueprint_requirement_id_count: 11,
            suggested_words_per_structure: 280,
            structure_coverage: {
              anchor_count: 4,
              covered_count: 1,
              required_count: 3,
              missing: [
                {
                  label: "waste segregation",
                  terms: ["waste", "segregation"],
                  matched_terms: ["waste"],
                  required_terms: 2,
                },
                {
                  label: "soil protection",
                  terms: ["soil", "protection"],
                  matched_terms: ["protection"],
                  required_terms: 2,
                },
              ],
            },
            issues: [{ code: "repetitive_content" }],
          },
        ]}
      />,
    );

    const summary = await screen.findByTestId("generation-attention-summary");
    expect(summary).toHaveTextContent("4 секции изискват внимание");
    expect(summary).toHaveTextContent("дублиран избор: 1");
    expect(summary).toHaveTextContent("остарели избрани: 1");
    expect(summary).toHaveTextContent("липсващи изисквания: 1");
    expect(summary).toHaveTextContent("кратки секции: 1");
    expect(screen.getByTestId("generation-section-sec-clean")).toBeInTheDocument();
    expect(screen.getByTestId("generation-quality-attention-badge-sec-quality"))
      .toHaveTextContent("кратка");
    expect(screen.getByTestId("generation-stale-selected-badge-sec-stale"))
      .toHaveTextContent("остаряла");

    await userEvent.click(
      screen.getByTestId("generation-attention-filter-toggle"),
    );

    expect(screen.queryByTestId("generation-section-sec-clean"))
      .not.toBeInTheDocument();
    expect(screen.getByTestId("generation-section-sec-duplicate"))
      .toBeInTheDocument();
    expect(screen.getByTestId("generation-section-sec-stale"))
      .toBeInTheDocument();
    expect(screen.getByTestId("generation-section-sec-missing"))
      .toBeInTheDocument();
    expect(screen.getByTestId("generation-section-sec-quality"))
      .toBeInTheDocument();
    expect(screen.getByText("4 / 5 секции")).toBeInTheDocument();
    expect(screen.getByTestId("generation-attention-filter-toggle"))
      .toHaveTextContent("Покажи всички");

    await userEvent.click(screen.getByTestId("generation-section-sec-quality"));

    expect(await screen.findByTestId("generation-quality-depth-sec-quality"))
      .toHaveTextContent("180/1400 думи");
    expect(screen.getByTestId("generation-quality-depth-sec-quality"))
      .toHaveTextContent("280 думи на група/тема");
    expect(screen.getByTestId("generation-quality-depth-sec-quality"))
      .toHaveTextContent("1/3 покрити групи/теми");
    expect(screen.getByTestId("generation-quality-depth-sec-quality"))
      .toHaveTextContent("11 checklist id");
    expect(screen.getByTestId("generation-quality-depth-sec-quality"))
      .toHaveTextContent(
        "waste segregation (1/2: waste), soil protection (1/2: protection)",
      );
    expect(screen.getByTestId("generation-quality-depth-sec-quality"))
      .toHaveTextContent("РїРѕРІС‚Р°СЂСЏС‰ СЃРµ С‚РµРєСЃС‚");
  });

  it("focuses the attention filter when requested by export remediation", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-clean",
        section_title: "Clean Section",
        variants: [
          {
            id: "gen-clean",
            section_uid: "sec-clean",
            variant: 1,
            text: "Clean text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
          },
        ],
      },
      {
        section_uid: "sec-duplicate",
        section_title: "Duplicate Section",
        variants: [
          {
            id: "gen-duplicate-1",
            section_uid: "sec-duplicate",
            variant: 1,
            text: "First duplicate text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
          },
          {
            id: "gen-duplicate-2",
            section_uid: "sec-duplicate",
            variant: 2,
            text: "Second duplicate text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-21T10:00:00.000Z",
          },
        ],
      },
    ]);

    render(<GenerationsPanel projectId="project-1" focusAttentionKey={1} />);

    expect(await screen.findByTestId("generation-attention-summary"))
      .toHaveTextContent("1 секция изисква внимание");
    await waitFor(() => {
      expect(screen.queryByTestId("generation-section-sec-clean"))
        .not.toBeInTheDocument();
    });
    expect(screen.getByTestId("generation-section-sec-duplicate"))
      .toBeInTheDocument();
    expect(screen.getByTestId("generation-attention-filter-toggle"))
      .toHaveTextContent("Покажи всички");
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
      .toHaveTextContent("1 остаряла избрана секция");
    expect(screen.getByTestId("generation-stale-regenerate-button"))
      .toHaveTextContent("Регенерирай");

    await userEvent.click(screen.getByTestId("generation-stale-regenerate-button"));

    await waitFor(() => {
      expect(regenerateStaleGenerationJobMock).toHaveBeenCalledWith("project-1");
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
  });

  it("starts a quality selected sections generation job", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-quality",
        section_title: "Quality Section",
        variants: [
          {
            id: "gen-quality",
            section_uid: "sec-quality",
            variant: 1,
            text: "Short text",
            evidence_status: "ok",
            selected: true,
            created_at: "2026-04-20T10:00:00.000Z",
          },
        ],
      },
    ]);
    regenerateQualityGenerationJobMock.mockResolvedValue({
      id: "job-quality",
      project_id: "project-1",
      job_type: "drafting_quality",
      status: "queued",
      total_sections: 1,
      completed_sections: 0,
      skipped_sections: 0,
      current_section_uid: null,
      current_section_title: null,
      error: null,
      result_json: {
        target_section_uids: ["sec-quality"],
        target_reason: "quality_review",
      },
      trace_id: "trace-quality",
      created_at: "2026-04-20T10:02:00.000Z",
      updated_at: "2026-04-20T10:02:00.000Z",
      completed_at: null,
    });

    render(
      <GenerationsPanel
        projectId="project-1"
        qualityAttentionSectionUids={["sec-quality"]}
      />,
    );

    expect(await screen.findByTestId("generation-quality-selected-action"))
      .toHaveTextContent("1 секция с недостатъчна детайлност");
    expect(screen.getByTestId("generation-quality-regenerate-button"))
      .toHaveTextContent("Регенерирай подробно");

    await userEvent.click(
      screen.getByTestId("generation-quality-regenerate-button"),
    );

    await waitFor(() => {
      expect(regenerateQualityGenerationJobMock).toHaveBeenCalledWith(
        "project-1",
      );
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
  });

  it("starts a missing requirements generation job", async () => {
    listGenerationsMock.mockResolvedValue([
      {
        section_uid: "sec-missing",
        section_title: "Missing Requirement Section",
        variants: [
          {
            id: "gen-missing",
            section_uid: "sec-missing",
            variant: 1,
            text: "Text without one requirement",
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
    regenerateMissingRequirementsGenerationJobMock.mockResolvedValue({
      id: "job-missing",
      project_id: "project-1",
      job_type: "drafting_requirements",
      status: "queued",
      total_sections: 1,
      completed_sections: 0,
      skipped_sections: 0,
      current_section_uid: null,
      current_section_title: null,
      error: null,
      result_json: {
        target_section_uids: ["sec-missing"],
        target_reason: "missing_requirements",
      },
      trace_id: "trace-missing",
      created_at: "2026-04-20T10:02:00.000Z",
      updated_at: "2026-04-20T10:02:00.000Z",
      completed_at: null,
    });

    render(<GenerationsPanel projectId="project-1" />);

    expect(await screen.findByTestId("generation-missing-requirements-action"))
      .toHaveTextContent("1 секция с непокрити изисквания");
    expect(screen.getByTestId("generation-missing-requirements-regenerate-button"))
      .toHaveTextContent("Регенерирай покритието");

    await userEvent.click(
      screen.getByTestId("generation-missing-requirements-regenerate-button"),
    );

    await waitFor(() => {
      expect(
        regenerateMissingRequirementsGenerationJobMock,
      ).toHaveBeenCalledWith("project-1");
    });
    await waitFor(() => {
      expect(listGenerationsMock).toHaveBeenCalledTimes(2);
    });
  });
});
