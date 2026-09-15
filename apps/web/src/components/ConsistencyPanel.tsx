"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ConsistencyConflict, type ConsistencyJob } from "@/lib/api";
import { useToast } from "@/components/ToastProvider";

interface Props {
  projectId: string;
  refreshKey?: number;
}

const KIND_LABELS: Record<string, string> = {
  cross_section: "между раздели",
  schedule: "спрямо графика",
  fact_sheet: "спрямо фактите",
};

function isActiveJob(job: ConsistencyJob | null | undefined): boolean {
  return !!job && (job.status === "queued" || job.status === "processing");
}

export default function ConsistencyPanel({ projectId, refreshKey = 0 }: Props) {
  const [job, setJob] = useState<ConsistencyJob | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const latest = await api.consistency.getLatest(projectId);
      setJob(latest);
      setError(null);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Грешка при зареждане на проверката за съгласуваност",
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
    if (isActiveJob(job)) {
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
  }, [job, load]);

  const handleStart = async () => {
    setStarting(true);
    setError(null);
    try {
      await api.consistency.start(projectId);
      toast("Проверката за съгласуваност е стартирана.", "success");
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

  const handleDownloadReport = async () => {
    try {
      const report = await api.consistency.report(projectId);
      const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "consistency_report.md";
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Грешка при изтегляне на доклада",
      );
    }
  };

  const report = job?.status === "done" ? job.result_json : null;
  const conflicts: ConsistencyConflict[] = report?.conflicts ?? [];
  const criticalCount = report?.critical_count ?? 0;
  const warningCount = report?.warning_count ?? 0;

  return (
    <div className="space-y-2 text-sm" data-testid="consistency-panel">
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={handleStart}
          disabled={starting || isActiveJob(job)}
          data-testid="consistency-start-button"
          className="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-teal-700 disabled:opacity-50"
        >
          {isActiveJob(job)
            ? "Проверява се..."
            : starting
              ? "Стартира се..."
              : "Провери съгласуваността"}
        </button>
        {loading && <span className="text-xs text-gray-400">Зарежда...</span>}
      </div>

      {isActiveJob(job) && (
        <p
          className="text-xs text-gray-500"
          data-testid="consistency-job-progress"
        >
          {`${job?.completed_sections ?? 0}/${job?.total_sections ?? 0} стъпки`}
          {job?.current_step ? ` — ${job.current_step}` : ""}
        </p>
      )}
      {job?.status === "error" && (
        <p className="text-xs text-red-600">{job.error}</p>
      )}

      {report && (
        <div className="space-y-1.5" data-testid="consistency-summary">
          <div className="flex flex-wrap gap-1">
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-700">
              {`проверени раздели: ${report.checked_section_count ?? 0}`}
            </span>
            {criticalCount > 0 && (
              <span className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-800">
                {`критични: ${criticalCount}`}
              </span>
            )}
            {warningCount > 0 && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-800">
                {`предупреждения: ${warningCount}`}
              </span>
            )}
            {criticalCount === 0 && warningCount === 0 && (
              <span className="rounded bg-green-100 px-1.5 py-0.5 text-[11px] font-medium text-green-800">
                без противоречия
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={handleDownloadReport}
            data-testid="consistency-report-button"
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
          >
            Свали доклада
          </button>
        </div>
      )}

      {conflicts.length > 0 && (
        <ul
          className="max-h-64 space-y-1.5 overflow-y-auto"
          data-testid="consistency-conflicts"
        >
          {conflicts.map((conflict, index) => (
            <li
              key={`${conflict.topic}-${index}`}
              className={`rounded border px-2 py-1.5 ${
                conflict.severity === "critical"
                  ? "border-red-200 bg-red-50"
                  : "border-amber-200 bg-amber-50"
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={`rounded px-1 py-0.5 text-[10px] font-semibold ${
                    conflict.severity === "critical"
                      ? "bg-red-200 text-red-900"
                      : "bg-amber-200 text-amber-900"
                  }`}
                >
                  {conflict.severity === "critical" ? "критично" : "предупреждение"}
                </span>
                <span className="text-[11px] text-gray-500">
                  {KIND_LABELS[conflict.kind] ?? conflict.kind}
                </span>
              </div>
              <p className="mt-1 text-xs font-medium text-gray-800">
                {conflict.topic}
              </p>
              <p className="mt-0.5 text-[11px] text-gray-600">
                {conflict.explanation}
              </p>
              {conflict.statements.map((statement, statementIndex) => (
                <p
                  key={`${statement.section_uid}-${statementIndex}`}
                  className="mt-0.5 text-[11px] text-gray-500"
                >
                  {`${statement.section_title || statement.section_uid}: „${statement.quote}“`}
                </p>
              ))}
            </li>
          ))}
        </ul>
      )}

      {!loading && !job && (
        <p className="text-xs text-gray-500">
          Няма изпълнена проверка. Стартирайте я след генериране на текстовете,
          за да откриете противоречия между разделите, графика и фактите.
        </p>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
