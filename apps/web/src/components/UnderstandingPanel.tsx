"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type UnderstandingRequirement,
  type UnderstandingWbsItem,
  type UnderstandingWorkspace,
} from "@/lib/api";

type Tab = "requirements" | "wbs" | "facts";

const KIND_LABELS: Record<string, string> = {
  obligation: "Задължение",
  prohibition: "Забрана",
  format: "Формат",
  content: "Съдържание",
  evaluation: "Оценяване",
  etap: "Етап",
  activity: "Дейност",
  subactivity: "Поддейност",
  task: "Задача",
};

export default function UnderstandingPanel({ projectId }: { projectId: string }) {
  const [workspace, setWorkspace] = useState<UnderstandingWorkspace | null>(null);
  const [tab, setTab] = useState<Tab>("requirements");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [factsText, setFactsText] = useState("{}");

  const load = useCallback(async () => {
    try {
      const result = await api.understanding.get(projectId);
      setWorkspace(result);
      setFactsText(JSON.stringify(result.fact_sheet?.facts_json ?? {}, null, 2));
      setError(null);
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не успях да заредя анализа.",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const job = workspace?.latest_job;
    if (!job || !["queued", "processing"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      const current = await api.understanding.getJob(projectId, job.id);
      setWorkspace((value) => (value ? { ...value, latest_job: current } : value));
      if (["done", "error"].includes(current.status)) void load();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [load, projectId, workspace?.latest_job]);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Действието е неуспешно.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-xs text-gray-500">Зарежда анализ...</p>;

  const job = workspace?.latest_job;
  const jobActive = job && ["queued", "processing"].includes(job.status);

  return (
    <div data-testid="understanding-panel" className="space-y-3 text-xs">
      {error && (
        <p className="rounded border border-red-200 bg-red-50 p-2 text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        data-testid="understanding-start"
        disabled={busy || Boolean(jobActive)}
        onClick={() => act(() => api.understanding.start(projectId))}
        className="w-full rounded-lg bg-blue-600 px-3 py-2 font-medium text-white disabled:opacity-50"
      >
        {jobActive ? "Анализира документацията..." : "Стартирай пълен анализ"}
      </button>
      {job && (
        <div className="rounded border bg-gray-50 p-2 text-gray-600">
          <div className="flex justify-between">
            <span>{job.current_step || (job.status === "done" ? "Анализът е готов" : job.status)}</span>
            <span>{job.completed_batches}/{job.total_batches || "?"}</span>
          </div>
          {job.error && <p className="mt-1 text-red-600">{job.error}</p>}
        </div>
      )}

      <div className="grid grid-cols-3 gap-1" role="tablist" aria-label="Артефакти от анализа">
        {([
          ["requirements", "Изисквания"],
          ["wbs", "Дейности"],
          ["facts", "Fact sheet"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`rounded px-1 py-1.5 ${tab === key ? "bg-blue-100 text-blue-800" : "bg-gray-100 text-gray-600"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "requirements" && workspace && (
        <RequirementsEditor
          projectId={projectId}
          workspace={workspace}
          busy={busy}
          act={act}
          updateLocal={(id, values) =>
            setWorkspace((current) =>
              current
                ? {
                    ...current,
                    requirements: current.requirements.map((item) =>
                      item.id === id ? { ...item, ...values } : item,
                    ),
                  }
                : current,
            )
          }
        />
      )}
      {tab === "wbs" && workspace && (
        <WbsEditor
          projectId={projectId}
          workspace={workspace}
          busy={busy}
          act={act}
          updateLocal={(id, values) =>
            setWorkspace((current) =>
              current
                ? {
                    ...current,
                    wbs_items: current.wbs_items.map((item) =>
                      item.id === id ? { ...item, ...values } : item,
                    ),
                  }
                : current,
            )
          }
        />
      )}
      {tab === "facts" && workspace && (
        <div className="space-y-2">
          <textarea
            aria-label="Fact sheet JSON"
            value={factsText}
            onChange={(event) => setFactsText(event.target.value)}
            rows={14}
            className="w-full rounded border p-2 font-mono text-[11px]"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                act(() => api.understanding.saveFactSheet(projectId, JSON.parse(factsText)))
              }
              className="flex-1 rounded border px-2 py-1.5"
            >
              Запази
            </button>
            <button
              type="button"
              disabled={busy || !workspace.fact_sheet}
              onClick={() => act(() => api.understanding.confirmFactSheet(projectId))}
              className="flex-1 rounded bg-green-600 px-2 py-1.5 text-white disabled:opacity-50"
            >
              Потвърди
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RequirementsEditor({
  projectId,
  workspace,
  busy,
  act,
  updateLocal,
}: {
  projectId: string;
  workspace: UnderstandingWorkspace;
  busy: boolean;
  act: (action: () => Promise<unknown>) => Promise<void>;
  updateLocal: (id: string, values: Partial<UnderstandingRequirement>) => void;
}) {
  const [draft, setDraft] = useState<Partial<UnderstandingRequirement>>({
    kind: "content",
    status: "extracted",
  });
  return (
    <div className="space-y-2">
      {workspace.requirements.map((item) => (
        <div key={item.id} className="rounded border bg-white p-2 space-y-1">
          <textarea
            aria-label="Нормализирано изискване"
            value={item.normalized_text}
            onChange={(event) => updateLocal(item.id, { normalized_text: event.target.value })}
            className="w-full rounded border p-1"
          />
          <p className="text-[10px] text-gray-500">стр. {item.source_page ?? "—"}: „{item.source_quote}“</p>
          <div className="flex gap-1">
            <select
              value={item.kind}
              onChange={(event) => updateLocal(item.id, { kind: event.target.value as UnderstandingRequirement["kind"] })}
              className="min-w-0 flex-1 rounded border p-1"
            >
              {Object.keys(KIND_LABELS).slice(0, 5).map((kind) => <option key={kind} value={kind}>{KIND_LABELS[kind]}</option>)}
            </select>
            <button type="button" disabled={busy} onClick={() => act(() => api.understanding.updateRequirement(projectId, item.id, item))} className="rounded border px-2">Запази</button>
            <button type="button" disabled={busy} aria-label="Изтрий изискване" onClick={() => act(() => api.understanding.deleteRequirement(projectId, item.id))} className="rounded border px-2 text-red-600">×</button>
          </div>
        </div>
      ))}
      <details className="rounded border bg-gray-50 p-2">
        <summary className="cursor-pointer font-medium">Добави изискване</summary>
        <div className="mt-2 space-y-1">
          <select aria-label="Файл-източник" value={draft.source_file_id || ""} onChange={(e) => setDraft({ ...draft, source_file_id: e.target.value })} className="w-full rounded border p-1">
            <option value="">Избери файл-източник</option>
            {workspace.sources.map((source) => <option key={source.id} value={source.id}>{source.filename}</option>)}
          </select>
          <input type="number" placeholder="Страница" value={draft.source_page ?? ""} onChange={(e) => setDraft({ ...draft, source_page: e.target.value ? Number(e.target.value) : null })} className="w-full rounded border p-1" />
          <textarea placeholder="Точен цитат" value={draft.source_quote || ""} onChange={(e) => setDraft({ ...draft, source_quote: e.target.value })} className="w-full rounded border p-1" />
          <textarea placeholder="Нормализирано изискване" value={draft.normalized_text || ""} onChange={(e) => setDraft({ ...draft, normalized_text: e.target.value })} className="w-full rounded border p-1" />
          <button type="button" disabled={busy || !draft.source_file_id || !draft.source_quote || !draft.normalized_text} onClick={() => act(() => api.understanding.createRequirement(projectId, draft as Omit<UnderstandingRequirement, "id" | "project_id" | "created_at">))} className="w-full rounded border px-2 py-1">Добави</button>
        </div>
      </details>
      <button type="button" disabled={busy || workspace.requirements.length === 0} onClick={() => act(() => api.understanding.confirmRequirements(projectId))} className="w-full rounded bg-green-600 px-2 py-1.5 text-white disabled:opacity-50">Потвърди регистъра</button>
    </div>
  );
}

function WbsEditor({ projectId, workspace, busy, act, updateLocal }: { projectId: string; workspace: UnderstandingWorkspace; busy: boolean; act: (action: () => Promise<unknown>) => Promise<void>; updateLocal: (id: string, values: Partial<UnderstandingWbsItem>) => void }) {
  const [newTitle, setNewTitle] = useState("");
  return (
    <div className="space-y-2">
      {workspace.wbs_items.map((item) => (
        <div key={item.id} style={{ marginLeft: `${Math.min(item.level, 4) * 10}px` }} className="rounded border bg-white p-2">
          <input aria-label="Наименование на дейност" value={item.title} onChange={(e) => updateLocal(item.id, { title: e.target.value })} className="w-full rounded border p-1 font-medium" />
          <div className="mt-1 flex gap-1">
            <select value={item.kind} onChange={(e) => updateLocal(item.id, { kind: e.target.value as UnderstandingWbsItem["kind"] })} className="min-w-0 flex-1 rounded border p-1">
              {Object.keys(KIND_LABELS).slice(5).map((kind) => <option key={kind} value={kind}>{KIND_LABELS[kind]}</option>)}
            </select>
            <button type="button" disabled={busy} onClick={() => act(() => api.understanding.updateWbsItem(projectId, item.id, item))} className="rounded border px-2">Запази</button>
            <button type="button" disabled={busy} aria-label="Изтрий дейност" onClick={() => act(() => api.understanding.deleteWbsItem(projectId, item.id))} className="rounded border px-2 text-red-600">×</button>
          </div>
          {item.schedule_task_uid && <p className="mt-1 text-[10px] text-blue-600">График: задача {item.schedule_task_uid}</p>}
        </div>
      ))}
      <div className="flex gap-1">
        <input placeholder="Нова дейност" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} className="min-w-0 flex-1 rounded border p-1" />
        <button type="button" disabled={busy || !newTitle.trim()} onClick={() => act(() => api.understanding.createWbsItem(projectId, { parent_id: null, level: 0, kind: "activity", title: newTitle, description: null, source_refs_json: [], schedule_task_uid: null, order_index: workspace.wbs_items.length, status: "extracted" }))} className="rounded border px-2">Добави</button>
      </div>
      <button type="button" disabled={busy || workspace.wbs_items.length === 0} onClick={() => act(() => api.understanding.confirmWbs(projectId))} className="w-full rounded bg-green-600 px-2 py-1.5 text-white disabled:opacity-50">Потвърди WBS</button>
    </div>
  );
}
