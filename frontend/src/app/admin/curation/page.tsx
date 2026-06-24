/**
 * Página /admin/curation — Jorge (role='admin') revisa mentores
 * pending_review y los aprueba a global o los rechaza.
 *
 * Incluye los user-mentors viejos importados via migrate_5_5.py.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";

type PendingMentor = {
  id: number;
  slug: string;
  nombre: string;
  canon: string;
  filosofia: string;
  visibility: string;
  status: string;
  created_at: string;
};

export default function AdminCurationPage() {
  const router = useRouter();
  const [pending, setPending] = useState<PendingMentor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/mentors/pending`, {
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
        setPending(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error cargando");
      }
    })();
  }, [router]);

  async function handleAction(id: number, action: "approve" | "reject") {
    if (busyId !== null) return;
    const token = getToken();
    if (!token) return;
    setBusyId(id);
    try {
      const res = await fetch(`${API_URL}/api/admin/mentors/${id}/${action}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPending((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error procesando");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-4xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              Anoven · Admin
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Cola de curación
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Mentores creados por users o importados del sistema viejo,
              esperando aprobación para entrar al catálogo público.
            </p>
          </div>
          <Link
            href="/dashboard"
            className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
          >
            ← Dashboard
          </Link>
        </header>

        {error && (
          <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
            {error}
          </p>
        )}

        {pending.length === 0 && (
          <p className="rounded-xl border border-rule bg-paper-dim p-6 text-center font-serif italic text-ink-soft">
            No hay mentores pendientes de revisión.
          </p>
        )}

        <ul className="space-y-4">
          {pending.map((m) => (
            <li
              key={m.id}
              className="rounded-xl border border-rule bg-paper-dim p-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                    {m.slug}
                  </p>
                  <h2 className="mt-1 font-serif text-2xl italic text-ink">
                    {m.nombre}
                  </h2>
                  <p className="mt-2 text-xs uppercase tracking-wide text-ink-muted">
                    {m.canon}
                  </p>
                  <p className="mt-3 font-serif text-base italic leading-relaxed text-ink-soft">
                    {m.filosofia}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col gap-2">
                  <button
                    onClick={() => handleAction(m.id, "approve")}
                    disabled={busyId !== null}
                    className="rounded-lg bg-leaf px-3 py-1.5 text-xs font-medium text-paper hover:opacity-90 disabled:opacity-50"
                  >
                    {busyId === m.id ? "..." : "Aprobar → global"}
                  </button>
                  <button
                    onClick={() => handleAction(m.id, "reject")}
                    disabled={busyId !== null}
                    className="rounded-lg border border-rule px-3 py-1.5 text-xs text-ink-soft hover:bg-accent-soft hover:text-accent disabled:opacity-50"
                  >
                    Rechazar
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
