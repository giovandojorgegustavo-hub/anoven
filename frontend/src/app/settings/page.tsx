/**
 * /settings — hub consolidado para el user logueado.
 *
 * Secciones:
 *   - Profile: email + nombre
 *   - Usage: turns 30d, total spend, conversaciones
 *   - Preferencias: rules + research opt-in (links a sub-páginas)
 *   - Logout
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import type { User } from "@/lib/user";

type Stats = {
  conversations: number;
  turns_total: number;
  turns_30d: number;
  usd_total: number;
  usd_30d: number;
};

function fmtUSD(v: number): string {
  if (v < 0.01 && v > 0) return "<$0.01";
  return `$${v.toFixed(2)}`;
}

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const [meRes, sRes, pRes] = await Promise.all([
          fetch(`${API_URL}/users/me`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/users/me/stats`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/users/me/pending-mentors`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);
        if (meRes.status === 401) {
          clearToken();
          router.replace("/");
          return;
        }
        if (!meRes.ok) throw new Error(`HTTP ${meRes.status}`);
        setUser(await meRes.json());
        if (sRes.ok) setStats(await sRes.json());
        if (pRes.ok) {
          const arr = await pRes.json();
          setPendingCount(Array.isArray(arr) ? arr.length : 0);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  function handleLogout() {
    clearToken();
    router.replace("/");
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-3xl">
          <header className="mb-10 border-b border-rule pb-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Tu cuenta
            </p>
            <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
              Configuración
            </h1>
          </header>

          {error && (
            <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
              {error}
            </p>
          )}

          {/* Profile */}
          <section className="animate-fade-in-up mb-6 rounded-xl border border-rule bg-paper-dim p-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Perfil
            </p>
            <h2 className="mt-1 font-serif text-2xl italic text-ink">
              {user?.nombre ?? "—"}
            </h2>
            <p className="mt-1 text-sm text-ink-soft">{user?.email ?? "—"}</p>
            {user?.role === "admin" && (
              <span className="mt-3 inline-block rounded-full bg-accent-soft px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent">
                Admin
              </span>
            )}
          </section>

          {/* Usage */}
          {stats && (
            <section
              className="animate-fade-in-up mb-6 rounded-xl border border-rule bg-paper-dim p-6"
              style={{ animationDelay: "60ms" }}
            >
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Uso
              </p>
              <h2 className="mt-1 font-serif text-2xl italic text-ink">
                Tus números
              </h2>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatBox label="Conversaciones" value={stats.conversations} />
                <StatBox label="Turns (30d)" value={stats.turns_30d} sub={`${stats.turns_total} total`} />
                <StatBox label="Costo (30d)" value={fmtUSD(stats.usd_30d)} accent />
                <StatBox label="Costo total" value={fmtUSD(stats.usd_total)} />
              </div>
            </section>
          )}

          {/* Preferencias */}
          <section
            className="animate-fade-in-up mb-6 rounded-xl border border-rule bg-paper-dim p-6"
            style={{ animationDelay: "120ms" }}
          >
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Preferencias
            </p>
            <h2 className="mt-1 font-serif text-2xl italic text-ink">
              Cómo te trata Anoven
            </h2>
            <ul className="mt-4 divide-y divide-rule">
              <PrefRow
                title="Mis reglas"
                desc="Instrucciones persistentes que los mentores respetan."
                href="/settings/rules"
              />
              <PrefRow
                title={
                  pendingCount > 0
                    ? `Mentores sugeridos · ${pendingCount}`
                    : "Mentores sugeridos"
                }
                desc={
                  pendingCount > 0
                    ? `Tenés ${pendingCount} mentor${pendingCount === 1 ? "" : "es"} pendiente${pendingCount === 1 ? "" : "s"} de armar con el Creador.`
                    : "Mentores que podrías querer crear con el Creador."
                }
                href="/settings/mentors-pending"
              />
              <PrefRow
                title="Investigación"
                desc={
                  user?.research_opt_in
                    ? "Aceptás que usemos tus charlas anonimizadas."
                    : "No aceptás — tus charlas quedan solo tuyas."
                }
                href="/settings/research"
              />
            </ul>
          </section>

          {/* Admin link si aplica */}
          {user?.role === "admin" && (
            <section
              className="animate-fade-in-up mb-6 rounded-xl border border-accent bg-accent-soft p-6"
              style={{ animationDelay: "180ms" }}
            >
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Panel admin
              </p>
              <h2 className="mt-1 font-serif text-2xl italic text-ink">
                Operación de Anoven
              </h2>
              <p className="mt-2 text-sm text-ink-soft">
                Métricas del sistema, cola de curación de mentores, y mentor
                requests pendientes.
              </p>
              <Link
                href="/admin"
                className="mt-4 inline-flex rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
              >
                Ir al panel admin →
              </Link>
            </section>
          )}

          {/* Logout */}
          <section className="animate-fade-in-up text-center" style={{ animationDelay: "240ms" }}>
            <button
              onClick={handleLogout}
              className="text-sm text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Cerrar sesión
            </button>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function StatBox({
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
    <div className={accent ? "rounded-lg border border-accent-soft bg-paper p-3" : "rounded-lg border border-rule bg-paper p-3"}>
      <p className="text-[10px] uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </p>
      <p className={accent ? "mt-1 font-serif text-xl font-medium text-accent" : "mt-1 font-serif text-xl font-medium text-ink"}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-[10px] text-ink-muted">{sub}</p>}
    </div>
  );
}

function PrefRow({
  title,
  desc,
  href,
}: {
  title: string;
  desc: string;
  href: string;
}) {
  return (
    <li className="flex items-center justify-between py-3">
      <div>
        <p className="font-serif text-base italic text-ink">{title}</p>
        <p className="mt-0.5 text-xs text-ink-soft">{desc}</p>
      </div>
      <Link
        href={href}
        className="text-sm text-ink-soft underline-offset-2 hover:text-accent hover:underline"
      >
        Configurar →
      </Link>
    </li>
  );
}
