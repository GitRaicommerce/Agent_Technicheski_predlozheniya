"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, LegislationStatusResponse, Project } from "@/lib/api";
import { useToast } from "@/components/ToastProvider";
import ChatPanel from "@/components/ChatPanel";
import ExportButton from "@/components/ExportButton";
import FileUploadPanel from "@/components/FileUploadPanel";
import OutlinePanel from "@/components/OutlinePanel";
import SchedulePanel from "@/components/SchedulePanel";
import GenerationsPanel from "@/components/GenerationsPanel";

type Module = "examples" | "tender_docs" | "schedule" | "legislation";

const MODULES: { key: Module; label: string; icon: string }[] = [
  { key: "examples", label: "Примерни ТП", icon: "📄" },
  { key: "tender_docs", label: "Документация", icon: "📋" },
  { key: "legislation", label: "Законодателство", icon: "⚖️" },
];

const WORKFLOW_STEPS = [
  "Качете тръжна документация и примерни ТП",
  "Чатирайте с AI да анализира документацията и предложи съдържание на ТП",
  "Прегледайте разделите и одобрете съдържанието",
  "Генерирайте текст за всяка секция",
  "Изберете най-добрите варианти",
  "Експортирайте готовия документ (DOCX)",
];

const DISABLE_AUTO_LEX_REFRESH_KEY = "tp_disable_auto_lex_refresh";

const displayModuleLabel = (module: { key: Module; label: string }) =>
  module.key === "legislation" ? "Нормативна база" : module.label;

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { toast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeModule, setActiveModule] = useState<Module | null>(null);
  const [showOutline, setShowOutline] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showGenerations, setShowGenerations] = useState(false);
  const [outlineRefreshKey, setOutlineRefreshKey] = useState(0);
  const [scheduleRefreshKey, setScheduleRefreshKey] = useState(0);
  const [generationsRefreshKey, setGenerationsRefreshKey] = useState(0);
  const [showEdit, setShowEdit] = useState(false);
  const [editData, setEditData] = useState({ name: "", location: "", description: "", contracting_authority: "", tender_date: "" });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [legislationStatus, setLegislationStatus] =
    useState<LegislationStatusResponse | null>(null);
  const [legislationStatusLoading, setLegislationStatusLoading] = useState(false);
  const [legislationRefreshing, setLegislationRefreshing] = useState(false);
  const [legislationError, setLegislationError] = useState<string | null>(null);

  const loadLegislationStatus = useCallback(async (projectId: string) => {
    setLegislationStatusLoading(true);
    setLegislationError(null);
    try {
      const status = await api.projects.legislationStatus(projectId);
      setLegislationStatus(status);
    } catch (error: unknown) {
      setLegislationError(
        error instanceof Error
          ? error.message
          : "Не успях да заредя статуса на нормативната база.",
      );
    } finally {
      setLegislationStatusLoading(false);
    }
  }, []);

  const refreshLegislation = useCallback(
    async (projectId: string, force = false) => {
      setLegislationRefreshing(true);
      setLegislationError(null);
      try {
        const refresh = await api.projects.refreshLegislation(projectId, force);
        await loadLegislationStatus(projectId);
        if (refresh.status === "warning") {
          toast("Част от нормативната база не можа да бъде обновена от Lex.bg.", "warning");
        } else if (refresh.changed > 0) {
          toast("Нормативната база е обновена от Lex.bg.", "success");
        } else if (force) {
          toast("Нормативната база е проверена. Няма промени.", "success");
        }
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Не успях да проверя нормативната база в Lex.bg.";
        setLegislationError(message);
        toast("Не успях да проверя нормативната база в Lex.bg.", "error");
      } finally {
        setLegislationRefreshing(false);
      }
    },
    [loadLegislationStatus, toast],
  );

  useEffect(() => {
    let cancelled = false;

    if (!params.id) {
      return () => {
        cancelled = true;
      };
    }

    api.projects
      .get(params.id)
      .then((p) => {
        if (cancelled) return;

        setProject(p);
        setEditData({ name: p.name, location: p.location ?? "", description: p.description ?? "", contracting_authority: p.contracting_authority ?? "", tender_date: p.tender_date ?? "" });
        void loadLegislationStatus(p.id);

        if (window.localStorage.getItem(DISABLE_AUTO_LEX_REFRESH_KEY) === "1") {
          return;
        }

        if (refreshLegislation) {
          void refreshLegislation(p.id);
          return;
        }

        void api.projects
          .refreshLegislation(p.id)
          .then((refresh) => {
            if (cancelled) return;
            if (refresh.changed > 0) {
              toast("Нормативната база е обновена от Lex.bg.", "success");
            } else if (refresh.status === "warning") {
              toast("Част от нормативната база не можа да бъде обновена.", "warning");
            }
          })
          .catch(() => {
            if (!cancelled) {
              toast("Не успях да проверя нормативната база в Lex.bg.", "error");
            }
          });
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [loadLegislationStatus, params.id, refreshLegislation, toast]);

  // Close edit/delete with Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") {
      setShowEdit(false);
      setShowDeleteConfirm(false);
      setSaveError(null);
      setDeleteError(null);
    }
  }, []);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const handleFileStatusChange = useCallback(
    (file: { ingest_status: string }, module: string) => {
      if (file.ingest_status !== "done") {
        return;
      }

      if (module === "schedule") {
        setShowSchedule(true);
        setScheduleRefreshKey((value) => value + 1);
      }

      if (module === "tender_docs") {
        setShowOutline(true);
        setOutlineRefreshKey((value) => value + 1);
      }
    },
    [],
  );

  async function handleSaveEdit() {
    if (!project) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.projects.update(project.id, {
        name: editData.name,
        location: editData.location || undefined,
        description: editData.description || undefined,
        contracting_authority: editData.contracting_authority || undefined,
        tender_date: editData.tender_date || undefined,
      });
      setProject(updated);
      setShowEdit(false);
      toast("Проектът е запазен.", "success");
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Грешка при запазване.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!project) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.projects.delete(project.id);
      toast("Проектът е изтрит.", "success");
      router.push("/projects");
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : "Грешка при изтриване.");
      setDeleting(false);
    }
  }

  if (loading) return <main className="p-8 text-gray-500">Зарежда се...</main>;
  if (!project)
    return <main className="p-8 text-red-500">Проектът не е намерен.</main>;

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-3">
        {/* Top bar: back + delete */}
        <div className="flex justify-between items-center mb-2">
          <Link
            href="/projects"
            className="text-xs text-blue-600 hover:underline flex items-center gap-1"
          >
            ← Моите проекти
          </Link>
          {!showEdit && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              data-testid="project-delete-button"
              className="text-xs text-red-400 hover:text-red-600 hover:bg-red-50 px-2 py-0.5 rounded transition"
            >
              🗑 Изтрий
            </button>
          )}
        </div>

        {/* Delete confirmation */}
        {showDeleteConfirm && (
          <div className="mb-2 p-3 bg-red-50 border border-red-200 rounded-lg flex flex-col gap-2">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm text-red-700">
                Изтриване на &#x201E;{project.name}&#x201C;? Действието е необратимо.
              </p>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={handleDelete}
                  data-testid="project-delete-confirm"
                  disabled={deleting}
                  className="px-3 py-1 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700 disabled:opacity-50"
                >
                  {deleting ? "Изтрива..." : "Да, изтрий"}
                </button>
                <button
                  onClick={() => { setShowDeleteConfirm(false); setDeleteError(null); }}
                  className="px-3 py-1 border text-xs rounded-lg text-gray-600 hover:bg-gray-50"
                >
                  Отказ
                </button>
              </div>
            </div>
            {deleteError && (
              <p className="text-xs text-red-600">{deleteError}</p>
            )}
          </div>
        )}

        {showEdit ? (
          <div className="flex items-start gap-3">
            <div className="flex-1 space-y-2">
              <input
                data-testid="project-edit-name-input"
                className="w-full border rounded-lg px-3 py-1.5 text-sm font-semibold text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editData.name}
                onChange={(e) => setEditData((d) => ({ ...d, name: e.target.value }))}
                placeholder="Наименование на проекта"
              />
              <input
                data-testid="project-edit-location-input"
                className="w-full border rounded-lg px-3 py-1.5 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editData.location}
                onChange={(e) => setEditData((d) => ({ ...d, location: e.target.value }))}
                placeholder="Местоположение"
              />
              <input
                data-testid="project-edit-authority-input"
                className="w-full border rounded-lg px-3 py-1.5 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editData.contracting_authority}
                onChange={(e) => setEditData((d) => ({ ...d, contracting_authority: e.target.value }))}
                placeholder="Възложител"
              />
              <div className="flex gap-2">
                <input
                  data-testid="project-edit-tender-date-input"
                  className="flex-1 border rounded-lg px-3 py-1.5 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  type="date"
                  value={editData.tender_date}
                  onChange={(e) => setEditData((d) => ({ ...d, tender_date: e.target.value }))}
                  title="Дата на подаване"
                />
                <input
                  data-testid="project-edit-description-input"
                  className="flex-1 border rounded-lg px-3 py-1.5 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  value={editData.description}
                  onChange={(e) => setEditData((d) => ({ ...d, description: e.target.value }))}
                  placeholder="Описание"
                />
              </div>
              {saveError && (
                <p className="text-xs text-red-500">{saveError}</p>
              )}
            </div>
            <div className="flex gap-2 pt-0.5">
              <button
                onClick={handleSaveEdit}
                data-testid="project-save-button"
                disabled={saving || !editData.name.trim()}
                className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Запазва..." : "Запази"}
              </button>
              <button
                onClick={() => { setShowEdit(false); setSaveError(null); }}
                className="px-3 py-1.5 border text-sm rounded-lg text-gray-600 hover:bg-gray-50"
              >
                Отказ
              </button>
            </div>
          </div>
        ) : (
          <div className="flex justify-between items-center">
            <div className="flex items-start gap-2">
              <div>
                <h1 className="text-xl font-bold text-gray-800">{project.name}</h1>
                {project.location && (
                  <p className="text-sm text-gray-500">{project.location}</p>
                )}
              </div>
              <button
                onClick={() => setShowEdit(true)}
                data-testid="project-edit-button"
                className="mt-0.5 text-gray-400 hover:text-gray-600 text-sm px-1.5 py-0.5 rounded hover:bg-gray-100"
                title="Редактирай проекта"
              >
                ✎
              </button>
            </div>
            <ExportButton
              projectId={project.id}
              projectName={project.name}
              onOpenGenerations={() => {
                setShowGenerations(true);
                setGenerationsRefreshKey((value) => value + 1);
              }}
            />
          </div>
        )}
      </div>

      {/* Main layout */}
      <div className="flex h-[calc(100vh-73px)]">
        {/* Left: module sidebar */}
        <aside className="w-80 border-r bg-white overflow-y-auto flex flex-col">
          {/* Module selector */}
          <div className="p-3 border-b">
            <h2 className="font-semibold text-gray-700 text-sm mb-2">Модули</h2>
            <div className="space-y-1">
              {MODULES.map((m) => (
                <button
                  key={m.key}
                  data-testid={`module-toggle-${m.key}`}
                  onClick={() =>
                    setActiveModule((prev) => (prev === m.key ? null : m.key))
                  }
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition flex items-center gap-2 ${
                    activeModule === m.key
                      ? "bg-blue-50 text-blue-700 border border-blue-200"
                      : "hover:bg-gray-50 text-gray-600 border border-transparent"
                  }`}
                >
                  <span>{m.icon}</span>
                  <span>{displayModuleLabel(m)}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Съдържание на ТП */}
          <div className="border-b">
            <button
              onClick={() => setShowOutline((v) => !v)}
              data-testid="outline-panel-toggle"
              className="w-full px-3 py-2.5 text-left text-sm font-semibold text-gray-700 flex justify-between items-center hover:bg-gray-50 transition"
            >
              <span>📐 Съдържание на ТП</span>
              <span className="text-gray-400 text-xs">
                {showOutline ? "▾" : "▸"}
              </span>
            </button>
            {showOutline && (
              <div className="px-3 pb-3">
                <OutlinePanel
                  projectId={project.id}
                  refreshKey={outlineRefreshKey}
                />
              </div>
            )}
          </div>

          {/* Линеен график */}
          <div className="border-b">
            <button
              onClick={() => setShowSchedule((v) => !v)}
              data-testid="schedule-panel-toggle"
              className="w-full px-3 py-2.5 text-left text-sm font-semibold text-gray-700 flex justify-between items-center hover:bg-gray-50 transition"
            >
              <span>📅 Линеен график</span>
              <span className="text-gray-400 text-xs">
                {showSchedule ? "▾" : "▸"}
              </span>
            </button>
            {showSchedule && (
              <div className="px-3 pb-3 space-y-3">
                <FileUploadPanel
                  projectId={project.id}
                  module="schedule"
                  onFileStatusChange={handleFileStatusChange}
                />
                <SchedulePanel
                  projectId={project.id}
                  refreshKey={scheduleRefreshKey}
                />
              </div>
            )}
          </div>

          {/* Генерирани текстове */}
          <div className="border-b">
            <button
              onClick={() => setShowGenerations((v) => !v)}
              data-testid="generations-panel-toggle"
              className="w-full px-3 py-2.5 text-left text-sm font-semibold text-gray-700 flex justify-between items-center hover:bg-gray-50 transition"
            >
              <span>📝 Генерации</span>
              <span className="text-gray-400 text-xs">
                {showGenerations ? "▾" : "▸"}
              </span>
            </button>
            {showGenerations && (
              <div className="px-3 pb-3">
                <GenerationsPanel
                  projectId={project.id}
                  refreshKey={generationsRefreshKey}
                />
              </div>
            )}
          </div>

          {/* Active module upload panel */}
          {activeModule && (
            <div className="p-3 flex-1 space-y-3">
              {activeModule === "legislation" && (
                <LegislationAutoPanel
                  status={legislationStatus}
                  loading={legislationStatusLoading}
                  refreshing={legislationRefreshing}
                  error={legislationError}
                  onRefresh={() => void refreshLegislation(project.id, true)}
                />
              )}
              <FileUploadPanel
                projectId={project.id}
                module={activeModule}
                onFileStatusChange={handleFileStatusChange}
              />
            </div>
          )}

          {!activeModule && (
            <div className="p-4 text-xs text-gray-400 text-center mt-4">
              Изберете модул за да качите файлове
            </div>
          )}

          {/* Workflow guide */}
          <div className="mt-auto border-t p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Работен процес
            </p>
            <ol className="space-y-2">
              {WORKFLOW_STEPS.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-gray-500">
                  <span className="shrink-0 w-5 h-5 rounded-full border border-gray-200 bg-gray-50 flex items-center justify-center font-semibold text-gray-400 text-[10px]">
                    {i + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </aside>

        {/* Right: Chat */}
        <div className="flex-1 p-4">
          <ChatPanel
            projectId={project.id}
            onOpenOutline={() => {
              setShowOutline(true);
              setOutlineRefreshKey((value) => value + 1);
            }}
            onOpenGenerations={() => {
              setShowGenerations(true);
              setGenerationsRefreshKey((value) => value + 1);
            }}
          />
        </div>
      </div>
    </main>
  );
}

function LegislationAutoPanel({
  status,
  loading,
  refreshing,
  error,
  onRefresh,
}: {
  status: LegislationStatusResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const loaded = status?.loaded_acts ?? 0;
  const configured = status?.configured_acts ?? 0;
  const isReady = status?.status === "ok";
  const isPartial = status?.status === "partial";
  const latest = status?.latest_fetched_at
    ? new Date(status.latest_fetched_at).toLocaleString("bg-BG")
    : "няма";

  return (
    <div
      data-testid="legislation-auto-panel"
      className={`rounded-lg border px-3 py-3 text-xs ${
        isReady
          ? "border-green-200 bg-green-50 text-green-800"
          : isPartial
            ? "border-amber-200 bg-amber-50 text-amber-800"
            : "border-blue-200 bg-blue-50 text-blue-800"
      }`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">Автоматично от Lex.bg</p>
          <p className="mt-0.5 leading-relaxed opacity-80">
            Оркестраторът проверява нормативната база при нужда и цитира само
            запазени проверени пасажи.
          </p>
        </div>
        <span className="shrink-0 rounded border border-current/20 px-1.5 py-0.5 font-medium">
          {loading ? "..." : `${loaded}/${configured || "?"}`}
        </span>
      </div>

      <dl className="space-y-1">
        <div className="flex justify-between gap-2">
          <dt className="opacity-70">Последна проверка</dt>
          <dd className="text-right">{latest}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="opacity-70">Нормативни chunks</dt>
          <dd>{status?.chunk_count ?? 0}</dd>
        </div>
      </dl>

      {status?.missing_acts?.length ? (
        <p
          className="mt-2 truncate opacity-80"
          title={status.missing_acts.join(", ")}
        >
          Липсват: {status.missing_acts.length} акта
        </p>
      ) : null}

      {error && <p className="mt-2 text-red-600">{error}</p>}

      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        data-testid="legislation-refresh-button"
        className="mt-3 w-full rounded-lg border bg-white px-3 py-2 text-blue-700 transition hover:bg-blue-50 disabled:opacity-50"
      >
        {refreshing ? "Обновява..." : "Обнови от Lex.bg"}
      </button>

      <p className="mt-2 leading-relaxed opacity-70">
        Качването по-долу е само за специфични указания, стандарти или актове,
        които не са част от стандартната Lex.bg база.
      </p>
    </div>
  );
}
