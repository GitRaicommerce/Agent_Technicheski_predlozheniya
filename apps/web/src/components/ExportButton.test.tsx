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
    exportMock.mockRejectedValue(new ApiError("stale evidence", 409));

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByRole("button"));

    expect(await screen.findByText(/актуализирани/i)).toBeInTheDocument();
  });

  it("shows generic export errors", async () => {
    exportMock.mockRejectedValue(new Error("Export failed"));

    render(<ExportButton projectId="project-1" projectName="Project Alpha" />);

    await userEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("Export failed")).toBeInTheDocument();
  });
});
