import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FileUploadPanel from "./FileUploadPanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      files: {
        ...actual.api.files,
        list: vi.fn(),
        delete: vi.fn(),
      },
    },
  };
});

const listMock = vi.mocked(api.files.list);
const deleteMock = vi.mocked(api.files.delete);

describe("FileUploadPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads existing files and renders their status", async () => {
    listMock.mockResolvedValue([
      {
        id: "file-1",
        project_id: "project-1",
        module: "examples",
        filename: "example.pdf",
        file_hash: "hash",
        ingest_status: "done",
      },
    ]);

    render(<FileUploadPanel projectId="project-1" module="examples" />);

    expect(await screen.findByText("example.pdf")).toBeInTheDocument();
    expect(screen.getByText(/готово/i)).toBeInTheDocument();
  });

  it("shows validation error for unsupported dropped files", async () => {
    listMock.mockResolvedValue([]);

    render(<FileUploadPanel projectId="project-1" module="examples" />);

    const panel = screen.getByText(/Примерни ТП/i).closest("div[class*='border-2']");
    const invalidFile = new File(["bad"], "notes.txt", { type: "text/plain" });

    fireEvent.drop(panel!, {
      dataTransfer: {
        files: [invalidFile],
      },
    });

    expect(await screen.findByText(/Неподдържан формат/i)).toBeInTheDocument();
  });

  it("deletes a file after confirmation", async () => {
    listMock.mockResolvedValue([
      {
        id: "file-1",
        project_id: "project-1",
        module: "examples",
        filename: "example.pdf",
        file_hash: "hash",
        ingest_status: "done",
      },
    ]);
    deleteMock.mockResolvedValue();

    render(<FileUploadPanel projectId="project-1" module="examples" />);

    expect(await screen.findByText("example.pdf")).toBeInTheDocument();

    await userEvent.click(screen.getByTitle(/Изтрий файл/i));
    await userEvent.click(screen.getByTitle(/Потвърди изтриване/i));

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith("project-1", "file-1");
    });
    await waitFor(() => {
      expect(screen.queryByText("example.pdf")).not.toBeInTheDocument();
    });
  });
});
