import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConsistencyPanel from "./ConsistencyPanel";
import CriteriaPanel from "./CriteriaPanel";
import { api, type ConsistencyJob, type CriteriaWorkspace } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      criteria: { ...actual.api.criteria, get: vi.fn(), start: vi.fn() },
      consistency: { ...actual.api.consistency, getLatest: vi.fn(), start: vi.fn(), report: vi.fn() },
    },
  };
});

const check = (id: string, verdict: string, current: boolean) => ({
  id,
  generation_id: `gen-${id}`,
  section_uid: "abcdef0123456789",
  criterion_id: `c-${id}`,
  criterion_text: `Критерий ${id}`,
  criterion_kind: "content",
  verdict,
  created_at: "2026-09-30T10:00:00Z",
  is_current: current,
  generation_revision: current ? 4 : 2,
});

describe("verification panels show only current results (K-15)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hides verdicts of versions that are no longer selected and shows section + version", async () => {
    const workspace: CriteriaWorkspace = {
      enabled: true,
      checks: [check("old", "missing", false), check("new", "partial", true)],
      totals: { total: 1, stale: 1, partial: 1 },
      latest_job: null,
    };
    vi.mocked(api.criteria.get).mockResolvedValue(workspace);
    render(<CriteriaPanel projectId="p1" />);

    expect(await screen.findByText("Критерий new")).toBeInTheDocument();
    expect(screen.queryByText("Критерий old")).not.toBeInTheDocument();
    expect(screen.getByTestId("criteria-stale")).toHaveTextContent("1 по-стари проверки");
    expect(screen.getByText("раздел abcdef01 · версия 4")).toBeInTheDocument();
  });

  it("does not present a stale consistency report as current", async () => {
    const job: ConsistencyJob = {
      id: "job-1",
      project_id: "p1",
      status: "done",
      total_sections: 2,
      completed_sections: 2,
      result_json: { checked_section_count: 2, critical_count: 0, warning_count: 0, conflicts: [] },
      created_at: "2026-09-30T10:00:00Z",
      updated_at: "2026-09-30T10:00:00Z",
      stale: true,
      stale_reasons: ["generation_set_changed"],
    };
    vi.mocked(api.consistency.getLatest).mockResolvedValue(job);
    render(<ConsistencyPanel projectId="p1" />);

    expect(await screen.findByTestId("consistency-stale")).toHaveTextContent("текстовете са променени");
    expect(screen.queryByText("без противоречия")).not.toBeInTheDocument();
    expect(screen.queryByTestId("consistency-summary")).not.toBeInTheDocument();
  });
});
