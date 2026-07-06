"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  Generation,
  GenerationJob,
  RequirementCoverage,
  RequirementCoverageItem,
  SectionGenerations,
} from "@/lib/api";
import { repairLikelyMojibake } from "@/lib/text";

interface Props {
  projectId: string;
  refreshKey?: number;
}

export default function GenerationsPanel({
  projectId,
  refreshKey = 0,
}: Props) {
  const [sections, setSections] = useState<SectionGenerations[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [regenerating, setRegenerating] = useState<string | null>(null);
  const [selectingGeneration, setSelectingGeneration] = useState<string | null>(
    null,
  );
  const [retryingJob, setRetryingJob] = useState(false);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  const hasLoadedRef = useRef(false);

  const load = useCallback(async () => {
    if (!hasLoadedRef.current) {
      setLoading(true);
    }
    setError(null);
    return Promise.all([
      api.agents.listGenerations(projectId),
      api.agents.latestGenerationJob(projectId),
    ])
      .then(([nextSections, nextJob]) => {
        setSections(nextSections);
        setGenerationJob(nextJob);
      })
      .catch((e: unknown) =>
        setError(
          e instanceof Error ? e.message : "Грешка при зареждане на генерациите.",
        ),
      )
      .finally(() => {
        setLoading(false);
        hasLoadedRef.current = true;
      });
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (
      generationJob?.status !== "queued" &&
      generationJob?.status !== "processing"
    ) {
      return;
    }

    const timer = window.setInterval(() => {
      void load();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [generationJob?.status, load]);

  const toggleSection = (uid: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) {
        next.delete(uid);
      } else {
        next.add(uid);
      }
      return next;
    });
  };

  const handleRegenerate = async (sectionUid: string) => {
    setRegenerating(sectionUid);
    try {
      await api.agents.regenerateSection(projectId, sectionUid);
      await load();
    } catch {
      // Allow a manual retry without blocking the rest of the panel.
    } finally {
      setRegenerating(null);
    }
  };

  const handleSelectGeneration = async (generationId: string) => {
    setSelectingGeneration(generationId);
    setError(null);
    try {
      await api.agents.selectGeneration(projectId, generationId);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation selection failed.");
    } finally {
      setSelectingGeneration(null);
    }
  };

  const handleRetryGenerationJob = async () => {
    setRetryingJob(true);
    try {
      const nextJob = await api.agents.retryGenerationJob(projectId);
      setGenerationJob(nextJob);
      await load();
    } finally {
      setRetryingJob(false);
    }
  };

  if (loading) {
    return (
      <p className="py-2 text-xs text-gray-400 animate-pulse">
        Зареждане на генерациите...
      </p>
    );
  }

  if (error) {
    return (
      <div className="space-y-1">
        <p className="text-xs text-red-400">{error}</p>
        <button
          onClick={load}
          className="text-xs text-blue-500 hover:underline"
        >
          Обнови
        </button>
      </div>
    );
  }

  if (sections.length === 0) {
    return (
      <div className="space-y-1">
        {generationJob && (
          <GenerationJobProgress
            job={generationJob}
            onRetry={handleRetryGenerationJob}
            retrying={retryingJob}
          />
        )}
        <p className="text-xs leading-relaxed text-gray-400">
          Все още няма генерирани текстове. Използвайте TP AI, за да
          генерирате съдържание по одобрения outline.
        </p>
        <button
          onClick={load}
          className="text-xs text-blue-500 hover:underline"
        >
          Обнови
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {generationJob && (
        <GenerationJobProgress
          job={generationJob}
          onRetry={handleRetryGenerationJob}
          retrying={retryingJob}
        />
      )}
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {sections.length} раздела
        </span>
        <button
          onClick={load}
          data-testid="generations-refresh-button"
          className="text-xs text-gray-400 transition hover:text-blue-500"
          title="Обнови"
        >
          ↻
        </button>
      </div>

      {sections.map((section) => {
        const isOpen = expanded.has(section.section_uid);
        const selectedVariants = section.variants.filter(
          (variant) => variant.selected,
        );
        const displayVariant =
          selectedVariants[0] ?? section.variants[0];
        const requirementCoverage = getRequirementCoverage(displayVariant);
        const hasDuplicateSelected = selectedVariants.length > 1;

        return (
          <div
            key={section.section_uid}
            className="overflow-hidden rounded-lg border"
          >
            <div className="flex items-start justify-between bg-gray-50 px-3 py-2 transition hover:bg-gray-100">
              <button
                onClick={() => toggleSection(section.section_uid)}
                data-testid={`generation-section-${section.section_uid}`}
                className="min-w-0 flex-1 text-left"
              >
                <p className="truncate pr-2 text-xs font-medium text-gray-700">
                  {repairLikelyMojibake(section.section_title) ||
                    `${section.section_uid.slice(0, 8)}...`}
                </p>
              </button>
              <div className="flex shrink-0 items-center gap-1">
                {hasDuplicateSelected && (
                  <span
                    data-testid={`generation-duplicate-selected-badge-${section.section_uid}`}
                    className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-700"
                    title="Multiple selected variants"
                  >
                    {selectedVariants.length} selected
                  </span>
                )}
                <RequirementCoverageBadge coverage={requirementCoverage} />
                <button
                  onClick={() => handleRegenerate(section.section_uid)}
                  disabled={regenerating === section.section_uid}
                  data-testid={`generation-regenerate-${section.section_uid}`}
                  className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 transition hover:bg-amber-200 disabled:opacity-50"
                  title="Регенерирай раздела"
                >
                  {regenerating === section.section_uid ? "..." : "↻"}
                </button>
                <span className="text-xs text-gray-400">
                  {isOpen ? "▾" : "▸"}
                </span>
              </div>
            </div>

            {isOpen && displayVariant && (
              <div className="bg-white px-3 py-3">
                <GenerationVariantSelector
                  sectionUid={section.section_uid}
                  variants={section.variants}
                  selectedCount={selectedVariants.length}
                  displayVariantId={displayVariant.id}
                  selectingGeneration={selectingGeneration}
                  onSelect={(generationId) => {
                    void handleSelectGeneration(generationId);
                  }}
                />
                <SectionText
                  variant={displayVariant}
                  requirementCoverage={requirementCoverage}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function GenerationVariantSelector({
  sectionUid,
  variants,
  selectedCount,
  displayVariantId,
  selectingGeneration,
  onSelect,
}: {
  sectionUid: string;
  variants: Generation[];
  selectedCount: number;
  displayVariantId: string;
  selectingGeneration: string | null;
  onSelect: (generationId: string) => void;
}) {
  if (variants.length <= 1 && selectedCount <= 1) return null;

  return (
    <div
      data-testid={`generation-variants-${sectionUid}`}
      className="mb-3 space-y-2"
    >
      {selectedCount > 1 && (
        <div
          data-testid={`generation-duplicate-selected-warning-${sectionUid}`}
          className="rounded border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-red-700"
        >
          This section has {selectedCount} selected variants. Choose one to make
          DOCX export unambiguous.
        </div>
      )}
      <div className="space-y-1">
        {variants.map((variant) => {
          const isDisplayed = variant.id === displayVariantId;
          const isSoleSelected = variant.selected && selectedCount === 1;
          const isSelecting = selectingGeneration === variant.id;

          return (
            <div
              key={variant.id}
              data-testid={`generation-variant-row-${variant.id}`}
              className={`flex items-center justify-between gap-2 rounded border px-2.5 py-2 text-xs ${
                isDisplayed
                  ? "border-blue-200 bg-blue-50"
                  : "border-gray-200 bg-white"
              }`}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-gray-700">
                    Variant {variant.variant}
                  </span>
                  {variant.selected && (
                    <span className="rounded bg-green-100 px-1.5 py-0.5 text-[11px] font-medium text-green-700">
                      Selected
                    </span>
                  )}
                  {variant.evidence_status === "stale" && (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">
                      Stale
                    </span>
                  )}
                </div>
                <p className="mt-1 truncate text-[11px] text-gray-500">
                  {new Date(variant.created_at).toLocaleString()}
                </p>
              </div>
              <button
                type="button"
                data-testid={`generation-select-${variant.id}`}
                onClick={() => onSelect(variant.id)}
                disabled={isSoleSelected || isSelecting}
                className="shrink-0 rounded border border-blue-200 bg-white px-2 py-1 text-[11px] font-medium text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400"
              >
                {isSelecting
                  ? "..."
                  : isSoleSelected
                    ? "Selected"
                    : selectedCount > 1
                      ? "Keep this"
                      : "Select"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GenerationJobProgress({
  job,
  onRetry,
  retrying = false,
}: {
  job: GenerationJob;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const doneCount = job.completed_sections + job.skipped_sections;
  const percent =
    job.total_sections > 0
      ? Math.min(100, Math.round((doneCount / job.total_sections) * 100))
      : job.status === "done"
        ? 100
        : 0;
  const currentTitle = repairLikelyMojibake(job.current_section_title ?? "");
  const error = repairLikelyMojibake(job.error ?? "");
  const isActive = job.status === "queued" || job.status === "processing";
  const statusLabel =
    job.status === "done"
      ? "Готово"
      : job.status === "error"
        ? "Грешка"
        : job.status === "queued"
          ? "В опашка"
          : "Генерира се";

  return (
    <div
      className={`mb-2 rounded-lg border px-3 py-2 text-xs ${
        job.status === "error"
          ? "border-red-200 bg-red-50 text-red-700"
          : isActive
            ? "border-blue-200 bg-blue-50 text-blue-800"
            : "border-green-200 bg-green-50 text-green-700"
      }`}
      data-testid="generation-job-progress"
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium">{statusLabel}</span>
        <span className="shrink-0 tabular-nums">
          {doneCount} / {job.total_sections}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/70">
        <div
          className={`h-full rounded-full transition-all ${
            job.status === "error" ? "bg-red-500" : "bg-blue-500"
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {currentTitle && isActive && (
        <p className="mt-1 truncate text-[11px] opacity-80">{currentTitle}</p>
      )}
      {error && job.status === "error" && (
        <p className="mt-1 text-[11px] opacity-90">{error}</p>
      )}
      {job.status === "error" && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          data-testid="generation-job-retry-button"
          className="mt-2 rounded border border-red-200 bg-white px-2 py-1 text-[11px] font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {retrying ? "..." : "Продължи"}
        </button>
      )}
    </div>
  );
}

function SectionText({
  variant,
  requirementCoverage,
}: {
  variant: Generation;
  requirementCoverage: RequirementCoverage | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const previewLen = 400;
  const text = repairLikelyMojibake(variant.text);
  const isLong = text.length > previewLen;

  return (
    <div>
      <RequirementCoverageDetails
        sectionUid={variant.section_uid}
        coverage={requirementCoverage}
      />
      <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-700">
        {expanded || !isLong ? text : `${text.slice(0, previewLen)}...`}
      </p>
      {isLong && (
        <button
          onClick={() => setExpanded((value) => !value)}
          className="mt-2 text-xs text-blue-500 hover:underline"
        >
          {expanded ? "Покажи по-малко" : "Покажи целия текст"}
        </button>
      )}
    </div>
  );
}

function getRequirementCoverage(
  variant: Generation | undefined,
): RequirementCoverage | null {
  const coverage = variant?.flags_json?.requirement_coverage;
  if (!coverage || typeof coverage !== "object") return null;
  return coverage;
}

function coverageCounts(coverage: RequirementCoverage | null) {
  const total = coverage?.total ?? coverage?.items?.length ?? 0;
  const missing =
    coverage?.missing ??
    coverage?.missing_ids?.length ??
    coverage?.items?.filter((item) => item.status === "missing").length ??
    0;
  const covered = coverage?.covered ?? Math.max(0, total - missing);
  return { total, covered, missing };
}

function missingCoverageItems(
  coverage: RequirementCoverage | null,
): RequirementCoverageItem[] {
  if (!coverage?.items?.length) return [];
  const missingIds = new Set((coverage.missing_ids ?? []).map(String));
  return coverage.items.filter(
    (item) => item.status === "missing" || missingIds.has(String(item.id)),
  );
}

function RequirementCoverageBadge({
  coverage,
}: {
  coverage: RequirementCoverage | null;
}) {
  const { total, covered, missing } = coverageCounts(coverage);
  if (!coverage || total === 0) return null;

  const className =
    missing > 0
      ? "bg-amber-100 text-amber-800"
      : "bg-green-100 text-green-700";

  return (
    <span
      data-testid="generation-requirement-coverage"
      className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${className}`}
      title="Покритие на изискванията"
    >
      {covered}/{total}
    </span>
  );
}

function RequirementCoverageDetails({
  sectionUid,
  coverage,
}: {
  sectionUid: string;
  coverage: RequirementCoverage | null;
}) {
  const { total, covered, missing } = coverageCounts(coverage);
  if (!coverage || total === 0) return null;

  const missingItems = missingCoverageItems(coverage);

  return (
    <div
      data-testid={`generation-requirement-coverage-${sectionUid}`}
      className={`mb-3 rounded border px-2.5 py-2 text-xs ${
        missing > 0
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-green-200 bg-green-50 text-green-800"
      }`}
    >
      <p className="font-medium">
        Изисквания: {covered}/{total} покрити
        {missing > 0 ? `, ${missing} липсват` : ""}
      </p>
      {missingItems.length > 0 && (
        <ul className="mt-1 space-y-1">
          {missingItems.slice(0, 5).map((item) => (
            <li key={item.id}>
              <span className="font-medium">{item.id}</span>
              {item.text ? `: ${repairLikelyMojibake(item.text)}` : ""}
            </li>
          ))}
        </ul>
      )}
      {missingItems.length > 5 && (
        <p className="mt-1 opacity-80">Още {missingItems.length - 5} липсващи точки.</p>
      )}
    </div>
  );
}
