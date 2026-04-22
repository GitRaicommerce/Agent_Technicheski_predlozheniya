"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  ChatMessage,
  GenerationVariant,
  OrchestratorResponse,
  RateLimitError,
} from "@/lib/api";
import { repairLikelyMojibake } from "@/lib/text";

interface Props {
  projectId: string;
  onOpenOutline?: () => void;
  onOpenGenerations?: () => void;
}

interface ExtendedMessage extends ChatMessage {
  variants?: { v1?: GenerationVariant; v2?: GenerationVariant };
  generationIds?: { variant_1?: string; variant_2?: string };
  verificationVerdict?: string;
}

const STORAGE_KEY = (id: string) => `tp_chat_history_${id}`;

export default function ChatPanel({
  projectId,
  onOpenOutline,
  onOpenGenerations,
}: Props) {
  const [history, setHistory] = useState<ExtendedMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [uiNotice, setUiNotice] = useState<string | null>(null);
  const [activeVariant, setActiveVariant] = useState<
    Record<number, "v1" | "v2">
  >({});
  const [pinnedGenerations, setPinnedGenerations] = useState<Set<string>>(
    new Set(),
  );
  const [rateLimitCountdown, setRateLimitCountdown] = useState<number | null>(
    null,
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (rateLimitCountdown === null || rateLimitCountdown <= 0) {
      if (rateLimitCountdown === 0) setRateLimitCountdown(null);
      return;
    }

    const timer = setTimeout(() => {
      setRateLimitCountdown((value) => (value !== null ? value - 1 : null));
    }, 1000);

    return () => clearTimeout(timer);
  }, [rateLimitCountdown]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = localStorage.getItem(STORAGE_KEY(projectId));
      if (saved) {
        setHistory(JSON.parse(saved));
      }
    } catch {
      // Ignore invalid local storage payloads.
    }
  }, [projectId]);

  useEffect(() => {
    if (typeof window === "undefined" || history.length === 0) return;
    try {
      localStorage.setItem(STORAGE_KEY(projectId), JSON.stringify(history));
    } catch {
      // Ignore quota errors.
    }
  }, [history, projectId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const send = async (overrideMessage?: string) => {
    const message = (overrideMessage ?? input).trim();
    if (!message || loading) return;

    setInput("");
    setSuggestedQuestions([]);
    setUiNotice(null);
    setLoading(true);

    const userMsg: ExtendedMessage = { role: "user", content: message };
    setHistory((items) => [...items, userMsg]);

    try {
      const res: OrchestratorResponse = await api.agents.chat(
        projectId,
        message,
        [...history, userMsg]
          .slice(-20)
          .map(({ role, content }) => ({ role, content })),
      );

      if (res.questions_to_user?.length) {
        setSuggestedQuestions(res.questions_to_user);
      }

      if (res.ui_actions?.length) {
        const notice = res.ui_actions.find(
          (action) =>
            action.type === "show_notice" || action.type === "show_outline",
        );

        if (notice) {
          if (notice.type === "show_outline") {
            onOpenOutline?.();
          }

          const payload = notice.payload as Record<string, unknown>;
          setUiNotice(
            typeof payload.message === "string"
              ? repairLikelyMojibake(payload.message)
              : `Действие: ${notice.type}`,
          );
        }
      }

      if (
        res.agent_called === "drafting" ||
        res.agent_called === "drafting_all" ||
        res.agent_result?.generation_ids
      ) {
        onOpenGenerations?.();
      }

      const assistantMsg: ExtendedMessage = {
        role: "assistant",
        content: res.assistant_message,
        variants:
          res.agent_result?.variant_1 || res.agent_result?.variant_2
            ? {
                v1: res.agent_result.variant_1,
                v2: res.agent_result.variant_2,
              }
            : undefined,
        generationIds: res.agent_result?.generation_ids
          ? {
              variant_1: (
                res.agent_result.generation_ids as Record<string, string>
              ).variant_1,
              variant_2: (
                res.agent_result.generation_ids as Record<string, string>
              ).variant_2,
            }
          : undefined,
        verificationVerdict: res.agent_result?.verification?.verdict,
      };

      setHistory((items) => [...items, assistantMsg]);
    } catch (err: unknown) {
      if (err instanceof RateLimitError) {
        setRateLimitCountdown(err.retryAfter);
      } else {
        const errorMsg: ExtendedMessage = {
          role: "assistant",
          content: `⚠ Грешка: ${
            err instanceof Error ? err.message : "Неизвестна грешка"
          }`,
        };
        setHistory((items) => [...items, errorMsg]);
      }
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => {
    setHistory([]);
    setSuggestedQuestions([]);
    setUiNotice(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem(STORAGE_KEY(projectId));
    }
  };

  const handlePin = async (genId: string) => {
    try {
      await api.agents.selectGeneration(projectId, genId);
      setPinnedGenerations((items) => new Set([...items, genId]));
    } catch {
      // Pinning is convenience-only, so a failure should not block the chat.
    }
  };

  return (
    <div className="flex h-full flex-col rounded-lg border bg-white shadow-sm">
      <div className="flex items-center justify-between rounded-t-lg border-b bg-gray-50 p-3">
        <span className="font-semibold text-gray-700">TP AI Оркестратор</span>
        {history.length > 0 && (
          <button
            onClick={clearHistory}
            className="text-xs text-gray-400 transition hover:text-red-500"
            title="Изчисти историята"
          >
            Изчисти
          </button>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {history.length === 0 && (
          <p className="mt-8 text-center text-sm text-gray-400">
            Опишете проекта или задайте въпрос...
          </p>
        )}

        {history.map((msg, index) => (
          <div
            key={index}
            className={`flex ${
              msg.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div className="max-w-[85%] space-y-2">
              <div
                className={`whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                  msg.role === "user"
                    ? "rounded-br-none bg-blue-600 text-white"
                    : "rounded-bl-none bg-gray-100 text-gray-800"
                }`}
              >
                {repairLikelyMojibake(msg.content)}
              </div>

              {msg.variants && (msg.variants.v1 || msg.variants.v2) && (
                <div className="overflow-hidden rounded-xl border text-xs">
                  <div className="flex border-b bg-gray-50">
                    {msg.variants.v1 && (
                      <button
                        onClick={() =>
                          setActiveVariant((value) => ({
                            ...value,
                            [index]: "v1",
                          }))
                        }
                        className={`px-3 py-1.5 font-medium transition ${
                          (activeVariant[index] ?? "v1") === "v1"
                            ? "border-b-2 border-blue-500 bg-white text-blue-700"
                            : "text-gray-500 hover:text-gray-700"
                        }`}
                      >
                        Вариант 1
                      </button>
                    )}
                    {msg.variants.v2 && (
                      <button
                        onClick={() =>
                          setActiveVariant((value) => ({
                            ...value,
                            [index]: "v2",
                          }))
                        }
                        className={`px-3 py-1.5 font-medium transition ${
                          (activeVariant[index] ?? "v1") === "v2"
                            ? "border-b-2 border-blue-500 bg-white text-blue-700"
                            : "text-gray-500 hover:text-gray-700"
                        }`}
                      >
                        Вариант 2
                      </button>
                    )}
                  </div>

                  <div className="whitespace-pre-wrap bg-white p-3 leading-relaxed text-gray-700">
                    {(activeVariant[index] ?? "v1") === "v1"
                      ? repairLikelyMojibake(msg.variants.v1?.text)
                      : repairLikelyMojibake(msg.variants.v2?.text)}
                  </div>

                  {msg.verificationVerdict && (
                    <div
                      className={`border-t px-3 py-1.5 text-xs ${
                        msg.verificationVerdict === "ok"
                          ? "bg-green-50 text-green-700"
                          : "bg-amber-50 text-amber-700"
                      }`}
                    >
                      Проверка: {msg.verificationVerdict}
                    </div>
                  )}

                  {(msg.generationIds?.variant_1 ||
                    msg.generationIds?.variant_2) && (
                    <div className="flex flex-wrap items-center gap-2 border-t bg-gray-50 px-3 py-1.5">
                      <span className="shrink-0 text-xs text-gray-400">
                        За документа:
                      </span>
                      {msg.generationIds.variant_1 && (
                        <button
                          onClick={() =>
                            void handlePin(msg.generationIds!.variant_1!)
                          }
                          className={`rounded border px-2 py-0.5 text-xs transition ${
                            pinnedGenerations.has(msg.generationIds.variant_1)
                              ? "border-green-200 bg-green-50 text-green-700"
                              : "border-gray-200 bg-white text-gray-600 hover:bg-blue-50 hover:text-blue-700"
                          }`}
                        >
                          {pinnedGenerations.has(msg.generationIds.variant_1)
                            ? "✓ Вариант 1 закрепен"
                            : "📌 Вариант 1"}
                        </button>
                      )}
                      {msg.generationIds.variant_2 && (
                        <button
                          onClick={() =>
                            void handlePin(msg.generationIds!.variant_2!)
                          }
                          className={`rounded border px-2 py-0.5 text-xs transition ${
                            pinnedGenerations.has(msg.generationIds.variant_2)
                              ? "border-green-200 bg-green-50 text-green-700"
                              : "border-gray-200 bg-white text-gray-600 hover:bg-blue-50 hover:text-blue-700"
                          }`}
                        >
                          {pinnedGenerations.has(msg.generationIds.variant_2)
                            ? "✓ Вариант 2 закрепен"
                            : "📌 Вариант 2"}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-none bg-gray-100 px-4 py-2 text-sm text-gray-500 animate-pulse">
              Обработва се...
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {uiNotice && (
        <div className="mx-3 mb-1 flex items-start justify-between rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <span>{repairLikelyMojibake(uiNotice)}</span>
          <button
            onClick={() => setUiNotice(null)}
            className="ml-2 font-bold leading-none text-amber-500 hover:text-amber-700"
            aria-label="Затвори"
          >
            ×
          </button>
        </div>
      )}

      {suggestedQuestions.length > 0 && (
        <div className="flex flex-wrap gap-2 px-3 pb-1">
          {suggestedQuestions.map((question, index) => (
            <button
              key={index}
              onClick={() => send(question)}
              disabled={loading}
              className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {repairLikelyMojibake(question)}
            </button>
          ))}
        </div>
      )}

      {rateLimitCountdown !== null && (
        <div className="mx-3 mb-1 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <span>⏱</span>
          <span>
            Твърде много заявки. Изчакайте{" "}
            <strong>{rateLimitCountdown}</strong> сек. преди следващото
            съобщение.
          </span>
        </div>
      )}

      <div className="flex items-end gap-2 border-t p-3">
        <textarea
          className="min-h-[38px] max-h-40 flex-1 resize-none overflow-y-auto rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          rows={1}
          value={input}
          onChange={(event) => {
            setInput(event.target.value);
            event.target.style.height = "auto";
            event.target.style.height = `${Math.min(
              event.target.scrollHeight,
              160,
            )}px`;
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder="Въведете съобщение... (Enter за изпращане, Shift+Enter за нов ред)"
          disabled={loading || rateLimitCountdown !== null}
        />
        <button
          onClick={() => void send()}
          disabled={loading || !input.trim() || rateLimitCountdown !== null}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {rateLimitCountdown !== null ? `⏱ ${rateLimitCountdown}s` : "Изпрати"}
        </button>
      </div>
    </div>
  );
}
