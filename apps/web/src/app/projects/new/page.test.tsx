import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NewProjectPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();
const backMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    back: backMock,
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        create: vi.fn(),
      },
    },
  };
});

const createMock = vi.mocked(api.projects.create);

describe("NewProjectPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits the form and redirects to the created project", async () => {
    createMock.mockResolvedValue({
      id: "project-123",
      name: "Project Alpha",
      created_at: "2026-04-20T10:00:00.000Z",
    });

    const { container } = render(<NewProjectPage />);
    const inputs = container.querySelectorAll("input");
    const textarea = container.querySelector("textarea");

    fireEvent.change(inputs[0], { target: { value: "Project Alpha" } });
    fireEvent.change(inputs[1], { target: { value: "Sofia" } });
    fireEvent.change(textarea!, { target: { value: "Public procurement scope" } });
    fireEvent.change(inputs[2], { target: { value: "Municipality" } });
    fireEvent.change(inputs[3], { target: { value: "2026-04-20" } });

    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith({
        name: "Project Alpha",
        location: "Sofia",
        description: "Public procurement scope",
        contracting_authority: "Municipality",
        tender_date: "2026-04-20",
      });
    });
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/projects/project-123");
    });
  });

  it("shows the API error when project creation fails", async () => {
    createMock.mockRejectedValue(new Error("Create failed"));

    const { container } = render(<NewProjectPage />);
    const nameInput = container.querySelector("input[required]");

    fireEvent.change(nameInput!, { target: { value: "Project Alpha" } });
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByText("Create failed")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
