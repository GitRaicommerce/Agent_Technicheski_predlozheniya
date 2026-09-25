"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PlanAuthorJob } from "@/lib/api";

interface Props {
  projectId: string;
  disabled: boolean;
  onApplied: () => void;
}

const ACTIVE = new Set(["queued", "processing"]);

/** K-26: start the model-assisted plan author and show its outcome. */
export default function PlanAuthorControl({ projectId, disabled, onApplied }: Props) {
  const [job, setJob] = useState<PlanAuthorJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The parent recreates its callback on every render; keep the latest one in
  // a ref so polling does not restart (and refetch) on each render.
  const onAppliedRef = useRef(onApplied);
  useEffect(() => {
    onAppliedRef.current = onApplied;
  }, [onApplied]);
  const statusRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const latest = await api.contentPlan.latestAuthorJob(projectId);
      const previous = statusRef.current;
      statusRef.current = latest?.status ?? null;
      setJob(latest);
      if (previous && ACTIVE.has(previous) && latest?.status === "done") {
        onAppliedRef.current();
      }
    } catch {
      // Not critical for the plan view; the start button reports real errors.
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    api.contentPlan
      .latestAuthorJob(projectId)
      .then((latest) => {
        if (cancelled) return;
        statusRef.current = latest?.status ?? null;
        setJob(latest);
      })
      .catch(() => {
        // Not critical for the plan view; the start button reports real errors.
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const jobStatus = job?.status;
  useEffect(() => {
    if (!jobStatus || !ACTIVE.has(jobStatus)) return;
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [jobStatus, refresh]);

  const start = async () => {
    setError(null);
    try {
      const started = await api.contentPlan.startAuthor(projectId);
      statusRef.current = started.status;
      setJob(started);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Моделното планиране не стартира.");
    }
  };

  const running = job ? ACTIVE.has(job.status) : false;
  const validationErrors = job?.result_json?.validation_errors ?? [];

  return (
    <div className="space-y-1" data-testid="plan-author-control">
      <button
        type="button"
        data-testid="plan-author-start"
        disabled={disabled || running}
        onClick={() => void start()}
        className="w-full rounded border border-indigo-300 bg-indigo-50 px-3 py-1.5 text-xs text-indigo-800 disabled:opacity-50"
      >
        {running ? "Моделът предлага подробен план..." : "Предложи подробен план с AI (използва API кредити)"}
      </button>
      <p className="text-[11px] text-gray-500">
        Задължителните заглавия и номерация остават непроменени. Резултатът е нова
        чернова, която преглеждате и одобрявате Вие.
      </p>
      {job?.status === "error" && (
        <div data-testid="plan-author-error" className="rounded bg-red-50 p-2 text-[11px] text-red-700">
          <p>{job.error}</p>
          {validationErrors.length > 0 && (
            <ul className="mt-1 list-disc pl-4">
              {validationErrors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
          <p className="mt-1">Текущият план не е променен.</p>
        </div>
      )}
      {job?.status === "done" && job.result_json && (
        <p data-testid="plan-author-done" className="text-[11px] text-green-700">
          Добавени подточки: {job.result_json.subpoints_added ?? 0}; разпределени изисквания:{" "}
          {job.result_json.assignments ?? 0}; без получател според модела:{" "}
          {job.result_json.author_unresolved ?? 0}.
        </p>
      )}
      {error && <p className="text-[11px] text-red-600">{error}</p>}
    </div>
  );
}
