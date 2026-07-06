import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ExportButton from "./ExportButton";
import { api, ApiError } from "@/lib/api";

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
        docx: vi.fn(),
      },
    },
  };
});

const exportMock = vi.mocked(api.export.docx);

describe("ExportButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = createObjectURLMock;
    URL.revokeObjectURL = revokeObjectURLMock;

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
    exportMock.mockRejectedValue(
      new ApiError("Pre-export check failed", 409, {
        detail: {
          stale_sections: ["s1", "s2"],
        },
      }),
    );

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

  it("shows requirement coverage warning for missing requirement conflicts", async () => {
    const openGenerationsMock = vi.fn();
    exportMock.mockRejectedValue(
      new ApiError("Pre-export check failed", 409, {
        detail: {
          missing_requirement_count: 2,
          missing_requirement_sections: [
            { section_uid: "s1", missing_count: 2 },
          ],
        },
      }),
    );

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
    exportMock.mockRejectedValue(
      new ApiError("Pre-export check failed", 409, {
        detail: {
          missing_requirement_count: 2,
          missing_requirement_sections: [
            {
              section_uid: "s1",
              missing_requirement_ids: ["req-1", "req-2"],
            },
          ],
        },
      }),
    );

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
    exportMock.mockRejectedValue(
      new ApiError("Pre-export check failed", 409, {
        detail: {
          quality_section_count: 1,
          quality_sections: [
            {
              section_uid: "s1",
              word_count: 12,
              min_words: 360,
            },
          ],
        },
      }),
    );

    render(
      <ExportButton
        projectId="project-1"
        projectName="Project Alpha"
        onOpenGenerations={openGenerationsMock}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByTestId("export-quality-warning"))
      .toHaveTextContent("1 секция");

    await userEvent.click(screen.getByRole("button", { name: "Отвори Генерации" }));

    expect(openGenerationsMock).toHaveBeenCalled();
  });

  it("shows generic export errors", async () => {
    exportMock.mockRejectedValue(new Error("Export failed"));

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByRole("button", { name: "Експорт .docx" }));

    expect(await screen.findByText("Export failed")).toBeInTheDocument();
  });
});
