/**
 * AppShell — layout unificado de la app post-login.
 *
 * Sidebar permanente con:
 *   - Wordmark "Anoven"
 *   - Project switcher
 *   - Toggle "solo focus" para filtrar conversaciones con star
 *   - Lista de conversaciones compactas (estilo Claude.ai)
 *     - Bold si tiene mensajes no leídos (last_seen_at < updated_at)
 *     - Star icon para toggle focus
 *     - Edit inline del título (icono ✎)
 *   - Links de navegación y logout
 */

"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import type { Project, User } from "@/lib/user";
import { SupportTicketModal } from "@/components/support/SupportTicketModal";
import { InvitationsBadge } from "@/components/InvitationsBadge";

type Conv = {
  id: number;
  mentor_id: number;
  title: string | null;
  updated_at: string;
  last_seen_at: string | null;
  is_focused: boolean;
  unread: boolean;
  message_count: number;
  mentor: { id: number; nombre: string; canon: string };
  // Shared-project indicator (anoven-shared-projects batch 6 — T3.14)
  is_shared_project?: boolean;
};

function relativeTime(iso: string): string {
  const diffSec = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diffSec < 60) return "ahora";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h`;
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d`;
  return new Date(iso).toLocaleDateString("es-AR", {
    day: "numeric",
    month: "short",
  });
}

export function AppShell({
  children,
  activeConvId,
}: {
  children: ReactNode;
  activeConvId?: number;
}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [conversations, setConversations] = useState<Conv[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isTicketModalOpen, setIsTicketModalOpen] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [onlyFocused, setOnlyFocused] = useState(false);
  // edit inline
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const [meRes, pRes, cRes] = await Promise.all([
          fetch(`${API_URL}/users/me`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_URL}/projects`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_URL}/conversations`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);
        if (meRes.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (!meRes.ok) throw new Error(`HTTP ${meRes.status}`);
        const me: User = await meRes.json();
        if (me.onboarding_state !== "passed") {
          router.replace("/onboarding");
          return;
        }
        setUser(me);
        if (pRes.ok) setProjects(await pRes.json());
        if (cRes.ok) setConversations(await cRes.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  // Cuando cambia el activeConvId, marcamos como visto en el backend
  useEffect(() => {
    if (!activeConvId) return;
    const token = getToken();
    if (!token) return;
    fetch(`${API_URL}/conversations/${activeConvId}/seen`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((updated) => {
        if (!updated) return;
        setConversations((prev) =>
          prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c)),
        );
      })
      .catch(() => {});
  }, [activeConvId]);

  async function switchProject(projectId: number) {
    if (!user || user.active_project_id === projectId) {
      setSwitcherOpen(false);
      return;
    }
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/users/me/active-project`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setUser(await res.json());
      const cRes = await fetch(`${API_URL}/conversations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (cRes.ok) setConversations(await cRes.json());
      setSwitcherOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }

  async function toggleFocus(conv: Conv) {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/conversations/${conv.id}/focus`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ is_focused: !conv.is_focused }),
      });
      if (!res.ok) return;
      const updated = await res.json();
      setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } catch {}
  }

  async function saveTitle(convId: number) {
    const trimmed = editingValue.trim();
    setEditingId(null);
    if (!trimmed) return;
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/conversations/${convId}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      });
      if (!res.ok) return;
      const updated = await res.json();
      setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } catch {}
  }

  function handleLogout() {
    clearToken();
    router.replace("/");
  }

  const activeProject = projects.find((p) => p.id === user?.active_project_id) ?? null;

  // Filtrar por focus si está activo
  const visibleConvs = onlyFocused
    ? conversations.filter((c) => c.is_focused)
    : conversations;

  // Agrupar por mentor manteniendo orden
  const byMentor = new Map<number, { name: string; convs: Conv[] }>();
  for (const c of visibleConvs) {
    const entry = byMentor.get(c.mentor_id) ?? { name: c.mentor.nombre, convs: [] };
    entry.convs.push(c);
    byMentor.set(c.mentor_id, entry);
  }

  return (
    <>
    <main className="flex flex-1 overflow-hidden">
      {sidebarOpen && (
        <div
          aria-hidden
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-ink/40 backdrop-blur-sm sm:hidden"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-80 flex-col border-r border-rule bg-paper-dim transition-transform sm:relative sm:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full sm:translate-x-0"
        }`}
      >
        {/* Header: brand + project + filter */}
        <div className="border-b border-rule px-3 py-3">
          <div className="flex items-center justify-between">
            <Link
              href="/dashboard"
              className="group inline-flex items-baseline gap-1.5 font-serif text-xl italic tracking-tight text-ink"
            >
              <span className="text-accent transition-transform group-hover:rotate-12">❦</span>
              <span>Anoven</span>
            </Link>
            <button
              type="button"
              aria-label="Cerrar"
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-1 text-ink-soft hover:text-ink sm:hidden"
            >
              ✕
            </button>
          </div>

          {activeProject && (
            <div className="relative mt-2">
              <button
                onClick={() => setSwitcherOpen((v) => !v)}
                className="flex w-full items-center justify-between gap-2 rounded-md border border-rule bg-paper px-2.5 py-1.5 text-left text-xs text-ink hover:bg-paper-deep"
              >
                <span className="truncate font-serif italic">{activeProject.name}</span>
                <span className="text-ink-muted">▾</span>
              </button>
              {switcherOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setSwitcherOpen(false)} />
                  <div className="absolute left-0 right-0 z-20 mt-1 rounded-md border border-rule bg-paper p-1 shadow-md">
                    {projects.map((p) => {
                      const active = p.id === activeProject.id;
                      return (
                        <button
                          key={p.id}
                          onClick={() => switchProject(p.id)}
                          className={
                            active
                              ? "block w-full rounded-sm bg-paper-dim px-2 py-1 text-left text-xs font-serif italic text-ink"
                              : "block w-full rounded-sm px-2 py-1 text-left text-xs font-serif italic text-ink-soft hover:bg-paper-dim hover:text-ink"
                          }
                        >
                          {p.name}
                          {p.is_default && (
                            <span className="ml-1.5 text-[9px] uppercase tracking-wide text-ink-muted">
                              default
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Toggle solo focus */}
          <label className="mt-2 flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1 text-[11px] text-ink-soft hover:bg-paper">
            <span className="flex items-center gap-1.5">
              <span className={onlyFocused ? "text-accent" : "text-ink-muted"}>★</span>
              Solo focus
            </span>
            <span className="text-ink-muted">
              {conversations.filter((c) => c.is_focused).length}
            </span>
            <input
              type="checkbox"
              checked={onlyFocused}
              onChange={(e) => setOnlyFocused(e.target.checked)}
              className="hidden"
            />
          </label>
        </div>

        {/* Lista de conversaciones — compacta */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {user === null ? (
            // Skeleton de carga: 3 grupos con 2 items cada uno
            <div className="space-y-3">
              {[0, 1, 2].map((g) => (
                <div key={g} className="mb-3">
                  <div className="mx-2 my-1 h-2 w-16 animate-pulse-dot rounded bg-rule" />
                  <div className="space-y-1">
                    {[0, 1].map((i) => (
                      <div
                        key={i}
                        className="mx-1 flex items-center gap-2 rounded-md px-2 py-1"
                      >
                        <div className="h-3 w-3 animate-pulse-dot rounded bg-rule" />
                        <div className="h-3 flex-1 animate-pulse-dot rounded bg-rule" />
                        <div className="h-2 w-6 animate-pulse-dot rounded bg-rule" />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : visibleConvs.length === 0 ? (
            <div className="mx-2 mt-4 rounded-md border border-dashed border-rule p-3 text-center">
              <p className="font-serif text-xs italic leading-relaxed text-ink-soft">
                {onlyFocused
                  ? "Cuando marqués chats con ★, los vas a ver acá."
                  : "Tu primera conversación va a aparecer en este sidebar."}
              </p>
            </div>
          ) : (
            (() => {
              return (
                <ul className="space-y-0.5">
                  {visibleConvs.map((c) => {
                    const active = c.id === activeConvId;
                    const isEditing = editingId === c.id;
                    return (
                      <li key={c.id} className="group relative">
                        {isEditing ? (
                          <div className="flex items-center gap-1 px-2 py-1">
                            <input
                              autoFocus
                              value={editingValue}
                              onChange={(e) => setEditingValue(e.target.value)}
                              onBlur={() => saveTitle(c.id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") saveTitle(c.id);
                                if (e.key === "Escape") setEditingId(null);
                              }}
                              className="w-full rounded-sm border border-accent bg-paper px-1.5 py-0.5 text-xs text-ink outline-none"
                            />
                          </div>
                        ) : (
                          <Link
                            href={`/chat/${c.id}`}
                            onClick={() => setSidebarOpen(false)}
                            className={
                              active
                                ? "flex items-center gap-1.5 rounded-md bg-paper px-2 py-1 text-xs text-ink"
                                : "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-ink-soft hover:bg-paper hover:text-ink"
                            }
                          >
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                toggleFocus(c);
                              }}
                              aria-label={c.is_focused ? "Quitar focus" : "Marcar focus"}
                              className={
                                c.is_focused
                                  ? "shrink-0 text-accent hover:opacity-70"
                                  : "shrink-0 text-ink-muted/40 opacity-0 hover:text-accent group-hover:opacity-100"
                              }
                            >
                              ★
                            </button>
                            <span
                              className={`min-w-0 flex-1 truncate ${
                                c.unread ? "font-semibold text-ink" : ""
                              }`}
                            >
                              {c.title ?? `Conversación #${c.id}`}
                            </span>
                            <span className="shrink-0 truncate font-serif text-[10px] italic text-ink-muted max-w-[80px]">
                              {c.mentor.nombre}
                            </span>
                            {c.is_shared_project && (
                              <span
                                title="Proyecto compartido"
                                className="shrink-0 text-[9px] font-medium uppercase tracking-[0.1em] text-accent opacity-70"
                                aria-label="Proyecto compartido"
                              >
                                ·comp
                              </span>
                            )}
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                setEditingValue(c.title ?? "");
                                setEditingId(c.id);
                              }}
                              aria-label="Renombrar"
                              className="shrink-0 text-ink-muted opacity-0 hover:text-accent group-hover:opacity-100"
                            >
                              ✎
                            </button>
                          </Link>
                        )}
                      </li>
                    );
                  })}
                </ul>
              );
            })()
          )}
        </div>

        {/* Footer: nav + logout */}
        <div className="border-t border-rule p-2 text-[11px]">
          <Link
            href="/dashboard"
            className="block rounded-sm px-2 py-1 text-ink-soft hover:bg-paper hover:text-ink"
          >
            + Nueva conversación
          </Link>
          <Link
            href="/mentors"
            className="block rounded-sm px-2 py-1 text-ink-soft hover:bg-paper hover:text-ink"
          >
            Mentores
          </Link>
          <Link
            href="/projects"
            className="block rounded-sm px-2 py-1 text-ink-soft hover:bg-paper hover:text-ink"
          >
            Proyectos
          </Link>
          <div className="mt-1 px-2">
            <InvitationsBadge />
          </div>
          <Link
            href="/settings"
            className="block rounded-sm px-2 py-1 text-ink-soft hover:bg-paper hover:text-ink"
          >
            Configuración
          </Link>
          <button
            type="button"
            onClick={() => setIsTicketModalOpen(true)}
            className="block w-full rounded-sm px-2 py-1 text-left text-accent hover:bg-paper"
          >
            Soporte
          </button>
          {user?.role === "admin" && (
            <Link
              href="/admin"
              className="block rounded-sm px-2 py-1 text-accent hover:bg-paper"
            >
              Panel admin
            </Link>
          )}
          <button
            onClick={handleLogout}
            className="mt-0.5 w-full rounded-sm px-2 py-1 text-left text-ink-soft hover:bg-paper hover:text-ink"
          >
            Cerrar sesión
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-rule bg-paper-dim px-4 py-2 sm:hidden">
          <button
            type="button"
            aria-label="Abrir menú"
            onClick={() => setSidebarOpen(true)}
            className="rounded-md border border-rule bg-paper p-1.5"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <p className="font-serif text-base italic text-ink">Anoven</p>
        </div>

        {error ? (
          <div className="flex flex-1 items-center justify-center px-6">
            <p className="font-serif text-lg italic text-accent">Error: {error}</p>
          </div>
        ) : (
          children
        )}
      </div>
    </main>
    <SupportTicketModal
      isOpen={isTicketModalOpen}
      onClose={() => setIsTicketModalOpen(false)}
    />
    </>
  );
}
