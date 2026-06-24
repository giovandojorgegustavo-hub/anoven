/**
 * /mis-tickets/[id] — detalle de un ticket del usuario.
 *
 * "use client" + getToken() — mismo patrón confirmado en T0.2.
 * Muestra: título, descripción, tipo, estado, fecha, adjuntos (imágenes),
 * y respuesta admin si existe.
 * Copy: tuteo limeño culto.
 * D3.1: solo paleta accent. D3.2: LIGHT MODE only.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { TicketStatusBadge } from "@/components/support/TicketStatusBadge";

type TicketStatus = "open" | "in_progress" | "closed";
type TicketType = "bug" | "mejora" | "pregunta" | "otro";

interface AttachmentRead {
  id: number;
  mime_type: string;
  original_name: string;
  size_bytes: number;
}

interface TicketReadDetail {
  id: number;
  ticket_type: TicketType;
  title: string;
  description: string;
  status: TicketStatus;
  created_at: string;
  responded_at: string | null;
  admin_response: string | null;
  attachments: AttachmentRead[];
}

const TYPE_LABEL: Record<TicketType, string> = {
  bug: "Bug",
  mejora: "Mejora",
  pregunta: "Pregunta",
  otro: "Otro",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-PE", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MiTicketDetailPage() {
  const router = useRouter();
  const params = useParams();
  const ticketId = params?.id as string;

  const [ticket, setTicket] = useState<TicketReadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticketId) return;
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    fetchTicket(token, ticketId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  async function fetchTicket(token: string, id: string) {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/tickets/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }
      if (res.status === 403) {
        router.replace("/mis-tickets?error=forbidden");
        return;
      }
      if (res.status === 404) {
        setError("Ticket no encontrado.");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTicket(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el ticket");
    }
  }

  function handleRetry() {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    setTicket(null);
    fetchTicket(token, ticketId);
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-3xl">
          {/* Back link */}
          <Link
            href="/mis-tickets"
            className="mb-6 inline-flex items-center gap-1 text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
          >
            ← Volver a Mis Tickets
          </Link>

          {/* Error state */}
          {error && (
            <div className="mt-6 flex items-center justify-between rounded-lg border border-accent bg-accent-soft px-4 py-3">
              <p className="text-sm text-accent">{error}</p>
              <button
                onClick={handleRetry}
                className="ml-4 rounded-lg border border-accent px-3 py-1 text-xs text-accent hover:bg-accent hover:text-accent-ink"
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Loading skeleton */}
          {ticket === null && !error && (
            <div className="mt-6 space-y-4">
              <div className="h-8 w-2/3 animate-pulse-dot rounded bg-paper-dim" />
              <div className="h-4 w-1/3 animate-pulse-dot rounded bg-paper-dim" />
              <div className="mt-4 h-32 animate-pulse-dot rounded-xl border border-rule bg-paper-dim" />
            </div>
          )}

          {/* Ticket detail */}
          {ticket !== null && (
            <div className="mt-6 space-y-6">
              {/* Title + meta */}
              <div>
                <div className="flex flex-wrap items-start gap-3">
                  <h1 className="flex-1 font-serif text-3xl font-medium tracking-tight text-ink">
                    {ticket.title}
                  </h1>
                  <TicketStatusBadge status={ticket.status} />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
                  <span className="rounded-full bg-paper-deep px-2 py-0.5 text-[10px] uppercase tracking-wide">
                    {TYPE_LABEL[ticket.ticket_type]}
                  </span>
                  <span>Creado el {formatDate(ticket.created_at)}</span>
                </div>
              </div>

              {/* Description */}
              <div className="rounded-xl border border-rule bg-paper-dim p-5">
                <p className="text-[10px] font-medium uppercase tracking-wide text-ink-muted mb-2">
                  Descripción
                </p>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                  {ticket.description}
                </p>
              </div>

              {/* Attachments */}
              {ticket.attachments.length > 0 && (
                <div>
                  <p className="mb-3 text-[10px] font-medium uppercase tracking-wide text-ink-muted">
                    Capturas adjuntas ({ticket.attachments.length})
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {ticket.attachments.map((att) => {
                      const token = getToken();
                      const src = `${API_URL}/api/tickets/${ticket.id}/attachments/${att.id}/file`;
                      return (
                        <a
                          key={att.id}
                          href={src}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block overflow-hidden rounded-xl border border-rule hover:border-rule-strong"
                          title={att.original_name}
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={`${src}?token=${token}`}
                            alt={att.original_name}
                            className="h-40 w-40 object-cover"
                            loading="lazy"
                          />
                        </a>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Admin response */}
              {ticket.admin_response ? (
                <div className="rounded-xl border border-leaf-border bg-leaf-soft p-5">
                  <p className="text-[10px] font-medium uppercase tracking-wide text-leaf mb-2">
                    Respuesta del equipo Anoven
                  </p>
                  {ticket.responded_at && (
                    <p className="mb-3 text-xs text-ink-muted">
                      {formatDate(ticket.responded_at)}
                    </p>
                  )}
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                    {ticket.admin_response}
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-rule bg-paper-dim p-5 text-center">
                  <p className="font-serif text-sm italic text-ink-soft">
                    Todavía no hay respuesta. El equipo Anoven revisará tu ticket pronto.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
