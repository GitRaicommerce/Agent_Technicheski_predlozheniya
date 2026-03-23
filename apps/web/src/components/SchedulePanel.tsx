"use client";

import { useState, useEffect } from "react";
import { api, ScheduleInfo } from "@/lib/api";

interface Props {
  projectId: string;
}

export default function SchedulePanel({ projectId }: Props) {
  const [schedule, setSchedule] = useState<ScheduleInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [locking, setLocking] = useState(false);
  const [lockError, setLockError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const load = () => {
    setLoading(true);
    setLoadError(null);
    api.agents
      .getSchedule(projectId)
      .then(setSchedule)
      .catch(() => setLoadError("Грешка при зареждане на графика."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLock = async () => {
    if (!schedule) return;
    setLocking(true);
    setLockError(null);
    try {
      await api.agents.lockSchedule(projectId, schedule.id);
      setSchedule((s) => (s ? { ...s, status_locked: true } : s));
    } catch (err: unknown) {
      setLockError(err instanceof Error ? err.message : "Грешка при одобрение");
    } finally {
      setLocking(false);
    }
  };

  const handleUnlock = async () => {
    if (!schedule) return;
    setLocking(true);
    setLockError(null);
    try {
      await api.agents.unlockSchedule(projectId, schedule.id);
      setSchedule((s) => (s ? { ...s, status_locked: false } : s));
    } catch (err: unknown) {
      setLockError(err instanceof Error ? err.message : "Грешка при отключване");
    } finally {
      setLocking(false);
    }
  };

  if (loading) {
    return (
      <p className="text-xs text-gray-400 py-2 animate-pulse">
        Зарежда графика...
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

  if (!schedule) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-gray-400 leading-relaxed">
          Графикът не е зареден. Качете .mpp, .xlsx или .pdf файл в модул
          &bdquo;Линеен график&ldquo;.
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

  const tasks = schedule.schedule_json.tasks ?? [];
  const resources = schedule.schedule_json.resources ?? [];
  const hasError = !!schedule.schedule_json.error;

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button onClick={load} className="text-xs text-gray-400 hover:text-blue-500 transition" title="Опресни">
          ↺
        </button>
      </div>
      {/* Status badge */}
      {schedule.status_locked ? (
        <div className="flex items-center justify-between py-1">
          <div className="flex items-center gap-1.5 text-xs text-green-700 font-medium">
            <span>✓</span>
            <span>Одобрен (версия {schedule.version})</span>
          </div>
          <button
            onClick={handleUnlock}
            disabled={locking}
            className="text-xs text-amber-600 hover:underline disabled:opacity-50"
          >
            🔓 Отключи
          </button>
        </div>
      ) : (
        <div>
          <button
            onClick={handleLock}
            disabled={locking || hasError}
            className="w-full py-1.5 px-3 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 disabled:opacity-50 transition"
          >
            {locking ? "Одобрява се..." : "✓ Одобри графика"}
          </button>
          {lockError && (
            <p className="text-xs text-red-500 mt-1">{lockError}</p>
          )}
        </div>
      )}

      {/* Error from parser */}
      {hasError && (
        <p className="text-xs text-amber-600 bg-amber-50 rounded px-2 py-1">
          ⚠ {schedule.schedule_json.error}
        </p>
      )}

      {/* Summary stats */}
      {!hasError && (
        <div className="text-xs text-gray-500 flex gap-3">
          <span>📋 {tasks.length} задачи</span>
          {resources.length > 0 && <span>👥 {resources.length} ресурса</span>}
        </div>
      )}

      {/* Expandable task list */}
      {tasks.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-blue-600 hover:underline"
          >
            {expanded ? "▾ Скрий задачите" : "▸ Покажи задачите"}
          </button>
          {expanded && (
            <ul className="mt-1 space-y-0.5 max-h-48 overflow-y-auto">
              {tasks.map((t) => (
                <li key={t.uid} className="text-xs text-gray-600 flex gap-1">
                  <span className="text-gray-400 shrink-0">{t.wbs ?? t.uid}.</span>
                  <span className="truncate">{t.name}</span>
                  {t.duration_days != null && (
                    <span className="text-gray-400 shrink-0">{t.duration_days}д</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
