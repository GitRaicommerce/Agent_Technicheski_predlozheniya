"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, Project } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import ExportButton from "@/components/ExportButton";
import FileUploadPanel from "@/components/FileUploadPanel";
import OutlinePanel from "@/components/OutlinePanel";

type Module = "examples" | "tender_docs" | "schedule" | "legislation";

const MODULES: { key: Module; label: string; icon: string }[] = [
  { key: "examples", label: "Примерни ТП", icon: "📄" },
  { key: "tender_docs", label: "Документация", icon: "📋" },
  { key: "schedule", label: "Линеен график", icon: "📅" },
  { key: "legislation", label: "Законодателство", icon: "⚖️" },
];

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeModule, setActiveModule] = useState<Module | null>(null);
  const [showOutline, setShowOutline] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editData, setEditData] = useState({ name: "", location: "", description: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (params.id) {
      api.projects
        .get(params.id)
        .then((p) => {
          setProject(p);
          setEditData({ name: p.name, location: p.location ?? "", description: p.description ?? "" });
        })
        .finally(() => setLoading(false));
    }
  }, [params.id]);

  async function handleSaveEdit() {
    if (!project) return;
    setSaving(true);
    try {
      const updated = await api.projects.update(project.id, {
        name: editData.name,
        location: editData.location || undefined,
        description: editData.description || undefined,
      });
      setProject(updated);
      setShowEdit(false);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <main className="p-8 text-gray-500">Зарежда се...</main>;
  if (!project)
    return <main className="p-8 text-red-500">Проектът не е намерен.</main>;

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-8 py-4">
        {showEdit ? (
          <div className="flex items-start gap-3">
            <div className="flex-1 space-y-2">
              <input
                className="w-full border rounded-lg px-3 py-1.5 text-sm font-semibold text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editData.name}
                onChange={(e) => setEditData((d) => ({ ...d, name: e.target.value }))}
                placeholder="Наименование на проекта"
              />
              <input
                className="w-full border rounded-lg px-3 py-1.5 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editData.location}
                onChange={(e) => setEditData((d) => ({ ...d, location: e.target.value }))}
                placeholder="Местоположение"
              />
              <input
                className="w-full border rounded-lg px-3 py-1.5 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editData.description}
                onChange={(e) => setEditData((d) => ({ ...d, description: e.target.value }))}
                placeholder="Описание"
              />
            </div>
            <div className="flex gap-2 pt-0.5">
              <button
                onClick={handleSaveEdit}
                disabled={saving || !editData.name.trim()}
                className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Запазва..." : "Запази"}
              </button>
              <button
                onClick={() => setShowEdit(false)}
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
                className="mt-0.5 text-gray-400 hover:text-gray-600 text-sm px-1.5 py-0.5 rounded hover:bg-gray-100"
                title="Редактирай проекта"
              >
                ✎
              </button>
            </div>
            <ExportButton projectId={project.id} projectName={project.name} />
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
                  <span>{m.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Структура на ТП */}
          <div className="border-b">
            <button
              onClick={() => setShowOutline((v) => !v)}
              className="w-full px-3 py-2.5 text-left text-sm font-semibold text-gray-700 flex justify-between items-center hover:bg-gray-50 transition"
            >
              <span>📐 Структура на ТП</span>
              <span className="text-gray-400 text-xs">
                {showOutline ? "▾" : "▸"}
              </span>
            </button>
            {showOutline && (
              <div className="px-3 pb-3">
                <OutlinePanel projectId={project.id} />
              </div>
            )}
          </div>

          {/* Active module upload panel */}
          {activeModule && (
            <div className="p-3 flex-1">
              <FileUploadPanel projectId={project.id} module={activeModule} />
            </div>
          )}

          {!activeModule && (
            <div className="p-4 text-xs text-gray-400 text-center mt-4">
              Изберете модул за да качите файлове
            </div>
          )}
        </aside>

        {/* Right: Chat */}
        <div className="flex-1 p-4">
          <ChatPanel projectId={project.id} />
        </div>
      </div>
    </main>
  );
}
