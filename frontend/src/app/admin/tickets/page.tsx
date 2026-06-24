/**
 * /admin/tickets — inbox de tickets de soporte para admins.
 *
 * Patron: /admin/requests/page.tsx
 * Auth: getToken() + Bearer. 403 → redirect al home.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { TicketStatusBadge } from "@/components/support/TicketStatusBadge";

type TicketAdminRow = {
  id: number;
  user_id: number;
  ticket_type: "bug" | "mejora" | "pregunta" | "otro";
  title: string;
  status: "open" | "in_progress" | "closed";
  admin_response: string | null;
  created_at: string;
  attachments: Array<{ id: number }>;
};

const TYPE_LABELS: Record<string, string> = {
  bug: "Bug",
  mejora: "Mejora",
  pregunta: "Pregunta",
  otro: "Otro",
};

const TYPE_CLASSES: Record<string, string> = {
  bug: "bg-accent-soft text-accent",
  mejora: "bg-paper-deep text-ink-soft",
  pregunta: "bg-paper-deep text-ink-soft",
  otro: "bg-paper-deep text-ink-soft",
};

type StatusFilter = "all" | "open" | "in_progress" | "closed";
type TypeFilter = "all" | "bug" | "mejora" | "pregunta" | "otro";

export default function AdminTicketsPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<TicketAdminRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("open");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (statusFilter !== "all") params.set("status", statusFilter);
        if (typeFilter !== "all") params.set("ticket_type", typeFilter);
        const res = await fetch(
          `${API_URL}/api/admin/tickets${params.toString() ? "?" + params.toString() : ""}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (res.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (res.status === 403) {
          router.replace("/dashboard?error=admin_only");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setTickets(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar tickets");
      } finally {
        setLoading(false);
      }
    })();
  }, [router, statusFilter, typeFilter]);

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString("es-PE", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
    { value: "open", label: "Abiertos" },
    { value: "in_progress", label: "En revisión" },
    { value: "closed", label: "Cerrados" },
    { value: "all", label: "Todos" },
  ];

  const TYPE_FILTERS: Array<{ value: TypeFilter; label: string }> = [
    { value: "all", label: "Todos" },
    { value: "bug", label: "Bug" },
    { value: "mejora", label: "Mejora" },
    { value: "pregunta", label: "Pregunta" },
    { value: "otro", label: "Otro" },
  ];

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              <span className="text-accent">❦</span> Anoven · Admin
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Tickets de soporte
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Reportes, consultas y sugerencias de los usuarios.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Link
              href="/admin"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Panel
            </Link>
          </div>
        </header>

        {error && (
          <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
            {error}
          </p>
        )}

        {/* Filtros */}
        <div className="mb-6 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-ink-muted">Estado:</span>
            <div className="flex gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setStatusFilter(f.value)}
                  className={
                    statusFilter === f.value
                      ? "rounded-full bg-ink px-3 py-1 text-xs text-paper"
                      : "rounded-full border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper-dim"
                  }
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-ink-muted">Tipo:</span>
            <div className="flex gap-1">
              {TYPE_FILTERS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setTypeFilter(f.value)}
                  className={
                    typeFilter === f.value
                      ? "rounded-full bg-ink px-3 py-1 text-xs text-paper"
                      : "rounded-full border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper-dim"
                  }
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <span className="ml-auto text-xs text-ink-muted">
            {loading ? "Cargando..." : `${tickets.length} ${tickets.length === 1 ? "ticket" : "tickets"}`}
          </span>
        </div>

        {/* Lista */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded-xl bg-paper-dim" />
            ))}
          </div>
        ) : tickets.length === 0 ? (
          <p className="rounded-xl border border-dashed border-rule bg-paper-dim p-8 text-center font-serif italic text-ink-soft">
            No hay tickets para mostrar.
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-rule bg-paper-dim">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-[11px] uppercase tracking-wide text-ink-muted">
                  <th className="px-4 py-3">ID</th>
                  <th className="px-4 py-3">Tipo</th>
                  <th className="px-4 py-3">Título</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="px-4 py-3">Fecha</th>
                  <th className="px-4 py-3 text-center">Adj.</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {tickets.map((t) => (
                  <tr
                    key={t.id}
                    className="hover:bg-paper transition-colors"
                  >
                    <td className="px-4 py-3 tabular-nums text-ink-muted">
                      #{t.id}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide ${TYPE_CLASSES[t.ticket_type] ?? "bg-paper-deep text-ink-soft"}`}
                      >
                        {TYPE_LABELS[t.ticket_type] ?? t.ticket_type}
                      </span>
                    </td>
                    <td className="max-w-xs px-4 py-3">
                      <p className="truncate font-serif italic text-ink">
                        {t.title}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <TicketStatusBadge status={t.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-ink-muted">
                      {fmtDate(t.created_at)}
                    </td>
                    <td className="px-4 py-3 text-center text-xs text-ink-muted">
                      {t.attachments?.length ?? 0}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/tickets/${t.id}`}
                        className="rounded-lg border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-accent-soft hover:text-accent"
                      >
                        Ver detalle
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
