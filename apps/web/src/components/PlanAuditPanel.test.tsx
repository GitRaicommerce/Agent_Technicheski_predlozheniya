import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PlanAuditPanel from "./PlanAuditPanel";
import { api, type PlanAuditState } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      planAudit: { get: vi.fn(), start: vi.fn(), resolve: vi.fn() },
      contentPlan: { ...actual.api.contentPlan, startAuthor: vi.fn() },
    },
  };
});

const changesRequired: PlanAuditState = {
  audit: {
    id: "audit-1",
    status: "done",
    overall: "changes_required",
    stale: false,
    created_at: "2026-09-25T10:00:00Z",
    report: {
      coverage: { complete: true },
      inventory: {
        obligations: [
          { id: "A1", quote: "да опише мерките за проверка на сертификатите", text: "Сертификати", page: 4 },
        ],
      },
      findings: [{ inventory_id: "A1", plan_item_ids: [], verdict: "missing", required_correction: "Добави подточка" }],
      plan_additions: [{ plan_item_id: "i2", verdict: "unsupported_addition", rationale: "Няма източник" }],
      plan_snapshot: [{ id: "i2", number: "3", title: "Безплатна поддръжка" }],
      resolutions: {},
      summary: { obligations: 1, findings: {}, unsupported_additions: 1, unanswered: 0, resolved_by_human: 0 },
    },
  },
  eligibility: { eligible: false, reason: "changes_required", message: "Одитът изисква корекции." },
};

describe("PlanAuditPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists the exact gaps with source quote and page, and blocks drafting", async () => {
    vi.mocked(api.planAudit.get).mockResolvedValue(changesRequired);
    render(<PlanAuditPanel projectId="p1" />);

    const findings = await screen.findByTestId("plan-audit-findings");
    expect(findings).toHaveTextContent("да опише мерките за проверка на сертификатите");
    expect(findings).toHaveTextContent("стр. 4");
    expect(findings).toHaveTextContent("няма получател");
    expect(findings).toHaveTextContent("3 Безплатна поддръжка");
    expect(screen.getByTestId("plan-audit-eligibility")).toHaveTextContent("блокирано");
  });

  it("starts a bounded correction by the author from this audit", async () => {
    vi.mocked(api.planAudit.get).mockResolvedValue(changesRequired);
    vi.mocked(api.contentPlan.startAuthor).mockResolvedValue({ id: "job", status: "queued", created_at: "" });
    render(<PlanAuditPanel projectId="p1" />);

    await userEvent.click(await screen.findByTestId("plan-audit-correct"));

    expect(api.contentPlan.startAuthor).toHaveBeenCalledWith("p1", "audit-1");
  });

  it("records a human resolution only with an interpretation and a reason", async () => {
    vi.mocked(api.planAudit.get).mockResolvedValue(changesRequired);
    vi.mocked(api.planAudit.resolve).mockResolvedValue({});
    render(<PlanAuditPanel projectId="p1" />);

    const item = await screen.findByTestId("plan-audit-finding:A1");
    const button = item.querySelector("button")!;
    expect(button).toBeDisabled();
    const [interpretation, reason] = Array.from(item.querySelectorAll("input"));
    await userEvent.type(interpretation, "Отнася се за позиция 2");
    await userEvent.type(reason, "Разяснение №3 от възложителя");
    await userEvent.click(button);

    await waitFor(() =>
      expect(api.planAudit.resolve).toHaveBeenCalledWith("p1", "audit-1", {
        key: "finding:A1",
        interpretation: "Отнася се за позиция 2",
        reason: "Разяснение №3 от възложителя",
      }),
    );
  });

  it("shows a stale audit as stale and hides its old findings", async () => {
    vi.mocked(api.planAudit.get).mockResolvedValue({
      ...changesRequired,
      audit: { ...changesRequired.audit!, overall: "stale", stale: true },
      eligibility: { eligible: false, reason: "stale", message: "Одитът е остарял." },
    });
    render(<PlanAuditPanel projectId="p1" />);

    expect(await screen.findByTestId("plan-audit-overall")).toHaveTextContent("Остарял");
    expect(screen.queryByTestId("plan-audit-findings")).not.toBeInTheDocument();
  });
});
