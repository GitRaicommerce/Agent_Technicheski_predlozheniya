"use client";

import { useState } from "react";
import { api, ApiError, type ExportQualitySection } from "@/lib/api";
import { useToast } from "@/components/ToastProvider";

interface Props {
  projectId: string;
  projectName: string;
  onOpenGenerations?: () => void;
  onQualitySectionsBlocked?: (
    sectionUids: string[],
    sections?: ExportQualitySection[],
  ) => void;
}

interface QualityWarningSummary {
  maxBlueprintGroupCount: number | null;
  maxBlueprintRequirementIdCount: number | null;
  maxMinWords: number | null;
  maxWordsPerGroupOrTopic: number | null;
}

export default function ExportButton({
  projectId,
  projectName,
  onOpenGenerations,
  onQualitySectionsBlocked,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicateSelectedWarning, setDuplicateSelectedWarning] = useState(false);
  const [duplicateSelectedCount, setDuplicateSelectedCount] =
    useState<number | null>(null);
  const [staleWarning, setStaleWarning] = useState(false);
  const [staleSectionCount, setStaleSectionCount] = useState<number | null>(null);
  const [missingRequirementWarning, setMissingRequirementWarning] = useState(false);
  const [missingRequirementCount, setMissingRequirementCount] =
    useState<number | null>(null);
  const [missingRequirementGuidance, setMissingRequirementGuidance] = useState<
    string[]
  >([]);
  const [qualityWarning, setQualityWarning] = useState(false);
  const [qualitySectionCount, setQualitySectionCount] = useState<number | null>(null);
  const [qualityWarningSummary, setQualityWarningSummary] =
    useState<QualityWarningSummary | null>(null);
  const { toast } = useToast();
  const qualityWarningDetail = formatQualityWarningSummary(qualityWarningSummary);
  const hasReadinessWarnings =
    duplicateSelectedWarning ||
    staleWarning ||
    missingRequirementWarning ||
    qualityWarning;

  const applyReadinessWarnings = (source: unknown, message = "") => {
    let handled = false;

    if (isDuplicateSelectedExportError(source)) {
      setDuplicateSelectedWarning(true);
      setDuplicateSelectedCount(getDuplicateSelectedCount(source));
      handled = true;
    }
    if (isStaleExportError(source, message)) {
      setStaleWarning(true);
      setStaleSectionCount(getStaleSectionCount(source));
      handled = true;
    }
    if (isRequirementCoverageExportError(source)) {
      setMissingRequirementWarning(true);
      setMissingRequirementCount(getMissingRequirementCount(source));
      setMissingRequirementGuidance(getMissingRequirementGuidance(source));
      handled = true;
    }
    if (isQualityExportError(source)) {
      setQualityWarning(true);
      setQualitySectionCount(getQualitySectionCount(source));
      setQualityWarningSummary(getQualityWarningSummary(source));
      onQualitySectionsBlocked?.(
        getQualitySectionUids(source),
        getQualitySections(source),
      );
      handled = true;
    }

    return handled;
  };

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    setDuplicateSelectedWarning(false);
    setDuplicateSelectedCount(null);
    setStaleWarning(false);
    setStaleSectionCount(null);
    setMissingRequirementWarning(false);
    setMissingRequirementCount(null);
    setMissingRequirementGuidance([]);
    setQualityWarning(false);
    setQualitySectionCount(null);
    setQualityWarningSummary(null);
    onQualitySectionsBlocked?.([], []);

    try {
      const readiness = await api.export.readiness(projectId);
      if (!readiness.ready) {
        if (!applyReadinessWarnings(readiness)) {
          setError(readiness.message ?? "Pre-export readiness check failed.");
        }
        return;
      }

      const blob = await api.export.docx(projectId);
      downloadBlob(
        blob,
        `TP_${projectName.slice(0, 50).replace(/\s+/g, "_")}.docx`,
      );
      toast("DOCX файлът е изтеглен.", "success");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Грешка при експорт";
      if (!applyReadinessWarnings(err, msg)) {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReadinessReport = async () => {
    setReportLoading(true);
    setError(null);

    try {
      const report = await api.export.readinessReport(projectId);
      downloadBlob(
        new Blob([report], { type: "text/markdown;charset=utf-8" }),
        `TP_${projectName.slice(0, 50).replace(/\s+/g, "_")}_readiness.md`,
      );
      toast("Readiness отчетът е изтеглен.", "success");
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Грешка при изтегляне на readiness отчета",
      );
    } finally {
      setReportLoading(false);
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

      {duplicateSelectedWarning && (
        <div
          data-testid="export-duplicate-selected-warning"
          className="mt-1 max-w-xs rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <p>
            {`Има секции с повече от една избрана версия${
              duplicateSelectedCount
                ? ` (${formatDuplicateSelectedCount(duplicateSelectedCount)})`
                : ""
            }. `}
            Оставете само една избрана генерация за всяка секция преди DOCX export.
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
          {missingRequirementGuidance.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {missingRequirementGuidance.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
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

      {qualityWarning && (
        <div
          data-testid="export-quality-warning"
          className="mt-1 max-w-xs rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <p>
            {`Има избрани секции, които са твърде кратки спрямо изискванията${
              qualitySectionCount
                ? ` (${formatQualitySectionCount(qualitySectionCount)})`
                : ""
            }. `}
            Прегледайте генерациите и регенерирайте по-подробен текст преди DOCX export.
          </p>
          {qualityWarningDetail && <p className="mt-1">{qualityWarningDetail}</p>}
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

      {hasReadinessWarnings && (
        <button
          type="button"
          onClick={handleDownloadReadinessReport}
          disabled={reportLoading}
          data-testid="export-readiness-report-button"
          className="mt-2 rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          {reportLoading ? "Изтегля се..." : "Свали readiness report"}
        </button>
      )}

      {error && <p className="text-red-500 text-xs mt-1">{error}</p>}
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function isStaleExportError(err: unknown, message: string): boolean {
  if (message.toLowerCase().includes("stale")) return true;

  const payload = getReadinessPayload(err);
  return (
    !!payload &&
    typeof payload === "object" &&
    (positiveNumber((payload as { stale_section_count?: unknown }).stale_section_count) ||
      nonEmptyArray((payload as { stale_sections?: unknown }).stale_sections))
  );
}

function getStaleSectionCount(err: unknown): number | null {
  const payload = getReadinessPayload(err);
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

function isDuplicateSelectedExportError(err: unknown): boolean {
  const payload = getReadinessPayload(err);
  return (
    !!payload &&
    typeof payload === "object" &&
    (positiveNumber(
      (payload as { duplicate_selected_count?: unknown })
        .duplicate_selected_count,
    ) ||
      nonEmptyArray(
        (payload as { duplicate_selected_sections?: unknown })
          .duplicate_selected_sections,
      ))
  );
}

function getDuplicateSelectedCount(err: unknown): number | null {
  const payload = getReadinessPayload(err);
  if (!payload || typeof payload !== "object") return null;

  const explicitCount = (payload as { duplicate_selected_count?: unknown })
    .duplicate_selected_count;
  if (typeof explicitCount === "number") return explicitCount;

  const sections = (payload as { duplicate_selected_sections?: unknown })
    .duplicate_selected_sections;
  return Array.isArray(sections) ? sections.length : null;
}

function isRequirementCoverageExportError(err: unknown): boolean {
  const payload = getReadinessPayload(err);
  return (
    !!payload &&
    typeof payload === "object" &&
    (positiveNumber(
      (payload as { missing_requirement_count?: unknown })
        .missing_requirement_count,
    ) ||
      nonEmptyArray(
        (payload as { missing_requirement_sections?: unknown })
          .missing_requirement_sections,
      ))
  );
}

function getMissingRequirementCount(err: unknown): number | null {
  const payload = getReadinessPayload(err);
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

function getMissingRequirementGuidance(err: unknown): string[] {
  const payload = getReadinessPayload(err);
  if (!payload || typeof payload !== "object") return [];

  const sections = (payload as { missing_requirement_sections?: unknown })
    .missing_requirement_sections;
  if (!Array.isArray(sections)) return [];

  const guidance: string[] = [];
  for (const section of sections) {
    if (!section || typeof section !== "object") continue;
    const missingItems = (section as { missing_items?: unknown }).missing_items;
    if (!Array.isArray(missingItems)) continue;
    for (const item of missingItems) {
      if (!item || typeof item !== "object") continue;
      const value = (item as { remediation_guidance?: unknown })
        .remediation_guidance;
      if (typeof value === "string" && value.trim()) {
        guidance.push(value.trim());
      }
      if (guidance.length >= 2) return guidance;
    }
  }
  return guidance;
}

function isQualityExportError(err: unknown): boolean {
  const payload = getReadinessPayload(err);
  return (
    !!payload &&
    typeof payload === "object" &&
    (positiveNumber(
      (payload as { quality_section_count?: unknown }).quality_section_count,
    ) ||
      nonEmptyArray((payload as { quality_sections?: unknown }).quality_sections))
  );
}

function getQualitySectionCount(err: unknown): number | null {
  const payload = getReadinessPayload(err);
  if (!payload || typeof payload !== "object") return null;

  const explicitCount = (payload as { quality_section_count?: unknown })
    .quality_section_count;
  if (typeof explicitCount === "number") return explicitCount;

  const sections = (payload as { quality_sections?: unknown }).quality_sections;
  return Array.isArray(sections) ? sections.length : null;
}

function getQualityWarningSummary(err: unknown): QualityWarningSummary | null {
  const payload = getReadinessPayload(err);
  if (!payload || typeof payload !== "object") return null;

  const sections = (payload as { quality_sections?: unknown }).quality_sections;
  if (!Array.isArray(sections)) return null;

  let maxBlueprintGroupCount = 0;
  let maxBlueprintRequirementIdCount = 0;
  let maxMinWords = 0;
  let maxWordsPerGroupOrTopic = 0;
  for (const rawSection of sections) {
    if (!rawSection || typeof rawSection !== "object") continue;
    const section = rawSection as ExportQualitySection;
    if (typeof section.blueprint_group_count === "number") {
      maxBlueprintGroupCount = Math.max(
        maxBlueprintGroupCount,
        section.blueprint_group_count,
      );
    }
    if (typeof section.blueprint_requirement_id_count === "number") {
      maxBlueprintRequirementIdCount = Math.max(
        maxBlueprintRequirementIdCount,
        section.blueprint_requirement_id_count,
      );
    }
    if (typeof section.min_words === "number") {
      maxMinWords = Math.max(maxMinWords, section.min_words);
    }
    if (typeof section.suggested_words_per_structure === "number") {
      maxWordsPerGroupOrTopic = Math.max(
        maxWordsPerGroupOrTopic,
        section.suggested_words_per_structure,
      );
    }
  }

  if (
    maxBlueprintGroupCount <= 0 &&
    maxBlueprintRequirementIdCount <= 0 &&
    maxMinWords <= 0 &&
    maxWordsPerGroupOrTopic <= 0
  ) return null;
  return {
    maxBlueprintGroupCount: maxBlueprintGroupCount || null,
    maxBlueprintRequirementIdCount: maxBlueprintRequirementIdCount || null,
    maxMinWords: maxMinWords || null,
    maxWordsPerGroupOrTopic: maxWordsPerGroupOrTopic || null,
  };
}

function getQualitySections(err: unknown): ExportQualitySection[] {
  const payload = getReadinessPayload(err);
  if (!payload || typeof payload !== "object") return [];

  const sections = (payload as { quality_sections?: unknown }).quality_sections;
  if (!Array.isArray(sections)) return [];

  return sections.filter(
    (section): section is ExportQualitySection =>
      !!section &&
      typeof section === "object" &&
      typeof (section as ExportQualitySection).section_uid === "string",
  );
}

function getQualitySectionUids(err: unknown): string[] {
  const sectionUids = getQualitySections(err).map(
    (section) => section.section_uid,
  );
  return [...new Set(sectionUids)];
}

function formatQualityWarningSummary(
  summary: QualityWarningSummary | null,
): string | null {
  const groupCount = summary?.maxBlueprintGroupCount ?? 0;
  const blueprintRequirementIdCount =
    summary?.maxBlueprintRequirementIdCount ?? 0;
  const wordsPerGroupOrTopic = summary?.maxWordsPerGroupOrTopic ?? 0;
  if (
    groupCount <= 0 &&
    blueprintRequirementIdCount <= 0 &&
    wordsPerGroupOrTopic <= 0
  ) return null;

  const minWords = summary?.maxMinWords ?? 0;
  const minWordsText =
    minWords > 0 ? ` и ориентир поне ${formatWordCount(minWords)}` : "";
  let groupText =
    groupCount > 0
      ? `има ${formatBlueprintGroupCount(groupCount)}`
      : "изисква развита структура";
  if (blueprintRequirementIdCount > 0) {
    groupText += `, ${blueprintRequirementIdCount} checklist id`;
  }
  const wordsPerGroupText =
    wordsPerGroupOrTopic > 0
      ? `, ориентир ${formatWordCount(wordsPerGroupOrTopic)} на група/тема`
      : "";
  return `Най-сложната засечена секция ${groupText}${minWordsText}${wordsPerGroupText}.`;
}

function getReadinessPayload(source: unknown): unknown {
  if (source instanceof ApiError) {
    return getApiErrorPayload(source);
  }
  return source;
}

function positiveNumber(value: unknown): boolean {
  return typeof value === "number" && value > 0;
}

function nonEmptyArray(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0;
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

function formatDuplicateSelectedCount(count: number): string {
  return `${count} ${count === 1 ? "секция" : "секции"}`;
}

function formatRequirementCount(count: number): string {
  return `${count} ${count === 1 ? "изискване" : "изисквания"}`;
}

function formatQualitySectionCount(count: number): string {
  return `${count} ${count === 1 ? "секция" : "секции"}`;
}

function formatBlueprintGroupCount(count: number): string {
  return `${count} ${count === 1 ? "група изисквания" : "групи изисквания"}`;
}

function formatWordCount(count: number): string {
  return `${count} ${count === 1 ? "дума" : "думи"}`;
}
