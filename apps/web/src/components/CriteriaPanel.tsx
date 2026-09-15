"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type CriteriaJob,
  type CriteriaWorkspace,
  type CriterionCheck,
} from "@/lib/api";
import { useToast } from "@/components/ToastProvider";

interface Props {
  projectId: string;
  refreshKey?: number;
}

const VERDICT_LABELS: Record<string, string> = {
  covered: "изпълнен",
  partial: "частичен",
  missing: "неизпълнен",
  violated: "нарушен",
  unchecked: "непроверен",
};

const VERDICT_BADGE_CLASSES: Record<string, string> = {
  covered: "bg-green-100 text-green-800",
  partial: "bg-amber-100 text-amber-800",
  missing: "bg-red-100 text-red-800",
  violated: "bg-red-200 text-red-900",
  unchecked: "bg-gray-200 text-gray-700",
};

function isActiveJob(job: CriteriaJob | null | undefined): boolean {
  return !!job && (job.status === "queued" || job.status === "processing");
}

export default function CriteriaPanel({ projectId, refreshKey = 0 }: Props) {
  const [workspace, setWorkspace] = useState<CriteriaWorkspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.criteria.get(projectId);
      setWorkspace(data);
      setError(null);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Грешка при зареждане на проверката по критерии",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (isActiveJob(workspace?.latest_job)) {
      pollRef.current = window.setInterval(() => {
        void load();
      }, 4000);
    }
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [workspace?.latest_job, load]);

  const handleStart = async () => {
    setStarting(true);
    setError(null);
    try {
      await api.criteria.start(projectId);
      toast("Проверката по критерии е стартирана.", "success");
      await load();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Грешка при стартиране на проверката",
      );
    } finally {
      setStarting(false);
    }
  };

  const job = workspace?.latest_job ?? null;
  const totals = workspace?.totals ?? {};
  const blockingCount = (totals.missing ?? 0) + (totals.violated ?? 0);
  const issueChecks = (workspace?.checks ?? []).filter(
    (check) => check.verdict !== "covered",
  );

  return (
    <div className="space-y-2 text-sm" data-testid="criteria-panel">
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={handleStart}
          disabled={starting || isActiveJob(job)}
          data-testid="criteria-start-button"
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
        >
          {isActiveJob(job)
            ? "Проверява се..."
            : starting
              ? "Стартира се..."
              : "Провери критериите"}
        </button>
        {loading && <span className="text-xs text-gray-400">Зарежда...</span>}
      </div>

      {isActiveJob(job) && (
        <p className="text-xs text-gray-500" data-testid="criteria-job-progress">
          {`${job?.completed_sections ?? 0}/${job?.total_sections ?? 0} подточки`}
          {job?.current_step ? ` — ${job.current_step}` : ""}
        </p>
      )}
      {job?.status === "error" && (
        <p className="text-xs text-red-600">{job.error}</p>
      )}

      {(totals.total ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1" data-testid="criteria-totals">
          {(["covered", "partial", "missing", "violated", "unchecked"] as const)
            .filter((verdict) => (totals[verdict] ?? 0) > 0)
            .map((verdict) => (
              <span
                key={verdict}
                className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${VERDICT_BADGE_CLASSES[verdict]}`}
              >
                {`${VERDICT_LABELS[verdict]}: ${totals[verdict]}`}
              </span>
            ))}
        </div>
      )}

      {blockingCount > 0 && (
        <p className="text-xs font-medium text-red-700">
          {`${blockingCount} критерия са неизпълнени или нарушени — прегледайте и регенерирайте засегнатите подточки.`}
        </p>
      )}

      {issueChecks.length > 0 && (
        <ul className="max-h-64 space-y-1.5 overflow-y-auto" data-testid="criteria-issues">
          {issueChecks.map((check: CriterionCheck) => (
            <li
              key={check.id}
              className="rounded border border-gray-200 bg-gray-50 px-2 py-1.5"
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={`rounded px-1 py-0.5 text-[10px] font-semibold ${
                    VERDICT_BADGE_CLASSES[check.verdict] ??
                    "bg-gray-200 text-gray-700"
                  }`}
                >
                  {VERDICT_LABELS[check.verdict] ?? check.verdict}
                </span>
                <span className="text-[11px] text-gray-500">
                  {check.criterion_kind}
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-700">{check.criterion_text}</p>
              {check.note && (
                <p className="mt-0.5 text-[11px] text-gray-500">{check.note}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {!loading && (totals.total ?? 0) === 0 && !isActiveJob(job) && (
        <p className="text-xs text-gray-500">
          Няма записани проверки. Стартирайте проверката след генериране на
          текстовете по одобрения план.
        </p>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
