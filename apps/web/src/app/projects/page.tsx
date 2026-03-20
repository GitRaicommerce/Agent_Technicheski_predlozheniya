"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Project, ProjectStat } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [stats, setStats] = useState<Record<string, ProjectStat>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.projects.list(), api.projects.stats()])
      .then(([ps, st]) => {
        setProjects(ps);
        setStats(st);
      })
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
            {projects.map((p) => {
              const st = stats[p.id];
              return (
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

                  {/* Progress badges */}
                  {st && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      <StatBadge
                        icon="📎"
                        label={`${st.files} файл${st.files !== 1 ? "а" : ""}`}
                        active={st.files > 0}
                      />
                      <StatBadge
                        icon="📐"
                        label="Структура"
                        active={st.outline_locked}
                        activeClass="bg-green-50 text-green-700 border-green-200"
                        inactiveLabel="без структура"
                      />
                      <StatBadge
                        icon="✍️"
                        label={`${st.sections_generated} генер.`}
                        active={st.sections_generated > 0}
                        activeClass="bg-blue-50 text-blue-700 border-blue-200"
                      />
                      {st.sections_generated > 0 && (
                        <StatBadge
                          icon="✓"
                          label={`${st.sections_selected}/${st.sections_generated} избрани`}
                          active={st.sections_selected > 0}
                          activeClass="bg-green-50 text-green-700 border-green-200"
                        />
                      )}
                    </div>
                  )}

                  <p className="text-xs text-gray-400 mt-2">
                    Създаден:{" "}
                    {new Date(p.created_at).toLocaleDateString("bg-BG")}
                    {p.updated_at && p.updated_at !== p.created_at && (
                      <span className="ml-3">
                        Обновен:{" "}
                        {new Date(p.updated_at).toLocaleDateString("bg-BG")}
                      </span>
                    )}
                  </p>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}

function StatBadge({
  icon,
  label,
  active,
  activeClass = "bg-gray-100 text-gray-600 border-gray-200",
  inactiveLabel,
}: {
  icon: string;
  label: string;
  active: boolean;
  activeClass?: string;
  inactiveLabel?: string;
}) {
  const cls = active ? activeClass : "bg-gray-50 text-gray-400 border-gray-100";
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium ${cls}`}
    >
      <span>{icon}</span>
      <span>{active ? label : (inactiveLabel ?? label)}</span>
    </span>
  );
}
