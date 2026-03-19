"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface Props {
  projectId: string;
  projectName: string;
}

export default function ExportButton({ projectId, projectName }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [staleWarning, setStaleWarning] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    setStaleWarning(false);
    try {
      const blob = await api.export.docx(projectId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `TP_${projectName.slice(0, 50).replace(/\s+/g, "_")}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Грешка при експорт";
      // 409 идва с message за остарели секции — показваме предупреждение
      if (msg.toLowerCase().includes("stale")) {
        setStaleWarning(true);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button
        onClick={handleExport}
        disabled={loading}
        className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? "Генерира се..." : "Експорт .docx"}
      </button>

      {staleWarning && (
        <p className="text-amber-600 text-xs mt-1 max-w-xs">
          ⚠ Някои секции имат остаряло доказателство — качете актуализирани
          файлове или регенерирайте преди експорт.
        </p>
      )}
      {error && <p className="text-red-500 text-xs mt-1">{error}</p>}
    </div>
  );
}
