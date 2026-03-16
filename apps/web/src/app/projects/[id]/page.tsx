"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, Project } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import ExportButton from "@/components/ExportButton";

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (params.id) {
      api.projects.get(params.id).then(setProject).finally(() => setLoading(false));
    }
  }, [params.id]);

  if (loading) return <main className="p-8 text-gray-500">Зарежда се...</main>;
  if (!project) return <main className="p-8 text-red-500">Проектът не е намерен.</main>;

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-8 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold text-gray-800">{project.name}</h1>
          {project.location && <p className="text-sm text-gray-500">{project.location}</p>}
        </div>
        <ExportButton projectId={project.id} projectName={project.name} />
      </div>

      {/* Main layout */}
      <div className="flex h-[calc(100vh-73px)]">
        {/* Left: future panels (outline, schedule, evidence) */}
        <aside className="w-80 border-r bg-white p-4 overflow-y-auto">
          <h2 className="font-semibold text-gray-700 mb-3">Модули</h2>
          <div className="space-y-2 text-sm text-gray-500">
            <div className="p-3 rounded-lg border hover:bg-gray-50 cursor-pointer">
              📄 Примерни ТП
            </div>
            <div className="p-3 rounded-lg border hover:bg-gray-50 cursor-pointer">
              📋 Документация
            </div>
            <div className="p-3 rounded-lg border hover:bg-gray-50 cursor-pointer">
              📅 Линеен график
            </div>
            <div className="p-3 rounded-lg border hover:bg-gray-50 cursor-pointer">
              ⚖️ Законодателство
            </div>
            <div className="p-3 rounded-lg border hover:bg-gray-50 cursor-pointer">
              🗂️ Структура на ТП
            </div>
          </div>
        </aside>

        {/* Right: Chat */}
        <div className="flex-1 p-4">
          <ChatPanel projectId={project.id} />
        </div>
      </div>
    </main>
  );
}
