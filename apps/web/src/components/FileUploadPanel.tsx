"use client";

import { useState, useRef } from "react";
import { api } from "@/lib/api";

const MODULE_LABELS: Record<string, { label: string; icon: string; accept: string; hint: string }> = {
  examples: {
    label: "Примерни ТП",
    icon: "📄",
    accept: ".pdf,.docx,.doc",
    hint: "Качете PDF или DOCX файлове с предишни технически предложения",
  },
  tender_docs: {
    label: "Тръжна документация",
    icon: "📋",
    accept: ".pdf,.docx,.doc",
    hint: "Техническа спецификация, задание и критерии за оценка",
  },
  schedule: {
    label: "Линеен график",
    icon: "📅",
    accept: ".mpp,.xlsx,.xls,.pdf",
    hint: "MS Project (.mpp), Excel или PDF export на графика",
  },
  legislation: {
    label: "Законодателство",
    icon: "⚖️",
    accept: ".pdf,.docx",
    hint: "Нормативни актове, наредби и технически норми",
  },
};

interface UploadedFile {
  id: string;
  filename: string;
  ingest_status: string;
}

interface Props {
  projectId: string;
  module: keyof typeof MODULE_LABELS;
}

export default function FileUploadPanel({ projectId, module }: Props) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const meta = MODULE_LABELS[module];

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.dataTransfer.files);
    await uploadFiles(droppedFiles);
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || []);
    await uploadFiles(selected);
    if (inputRef.current) inputRef.current.value = "";
  };

  const uploadFiles = async (fileList: File[]) => {
    if (!fileList.length) return;
    setUploading(true);
    setError(null);

    for (const file of fileList) {
      try {
        const uploaded = await api.files.upload(projectId, module, file);
        setFiles((prev) => [...prev, uploaded]);
      } catch (err: unknown) {
        setError(
          `${file.name}: ${err instanceof Error ? err.message : "Грешка при качване"}`
        );
      }
    }
    setUploading(false);
  };

  const statusColor = (status: string) => {
    if (status === "done") return "text-green-600";
    if (status === "error") return "text-red-500";
    if (status === "processing") return "text-yellow-500";
    return "text-gray-400";
  };

  const statusLabel = (status: string) => {
    if (status === "done") return "✓ готово";
    if (status === "error") return "✗ грешка";
    if (status === "processing") return "⏳ обработва се";
    return "⌛ изчаква";
  };

  return (
    <div
      className="border-2 border-dashed border-gray-200 rounded-xl p-4 bg-gray-50 hover:border-blue-300 transition"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{meta.icon}</span>
        <span className="font-medium text-sm text-gray-700">{meta.label}</span>
      </div>
      <p className="text-xs text-gray-400 mb-3">{meta.hint}</p>

      <button
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="w-full py-2 px-3 bg-white border rounded-lg text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50 transition"
      >
        {uploading ? "Качва се..." : "Избери файл или плъзни тук"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={meta.accept}
        multiple
        className="hidden"
        onChange={handleChange}
      />

      {error && (
        <p className="text-xs text-red-500 mt-2 break-words">{error}</p>
      )}

      {files.length > 0 && (
        <ul className="mt-3 space-y-1">
          {files.map((f) => (
            <li
              key={f.id}
              className="flex justify-between items-center text-xs text-gray-600"
            >
              <span className="truncate max-w-[160px]" title={f.filename}>
                {f.filename}
              </span>
              <span className={statusColor(f.ingest_status)}>
                {statusLabel(f.ingest_status)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
