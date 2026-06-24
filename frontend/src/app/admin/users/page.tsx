/**
 * /admin/users — listado completo de users con sus métricas.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";

type AdminUser = {
  id: number;
  email: string;
  nombre: string;
  role: string;
  onboarding_state: string;
  onboarding_attempts: number;
  research_opt_in: boolean;
  conv_count: number;
  usd_spent: number;
  created_at: string;
};

function fmtUSD(v: number): string {
  if (v < 0.01 && v > 0) return "<$0.01";
  return `$${v.toFixed(2)}`;
}

export default function AdminUsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/users`, {
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
        setUsers(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              Anoven · Admin
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Users
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              {users.length} users registrados.
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
              href="/dashboard"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Dashboard →
            </Link>
          </div>
        </header>

        {error && (
          <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
            {error}
          </p>
        )}

        <div className="overflow-x-auto rounded-xl border border-rule bg-paper-dim">
          <table className="w-full text-sm">
            <thead className="border-b border-rule text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              <tr>
                <th className="px-4 py-3 text-left">ID</th>
                <th className="px-4 py-3 text-left">User</th>
                <th className="px-4 py-3 text-left">Onboarding</th>
                <th className="px-4 py-3 text-right">Convs</th>
                <th className="px-4 py-3 text-right">Spend</th>
                <th className="px-4 py-3 text-left">Research</th>
                <th className="px-4 py-3 text-left">Rol</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-rule last:border-b-0">
                  <td className="px-4 py-3 font-mono text-xs text-ink-muted">
                    {u.id}
                  </td>
                  <td className="px-4 py-3">
                    <p className="font-serif text-base italic text-ink">
                      {u.nombre || u.email}
                    </p>
                    <p className="text-[11px] text-ink-muted">{u.email}</p>
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-soft">
                    {u.onboarding_state}
                    {u.onboarding_attempts > 1 && (
                      <span className="text-ink-muted"> · {u.onboarding_attempts} intentos</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink">
                    {u.conv_count}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink">
                    {fmtUSD(u.usd_spent)}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {u.research_opt_in ? (
                      <span className="rounded-full bg-leaf-soft px-2 py-0.5 text-[10px] uppercase tracking-wide text-leaf">
                        opt-in
                      </span>
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {u.role === "admin" ? (
                      <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] uppercase tracking-wide text-accent">
                        admin
                      </span>
                    ) : (
                      <span className="text-ink-muted">user</span>
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center font-serif italic text-ink-soft">
                    Sin users todavía.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
