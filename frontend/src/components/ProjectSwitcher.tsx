/**
 * ProjectSwitcher — dropdown en el sidebar para cambiar de proyecto activo.
 *
 * Extiende la funcionalidad del switcher base de AppShell con soporte para
 * proyectos donde el user es miembro (not just owner).
 *
 * "use client" justificado (A2.1): estado de dropdown + fetch + eventos onClick.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 *
 * Props:
 *   currentProjectId — ID del proyecto activo actual
 *   onSwitch — callback después de cambiar proyecto (para reload)
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

type ProjectRole = "owner" | "member";

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

interface ProjectSwitcherProps {
  currentProjectId: number | null;
  onSwitch?: (newProjectId: number) => void;
}

const ROLE_LABELS: Record<ProjectRole, string> = {
  owner: "Prop.",
  member: "Miembro",
};

export function ProjectSwitcher({ currentProjectId, onSwitch }: ProjectSwitcherProps) {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectShareView[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    fetch(`${API_URL}/api/projects/mine`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: ProjectShareView[]) => setProjects(data))
      .catch(() => {});
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen]);

  const activeProject = projects.find((p) => p.id === currentProjectId);

  async function handleSwitch(projectId: number) {
    if (projectId === currentProjectId) {
      setIsOpen(false);
      return;
    }

    const token = getToken();
    if (!token) return;

    setSwitching(true);
    try {
      const res = await fetch(`${API_URL}/users/me/active-project`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ project_id: projectId }),
      });

      if (res.ok) {
        setIsOpen(false);
        onSwitch?.(projectId);
        router.refresh();
      }
    } catch {
      // Silently fail — project switch is best-effort
    } finally {
      setSwitching(false);
    }
  }

  if (projects.length === 0) return null;

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setIsOpen((v) => !v)}
        disabled={switching}
        aria-label="Cambiar proyecto"
        title="Proyectos compartidos"
        className="flex items-center gap-1.5 rounded-md border border-rule bg-paper px-2 py-1 text-left text-[11px] text-ink hover:bg-paper-dim disabled:opacity-60"
      >
        <span className="truncate max-w-[96px] font-serif italic">
          {activeProject?.name ?? "Proyectos"}
        </span>
        {activeProject && (
          <span
            className={
              activeProject.role === "owner"
                ? "rounded-full bg-accent-soft px-1.5 py-px text-[9px] font-medium text-accent"
                : "rounded-full bg-paper-deep px-1.5 py-px text-[9px] font-medium text-ink-muted"
            }
          >
            {ROLE_LABELS[activeProject.role]}
          </span>
        )}
        <span className="text-ink-muted">▾</span>
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 w-56 rounded-xl border border-rule bg-paper p-1 shadow-lg">
          {/* Owned projects */}
          {projects.filter((p) => p.role === "owner").length > 0 && (
            <>
              <p className="px-2 py-1 text-[9px] font-medium uppercase tracking-[0.14em] text-ink-muted">
                Mis proyectos
              </p>
              {projects
                .filter((p) => p.role === "owner")
                .map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleSwitch(p.id)}
                    className={
                      p.id === currentProjectId
                        ? "flex w-full items-center justify-between rounded-lg bg-paper-dim px-2 py-1.5 text-left"
                        : "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-paper-dim"
                    }
                  >
                    <span className="truncate font-serif text-xs italic text-ink">
                      {p.name}
                    </span>
                    <span className="ml-2 text-[9px] text-ink-muted">
                      {p.members_count} {p.members_count === 1 ? "miembro" : "miembros"}
                    </span>
                  </button>
                ))}
            </>
          )}

          {/* Member-of projects */}
          {projects.filter((p) => p.role === "member").length > 0 && (
            <>
              <p className="mt-1 px-2 py-1 text-[9px] font-medium uppercase tracking-[0.14em] text-ink-muted">
                Miembro
              </p>
              {projects
                .filter((p) => p.role === "member")
                .map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleSwitch(p.id)}
                    className={
                      p.id === currentProjectId
                        ? "flex w-full items-center justify-between rounded-lg bg-paper-dim px-2 py-1.5 text-left"
                        : "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-paper-dim"
                    }
                  >
                    <span className="truncate font-serif text-xs italic text-ink-soft">
                      {p.name}
                    </span>
                    <span className="ml-2 rounded-full bg-paper-deep px-1.5 py-px text-[9px] text-ink-muted">
                      Miembro
                    </span>
                  </button>
                ))}
            </>
          )}

          {/* Divider + link to full list */}
          <div className="mt-1 border-t border-rule pt-1">
            <a
              href="/projects"
              className="block rounded-lg px-2 py-1.5 text-xs text-ink-muted hover:bg-paper-dim hover:text-ink"
            >
              Ver todos los proyectos →
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
