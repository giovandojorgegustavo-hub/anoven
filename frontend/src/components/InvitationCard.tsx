/**
 * InvitationCard — tarjeta de invitación con botones Aceptar / Rechazar.
 *
 * "use client" justificado (A2.1): estado de acción pendiente + fetch.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 * Maneja 410 (expirada) mostrando mensaje + auto-refresh.
 */

"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

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

interface InvitationCardProps {
  invitation: InvitationRead;
  onResponded: () => void;
}

function daysUntil(isoDate: string): number {
  const diff = new Date(isoDate).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

function formatExpiry(isoDate: string): string {
  const days = daysUntil(isoDate);
  if (days === 0) return "Expira hoy";
  if (days === 1) return "Expira mañana";
  return `Expira en ${days} días`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-PE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function InvitationCard({ invitation, onResponded }: InvitationCardProps) {
  const [acting, setActing] = useState<"accept" | "reject" | null>(null);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const days = daysUntil(invitation.expires_at);
  const isUrgent = days <= 1;

  async function handleAction(action: "accept" | "reject") {
    const token = getToken();
    if (!token) return;

    setActing(action);
    setError(null);

    try {
      const res = await fetch(
        `${API_URL}/api/projects/invitations/${invitation.id}/${action}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );

      if (res.status === 410) {
        setExpired(true);
        setTimeout(() => onResponded(), 2000);
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `HTTP ${res.status}`);
      }

      onResponded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al procesar la invitación");
      setActing(null);
    }
  }

  return (
    <div className="rounded-2xl border border-rule bg-paper-dim p-5">
      {/* Expired state */}
      {expired && (
        <div className="rounded-xl border border-accent bg-accent-soft px-4 py-3 text-center">
          <p className="text-sm font-medium text-accent">Esta invitación ya expiró.</p>
          <p className="mt-1 text-xs text-accent/80">
            Pide al propietario del proyecto que te invite de nuevo.
          </p>
        </div>
      )}

      {!expired && (
        <>
          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <h3 className="font-serif text-xl font-medium tracking-tight text-ink">
                {invitation.project_name}
              </h3>
              <p className="mt-1 text-xs text-ink-muted">
                Invitado por{" "}
                <span className="font-medium text-ink-soft">
                  {invitation.invited_by_user_email}
                </span>
              </p>
              <p className="mt-0.5 text-xs text-ink-muted">
                Recibida el {formatDate(invitation.created_at)}
              </p>
            </div>

            {/* Expiry badge */}
            <span
              className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-medium ${
                isUrgent
                  ? "bg-accent-soft text-accent"
                  : "bg-paper-deep text-ink-muted"
              }`}
            >
              {formatExpiry(invitation.expires_at)}
            </span>
          </div>

          {/* Error */}
          {error && (
            <p className="mt-3 rounded-lg border border-accent bg-accent-soft px-3 py-2 text-xs text-accent">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={() => handleAction("accept")}
              disabled={acting !== null}
              className="rounded-xl bg-accent px-5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
            >
              {acting === "accept" ? "Aceptando..." : "Aceptar"}
            </button>
            <button
              onClick={() => handleAction("reject")}
              disabled={acting !== null}
              className="rounded-xl border border-rule px-5 py-2 text-sm text-ink-soft hover:border-rule-strong hover:text-ink disabled:opacity-60"
            >
              {acting === "reject" ? "Rechazando..." : "Rechazar"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
