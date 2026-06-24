/**
 * /projects/[id]/conversations — lista de conversaciones del proyecto compartido.
 *
 * "use client" justificado (A2.1): fetch en cliente con token desde localStorage.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

interface ConversationRow {
  id: number;
  mentor_id: number;
  title: string | null;
  updated_at: string;
  message_count: number;
  mentor: { id: number; nombre: string; canon: string };
}

function relativeTime(iso: string): string {
  const diffSec = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diffSec < 60) return "ahora";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h`;
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d`;
  return new Date(iso).toLocaleDateString("es-PE", { day: "numeric", month: "short" });
}

export default function ProjectConversationsPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = Number(params.id);

  const [conversations, setConversations] = useState<ConversationRow[] | null>(null);
  const [projectName, setProjectName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    (async () => {
      try {
        const [projectsRes, convsRes] = await Promise.all([
          fetch(`${API_URL}/api/projects/mine`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/api/conversations?project_id=${projectId}`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);

        if (projectsRes.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }

        if (projectsRes.ok) {
          const projects = await projectsRes.json();
          const found = projects.find((p: { id: number; name: string }) => p.id === projectId);
          if (found) setProjectName(found.name);
        }

        if (!convsRes.ok) throw new Error(`HTTP ${convsRes.status}`);
        setConversations(await convsRes.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar las conversaciones");
      }
    })();
  }, [projectId, router]);

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-4xl">
          {/* Nav */}
          <div className="mb-6 flex items-center gap-2 text-sm text-ink-muted">
            <Link href="/projects" className="hover:text-accent">
              Proyectos
            </Link>
            <span>›</span>
            <Link href={`/projects/${projectId}`} className="hover:text-accent">
              {projectName ?? `Proyecto #${projectId}`}
            </Link>
            <span>›</span>
            <span className="text-ink">Conversaciones</span>
          </div>

          {/* Header */}
          <header className="mb-10 border-b border-rule pb-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              {projectName ?? `Proyecto #${projectId}`}
            </p>
            <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
              Conversaciones del proyecto
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Todas las conversaciones realizadas en el contexto de este proyecto.
            </p>
          </header>

          {/* Error state */}
          {error && (
            <div className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-3">
              <p className="text-sm text-accent">{error}</p>
            </div>
          )}

          {/* Loading skeleton */}
          {conversations === null && !error && (
            <ul className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <li
                  key={i}
                  className="h-20 animate-pulse rounded-xl border border-rule bg-paper-dim"
                />
              ))}
            </ul>
          )}

          {/* Empty state */}
          {conversations !== null && conversations.length === 0 && (
            <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-10 text-center">
              <p className="font-serif text-xl italic text-ink-soft">
                Este proyecto aún no tiene conversaciones.
              </p>
              <p className="mt-2 text-sm text-ink-muted">
                Empieza una desde el ProjectSwitcher en el panel lateral.
              </p>
            </div>
          )}

          {/* Conversation list */}
          {conversations !== null && conversations.length > 0 && (
            <ul className="space-y-3">
              {conversations.map((conv, i) => (
                <li
                  key={conv.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <Link
                    href={`/chat/${conv.id}`}
                    className="block rounded-xl border border-rule bg-paper-dim p-5 transition-colors hover:border-rule-strong hover:bg-paper"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] font-medium uppercase tracking-wide text-ink-muted">
                          {conv.mentor.nombre}
                        </p>
                        <h2 className="mt-1 font-serif text-lg font-medium tracking-tight text-ink truncate">
                          {conv.title ?? `Conversación #${conv.id}`}
                        </h2>
                        <p className="mt-1 text-xs text-ink-muted">
                          {conv.message_count}{" "}
                          {conv.message_count === 1 ? "mensaje" : "mensajes"}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-ink-muted">
                        {relativeTime(conv.updated_at)}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </AppShell>
  );
}
