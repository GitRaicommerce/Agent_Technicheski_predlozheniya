import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();
const toastMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "project-1" }),
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: { children: React.ReactNode; href: string } & Record<string, unknown>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/ToastProvider", () => ({
  useToast: () => ({
    toast: toastMock,
  }),
}));

vi.mock("@/components/ChatPanel", () => ({
  default: () => <div>Chat Panel</div>,
}));

vi.mock("@/components/ExportButton", () => ({
  default: () => <div>Export Button</div>,
}));

vi.mock("@/components/FileUploadPanel", () => ({
  default: () => <div>File Upload Panel</div>,
}));

vi.mock("@/components/OutlinePanel", () => ({
  default: () => <div>Outline Panel</div>,
}));

vi.mock("@/components/SchedulePanel", () => ({
  default: () => <div>Schedule Panel</div>,
}));

vi.mock("@/components/GenerationsPanel", () => ({
  default: () => <div>Generations Panel</div>,
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        get: vi.fn(),
        update: vi.fn(),
        delete: vi.fn(),
      },
    },
  };
});

const getMock = vi.mocked(api.projects.get);
const updateMock = vi.mocked(api.projects.update);
const deleteMock = vi.mocked(api.projects.delete);

describe("ProjectPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMock.mockResolvedValue({
      id: "project-1",
      name: "Project Alpha",
      location: "Sofia",
      description: "Initial description",
      contracting_authority: "Municipality",
      tender_date: "2026-04-20",
      created_at: "2026-04-20T10:00:00.000Z",
    });
  });

  it("loads a project and saves edits", async () => {
    updateMock.mockResolvedValue({
      id: "project-1",
      name: "Updated Project",
      location: "Plovdiv",
      description: "Updated description",
      contracting_authority: "Updated authority",
      tender_date: "2026-04-21",
      created_at: "2026-04-20T10:00:00.000Z",
      updated_at: "2026-04-21T10:00:00.000Z",
    });

    const { container } = render(<ProjectPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();

    const editButton = screen.getByRole("button", { name: "✎" });
    await userEvent.click(editButton!);

    await waitFor(() => {
      expect(container.querySelectorAll("input").length).toBe(5);
    });

    const inputs = container.querySelectorAll("input");
    fireEvent.change(inputs[0], { target: { value: "Updated Project" } });
    fireEvent.change(inputs[1], { target: { value: "Plovdiv" } });
    fireEvent.change(inputs[2], { target: { value: "Updated authority" } });
    fireEvent.change(inputs[3], { target: { value: "2026-04-21" } });
    fireEvent.change(inputs[4], { target: { value: "Updated description" } });

    await userEvent.click(screen.getByRole("button", { name: "Запази" }));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith("project-1", {
        name: "Updated Project",
        location: "Plovdiv",
        description: "Updated description",
        contracting_authority: "Updated authority",
        tender_date: "2026-04-21",
      });
    });
    expect(await screen.findByText("Updated Project")).toBeInTheDocument();
    expect(toastMock).toHaveBeenCalled();
  });

  it("deletes a project after confirmation and redirects", async () => {
    deleteMock.mockResolvedValue();

    render(<ProjectPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button")[0]);
    await userEvent.click(screen.getByRole("button", { name: /Да, изтрий/i }));

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith("project-1");
    });
    expect(pushMock).toHaveBeenCalledWith("/projects");
  });
});
