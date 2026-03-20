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
  const [selecting, setSelecting] = useState<string | null>(null);
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
      next.has(uid) ? next.delete(uid) : next.add(uid);
      return next;
    });
  };

  const handleSelect = async (sectionUid: string, generationId: string) => {
    setSelecting(generationId);
    try {
      await api.agents.selectGeneration(projectId, generationId);
      setSections((prev) =>
        prev.map((sec) =>
          sec.section_uid !== sectionUid
            ? sec
            : {
                ...sec,
                variants: sec.variants.map((v) => ({
                  ...v,
                  selected: v.id === generationId,
                })),
              }
        )
      );
    } catch {
      // keep going — selection is best-effort
    } finally {
      setSelecting(null);
    }
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
        const selectedVariant = sec.variants.find((v) => v.selected);
        const hasStale = sec.variants.some((v) => v.evidence_status === "stale");

        return (
          <div key={sec.section_uid} className="border rounded-lg overflow-hidden">
            {/* Section header */}
            <button
              onClick={() => toggleSection(sec.section_uid)}
              className="w-full flex items-start justify-between px-3 py-2 text-left bg-gray-50 hover:bg-gray-100 transition"
            >
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-gray-700 truncate">
                  {sec.section_title || sec.section_uid.slice(0, 8) + "…"}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {sec.variants.length} вариант{sec.variants.length !== 1 ? "а" : ""}
                  {selectedVariant && (
                    <span className="ml-2 text-green-600">✓ избран: Вариант {selectedVariant.variant}</span>
                  )}
                  {hasStale && (
                    <span className="ml-2 text-amber-500">⚠ остарял</span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-1 ml-2 mt-0.5 shrink-0">
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

            {/* Variants */}
            {isOpen && (
              <div className="divide-y">
                {sec.variants.map((v) => (
                  <VariantCard
                    key={v.id}
                    variant={v}
                    sectionUid={sec.section_uid}
                    onSelect={handleSelect}
                    selecting={selecting}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function VariantCard({
  variant,
  sectionUid,
  onSelect,
  selecting,
}: {
  variant: Generation;
  sectionUid: string;
  onSelect: (sectionUid: string, id: string) => void;
  selecting: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const flags = (variant.flags_json?.verification as { flags?: string[] } | undefined)?.flags ?? [];
  const verdict = (variant.flags_json?.verification as { verdict?: string } | undefined)?.verdict;
  const isStale = variant.evidence_status === "stale";

  const previewLen = 220;
  const preview = variant.text.length > previewLen
    ? variant.text.slice(0, previewLen) + "…"
    : variant.text;

  return (
    <div
      className={`px-3 py-2 text-xs ${
        variant.selected ? "bg-green-50 border-l-2 border-green-400" : "bg-white"
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-600">Вариант {variant.variant}</span>
          {variant.selected && (
            <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-xs font-medium">
              ✓ Избран
            </span>
          )}
          {isStale && (
            <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-xs">
              ⚠ остарял
            </span>
          )}
          {verdict === "ok" && (
            <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded text-xs">
              ✓ Верифициран
            </span>
          )}
          {verdict === "warning" && (
            <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-xs">
              ⚠ {flags.length} флага
            </span>
          )}
        </div>
        <div className="flex gap-2 items-center">
          <span className="text-gray-300">
            {new Date(variant.created_at).toLocaleDateString("bg-BG")}
          </span>
          {!variant.selected && (
            <button
              onClick={() => onSelect(sectionUid, variant.id)}
              disabled={selecting === variant.id}
              className="px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition"
            >
              {selecting === variant.id ? "…" : "Избери"}
            </button>
          )}
        </div>
      </div>

      {/* Text preview / full */}
      <p className="text-gray-600 leading-relaxed whitespace-pre-wrap">
        {expanded ? variant.text : preview}
      </p>
      {variant.text.length > previewLen && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-blue-500 hover:underline"
        >
          {expanded ? "Скрий" : "Виж целия текст"}
        </button>
      )}

      {/* Verification flags */}
      {flags.length > 0 && expanded && (
        <div className="mt-2 space-y-0.5">
          <p className="font-medium text-gray-500">Флагове от верификатора:</p>
          {flags.map((f, i) => (
            <p key={i} className="text-amber-600 flex gap-1">
              <span>•</span>
              <span>{f}</span>
            </p>
          ))}
        </div>
      )}

      {/* Used sources */}
      {variant.used_sources_json && expanded && (
        <UsedSources sources={variant.used_sources_json} />
      )}
    </div>
  );
}

function UsedSources({ sources }: { sources: Record<string, unknown> }) {
  // sources can be { filename: snippet } or { chunk_id: { filename, text } }
  const entries = Object.entries(sources);
  if (!entries.length) return null;

  return (
    <div className="mt-2 border-t pt-2 space-y-1">
      <p className="font-medium text-gray-500 text-xs">Използвани източници ({entries.length}):</p>
      {entries.map(([key, val]) => {
        const filename =
          typeof val === "object" && val !== null && "filename" in val
            ? String((val as Record<string, unknown>).filename)
            : key;
        const snippet =
          typeof val === "string"
            ? val
            : typeof val === "object" && val !== null && "text" in val
            ? String((val as Record<string, unknown>).text)
            : null;
        return (
          <div key={key} className="text-gray-400">
            <span className="font-medium text-gray-500 truncate">{filename}</span>
            {snippet && (
              <p className="mt-0.5 italic line-clamp-2">{snippet}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
