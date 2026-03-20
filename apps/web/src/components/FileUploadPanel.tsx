"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

const MODULE_LABELS: Record<
  string,
  { label: string; icon: string; accept: string; hint: string }
> = {
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
  ingest_error?: string;
}

interface Props {
  projectId: string;
  module: keyof typeof MODULE_LABELS;
}

const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATUSES = new Set(["done", "error"]);

export default function FileUploadPanel({ projectId, module }: Props) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const meta = MODULE_LABELS[module];

  // Derive allowed extensions from meta.accept for client-side validation
  const allowedExts = meta.accept.split(",").map((e) => e.trim().toLowerCase());
  const isAllowedFile = (file: File) =>
    allowedExts.some((ext) => file.name.toLowerCase().endsWith(ext));

  // Зареди съществуващи файлове при mount
  useEffect(() => {
    api.files
      .list(projectId, module)
      .then((loaded) =>
        setFiles(
          loaded.map((f) => ({
            id: f.id,
            filename: f.filename,
            ingest_status: f.ingest_status,
            ingest_error: f.ingest_error,
          })),
        ),
      )
      .catch(() => {
        /* игнорираме — потребителят може да ги качи наново */
      });
  }, [projectId, module]);

  // Poll statuses of non-terminal files
  const pollPending = useCallback(async () => {
    setFiles((prev) => {
      const pending = prev.filter(
        (f) => !TERMINAL_STATUSES.has(f.ingest_status),
      );
      if (!pending.length) return prev;
      Promise.all(
        pending.map((f) =>
          api.files
            .getStatus(projectId, f.id)
            .then((updated) => ({ id: f.id, updated }))
            .catch(() => null),
        ),
      ).then((results) => {
        setFiles((current) =>
          current.map((f) => {
            const r = results.find((x) => x?.id === f.id);
            return r ? { ...f, ...r.updated } : f;
          }),
        );
      });
      return prev;
    });
  }, [projectId]);

  // Start polling when there are pending files, stop when all are terminal
  useEffect(() => {
    const hasPending = files.some(
      (f) => !TERMINAL_STATUSES.has(f.ingest_status),
    );
    if (hasPending && !pollRef.current) {
      pollRef.current = setInterval(pollPending, POLL_INTERVAL_MS);
    } else if (!hasPending && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [files, pollPending]);

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.dataTransfer.files);
    const invalid = droppedFiles.filter((f) => !isAllowedFile(f));
    if (invalid.length) {
      setError(
        `Неподдържан формат: ${invalid.map((f) => f.name).join(", ")}. Допустими: ${meta.accept}`,
      );
      return;
    }
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
          `${file.name}: ${err instanceof Error ? err.message : "Грешка при качване"}`,
        );
      }
    }
    setUploading(false);
  };

  const handleDeleteFile = async (fileId: string) => {
    try {
      await api.files.delete(projectId, fileId);
      setFiles((prev) => prev.filter((f) => f.id !== fileId));
    } catch {
      setError("Грешка при изтриване на файла.");
    }
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
    if (status === "processing") return "⏳ обработва се...";
    return "⌛ на опашка";
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
        <p className="text-xs text-red-500 mt-2 wrap-break-word">{error}</p>
      )}

      {files.length > 0 && (
        <ul className="mt-3 space-y-1">
          {files.map((f) => (
            <li key={f.id} className="text-xs text-gray-600">
              <div className="flex justify-between items-center gap-1">
                <span className="truncate max-w-36" title={f.filename}>
                  {f.filename}
                </span>
                <div className="flex items-center gap-1 shrink-0">
                  <span
                    className={`${statusColor(f.ingest_status)} ${
                      !TERMINAL_STATUSES.has(f.ingest_status)
                        ? "animate-pulse"
                        : ""
                    }`}
                  >
                    {statusLabel(f.ingest_status)}
                  </span>
                  <button
                    onClick={() => handleDeleteFile(f.id)}
                    className="ml-1 text-gray-300 hover:text-red-400 transition"
                    title="Изтрий файл"
                  >
                    ✕
                  </button>
                </div>
              </div>
              {f.ingest_status === "error" && f.ingest_error && (
                <p
                  className="text-red-400 mt-0.5 truncate"
                  title={f.ingest_error}
                >
                  {f.ingest_error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
