import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectsPage from "./page";
import { api } from "@/lib/api";

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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        list: vi.fn(),
        stats: vi.fn(),
        delete: vi.fn(),
      },
    },
  };
});

const listMock = vi.mocked(api.projects.list);
const statsMock = vi.mocked(api.projects.stats);

describe("ProjectsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loaded projects and stats", async () => {
    listMock.mockResolvedValue([
      {
        id: "p1",
        name: "Project Alpha",
        location: "Sofia",
        description: "Public procurement",
        created_at: "2026-04-20T10:00:00.000Z",
      },
    ]);
    statsMock.mockResolvedValue({
      p1: {
        files: 3,
        outline_locked: true,
        sections_generated: 2,
        sections_selected: 1,
      },
    });

    render(<ProjectsPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();
    expect(screen.getByText("Sofia")).toBeInTheDocument();
    expect(screen.getByText("Public procurement")).toBeInTheDocument();
    expect(listMock).toHaveBeenCalledWith(20, 0);
    expect(statsMock).toHaveBeenCalled();
  });

  it("filters projects by search query", async () => {
    listMock.mockResolvedValue([
      {
        id: "p1",
        name: "Water Upgrade",
        location: "Sofia",
        description: "Network",
        created_at: "2026-04-20T10:00:00.000Z",
      },
      {
        id: "p2",
        name: "Road Repair",
        location: "Varna",
        description: "Infrastructure",
        created_at: "2026-04-19T10:00:00.000Z",
      },
    ]);
    statsMock.mockResolvedValue({});

    render(<ProjectsPage />);

    await screen.findByText("Water Upgrade");
    const search = screen.getByRole("searchbox");
    await userEvent.type(search, "Road");

    expect(screen.getByText("Road Repair")).toBeInTheDocument();
    expect(screen.queryByText("Water Upgrade")).not.toBeInTheDocument();
  });
});
