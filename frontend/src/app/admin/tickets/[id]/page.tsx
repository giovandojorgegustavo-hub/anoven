/**
 * /admin/tickets/[id] — detalle de ticket de soporte + formulario de respuesta.
 *
 * Auth: getToken() + Bearer.
 * PATCH /api/admin/tickets/{id} para responder/cambiar estado.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { TicketStatusBadge } from "@/components/support/TicketStatusBadge";

type Attachment = {
  id: number;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  file_url: string;
};

type TicketDetail = {
  id: number;
  user_id: number;
  ticket_type: string;
  title: string;
  description: string;
  status: "open" | "in_progress" | "closed";
  admin_response: string | null;
  admin_user_id: number | null;
  created_at: string;
  updated_at: string;
  responded_at: string | null;
  closed_at: string | null;
  conversation_id: number | null;
  mentor_id: number | null;
  attachments: Attachment[];
};

const TYPE_LABELS: Record<string, string> = {
  bug: "Bug",
  mejora: "Mejora",
  pregunta: "Pregunta",
  otro: "Otro",
};

// Allowed transitions shown in the UI for guidance
const TRANSITION_HINTS: Record<string, string[]> = {
  open: ["in_progress", "closed"],
  in_progress: ["closed", "open"],
  closed: ["open", "in_progress"],
};

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "open", label: "Abierto" },
  { value: "in_progress", label: "En revisión" },
  { value: "closed", label: "Cerrado" },
];

export default function AdminTicketDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const ticketId = params?.id;

  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Response form state
  const [responseText, setResponseText] = useState("");
  const [newStatus, setNewStatus] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!ticketId) return;
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_URL}/api/admin/tickets/${ticketId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (res.status === 403) {
          router.replace("/dashboard?error=admin_only");
          return;
        }
        if (res.status === 404) {
          setError("Ticket no encontrado.");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: TicketDetail = await res.json();
        setTicket(data);
        // Pre-fill form if already responded
        if (data.admin_response) setResponseText(data.admin_response);
        setNewStatus(data.status);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar el ticket");
      } finally {
        setLoading(false);
      }
    })();
  }, [router, ticketId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticket || submitting) return;
    const token = getToken();
    if (!token) return;

    setSubmitting(true);
    setSubmitError(null);

    try {
      const payload: { admin_response: string; new_status?: string } = {
        admin_response: responseText.trim(),
      };
      if (newStatus && newStatus !== ticket.status) {
        payload.new_status = newStatus;
      }

      const res = await fetch(`${API_URL}/api/admin/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (res.status === 422) {
        const body = await res.json();
        const detail = body?.detail ?? "Transición no permitida.";
        const allowed = TRANSITION_HINTS[ticket.status] ?? [];
        setSubmitError(
          `${detail} Estados válidos desde "${ticket.status}": ${allowed.map((s) => `"${s}"`).join(", ")}.`,
        );
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }

      const updated: TicketDetail = await res.json();
      setTicket(updated);
      setResponseText(updated.admin_response ?? "");
      setNewStatus(updated.status);
      setToast("Respuesta guardada.");
      setTimeout(() => setToast(null), 3500);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Error al guardar");
    } finally {
      setSubmitting(false);
    }
  }

  function fmtDate(iso: string | null | undefined): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("es-PE", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  if (loading) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="font-serif text-lg italic text-ink-soft">Cargando ticket...</p>
      </main>
    );
  }

  if (error || !ticket) {
    return (
      <main className="flex flex-1 items-center justify-center px-6">
        <div className="text-center">
          <p className="font-serif text-lg italic text-accent">{error ?? "Ticket no encontrado."}</p>
          <Link href="/admin/tickets" className="mt-4 block text-sm text-ink-soft hover:text-accent hover:underline">
            ← Volver a tickets
          </Link>
        </div>
      </main>
    );
  }

  const token = getToken();
  const allowedTransitions = TRANSITION_HINTS[ticket.status] ?? [];

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-3xl">
        {/* Toast */}
        {toast && (
          <div className="mb-6 rounded-xl border border-rule bg-paper-dim px-5 py-3 text-sm text-ink">
            {toast}
          </div>
        )}

        <header className="mb-8 flex items-start justify-between gap-4 border-b border-rule pb-6">
          <div className="flex-1">
            <Link
              href="/admin/tickets"
              className="text-xs text-ink-soft hover:text-accent hover:underline"
            >
              ← Tickets de soporte
            </Link>
            <h1 className="mt-3 font-serif text-3xl font-medium tracking-tight text-ink">
              {ticket.title}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <TicketStatusBadge status={ticket.status} />
              <span className="rounded-full bg-paper-deep px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-soft">
                {TYPE_LABELS[ticket.ticket_type] ?? ticket.ticket_type}
              </span>
              <span className="text-xs text-ink-muted">#{ticket.id}</span>
            </div>
          </div>
        </header>

        {/* Meta */}
        <section className="mb-6 grid grid-cols-2 gap-3 text-xs text-ink-muted sm:grid-cols-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide">Usuario ID</p>
            <p className="mt-1 tabular-nums text-ink">{ticket.user_id}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide">Creado</p>
            <p className="mt-1 text-ink">{fmtDate(ticket.created_at)}</p>
          </div>
          {ticket.responded_at && (
            <div>
              <p className="text-[11px] uppercase tracking-wide">Respondido</p>
              <p className="mt-1 text-ink">{fmtDate(ticket.responded_at)}</p>
            </div>
          )}
          {ticket.closed_at && (
            <div>
              <p className="text-[11px] uppercase tracking-wide">Cerrado</p>
              <p className="mt-1 text-ink">{fmtDate(ticket.closed_at)}</p>
            </div>
          )}
        </section>

        {/* Descripción */}
        <section className="mb-6 rounded-xl border border-rule bg-paper-dim p-5">
          <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">Descripción</p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">
            {ticket.description}
          </p>
        </section>

        {/* Adjuntos */}
        {ticket.attachments.length > 0 && (
          <section className="mb-6">
            <p className="mb-3 text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Adjuntos ({ticket.attachments.length})
            </p>
            <div className="flex flex-wrap gap-3">
              {ticket.attachments.map((att) => (
                <div key={att.id} className="overflow-hidden rounded-xl border border-rule bg-paper-dim">
                  <img
                    src={`${API_URL}${att.file_url}?token=${token}`}
                    alt={att.original_name}
                    className="h-48 w-auto max-w-xs object-contain"
                    loading="lazy"
                  />
                  <p className="truncate px-3 py-1.5 text-[11px] text-ink-muted">
                    {att.original_name}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Respuesta admin existente */}
        {ticket.admin_response && (
          <section className="mb-6 rounded-xl border border-rule bg-paper-dim p-5">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Respuesta del equipo Anoven
            </p>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">
              {ticket.admin_response}
            </p>
            {ticket.responded_at && (
              <p className="mt-2 text-[11px] text-ink-muted">
                Enviada el {fmtDate(ticket.responded_at)}
              </p>
            )}
          </section>
        )}

        {/* Formulario de respuesta */}
        <section className="rounded-xl border border-rule bg-paper-dim p-5">
          <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
            {ticket.admin_response ? "Actualizar respuesta" : "Responder"}
          </p>

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div>
              <label
                htmlFor="admin-response"
                className="block text-xs text-ink-soft"
              >
                Respuesta para el usuario
              </label>
              <textarea
                id="admin-response"
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                rows={5}
                placeholder="Escribe la respuesta para el usuario..."
                className="mt-1 w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder-ink-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                required
                minLength={1}
              />
            </div>

            <div>
              <label
                htmlFor="new-status"
                className="block text-xs text-ink-soft"
              >
                Nuevo estado{" "}
                <span className="text-ink-muted">
                  (desde &quot;{ticket.status}&quot; → válidos: {allowedTransitions.join(", ") || "ninguno"})
                </span>
              </label>
              <select
                id="new-status"
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
                className="mt-1 w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option
                    key={opt.value}
                    value={opt.value}
                    disabled={opt.value !== ticket.status && !allowedTransitions.includes(opt.value)}
                  >
                    {opt.label}
                    {opt.value === ticket.status ? " (actual)" : ""}
                  </option>
                ))}
              </select>
            </div>

            {submitError && (
              <p className="rounded-lg border border-accent bg-accent-soft px-3 py-2 text-sm text-accent">
                {submitError}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || responseText.trim().length === 0}
              className="rounded-lg bg-ink px-5 py-2 text-sm text-paper hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Guardando..." : "Guardar respuesta"}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
