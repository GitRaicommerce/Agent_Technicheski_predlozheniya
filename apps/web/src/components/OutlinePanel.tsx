"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type ContentPlan,
  type ContentPlanCriterion,
  type ContentPlanItem,
  type TpOutline,
} from "@/lib/api";

interface Props {
  projectId: string;
  refreshKey?: number;
}

export default function OutlinePanel({ projectId, refreshKey = 0 }: Props) {
  const [plan, setPlan] = useState<ContentPlan | null>(null);
  const [legacyOutline, setLegacyOutline] = useState<TpOutline | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [contentPlan, outline] = await Promise.all([
        api.contentPlan.get(projectId),
        api.agents.getOutline(projectId),
      ]);
      setPlan(contentPlan);
      setLegacyOutline(outline);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Грешка при зареждане на плана.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [projectId, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (action: () => Promise<ContentPlan>) => {
    setBusy(true);
    setError(null);
    try {
      setPlan(await action());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Операцията не бе изпълнена.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="py-2 text-xs text-gray-400 animate-pulse">Зарежда се планът на ТП...</p>;

  if (!plan) {
    const legacy = legacyOutline && legacyOutline.outline_json.source !== "understanding_content_plan";
    return (
      <div className="space-y-2">
        {legacy && (
          <p data-testid="legacy-outline-warning" className="rounded bg-amber-50 p-2 text-xs text-amber-800">
            Съществува стар план v{legacyOutline.version}, който не е създаден от потвърденото „Разбиране на изискванията“. Той няма да бъде използван след създаването на Phase 2 плана.
          </p>
        )}
        <p className="text-xs leading-relaxed text-gray-500">
          Създайте подробен план раздел → подточка от потвърдените изисквания към ТП, WBS и fact sheet. Операцията е детерминистична и не използва API кредити.
        </p>
        <button
          type="button"
          data-testid="content-plan-build-button"
          disabled={busy}
          onClick={() => act(() => api.contentPlan.build(projectId))}
          className="w-full rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          {busy ? "Създава се..." : "Създай план от Разбиране"}
        </button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    );
  }

  const roots = plan.items.filter((item) => !item.parent_id);
  const generatableCount = plan.items.filter((item) => item.generation_uid).length;
  const understandingReady =
    plan.understanding_status.wbs_confirmed &&
    plan.understanding_status.fact_sheet_confirmed;

  return (
    <div className="space-y-2" data-testid="content-plan-editor">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">
          Phase 2 · v{plan.version} · {plan.items.length} точки · {generatableCount} работни подточки
        </span>
        <button type="button" onClick={() => void load()} className="text-gray-400 hover:text-blue-600">↻</button>
      </div>
      <p className="rounded bg-blue-50 p-2 text-[11px] text-blue-800">
        Задължителната номерация и заглавия са възпроизведени директно от минималното съдържание в документацията. Допълнителните подподточки са обосновани с изискванията от „Разбиране“ и имат проверими критерии и цитати.
      </p>
      {!understandingReady && (
        <p data-testid="content-plan-understanding-warning" className="rounded bg-blue-50 p-2 text-[11px] text-blue-800">
          „Дейности“ и „Данни за проекта“ още не са потвърдени. Те са помощни за генерирането, но не блокират Вашето одобрение на подробния план.
        </p>
      )}

      <ul className="max-h-[34rem] space-y-1 overflow-y-auto pr-1">
        {roots.map((item) => (
          <PlanItemEditor
            key={item.id}
            item={item}
            allItems={plan.items}
            locked={plan.status_locked}
            busy={busy}
            onSave={async (itemId, values) => {
              setBusy(true);
              setError(null);
              try {
                const updated = await api.contentPlan.updateItem(projectId, itemId, values);
                setPlan((current) => current ? {
                  ...current,
                  items: current.items.map((entry) => entry.id === itemId ? updated : entry),
                } : current);
              } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "Промяната не бе записана.");
              } finally {
                setBusy(false);
              }
            }}
          />
        ))}
      </ul>

      {plan.status_locked ? (
        <div className="flex items-center justify-between border-t pt-2">
          <span className="text-xs font-medium text-green-700">✓ Планът е одобрен</span>
          <button
            type="button"
            data-testid="content-plan-unlock-button"
            disabled={busy}
            onClick={() => act(() => api.contentPlan.unlock(projectId))}
            className="text-xs text-amber-700 hover:underline disabled:opacity-50"
          >
            Редактирай
          </button>
        </div>
      ) : (
        <button
          type="button"
          data-testid="content-plan-approve-button"
          disabled={busy || generatableCount === 0}
          onClick={() => act(() => api.contentPlan.approve(projectId))}
          className="w-full rounded bg-green-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          {busy ? "Обработва се..." : "✓ Одобри подробния план"}
        </button>
      )}
      {!plan.status_locked && (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            if (window.confirm("Да се създаде нова версия от текущите Understanding артефакти?")) {
              void act(() => api.contentPlan.build(projectId));
            }
          }}
          className="w-full text-[11px] text-gray-500 hover:underline disabled:opacity-50"
        >
          Създай нова версия от Разбиране
        </button>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

function PlanItemEditor({
  item,
  allItems,
  locked,
  busy,
  onSave,
}: {
  item: ContentPlanItem;
  allItems: ContentPlanItem[];
  locked: boolean;
  busy: boolean;
  onSave: (itemId: string, values: Partial<ContentPlanItem>) => Promise<void>;
}) {
  const children = useMemo(
    () => allItems.filter((entry) => entry.parent_id === item.id),
    [allItems, item.id],
  );
  const [expanded, setExpanded] = useState(!item.parent_id);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [kind, setKind] = useState(item.content_kind);
  const [criteriaText, setCriteriaText] = useState(
    item.acceptance_criteria_json.map((criterion) => criterion.text).join("\n"),
  );
  const mandatory = item.source_quotes_json.some(
    (source) => source.source_kind === "mandatory_heading",
  );

  const save = async () => {
    const lines = criteriaText.split("\n").map((line) => line.trim()).filter(Boolean);
    const criteria: ContentPlanCriterion[] = lines.map((text, index) => ({
      ...(item.acceptance_criteria_json[index] || {
        id: `manual-${item.id}-${index + 1}`,
        kind: "content",
      }),
      text,
    }));
    await onSave(item.id, {
      title: title.trim(),
      content_kind: kind,
      acceptance_criteria_json: criteria,
    });
    setEditing(false);
  };

  return (
    <li className="rounded border bg-white p-1.5" data-testid={`content-plan-item-${item.id}`}>
      <div className="flex items-start gap-1">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="w-4 shrink-0 text-xs text-gray-400"
        >
          {expanded ? "▾" : "▸"}
        </button>
        <button type="button" onClick={() => setExpanded((value) => !value)} className="flex-1 text-left text-xs text-gray-800">
          <span className="mr-1 font-semibold text-gray-500">{item.number}</span>{item.title}
        </button>
        {item.generation_uid && (
          <span className="rounded bg-blue-50 px-1 text-[10px] text-blue-700">{item.acceptance_criteria_json.length}</span>
        )}
        {mandatory && (
          <span className="rounded bg-amber-50 px-1 text-[10px] text-amber-700">задължително</span>
        )}
        {!locked && (
          <button type="button" onClick={() => setEditing((value) => !value)} className="text-[10px] text-blue-600">редакция</button>
        )}
      </div>

      {expanded && (
        <div className="mt-1 space-y-1 pl-5">
          {editing ? (
            <div className="space-y-1 rounded bg-gray-50 p-2">
              <input aria-label="Заглавие на точката" disabled={mandatory} value={title} onChange={(event) => setTitle(event.target.value)} className="w-full rounded border p-1 text-xs disabled:bg-gray-100" />
              <select aria-label="Вид съдържание" value={kind} onChange={(event) => setKind(event.target.value as ContentPlanItem["content_kind"])} className="w-full rounded border p-1 text-xs">
                <option value="reuse">Типова методология</option>
                <option value="specific">Специфично за поръчката</option>
                <option value="mixed">Смесено</option>
              </select>
              <textarea aria-label="Критерии за приемане" value={criteriaText} onChange={(event) => setCriteriaText(event.target.value)} rows={5} className="w-full rounded border p-1 text-xs" placeholder="Един проверим критерий на ред" />
              <button type="button" disabled={busy || !title.trim()} onClick={() => void save()} className="rounded bg-blue-600 px-2 py-1 text-[11px] text-white disabled:opacity-50">Запази</button>
            </div>
          ) : (
            <>
              {item.acceptance_criteria_json.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-[10px] text-gray-600">
                  {item.acceptance_criteria_json.map((criterion) => <li key={criterion.id}>{criterion.text}</li>)}
                </ul>
              )}
              {item.source_quotes_json.length > 0 && (
                <details className="text-[10px] text-gray-500">
                  <summary className="cursor-pointer">Цитати-източници ({item.source_quotes_json.length})</summary>
                  <div className="mt-1 space-y-1">
                    {item.source_quotes_json.map((source, index) => (
                      <p key={`${source.requirement_id}-${index}`} className="border-l-2 pl-1">
                        {source.source_page ? `стр. ${source.source_page}: ` : ""}„{source.source_quote}“
                      </p>
                    ))}
                  </div>
                </details>
              )}
              {(item.linked_wbs_ids.length > 0 || item.linked_fact_keys.length > 0) && (
                <p className="text-[10px] text-gray-400">Свързано: {item.linked_wbs_ids.length} WBS · {item.linked_fact_keys.join(", ") || "без fact ключ"}</p>
              )}
            </>
          )}
          {children.length > 0 && (
            <ul className="space-y-1">
              {children.map((child) => (
                <PlanItemEditor key={child.id} item={child} allItems={allItems} locked={locked} busy={busy} onSave={onSave} />
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
