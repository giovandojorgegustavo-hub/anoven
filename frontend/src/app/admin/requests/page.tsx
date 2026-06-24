/**
 * /admin/requests — pedidos de mentores que NO existen todavía.
 *
 * Source = 'interview' significa que el Evaluador detectó gaps en los
 * dolores del user que no cubre el catálogo. Source = 'manual' (futuro)
 * sería un pedido explícito.
 *
 * Diferente de /admin/curation, que muestra mentores YA CREADOS por users.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";

type Request = {
  id: number;
  user_id: number;
  user_email: string;
  user_nombre: string;
  source: "interview" | "manual";
  proposed_name: string;
  proposed_canon: string | null;
  why: string;
  status: "pending" | "created" | "rejected";
  created_at: string;
};

export default function AdminRequestsPage() {
  const router = useRouter();
  const [requests, setRequests] = useState<Request[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [filter, setFilter] = useState<"pending" | "all">("pending");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/mentor-requests`, {
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
        setRequests(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  async function reject(id: number) {
    if (busyId !== null) return;
    const token = getToken();
    if (!token) return;
    setBusyId(id);
    try {
      const res = await fetch(`${API_URL}/api/admin/mentor-requests/${id}/reject`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRequests((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: "rejected" } : r)),
      );
    } finally {
      setBusyId(null);
    }
  }

  const visible = filter === "pending"
    ? requests.filter((r) => r.status === "pending")
    : requests;

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-4xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              <span className="text-accent">❦</span> Anoven · Admin
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Pedidos de mentores
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Mentores que los users PIDIERON crear (Evaluador detectó gaps)
              o que pidieron manualmente. Distinto a "cola de curación" que es
              para mentores ya creados.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Link
              href="/admin"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Panel
            </Link>
            <Link
              href="/admin/curation"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Cola de curación →
            </Link>
          </div>
        </header>

        {error && (
          <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
            {error}
          </p>
        )}

        <div className="mb-4 flex items-center gap-2 text-sm">
          <button
            onClick={() => setFilter("pending")}
            className={
              filter === "pending"
                ? "rounded-full bg-ink px-3 py-1 text-xs text-paper"
                : "rounded-full border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper-dim"
            }
          >
            Pendientes
          </button>
          <button
            onClick={() => setFilter("all")}
            className={
              filter === "all"
                ? "rounded-full bg-ink px-3 py-1 text-xs text-paper"
                : "rounded-full border border-rule px-3 py-1 text-xs text-ink-soft hover:bg-paper-dim"
            }
          >
            Todos
          </button>
          <span className="ml-auto text-xs text-ink-muted">
            {visible.length} {visible.length === 1 ? "pedido" : "pedidos"}
          </span>
        </div>

        {visible.length === 0 ? (
          <p className="rounded-xl border border-dashed border-rule bg-paper-dim p-6 text-center font-serif italic text-ink-soft">
            {filter === "pending"
              ? "No hay pedidos pendientes. Cuando los users hagan la entrevista, los gaps detectados van a aparecer acá."
              : "No hay pedidos todavía."}
          </p>
        ) : (
          <ul className="space-y-4">
            {visible.map((r) => (
              <li
                key={r.id}
                className="animate-fade-in-up rounded-xl border border-rule bg-paper-dim p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-serif text-xl italic text-ink">
                        {r.proposed_name}
                      </h2>
                      <span
                        className={
                          r.source === "interview"
                            ? "rounded-full bg-accent-soft px-2 py-0.5 text-[10px] uppercase tracking-wide text-accent"
                            : "rounded-full bg-paper-deep px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-soft"
                        }
                      >
                        {r.source === "interview" ? "Entrevista" : "Manual"}
                      </span>
                      {r.status !== "pending" && (
                        <span className="rounded-full bg-paper-deep px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-muted">
                          {r.status}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-ink-muted">
                      Para {r.user_nombre || r.user_email}
                    </p>
                    {r.proposed_canon && (
                      <p className="mt-2 text-[11px] uppercase tracking-wide text-ink-muted">
                        Canon sugerido: {r.proposed_canon}
                      </p>
                    )}
                    <p className="mt-3 font-serif text-sm italic leading-relaxed text-ink-soft">
                      {r.why}
                    </p>
                  </div>
                  {r.status === "pending" && (
                    <div className="flex shrink-0 flex-col gap-2">
                      <button
                        onClick={() => reject(r.id)}
                        disabled={busyId !== null}
                        className="rounded-lg border border-rule px-3 py-1.5 text-xs text-ink-soft hover:bg-accent-soft hover:text-accent disabled:opacity-50"
                      >
                        Rechazar
                      </button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
