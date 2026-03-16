"use client";

import { useState, useRef, useEffect } from "react";
import { api, ChatMessage, OrchestratorResponse } from "@/lib/api";

interface Props {
  projectId: string;
}

export default function ChatPanel({ projectId }: Props) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const send = async () => {
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    setLoading(true);

    const userMsg: ChatMessage = { role: "user", content: message };
    setHistory((h) => [...h, userMsg]);

    try {
      const res: OrchestratorResponse = await api.agents.chat(
        projectId,
        message,
        [...history, userMsg],
      );
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: res.assistant_message,
      };
      setHistory((h) => [...h, assistantMsg]);
    } catch (err: unknown) {
      const errorMsg: ChatMessage = {
        role: "assistant",
        content: `⚠ Грешка: ${err instanceof Error ? err.message : "Неизвестна грешка"}`,
      };
      setHistory((h) => [...h, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full border rounded-lg bg-white shadow-sm">
      <div className="p-3 border-b font-semibold text-gray-700 bg-gray-50 rounded-t-lg">
        TP AI Оркестратор
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
            <div
              className={`max-w-[80%] px-4 py-2 rounded-2xl text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-br-none"
                  : "bg-gray-100 text-gray-800 rounded-bl-none"
              }`}
            >
              {msg.content}
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

      <div className="p-3 border-t flex gap-2">
        <input
          className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Въведете съобщение..."
          disabled={loading}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Изпрати
        </button>
      </div>
    </div>
  );
}
