"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Project } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects
      .list()
      .then(setProjects)
      .catch(() => setError("Грешка при зареждане на проектите."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold text-gray-800">Моите проекти</h1>
          <Link
            href="/projects/new"
            className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
          >
            + Нов проект
          </Link>
        </div>

        {loading ? (
          <p className="text-gray-500">Зарежда се...</p>
        ) : error ? (
          <p className="text-red-500">{error}</p>
        ) : projects.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg">Нямате проекти все още.</p>
            <Link
              href="/projects/new"
              className="text-blue-600 hover:underline mt-2 block"
            >
              Създайте първия си проект
            </Link>
          </div>
        ) : (
          <div className="grid gap-4">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="block p-5 bg-white rounded-xl shadow-sm border hover:border-blue-400 transition"
              >
                <h2 className="font-semibold text-gray-800">{p.name}</h2>
                {p.location && (
                  <p className="text-sm text-gray-500">{p.location}</p>
                )}
                {p.description && (
                  <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                    {p.description}
                  </p>
                )}
                <p className="text-xs text-gray-400 mt-2">
                  Създаден: {new Date(p.created_at).toLocaleDateString("bg-BG")}
                  {p.updated_at && p.updated_at !== p.created_at && (
                    <span className="ml-3">
                      Обновен: {new Date(p.updated_at).toLocaleDateString("bg-BG")}
                    </span>
                  )}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
