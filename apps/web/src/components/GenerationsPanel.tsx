"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, Generation, GenerationJob, SectionGenerations } from "@/lib/api";
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
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  const hasLoadedRef = useRef(false);

  const load = useCallback(() => {
    if (!hasLoadedRef.current) {
      setLoading(true);
    }
    setError(null);
    Promise.all([
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
    load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (
      generationJob?.status !== "queued" &&
      generationJob?.status !== "processing"
    ) {
      return;
    }

    const timer = window.setInterval(load, 2500);
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
        {generationJob && <GenerationJobProgress job={generationJob} />}
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
      {generationJob && <GenerationJobProgress job={generationJob} />}
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
        const displayVariant =
          section.variants.find((variant) => variant.selected) ??
          section.variants[0];

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
              <SectionText variant={displayVariant} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function GenerationJobProgress({ job }: { job: GenerationJob }) {
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
    </div>
  );
}

function SectionText({ variant }: { variant: Generation }) {
  const [expanded, setExpanded] = useState(false);
  const previewLen = 400;
  const text = repairLikelyMojibake(variant.text);
  const isLong = text.length > previewLen;

  return (
    <div className="bg-white px-3 py-3">
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
