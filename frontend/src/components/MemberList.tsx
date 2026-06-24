/**
 * MemberList — lista de miembros del proyecto con acción de expulsión (owner only).
 *
 * "use client" justificado (A2.1): estado de confirmación de expulsión + fetch.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

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

interface MemberListProps {
  projectId: number;
  members: ProjectMemberRead[];
  isOwner: boolean;
  onMemberRemoved: () => void;
}

const ROLE_LABELS: Record<string, string> = {
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

export function MemberList({ projectId, members, isOwner, onMemberRemoved }: MemberListProps) {
  const [confirmingKickFor, setConfirmingKickFor] = useState<number | null>(null);
  const [kicking, setKicking] = useState(false);
  const [kickError, setKickError] = useState<string | null>(null);

  async function handleKick(userId: number) {
    const token = getToken();
    if (!token) return;

    setKicking(true);
    setKickError(null);

    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}/members/${userId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `HTTP ${res.status}`);
      }

      setConfirmingKickFor(null);
      onMemberRemoved();
    } catch (err) {
      setKickError(err instanceof Error ? err.message : "Error al sacar al miembro");
    } finally {
      setKicking(false);
    }
  }

  if (members.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-8 text-center">
        <p className="font-serif text-lg italic text-ink-soft">No hay miembros en este proyecto.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {kickError && (
        <div className="mb-4 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
          {kickError}
        </div>
      )}

      {members.map((member) => {
        const isConfirming = confirmingKickFor === member.user_id;
        const canKick = isOwner && member.role !== "owner";

        return (
          <div
            key={member.id}
            className="flex items-start justify-between gap-3 rounded-xl border border-rule bg-paper-dim px-4 py-3"
          >
            {/* Member info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-ink truncate">
                  {member.user_nombre}
                </p>
                <span
                  className={
                    member.role === "owner"
                      ? "rounded-full bg-accent-soft px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide text-accent"
                      : "rounded-full bg-paper-deep px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide text-ink-muted"
                  }
                >
                  {ROLE_LABELS[member.role] ?? member.role}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-ink-muted">{member.user_email}</p>
              <p className="mt-0.5 text-xs text-ink-muted">
                Se unió el {formatDate(member.joined_at)}
              </p>
            </div>

            {/* Kick action — owner only, not for other owners */}
            {canKick && !isConfirming && (
              <button
                onClick={() => {
                  setConfirmingKickFor(member.user_id);
                  setKickError(null);
                }}
                className="shrink-0 rounded-lg border border-rule px-3 py-1.5 text-xs text-ink-soft hover:border-accent hover:text-accent"
              >
                Sacar del proyecto
              </button>
            )}

            {canKick && isConfirming && (
              <div className="shrink-0 flex flex-col items-end gap-1">
                <p className="text-xs text-ink-soft">¿Confirmas?</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleKick(member.user_id)}
                    disabled={kicking}
                    className="rounded-lg bg-accent px-3 py-1 text-xs font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
                  >
                    {kicking ? "..." : "Sí, sacar"}
                  </button>
                  <button
                    onClick={() => setConfirmingKickFor(null)}
                    disabled={kicking}
                    className="rounded-lg border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper disabled:opacity-60"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
