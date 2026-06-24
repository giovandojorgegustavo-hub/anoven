/**
 * /projects — lista de proyectos del usuario (owned + member-of).
 *
 * "use client" justificado (A2.1): estado local para filtro + fetch en cliente.
 * Tuteo limeño culto en todo el copy. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

type ProjectRole = "owner" | "member";
type RoleFilter = "all" | "owner" | "member";

interface ProjectShareView {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  role: ProjectRole;
  members_count: number;
  mentors_count: number;
  created_at: string;
}

const ROLE_FILTER_OPTIONS: { value: RoleFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "owner", label: "Propietario" },
  { value: "member", label: "Miembro" },
];

const ROLE_LABELS: Record<ProjectRole, string> = {
  owner: "Propietario",
  member: "Miembro",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-PE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectShareView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RoleFilter>("all");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    setError(null);
    setProjects(null);

    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/projects/mine`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (res.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setProjects(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar los proyectos");
      }
    })();
  }, [router]);

  const visible =
    projects === null
      ? null
      : filter === "all"
        ? projects
        : projects.filter((p) => p.role === filter);

  function handleRetry() {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    setProjects(null);
    setError(null);
    router.refresh();
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-4xl">
          {/* Header */}
          <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Colaboración
              </p>
              <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
                Proyectos compartidos
              </h1>
              <p className="mt-2 text-sm text-ink-soft">
                Proyectos en los que participas, ya sea como propietario o miembro.
              </p>
            </div>
            <Link
              href="/dashboard"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Dashboard
            </Link>
          </header>

          {/* Error state */}
          {error && (
            <div className="mb-6 flex items-center justify-between rounded-lg border border-accent bg-accent-soft px-4 py-3">
              <p className="text-sm text-accent">{error}</p>
              <button
                onClick={handleRetry}
                className="ml-4 rounded-lg border border-accent px-3 py-1 text-xs text-accent hover:bg-accent hover:text-accent-ink"
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Role filter */}
          <div className="mb-6 flex flex-wrap items-center gap-2">
            {ROLE_FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setFilter(opt.value)}
                className={
                  filter === opt.value
                    ? "rounded-full bg-ink px-3 py-1 text-xs text-paper"
                    : "rounded-full border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper-dim"
                }
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Loading skeleton */}
          {visible === null && !error && (
            <div className="grid gap-4 sm:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-36 animate-pulse rounded-2xl border border-rule bg-paper-dim"
                />
              ))}
            </div>
          )}

          {/* Empty state */}
          {visible !== null && visible.length === 0 && (
            <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-10 text-center">
              <p className="font-serif text-xl italic text-ink-soft">
                {filter === "all"
                  ? "Aún no tienes proyectos compartidos."
                  : filter === "owner"
                    ? "No eres propietario de ningún proyecto compartido."
                    : "No eres miembro de ningún proyecto compartido."}
              </p>
              {filter === "all" && (
                <p className="mt-2 text-sm text-ink-muted">
                  Crea uno desde el ProjectSwitcher en el panel lateral.
                </p>
              )}
            </div>
          )}

          {/* Project cards */}
          {visible !== null && visible.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2">
              {visible.map((project, i) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="group block animate-fade-in-up rounded-2xl border border-rule bg-paper-dim p-6 transition-colors hover:border-rule-strong hover:bg-paper"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  {/* Role badge */}
                  <div className="mb-3 flex items-center justify-between">
                    <span
                      className={
                        project.role === "owner"
                          ? "rounded-full bg-accent-soft px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent"
                          : "rounded-full bg-paper-deep px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-muted"
                      }
                    >
                      {ROLE_LABELS[project.role]}
                    </span>
                    <span className="text-[10px] text-ink-muted">
                      {formatDate(project.created_at)}
                    </span>
                  </div>

                  {/* Project name */}
                  <h2 className="font-serif text-xl font-medium tracking-tight text-ink group-hover:text-accent">
                    {project.name}
                  </h2>

                  {/* Description */}
                  {project.description && (
                    <p className="mt-1 line-clamp-2 text-sm text-ink-soft">
                      {project.description}
                    </p>
                  )}

                  {/* Stats */}
                  <div className="mt-4 flex items-center gap-4 text-xs text-ink-muted">
                    <span>
                      {project.members_count}{" "}
                      {project.members_count === 1 ? "miembro" : "miembros"}
                    </span>
                    <span>·</span>
                    <span>
                      {project.mentors_count}{" "}
                      {project.mentors_count === 1 ? "mentor" : "mentores"}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
