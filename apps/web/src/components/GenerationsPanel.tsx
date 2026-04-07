"use client";

import { useState, useEffect, useCallback } from "react";
import { api, SectionGenerations, Generation } from "@/lib/api";

interface Props {
  projectId: string;
}

export default function GenerationsPanel({ projectId }: Props) {
  const [sections, setSections] = useState<SectionGenerations[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [regenerating, setRegenerating] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.agents
      .listGenerations(projectId)
      .then(setSections)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Грешка при зареждане.")
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const toggleSection = (uid: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) { next.delete(uid); } else { next.add(uid); }
      return next;
    });
  };

  const handleRegenerate = async (sectionUid: string) => {
    setRegenerating(sectionUid);
    try {
      await api.agents.regenerateSection(projectId, sectionUid);
      // reload to show the new variants
      await api.agents.listGenerations(projectId).then(setSections);
    } catch {
      // ignore — user can retry
    } finally {
      setRegenerating(null);
    }
  };

  if (loading) {
    return (
      <p className="text-xs text-gray-400 py-2 animate-pulse">
        Зарежда генерациите...
      </p>
    );
  }

  if (error) {
    return (
      <div className="space-y-1">
        <p className="text-xs text-red-400">{error}</p>
        <button onClick={load} className="text-xs text-blue-500 hover:underline">
          ↺ Опитай отново
        </button>
      </div>
    );
  }

  if (sections.length === 0) {
    return (
      <div className="space-y-1">
        <p className="text-xs text-gray-400 leading-relaxed">
          Няма генерирани текстове. Поискайте от TP AI да генерира раздел от ТП-то.
        </p>
        <button onClick={load} className="text-xs text-blue-500 hover:underline">
          ↺ Обнови
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-gray-400">{sections.length} раздела</span>
        <button
          onClick={load}
          className="text-xs text-gray-400 hover:text-blue-500 transition"
          title="Обнови"
        >
          ↺
        </button>
      </div>

      {sections.map((sec) => {
        const isOpen = expanded.has(sec.section_uid);
        // Show the selected variant, or the first one
        const displayVariant = sec.variants.find((v) => v.selected) ?? sec.variants[0];

        return (
          <div key={sec.section_uid} className="border rounded-lg overflow-hidden">
            {/* Section header */}
            <button
              onClick={() => toggleSection(sec.section_uid)}
              className="w-full flex items-start justify-between px-3 py-2 text-left bg-gray-50 hover:bg-gray-100 transition"
            >
              <p className="text-xs font-medium text-gray-700 flex-1 min-w-0 truncate pr-2">
                {sec.section_title || sec.section_uid.slice(0, 8) + "…"}
              </p>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={(e) => { e.stopPropagation(); handleRegenerate(sec.section_uid); }}
                  disabled={regenerating === sec.section_uid}
                  className="px-1.5 py-0.5 text-xs rounded bg-amber-100 text-amber-700 hover:bg-amber-200 disabled:opacity-50 transition"
                  title="Регенерирай раздела"
                >
                  {regenerating === sec.section_uid ? "…" : "↻"}
                </button>
                <span className="text-gray-400 text-xs">{isOpen ? "▾" : "▸"}</span>
              </div>
            </button>

            {/* Text */}
            {isOpen && displayVariant && (
              <SectionText variant={displayVariant} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function SectionText({ variant }: { variant: Generation }) {
  const [expanded, setExpanded] = useState(false);
  const previewLen = 400;
  const isLong = variant.text.length > previewLen;

  return (
    <div className="px-3 py-3 bg-white">
      <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">
        {expanded || !isLong ? variant.text : variant.text.slice(0, previewLen) + "…"}
      </p>
      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-blue-500 hover:underline"
        >
          {expanded ? "▴ Скрий" : "▾ Виж целия текст"}
        </button>
      )}
    </div>
  );
}
