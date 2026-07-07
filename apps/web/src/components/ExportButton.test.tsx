import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ExportButton from "./ExportButton";
import { api } from "@/lib/api";

const toastMock = vi.fn();
const createObjectURLMock = vi.fn(() => "blob:test-url");
const revokeObjectURLMock = vi.fn();
const clickMock = vi.fn();

vi.mock("@/components/ToastProvider", () => ({
  useToast: () => ({
    toast: toastMock,
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      export: {
        ...actual.api.export,
        readiness: vi.fn(),
        readinessReport: vi.fn(),
        docx: vi.fn(),
      },
    },
  };
});

const readinessMock = vi.mocked(api.export.readiness);
const readinessReportMock = vi.mocked(api.export.readinessReport);
const exportMock = vi.mocked(api.export.docx);

describe("ExportButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = createObjectURLMock;
    URL.revokeObjectURL = revokeObjectURLMock;
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: true,
      status: "ready",
    });
    readinessReportMock.mockResolvedValue("# readiness");

    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation(((tagName: string) => {
      const element = originalCreateElement(tagName);
      if (tagName === "a") {
        element.click = clickMock;
      }
      return element;
    }) as typeof document.createElement);
  });

  it("downloads a docx and shows success toast", async () => {
    exportMock.mockResolvedValue(new Blob(["docx"]));

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(exportMock).toHaveBeenCalledWith("project-1");
    });
    expect(createObjectURLMock).toHaveBeenCalled();
    expect(clickMock).toHaveBeenCalled();
    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:test-url");
    expect(toastMock).toHaveBeenCalled();
  });

  it("shows stale warning for stale export conflicts", async () => {
    const openGenerationsMock = vi.fn();
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      stale_sections: ["s1", "s2"],
      stale_section_count: 2,
    });

    render(
      <ExportButton
        projectId="project-1"
        projectName="Project Alpha"
        onOpenGenerations={openGenerationsMock}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByTestId("export-stale-warning")).toHaveTextContent(
      "2 секции",
    );

    await userEvent.click(screen.getByRole("button", { name: "Отвори Генерации" }));

    expect(openGenerationsMock).toHaveBeenCalled();
  });

  it("shows duplicate selected warning for ambiguous export sections", async () => {
    const openGenerationsMock = vi.fn();
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      duplicate_selected_count: 1,
      duplicate_selected_sections: [
        {
          section_uid: "s1",
          selected_count: 2,
          generation_ids: ["g1", "g2"],
        },
      ],
    });

    render(
      <ExportButton
        projectId="project-1"
        projectName="Project Alpha"
        onOpenGenerations={openGenerationsMock}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByTestId("export-duplicate-selected-warning"))
      .toHaveTextContent("1 секция");

    await userEvent.click(screen.getByRole("button", { name: "Отвори Генерации" }));

    expect(openGenerationsMock).toHaveBeenCalled();
  });

  it("shows requirement coverage warning for missing requirement conflicts", async () => {
    const openGenerationsMock = vi.fn();
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      missing_requirement_count: 2,
      missing_requirement_sections: [{ section_uid: "s1", missing_count: 2 }],
    });

    render(
      <ExportButton
        projectId="project-1"
        projectName="Project Alpha"
        onOpenGenerations={openGenerationsMock}
      />,
    );

    await userEvent.click(screen.getByTestId("export-docx-button"));

    expect(await screen.findByTestId("export-requirement-warning"))
      .toHaveTextContent("2");

    await userEvent.click(screen.getByRole("button", { name: "Отвори Генерации" }));

    expect(openGenerationsMock).toHaveBeenCalled();
  });

  it("shows requirement warning for missing requirement coverage", async () => {
    const openGenerationsMock = vi.fn();
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      missing_requirement_count: 2,
      missing_requirement_sections: [
        {
          section_uid: "s1",
          missing_requirement_ids: ["req-1", "req-2"],
        },
      ],
    });

    render(
      <ExportButton
        projectId="project-1"
        projectName="Project Alpha"
        onOpenGenerations={openGenerationsMock}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByTestId("export-requirement-warning"))
      .toHaveTextContent("2 изисквания");

    await userEvent.click(screen.getByRole("button", { name: "Отвори Генерации" }));

    expect(openGenerationsMock).toHaveBeenCalled();
  });

  it("shows quality warning for shallow generated sections", async () => {
    const openGenerationsMock = vi.fn();
    const qualitySectionsBlockedMock = vi.fn();
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      quality_section_count: 1,
      quality_sections: [
        {
          section_uid: "s1",
          word_count: 12,
          min_words: 1200,
          blueprint_group_count: 6,
        },
      ],
    });

    render(
      <ExportButton
        projectId="project-1"
        projectName="Project Alpha"
        onOpenGenerations={openGenerationsMock}
        onQualitySectionsBlocked={qualitySectionsBlockedMock}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByTestId("export-quality-warning"))
      .toHaveTextContent("1 секция");
    expect(screen.getByTestId("export-quality-warning"))
      .toHaveTextContent("6 групи изисквания");
    expect(screen.getByTestId("export-quality-warning"))
      .toHaveTextContent("1200 думи");
    expect(qualitySectionsBlockedMock).toHaveBeenNthCalledWith(1, []);
    expect(qualitySectionsBlockedMock).toHaveBeenLastCalledWith(["s1"]);

    await userEvent.click(screen.getByRole("button", { name: "Отвори Генерации" }));

    expect(openGenerationsMock).toHaveBeenCalled();
  });

  it("downloads markdown readiness report after blocked preflight", async () => {
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      duplicate_selected_count: 1,
      duplicate_selected_sections: [{ section_uid: "s1" }],
    });
    readinessReportMock.mockResolvedValue("# DOCX export readiness report");

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByTestId("export-docx-button"));
    await userEvent.click(
      await screen.findByRole("button", { name: "Свали readiness report" }),
    );

    expect(readinessReportMock).toHaveBeenCalledWith("project-1");
    expect(createObjectURLMock).toHaveBeenCalledWith(expect.any(Blob));
    expect(clickMock).toHaveBeenCalled();
    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:test-url");
    expect(toastMock).toHaveBeenCalledWith(
      "Readiness отчетът е изтеглен.",
      "success",
    );
  });

  it("shows multiple readiness warnings from one preflight response", async () => {
    readinessMock.mockResolvedValue({
      project_id: "project-1",
      ready: false,
      status: "blocked",
      duplicate_selected_count: 1,
      duplicate_selected_sections: [{ section_uid: "s1" }],
      stale_section_count: 2,
      stale_sections: ["s2", "s3"],
      missing_requirement_count: 3,
      missing_requirement_sections: [{ section_uid: "s4", missing_count: 3 }],
      quality_section_count: 1,
      quality_sections: [{ section_uid: "s5" }],
    });

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByTestId("export-docx-button"));

    expect(
      await screen.findByTestId("export-duplicate-selected-warning"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("export-stale-warning")).toBeInTheDocument();
    expect(screen.getByTestId("export-requirement-warning")).toBeInTheDocument();
    expect(screen.getByTestId("export-quality-warning")).toBeInTheDocument();
    expect(exportMock).not.toHaveBeenCalled();
  });

  it("shows generic export errors", async () => {
    exportMock.mockRejectedValue(new Error("Export failed"));

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByText("Export failed")).toBeInTheDocument();
  });
});
