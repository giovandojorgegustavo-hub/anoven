/**
 * InviteMemberModal — modal para invitar a un usuario al proyecto.
 *
 * "use client" justificado (A2.1): estado de formulario + fetch async + submit.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 * Errores mapeados a mensajes legibles (spec §9).
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

interface InviteMemberModalProps {
  projectId: number;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

function mapInviteError(status: number, detail: string): string {
  if (status === 404) return "No encontramos a ese email en Anoven. Solo puedes invitar a usuarios registrados.";
  if (status === 409) {
    if (detail.includes("miembro") || detail.includes("member")) {
      return "Esa persona ya es miembro de este proyecto.";
    }
    if (detail.includes("invit")) {
      return "Ya hay una invitación pendiente para ese email.";
    }
    if (detail.includes("máximo") || detail.includes("20")) {
      return "El proyecto ya tiene el máximo de 20 miembros.";
    }
    if (detail.includes("General") || detail.includes("default")) {
      return "El proyecto General no se puede compartir.";
    }
  }
  return detail || "Ocurrió un error al enviar la invitación.";
}

export function InviteMemberModal({
  projectId,
  isOpen,
  onClose,
  onSuccess,
}: InviteMemberModalProps) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset on open
  useEffect(() => {
    if (isOpen) {
      setEmail("");
      setError(null);
      setSuccess(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) return;

    const token = getToken();
    if (!token) return;

    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}/members/invite`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ invited_user_email: trimmedEmail }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data.detail ?? "";
        throw { status: res.status, detail };
      }

      setSuccess(true);
      setTimeout(() => {
        onSuccess();
      }, 1200);
    } catch (err: unknown) {
      if (err && typeof err === "object" && "status" in err) {
        const e = err as { status: number; detail: string };
        setError(mapInviteError(e.status, e.detail));
      } else {
        setError("Ocurrió un error inesperado. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-rule bg-paper shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-rule px-6 py-4">
          <h2 className="font-serif text-xl font-medium tracking-tight text-ink">
            Invitar miembro
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Cerrar"
            className="rounded-md p-1 text-ink-muted hover:text-ink disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {/* Success state */}
        {success ? (
          <div className="px-6 py-8 text-center">
            <p className="font-serif text-2xl italic text-ink">Invitación enviada.</p>
            <p className="mt-2 text-sm text-ink-soft">
              La persona recibirá la invitación en la sección{" "}
              <span className="font-medium text-ink">Invitaciones</span> de su cuenta.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
            <p className="text-sm text-ink-soft">
              Ingresa el email de la persona que quieres invitar. Debe tener una cuenta en
              Anoven.
            </p>

            {/* Error */}
            {error && (
              <p className="rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
                {error}
              </p>
            )}

            {/* Email input */}
            <div>
              <label
                htmlFor="invite-email"
                className="block text-xs font-medium uppercase tracking-wide text-ink-muted mb-1"
              >
                Email
              </label>
              <input
                ref={inputRef}
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nombre@ejemplo.com"
                required
                disabled={submitting}
                className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none disabled:opacity-60"
              />
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="rounded-xl border border-rule px-4 py-2 text-sm text-ink-soft hover:bg-paper-dim disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting || !email.trim()}
                className="rounded-xl bg-accent px-5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
              >
                {submitting ? "Enviando..." : "Invitar"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
