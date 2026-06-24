/**
 * TicketStatusBadge — badge presentacional de estado de ticket.
 * Presentational only — no "use client" needed.
 * D3.1: solo colores de la paleta accent (terracotta) + amber + stone.
 * D3.2: LIGHT MODE only — sin clases dark:.
 */

type TicketStatus = "open" | "in_progress" | "closed";

const LABEL: Record<TicketStatus, string> = {
  open: "Abierto",
  in_progress: "En revisión",
  closed: "Cerrado",
};

const CLASS: Record<TicketStatus, string> = {
  open: "bg-accent-soft text-accent",
  in_progress: "bg-amber-50 text-amber-800",
  closed: "bg-paper-deep text-ink-muted",
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${CLASS[status]}`}
    >
      {LABEL[status]}
    </span>
  );
}
