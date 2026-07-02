"use client";

import { useEffect, useMemo, useState } from "react";
import { api, RequirementChecklist, RequirementChecklistItem } from "@/lib/api";

interface Props {
  projectId: string;
  refreshKey?: number;
}

const importanceLabels: Record<string, string> = {
  mandatory: "задължително",
  scored: "оценяемо",
  optional: "по избор",
  scope: "обхват",
};

function storageKey(projectId: string) {
  return `tp_requirement_checklist_checked_${projectId}`;
}

export default function RequirementChecklistPanel({
  projectId,
  refreshKey = 0,
}: Props) {
  const [checklist, setChecklist] = useState<RequirementChecklist | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [importanceFilter, setImportanceFilter] = useState("all");
  const [checked, setChecked] = useState<Set<string>>(() => {
    if (typeof window === "undefined") {
      return new Set();
    }
    try {
      const raw = window.localStorage.getItem(storageKey(projectId));
      return new Set(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set();
    }
  });

  const load = () => {
    setLoading(true);
    setLoadError(null);
    api.agents
      .getRequirementChecklist(projectId)
      .then(setChecklist)
      .catch((err: unknown) =>
        setLoadError(
          err instanceof Error
            ? err.message
            : "Грешка при зареждане на чеклиста.",
        ),
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let cancelled = false;
    api.agents
      .getRequirementChecklist(projectId)
      .then((data) => {
        if (!cancelled) {
          setChecklist(data);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof Error
              ? err.message
              : "Грешка при зареждане на чеклиста.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, refreshKey]);

  const categories = useMemo(() => {
    return Object.keys(checklist?.category_counts ?? {}).sort((a, b) =>
      a.localeCompare(b, "bg"),
    );
  }, [checklist]);

  const filteredItems = useMemo(() => {
    const items = checklist?.items ?? [];
    return items.filter((item) => {
      const categoryOk =
        categoryFilter === "all" || item.category_label === categoryFilter;
      const importanceOk =
        importanceFilter === "all" || item.importance === importanceFilter;
      return categoryOk && importanceOk;
    });
  }, [categoryFilter, checklist, importanceFilter]);

  const toggleChecked = (item: RequirementChecklistItem) => {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else {
        next.add(item.id);
      }
      window.localStorage.setItem(
        storageKey(projectId),
        JSON.stringify([...next]),
      );
      return next;
    });
  };

  if (loading) {
    return (
      <p className="py-2 text-xs text-gray-400 animate-pulse">
        Зарежда чеклиста...
      </p>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-red-500">{loadError}</p>
        <button
          onClick={load}
          className="text-xs text-blue-500 hover:underline"
        >
          ↻ Опитай отново
        </button>
      </div>
    );
  }

  if (!checklist || checklist.total === 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs leading-relaxed text-gray-400">
          Няма извлечени изисквания от тръжната документация.
        </p>
        <button
          onClick={load}
          className="text-xs text-blue-500 hover:underline"
        >
          ↻ Опресни
        </button>
      </div>
    );
  }

  const checkedCount = checklist.items.filter((item) => checked.has(item.id)).length;

  return (
    <div data-testid="requirements-checklist-panel" className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs text-gray-500">
          <p>
            <span className="font-semibold text-gray-700">{checklist.total}</span>{" "}
            изисквания
          </p>
          <p>
            <span className="font-semibold text-green-700">{checkedCount}</span>{" "}
            маркирани
          </p>
        </div>
        <button
          onClick={load}
          className="text-xs text-gray-400 transition hover:text-blue-500"
          title="Опресни"
        >
          ↻
        </button>
      </div>

      <div className="grid grid-cols-2 gap-1.5 text-[11px]">
        {Object.entries(checklist.importance_counts).map(([key, value]) => (
          <div key={key} className="rounded border border-gray-200 px-2 py-1 text-gray-600">
            <span className="font-semibold text-gray-800">{value}</span>{" "}
            {importanceLabels[key] ?? key}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-1.5">
        <select
          value={categoryFilter}
          onChange={(event) => setCategoryFilter(event.target.value)}
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          aria-label="Филтър по категория"
        >
          <option value="all">Всички категории</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category} ({checklist.category_counts[category]})
            </option>
          ))}
        </select>
        <select
          value={importanceFilter}
          onChange={(event) => setImportanceFilter(event.target.value)}
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          aria-label="Филтър по важност"
        >
          <option value="all">Всички важности</option>
          {Object.entries(checklist.importance_counts).map(([key, value]) => (
            <option key={key} value={key}>
              {importanceLabels[key] ?? key} ({value})
            </option>
          ))}
        </select>
      </div>

      <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
        {filteredItems.map((item, index) => (
          <label
            key={item.id}
            className="block border-b border-gray-100 pb-2 text-xs last:border-0"
          >
            <div className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={checked.has(item.id)}
                onChange={() => toggleChecked(item)}
                className="mt-0.5 h-3.5 w-3.5 rounded border-gray-300"
              />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-1">
                  <span className="text-[10px] font-semibold text-gray-400">
                    #{index + 1}
                  </span>
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600">
                    {item.category_label}
                  </span>
                  <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700">
                    {importanceLabels[item.importance] ?? item.importance}
                  </span>
                </div>
                <p className="break-words leading-relaxed text-gray-700">
                  {item.text}
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-gray-500">
                  {item.coverage_question}
                </p>
                <p className="mt-1 truncate text-[10px] text-gray-400">
                  {item.source_file ?? "Документ"}
                  {item.source_page ? `, стр. ${item.source_page}` : ""} ·{" "}
                  {item.suggested_section}
                </p>
              </div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}
