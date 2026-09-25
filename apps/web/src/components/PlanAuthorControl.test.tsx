import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PlanAuthorControl from "./PlanAuthorControl";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      contentPlan: {
        ...actual.api.contentPlan,
        startAuthor: vi.fn(),
        latestAuthorJob: vi.fn(),
      },
    },
  };
});

describe("PlanAuthorControl", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows validation errors and states that the plan is unchanged", async () => {
    vi.mocked(api.contentPlan.latestAuthorJob).mockResolvedValue({
      id: "job-1",
      status: "error",
      error: "Моделното предложение е отхвърлено при валидация.",
      result_json: { validation_errors: ["Моделът се опита да промени съществуващи точки"] },
      created_at: "2026-09-25T10:00:00Z",
    });
    render(<PlanAuthorControl projectId="p1" disabled={false} onApplied={() => {}} />);

    const box = await screen.findByTestId("plan-author-error");
    expect(box).toHaveTextContent("промени съществуващи точки");
    expect(box).toHaveTextContent("Текущият план не е променен");
  });

  it("does not refetch on every parent render", async () => {
    vi.mocked(api.contentPlan.latestAuthorJob).mockResolvedValue(null);
    const { rerender } = render(
      <PlanAuthorControl projectId="p1" disabled={false} onApplied={() => {}} />,
    );
    await waitFor(() => expect(api.contentPlan.latestAuthorJob).toHaveBeenCalledTimes(1));
    rerender(<PlanAuthorControl projectId="p1" disabled={false} onApplied={() => {}} />);
    rerender(<PlanAuthorControl projectId="p1" disabled={false} onApplied={() => {}} />);
    expect(api.contentPlan.latestAuthorJob).toHaveBeenCalledTimes(1);
  });

  it("starts the author job explicitly", async () => {
    vi.mocked(api.contentPlan.latestAuthorJob).mockResolvedValue(null);
    vi.mocked(api.contentPlan.startAuthor).mockResolvedValue({
      id: "job-2",
      status: "queued",
      created_at: "2026-09-25T10:00:00Z",
    });
    render(<PlanAuthorControl projectId="p1" disabled={false} onApplied={() => {}} />);

    await userEvent.click(await screen.findByTestId("plan-author-start"));

    expect(api.contentPlan.startAuthor).toHaveBeenCalledWith("p1");
    expect(await screen.findByText(/Моделът предлага подробен план/)).toBeInTheDocument();
  });
});
