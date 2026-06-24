/**
 * /mis-tickets — lista de tickets del usuario autenticado.
 *
 * "use client" + getToken() pattern — misma convención que TODOS
 * los pages de la app (T0.2 confirmado: NO Server Component con cookies).
 * Copy: tuteo limeño culto (NO voseo).
 * D3.1: solo paleta accent. D3.2: LIGHT MODE only.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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

interface TicketRead {
  id: number;
  ticket_type: TicketType;
  title: string;
  description: string;
  status: TicketStatus;
  created_at: string;
  admin_response: string | null;
  attachments: AttachmentRead[];
}

const TYPE_LABEL: Record<TicketType, string> = {
  bug: "Bug",
  mejora: "Mejora",
  pregunta: "Pregunta",
  otro: "Otro",
};

const STATUS_OPTIONS: { value: TicketStatus | "all"; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "open", label: "Abierto" },
  { value: "in_progress", label: "En revisión" },
  { value: "closed", label: "Cerrado" },
];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-PE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function MisTicketsPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<TicketRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<TicketStatus | "all">("all");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    fetchTickets(token, filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function fetchTickets(token: string, statusFilter: TicketStatus | "all") {
    setError(null);
    try {
      const url =
        statusFilter === "all"
          ? `${API_URL}/api/tickets/mine`
          : `${API_URL}/api/tickets/mine?status=${statusFilter}`;

      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTickets(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar los tickets");
    }
  }

  function handleRetry() {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    setTickets(null);
    fetchTickets(token, filter);
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-4xl">
          {/* Header */}
          <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Soporte
              </p>
              <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
                Mis tickets
              </h1>
              <p className="mt-2 text-sm text-ink-soft">
                Acá puedes ver el historial de tus reportes y las respuestas del equipo Anoven.
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
                onClick={handleRetry}
                className="ml-4 rounded-lg border border-accent px-3 py-1 text-xs text-accent hover:bg-accent hover:text-accent-ink"
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Filter */}
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  setTickets(null);
                  setFilter(opt.value);
                }}
                className={
                  filter === opt.value
                    ? "rounded-full bg-ink px-3 py-1 text-xs text-paper"
                    : "rounded-full border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper-dim"
                }
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Loading state */}
          {tickets === null && !error && (
            <ul className="space-y-3">
              {[0, 1, 2].map((i) => (
                <li
                  key={i}
                  className="h-24 animate-pulse-dot rounded-xl border border-rule bg-paper-dim"
                />
              ))}
            </ul>
          )}

          {/* Empty state */}
          {tickets !== null && tickets.length === 0 && (
            <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-10 text-center">
              <p className="font-serif text-xl italic text-ink-soft">
                Todavía no has reportado nada. Cuando lo hagas, aparecerá aquí.
              </p>
              <p className="mt-2 text-sm text-ink-muted">
                Puedes crear uno desde el botón Soporte en el encabezado.
              </p>
            </div>
          )}

          {/* Ticket list */}
          {tickets !== null && tickets.length > 0 && (
            <ul className="space-y-3">
              {tickets.map((ticket, i) => (
                <li
                  key={ticket.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <Link
                    href={`/mis-tickets/${ticket.id}`}
                    className="block rounded-xl border border-rule bg-paper-dim p-5 transition-colors hover:border-rule-strong hover:bg-paper"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="font-serif text-lg font-medium tracking-tight text-ink truncate">
                            {ticket.title}
                          </h2>
                          <span className="rounded-full bg-paper-deep px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-muted">
                            {TYPE_LABEL[ticket.ticket_type]}
                          </span>
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
                          <span>{formatDate(ticket.created_at)}</span>
                          {ticket.attachments.length > 0 && (
                            <span>
                              {ticket.attachments.length}{" "}
                              {ticket.attachments.length === 1 ? "imagen" : "imágenes"}
                            </span>
                          )}
                          {ticket.admin_response && (
                            <span className="text-leaf font-medium">Respondido</span>
                          )}
                        </div>
                      </div>
                      <TicketStatusBadge status={ticket.status} />
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
