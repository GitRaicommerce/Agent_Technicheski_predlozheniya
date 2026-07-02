"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ToastProvider";

interface Props {
  projectId: string;
  projectName: string;
  onOpenGenerations?: () => void;
}

export default function ExportButton({
  projectId,
  projectName,
  onOpenGenerations,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [staleWarning, setStaleWarning] = useState(false);
  const [staleSectionCount, setStaleSectionCount] = useState<number | null>(null);
  const [missingRequirementWarning, setMissingRequirementWarning] = useState(false);
  const [missingRequirementCount, setMissingRequirementCount] =
    useState<number | null>(null);
  const { toast } = useToast();

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    setStaleWarning(false);
    setStaleSectionCount(null);
    setMissingRequirementWarning(false);
    setMissingRequirementCount(null);

    try {
      const blob = await api.export.docx(projectId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `TP_${projectName.slice(0, 50).replace(/\s+/g, "_")}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      toast("DOCX файлът е изтеглен.", "success");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Грешка при експорт";
      if (isRequirementCoverageExportError(err)) {
        setMissingRequirementWarning(true);
        setMissingRequirementCount(getMissingRequirementCount(err));
      } else if (isStaleExportError(err, msg)) {
        setStaleWarning(true);
        setStaleSectionCount(getStaleSectionCount(err));
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
        data-testid="export-docx-button"
        className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? "Генерира се..." : "Експорт .docx"}
      </button>

      {staleWarning && (
        <div
          data-testid="export-stale-warning"
          className="mt-1 max-w-xs rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <p>
            {`Някои секции са генерирани върху по-стара evidence база${
              staleSectionCount
                ? ` (${formatStaleSectionCount(staleSectionCount)})`
                : ""
            }. `}
            Регенерирайте ги преди DOCX export.
          </p>
          {onOpenGenerations && (
            <button
              type="button"
              onClick={onOpenGenerations}
              className="mt-2 rounded border border-amber-300 bg-white px-2 py-1 font-medium text-amber-800 transition hover:bg-amber-100"
            >
              Отвори Генерации
            </button>
          )}
        </div>
      )}

      {missingRequirementWarning && (
        <div
          data-testid="export-requirement-warning"
          className="mt-1 max-w-xs rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <p>
            {`Има непокрити изисквания от документацията${
              missingRequirementCount
                ? ` (${formatRequirementCount(missingRequirementCount)})`
                : ""
            }. `}
            Прегледайте генерациите и регенерирайте засегнатите секции преди DOCX export.
          </p>
          {onOpenGenerations && (
            <button
              type="button"
              onClick={onOpenGenerations}
              className="mt-2 rounded border border-amber-300 bg-white px-2 py-1 font-medium text-amber-800 transition hover:bg-amber-100"
            >
              Отвори Генерации
            </button>
          )}
        </div>
      )}

      {error && <p className="text-red-500 text-xs mt-1">{error}</p>}
    </div>
  );
}

function isStaleExportError(err: unknown, message: string): boolean {
  if (message.toLowerCase().includes("stale")) return true;
  if (!(err instanceof ApiError) || err.status !== 409) return false;

  const payload = getApiErrorPayload(err);
  return (
    !!payload &&
    typeof payload === "object" &&
    Array.isArray((payload as { stale_sections?: unknown }).stale_sections)
  );
}

function getStaleSectionCount(err: unknown): number | null {
  if (!(err instanceof ApiError)) return null;
  const payload = getApiErrorPayload(err);
  if (!payload || typeof payload !== "object") return null;

  const staleSections = (payload as { stale_sections?: unknown }).stale_sections;
  if (!Array.isArray(staleSections)) return null;

  const uniqueSectionIds = staleSections.filter(
    (section): section is string => typeof section === "string" && section.length > 0,
  );
  return uniqueSectionIds.length > 0
    ? new Set(uniqueSectionIds).size
    : staleSections.length;
}

function isRequirementCoverageExportError(err: unknown): boolean {
  if (!(err instanceof ApiError) || err.status !== 409) return false;

  const payload = getApiErrorPayload(err);
  return (
    !!payload &&
    typeof payload === "object" &&
    (Array.isArray(
      (payload as { missing_requirement_sections?: unknown })
        .missing_requirement_sections,
    ) ||
      typeof (payload as { missing_requirement_count?: unknown })
        .missing_requirement_count === "number")
  );
}

function getMissingRequirementCount(err: unknown): number | null {
  if (!(err instanceof ApiError)) return null;
  const payload = getApiErrorPayload(err);
  if (!payload || typeof payload !== "object") return null;

  const explicitCount = (payload as { missing_requirement_count?: unknown })
    .missing_requirement_count;
  if (typeof explicitCount === "number") return explicitCount;

  const sections = (payload as { missing_requirement_sections?: unknown })
    .missing_requirement_sections;
  if (!Array.isArray(sections)) return null;

  const count = sections.reduce((total, section) => {
    if (!section || typeof section !== "object") return total;
    const missingCount = (section as { missing_count?: unknown }).missing_count;
    return total + (typeof missingCount === "number" ? missingCount : 0);
  }, 0);
  return count > 0 ? count : sections.length;
}

function getApiErrorPayload(error: ApiError): unknown {
  const detail = error.detail;
  return detail && typeof detail === "object" && "detail" in detail
    ? (detail as { detail?: unknown }).detail
    : detail;
}

function formatStaleSectionCount(count: number): string {
  return `${count} ${count === 1 ? "секция" : "секции"}`;
}

function formatRequirementCount(count: number): string {
  return `${count} ${count === 1 ? "изискване" : "изисквания"}`;
}
