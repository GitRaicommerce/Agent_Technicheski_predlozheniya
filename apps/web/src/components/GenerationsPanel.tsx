"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  Generation,
  GenerationJob,
  ExportQualitySection,
  RequirementCoverage,
  RequirementCoverageItem,
  SectionGenerations,
} from "@/lib/api";
import { repairLikelyMojibake } from "@/lib/text";

interface Props {
  projectId: string;
  refreshKey?: number;
  focusAttentionKey?: number;
  qualityAttentionSectionUids?: string[];
  qualityAttentionSections?: ExportQualitySection[];
}

export default function GenerationsPanel({
  projectId,
  refreshKey = 0,
  focusAttentionKey = 0,
  qualityAttentionSectionUids = [],
  qualityAttentionSections = [],
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
  const [regeneratingStaleJob, setRegeneratingStaleJob] = useState(false);
  const [regeneratingRequirementsJob, setRegeneratingRequirementsJob] =
    useState(false);
  const [regeneratingQualityJob, setRegeneratingQualityJob] = useState(false);
  const [showOnlyAttention, setShowOnlyAttention] = useState(false);
  const [resolvingDuplicateSelections, setResolvingDuplicateSelections] =
    useState(false);
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
    if (focusAttentionKey > 0) {
      setShowOnlyAttention(true);
    }
  }, [focusAttentionKey]);

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

  const handleRegenerateStaleSections = async () => {
    setRegeneratingStaleJob(true);
    setError(null);
    try {
      const nextJob = await api.agents.regenerateStaleGenerationJob(projectId);
      setGenerationJob(nextJob);
      await load();
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Stale regeneration job failed.",
      );
    } finally {
      setRegeneratingStaleJob(false);
    }
  };

  const handleRegenerateQualitySections = async () => {
    setRegeneratingQualityJob(true);
    setError(null);
    try {
      const nextJob = await api.agents.regenerateQualityGenerationJob(projectId);
      setGenerationJob(nextJob);
      await load();
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Quality regeneration job failed.",
      );
    } finally {
      setRegeneratingQualityJob(false);
    }
  };

  const handleRegenerateMissingRequirementSections = async () => {
    setRegeneratingRequirementsJob(true);
    setError(null);
    try {
      const nextJob =
        await api.agents.regenerateMissingRequirementsGenerationJob(projectId);
      setGenerationJob(nextJob);
      await load();
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Missing requirements regeneration job failed.",
      );
    } finally {
      setRegeneratingRequirementsJob(false);
    }
  };

  const handleResolveDuplicateSelections = async () => {
    if (duplicateSelectionResolutionTargets(sections).length === 0) return;

    setResolvingDuplicateSelections(true);
    setError(null);
    try {
      await api.agents.resolveDuplicateSelectedGenerations(projectId);
      await load();
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Duplicate generation selection failed.",
      );
    } finally {
      setResolvingDuplicateSelections(false);
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

  const qualityAttentionSectionSet = new Set(qualityAttentionSectionUids);
  const qualityAttentionSectionMap = new Map(
    qualityAttentionSections.map((section) => [section.section_uid, section]),
  );
  const attentionSummary = summarizeGenerationAttention(
    sections,
    qualityAttentionSectionSet,
  );
  const shouldFilterAttention =
    showOnlyAttention && attentionSummary.attentionSectionCount > 0;
  const visibleSections = shouldFilterAttention
    ? sections.filter((section) =>
        sectionNeedsAttention(section, qualityAttentionSectionSet),
      )
    : sections;
  const duplicateResolutionTargets =
    duplicateSelectionResolutionTargets(sections);

  return (
    <div className="space-y-1">
      {generationJob && (
        <GenerationJobProgress
          job={generationJob}
          onRetry={handleRetryGenerationJob}
          retrying={retryingJob}
        />
      )}
      <StaleRegenerationAction
        staleSectionCount={countStaleSelectedSections(sections)}
        generationJob={generationJob}
        regenerating={regeneratingStaleJob}
        onRegenerate={() => {
          void handleRegenerateStaleSections();
        }}
      />
      <MissingRequirementsRegenerationAction
        missingRequirementSectionCount={countMissingRequirementSelectedSections(
          sections,
        )}
        generationJob={generationJob}
        regenerating={regeneratingRequirementsJob}
        onRegenerate={() => {
          void handleRegenerateMissingRequirementSections();
        }}
      />
      <QualityRegenerationAction
        qualitySectionCount={qualityAttentionSectionSet.size}
        generationJob={generationJob}
        regenerating={regeneratingQualityJob}
        onRegenerate={() => {
          void handleRegenerateQualitySections();
        }}
      />
      <GenerationAttentionSummary
        summary={attentionSummary}
        showOnlyAttention={shouldFilterAttention}
        onToggle={() => setShowOnlyAttention((value) => !value)}
        duplicateResolutionCount={duplicateResolutionTargets.length}
        resolvingDuplicates={resolvingDuplicateSelections}
        onResolveDuplicates={() => {
          void handleResolveDuplicateSelections();
        }}
      />
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {shouldFilterAttention
            ? `${visibleSections.length} / ${sections.length} секции`
            : `${sections.length} раздела`}
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

      {visibleSections.map((section) => {
        const isOpen = expanded.has(section.section_uid);
        const selectedVariants = section.variants.filter(
          (variant) => variant.selected,
        );
        const displayVariant =
          selectedVariants[0] ?? section.variants[0];
        const requirementCoverage = getRequirementCoverage(displayVariant);
        const attention = getSectionAttention(section, qualityAttentionSectionSet);
        const qualityDetail = qualityAttentionSectionMap.get(section.section_uid);

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
                {attention.hasDuplicateSelected && (
                  <span
                    data-testid={`generation-duplicate-selected-badge-${section.section_uid}`}
                    className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-700"
                    title="Multiple selected variants"
                  >
                    {selectedVariants.length} selected
                  </span>
                )}
                {attention.hasStaleSelected && (
                  <span
                    data-testid={`generation-stale-selected-badge-${section.section_uid}`}
                    className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-700"
                    title="Избраната генерация използва остарели доказателства"
                  >
                    остаряла
                  </span>
                )}
                {attention.hasQualityReviewIssue && (
                  <span
                    data-testid={`generation-quality-attention-badge-${section.section_uid}`}
                    className="rounded bg-blue-100 px-1.5 py-0.5 text-[11px] font-medium text-blue-700"
                    title="Избраната генерация е твърде кратка за export readiness"
                  >
                    кратка
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
                  qualityDetail={qualityDetail}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface GenerationAttentionSummaryData {
  attentionSectionCount: number;
  duplicateSelectedSectionCount: number;
  staleSelectedSectionCount: number;
  missingRequirementSectionCount: number;
  qualityReviewSectionCount: number;
}

function GenerationAttentionSummary({
  summary,
  showOnlyAttention,
  duplicateResolutionCount,
  resolvingDuplicates,
  onToggle,
  onResolveDuplicates,
}: {
  summary: GenerationAttentionSummaryData;
  showOnlyAttention: boolean;
  duplicateResolutionCount: number;
  resolvingDuplicates: boolean;
  onToggle: () => void;
  onResolveDuplicates: () => void;
}) {
  if (summary.attentionSectionCount <= 0) return null;

  return (
    <div
      data-testid="generation-attention-summary"
      className="mb-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <p className="font-medium">
            {summary.attentionSectionCount}{" "}
            {summary.attentionSectionCount === 1
              ? "секция изисква"
              : "секции изискват"}{" "}
            внимание
          </p>
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            {summary.duplicateSelectedSectionCount > 0 && (
              <span className="rounded bg-white px-1.5 py-0.5">
                дублиран избор: {summary.duplicateSelectedSectionCount}
              </span>
            )}
            {summary.staleSelectedSectionCount > 0 && (
              <span className="rounded bg-white px-1.5 py-0.5">
                остарели избрани: {summary.staleSelectedSectionCount}
              </span>
            )}
            {summary.missingRequirementSectionCount > 0 && (
              <span className="rounded bg-white px-1.5 py-0.5">
                липсващи изисквания: {summary.missingRequirementSectionCount}
              </span>
            )}
            {summary.qualityReviewSectionCount > 0 && (
              <span className="rounded bg-white px-1.5 py-0.5">
                кратки секции: {summary.qualityReviewSectionCount}
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onToggle}
          data-testid="generation-attention-filter-toggle"
          className="shrink-0 rounded border border-blue-300 bg-white px-2 py-1 font-medium text-blue-800 transition hover:bg-blue-100"
        >
          {showOnlyAttention ? "Покажи всички" : "Покажи проблемните"}
        </button>
        {duplicateResolutionCount > 0 && (
          <button
            type="button"
            onClick={onResolveDuplicates}
            disabled={resolvingDuplicates}
            data-testid="generation-resolve-duplicates-latest-button"
            className="shrink-0 rounded border border-red-300 bg-white px-2 py-1 font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
            title="Оставя само най-новата избрана версия във всяка секция с дублиран избор"
          >
            {resolvingDuplicates ? "Поправя..." : "Остави най-новите"}
          </button>
        )}
      </div>
    </div>
  );
}

function StaleRegenerationAction({
  staleSectionCount,
  generationJob,
  regenerating,
  onRegenerate,
}: {
  staleSectionCount: number;
  generationJob: GenerationJob | null;
  regenerating: boolean;
  onRegenerate: () => void;
}) {
  const isActive =
    generationJob?.status === "queued" || generationJob?.status === "processing";

  if (staleSectionCount <= 0) return null;

  return (
    <div
      data-testid="generation-stale-selected-action"
      className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
    >
      <div className="flex items-center justify-between gap-2">
        <span>
          {staleSectionCount} selected stale{" "}
          {staleSectionCount === 1 ? "section" : "sections"}
        </span>
        <button
          type="button"
          onClick={onRegenerate}
          disabled={regenerating || isActive}
          data-testid="generation-stale-regenerate-button"
          className="shrink-0 rounded border border-amber-300 bg-white px-2 py-1 font-medium text-amber-800 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {regenerating ? "..." : "Regenerate"}
        </button>
      </div>
    </div>
  );
}

function MissingRequirementsRegenerationAction({
  missingRequirementSectionCount,
  generationJob,
  regenerating,
  onRegenerate,
}: {
  missingRequirementSectionCount: number;
  generationJob: GenerationJob | null;
  regenerating: boolean;
  onRegenerate: () => void;
}) {
  const isActive =
    generationJob?.status === "queued" || generationJob?.status === "processing";

  if (missingRequirementSectionCount <= 0) return null;

  return (
    <div
      data-testid="generation-missing-requirements-action"
      className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
    >
      <div className="flex items-center justify-between gap-2">
        <span>
          {missingRequirementSectionCount} missing-requirement{" "}
          {missingRequirementSectionCount === 1 ? "section" : "sections"}
        </span>
        <button
          type="button"
          onClick={onRegenerate}
          disabled={regenerating || isActive}
          data-testid="generation-missing-requirements-regenerate-button"
          className="shrink-0 rounded border border-amber-300 bg-white px-2 py-1 font-medium text-amber-800 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {regenerating ? "..." : "Regenerate coverage"}
        </button>
      </div>
    </div>
  );
}

function QualityRegenerationAction({
  qualitySectionCount,
  generationJob,
  regenerating,
  onRegenerate,
}: {
  qualitySectionCount: number;
  generationJob: GenerationJob | null;
  regenerating: boolean;
  onRegenerate: () => void;
}) {
  const isActive =
    generationJob?.status === "queued" || generationJob?.status === "processing";

  if (qualitySectionCount <= 0) return null;

  return (
    <div
      data-testid="generation-quality-selected-action"
      className="mb-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900"
    >
      <div className="flex items-center justify-between gap-2">
        <span>
          {qualitySectionCount} short/depth-blocked{" "}
          {qualitySectionCount === 1 ? "section" : "sections"}
        </span>
        <button
          type="button"
          onClick={onRegenerate}
          disabled={regenerating || isActive}
          data-testid="generation-quality-regenerate-button"
          className="shrink-0 rounded border border-blue-300 bg-white px-2 py-1 font-medium text-blue-800 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {regenerating ? "..." : "Regenerate detailed"}
        </button>
      </div>
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

interface DuplicateSelectionResolutionTarget {
  sectionUid: string;
  generationId: string;
}

function duplicateSelectionResolutionTargets(
  sections: SectionGenerations[],
): DuplicateSelectionResolutionTarget[] {
  return sections
    .map((section) => {
      const selectedVariants = section.variants.filter(
        (variant) => variant.selected,
      );
      if (selectedVariants.length <= 1) return null;

      const latestSelected = selectedVariants.reduce((latest, variant) =>
        compareGenerationRecency(variant, latest) >= 0 ? variant : latest,
      );
      return {
        sectionUid: section.section_uid,
        generationId: latestSelected.id,
      };
    })
    .filter(
      (target): target is DuplicateSelectionResolutionTarget =>
        target !== null,
    );
}

function compareGenerationRecency(left: Generation, right: Generation): number {
  const leftTime = Date.parse(left.created_at);
  const rightTime = Date.parse(right.created_at);
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) {
    const timeDiff = leftTime - rightTime;
    if (timeDiff !== 0) return timeDiff;
  } else if (Number.isFinite(leftTime)) {
    return 1;
  } else if (Number.isFinite(rightTime)) {
    return -1;
  }

  const leftVariant = Number(left.variant);
  const rightVariant = Number(right.variant);
  if (Number.isFinite(leftVariant) && Number.isFinite(rightVariant)) {
    const variantDiff = leftVariant - rightVariant;
    if (variantDiff !== 0) return variantDiff;
  }

  return left.id.localeCompare(right.id);
}

function countStaleSelectedSections(sections: SectionGenerations[]): number {
  return sections.filter((section) =>
    getSectionAttention(section).hasStaleSelected,
  ).length;
}

function countMissingRequirementSelectedSections(
  sections: SectionGenerations[],
): number {
  return sections.filter((section) => {
    const selectedVariants = section.variants.filter((variant) => variant.selected);
    const displayVariant = selectedVariants[0] ?? section.variants[0];
    const { missing } = coverageCounts(getRequirementCoverage(displayVariant));
    return missing > 0;
  }).length;
}

function summarizeGenerationAttention(
  sections: SectionGenerations[],
  qualityAttentionSectionUids: Set<string>,
): GenerationAttentionSummaryData {
  return sections.reduce<GenerationAttentionSummaryData>(
    (summary, section) => {
      const attention = getSectionAttention(section, qualityAttentionSectionUids);
      if (sectionAttentionCount(attention) > 0) {
        summary.attentionSectionCount += 1;
      }
      if (attention.hasDuplicateSelected) {
        summary.duplicateSelectedSectionCount += 1;
      }
      if (attention.hasStaleSelected) {
        summary.staleSelectedSectionCount += 1;
      }
      if (attention.hasMissingRequirementCoverage) {
        summary.missingRequirementSectionCount += 1;
      }
      if (attention.hasQualityReviewIssue) {
        summary.qualityReviewSectionCount += 1;
      }
      return summary;
    },
    {
      attentionSectionCount: 0,
      duplicateSelectedSectionCount: 0,
      staleSelectedSectionCount: 0,
      missingRequirementSectionCount: 0,
      qualityReviewSectionCount: 0,
    },
  );
}

function sectionNeedsAttention(
  section: SectionGenerations,
  qualityAttentionSectionUids: Set<string>,
): boolean {
  return (
    sectionAttentionCount(getSectionAttention(section, qualityAttentionSectionUids)) >
    0
  );
}

function sectionAttentionCount(attention: {
  hasDuplicateSelected: boolean;
  hasStaleSelected: boolean;
  hasMissingRequirementCoverage: boolean;
  hasQualityReviewIssue: boolean;
}): number {
  return [
    attention.hasDuplicateSelected,
    attention.hasStaleSelected,
    attention.hasMissingRequirementCoverage,
    attention.hasQualityReviewIssue,
  ].filter(Boolean).length;
}

function getSectionAttention(
  section: SectionGenerations,
  qualityAttentionSectionUids = new Set<string>(),
) {
  const selectedVariants = section.variants.filter((variant) => variant.selected);
  const displayVariant = selectedVariants[0] ?? section.variants[0];
  const { missing } = coverageCounts(getRequirementCoverage(displayVariant));

  return {
    hasDuplicateSelected: selectedVariants.length > 1,
    hasStaleSelected: selectedVariants.some(
      (variant) => variant.evidence_status === "stale",
    ),
    hasMissingRequirementCoverage: missing > 0,
    hasQualityReviewIssue: qualityAttentionSectionUids.has(section.section_uid),
  };
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
  qualityDetail,
}: {
  variant: Generation;
  requirementCoverage: RequirementCoverage | null;
  qualityDetail?: ExportQualitySection;
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
      <QualityDepthDetails sectionUid={variant.section_uid} detail={qualityDetail} />
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

function QualityDepthDetails({
  sectionUid,
  detail,
}: {
  sectionUid: string;
  detail?: ExportQualitySection;
}) {
  if (!detail) return null;

  const diagnostics = qualityDepthDiagnostics(detail);
  if (!diagnostics.length) return null;

  return (
    <div
      data-testid={`generation-quality-depth-${sectionUid}`}
      className="mb-3 rounded border border-blue-200 bg-blue-50 px-2.5 py-2 text-xs text-blue-900"
    >
      <p className="font-medium">Дълбочина за export readiness</p>
      <p className="mt-0.5 text-[11px] opacity-80">{diagnostics.join(" · ")}</p>
    </div>
  );
}

function qualityDepthDiagnostics(detail: ExportQualitySection): string[] {
  const diagnostics: string[] = [];
  if (
    typeof detail.word_count === "number" &&
    typeof detail.min_words === "number"
  ) {
    diagnostics.push(`${detail.word_count}/${detail.min_words} думи`);
  } else if (typeof detail.min_words === "number") {
    diagnostics.push(`минимум ${detail.min_words} думи`);
  }
  if (
    typeof detail.sentence_count === "number" &&
    typeof detail.min_sentences === "number" &&
    detail.min_sentences > 0
  ) {
    diagnostics.push(`${detail.sentence_count}/${detail.min_sentences} развити изречения`);
  }
  if (typeof detail.blueprint_group_count === "number") {
    diagnostics.push(`${detail.blueprint_group_count} групи`);
  }
  if (typeof detail.blueprint_topic_count === "number") {
    diagnostics.push(`${detail.blueprint_topic_count} теми`);
  }
  if (typeof detail.blueprint_requirement_id_count === "number") {
    diagnostics.push(`${detail.blueprint_requirement_id_count} checklist id`);
  }
  if (typeof detail.suggested_words_per_structure === "number") {
    diagnostics.push(`${detail.suggested_words_per_structure} думи на група/тема`);
  }
  diagnostics.push(...qualityIssueLabels(detail));
  const structureCoverage = detail.structure_coverage;
  if (
    structureCoverage &&
    typeof structureCoverage.covered_count === "number" &&
    typeof structureCoverage.required_count === "number" &&
    structureCoverage.required_count > 0
  ) {
    diagnostics.push(
      `${structureCoverage.covered_count}/${structureCoverage.required_count} покрити групи/теми`,
    );
    const missingLabels = Array.isArray(structureCoverage.missing)
      ? structureCoverage.missing
          .map((item) => structureMissingLabel(item))
          .filter(
            (label): label is string =>
              typeof label === "string" && label.length > 0,
          )
          .slice(0, 4)
      : [];
    if (missingLabels.length > 0) {
      diagnostics.push(`липсват: ${missingLabels.join(", ")}`);
    }
  }
  return diagnostics;
}

function structureMissingLabel(
  item:
    | {
        label?: string;
        terms?: string[];
        matched_terms?: string[];
        required_terms?: number;
      }
    | undefined,
): string {
  const label = item?.label;
  if (typeof label !== "string" || label.length === 0) return "";

  const matchedTerms = Array.isArray(item?.matched_terms)
    ? item.matched_terms.filter(
        (term): term is string => typeof term === "string" && term.length > 0,
      )
    : [];
  const termCount = Array.isArray(item?.terms)
    ? item.terms.filter((term) => typeof term === "string" && term.length > 0)
        .length
    : 0;
  const requiredTerms =
    typeof item?.required_terms === "number" && item.required_terms > 0
      ? item.required_terms
      : termCount;

  if (requiredTerms <= 0 && matchedTerms.length === 0) return label;

  const suffix = matchedTerms.length
    ? ` (${matchedTerms.length}/${requiredTerms}: ${matchedTerms
        .slice(0, 5)
        .join(", ")})`
    : ` (0/${requiredTerms})`;
  return `${label}${suffix}`;
}

function qualityIssueLabels(detail: ExportQualitySection): string[] {
  const labels: Record<string, string> = {
    too_short_for_requirements: "С‚РІСЉСЂРґРµ РєСЂР°С‚РєРѕ Р·Р° РёР·РёСЃРєРІР°РЅРёСЏС‚Р°",
    too_few_developed_sentences: "РјР°Р»РєРѕ СЂР°Р·РІРёС‚Рё РёР·СЂРµС‡РµРЅРёСЏ",
    uneven_blueprint_distribution: "РЅРµСЂР°РІРЅРѕРјРµСЂРЅРѕ РїРѕРєСЂРёС‚РёРµ РЅР° С‚РµРјРёС‚Рµ",
    repetitive_content: "РїРѕРІС‚Р°СЂСЏС‰ СЃРµ С‚РµРєСЃС‚",
  };
  const issues = Array.isArray(detail.issues) ? detail.issues : [];
  return [
    ...new Set(
      issues
        .map((issue) => {
          const code =
            issue && typeof issue === "object"
              ? (issue as { code?: unknown }).code
              : null;
          return typeof code === "string" ? labels[code] || code : "";
        })
        .filter((label) => label.length > 0),
    ),
  ];
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

function requirementCoverageReasonLabel(item: RequirementCoverageItem): string | null {
  const reason = String(item.reason ?? item.reasons?.[0] ?? "");
  if (reason === "needs operational evidence") {
    return "липсват оперативни доказателства";
  }
  if (reason === "needs coherent passage") {
    return "липсва свързан пасаж";
  }
  if (reason === "missing key terms") {
    return "липсват ключови термини";
  }
  if (reason === "missing distinctive requirement detail") {
    return "липсва отличителен детайл";
  }
  if (reason === "missing requirement coverage") {
    return "липсва покритие";
  }
  if (item.requires_operational_detail) {
    return "липсват оперативни доказателства";
  }
  return null;
}

function requirementCoverageReasonLabels(item: RequirementCoverageItem): string[] {
  const reasons = item.reasons?.length
    ? item.reasons
    : item.reason
      ? [item.reason]
      : [];
  const labels = reasons
    .map((reason) => requirementCoverageReasonLabel({ ...item, reason }))
    .filter((label): label is string => Boolean(label));
  return Array.from(new Set(labels));
}

function requirementCoverageDiagnostics(item: RequirementCoverageItem): string | null {
  const diagnostics: string[] = [];
  if (typeof item.matched_ratio === "number") {
    diagnostics.push(`термини ${Math.round(item.matched_ratio * 100)}%`);
  }
  if (typeof item.coherent_matched_ratio === "number") {
    diagnostics.push(`свързаност ${Math.round(item.coherent_matched_ratio * 100)}%`);
  }
  if (
    typeof item.required_operational_signal_count === "number" &&
    item.required_operational_signal_count > 0
  ) {
    diagnostics.push(
      `оперативни сигнали ${(item.operational_signals ?? []).length}/${item.required_operational_signal_count}`,
    );
  }
  if (
    typeof item.required_distinctive_count === "number" &&
    item.required_distinctive_count > 0
  ) {
    diagnostics.push(
      `отличителни детайли ${(item.distinctive_matches ?? []).length}/${item.required_distinctive_count}`,
    );
    if (item.distinctive_terms?.length) {
      diagnostics.push(`отличаващи: ${item.distinctive_terms.slice(0, 5).join(", ")}`);
    }
  }
  return diagnostics.length ? diagnostics.join(" · ") : null;
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
              {requirementCoverageReasonLabels(item).slice(0, 3).map((label) => (
                <span
                  key={label}
                  className="ml-1 rounded bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-800"
                >
                  {label}
                </span>
              ))}
              {item.text ? `: ${repairLikelyMojibake(item.text)}` : ""}
              {requirementCoverageDiagnostics(item) ? (
                <p className="mt-0.5 text-[11px] opacity-75">
                  {requirementCoverageDiagnostics(item)}
                </p>
              ) : null}
              {item.remediation_guidance ? (
                <p className="mt-0.5 text-[11px] font-medium text-amber-800">
                  Repair: {repairLikelyMojibake(item.remediation_guidance)}
                </p>
              ) : null}
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
