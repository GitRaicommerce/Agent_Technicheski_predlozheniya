import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChatPanel from "./ChatPanel";
import { api, RateLimitError } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");

  return {
    ...actual,
    api: {
      ...actual.api,
      agents: {
        ...actual.api.agents,
        chat: vi.fn(),
        selectGeneration: vi.fn(),
        listGenerations: vi.fn(),
      },
    },
  };
});

const chatMock = vi.mocked(api.agents.chat);
const selectGenerationMock = vi.mocked(api.agents.selectGeneration);
const listGenerationsMock = vi.mocked(api.agents.listGenerations);

const serverSelection = (selectedId: string | null) => [
  {
    section_uid: "s-1",
    variants: ["gen-1", "gen-2"].map((id, index) => ({
      id,
      project_id: "project-1",
      section_uid: "s-1",
      variant: index + 1,
      text: "",
      evidence_status: "ok",
      selected: id === selectedId,
      created_at: "2026-09-30T10:00:00Z",
    })),
  },
];

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listGenerationsMock.mockResolvedValue([]);
  });

  it("sends a chat message and renders the assistant response", async () => {
    chatMock.mockResolvedValue({
      schema_version: "v1.3",
      status: "ok",
      trace_id: "trace-1",
      assistant_message: "Assistant reply",
      ui_actions: [],
      questions_to_user: [],
    });

    render(<ChatPanel projectId="project-1" />);

    await userEvent.type(screen.getByPlaceholderText(/Въведете съобщение/), "Hello agent");
    await userEvent.click(screen.getByRole("button", { name: "Изпрати" }));

    expect(await screen.findByText("Assistant reply")).toBeInTheDocument();
    expect(chatMock).toHaveBeenCalledWith(
      "project-1",
      "Hello agent",
      [{ role: "user", content: "Hello agent" }],
    );
  });

  it("renders suggested questions and sends one when clicked", async () => {
    chatMock
      .mockResolvedValueOnce({
        schema_version: "v1.3",
        status: "ok",
        trace_id: "trace-1",
        assistant_message: "Need more info",
        ui_actions: [],
        questions_to_user: ["Follow-up question"],
      })
      .mockResolvedValueOnce({
        schema_version: "v1.3",
        status: "ok",
        trace_id: "trace-2",
        assistant_message: "Answered follow-up",
        ui_actions: [],
        questions_to_user: [],
      });

    render(<ChatPanel projectId="project-1" />);

    await userEvent.type(screen.getByPlaceholderText(/Въведете съобщение/), "Initial");
    await userEvent.click(screen.getByRole("button", { name: "Изпрати" }));

    const followUp = await screen.findByRole("button", {
      name: "Follow-up question",
    });
    await userEvent.click(followUp);

    expect(await screen.findByText("Answered follow-up")).toBeInTheDocument();
    expect(chatMock).toHaveBeenNthCalledWith(
      2,
      "project-1",
      "Follow-up question",
      expect.arrayContaining([
        { role: "assistant", content: "Need more info" },
        { role: "user", content: "Follow-up question" },
      ]),
    );
  });

  it("pins a generated variant", async () => {
    chatMock.mockResolvedValue({
      schema_version: "v1.3",
      status: "ok",
      trace_id: "trace-1",
      assistant_message: "Generated",
      ui_actions: [],
      questions_to_user: [],
      agent_result: {
        variant_1: { text: "Variant text" },
        generation_ids: { variant_1: "gen-1" },
      },
    });
    selectGenerationMock.mockResolvedValue({
      status: "selected",
      generation_id: "gen-1",
    });

    render(<ChatPanel projectId="project-1" />);

    await userEvent.type(screen.getByPlaceholderText(/Въведете съобщение/), "Generate section");
    await userEvent.click(screen.getByRole("button", { name: "Изпрати" }));

    const pinButton = await screen.findByRole("button", { name: /📌/ });
    await userEvent.click(pinButton);

    await waitFor(() => {
      expect(selectGenerationMock).toHaveBeenCalledWith("project-1", "gen-1");
    });
  });

  it("shows rate limit countdown when chat is throttled", async () => {
    chatMock.mockRejectedValue(new RateLimitError("Too many requests.", 7));

    render(<ChatPanel projectId="project-1" />);

    await userEvent.type(screen.getByPlaceholderText(/Въведете съобщение/), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Изпрати" }));

    expect(await screen.findByRole("button", { name: /7s/ })).toBeInTheDocument();
  });

  it("renders a UI notice from orchestrator actions and allows dismissing it", async () => {
    chatMock.mockResolvedValue({
      schema_version: "v1.3",
      status: "ok",
      trace_id: "trace-1",
      assistant_message: "Notice delivered",
      ui_actions: [
        {
          type: "show_notice",
          payload: { message: "Outline is ready for review" },
        },
      ],
      questions_to_user: [],
    });

    render(<ChatPanel projectId="project-1" />);

    await userEvent.type(
      screen.getByRole("textbox"),
      "Check outline",
    );
    await userEvent.click(screen.getByRole("button", { name: /Изпрати/i }));

    expect(await screen.findByText("Outline is ready for review")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Затвори/i }));

    await waitFor(() => {
      expect(
        screen.queryByText("Outline is ready for review"),
      ).not.toBeInTheDocument();
    });
  });

  it("loads persisted chat history from localStorage", () => {
    localStorage.setItem(
      "tp_chat_history_project-1",
      JSON.stringify([
        { role: "assistant", content: "Persisted response" },
      ]),
    );

    render(<ChatPanel projectId="project-1" />);

    expect(screen.getByText("Persisted response")).toBeInTheDocument();
  });

  it("shows the server-confirmed selection and a visible pin failure (K-15)", async () => {
    chatMock.mockResolvedValue({
      schema_version: "v1.3",
      status: "ok",
      trace_id: "trace-1",
      assistant_message: "Generated",
      ui_actions: [],
      questions_to_user: [],
      agent_result: {
        variant_1: { text: "A" },
        variant_2: { text: "B" },
        generation_ids: { variant_1: "gen-1", variant_2: "gen-2" },
      },
    });
    listGenerationsMock.mockResolvedValue(serverSelection("gen-2") as never);
    selectGenerationMock.mockRejectedValue(new Error("409 конфликт"));

    render(<ChatPanel projectId="project-1" />);
    await userEvent.type(screen.getByPlaceholderText(/Въведете съобщение/), "Generate");
    await userEvent.click(screen.getByRole("button", { name: "Изпрати" }));

    // The server says variant 2 is selected, so that is what the chat shows.
    expect(await screen.findByText("✓ Вариант 2 закрепен")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "📌 Вариант 1" }));

    expect(await screen.findByTestId("chat-pin-error")).toHaveTextContent("409 конфликт");
    expect(screen.getByText("📌 Вариант 1")).toBeInTheDocument();
    expect(screen.getByText("✓ Вариант 2 закрепен")).toBeInTheDocument();
  });
});
