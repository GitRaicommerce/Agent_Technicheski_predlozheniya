"use client";

import { useEffect, useMemo, useState } from "react";

import { api, type ForlageWorkspace } from "@/lib/api";

export default function ForlagePanel({ projectId }: { projectId: string }) {
  const [workspace, setWorkspace] = useState<ForlageWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sectionsById = useMemo(
    () => new Map((workspace?.sections || []).map((section) => [section.id, section])),
    [workspace?.sections],
  );

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setWorkspace(await api.forlage.get(projectId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Грешка при зареждане на форлагето.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const analyze = async () => {
    if (workspace?.analyzed && !window.confirm(
      "Повторният анализ ще обнови автоматичните връзки към текущия подробен план. Да продължа ли?",
    )) return;
    setBusy(true);
    setError(null);
    try {
      setWorkspace(await api.forlage.analyze(projectId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Анализът на форлагето не бе изпълнен.");
    } finally {
      setBusy(false);
    }
  };

  const updateLink = async (itemId: string, sectionId: string | null) => {
    setBusy(true);
    setError(null);
    try {
      setWorkspace(await api.forlage.updateLink(projectId, itemId, sectionId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Връзката не бе записана.");
    } finally {
      setBusy(false);
    }
  };

  const confirmReview = async () => {
    setBusy(true);
    setError(null);
    try {
      setWorkspace(await api.forlage.confirm(projectId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Прегледът не бе потвърден.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="text-xs text-gray-400">Зарежда се Phase 3...</p>;

  return (
    <section className="space-y-2 border-t pt-3" data-testid="forlage-panel">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-gray-700">Phase 3 · Съпоставяне</p>
        <button type="button" onClick={() => void load()} className="text-xs text-gray-400">↻</button>
      </div>
      <p className="text-[11px] leading-relaxed text-gray-500">
        Форлагето предоставя само приложими текстове и методологии. То не създава изисквания, дейности или структура за текущата поръчка.
      </p>
      <button
        type="button"
        data-testid="forlage-analyze-button"
        disabled={busy}
        onClick={() => void analyze()}
        className="w-full rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
      >
        {busy ? "Обработва се..." : workspace?.analyzed ? "Анализирай отново" : "Анализирай и съпостави"}
      </button>

      {workspace?.analyzed && (
        <>
          <p className="rounded bg-blue-50 p-2 text-[11px] text-blue-800" data-testid="forlage-summary">
            {workspace.section_count} йерархични раздела · {workspace.mapped_count}/{workspace.mappings.length} свързани точки от план v{workspace.outline_version}
          </p>
          <p className="text-[11px] text-amber-700">
            {workspace.review_confirmed
              ? "✓ Съпоставянето е прегледано и ще се използва при следващата генерация."
              : "Прегледайте автоматичните съвпадения. Изберете „Без форлаге“, ако текстът не е подходящ."}
          </p>
          <ul className="max-h-[30rem] space-y-2 overflow-y-auto pr-1">
            {workspace.mappings.map((mapping) => {
              const candidateIds = new Set(mapping.candidates.map((candidate) => candidate.section_id));
              const optionIds = [
                ...(mapping.selected_section_id && !candidateIds.has(mapping.selected_section_id)
                  ? [mapping.selected_section_id]
                  : []),
                ...mapping.candidates.map((candidate) => candidate.section_id),
              ];
              const selected = mapping.selected_section_id
                ? sectionsById.get(mapping.selected_section_id)
                : null;
              return (
                <li key={mapping.item_id} className="rounded border bg-white p-2" data-testid={`forlage-mapping-${mapping.item_id}`}>
                  <p className="text-xs font-medium text-gray-800">
                    <span className="mr-1 text-gray-500">{mapping.item_number}</span>{mapping.item_title}
                  </p>
                  <select
                    aria-label={`Форлаге за ${mapping.item_number} ${mapping.item_title}`}
                    disabled={busy}
                    value={mapping.selected_section_id || ""}
                    onChange={(event) => void updateLink(mapping.item_id, event.target.value || null)}
                    className="mt-1 w-full rounded border p-1 text-[11px]"
                  >
                    <option value="">Без форлаге</option>
                    {optionIds.map((sectionId) => {
                      const section = sectionsById.get(sectionId);
                      const candidate = mapping.candidates.find((entry) => entry.section_id === sectionId);
                      return section ? (
                        <option key={sectionId} value={sectionId}>
                          {candidate ? `${Math.round(candidate.score * 100)}% · ` : ""}{section.number ? `${section.number} ` : ""}{section.title} · {section.filename}
                        </option>
                      ) : null;
                    })}
                  </select>
                  {selected && (
                    <details className="mt-1 text-[11px] text-gray-500">
                      <summary className="cursor-pointer text-blue-700">Преглед на избрания раздел</summary>
                      <p className="mt-1 whitespace-pre-wrap rounded bg-gray-50 p-1.5">{selected.text_preview}</p>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
          {!workspace.review_confirmed && (
            <button
              type="button"
              data-testid="forlage-confirm-button"
              disabled={busy}
              onClick={() => void confirmReview()}
              className="w-full rounded bg-green-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              ✓ Потвърди съпоставянето
            </button>
          )}
        </>
      )}
      {!workspace?.outline_id && <p className="text-xs text-amber-700">Първо създайте подробен план на ТП.</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </section>
  );
}
