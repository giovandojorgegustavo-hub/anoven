/**
 * /projects/[id] — detalle del proyecto compartido.
 *
 * "use client" justificado (A2.1): múltiples fetches paralelos, modales con
 * estado local (InviteMemberModal, confirmación de salida), tabs interactivas.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { MemberList } from "@/components/MemberList";
import { MentorSelector } from "@/components/MentorSelector";
import { InviteMemberModal } from "@/components/InviteMemberModal";

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

interface ProjectMemberRead {
  id: number;
  project_id: number;
  user_id: number;
  user_email: string;
  user_nombre: string;
  role: string;
  joined_at: string;
  invited_by_user_id: number | null;
}

interface ProjectMentorRead {
  id: number;
  project_id: number;
  mentor_id: number;
  mentor_slug: string;
  mentor_nombre: string;
  added_by_user_email: string;
  added_at: string;
}

type Tab = "members" | "mentors" | "conversations";

const TAB_LABELS: Record<Tab, string> = {
  members: "Miembros",
  mentors: "Mentores",
  conversations: "Conversaciones",
};

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = Number(params.id);

  const [project, setProject] = useState<ProjectShareView | null>(null);
  const [members, setMembers] = useState<ProjectMemberRead[] | null>(null);
  const [mentors, setMentors] = useState<ProjectMentorRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("members");
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [isLeaving, setIsLeaving] = useState(false);
  const [leaveError, setLeaveError] = useState<string | null>(null);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    setError(null);

    try {
      const [projectsRes, membersRes, mentorsRes] = await Promise.all([
        fetch(`${API_URL}/api/projects/mine`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_URL}/api/projects/${projectId}/members`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_URL}/api/projects/${projectId}/mentors`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (projectsRes.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }

      if (!projectsRes.ok) throw new Error(`HTTP ${projectsRes.status} al cargar proyectos`);
      if (!membersRes.ok) throw new Error(`HTTP ${membersRes.status} al cargar miembros`);
      if (!mentorsRes.ok) throw new Error(`HTTP ${mentorsRes.status} al cargar mentores`);

      const allProjects: ProjectShareView[] = await projectsRes.json();
      const found = allProjects.find((p) => p.id === projectId);
      if (!found) {
        router.replace("/projects");
        return;
      }

      setProject(found);
      setMembers(await membersRes.json());
      setMentors(await mentorsRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el proyecto");
    }
  }, [projectId, router]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleLeave() {
    const token = getToken();
    if (!token) return;
    setIsLeaving(true);
    setLeaveError(null);

    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}/leave`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `HTTP ${res.status}`);
      }
      router.replace("/projects");
    } catch (err) {
      setLeaveError(err instanceof Error ? err.message : "Error al salir del proyecto");
      setShowLeaveConfirm(false);
    } finally {
      setIsLeaving(false);
    }
  }

  const isOwner = project?.role === "owner";

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-4xl">

          {/* Back nav */}
          <div className="mb-6">
            <Link
              href="/projects"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Proyectos compartidos
            </Link>
          </div>

          {/* Error state */}
          {error && (
            <div className="mb-6 flex items-center justify-between rounded-lg border border-accent bg-accent-soft px-4 py-3">
              <p className="text-sm text-accent">{error}</p>
              <button
                onClick={loadAll}
                className="ml-4 rounded-lg border border-accent px-3 py-1 text-xs text-accent hover:bg-accent hover:text-accent-ink"
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Loading skeleton */}
          {project === null && !error && (
            <div className="space-y-6">
              <div className="h-24 animate-pulse rounded-2xl border border-rule bg-paper-dim" />
              <div className="h-64 animate-pulse rounded-2xl border border-rule bg-paper-dim" />
            </div>
          )}

          {/* Project content */}
          {project !== null && (
            <>
              {/* Header */}
              <header className="mb-8 border-b border-rule pb-6">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={
                          isOwner
                            ? "rounded-full bg-accent-soft px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent"
                            : "rounded-full bg-paper-deep px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-muted"
                        }
                      >
                        {isOwner ? "Propietario" : "Miembro"}
                      </span>
                    </div>
                    <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
                      {project.name}
                    </h1>
                    {project.description && (
                      <p className="mt-2 text-sm text-ink-soft">{project.description}</p>
                    )}
                    <div className="mt-3 flex items-center gap-4 text-xs text-ink-muted">
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
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    {isOwner && (
                      <button
                        onClick={() => setIsInviteModalOpen(true)}
                        className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
                      >
                        Invitar miembro
                      </button>
                    )}
                    {!isOwner && (
                      <button
                        onClick={() => setShowLeaveConfirm(true)}
                        className="rounded-xl border border-rule px-4 py-2 text-sm text-ink-soft hover:border-accent hover:text-accent"
                      >
                        Salir del proyecto
                      </button>
                    )}
                  </div>
                </div>

                {/* Leave confirm */}
                {showLeaveConfirm && (
                  <div className="mt-4 rounded-xl border border-rule bg-paper p-4">
                    <p className="text-sm text-ink">
                      ¿Seguro que quieres salir de este proyecto? Perderás acceso a las
                      conversaciones compartidas.
                    </p>
                    {leaveError && (
                      <p className="mt-2 text-xs text-accent">{leaveError}</p>
                    )}
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={handleLeave}
                        disabled={isLeaving}
                        className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
                      >
                        {isLeaving ? "Saliendo..." : "Sí, salir"}
                      </button>
                      <button
                        onClick={() => setShowLeaveConfirm(false)}
                        disabled={isLeaving}
                        className="rounded-lg border border-rule px-4 py-1.5 text-xs text-ink-soft hover:bg-paper-dim disabled:opacity-60"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                )}
              </header>

              {/* Tabs */}
              <div className="mb-6 flex items-center gap-1 border-b border-rule">
                {(["members", "mentors", "conversations"] as Tab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={
                      activeTab === tab
                        ? "border-b-2 border-accent px-4 py-2 text-sm font-medium text-accent"
                        : "px-4 py-2 text-sm text-ink-soft hover:text-ink"
                    }
                  >
                    {TAB_LABELS[tab]}
                  </button>
                ))}
              </div>

              {/* Tab: Members */}
              {activeTab === "members" && members !== null && (
                <MemberList
                  projectId={projectId}
                  members={members}
                  isOwner={isOwner}
                  onMemberRemoved={loadAll}
                />
              )}

              {/* Tab: Mentors */}
              {activeTab === "mentors" && mentors !== null && (
                <MentorSelector
                  projectId={projectId}
                  currentMentors={mentors}
                  isOwner={isOwner}
                  onChange={loadAll}
                />
              )}

              {/* Tab: Conversations */}
              {activeTab === "conversations" && (
                <div className="space-y-4">
                  <p className="text-sm text-ink-soft">
                    Conversaciones del proyecto.{" "}
                    <Link
                      href={`/projects/${projectId}/conversations`}
                      className="text-accent underline-offset-4 hover:underline"
                    >
                      Ver todas
                    </Link>
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Invite modal */}
      {project !== null && (
        <InviteMemberModal
          projectId={projectId}
          isOpen={isInviteModalOpen}
          onClose={() => setIsInviteModalOpen(false)}
          onSuccess={() => {
            setIsInviteModalOpen(false);
            loadAll();
          }}
        />
      )}
    </AppShell>
  );
}
