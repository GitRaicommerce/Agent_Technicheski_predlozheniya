"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, Project } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import ExportButton from "@/components/ExportButton";
import FileUploadPanel from "@/components/FileUploadPanel";

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

  useEffect(() => {
    if (params.id) {
      api.projects
        .get(params.id)
        .then(setProject)
        .finally(() => setLoading(false));
    }
  }, [params.id]);

  if (loading) return <main className="p-8 text-gray-500">Зарежда се...</main>;
  if (!project)
    return <main className="p-8 text-red-500">Проектът не е намерен.</main>;

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-8 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold text-gray-800">{project.name}</h1>
          {project.location && (
            <p className="text-sm text-gray-500">{project.location}</p>
          )}
        </div>
        <ExportButton projectId={project.id} projectName={project.name} />
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

          {/* Active module upload panel */}
          {activeModule && (
            <div className="p-3 flex-1">
              <FileUploadPanel
                projectId={project.id}
                module={activeModule}
              />
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
