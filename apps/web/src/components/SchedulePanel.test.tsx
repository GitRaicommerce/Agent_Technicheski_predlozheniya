import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SchedulePanel from "./SchedulePanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      agents: {
        ...actual.api.agents,
        getSchedule: vi.fn(),
        lockSchedule: vi.fn(),
        unlockSchedule: vi.fn(),
      },
    },
  };
});

const getScheduleMock = vi.mocked(api.agents.getSchedule);
const lockScheduleMock = vi.mocked(api.agents.lockSchedule);
const unlockScheduleMock = vi.mocked(api.agents.unlockSchedule);

describe("SchedulePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when schedule is not uploaded yet", async () => {
    getScheduleMock.mockResolvedValue(null);

    render(<SchedulePanel projectId="project-1" />);

    expect(
      await screen.findByRole("button", { name: /Опресни/i }),
    ).toBeInTheDocument();
  });

  it("renders schedule summary and task list", async () => {
    getScheduleMock.mockResolvedValue({
      id: "schedule-1",
      schedule_json: {
        tasks: [{ uid: "1", wbs: "1", name: "Task One", duration_days: 5 }],
        resources: [{ id: "r1", name: "Resource One" }],
      },
      status_locked: false,
      version: 1,
    });

    render(<SchedulePanel projectId="project-1" />);

    expect(await screen.findByText(/1 задачи/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Покажи задачите/i }));
    expect(await screen.findByText("Task One")).toBeInTheDocument();
  });

  it("locks and unlocks a schedule", async () => {
    getScheduleMock.mockResolvedValue({
      id: "schedule-1",
      schedule_json: {
        tasks: [],
        resources: [],
      },
      status_locked: false,
      version: 1,
    });
    lockScheduleMock.mockResolvedValue({ status: "locked", schedule_id: "schedule-1" });
    unlockScheduleMock.mockResolvedValue({ status: "unlocked", schedule_id: "schedule-1" });

    render(<SchedulePanel projectId="project-1" />);

    const approveButton = await screen.findByRole("button", { name: /Одобри графика/i });
    await userEvent.click(approveButton);

    await waitFor(() => {
      expect(lockScheduleMock).toHaveBeenCalledWith("project-1", "schedule-1");
    });

    const unlockButton = await screen.findByRole("button", { name: /Отключи/i });
    await userEvent.click(unlockButton);

    await waitFor(() => {
      expect(unlockScheduleMock).toHaveBeenCalledWith("project-1", "schedule-1");
    });
  });
});
