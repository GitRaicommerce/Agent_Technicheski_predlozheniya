"use client";

import { useState, useEffect } from "react";
import { api, TpOutline, TpOutlineSection } from "@/lib/api";

interface Props {
  projectId: string;
}

export default function OutlinePanel({ projectId }: Props) {
  const [outline, setOutline] = useState<TpOutline | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [locking, setLocking] = useState(false);
  const [lockError, setLockError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setLoadError(null);
    api.agents
      .getOutline(projectId)
      .then(setOutline)
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : "Грешка при зареждане на структурата."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLock = async () => {
    if (!outline) return;
    setLocking(true);
    setLockError(null);
    try {
      await api.agents.lockOutline(projectId, outline.id);
      setOutline((o) => (o ? { ...o, status_locked: true } : o));
    } catch (err: unknown) {
      setLockError(
        err instanceof Error ? err.message : "Грешка при одобрение",
      );
    } finally {
      setLocking(false);
    }
  };

  const handleUnlock = async () => {
    if (!outline) return;
    setLocking(true);
    setLockError(null);
    try {
      await api.agents.unlockOutline(projectId, outline.id);
      setOutline((o) => (o ? { ...o, status_locked: false } : o));
    } catch (err: unknown) {
      setLockError(
        err instanceof Error ? err.message : "Грешка при отключване",
      );
    } finally {
      setLocking(false);
    }
  };

  if (loading) {
    return (
      <p className="text-xs text-gray-400 py-2 animate-pulse">
        Зарежда структурата...
      </p>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-red-500">{loadError}</p>
        <button onClick={load} className="text-xs text-blue-500 hover:underline">↺ Опитай отново</button>
      </div>
    );
  }

  if (!outline) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-gray-400 leading-relaxed">
          Съдържанието на ТП не е генерирано. Качете тръжна документация и напишете в чата
          &ldquo;Анализирай документацията и предложи съдържание на ТП&rdquo;.
        </p>
        <button
          onClick={load}
          className="text-xs text-blue-500 hover:underline"
        >
          ↺ Опресни
        </button>
      </div>
    );
  }

  const sections =
    outline.outline_json.sections ?? outline.outline_json.outline ?? [];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {sections.length} раздел{sections.length !== 1 ? "а" : ""}
          {outline.status_locked && <span className="ml-2 text-green-600 font-medium">✓ Одобрено</span>}
        </span>
        <button onClick={load} className="text-xs text-gray-400 hover:text-blue-500 transition" title="Опресни">
          ↺
        </button>
      </div>

      {sections.length > 0 && (
        <ul className="space-y-0.5 max-h-64 overflow-y-auto pr-1">
          {sections.map((s, i) => (
            <SectionItem key={s.uid ?? i} section={s} depth={0} />
          ))}
        </ul>
      )}

      {outline.status_locked ? (
        <div className="flex items-center justify-between pt-1 border-t">
          <span className="text-xs text-green-700 font-medium">✓ Одобрено (v{outline.version})</span>
          <button
            onClick={handleUnlock}
            disabled={locking}
            className="text-xs text-amber-600 hover:underline disabled:opacity-50"
          >
            🔓 Редактирай
          </button>
        </div>
      ) : (
        <div className="pt-1 border-t">
          <p className="text-xs text-gray-400 mb-1.5">
            Прегледайте разделите и одобрете за да започне генерирането.
          </p>
          <button
            onClick={handleLock}
            disabled={locking}
            className="w-full py-1.5 px-3 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 disabled:opacity-50 transition"
          >
            {locking ? "Одобрява се..." : "✓ Одобри и генерирай"}
          </button>
          {lockError && (
            <p className="text-xs text-red-500 mt-1">{lockError}</p>
          )}
        </div>
      )}
    </div>
  );
}

function SectionItem({
  section,
  depth,
}: {
  section: TpOutlineSection;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const children = section.subsections ?? [];

  return (
    <li>
      <button
        onClick={() => children.length > 0 && setExpanded((e) => !e)}
        style={{ paddingLeft: `${0.5 + depth * 0.75}rem` }}
        className="text-left w-full text-xs py-1 pr-2 rounded flex items-start gap-1 hover:bg-gray-100 transition"
      >
        {children.length > 0 ? (
          <span className="text-gray-400 mt-0.5 w-3 shrink-0 text-center">
            {expanded ? "▾" : "▸"}
          </span>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <span className="flex-1 text-gray-700">{section.title}</span>
        {section.required && (
          <span className="text-red-400 shrink-0 ml-1">*</span>
        )}
      </button>
      {expanded && children.length > 0 && (
        <ul>
          {children.map((c, i) => (
            <SectionItem key={c.uid ?? i} section={c} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}
