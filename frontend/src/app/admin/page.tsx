/**
 * /admin — home del panel admin. KPIs + top users + top mentors + spend
 * por día + links a sub-secciones (curación, users).
 *
 * Solo accesible para role='admin'. Si no sos admin → redirect.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import AdminTicketsBadge from "@/components/AdminTicketsBadge";

type AdminOverview = {
  kpis: {
    users: number;
    conversations: number;
    messages_total: number;
    messages_7d: number;
    usd_total: number;
    usd_7d: number;
    pending_mentors: number;
  };
  top_users: Array<{
    id: number;
    email: string;
    nombre: string;
    usd: number;
    turns: number;
  }>;
  top_mentors: Array<{
    id: number;
    slug: string;
    nombre: string;
    usd: number;
    turns: number;
  }>;
  by_day: Array<{ day: string; usd: number; turns: number }>;
};

function fmtUSD(v: number): string {
  if (v < 0.01 && v > 0) return "<$0.01";
  return `$${v.toFixed(2)}`;
}

function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString("es-AR", {
    day: "numeric",
    month: "short",
  });
}

export default function AdminHomePage() {
  const router = useRouter();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/overview`, {
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
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setData(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  if (error) {
    return (
      <main className="flex flex-1 items-center justify-center px-6">
        <p className="font-serif text-lg italic text-accent">Error: {error}</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="font-serif text-lg italic text-ink-soft">Cargando admin...</p>
      </main>
    );
  }

  const maxByDay = Math.max(0.01, ...data.by_day.map((d) => d.usd));

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              Anoven · Admin
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Panel
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Solo para vos. Métricas en vivo del sistema.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Link
              href="/dashboard"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Dashboard
            </Link>
            <Link
              href="/admin/requests"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Pedidos de mentores →
            </Link>
            <Link
              href="/admin/curation"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Cola de curación →
            </Link>
            <Link
              href="/admin/recurate"
              className="text-xs font-medium text-accent underline-offset-2 hover:underline"
            >
              Recuración Promptifex SDD →
            </Link>
            <Link
              href="/admin/skills"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Skills →
            </Link>
            <Link
              href="/admin/tickets"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Tickets →
            </Link>
            <Link
              href="/admin/users"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Users →
            </Link>
          </div>
        </header>

        {/* KPIs */}
        <section className="mb-10 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <KpiCard label="Users" value={data.kpis.users} />
          <KpiCard label="Conversaciones" value={data.kpis.conversations} />
          <KpiCard
            label="Mensajes (7d)"
            value={data.kpis.messages_7d}
            sub={`${data.kpis.messages_total} totales`}
          />
          <KpiCard
            label="Costo (7d)"
            value={fmtUSD(data.kpis.usd_7d)}
            sub={`${fmtUSD(data.kpis.usd_total)} total`}
            accent
          />
        </section>

        {data.kpis.pending_mentors > 0 && (
          <div className="mb-10 rounded-xl border border-accent bg-accent-soft px-5 py-3 text-sm text-ink">
            <Link href="/admin/curation" className="font-medium hover:underline">
              Hay {data.kpis.pending_mentors} mentor
              {data.kpis.pending_mentors === 1 ? "" : "es"} esperando curación →
            </Link>
          </div>
        )}

        {/* Badge de tickets pendientes — polling cada 30s */}
        <div className="mb-6">
          <AdminTicketsBadge />
        </div>

        {/* Spend por día */}
        <section className="mb-10 rounded-xl border border-rule bg-paper-dim p-6">
          <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
            Costo últimos 14 días
          </p>
          <h2 className="mt-1 font-serif text-2xl italic text-ink">
            Spend diario
          </h2>
          {data.by_day.length === 0 ? (
            <p className="mt-4 font-serif italic text-ink-soft">
              Todavía no hay datos de costo.
            </p>
          ) : (
            <ul className="mt-4 space-y-1.5">
              {data.by_day.map((d) => (
                <li key={d.day} className="flex items-center gap-3">
                  <span className="w-14 shrink-0 text-xs text-ink-muted">
                    {fmtDay(d.day)}
                  </span>
                  <div className="flex-1">
                    <div className="h-2 overflow-hidden rounded-full bg-paper">
                      <div
                        className="h-full rounded-full bg-accent"
                        style={{ width: `${(d.usd / maxByDay) * 100}%` }}
                      />
                    </div>
                  </div>
                  <span className="w-20 shrink-0 text-right text-sm tabular-nums text-ink">
                    {fmtUSD(d.usd)}
                  </span>
                  <span className="w-10 shrink-0 text-right text-[11px] text-ink-muted">
                    {d.turns}t
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Top users + Top mentors */}
        <section className="mb-10 grid gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-rule bg-paper-dim p-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Top users por costo
            </p>
            <h2 className="mt-1 font-serif text-2xl italic text-ink">Users</h2>
            {data.top_users.length === 0 ? (
              <p className="mt-4 font-serif italic text-ink-soft">
                Sin datos todavía.
              </p>
            ) : (
              <ul className="mt-4 space-y-2">
                {data.top_users.map((u) => (
                  <li
                    key={u.id}
                    className="flex items-center justify-between gap-3 border-b border-rule pb-2 last:border-b-0 last:pb-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-serif text-base italic text-ink">
                        {u.nombre || u.email}
                      </p>
                      <p className="truncate text-[11px] text-ink-muted">
                        {u.email}
                      </p>
                    </div>
                    <div className="text-right text-sm">
                      <p className="tabular-nums font-medium text-ink">
                        {fmtUSD(u.usd)}
                      </p>
                      <p className="text-[11px] text-ink-muted">{u.turns}t</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-rule bg-paper-dim p-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Top mentors por costo
            </p>
            <h2 className="mt-1 font-serif text-2xl italic text-ink">Mentors</h2>
            {data.top_mentors.length === 0 ? (
              <p className="mt-4 font-serif italic text-ink-soft">
                Sin datos todavía.
              </p>
            ) : (
              <ul className="mt-4 space-y-2">
                {data.top_mentors.map((m) => (
                  <li
                    key={m.id}
                    className="flex items-center justify-between gap-3 border-b border-rule pb-2 last:border-b-0 last:pb-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-serif text-base italic text-ink">
                        {m.nombre}
                      </p>
                      <p className="truncate text-[11px] text-ink-muted">
                        {m.slug}
                      </p>
                    </div>
                    <div className="text-right text-sm">
                      <p className="tabular-nums font-medium text-ink">
                        {fmtUSD(m.usd)}
                      </p>
                      <p className="text-[11px] text-ink-muted">{m.turns}t</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function KpiCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: number | string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={
        accent
          ? "rounded-xl border border-accent-soft bg-accent-soft p-5"
          : "rounded-xl border border-rule bg-paper-dim p-5"
      }
    >
      <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </p>
      <p className={accent ? "mt-2 font-serif text-3xl font-medium text-accent" : "mt-2 font-serif text-3xl font-medium text-ink"}>
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-ink-muted">{sub}</p>}
    </div>
  );
}
