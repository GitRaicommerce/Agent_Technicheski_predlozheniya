"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PlanAuditState } from "@/lib/api";

interface Props {
  projectId: string;
  refreshKey?: number;
}

const OVERALL_LABELS: Record<string, string> = {
  passed: "Приет — генерирането е разрешено",
  changes_required: "Нужни са корекции",
  partial: "Непълен — не са прочетени всички източници",
  error: "Грешка — не е приемане",
  stale: "Остарял — планът, документацията или заданието са променени",
};

const VERDICT_LABELS: Record<string, string> = {
  partial: "частично",
  missing: "липсва",
  contradiction: "противоречие",
  ambiguous: "неясно",
  unsupported_addition: "добавено без основание",
};

const ACTIVE = new Set(["queued", "processing"]);

/** K-25: the independent plan audit — precise gaps, not only a badge. */
export default function PlanAuditPanel({ projectId, refreshKey = 0 }: Props) {
  const [state, setState] = useState<PlanAuditState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const statusRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api.planAudit.get(projectId);
      statusRef.current = next.audit?.status ?? null;
      setState(next);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Одитът не бе зареден.");
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    api.planAudit
      .get(projectId)
      .then((next) => {
        if (cancelled) return;
        statusRef.current = next.audit?.status ?? null;
        setState(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Одитът не бе зареден.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, refreshKey]);

  const auditStatus = state?.audit?.status;
  useEffect(() => {
    if (!auditStatus || !ACTIVE.has(auditStatus)) return;
    const timer = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(timer);
  }, [auditStatus, load]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Действието не бе изпълнено.");
    } finally {
      setBusy(false);
    }
  };

  const audit = state?.audit ?? null;
  const report = audit?.report ?? null;
  const running = audit ? ACTIVE.has(audit.status) : false;
  const overall = audit?.overall ?? (audit?.status === "error" ? "error" : null);
  const obligations = new Map(
    (report?.inventory?.obligations ?? []).map((entry) => [entry.id, entry]),
  );
  const planTitles = new Map(
    (report?.plan_snapshot ?? []).map((entry) => [entry.id, `${entry.number} ${entry.title}`]),
  );
  const resolutions = report?.resolutions ?? {};
  const blocking = (report?.findings ?? []).filter(
    (finding) => finding.verdict !== "covered",
  );
  const unsupported = (report?.plan_additions ?? []).filter(
    (entry) => entry.verdict === "unsupported_addition",
  );

  return (
    <div className="space-y-2 text-xs" data-testid="plan-audit-panel">
      <button
        type="button"
        data-testid="plan-audit-start"
        disabled={busy || running}
        onClick={() => void run(() => api.planAudit.start(projectId))}
        className="w-full rounded border border-violet-300 bg-violet-50 px-3 py-1.5 text-violet-900 disabled:opacity-50"
      >
        {running ? "Одитът тече..." : "Независим одит на плана (използва API кредити)"}
      </button>
      <p className="text-[11px] text-gray-500">
        Отделен проверяващ чете документацията без плана, после сравнява плана
        с нея в двете посоки. Генерирането е разрешено само след приет одит на
        точно тази версия на плана, документацията и заданието.
      </p>

      {state && (
        <p
          data-testid="plan-audit-eligibility"
          className={`rounded px-2 py-1 ${state.eligibility.eligible ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"}`}
        >
          {state.eligibility.eligible
            ? "✓ Генерирането е разрешено за текущия план."
            : `Генерирането е блокирано: ${state.eligibility.message ?? state.eligibility.reason}`}
        </p>
      )}

      {audit && overall && !running && (
        <p data-testid="plan-audit-overall" className="font-medium text-gray-800">
          Одит: {OVERALL_LABELS[overall] ?? overall}
          {report?.summary
            ? ` · задължения: ${report.summary.obligations}, решени от човек: ${report.summary.resolved_by_human}`
            : ""}
        </p>
      )}
      {audit?.status === "error" && audit.error && (
        <p className="text-red-600">{audit.error}</p>
      )}

      {report?.coverage && !report.coverage.complete && (
        <div data-testid="plan-audit-coverage" className="rounded bg-red-50 p-2 text-red-800">
          Непрочетени или непълни източници — одитът не може да бъде приет:
          <ul className="mt-1 list-disc pl-4">
            {(report.coverage.missing_or_partial_locations ?? []).map((location, index) => (
              <li key={index}>{JSON.stringify(location)}</li>
            ))}
          </ul>
        </div>
      )}

      {!audit?.stale && (blocking.length > 0 || unsupported.length > 0) && (
        <ul data-testid="plan-audit-findings" className="max-h-80 space-y-1.5 overflow-y-auto">
          {blocking.map((finding) => {
            const source = obligations.get(finding.inventory_id);
            const key = `finding:${finding.inventory_id}`;
            return (
              <FindingItem
                key={key}
                resolutionKey={key}
                verdict={finding.verdict}
                quote={source?.quote}
                page={source?.page}
                targets={finding.plan_item_ids.map((id) => planTitles.get(id) ?? id)}
                correction={finding.required_correction ?? finding.rationale}
                resolved={Boolean(resolutions[key])}
                busy={busy}
                onResolve={(interpretation, reason) =>
                  run(() => api.planAudit.resolve(projectId, audit!.id, { key, interpretation, reason }))
                }
              />
            );
          })}
          {unsupported.map((entry) => {
            const key = `addition:${entry.plan_item_id}`;
            return (
              <FindingItem
                key={key}
                resolutionKey={key}
                verdict="unsupported_addition"
                targets={[planTitles.get(entry.plan_item_id) ?? entry.plan_item_id]}
                correction={entry.required_correction ?? entry.rationale}
                resolved={Boolean(resolutions[key])}
                busy={busy}
                onResolve={(interpretation, reason) =>
                  run(() => api.planAudit.resolve(projectId, audit!.id, { key, interpretation, reason }))
                }
              />
            );
          })}
        </ul>
      )}

      {overall === "changes_required" && audit && !audit.stale && (
        <button
          type="button"
          data-testid="plan-audit-correct"
          disabled={busy}
          onClick={() => void run(() => api.contentPlan.startAuthor(projectId, audit.id))}
          className="w-full rounded border px-3 py-1.5 text-gray-700 disabled:opacity-50"
        >
          Коригирай плана по констатациите (нова версия за повторен одит)
        </button>
      )}
      {error && <p className="text-red-600">{error}</p>}
    </div>
  );
}

function FindingItem({
  resolutionKey,
  verdict,
  quote,
  page,
  targets,
  correction,
  resolved,
  busy,
  onResolve,
}: {
  resolutionKey: string;
  verdict: string;
  quote?: string;
  page?: number | null;
  targets: string[];
  correction?: string | null;
  resolved: boolean;
  busy: boolean;
  onResolve: (interpretation: string, reason: string) => Promise<void>;
}) {
  const [interpretation, setInterpretation] = useState("");
  const [reason, setReason] = useState("");
  return (
    <li className={`rounded border px-2 py-1.5 ${resolved ? "border-gray-200 bg-gray-50" : "border-amber-200 bg-amber-50"}`} data-testid={`plan-audit-${resolutionKey}`}>
      <p className="font-medium">
        {VERDICT_LABELS[verdict] ?? verdict}
        {resolved ? " · решено от човек" : ""}
      </p>
      {quote && (
        <p className="italic text-gray-600">
          „{quote}“{page ? ` (стр. ${page})` : ""}
        </p>
      )}
      <p className="text-gray-600">Точки: {targets.length > 0 ? targets.join("; ") : "няма получател"}</p>
      {correction && <p className="text-gray-700">Корекция: {correction}</p>}
      {!resolved && (
        <div className="mt-1 space-y-1">
          <input
            value={interpretation}
            onChange={(event) => setInterpretation(event.target.value)}
            placeholder="Тълкуване (при истинска двусмисленост)"
            className="w-full rounded border px-1"
          />
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Обосновка (източник, разяснение)"
            className="w-full rounded border px-1"
          />
          <button
            type="button"
            disabled={busy || interpretation.trim().length < 5 || reason.trim().length < 10}
            onClick={() => void onResolve(interpretation, reason)}
            className="rounded border px-2"
          >
            Запиши човешко решение
          </button>
        </div>
      )}
    </li>
  );
}
