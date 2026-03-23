"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { api, Project, ProjectStat } from "@/lib/api";

type SortKey = "newest" | "oldest" | "az" | "za";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [stats, setStats] = useState<Record<string, ProjectStat>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");

  useEffect(() => {
    Promise.all([api.projects.list(), api.projects.stats()])
      .then(([ps, st]) => {
        setProjects(ps);
        setStats(st);
      })
      .catch(() => setError("Грешка при зареждане на проектите."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = q
      ? projects.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            (p.location ?? "").toLowerCase().includes(q) ||
            (p.description ?? "").toLowerCase().includes(q),
        )
      : [...projects];

    list.sort((a, b) => {
      if (sort === "newest") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (sort === "oldest") return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      if (sort === "az") return a.name.localeCompare(b.name, "bg");
      if (sort === "za") return b.name.localeCompare(a.name, "bg");
      return 0;
    });
    return list;
  }, [projects, search, sort]);

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

        {/* Search + Sort toolbar */}
        {!loading && !error && projects.length > 0 && (
          <div className="flex gap-3 mb-4">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Търси по название, местоположение..."
              className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400"
            />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-blue-400"
            >
              <option value="newest">Най-нови</option>
              <option value="oldest">Най-стари</option>
              <option value="az">А → Я</option>
              <option value="za">Я → А</option>
            </select>
          </div>
        )}

        {loading ? (
          <div className="grid gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="p-5 bg-white rounded-xl shadow-sm border animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-2/3 mb-2" />
                <div className="h-3 bg-gray-100 rounded w-1/3 mb-3" />
                <div className="flex gap-2">
                  <div className="h-5 bg-gray-100 rounded-full w-16" />
                  <div className="h-5 bg-gray-100 rounded-full w-20" />
                  <div className="h-5 bg-gray-100 rounded-full w-24" />
                </div>
              </div>
            ))}
          </div>
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
        ) : filtered.length === 0 ? (
          <p className="text-gray-400 text-sm py-8 text-center">
            Няма проекти, съответстващи на "{search}".
          </p>
        ) : (
          <div className="grid gap-4">
            {search && (
              <p className="text-xs text-gray-400">
                {filtered.length} от {projects.length} проекта
              </p>
            )}
            {filtered.map((p) => {
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
                    Създаден: {new Date(p.created_at).toLocaleDateString("bg-BG")}
                    {p.updated_at && p.updated_at !== p.created_at && (
                      <span className="ml-3">
                        Обновен: {new Date(p.updated_at).toLocaleDateString("bg-BG")}
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
  const cls = active
    ? activeClass
    : "bg-gray-50 text-gray-400 border-gray-100";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium ${cls}`}>
      <span>{icon}</span>
      <span>{active ? label : (inactiveLabel ?? label)}</span>
    </span>
  );
}
