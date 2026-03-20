"use client";

import { useState, useRef, useEffect } from "react";
import {
  api,
  ChatMessage,
  OrchestratorResponse,
  GenerationVariant,
  RateLimitError,
} from "@/lib/api";

interface Props {
  projectId: string;
}

// Разширено съобщение — пази и генерираните варианти ако има
interface ExtendedMessage extends ChatMessage {
  variants?: { v1?: GenerationVariant; v2?: GenerationVariant };
  generationIds?: { variant_1?: string; variant_2?: string };
  verificationVerdict?: string;
}

const STORAGE_KEY = (id: string) => `tp_chat_history_${id}`;

export default function ChatPanel({ projectId }: Props) {
  const [history, setHistory] = useState<ExtendedMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [uiNotice, setUiNotice] = useState<string | null>(null);
  // Активен вариант по message index
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
    const timer = setTimeout(
      () => setRateLimitCountdown((n) => (n !== null ? n - 1 : null)),
      1000,
    );
    return () => clearTimeout(timer);
  }, [rateLimitCountdown]);

  // Зареди историята от localStorage при mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = localStorage.getItem(STORAGE_KEY(projectId));
      if (saved) setHistory(JSON.parse(saved));
    } catch {
      /* повредени данни — игнорираме */
    }
  }, [projectId]);

  // Запази историята при промяна
  useEffect(() => {
    if (typeof window === "undefined" || history.length === 0) return;
    try {
      localStorage.setItem(STORAGE_KEY(projectId), JSON.stringify(history));
    } catch {
      /* quota exceeded — игнорираме */
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
    setHistory((h) => [...h, userMsg]);

    try {
      const res: OrchestratorResponse = await api.agents.chat(
        projectId,
        message,
        // Send only the last 20 messages to avoid LLM context limits
        [...history, userMsg]
          .slice(-20)
          .map(({ role, content }) => ({ role, content })),
      );

      if (res.questions_to_user?.length) {
        setSuggestedQuestions(res.questions_to_user);
      }

      if (res.ui_actions?.length) {
        const notice = res.ui_actions.find(
          (a) => a.type === "show_notice" || a.type === "show_outline",
        );
        if (notice) {
          const payload = notice.payload as Record<string, unknown>;
          setUiNotice(
            typeof payload.message === "string"
              ? payload.message
              : `Действие: ${notice.type}`,
          );
        }
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
              )["variant_1"],
              variant_2: (
                res.agent_result.generation_ids as Record<string, string>
              )["variant_2"],
            }
          : undefined,
        verificationVerdict: res.agent_result?.verification?.verdict,
      };
      setHistory((h) => [...h, assistantMsg]);
    } catch (err: unknown) {
      if (err instanceof RateLimitError) {
        setRateLimitCountdown(err.retryAfter);
      } else {
        const errorMsg: ExtendedMessage = {
          role: "assistant",
          content: `⚠ Грешка: ${err instanceof Error ? err.message : "Неизвестна грешка"}`,
        };
        setHistory((h) => [...h, errorMsg]);
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
      setPinnedGenerations((p) => new Set([...p, genId]));
    } catch {
      // закрепването е удобство — тихо игнорираме грешка
    }
  };

  return (
    <div className="flex flex-col h-full border rounded-lg bg-white shadow-sm">
      <div className="p-3 border-b bg-gray-50 rounded-t-lg flex justify-between items-center">
        <span className="font-semibold text-gray-700">TP AI Оркестратор</span>
        {history.length > 0 && (
          <button
            onClick={clearHistory}
            className="text-xs text-gray-400 hover:text-red-500 transition"
            title="Изчисти историята"
          >
            Изчисти
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {history.length === 0 && (
          <p className="text-gray-400 text-sm text-center mt-8">
            Опишете проекта или задайте въпрос...
          </p>
        )}
        {history.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div className="max-w-[85%] space-y-2">
              <div
                className={`px-4 py-2 rounded-2xl text-sm whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-gray-100 text-gray-800 rounded-bl-none"
                }`}
              >
                {msg.content}
              </div>

              {/* Генерирани варианти */}
              {msg.variants && (msg.variants.v1 || msg.variants.v2) && (
                <div className="border rounded-xl overflow-hidden text-xs">
                  {/* Tab header */}
                  <div className="flex border-b bg-gray-50">
                    {msg.variants.v1 && (
                      <button
                        onClick={() =>
                          setActiveVariant((av) => ({ ...av, [i]: "v1" }))
                        }
                        className={`px-3 py-1.5 font-medium transition ${
                          (activeVariant[i] ?? "v1") === "v1"
                            ? "bg-white border-b-2 border-blue-500 text-blue-700"
                            : "text-gray-500 hover:text-gray-700"
                        }`}
                      >
                        Вариант 1 (кратък)
                      </button>
                    )}
                    {msg.variants.v2 && (
                      <button
                        onClick={() =>
                          setActiveVariant((av) => ({ ...av, [i]: "v2" }))
                        }
                        className={`px-3 py-1.5 font-medium transition ${
                          (activeVariant[i] ?? "v1") === "v2"
                            ? "bg-white border-b-2 border-blue-500 text-blue-700"
                            : "text-gray-500 hover:text-gray-700"
                        }`}
                      >
                        Вариант 2 (детайлен)
                      </button>
                    )}
                  </div>
                  {/* Tab content */}
                  <div className="p-3 bg-white text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {(activeVariant[i] ?? "v1") === "v1"
                      ? msg.variants.v1?.text
                      : msg.variants.v2?.text}
                  </div>
                  {/* Verification verdict */}
                  {msg.verificationVerdict && (
                    <div
                      className={`px-3 py-1.5 text-xs border-t ${
                        msg.verificationVerdict === "ok"
                          ? "bg-green-50 text-green-700"
                          : "bg-amber-50 text-amber-700"
                      }`}
                    >
                      Проверка: {msg.verificationVerdict}
                    </div>
                  )}
                  {/* Закрепване за документ */}
                  {(msg.generationIds?.variant_1 ||
                    msg.generationIds?.variant_2) && (
                    <div className="px-3 py-1.5 border-t bg-gray-50 flex items-center gap-2 flex-wrap">
                      <span className="text-gray-400 text-xs shrink-0">
                        За документ:
                      </span>
                      {msg.generationIds.variant_1 && (
                        <button
                          onClick={() =>
                            void handlePin(msg.generationIds!.variant_1!)
                          }
                          className={`text-xs px-2 py-0.5 rounded border transition ${
                            pinnedGenerations.has(msg.generationIds.variant_1)
                              ? "bg-green-50 text-green-700 border-green-200"
                              : "bg-white text-gray-600 hover:bg-blue-50 hover:text-blue-700 border-gray-200"
                          }`}
                        >
                          {pinnedGenerations.has(msg.generationIds.variant_1)
                            ? "✓ Вар 1 закрепен"
                            : "📌 Вариант 1"}
                        </button>
                      )}
                      {msg.generationIds.variant_2 && (
                        <button
                          onClick={() =>
                            void handlePin(msg.generationIds!.variant_2!)
                          }
                          className={`text-xs px-2 py-0.5 rounded border transition ${
                            pinnedGenerations.has(msg.generationIds.variant_2)
                              ? "bg-green-50 text-green-700 border-green-200"
                              : "bg-white text-gray-600 hover:bg-blue-50 hover:text-blue-700 border-gray-200"
                          }`}
                        >
                          {pinnedGenerations.has(msg.generationIds.variant_2)
                            ? "✓ Вар 2 закрепен"
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
            <div className="bg-gray-100 text-gray-500 px-4 py-2 rounded-2xl rounded-bl-none text-sm animate-pulse">
              Обработва се...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* UI notice banner */}
      {uiNotice && (
        <div className="mx-3 mb-1 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex justify-between items-start">
          <span>{uiNotice}</span>
          <button
            onClick={() => setUiNotice(null)}
            className="ml-2 text-amber-500 hover:text-amber-700 font-bold leading-none"
            aria-label="Затвори"
          >
            ×
          </button>
        </div>
      )}

      {/* Suggested questions chips */}
      {suggestedQuestions.length > 0 && (
        <div className="px-3 pb-1 flex flex-wrap gap-2">
          {suggestedQuestions.map((q, idx) => (
            <button
              key={idx}
              onClick={() => send(q)}
              disabled={loading}
              className="text-xs px-3 py-1 bg-blue-50 text-blue-700 border border-blue-200 rounded-full hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {rateLimitCountdown !== null && (
        <div className="mx-3 mb-1 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
          <span>⏳</span>
          <span>
            Твърде много заявки. Изчакайте <strong>{rateLimitCountdown}</strong>{" "}
            сек. преди следващото съобщение.
          </span>
        </div>
      )}
      <div className="p-3 border-t flex gap-2">
        <input
          className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Въведете съобщение..."
          disabled={loading || rateLimitCountdown !== null}
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim() || rateLimitCountdown !== null}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {rateLimitCountdown !== null
            ? `⏳ ${rateLimitCountdown}s`
            : "Изпрати"}
        </button>
      </div>
    </div>
  );
}
