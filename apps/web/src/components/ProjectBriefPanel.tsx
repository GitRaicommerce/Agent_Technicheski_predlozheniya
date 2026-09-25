"use client";

import { useEffect, useState } from "react";
import { api, type ProjectBrief } from "@/lib/api";

interface Props {
  projectId: string;
}

/**
 * K-11: the durable project brief — approved scope, exclusions and
 * constraints. It is saved explicitly as a new version; chat messages never
 * change it. Every generation job records the version it used.
 */
export default function ProjectBriefPanel({ projectId }: Props) {
  const [brief, setBrief] = useState<ProjectBrief | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.projects
      .getBrief(projectId)
      .then((loaded) => {
        if (cancelled) return;
        setBrief(loaded);
        setDraft(loaded.content);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Заданието не бе заредено.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const dirty = brief !== null && draft.trim() !== brief.content.trim();

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const next = await api.projects.saveBrief(projectId, draft);
      setBrief(next);
      setDraft(next.content);
      setSaved(true);
    } catch (err: unknown) {
      // Keep the unsaved text in the editor; nothing is lost on failure.
      setError(err instanceof Error ? err.message : "Заданието не бе записано.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2 text-xs" data-testid="project-brief-panel">
      <p className="text-gray-500">
        Постоянни указания за цялото ТП (обхват, изключения, ограничения). Те
        важат за всяко генериране, независимо от чата. Записват се като нова
        версия; вече стартирани задачи ползват версията, с която са започнали.
      </p>
      <textarea
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          setSaved(false);
        }}
        rows={5}
        data-testid="project-brief-input"
        placeholder="Напр.: Не включвай проектна част Електро — тя е извън обхвата на тази обособена позиция."
        className="w-full rounded border px-2 py-1"
      />
      <div className="flex items-center justify-between">
        <span className="text-gray-400">
          {brief && brief.version > 0 ? `Версия ${brief.version}` : "Няма записано задание"}
          {dirty ? " · незаписани промени" : ""}
        </span>
        <button
          type="button"
          data-testid="project-brief-save"
          disabled={saving || !dirty}
          onClick={() => void save()}
          className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
        >
          {saving ? "Записва се..." : "Запиши заданието"}
        </button>
      </div>
      {saved && <p className="text-green-700">Заданието е записано.</p>}
      {error && <p className="text-red-600">{error}</p>}
    </div>
  );
}
