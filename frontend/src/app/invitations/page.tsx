/**
 * /invitations — lista de invitaciones pendientes del usuario.
 *
 * "use client" justificado (A2.1): fetch en cliente con token desde localStorage,
 * estado de carga + respuesta a invitaciones.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { InvitationCard } from "@/components/InvitationCard";

export interface InvitationRead {
  id: number;
  project_id: number;
  project_name: string;
  invited_user_email: string;
  invited_by_user_email: string;
  status: string;
  expires_at: string;
  created_at: string;
  responded_at: string | null;
}

export default function InvitationsPage() {
  const router = useRouter();
  const [invitations, setInvitations] = useState<InvitationRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadInvitations = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/projects/invitations/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setInvitations(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar las invitaciones");
    }
  }, [router]);

  useEffect(() => {
    loadInvitations();
  }, [loadInvitations]);

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-2xl">
          {/* Header */}
          <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Colaboración
              </p>
              <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
                Invitaciones
              </h1>
              <p className="mt-2 text-sm text-ink-soft">
                Proyectos a los que te han invitado a colaborar.
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
                onClick={loadInvitations}
                className="ml-4 rounded-lg border border-accent px-3 py-1 text-xs text-accent hover:bg-accent hover:text-accent-ink"
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Loading skeleton */}
          {invitations === null && !error && (
            <ul className="space-y-4">
              {[0, 1, 2].map((i) => (
                <li
                  key={i}
                  className="h-32 animate-pulse rounded-2xl border border-rule bg-paper-dim"
                />
              ))}
            </ul>
          )}

          {/* Empty state */}
          {invitations !== null && invitations.length === 0 && (
            <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-10 text-center">
              <p className="font-serif text-xl italic text-ink-soft">
                No tienes invitaciones pendientes.
              </p>
              <p className="mt-2 text-sm text-ink-muted">
                Cuando alguien te invite a un proyecto, aparecerá aquí.
              </p>
            </div>
          )}

          {/* Invitation list */}
          {invitations !== null && invitations.length > 0 && (
            <ul className="space-y-4">
              {invitations.map((invitation, i) => (
                <li
                  key={invitation.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  <InvitationCard
                    invitation={invitation}
                    onResponded={loadInvitations}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </AppShell>
  );
}
