import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectPage from "./page";
import { api, type ExportQualitySection } from "@/lib/api";

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
  default: ({
    onOpenGenerations,
    onQualitySectionsBlocked,
  }: {
    onOpenGenerations?: () => void;
    onQualitySectionsBlocked?: (
      sectionUids: string[],
      sections?: ExportQualitySection[],
    ) => void;
  }) => (
    <div>
      Export Button
      <div
        data-testid="mock-open-generations"
        onClick={onOpenGenerations}
      >
        Open Generations
      </div>
      <div
        data-testid="mock-quality-blockers"
        onClick={() =>
          onQualitySectionsBlocked?.(["sec-quality"], [
            {
              section_uid: "sec-quality",
              min_words: 1400,
              suggested_words_per_structure: 280,
            },
          ])
        }
      >
        Set Quality Blockers
      </div>
    </div>
  ),
}));

vi.mock("@/components/FileUploadPanel", () => ({
  default: () => <div>File Upload Panel</div>,
}));

vi.mock("@/components/OutlinePanel", () => ({
  default: () => <div>Outline Panel</div>,
}));

vi.mock("@/components/RequirementChecklistPanel", () => ({
  default: () => <div>Requirement Checklist Panel</div>,
}));

vi.mock("@/components/SchedulePanel", () => ({
  default: () => <div>Schedule Panel</div>,
}));

vi.mock("@/components/GenerationsPanel", () => ({
  default: ({
    focusAttentionKey = 0,
    qualityAttentionSectionUids = [],
    qualityAttentionSections = [],
  }: {
    focusAttentionKey?: number;
    qualityAttentionSectionUids?: string[];
    qualityAttentionSections?: ExportQualitySection[];
  }) => (
    <div data-testid="mock-generations-panel">
      Generations Panel focus={focusAttentionKey}{" "}
      {qualityAttentionSectionUids.join(",")} details=
      {qualityAttentionSections
        .map((section) => section.suggested_words_per_structure)
        .join(",")}
    </div>
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
        get: vi.fn(),
        update: vi.fn(),
        refreshLegislation: vi.fn(),
        legislationStatus: vi.fn(),
        delete: vi.fn(),
      },
    },
  };
});

const getMock = vi.mocked(api.projects.get);
const updateMock = vi.mocked(api.projects.update);
const refreshLegislationMock = vi.mocked(api.projects.refreshLegislation);
const legislationStatusMock = vi.mocked(api.projects.legislationStatus);
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
    refreshLegislationMock.mockResolvedValue({
      status: "ok",
      checked: 0,
      changed: 0,
      unchanged: 0,
      skipped_fresh: 9,
      refreshed: [],
      errors: [],
    });
    legislationStatusMock.mockResolvedValue({
      status: "ok",
      automatic_source: "Lex.bg",
      configured_acts: 9,
      loaded_acts: 9,
      missing_acts: [],
      chunk_count: 90,
      latest_fetched_at: "2026-04-20T10:00:00.000Z",
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
    await waitFor(() => {
      expect(refreshLegislationMock).toHaveBeenCalledWith("project-1", false);
    });

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

  it("shows schedule only as a dedicated panel, not as a duplicate upload module", async () => {
    render(<ProjectPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();

    expect(screen.queryByTestId("module-toggle-schedule")).not.toBeInTheDocument();
    expect(screen.getByTestId("schedule-panel-toggle")).toBeInTheDocument();
  });

  it("shows the requirements checklist as a dedicated project panel", async () => {
    render(<ProjectPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("requirements-panel-toggle"));

    expect(screen.getByText("Requirement Checklist Panel")).toBeInTheDocument();
  });

  it("passes quality export blockers into the generations panel", async () => {
    render(<ProjectPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("mock-quality-blockers"));
    await userEvent.click(screen.getByTestId("mock-open-generations"));

    expect(screen.getByTestId("mock-generations-panel"))
      .toHaveTextContent("sec-quality");
    expect(screen.getByTestId("mock-generations-panel"))
      .toHaveTextContent("details=280");
    expect(screen.getByTestId("mock-generations-panel"))
      .toHaveTextContent("focus=1");
  });

  it("shows automatic Lex.bg status and allows manual refresh", async () => {
    render(<ProjectPage />);

    expect(await screen.findByText("Project Alpha")).toBeInTheDocument();
    await waitFor(() => {
      expect(legislationStatusMock).toHaveBeenCalledWith("project-1");
    });

    await userEvent.click(screen.getByTestId("module-toggle-legislation"));

    expect(await screen.findByTestId("legislation-auto-panel")).toHaveTextContent(
      "Lex.bg",
    );

    await userEvent.click(screen.getByTestId("legislation-refresh-button"));

    await waitFor(() => {
      expect(refreshLegislationMock).toHaveBeenCalledWith("project-1", true);
    });
  });
});
