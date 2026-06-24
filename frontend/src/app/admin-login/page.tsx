/**
 * /admin-login — login para el admin (admin@anoven.ai con password).
 *
 * Separado del Google OAuth porque el admin necesita login email+password.
 * Backend ya soporta POST /auth/login desde Fase 1.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { setToken } from "@/lib/auth";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@anoven.ai");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setToken(data.access_token);
      router.replace("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login falló");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="text-center">
          <p className="font-serif text-2xl italic tracking-tight text-ink">
            <span className="text-accent">❦</span> Anoven
          </p>
          <h1 className="mt-4 font-serif text-3xl font-medium tracking-tight text-ink">
            Admin
          </h1>
        </div>

        <form
          onSubmit={handleSubmit}
          className="mt-10 rounded-2xl border border-rule bg-paper-dim p-6"
        >
          <label className="block">
            <span className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Email
            </span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="mt-3 block">
            <span className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Password
            </span>
            <input
              type="password"
              required
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>

          {error && (
            <p className="mt-3 text-xs text-accent">{error}</p>
          )}

          <button
            type="submit"
            disabled={busy || !password.trim()}
            className="mt-5 w-full rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
          >
            {busy ? "Entrando..." : "Entrar como admin"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs">
          <Link
            href="/"
            className="text-ink-soft underline-offset-2 hover:text-accent hover:underline"
          >
            ← Volver al inicio
          </Link>
        </p>
      </div>
    </main>
  );
}
