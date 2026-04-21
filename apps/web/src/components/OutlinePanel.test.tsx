import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OutlinePanel from "./OutlinePanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      agents: {
        ...actual.api.agents,
        getOutline: vi.fn(),
        lockOutline: vi.fn(),
        unlockOutline: vi.fn(),
        deleteOutline: vi.fn(),
      },
    },
  };
});

const getOutlineMock = vi.mocked(api.agents.getOutline);
const lockOutlineMock = vi.mocked(api.agents.lockOutline);
const unlockOutlineMock = vi.mocked(api.agents.unlockOutline);
const deleteOutlineMock = vi.mocked(api.agents.deleteOutline);

describe("OutlinePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders load error state when outline request fails", async () => {
    getOutlineMock.mockRejectedValue(new Error("Outline not found"));

    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByText("Outline not found")).toBeInTheDocument();
  });

  it("locks an unlocked outline", async () => {
    getOutlineMock.mockResolvedValue({
      id: "outline-1",
      outline_json: {
        sections: [{ uid: "sec-1", title: "Section 1" }],
      },
      status_locked: false,
      version: 1,
    });
    lockOutlineMock.mockResolvedValue({ status: "locked", outline_id: "outline-1" });

    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByText("Section 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Одобри/i }));

    await waitFor(() => {
      expect(lockOutlineMock).toHaveBeenCalledWith("project-1", "outline-1");
    });
    expect(await screen.findByRole("button", { name: /Редактирай/i })).toBeInTheDocument();
  });

  it("unlocks a locked outline", async () => {
    getOutlineMock.mockResolvedValue({
      id: "outline-1",
      outline_json: {
        sections: [{ uid: "sec-1", title: "Section 1" }],
      },
      status_locked: true,
      version: 2,
    });
    unlockOutlineMock.mockResolvedValue({ status: "unlocked", outline_id: "outline-1" });

    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByRole("button", { name: /Редактирай/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Редактирай/i }));

    await waitFor(() => {
      expect(unlockOutlineMock).toHaveBeenCalledWith("project-1", "outline-1");
    });
    expect(await screen.findByRole("button", { name: /Одобри/i })).toBeInTheDocument();
  });

  it("deletes outline after confirmation", async () => {
    getOutlineMock.mockResolvedValue({
      id: "outline-1",
      outline_json: {
        sections: [{ uid: "sec-1", title: "Section 1" }],
      },
      status_locked: false,
      version: 1,
    });
    deleteOutlineMock.mockResolvedValue();

    render(<OutlinePanel projectId="project-1" />);

    expect(await screen.findByText("Section 1")).toBeInTheDocument();
    await userEvent.click(screen.getByTitle(/генерирай наново/i));
    await userEvent.click(screen.getByRole("button", { name: "Да" }));

    await waitFor(() => {
      expect(deleteOutlineMock).toHaveBeenCalledWith("project-1");
    });
  });
});
